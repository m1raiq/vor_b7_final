import json
import re
from typing import Any, Optional

import requests

from app.config import settings

_CACHE: dict[str, Optional[str]] = {}


def _extract_text_content(data: dict[str, Any]) -> str:
    content = (((data.get("choices") or [{}])[0].get("message") or {}).get("content")) or ""
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict):
                txt = item.get("text")
                if txt:
                    parts.append(str(txt))
            else:
                parts.append(str(item))
        return "\n".join(parts).strip()
    return str(content).strip()


def semantic_pick_vor_id(
    *,
    section_title: str,
    work_name: str,
    unit: str,
    candidates: list[dict[str, str]],
) -> Optional[str]:
    if not candidates:
        return None

    api_url = (settings.qwen_vl_api_url or "").strip().rstrip("/")
    token = (settings.qwen_vl_token or "").strip()
    model = (settings.qwen_vl_model or "").strip()
    if not api_url or not token or not model:
        return None

    key_obj = {
        "s": section_title or "",
        "w": work_name or "",
        "u": unit or "",
        "c": candidates,
    }
    cache_key = json.dumps(key_obj, ensure_ascii=False, sort_keys=True)
    if cache_key in _CACHE:
        return _CACHE[cache_key]

    cand_lines = []
    for c in candidates:
        cand_lines.append(f"{c['id']} | {c['name']} | {c['unit']}")

    prompt = (
        "Ты сопоставляешь строку отчета Б.7 со строкой ВОР.\n"
        "Выбери ОДИН лучший кандидат по смыслу.\n"
        "Если нет подходящего, верни NONE.\n"
        "Ответь только JSON в формате {\"id\":\"<candidate_id|NONE>\"}.\n\n"
        f"Секция: {section_title or '-'}\n"
        f"Работа Б.7: {work_name}\n"
        f"Ед.изм. Б.7: {unit}\n\n"
        "Кандидаты ВОР:\n"
        + "\n".join(cand_lines)
    )

    url = f"{api_url}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "temperature": 0,
        "max_tokens": min(int(settings.qwen_vl_max_tokens), 300),
        "messages": [{"role": "user", "content": prompt}],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=settings.qwen_vl_timeout_seconds)
        if resp.status_code != 200:
            _CACHE[cache_key] = None
            return None
        data = resp.json()
    except Exception:
        _CACHE[cache_key] = None
        return None

    text = _extract_text_content(data)
    parsed_id = None
    try:
        m = re.search(r"\{[\s\S]*\}", text)
        if m:
            obj = json.loads(m.group(0))
            parsed_id = str(obj.get("id") or "").strip()
    except Exception:
        parsed_id = None

    allowed = {str(c["id"]) for c in candidates}
    if parsed_id in allowed:
        _CACHE[cache_key] = parsed_id
        return parsed_id
    if parsed_id and parsed_id.upper() == "NONE":
        _CACHE[cache_key] = None
        return None

    for c in candidates:
        if str(c["id"]) in text:
            _CACHE[cache_key] = str(c["id"])
            return str(c["id"])

    _CACHE[cache_key] = None
    return None
