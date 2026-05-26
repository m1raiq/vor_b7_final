import json
from typing import Any, Dict, List

import requests

from app.config import settings
from app.services.b7_pdf_service import _render_pdf_pages_to_data_urls
from app.utils.normalization import parse_num


def _extract_json_payload(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    txt = text.strip()
    if txt.startswith("```"):
        txt = txt.strip("`")
        txt = txt.replace("json", "", 1).strip()
    try:
        parsed = json.loads(txt)
        if isinstance(parsed, list):
            return [x for x in parsed if isinstance(x, dict)]
        if isinstance(parsed, dict):
            rows = parsed.get("rows")
            if isinstance(rows, list):
                return [x for x in rows if isinstance(x, dict)]
    except Exception:
        pass

    lb = txt.find("[")
    rb = txt.rfind("]")
    if lb >= 0 and rb > lb:
        frag = txt[lb : rb + 1]
        try:
            parsed = json.loads(frag)
            if isinstance(parsed, list):
                return [x for x in parsed if isinstance(x, dict)]
        except Exception:
            return []
    return []


def _qwen_extract_vor_rows_page(image_data_url: str) -> Dict[str, Any]:
    api_url = (settings.qwen_vl_api_url or "").strip().rstrip("/")
    token = (settings.qwen_vl_token or "").strip()
    model = (settings.qwen_vl_model or "").strip()
    if not api_url:
        return {"ok": False, "msg": "QWEN_VL_API_URL is not configured"}
    if not token:
        return {"ok": False, "msg": "QWEN_VL_TOKEN is not configured"}
    if not model:
        return {"ok": False, "msg": "QWEN_VL_MODEL is not configured"}

    prompt = (
        "Это страница ВОР (ведомость объемов работ) на русском языке. "
        "Извлеки только строки работ и верни строго JSON-массив объектов вида: "
        '[{"work_name":"...", "unit":"...", "plan_volume":"..."}]. '
        "Без пояснений и без markdown. "
        "Игнорируй итоги, подписи, шапку, даты и служебные строки. "
        "Если на странице нет строк работ — верни []."
    )
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": int(settings.qwen_vl_max_tokens),
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": image_data_url}},
                ],
            }
        ],
    }
    url = f"{api_url}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=settings.qwen_vl_timeout_seconds)
    except Exception as e:
        return {"ok": False, "msg": f"Qwen-VL call failed: {e}"}
    if resp.status_code != 200:
        return {"ok": False, "msg": f"Qwen-VL status={resp.status_code}", "debug": resp.text[:1200]}
    try:
        data = resp.json()
    except Exception as e:
        return {"ok": False, "msg": f"Qwen-VL returned invalid JSON: {e}"}
    content = ((data.get("choices") or [{}])[0].get("message") or {}).get("content") or ""
    rows = _extract_json_payload(str(content))
    return {"ok": True, "rows": rows, "raw": str(content)[:2000]}


def extract_vor_rows_from_pdf(pdf_bytes: bytes) -> Dict[str, Any]:
    try:
        pages = _render_pdf_pages_to_data_urls(
            pdf_bytes=pdf_bytes,
            max_pages=max(1, int(settings.qwen_vl_max_pages)),
            zoom=float(settings.qwen_vl_render_zoom),
        )
    except Exception as e:
        return {"ok": False, "msg": f"PDF render failed: {e}"}
    if not pages:
        return {"ok": False, "msg": "PDF has no pages"}

    out_rows: List[Dict[str, Any]] = []
    debug_pages: List[Dict[str, Any]] = []
    for i, page_url in enumerate(pages):
        pr = _qwen_extract_vor_rows_page(page_url)
        if not pr.get("ok"):
            debug_pages.append({"page_index": i, "ok": False, "msg": pr.get("msg"), "debug": pr.get("debug")})
            continue
        rows = pr.get("rows") or []
        debug_pages.append({"page_index": i, "ok": True, "rows": len(rows)})
        for r in rows:
            work_name = str(r.get("work_name") or "").strip()
            unit = str(r.get("unit") or "").strip()
            plan_raw = r.get("plan_volume")
            plan_volume = parse_num(plan_raw)
            if not work_name:
                continue
            out_rows.append(
                {
                    "work_name": work_name,
                    "unit": unit,
                    "plan_volume": float(plan_volume) if plan_volume is not None else None,
                }
            )

    if not out_rows:
        return {"ok": False, "msg": "No VOR rows recognized from PDF", "debug": debug_pages}
    return {"ok": True, "rows": out_rows, "debug": debug_pages}
