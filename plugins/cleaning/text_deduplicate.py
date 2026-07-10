"""Text deduplicate cleaning plugin."""

import re
from pathlib import Path


PARAMETERS = [
    {
        "name": "deduplicate_mode",
        "type": "select",
        "label": "去重模式",
        "default": "char",
        "min": None,
        "max": None,
        "options": ["char", "line"],
        "description": "char: 按字去重; line: 按行/句去重",
        "required": False,
    },
    {
        "name": "apply",
        "type": "bool",
        "label": "写入清洗结果",
        "default": True,
        "min": None,
        "max": None,
        "options": [],
        "description": "是否将去重后的文本写入磁盘",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir", "."))
    mode = _normalize_mode(parameters.get("deduplicate_mode", "char"))
    apply_changes = bool(parameters.get("apply", True))

    if not samples:
        return {"ok": True, "suggestions": [], "logs": []}

    total = max(len(samples), 1)
    suggestions = []

    for idx, sample in enumerate(samples):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        context.set_progress((idx + 1) * 100 / total, f"文本去重 {idx + 1}/{total}")

        sample_path = _sample_path(sample)
        if not sample_path or not sample_path.is_file():
            continue

        text = _read_text(sample_path)
        if text is None:
            continue

        cleaned, dup_count = _deduplicate(text, mode)
        if dup_count:
            total_units = _unit_count(text, mode)
            confidence = _clamp(dup_count / max(total_units, 1))
            output_path = ""
            if apply_changes:
                output_path = _write_cleaned(sample_path, output_dir, cleaned)
            suggestions.append(
                {
                    "sample_id": sample["id"],
                    "issue_type": "text_duplicate",
                    "suggested_action": "repair",
                    "confidence": confidence,
                    "message": f"Found {dup_count} duplicate {'characters' if mode == 'char' else 'lines/sentences'}",
                    "details": {
                        "duplicate_count": dup_count,
                        "mode": mode,
                        "output_file_path": output_path,
                        "processing_result": "deduplicated",
                    },
                }
            )

    return {"ok": True, "suggestions": suggestions, "logs": []}


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


def _deduplicate(text: str, mode: str) -> tuple[str, int]:
    if _normalize_mode(mode) == "line":
        return _deduplicate_lines_and_sentences(text)
    return _collapse_repeated_chars(text)


def _collapse_repeated_chars(text: str) -> tuple[str, int]:
    result = []
    duplicate_count = 0
    previous = ""
    for char in text:
        if char == previous and _is_cjk(char):
            duplicate_count += 1
            continue
        result.append(char)
        previous = char
    return "".join(result), duplicate_count


def _deduplicate_lines_and_sentences(text: str) -> tuple[str, int]:
    seen_lines = set()
    result_lines = []
    duplicate_count = 0
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        line_key = stripped.casefold()
        if line_key in seen_lines:
            duplicate_count += 1
            continue
        seen_lines.add(line_key)
        cleaned_line, sentence_duplicates = _deduplicate_sentence_units(line)
        duplicate_count += sentence_duplicates
        result_lines.append(cleaned_line)
    return "\n".join(result_lines), duplicate_count


def _deduplicate_sentence_units(line: str) -> tuple[str, int]:
    parts = re.findall(r"([^，,。！？!?；;\n]+)([，,。！？!?；;]?)", line)
    units = [(text, separator) for text, separator in parts if text.strip()]
    if len(units) <= 1:
        return line, 0

    seen = set()
    result = []
    duplicate_count = 0
    for text, separator in units:
        key = text.strip().casefold()
        if key in seen:
            duplicate_count += 1
            continue
        seen.add(key)
        result.append((text, separator))

    if result:
        last_text, last_separator = result[-1]
        result[-1] = (last_text, "" if last_separator in {"，", ","} else last_separator)
    return "".join(text + separator for text, separator in result), duplicate_count


def _unit_count(text: str, mode: str) -> int:
    if _normalize_mode(mode) == "char":
        return len([char for char in text if _is_cjk(char)])
    return len([line for line in text.splitlines() if line.strip()])


def _normalize_mode(mode: str) -> str:
    mode = str(mode or "char").strip().lower()
    if mode in {"line", "sentence"}:
        return "line"
    return "char"


def _is_cjk(char: str) -> bool:
    return bool(re.match(r"[\u4e00-\u9fff]", char))


def _write_cleaned(orig: Path, output_dir: Path, cleaned: str) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    out_path = output_dir / f"dedup_{orig.name}"
    out_path.write_text(cleaned, encoding="utf-8")
    return str(out_path)


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
