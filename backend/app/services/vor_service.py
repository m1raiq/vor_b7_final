import io
import uuid
from typing import Optional

import pandas as pd
from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models.project import Project
from app.models.vor_item import VorItem
from app.utils.normalization import norm_text, norm_unit, parse_num


def _is_service_row(name_norm: str) -> bool:
    if not name_norm:
        return True
    bad_starts = (
        "итого",
        "всего",
        "отклон",
        "итого выполн",
        "итого по",
    )
    bad_contains = (
        "отклон",
        "итого выполн",
    )
    if any(name_norm.startswith(x) for x in bad_starts):
        return True
    if any(x in name_norm for x in bad_contains):
        return True
    return False


def _find_header_row(df_raw: pd.DataFrame, max_scan: int = 60) -> Optional[int]:
    keys = [
        "наимен",
        "ед",
        "изм",
        "кол",
        "work",
        "name",
        "unit",
        "plan",
        "volume",
        "qty",
        "quantity",
    ]
    best_i, best_score = None, -1

    scan = min(max_scan, len(df_raw))
    for i in range(scan):
        row_vals = df_raw.iloc[i].tolist()
        row_text = " ".join(
            [str(x).strip().lower() for x in row_vals if str(x).strip().lower() not in {"nan", ""}]
        )
        score = sum(1 for k in keys if k in row_text)
        if "work name" in row_text:
            score += 2
        if "plan volume" in row_text:
            score += 2
        if "qty" in row_text or "quantity" in row_text:
            score += 1
        if score > best_score:
            best_score = score
            best_i = i

    return best_i if best_score >= 3 else None


def _detect_columns(df: pd.DataFrame) -> tuple[str, str, str]:
    normalized = {str(c).strip().lower(): str(c) for c in df.columns}
    cleaned = {k: " ".join(k.replace("_", " ").replace(".", " ").split()) for k in normalized.keys()}

    name_col = None
    for k, orig in normalized.items():
        kc = cleaned.get(k, k)
        if "наимен" in kc or "work name" in kc or kc == "work" or ("work" in kc and "name" in kc):
            name_col = orig
            break

    unit_col = None
    for k, orig in normalized.items():
        kc = cleaned.get(k, k)
        if (
            ("ед" in kc and "изм" in kc)
            or "ед.изм" in kc
            or "едизм" in kc
            or "ед изм" in kc
            or kc == "unit"
            or "unit" in kc
        ):
            unit_col = orig
            break

    plan_col = None
    for k, orig in normalized.items():
        kc = cleaned.get(k, k)
        if (
            ("кол" in kc and "проект" in kc)
            or "по проект" in kc
            or ("plan" in kc and "volume" in kc)
            or kc == "plan"
            or kc == "qty"
            or "quantity" in kc
        ):
            plan_col = orig
            break

    if not plan_col:
        for k, orig in normalized.items():
            kc = cleaned.get(k, k)
            if "итого" in kc or "выполн" in kc or "отклон" in kc:
                continue
            if (
                "кол-во" in kc
                or "колво" in kc
                or "кол во" in kc
                or kc.startswith("кол")
                or "количество" in kc
                or "объем" in kc
                or "объём" in kc
                or "plan" in kc
                or "volume" in kc
                or "qty" in kc
                or "quantity" in kc
            ):
                plan_col = orig
                break

    if not name_col or not unit_col or not plan_col:
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Не найдены обязательные колонки ВОР (лист 1).",
                "found_columns": list(df.columns),
                "needed": [
                    "Наименование видов работ / Work Name",
                    "Ед. изм. / Unit",
                    "Кол-во по проекту / Plan Volume / Qty",
                ],
            },
        )

    return name_col, unit_col, plan_col


def upload_vor_service(
    project_id: uuid.UUID,
    file_bytes: bytes,
    db: Session,
    filename: str | None = None,
):
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    try:
        df_raw = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=None)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Cannot read Excel (sheet 1): {e}")

    header_i = _find_header_row(df_raw)
    if header_i is None:
        preview = df_raw.head(12).fillna("").astype(str).values.tolist()
        raise HTTPException(
            status_code=400,
            detail={
                "msg": "Не удалось найти строку заголовков в первых строках ВОР (лист 1).",
                "preview_first_12_rows": preview,
            },
        )

    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=0, header=header_i)
    df = df.dropna(axis=1, how="all")

    name_col, unit_col, plan_col = _detect_columns(df)

    df = df[[name_col, unit_col, plan_col]].copy()
    df.columns = ["work_name", "unit", "plan_volume"]

    df["work_name"] = df["work_name"].astype(str).str.strip()
    df["unit"] = df["unit"].astype(str).str.strip()

    df.loc[df["work_name"].str.lower().isin({"nan", "none", ""}), "work_name"] = None
    df.loc[df["unit"].str.lower().isin({"nan", "none"}), "unit"] = ""

    df["_plan_parsed"] = df["plan_volume"].apply(parse_num)
    has_plan = df["_plan_parsed"].notna()

    mask_cont = df["work_name"].isna() & has_plan
    df["_ffill"] = df["work_name"].ffill()
    df.loc[mask_cont, "work_name"] = df.loc[mask_cont, "_ffill"]
    df = df.drop(columns=["_ffill"])

    df = df[df["work_name"].notna()]
    df = df[df["work_name"].astype(str).str.len() > 0]

    db.execute(delete(VorItem).where(VorItem.project_id == project_id))

    inserted = 0
    skipped_service = 0
    skipped_no_volume = 0

    for _, row in df.iterrows():
        work_name = str(row["work_name"]).strip()
        unit = str(row["unit"] or "").strip()

        name_norm = norm_text(work_name)
        unit_norm = norm_unit(unit)

        plan_volume = row.get("_plan_parsed")
        if isinstance(plan_volume, float) and pd.isna(plan_volume):
            plan_volume = None

        if _is_service_row(name_norm):
            skipped_service += 1
            continue

        if plan_volume is None:
            skipped_no_volume += 1
            continue

        item = VorItem(
            project_id=project_id,
            work_name=work_name,
            work_name_norm=name_norm,
            unit=unit or None,
            unit_norm=unit_norm or None,
            plan_volume=plan_volume,
        )

        db.add(item)
        inserted += 1

    db.commit()

    return {
        "status": "ok",
        "inserted": inserted,
        "header_row_detected": header_i + 1,
        "columns_used": {"name": name_col, "unit": unit_col, "plan": plan_col},
        "skipped_service_rows": skipped_service,
        "skipped_rows_without_volume": skipped_no_volume,
    }


def upload_vor_rows_service(
    project_id: uuid.UUID,
    rows: list[dict],
    db: Session,
):
    project = db.execute(select(Project).where(Project.id == project_id)).scalar_one_or_none()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    if not rows:
        raise HTTPException(status_code=400, detail="No rows to upload")

    df = pd.DataFrame(rows or [])
    if "work_name" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing work_name in uploaded rows")
    if "unit" not in df.columns:
        df["unit"] = ""
    if "plan_volume" not in df.columns:
        raise HTTPException(status_code=400, detail="Missing plan_volume in uploaded rows")

    df = df[["work_name", "unit", "plan_volume"]].copy()
    df["work_name"] = df["work_name"].astype(str).str.strip()
    df["unit"] = df["unit"].astype(str).str.strip()
    df.loc[df["work_name"].str.lower().isin({"nan", "none", ""}), "work_name"] = None
    df.loc[df["unit"].str.lower().isin({"nan", "none"}), "unit"] = ""
    df["_plan_parsed"] = df["plan_volume"].apply(parse_num)
    df = df[df["work_name"].notna()]
    df = df[df["work_name"].astype(str).str.len() > 0]

    db.execute(delete(VorItem).where(VorItem.project_id == project_id))

    inserted = 0
    skipped_service = 0
    skipped_no_volume = 0
    for _, row in df.iterrows():
        work_name = str(row["work_name"]).strip()
        unit = str(row["unit"] or "").strip()
        name_norm = norm_text(work_name)
        unit_norm = norm_unit(unit)
        plan_volume = row.get("_plan_parsed")
        if isinstance(plan_volume, float) and pd.isna(plan_volume):
            plan_volume = None

        if _is_service_row(name_norm):
            skipped_service += 1
            continue
        if plan_volume is None:
            skipped_no_volume += 1
            continue

        db.add(
            VorItem(
                project_id=project_id,
                work_name=work_name,
                work_name_norm=name_norm,
                unit=unit or None,
                unit_norm=unit_norm or None,
                plan_volume=plan_volume,
            )
        )
        inserted += 1

    db.commit()
    return {
        "status": "ok",
        "inserted": inserted,
        "source": "pdf",
        "skipped_service_rows": skipped_service,
        "skipped_rows_without_volume": skipped_no_volume,
    }
