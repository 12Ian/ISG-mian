"""Text stemming cleaning plugin.

Applies lightweight rule-based English stemming while preserving Chinese text,
punctuation, and line breaks unchanged.
"""

import re
from pathlib import Path


PARAMETERS = [
    {
        "name": 'apply',
        "type": 'bool',
        "label": '写入清洗结果',
        "default": True,
        "min": None,
        "max": None,
        "options": [],
        "description": '是否将词干提取后的文本写入磁盘',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir", "."))
    apply_changes = bool(parameters.get("apply", True))

    if not samples:
        return {"ok": True, "suggestions": [], "logs": []}

    total = max(len(samples), 1)
    suggestions = []

    for idx, sample in enumerate(samples):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        context.set_progress((idx + 1) * 100 / total, f"词干提取 {idx + 1}/{total}")

        sample_path = _sample_path(sample)
        if not sample_path or not sample_path.is_file():
            continue

        text = _read_text(sample_path)
        if text is None:
            continue

        cleaned, changed, token_count = _stem_english_words(text)
        if changed:
            confidence = _clamp(changed / max(token_count, 1))
            output_path = ""
            if apply_changes:
                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / f"stemmed_{sample_path.name}"
                out_path.write_text(cleaned, encoding="utf-8")
                output_path = str(out_path)
            suggestions.append({
                "sample_id": sample["id"],
                "issue_type": "text_unstemmed",
                "suggested_action": "repair",
                "confidence": confidence,
                "message": f"Stemmed {changed} English tokens ({token_count} total); Chinese text preserved",
                "details": {"changed_count": changed, "total_tokens": token_count,
                            "output_file_path": output_path, "processing_result": "stemmed"},
            })

    return {"ok": True, "suggestions": suggestions, "logs": []}


_SUFFIX_RULES: list[tuple[str, int, str]] = [
    # (suffix, min_len, replacement) — replacement empty means strip
    ("ingly", 7, ""),
    ("edly", 6, ""),
    ("ing", 5, ""),
    ("ed", 4, ""),
    ("ies", 5, "y"),
    ("es", 4, ""),
    ("s", 4, ""),
]


def _stem_english_words(text: str) -> tuple[str, int, int]:
    changed = 0
    token_count = 0

    def replace(match: re.Match) -> str:
        nonlocal changed, token_count
        token = match.group(0)
        stemmed = _stem_token(token)
        token_count += 1
        if stemmed != token:
            changed += 1
        return stemmed

    return re.sub(r"[A-Za-z]+", replace, text), changed, token_count


def _stem_token(token: str) -> str:
    lower = token.lower()
    for suffix, min_len, replacement in _SUFFIX_RULES:
        if lower.endswith(suffix) and len(lower) >= min_len:
            stem = lower[:-len(suffix)] + replacement
            return stem if stem else lower
    return lower


def _sample_path(sample: dict):
    path = sample.get("sample_path") or sample.get("path") or sample.get("file_path")
    if not path:
        return None
    return Path(path)


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except Exception:
        try:
            return path.read_text(encoding="latin-1")
        except Exception:
            return None


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
