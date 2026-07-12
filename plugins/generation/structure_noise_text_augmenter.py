from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": "perturbation_strength", "type": "float", "label": "扰动强度", "default": 0.1,
        "min": 0.0, "max": 1.0, "options": [], "description": "受控词语级噪声强度", "required": False,
    },
    {
        "name": "deletion_probability", "type": "float", "label": "删除概率", "default": 0.02,
        "min": 0.0, "max": 0.1, "options": [], "description": "删除完整词语单元的基础概率", "required": False,
    },
    {
        "name": "swap_probability", "type": "float", "label": "交换概率", "default": 0.03,
        "min": 0.0, "max": 0.1, "options": [], "description": "交换相邻词语单元的基础概率", "required": False,
    },
    {
        "name": "insertion_probability", "type": "float", "label": "插入概率", "default": 0.02,
        "min": 0.0, "max": 0.1, "options": [], "description": "在词语边界插入邻近或形近内容的基础概率", "required": False,
    },
]


NEGATIONS = {"不", "不是", "不能", "不可", "没有", "并非", "未", "无", "否", "无需", "只要"}
PUNCTUATION_PATTERN = re.compile(r"[，。！？；：、,.!?;:\n]")
TOKEN_PATTERN = re.compile(r"[\u4e00-\u9fff]+|[A-Za-z][A-Za-z0-9_.-]*|\d+(?:\.\d+)?|\s+|[^\w\s]", re.UNICODE)
CONFUSABLES = {
    "己": "已", "已": "己", "未": "末", "末": "未", "日": "目", "目": "日",
    "人": "入", "入": "人", "土": "士", "士": "土", "口": "囗", "干": "千",
}
MAX_ATTEMPTS_PER_OUTPUT = 30


def _split_chinese_run(run: str) -> list[str]:
    # 优先保留常见否定词，再以双字单元近似词边界，避免单字随机拆散。
    protected = sorted(NEGATIONS, key=len, reverse=True)
    result = []
    index = 0
    while index < len(run):
        matched = next((word for word in protected if run.startswith(word, index)), None)
        if matched:
            result.append(matched)
            index += len(matched)
            continue
        remaining = len(run) - index
        size = 2 if remaining != 1 else 1
        result.append(run[index:index + size])
        index += size
    return result


def _tokenize(text: str) -> list[str]:
    tokens = []
    for match in TOKEN_PATTERN.finditer(text):
        token = match.group(0)
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            tokens.extend(_split_chinese_run(token))
        else:
            tokens.append(token)
    return tokens


def _quoted_tokens(tokens: list[str]) -> set[str]:
    protected = set()
    closing = None
    pairs = {"“": "”", "‘": "’", '"': '"'}
    for token in tokens:
        if closing is not None:
            if token == closing:
                closing = None
            else:
                protected.add(token)
            continue
        if token in pairs:
            closing = pairs[token]
    return protected


def _is_protected(token: str, quoted: set[str] | None = None) -> bool:
    if not token or token.isspace() or PUNCTUATION_PATTERN.fullmatch(token):
        return True
    if token in NEGATIONS or re.fullmatch(r"\d+(?:\.\d+)?", token):
        return True
    if quoted and token in quoted:
        return True
    # 英文大写开头或包含点/连字符的内容按专有名词保护。
    if re.fullmatch(r"[A-Z][A-Za-z0-9_.-]*", token) or re.search(r"[_.-]", token):
        return True
    return False


def _similar_insertion(neighbor: str) -> str:
    chars = list(neighbor)
    candidates = [index for index, char in enumerate(chars) if char in CONFUSABLES]
    if candidates:
        index = int(np.random.choice(candidates))
        chars[index] = CONFUSABLES[chars[index]]
        return "".join(chars)
    return neighbor


def _perturb(text: str, strength: float, delete_p: float, swap_p: float, insert_p: float) -> tuple[str, dict]:
    tokens = _tokenize(text)
    quoted = _quoted_tokens(tokens)
    stats = {"delete": 0, "swap": 0, "insert": 0}
    scale = max(0.1, strength)
    delete_p *= scale
    swap_p *= scale
    insert_p *= scale

    index = 0
    while index < len(tokens):
        if _is_protected(tokens[index], quoted):
            index += 1
            continue
        roll = np.random.rand()
        if roll < delete_p and len(tokens) > 2:
            del tokens[index]
            stats["delete"] += 1
            continue
        if roll < delete_p + swap_p and index + 1 < len(tokens) and not _is_protected(tokens[index + 1], quoted):
            tokens[index], tokens[index + 1] = tokens[index + 1], tokens[index]
            stats["swap"] += 1
            index += 2
            continue
        if roll < delete_p + swap_p + insert_p:
            tokens.insert(index + 1, _similar_insertion(tokens[index]))
            stats["insert"] += 1
            index += 2
            continue
        index += 1

    return "".join(tokens), stats


def _edit_distance(left: str, right: str) -> int:
    previous = list(range(len(right) + 1))
    for i, left_char in enumerate(left, 1):
        current = [i]
        for j, right_char in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (left_char != right_char)))
        previous = current
    return previous[-1]


def _quality_check(source: str, candidate: str) -> tuple[bool, str, float, float]:
    if candidate == source or not candidate.strip():
        return False, "unchanged", 1.0, 0.0
    if re.findall(r"\d+(?:\.\d+)?", source) != re.findall(r"\d+(?:\.\d+)?", candidate):
        return False, "numbers_changed", 0.0, 1.0
    if [word for word in NEGATIONS if word in source] != [word for word in NEGATIONS if word in candidate]:
        return False, "negation_changed", 0.0, 1.0
    if PUNCTUATION_PATTERN.findall(source) != PUNCTUATION_PATTERN.findall(candidate):
        return False, "punctuation_changed", 0.0, 1.0

    similarity = SequenceMatcher(None, source, candidate).ratio()
    edit_ratio = _edit_distance(source, candidate) / max(1, len(source))
    if similarity < 0.85:
        return False, "similarity_too_low", similarity, edit_ratio
    if edit_ratio > 0.15:
        return False, "edit_distance_too_large", similarity, edit_ratio
    if re.search(r"(.)\1{3,}", candidate):
        return False, "low_readability", similarity, edit_ratio
    return True, "passed", similarity, edit_ratio


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    strength = _clamp(parameters.get("perturbation_strength", parameters.get("strength", 0.1)), 0.0, 1.0)
    delete_p = _clamp(parameters.get("deletion_probability", 0.02), 0.0, 0.1)
    swap_p = _clamp(parameters.get("swap_probability", 0.03), 0.0, 0.1)
    insert_p = _clamp(parameters.get("insertion_probability", 0.02), 0.0, 0.1)

    source_items = []
    for sample in samples:
        path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if text:
            source_items.append({"sample": sample, "path": path, "text": text, "used": set(), "failures": 0})

    outputs = []
    output_index = 0
    while len(outputs) < target_count and source_items:
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        remaining = []
        for item in source_items:
            if len(outputs) >= target_count:
                break
            created = None
            for attempt in range(1, MAX_ATTEMPTS_PER_OUTPUT + 1):
                candidate, stats = _perturb(item["text"], strength, delete_p, swap_p, insert_p)
                passed, quality, similarity, edit_ratio = _quality_check(item["text"], candidate)
                if passed and candidate not in item["used"]:
                    created = (candidate, stats, quality, similarity, edit_ratio, attempt)
                    break
            if created is None:
                item["failures"] += 1
                if item["failures"] < 2:
                    remaining.append(item)
                continue

            candidate, stats, quality, similarity, edit_ratio, attempts = created
            item["used"].add(candidate)
            item["failures"] = 0
            remaining.append(item)
            output_path = output_dir / f"{item['path'].stem}_noise_{output_index:04d}{item['path'].suffix or '.txt'}"
            output_path.write_text(candidate, encoding="utf-8")
            outputs.append({
                "source_sample_id": item["sample"].get("id"), "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "structure_noise", "strength": strength,
                    "strategies": [name for name, count in stats.items() if count > 0],
                    "perturbation_counts": stats, "perturbation_count": sum(stats.values()),
                    "similarity": round(similarity, 6), "edit_distance_ratio": round(edit_ratio, 6),
                    "quality_check": quality, "changed": True, "unique_for_source": True,
                    "generation_attempts": attempts,
                },
                "status": "created",
            })
            output_index += 1
            context.set_progress(len(outputs) * 100 / target_count, f"结构噪声 {len(outputs)}/{target_count}")
        source_items = remaining

    logs = []
    if len(outputs) < target_count:
        logs.append(f"合格且唯一的受控噪声变体已耗尽，目标 {target_count} 条，实际生成 {len(outputs)} 条。")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _clamp(value, low: float, high: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(parsed, high))
