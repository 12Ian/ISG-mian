"""Text stop-word removal plugin."""

import re
from pathlib import Path


DEFAULT_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for", "from", "has",
    "he", "in", "is", "it", "its", "of", "on", "that", "the", "to", "was",
    "were", "will", "with", "this", "these", "those", "or", "not", "but",
    "we", "you", "they", "i",
    "的", "了", "和", "是", "在", "我", "有", "就", "不", "人", "都", "一",
    "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有",
}

PARAMETERS = [
    {
        "name": "stop_words",
        "type": "string",
        "label": "额外停用词",
        "default": "",
        "min": None,
        "max": None,
        "options": [],
        "description": "用户自定义的额外停用词，逗号分隔",
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
        "description": "是否将去停用词后的文本写入磁盘",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir", "."))
    apply_changes = bool(parameters.get("apply", True))

    extra_words = _parse_stop_words(parameters.get("stop_words"))
    stop_words = DEFAULT_STOP_WORDS | {str(word).strip() for word in extra_words if str(word).strip()}

    if not samples:
        return {"ok": True, "suggestions": [], "logs": []}

    total = max(len(samples), 1)
    suggestions = []

    for idx, sample in enumerate(samples):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消", "details": {}}
        context.set_progress((idx + 1) * 100 / total, f"停用词过滤 {idx + 1}/{total}")

        sample_path = _sample_path(sample)
        if not sample_path or not sample_path.is_file():
            continue

        text = _read_text(sample_path)
        if text is None:
            continue

        cleaned, removed = _remove_stop_words(text, stop_words)
        if removed:
            confidence = _clamp(removed / max(_rough_token_count(text), 1))
            output_path = ""
            if apply_changes:
                output_dir.mkdir(parents=True, exist_ok=True)
                out_path = output_dir / f"nostop_{sample_path.name}"
                out_path.write_text(cleaned, encoding="utf-8")
                output_path = str(out_path)
            suggestions.append(
                {
                    "sample_id": sample["id"],
                    "issue_type": "text_stopwords",
                    "suggested_action": "repair",
                    "confidence": confidence,
                    "message": f"Removed {removed} stop words",
                    "details": {
                        "removed_count": removed,
                        "output_file_path": output_path,
                        "processing_result": "stopwords_removed",
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


def _parse_stop_words(value) -> set[str]:
    if not value:
        return set()
    if isinstance(value, str):
        return {word.strip() for word in re.split(r"[,，\s]+", value) if word.strip()}
    try:
        return {str(word).strip() for word in value if str(word).strip()}
    except TypeError:
        word = str(value).strip()
        return {word} if word else set()


def _remove_stop_words(text: str, stop_words: set[str]) -> tuple[str, int]:
    cleaned = text
    removed = 0
    for word in sorted(stop_words, key=len, reverse=True):
        if not word:
            continue
        if re.fullmatch(r"[A-Za-z0-9_]+", word):
            cleaned, count = _remove_ascii_word(cleaned, word)
        else:
            cleaned, count = _remove_literal_word(cleaned, word)
        removed += count
    cleaned = re.sub(r"[^\S\r\n]{2,}", " ", cleaned)
    cleaned = re.sub(r"(?m)^[ \t]+|[ \t]+$", "", cleaned)
    return cleaned, removed


def _remove_ascii_word(text: str, word: str) -> tuple[str, int]:
    pattern = re.compile(rf"(?<![A-Za-z0-9_])[^\S\r\n]*{re.escape(word)}[^\S\r\n]*(?![A-Za-z0-9_])", re.IGNORECASE)

    def replace(match: re.Match) -> str:
        left = text[match.start() - 1] if match.start() > 0 else ""
        right = text[match.end()] if match.end() < len(text) else ""
        if _is_word_char(left) and _is_word_char(right):
            return " "
        if left in ",，。.!！？?;；:" or right in ",，。.!！？?;；:":
            return ""
        return " "

    return pattern.subn(replace, text)


def _remove_literal_word(text: str, word: str) -> tuple[str, int]:
    return re.subn(re.escape(word), "", text)


def _rough_token_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]|[A-Za-z0-9_]+", text))


def _is_word_char(char: str) -> bool:
    return bool(re.match(r"[A-Za-z0-9_\u4e00-\u9fff]", char or ""))


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 4)
