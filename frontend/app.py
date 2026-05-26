# -*- coding: utf-8 -*-
import pandas as pd
import requests
import streamlit as st
 
API_BASE = "http://127.0.0.1:8000"
 
 
# -------------------------
# HTTP helpers (backward-compatible, НЕ ломает текущие вызовы)
# -------------------------
def api_get(path: str, kwargs=None, **kw):
    merged = {}
    if isinstance(kwargs, dict):
        merged.update(kwargs)
    merged.update(kw)
    headers = dict(merged.pop("headers", {}) or {})
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers:
        merged["headers"] = headers
    return requests.get(f"{API_BASE}{path}", timeout=60, **merged)
 
 
def api_post(path: str, kwargs=None, **kw):
    merged = {}
    if isinstance(kwargs, dict):
        merged.update(kwargs)
    merged.update(kw)
    add_auth = bool(merged.pop("add_auth", True))
    headers = dict(merged.pop("headers", {}) or {})
    token = st.session_state.get("auth_token")
    if add_auth and token:
        headers["Authorization"] = f"Bearer {token}"
    if headers:
        merged["headers"] = headers
    timeout = merged.pop("timeout", 180)
    return requests.post(f"{API_BASE}{path}", timeout=timeout, **merged)
 
 
def api_delete(path: str, kwargs=None, **kw):
    merged = {}
    if isinstance(kwargs, dict):
        merged.update(kwargs)
    merged.update(kw)
    headers = dict(merged.pop("headers", {}) or {})
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers:
        merged["headers"] = headers
    return requests.delete(f"{API_BASE}{path}", timeout=60, **merged)


def api_patch(path: str, kwargs=None, **kw):
    merged = {}
    if isinstance(kwargs, dict):
        merged.update(kwargs)
    merged.update(kw)
    headers = dict(merged.pop("headers", {}) or {})
    token = st.session_state.get("auth_token")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if headers:
        merged["headers"] = headers
    return requests.patch(f"{API_BASE}{path}", timeout=60, **merged)
 
 
def api_ok(r: requests.Response) -> bool:
    return r is not None and r.status_code == 200
 
 
def show_api_error(prefix: str, r: requests.Response):
    try:
        st.error(f"{prefix}: {r.status_code} — {r.json()}")
    except Exception:
        st.error(f"{prefix}: {r.status_code} — {r.text}")


def auth_login(login: str, password: str) -> tuple[bool, str]:
    try:
        r = api_post("/auth/login", json={"login": login, "password": password}, add_auth=False)
    except requests.exceptions.RequestException as e:
        return False, f"Ошибка соединения с backend: {e}"
    if not api_ok(r):
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        return False, f"Ошибка входа: {detail}"
    data = r.json() or {}
    token = data.get("access_token")
    if not token:
        return False, "Токен не получен"
    st.session_state["auth_token"] = token
    st.session_state["auth_user"] = {
        "login": data.get("login") or data.get("email"),
        "role": data.get("role"),
        "full_name": data.get("full_name") or "",
    }
    return True, ""


def auth_register(login: str, password: str, full_name: str) -> tuple[bool, str]:
    try:
        r = api_post(
            "/auth/register",
            json={"login": login, "password": password, "full_name": full_name},
            add_auth=False,
        )
    except requests.exceptions.RequestException as e:
        return False, f"Ошибка соединения с backend: {e}"
    if not api_ok(r):
        try:
            detail = r.json()
        except Exception:
            detail = r.text
        return False, f"Ошибка регистрации: {detail}"
    return True, ""
 
 
# -------------------------
# UI helpers
# -------------------------
def df_safe(data) -> pd.DataFrame:
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data)
 
 
def prettify_matching_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
 
    df = df.copy()
 
    rename_map = {
        "report_date": "Дата отчёта",
        "section_title": "Секция",
        "work_name": "Работа (Б.7)",
        "unit": "Ед. изм. (Б.7)",
        "fact_week": "Факт за неделю",
        "status": "Статус",
        "match_type": "Тип",
        "fuzzy_score": "Fuzzy %",
        "vor_work_name": "Кандидат ВОР",
        "vor_unit": "Ед. изм. (ВОР)",
    }
    for k, v in rename_map.items():
        if k in df.columns:
            df.rename(columns={k: v}, inplace=True)
 
    if "Факт за неделю" in df.columns:
        df["Факт за неделю"] = pd.to_numeric(df["Факт за неделю"], errors="coerce").round(3)
 
    if "Fuzzy %" in df.columns:
        df["Fuzzy %"] = pd.to_numeric(df["Fuzzy %"], errors="coerce").round(1)
 
    preferred = [
        "Дата отчёта",
        "Секция",
        "Работа (Б.7)",
        "Ед. изм. (Б.7)",
        "Факт за неделю",
        "Статус",
        "Тип",
        "Fuzzy %",
        "Кандидат ВОР",
        "Ед. изм. (ВОР)",
    ]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
 
    tech_cols = {"b7_row_id", "section_id", "vor_id_candidate", "b7_match_key", "unit_original", "fact_week_original"}
    for tc in list(tech_cols):
        if tc in df.columns:
            df.drop(columns=[tc], inplace=True)
 
    cols = [c for c in cols if c in df.columns]
    return df[cols]
 
 
def prettify_vor_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    keep = [c for c in ["work_name", "unit", "plan_volume"] if c in df.columns]
    df = df[keep]
    df.rename(
        columns={
            "work_name": "Работа (ВОР)",
            "unit": "Ед. изм.",
            "plan_volume": "Объём по проекту",
        },
        inplace=True,
    )
    if "Объём по проекту" in df.columns:
        df["Объём по проекту"] = pd.to_numeric(df["Объём по проекту"], errors="coerce").round(3)
    return df
 
 
def prettify_b7_rows_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
 
    for c in ["id", "project_id", "report_id", "section_id", "work_name_norm", "unit_norm", "created_at"]:
        if c in df.columns:
            df.drop(columns=[c], inplace=True)
 
    rename_map = {
        "report_date": "Дата отчёта",
        "section_title": "Секция",
        "work_name": "Работа",
        "unit": "Ед. изм.",
        "fact_week": "Факт за неделю",
    }
    for k, v in rename_map.items():
        if k in df.columns:
            df.rename(columns={k: v}, inplace=True)
 
    if "Факт за неделю" in df.columns:
        df["Факт за неделю"] = pd.to_numeric(df["Факт за неделю"], errors="coerce").round(3)
 
    preferred = ["Дата отчёта", "Секция", "Работа", "Ед. изм.", "Факт за неделю"]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    return df[cols]
 
 
def prettify_sections_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    for c in ["id", "project_id", "report_id", "title_norm"]:
        if c in df.columns:
            df.drop(columns=[c], inplace=True)
 
    if "title" in df.columns:
        df.rename(columns={"title": "Секция"}, inplace=True)
    if "row_index" in df.columns:
        df.rename(columns={"row_index": "Позиция (в листе)"}, inplace=True)
 
    preferred = ["Позиция (в листе)", "Секция"]
    cols = [c for c in preferred if c in df.columns] + [c for c in df.columns if c not in preferred]
    return df[cols]
 
 
# -------------------------
# Styling helpers
# -------------------------
def style_status_column(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df.empty or "Статус" not in df.columns:
        return df.style
 
    def _cell_style(val):
        status = str(val or "").upper()
        if status == "MATCHED":
            return "color: #1b5e20; font-weight: 600;"
        if status == "UNIT_MISMATCH":
            return "color: #b26a00; font-weight: 600;"
        if status == "UNMATCHED":
            return "color: #b00020; font-weight: 600;"
        return ""
 
    styler = df.style.map(_cell_style, subset=["Статус"])
    styler = styler.set_properties(
        **{
            "white-space": "pre-wrap",
            "font-size": "13px",
        }
    )
    return styler
 
 
def style_b7_fact_week(df: pd.DataFrame) -> "pd.io.formats.style.Styler":
    if df.empty:
        return df.style
 
    col = "Факт за неделю"
    if col not in df.columns:
        return df.style
 
    def _style_week(v) -> str:
        try:
            x = float(v)
            if x == 0.0:
                return "color: #777;"
            return ""
        except Exception:
            return "color: #777;"
 
    styler = df.style.map(_style_week, subset=[col])
    styler = styler.set_properties(**{"white-space": "pre-wrap"})
    return styler


def render_summary_charts(
    df_summary: pd.DataFrame,
    weeks_items: list,
    weeks_cols: list,
    months_items: list,
    months_cols: list,
):
    st.markdown("### Графики")

    if not df_summary.empty:
        c1, c2, c3 = st.columns(3)
        total_plan = float(pd.to_numeric(df_summary.get("План с начала строительства"), errors="coerce").fillna(0).sum())
        total_fact = float(pd.to_numeric(df_summary.get("Факт с начала строительства"), errors="coerce").fillna(0).sum())
        total_delta_abs = float(pd.to_numeric(df_summary.get("Дельта (План - Факт), абс."), errors="coerce").fillna(0).sum())
        completion_pct = (total_fact / total_plan * 100.0) if total_plan > 0 else 0.0
        c1.metric("План (сумма)", f"{total_plan:,.2f}")
        c2.metric("Факт (сумма)", f"{total_fact:,.2f}")
        c3.metric("Выполнение, %", f"{completion_pct:,.2f}%")

        top_col = "Дельта (План - Факт), абс."
        if top_col in df_summary.columns and "Работа (ВОР)" in df_summary.columns:
            top_df = df_summary[["Работа (ВОР)", top_col]].copy()
            top_df[top_col] = pd.to_numeric(top_df[top_col], errors="coerce")
            top_df = top_df.dropna(subset=[top_col])
            if not top_df.empty:
                top_df["|Δ|"] = top_df[top_col].abs()
                top_df = top_df.sort_values("|Δ|", ascending=False).head(10)
                top_df = top_df.set_index("Работа (ВОР)")[[top_col]]
                st.caption("ТОП-10 работ по абсолютному отклонению плана и факта")
                st.bar_chart(top_df, use_container_width=True)

        if {"План с начала строительства", "Факт с начала строительства"}.issubset(df_summary.columns):
            pf_df = df_summary[["План с начала строительства", "Факт с начала строительства"]].copy()
            pf_df["План с начала строительства"] = pd.to_numeric(pf_df["План с начала строительства"], errors="coerce")
            pf_df["Факт с начала строительства"] = pd.to_numeric(pf_df["Факт с начала строительства"], errors="coerce")
            pf_df = pf_df.dropna(how="all")
            if not pf_df.empty:
                st.caption("Распределение по работам: план vs факт")
                st.bar_chart(pf_df, use_container_width=True)

    if weeks_items and weeks_cols:
        week_points = []
        for w in weeks_cols:
            total = 0.0
            for item in weeks_items:
                total += float((item.get("weeks") or {}).get(w, 0.0) or 0.0)
            week_points.append({"Неделя": str(w), "Факт за неделю": total})
        df_week_trend = pd.DataFrame(week_points)
        if not df_week_trend.empty:
            st.caption("Динамика общего факта по неделям")
            st.line_chart(df_week_trend.set_index("Неделя"), use_container_width=True)

    if months_items and months_cols:
        month_points = []
        for m in months_cols:
            total = 0.0
            for item in months_items:
                total += float((item.get("months") or {}).get(m, 0.0) or 0.0)
            month_points.append({"Месяц": str(m), "Факт за месяц": total})
        df_month_trend = pd.DataFrame(month_points)
        if not df_month_trend.empty:
            st.caption("Динамика общего факта по месяцам")
            st.line_chart(df_month_trend.set_index("Месяц"), use_container_width=True)
# -------------------------
# pdf
# -------------------------
def tab_b7_pdf_preview(project_id: str):
    st.subheader("6) Б.7 PDF — Предпросмотр (OCR)")
    st.caption("Сначала распознайте PDF и проверьте таблицу. Затем нажмите «Загрузить в БД».")

    report_date_pdf = st.date_input("Дата отчёта (PDF, предпросмотр)", key="pdf_report_date")
    pdf_file = st.file_uploader("PDF файл Б.7", type=["pdf"], key="b7_pdf_file")
    report_date_pdf_str = str(report_date_pdf)

    existing_report_same_date = False
    existing_report_name = None
    rr = api_get(f"/projects/{project_id}/b7/reports", {})
    if api_ok(rr):
        for rep in rr.json() or []:
            if str(rep.get("report_date") or "") == report_date_pdf_str:
                existing_report_same_date = True
                existing_report_name = rep.get("source_filename") or "-"
                break

    c1, c2, c3 = st.columns([1, 1, 3])
    with c1:
        do_ocr = st.button("Распознать PDF", key="run_pdf_ocr_btn")
    with c2:
        do_save_db = st.button("Загрузить в БД", key="upload_pdf_preview_to_db_btn", disabled=not can_edit)
    with c3:
        st.caption("Загрузка в БД берёт текущий предпросмотр и не запускает OCR повторно.")

    allow_replace_existing = True
    if existing_report_same_date:
        st.warning("На эту дату уже загружен отчёт. Вы уверены, что хотите загрузить новый и удалить предыдущий?")
        st.caption(f"Текущий отчёт за {report_date_pdf_str}: {existing_report_name}")
        allow_replace_existing = st.checkbox(
            "Подтверждаю перезапись отчёта за выбранную дату",
            key=f"confirm_replace_b7_pdf_{project_id}_{report_date_pdf_str}",
        )

    if not do_ocr and not do_save_db:
        last = st.session_state.get("pdf_preview_last")
        if last:
            _render_pdf_preview_result(last)
        return

    if do_save_db:
        if not can_edit:
            st.warning("Недостаточно прав: загрузка в БД доступна только editor/admin.")
            return
        if existing_report_same_date and not allow_replace_existing:
            st.warning("Подтвердите перезапись отчёта за выбранную дату и повторите загрузку.")
            return

        last = st.session_state.get("pdf_preview_last") or {}
        last_rows = last.get("rows") or []
        last_date = str(last.get("_report_date") or "")
        last_project = str(last.get("_project_id") or "")
        if not last_rows:
            st.warning("Сначала нажмите «Распознать PDF», чтобы получить предпросмотр.")
            return
        if last_project != str(project_id) or last_date != report_date_pdf_str:
            st.warning("Распознайте PDF заново для текущего проекта и выбранной даты.")
            return

        json_payload = {
            "rows": last_rows,
            "source_filename": last.get("_source_filename") or "b7_report.pdf",
        }
        with st.spinner("Загружаю в БД..."):
            try:
                r = api_post(
                    f"/projects/{project_id}/b7/upload_pdf_rows",
                    json=json_payload,
                    params={"report_date": report_date_pdf_str},
                    timeout=180,
                )
            except requests.exceptions.RequestException as e:
                st.error(f"Ошибка соединения с backend: {e}")
                return

        if not api_ok(r):
            show_api_error("Ошибка загрузки в БД", r)
            return

        payload = r.json() or {}
        st.success(
            f"Сохранено в БД: report_id={payload.get('report_id')} | "
            f"rows={payload.get('inserted_rows')}"
        )
        return

    if not pdf_file:
        st.warning("Выберите PDF-файл.")
        return

    files = {
        "file": (
            pdf_file.name,
            pdf_file.getvalue(),
            "application/pdf",
        )
    }
    params = {"report_date": report_date_pdf_str}

    with st.spinner("Запускаю OCR..."):
        r = api_post(f"/projects/{project_id}/b7_pdf/upload_pdf_preview", files=files, params=params, timeout=420)

    if not api_ok(r):
        show_api_error("Ошибка PDF OCR", r)
        return

    payload = r.json() or {}
    payload["_report_date"] = report_date_pdf_str
    payload["_project_id"] = str(project_id)
    payload["_source_filename"] = pdf_file.name
    st.session_state["pdf_preview_last"] = payload
    _render_pdf_preview_result(payload)


def _render_pdf_preview_result(payload: dict):
    st.success(f"OCR выполнен. Распознано строк: {payload.get('recognized_rows', 0)}")

    rows = payload.get("rows") or []
    if rows:
        df = pd.DataFrame(rows)

        # чуть приведём колонки к привычному виду
        rename = {
            "no": "№",
            "work_name": "Наименование работ",
            "unit": "Ед. изм.",
            "fact_week": "Факт за неделю",
            "section_title": "Секция",
        }
        for k, v in rename.items():
            if k in df.columns:
                df.rename(columns={k: v}, inplace=True)

        if "Факт за неделю" in df.columns:
            df["Факт за неделю"] = pd.to_numeric(df["Факт за неделю"], errors="coerce").round(3)

        st.dataframe(df, use_container_width=True, height=520)

        csv = df.to_csv(index=False).encode("utf-8-sig")
        st.download_button(
            "Скачать распознанное (CSV)",
            data=csv,
            file_name="b7_pdf_preview.csv",
            mime="text/csv",
        )
    else:
        st.info("Строки не вернулись (rows пустые).")

    dbg = payload.get("debug")

    if dbg:
        with st.expander("Debug (по страницам)"):

            # raw debug
            raw_dbg = dbg.get("raw")
            if raw_dbg:
                st.markdown("### Raw OCR debug")
                try:
                    st.dataframe(pd.DataFrame(raw_dbg))
                except Exception:
                    st.json(raw_dbg)

            # parsed debug
            parsed_dbg = dbg.get("parsed")
            if parsed_dbg:
                st.markdown("### Parsed table debug")
                try:
                    st.dataframe(pd.DataFrame([parsed_dbg]))
                except Exception:
                    st.json(parsed_dbg)

# -------------------------
# Page
# -------------------------
st.set_page_config(page_title="VOR / B7", layout="wide")
st.title("VOR / B7")
st.markdown(
    """
    <style>
    .block-container { padding-top: 2.8rem; padding-bottom: 1.4rem; }
    div[data-testid="stMetricValue"] { font-size: 1.8rem; }
    div[data-testid="stAlert"] { border-radius: 12px; }
    div[data-baseweb="tab-list"] {
        gap: 0.65rem;
        margin-top: 0.6rem;
        margin-bottom: 0.25rem;
        border-bottom: 1px solid rgba(250, 250, 250, 0.14);
    }
    button[data-baseweb="tab"] {
        padding: 0.48rem 0.9rem;
        min-height: 2.3rem;
        border-radius: 10px 10px 0 0;
        border: 1px solid transparent;
        font-weight: 600;
        letter-spacing: 0.01em;
    }
    button[data-baseweb="tab"]:hover {
        background: rgba(255, 255, 255, 0.06);
        border-color: rgba(255, 255, 255, 0.12);
    }
    button[data-baseweb="tab"][aria-selected="true"] {
        background: rgba(255, 255, 255, 0.10);
        border-color: rgba(255, 255, 255, 0.22);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

if "auth_token" not in st.session_state:
    st.session_state["auth_token"] = ""
if "auth_user" not in st.session_state:
    st.session_state["auth_user"] = {}
if not st.session_state.get("_summary_v2_cleanup_done"):
    for k in ["summary_df", "summary_details_df", "summary_weeks_payload", "summary_months_payload"]:
        st.session_state.pop(k, None)
    st.session_state["_summary_v2_cleanup_done"] = True

if not st.session_state["auth_token"]:
    st.subheader("Вход")
    st.caption("Самостоятельная регистрация отключена. Обратитесь к администратору для создания пользователя.")
    with st.form("login_form", clear_on_submit=False):
        login_val = st.text_input("Логин", value="")
        password = st.text_input("Пароль", type="password")
        submitted = st.form_submit_button("Войти")
    if submitted:
        ok, err = auth_login(login=login_val.strip(), password=password)
        if ok:
            st.success("Вход выполнен")
            st.rerun()
        else:
            st.error(err)
    st.stop()

auth_user = st.session_state.get("auth_user") or {}
try:
    me_resp = api_get("/auth/me")
except requests.exceptions.RequestException as e:
    st.error(f"Ошибка соединения с backend: {e}")
    st.stop()
if not api_ok(me_resp):
    st.session_state["auth_token"] = ""
    st.session_state["auth_user"] = {}
    st.warning("Сессия истекла. Войдите снова.")
    st.rerun()
auth_user = me_resp.json() or auth_user
st.session_state["auth_user"] = auth_user
role_name = str(auth_user.get("role", "")).lower()
is_admin = role_name == "admin"
is_editor = role_name == "editor"
can_edit = is_admin or is_editor
st.sidebar.markdown(f"**Пользователь:** {auth_user.get('login', auth_user.get('email','—'))}")
st.sidebar.caption(f"Роль: {auth_user.get('role','user')}")
if st.sidebar.button("Выйти", key="logout_btn"):
    st.session_state["auth_token"] = ""
    st.session_state["auth_user"] = {}
    st.rerun()
 
# =========================
# Sidebar: Project select/create
# =========================
st.sidebar.header("Проект")
 
with st.sidebar.expander("Создать проект", expanded=False):
    if not is_admin:
        st.caption("Только администратор может создавать проекты.")
    else:
        new_name = st.text_input("Название проекта", key="new_project_name")
        if st.button("Создать", key="create_project_btn"):
            if not new_name.strip():
                st.warning("Введите название проекта.")
            else:
                r = api_post("/projects", json={"name": new_name.strip()})
                if api_ok(r):
                    st.success("Проект создан.")
                    st.session_state["refresh_projects"] = True
                else:
                    show_api_error("Ошибка создания проекта", r)
 
r = api_get("/projects")
projects = r.json() if api_ok(r) else []
if not projects:
    st.info("Проекты пока не созданы. Создайте проект слева.")
    st.stop()
 
project_options = {f'{p["name"]}': p["id"] for p in projects}
project_name = st.sidebar.selectbox("Выберите проект", list(project_options.keys()))
project_id = project_options[project_name]
st.sidebar.caption(f"ID проекта: {project_id}")
 
# =========================
# Sidebar: B7 reports list + selector
# =========================
st.sidebar.divider()
st.sidebar.subheader("B.7 отчёты в проекте")

rr = api_get(f"/projects/{project_id}/b7/reports", {})
reports = rr.json() if api_ok(rr) else []

if not reports:
    st.sidebar.caption("Пока нет загруженных отчётов B.7.")
    selected_report_id = None
else:
    def _label(r):
        d = r.get("report_date") or "—"
        fn = r.get("source_filename") or "—"
        return f"{d} — {fn}"

    options = { _label(r): r for r in reports }

    labels = list(options.keys())
    default_idx = max(0, len(labels) - 1)

    selected_label = st.sidebar.selectbox(
        "Выберите отчёт B.7",
        labels,
        index=default_idx,
        key="b7_report_select",
    )
    selected_report_id = options[selected_label]["id"]
    selected_report_date = options[selected_label].get("report_date")

    st.sidebar.markdown("### Удаление отчёта")
    st.sidebar.caption("Удалит разделы и строки этого отчёта B.7.")

    confirm_delete = st.sidebar.checkbox(
        f"Подтверждаю удаление отчёта {selected_report_date}",
        value=False,
        disabled=not can_edit,
        key="confirm_delete_b7_report",
    )

    if st.sidebar.button("Удалить выбранный отчёт", disabled=not (confirm_delete and can_edit), key="delete_b7_report_btn"):
        if not can_edit:
            st.sidebar.warning("Удаление доступно только editor/admin.")
            st.stop()
        resp = api_delete(f"/projects/{project_id}/b7/reports/{selected_report_id}")
        if api_ok(resp):
            st.sidebar.success("Отчёт удалён.")
            st.rerun()
        else:
            show_api_error("Ошибка удаления отчёта", resp)

st.caption("Рабочий контур: загрузка данных → проверка → сопоставление → свод.")
meta1, meta2, meta3 = st.columns(3)
meta1.metric("Проект", project_name)
meta2.metric("Отчётов B.7", len(reports))
meta3.metric("Роль", str(auth_user.get("role", "user")))
 
tab_specs = []
if can_edit:
    tab_specs.append(("upload", "1) Загрузка"))
tab_specs.extend(
    [
        ("view", "2) Данные"),
        ("matching", "3) Сопоставление"),
    ]
)
if can_edit:
    tab_specs.append(("manual", "4) Ручное подтверждение"))
tab_specs.extend(
    [
        ("summary", "5) Свод"),
    ]
)
if can_edit:
    tab_specs.append(("ocr", "6) OCR PDF"))
if is_admin:
    tab_specs.append(("users", "7) Пользователи"))

tabs = st.tabs([title for _, title in tab_specs])
tab_by_key = {key: tabs[idx] for idx, (key, _) in enumerate(tab_specs)}
hidden_tab_slots = []
tab_ctx = {}
for key in ["upload", "view", "matching", "manual", "summary", "ocr", "users"]:
    if key in tab_by_key:
        tab_ctx[key] = tab_by_key[key]
    else:
        slot = st.empty()
        hidden_tab_slots.append(slot)
        tab_ctx[key] = slot.container()
 
 
# =========================
# TAB 1: Upload
# =========================
with tab_ctx["upload"]:
    st.subheader("1) Загрузка исходных файлов")
    st.caption("Загрузите ВОР и Б.7 для выбранного проекта и даты отчёта.")
 
    c1, c2 = st.columns(2)
 
    with c1:
        st.markdown("### ВОР")
        vor_file = st.file_uploader("Файл ВОР (.xlsx)", type=["xlsx"], key="vor_file")
        vor_pdf_file = st.file_uploader("Файл ВОР (.pdf)", type=["pdf"], key="vor_pdf_file")
        if st.button("Загрузить ВОР", key="upload_vor_btn", disabled=not can_edit):
            if not can_edit:
                st.warning("Загрузка доступна только editor/admin.")
                st.stop()
            if not vor_file:
                st.warning("Выберите файл ВОР.")
            else:
                files = {
                    "file": (
                        vor_file.name,
                        vor_file.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }
                r = api_post(f"/projects/{project_id}/vor/upload", files=files)
                if api_ok(r):
                    j = r.json()
                    st.success(f"ВОР загружен: {j.get('inserted', '—')} строк.")
                    st.caption(
                        f"Пропущено сервисных: {j.get('skipped_service_rows', '—')}, "
                        f"без объёма: {j.get('skipped_rows_without_volume', '—')}"
                    )
                else:
                    show_api_error("Ошибка загрузки ВОР", r)
        if st.button("Загрузить ВОР из PDF", key="upload_vor_pdf_btn", disabled=not can_edit):
            if not can_edit:
                st.warning("Загрузка доступна только editor/admin.")
                st.stop()
            if not vor_pdf_file:
                st.warning("Выберите PDF-файл ВОР.")
            else:
                files = {"file": (vor_pdf_file.name, vor_pdf_file.getvalue(), "application/pdf")}
                r = api_post(f"/projects/{project_id}/vor/upload_pdf", files=files, timeout=420)
                if api_ok(r):
                    j = r.json()
                    st.success(f"ВОР (PDF) загружен: {j.get('inserted', '—')} строк.")
                    st.caption(
                        f"Распознано строк: {j.get('recognized_rows', '—')}; "
                        f"пропущено сервисных: {j.get('skipped_service_rows', '—')}; "
                        f"без объёма: {j.get('skipped_rows_without_volume', '—')}"
                    )
                else:
                    show_api_error("Ошибка загрузки ВОР из PDF", r)
 
    with c2:
        st.markdown("### Б.7")
        report_date = st.date_input("Дата отчёта (для Б.7)", key="report_date")
        b7_file = st.file_uploader("Файл Б.7 (.xlsx)", type=["xlsx"], key="b7_file")
 
        if st.button("Загрузить Б.7", key="upload_b7_btn", disabled=not can_edit):
            if not can_edit:
                st.warning("Загрузка доступна только editor/admin.")
                st.stop()
            if not b7_file:
                st.warning("Выберите файл Б.7.")
            else:
                files = {
                    "file": (
                        b7_file.name,
                        b7_file.getvalue(),
                        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    )
                }
                r = api_post(
                    f"/projects/{project_id}/b7/upload",
                    files=files,
                    params={"report_date": str(report_date)},
                )
                if api_ok(r):
                    j = r.json()
                    st.success(
                        f"Б.7 загружен: {j.get('inserted_rows', '—')} строк, "
                        f"секций: {j.get('inserted_sections', '—')}."
                    )
                else:
                    show_api_error("Ошибка загрузки Б.7", r)
 
 
# =========================
# TAB 2: View data
# =========================
with tab_ctx["view"]:
    st.subheader("2) Просмотр данных")
    st.caption("Проверка загруженных данных перед сопоставлением.")
 
    colA, colB, colC = st.columns(3)
 
    with colA:
        if st.button("Показать ВОР", key="show_vor_btn"):
            r = api_get(f"/projects/{project_id}/vor")
            if api_ok(r):
                df = prettify_vor_df(df_safe(r.json()))
                st.session_state["vor_df"] = df
            else:
                show_api_error("Ошибка", r)
 
    with colB:
        if st.button("Показать Б.7 (строки)", key="show_b7_btn"):
            params = {"report_id": selected_report_id} if selected_report_id else {}
            r = api_get(f"/projects/{project_id}/b7", params=params)
            if api_ok(r):
                df = prettify_b7_rows_df(df_safe(r.json()))
                st.session_state["b7_df"] = df
            else:
                show_api_error("Ошибка", r)
 
    with colC:
        if st.button("Показать разделы B.7", key="show_sections_btn"):
            params = {"report_id": selected_report_id} if selected_report_id else {}
            r = api_get(f"/projects/{project_id}/b7/sections", params=params)
            if api_ok(r):
                df = prettify_sections_df(df_safe(r.json()))
                st.session_state["sections_df"] = df
            else:
                show_api_error("Ошибка", r)
 
    st.divider()
 
    if "vor_df" in st.session_state:
        st.markdown("### ВОР")
        st.dataframe(st.session_state["vor_df"], use_container_width=True, height=420)
 
    if "b7_df" in st.session_state:
        st.markdown("### Б.7 (строки)")
        st.write(style_b7_fact_week(st.session_state["b7_df"]))
 
    if "sections_df" in st.session_state:
        st.markdown("### Sections")
        st.dataframe(st.session_state["sections_df"], use_container_width=True, height=420)
 
 
# =========================
# TAB 3: Matching preview
# =========================
with tab_ctx["matching"]:
    st.subheader("3) Сопоставление (предпросмотр)")
 
    c1, c2, c3 = st.columns([1, 1, 2])
    with c1:
        limit = st.number_input("Сколько строк проверить", min_value=10, max_value=5000, value=300, step=10)
    with c2:
        fuzzy_threshold = st.number_input("Порог fuzzy (%)", min_value=50, max_value=100, value=85, step=1)
    with c3:
        only_problems = st.checkbox("Показывать только проблемы (UNMATCHED + UNIT_MISMATCH)", value=True)
 
    if st.button("Проверить сопоставление", key="matching_preview_btn"):
        params = {"limit": int(limit), "fuzzy_threshold": int(fuzzy_threshold)}
        if selected_report_id:
            params["report_id"] = selected_report_id
 
        r = api_get(f"/projects/{project_id}/matching/preview", params=params)
        if api_ok(r):
            res = r.json()
            st.session_state["matching_last_raw"] = res
            st.success("Предпросмотр сопоставления готов.")
        else:
            show_api_error("Ошибка предпросмотра", r)
 
    res = st.session_state.get("matching_last_raw")
    if res:
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Проверено", res.get("checked", 0))
        m2.metric("MATCHED", res.get("matched", 0))
        m3.metric("UNIT_MISMATCH", res.get("unit_mismatch", 0))
        m4.metric("UNMATCHED", res.get("unmatched", 0))
 
        items = res.get("items", []) or []
        raw_df = df_safe(items)
 
        st.session_state["matching_items_raw"] = items
 
        if only_problems and "status" in raw_df.columns:
            raw_df = raw_df[raw_df["status"].isin(["UNMATCHED", "UNIT_MISMATCH"])]
 
        pretty_df = prettify_matching_df(raw_df)
 
        st.markdown("### Результаты сопоставления")
        if pretty_df.empty:
            st.success("Нет строк для отображения по выбранным фильтрам.")
        else:
            styled = style_status_column(pretty_df)
            st.write(styled)
 
            csv = pretty_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "Скачать таблицу (CSV)",
                data=csv,
                file_name="matching_preview.csv",
                mime="text/csv",
            )
 
 
# =========================
# TAB 4: Manual confirm mapping
# =========================
with tab_ctx["manual"]:
    st.subheader("4) Ручное подтверждение сопоставления")
    st.caption("Используется для корректировки спорных строк, когда авто-сопоставление ошиблось.")
 
    items = st.session_state.get("matching_items_raw") or []
    if not items:
        st.info("Сначала сделайте предпросмотр во вкладке «Сопоставление» — здесь появятся строки.")
    else:
        items_norm = []
        for x in items:
            x = dict(x)
            x["status"] = (x.get("status") or "").upper().strip()
            items_norm.append(x)
 
        status_choices = ["UNMATCHED", "UNIT_MISMATCH", "MATCHED"]
        default_statuses = ["UNMATCHED", "UNIT_MISMATCH"]
 
        def _reset_b7_select():
            st.session_state.pop("manual_b7_select", None)
 
        selected_statuses = st.multiselect(
            "Показать статусы",
            options=status_choices,
            default=default_statuses,
            help="Выберите, какие статусы показывать в ручном подтверждении.",
            key="manual_status_filter",
            on_change=_reset_b7_select,
        )
 
        if selected_statuses:
            items_filtered = [x for x in items_norm if x["status"] in selected_statuses]
        else:
            items_filtered = items_norm
 
        st.caption(
            f"Всего: {len(items_norm)} | "
            f"После фильтра: {len(items_filtered)} | "
            f"MATCHED: {sum(1 for x in items_filtered if x['status']=='MATCHED')} | "
            f"UNIT_MISMATCH: {sum(1 for x in items_filtered if x['status']=='UNIT_MISMATCH')} | "
            f"UNMATCHED: {sum(1 for x in items_filtered if x['status']=='UNMATCHED')}"
        )
 
        if not items_filtered:
            st.info("По выбранным статусам строк нет.")
        else:
            def b7_label(x: dict) -> str:
                sec = x.get("section_title") or "—"
                work = x.get("work_name") or ""
                unit = x.get("unit") or ""
                stt = x.get("status") or ""
                return f"{sec} | {work} | {unit} | {stt}"
 
            b7_options = {b7_label(x): x for x in items_filtered}
            selected_b7_label = st.selectbox(
                "Выберите строку Б.7",
                list(b7_options.keys()),
                key="manual_b7_select",
            )
            selected_b7 = b7_options[selected_b7_label]
            selected_b7_id = selected_b7.get("b7_row_id")
 
            st.markdown("#### Подбор строки ВОР")
 
            vr = api_get(f"/projects/{project_id}/vor")
            vor_items = vr.json() if api_ok(vr) else []
            if not vor_items:
                st.warning("ВОР не загружен или пуст — загрузите ВОР.")
            else:
                default_search = (selected_b7.get("work_name") or "")[:60]
                q = st.text_input("Поиск по ВОР (2–3 слова)", value=default_search).strip().lower()
 
                if q:
                    filtered_vor = [v for v in vor_items if q in (v.get("work_name", "").lower())]
                else:
                    filtered_vor = vor_items
 
                filtered_vor = filtered_vor[:200]
                if not filtered_vor:
                    st.info("Ничего не найдено. Попробуйте другие слова.")
                else:
                    vor_options = {
                        f'{v.get("work_name","")} | {v.get("unit","")} | объём: {v.get("plan_volume","")}': v
                        for v in filtered_vor
                    }
                    selected_vor_label = st.selectbox("Выберите строку ВОР", list(vor_options.keys()))
                    selected_vor_id = vor_options[selected_vor_label]["id"]
 
                    st.divider()
 
                    cA, cB = st.columns(2)
                    with cA:
                        if st.button("Сопоставить и сохранить (в память)", key="confirm_mapping_btn", disabled=not can_edit):
                            if not can_edit:
                                st.warning("Редактирование доступно только editor/admin.")
                                st.stop()
                            payload = {"b7_row_id": selected_b7_id, "vor_item_id": selected_vor_id}
                            resp = api_post(f"/projects/{project_id}/matching/confirm", json=payload)
                            if api_ok(resp):
                                st.success("Сопоставление сохранено. Вернитесь во вкладку «Сопоставление» и нажмите «Проверить сопоставление» снова.")
                            else:
                                show_api_error("Ошибка confirm", resp)
 
                    with cB:
                        if st.button("Удалить подтверждение (для этой строки Б.7)", key="delete_confirm_btn", disabled=not can_edit):
                            if not can_edit:
                                st.warning("Редактирование доступно только editor/admin.")
                                st.stop()
                            resp = api_delete(f"/projects/{project_id}/matching/confirm/{selected_b7_id}")
                            if api_ok(resp):
                                st.success("Подтверждение удалено. Вернитесь во вкладку «Сопоставление» и нажмите «Проверить сопоставление» снова.")
                            else:
                                show_api_error("Ошибка delete", resp)
 
 
# =========================
# TAB 5: Summary / Свод
# =========================
with tab_ctx["summary"]:
    st.subheader("5) Свод по отчётам")
    st.caption("Расчёт выполняется строго по выбранным отчётам Б.7: неделя, месяц, накопление, план и отклонения.")

    if not reports:
        st.info("Нет загруженных отчётов Б.7 — загрузите хотя бы один отчёт.")
    else:
        report_labels = []
        rep_by_label = {}
        for rep in reports:
            d = rep.get("report_date") or "—"
            fn = rep.get("source_filename") or "—"
            label = f"{d} — {fn}"
            report_labels.append(label)
            rep_by_label[label] = rep

        selected_labels = st.multiselect(
            "Выберите отчёты для свода",
            options=report_labels,
            default=report_labels,
            key="summary_reports_select_v2",
        )

        if st.button("Собрать свод", key="build_summary_btn_v2"):
            if not selected_labels:
                st.warning("Выберите хотя бы один отчёт.")
            else:
                report_ids = [str(rep_by_label[x]["id"]) for x in selected_labels if rep_by_label.get(x)]
                params_dyn = {"report_ids": report_ids, "include_problems": False}
                params_problems = {"report_ids": report_ids, "include_problems": True}
                rw = api_get(f"/projects/{project_id}/summary/weeks", params=params_dyn)
                rm = api_get(f"/projects/{project_id}/summary/months", params=params_dyn)
                rp = api_get(f"/projects/{project_id}/summary/weeks", params=params_problems)
                if api_ok(rw) and api_ok(rm):
                    st.session_state["summary_weeks_payload_v2"] = rw.json() or {}
                    st.session_state["summary_months_payload_v2"] = rm.json() or {}
                    st.session_state["summary_problems_payload_v2"] = (rp.json() or {}).get("problems") if api_ok(rp) else []
                    st.success("Свод и динамика построены.")
                else:
                    if not api_ok(rw):
                        show_api_error("Ошибка свода (недели)", rw)
                    if not api_ok(rm):
                        show_api_error("Ошибка свода (месяцы)", rm)

        weeks_payload = st.session_state.get("summary_weeks_payload_v2") or {}
        weeks_items = weeks_payload.get("items") or []
        weeks_cols = weeks_payload.get("weeks") or []

        months_payload = st.session_state.get("summary_months_payload_v2") or {}
        months_items = months_payload.get("items") or []
        months_cols = months_payload.get("months") or []
        problems_payload = st.session_state.get("summary_problems_payload_v2") or []

        if problems_payload:
            total_problems = len(problems_payload)
            unmatched_cnt = sum(1 for x in problems_payload if str(x.get("status") or "").upper() == "UNMATCHED")
            unit_mismatch_cnt = sum(1 for x in problems_payload if str(x.get("status") or "").upper() == "UNIT_MISMATCH")
            st.warning(
                f"Есть проблемные строки сопоставления: {total_problems} "
                f"(UNMATCHED: {unmatched_cnt}, UNIT_MISMATCH: {unit_mismatch_cnt})"
            )
            with st.expander("Показать проблемные строки"):
                df_problems = pd.DataFrame(problems_payload)
                if not df_problems.empty:
                    cols_order = [
                        "report_date",
                        "section_title",
                        "work_name",
                        "unit",
                        "fact_week",
                        "status",
                        "match_type",
                        "vor_candidate",
                        "vor_unit",
                    ]
                    df_problems = df_problems[[c for c in cols_order if c in df_problems.columns]]
                    df_problems = df_problems.rename(
                        columns={
                            "report_date": "Дата отчёта",
                            "section_title": "Секция",
                            "work_name": "Работа Б.7",
                            "unit": "Ед. изм. Б.7",
                            "fact_week": "Факт за неделю",
                            "status": "Статус",
                            "match_type": "Тип подбора",
                            "vor_candidate": "Кандидат ВОР",
                            "vor_unit": "Ед. изм. ВОР",
                        }
                    )
                st.dataframe(df_problems, use_container_width=True, height=260)
                st.download_button(
                    "Скачать проблемные строки (CSV)",
                    data=df_problems.to_csv(index=False).encode("utf-8-sig"),
                    file_name="summary_problems.csv",
                    mime="text/csv",
                )

        if weeks_items:
            latest_week = weeks_cols[-1] if weeks_cols else None
            latest_month = months_cols[-1] if months_cols else None
            month_map_by_vor = {}
            for mi in months_items:
                month_map_by_vor[str(mi.get("vor_id"))] = mi.get("months") or {}

            summary_rows = []
            for item in weeks_items:
                vor_id = str(item.get("vor_id"))
                week_map = item.get("weeks") or {}
                month_map = month_map_by_vor.get(vor_id, {})
                fact_week_last = week_map.get(latest_week, 0.0) if latest_week else 0.0
                fact_month_last = month_map.get(latest_month, 0.0) if latest_month else 0.0
                summary_rows.append(
                    {
                        "Работа (ВОР)": item.get("work_name"),
                        "Ед. изм.": item.get("unit"),
                        "Факт за неделю": fact_week_last,
                        "Факт за месяц": fact_month_last,
                        "Факт с начала строительства": item.get("fact_total"),
                        "План с начала строительства": item.get("plan_total"),
                        "Дельта (План - Факт), абс.": item.get("delta_abs"),
                        "Дельта (Факт/План), %": item.get("delta_pct"),
                    }
                )

            df_summary = pd.DataFrame(summary_rows)
            num_cols = [
                "Факт за неделю",
                "Факт за месяц",
                "Факт с начала строительства",
                "План с начала строительства",
                "Дельта (План - Факт), абс.",
                "Дельта (Факт/План), %",
            ]
            for col in num_cols:
                if col in df_summary.columns:
                    df_summary[col] = pd.to_numeric(df_summary[col], errors="coerce")
            for col in ["Факт за неделю", "Факт за месяц", "Факт с начала строительства", "План с начала строительства", "Дельта (План - Факт), абс."]:
                if col in df_summary.columns:
                    df_summary[col] = df_summary[col].round(3)
            if "Дельта (Факт/План), %" in df_summary.columns:
                df_summary["Дельта (Факт/План), %"] = df_summary["Дельта (Факт/План), %"].round(2)

            show_only_nonzero = st.checkbox(
                "Показывать только строки с ненулевыми значениями",
                value=True,
                key="summary_nonzero_only",
            )
            df_summary_view = df_summary.copy()
            if show_only_nonzero:
                fact_cols = [
                    c
                    for c in [
                        "Факт за неделю",
                        "Факт за месяц",
                        "Факт с начала строительства",
                    ]
                    if c in df_summary_view.columns
                ]
                if fact_cols:
                    mask_nonzero = (
                        df_summary_view[fact_cols]
                        .apply(pd.to_numeric, errors="coerce")
                        .fillna(0.0)
                        .abs()
                        .sum(axis=1)
                        > 0
                    )
                    df_summary_view = df_summary_view[mask_nonzero].reset_index(drop=True)

            st.markdown("### Общий свод")
            st.dataframe(df_summary_view, use_container_width=True, height=420)
            render_summary_charts(
                df_summary=df_summary,
                weeks_items=weeks_items,
                weeks_cols=weeks_cols,
                months_items=months_items,
                months_cols=months_cols,
            )
            st.download_button(
                "Скачать общий свод (CSV)",
                data=df_summary_view.to_csv(index=False).encode("utf-8-sig"),
                file_name="summary_total.csv",
                mime="text/csv",
            )

        if weeks_items and weeks_cols:
            week_rows = []
            for item in weeks_items:
                row = {"Работа (ВОР)": item.get("work_name"), "Ед. изм.": item.get("unit"), "План": item.get("plan_total")}
                week_map = item.get("weeks") or {}
                for w in weeks_cols:
                    row[w] = week_map.get(w, 0.0)
                row["Факт с начала"] = item.get("fact_total")
                row["Дельта (План-Факт)"] = item.get("delta_abs")
                row["Дельта (Факт/План), %"] = item.get("delta_pct")
                week_rows.append(row)
            df_weeks = pd.DataFrame(week_rows)
            st.markdown("### Динамика по неделям")
            st.dataframe(df_weeks, use_container_width=True, height=340)
            st.download_button(
                "Скачать недели (CSV)",
                data=df_weeks.to_csv(index=False).encode("utf-8-sig"),
                file_name="summary_weeks.csv",
                mime="text/csv",
            )

        if months_items and months_cols:
            month_rows = []
            for item in months_items:
                row = {"Работа (ВОР)": item.get("work_name"), "Ед. изм.": item.get("unit"), "План": item.get("plan_total")}
                month_map = item.get("months") or {}
                for m in months_cols:
                    row[m] = month_map.get(m, 0.0)
                row["Факт с начала"] = item.get("fact_total")
                row["Дельта (План-Факт)"] = item.get("delta_abs")
                row["Дельта (Факт/План), %"] = item.get("delta_pct")
                month_rows.append(row)
            df_months = pd.DataFrame(month_rows)
            st.markdown("### Динамика по месяцам")
            st.dataframe(df_months, use_container_width=True, height=340)
            st.download_button(
                "Скачать месяцы (CSV)",
                data=df_months.to_csv(index=False).encode("utf-8-sig"),
                file_name="summary_months.csv",
                mime="text/csv",
            )

            year_rows = []
            for item in months_items:
                row = {"Работа (ВОР)": item.get("work_name"), "Ед. изм.": item.get("unit"), "План": item.get("plan_total")}
                by_year = {}
                for month_key, val in (item.get("months") or {}).items():
                    y = str(month_key)[:4]
                    by_year[y] = by_year.get(y, 0.0) + float(val or 0.0)
                for y in sorted(by_year.keys()):
                    row[y] = round(by_year[y], 6)
                row["Факт с начала"] = item.get("fact_total")
                row["Дельта (План-Факт)"] = item.get("delta_abs")
                row["Дельта (Факт/План), %"] = item.get("delta_pct")
                year_rows.append(row)
            if year_rows:
                df_years = pd.DataFrame(year_rows)
                st.markdown("### Динамика по годам")
                st.dataframe(df_years, use_container_width=True, height=300)
                st.download_button(
                    "Скачать годы (CSV)",
                    data=df_years.to_csv(index=False).encode("utf-8-sig"),
                    file_name="summary_years.csv",
                    mime="text/csv",
                )

with tab_ctx["ocr"]:
    tab_b7_pdf_preview(project_id)

if is_admin:
    with tab_ctx["users"]:
        st.subheader("7) Пользователи")
        st.caption("Управление пользователями доступно только администратору.")

        users = []
        r_users = api_get("/auth/users")
        if not api_ok(r_users):
            show_api_error("Ошибка загрузки пользователей", r_users)
        else:
            users = r_users.json() or []
            if users:
                st.dataframe(pd.DataFrame(users), use_container_width=True, height=300, hide_index=True)
            else:
                st.info("Пользователей пока нет.")

        st.markdown("### Создать пользователя")
        with st.form("admin_create_user_form", clear_on_submit=True):
            new_login = st.text_input("Логин")
            new_full_name = st.text_input("Имя")
            new_password = st.text_input("Пароль", type="password")
            new_role = st.selectbox("Роль", ["user", "editor", "admin"], index=0)
            new_is_active = st.checkbox("Активен", value=True)
            create_submit = st.form_submit_button("Создать пользователя")
        if create_submit:
            payload = {
                "login": new_login.strip().lower(),
                "password": new_password,
                "full_name": new_full_name.strip(),
                "role": new_role,
                "is_active": new_is_active,
            }
            resp = api_post("/auth/users", json=payload)
            if api_ok(resp):
                st.success("Пользователь создан.")
                st.rerun()
            else:
                show_api_error("Ошибка создания пользователя", resp)

        st.markdown("### Изменить роль / статус")
        if users:
            user_map = {f"{u.get('login','')} | {u.get('role','')} | active={u.get('is_active', True)}": u for u in users}
            selected_label = st.selectbox("Пользователь", list(user_map.keys()), key="admin_user_select")
            selected_user = user_map[selected_label]
            upd_role = st.selectbox("Новая роль", ["user", "editor", "admin"], index=["user", "editor", "admin"].index(selected_user.get("role", "user")))
            upd_active = st.checkbox("Активен", value=bool(selected_user.get("is_active", True)), key="admin_user_active")
            upd_full_name = st.text_input("Имя", value=selected_user.get("full_name", ""), key="admin_user_full_name")
            upd_password = st.text_input("Новый пароль (необязательно)", type="password", key="admin_user_password")
            if st.button("Сохранить изменения", key="admin_user_update_btn"):
                payload = {
                    "role": upd_role,
                    "is_active": upd_active,
                    "full_name": upd_full_name.strip(),
                }
                if upd_password.strip():
                    payload["password"] = upd_password
                resp = api_patch(f"/auth/users/{selected_user.get('id')}", json=payload)
                if api_ok(resp):
                    st.success("Пользователь обновлен.")
                    st.rerun()
                else:
                    show_api_error("Ошибка обновления пользователя", resp)
for slot in hidden_tab_slots:
    slot.empty()
