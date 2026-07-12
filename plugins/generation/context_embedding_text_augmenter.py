from __future__ import annotations

import itertools
import re
from collections import defaultdict, deque
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": "mask_ratio", "type": "float", "label": "Mask比例", "default": 0.25,
        "min": 0.0, "max": 1.0, "options": [], "description": "被替换的词语比例", "required": False,
    },
    {
        "name": "cross_lingual_strength", "type": "float", "label": "跨语言增强强度", "default": 0.35,
        "min": 0.0, "max": 1.0, "options": [], "description": "跨语言表达替换强度", "required": False,
    },
    {
        "name": "context_style", "type": "select", "label": "上下文语体", "default": "natural",
        "min": None, "max": None, "options": ["formal", "natural", "concise"],
        "description": "formal: 正式; natural: 自然; concise: 简洁", "required": False,
    },
]


PHRASE_REPLACEMENTS = {
    "进行分析": ["开展分析", "作进一步分析"], "进行处理": ["执行处理", "开展处理"],
    "解决问题": ["处理问题", "应对问题"], "采取措施": ["实施措施", "采用相应措施"],
    "产生影响": ["带来影响", "造成影响"], "满足要求": ["符合要求", "达到要求"],
    "实际情况": ["具体情况", "现实情况"], "主要原因": ["核心原因", "首要原因"],
    "关键因素": ["重要因素", "核心因素"], "相关数据": ["有关数据", "对应数据"],
    "显著提高": ["明显提升", "大幅提高"], "逐步完善": ["持续完善", "逐渐健全"],
    "较为明显": ["比较明显", "相对显著"], "非常重要": ["十分重要", "尤为关键"],
}
CONNECTOR_REPLACEMENTS = {
    "同时": "并且", "此外": "另外", "因此": "所以", "但是": "不过", "和": "以及",
    "and": "as well as", "however": "nevertheless",
}
NEGATION_PATTERN = re.compile(r"没有|不能|不可|并非|未曾|无需|无须|不|未|无|否|非(?!常)")
MAX_VARIANTS_PER_SOURCE = 1000
STYLE_PREFIXES = {
    "formal": ("在此基础上，", "进一步分析可知，", "结合前述内容，"),
    "natural": ("接着来看，", "与此同时，", "从前文来看，"),
    "concise": ("进一步看，", "同时，", "由此看，"),
}


def _split_sentences(text: str) -> list[str]:
    pattern = r"[^。！？!?]+[。！？!?]"
    sentences = re.findall(pattern, text)
    remainder = re.sub(pattern, "", text).strip()
    if remainder:
        sentences.append(remainder)
    return sentences


def _context_prefix(previous: str, current: str, style: str) -> list[str]:
    if re.search(r"^(但是|但|然而|不过)", current.strip()):
        return ["从前文来看，", "结合上述内容，"]
    if re.search(r"(因此|所以|由此)", current):
        return ["基于前述内容，", "由此进一步来看，"]
    if re.search(r"(同时|此外|另外)", current):
        return ["在此基础上，", "与此同时，"]
    if re.search(r"(困难|问题|风险|不足)", previous + current):
        return ["面对这一情况，", "从这一问题出发，"]
    return list(STYLE_PREFIXES.get(style, STYLE_PREFIXES["natural"]))


def _relation_operations(text: str) -> list[tuple[str, str]]:
    rules = (
        ("因果展开", r"因为([^。！？；]+?)[，,](?:所以|因此)([^。！？；]+)", r"\2，其原因在于\1"),
        ("因果展开", r"([^。！？；]+?)[，,]因此([^。！？；]+)", r"由于\1，\2"),
        ("因果展开", r"([^。！？；，,]+?)导致([^。！？；]+)", r"由于\1，因而\2"),
        ("转折承接", r"尽管([^。！？；，,]+?)[，,](?:但是|但)([^。！？；]+)", r"虽然\1，但\2"),
        ("转折承接", r"([^。！？；]+?)[，,](?:但是|不过|然而)([^。！？；]+)", r"\1；不过，\2"),
        ("条件展开", r"如果([^。！？；，,]+?)[，,]那么([^。！？；]+)", r"在\1的条件下，\2"),
        ("条件展开", r"只要([^。！？；，,]+?)[，,]就([^。！？；]+)", r"若能\1，便可\2"),
    )
    operations = []
    for strategy, pattern, replacement in rules:
        if re.search(pattern, text):
            operations.append((strategy, re.sub(pattern, replacement, text, count=1)))
    return operations


def _single_context_operations(sentences: list[str], style: str) -> list[tuple[str, str]]:
    operations = []
    for index, sentence in enumerate(sentences):
        clean = sentence.strip()
        if not clean:
            continue
        if index > 0:
            for prefix in _context_prefix(sentences[index - 1], clean, style):
                updated = sentences[:]
                updated[index] = prefix + clean
                operations.append(("承接", "".join(updated)))

        if index not in {0, len(sentences) - 1}:
            for prefix in ("需要指出的是，", "值得注意的是，"):
                updated = sentences[:]
                updated[index] = prefix + clean
                operations.append(("扩展", "".join(updated)))

        # 解释模板复述原句，不引入原文之外的事实。
        if len(clean) <= 80 and not NEGATION_PATTERN.search(clean):
            updated = sentences[:]
            updated.insert(index + 1, "换言之，" + clean)
            operations.append(("解释", "".join(updated)))

        if index > 0:
            previous = sentences[index - 1]
            reference = "这一现象" if "现象" in previous else "该过程" if "过程" in previous else "上述情况"
            updated = sentences[:]
            updated[index] = reference + "下，" + clean
            operations.append(("指代承接", "".join(updated)))

    if len(sentences) >= 2:
        last = sentences[-1].strip()
        if last and not NEGATION_PATTERN.search(last):
            operations.append(("总结", "".join(sentences) + "总体而言，" + last))

    # 长句按已有标点拆分，短句用分号合并，不添加新的事实关系。
    for index, sentence in enumerate(sentences):
        if len(sentence) > 55 and "，" in sentence:
            updated = sentences[:]
            updated[index] = sentence.replace("，", "。", 1)
            operations.append(("长短句转换", "".join(updated)))
        if index + 1 < len(sentences) and len(sentence) < 35 and len(sentences[index + 1]) < 35:
            merged = sentences[:index] + [sentence.rstrip("。！？!?，,") + "；" + sentences[index + 1]] + sentences[index + 2:]
            operations.append(("长短句转换", "".join(merged)))

    # 局部摘要直接复用相邻原句，避免引入原文之外的实体和结论。
    for index in range(len(sentences) - 1):
        pair = sentences[index].strip() + sentences[index + 1].strip()
        if len(pair) <= 130 and not NEGATION_PATTERN.search(pair):
            updated = sentences[:index + 2] + ["概括而言，" + pair] + sentences[index + 2:]
            operations.append(("局部摘要", "".join(updated)))
    return operations


def _lexical_variants(text: str, mask_ratio: float, cross_strength: float) -> list[tuple[str, str]]:
    variants = []
    phrases = [phrase for phrase in PHRASE_REPLACEMENTS if phrase in text]
    max_phrases = max(1, round(len(phrases) * mask_ratio)) if phrases else 0
    for phrase in phrases[:max_phrases]:
        for replacement in PHRASE_REPLACEMENTS[phrase]:
            variants.append(("词语替换", text.replace(phrase, replacement, 1)))
    if cross_strength > 0:
        for source, target in CONNECTOR_REPLACEMENTS.items():
            if source in text:
                variants.append(("连接表达", text.replace(source, target, 1)))
    return variants


def _quality_check(source: str, candidate: str) -> tuple[bool, str]:
    if not candidate.strip() or candidate == source:
        return False, "unchanged"
    if re.findall(r"\d+(?:\.\d+)?", source) != re.findall(r"\d+(?:\.\d+)?", candidate):
        return False, "numbers_changed"
    if len(NEGATION_PATTERN.findall(source)) != len(NEGATION_PATTERN.findall(candidate)):
        return False, "negation_changed"
    ratio = len(candidate.strip()) / max(1, len(source.strip()))
    if not 0.75 <= ratio <= 1.55:
        return False, "length_out_of_range"
    similarity = SequenceMatcher(None, source, candidate).ratio()
    if similarity > 0.985:
        return False, "change_too_small"
    if similarity < 0.55:
        return False, "change_too_large"
    return True, "passed"


def _source_variants(text: str, mask_ratio: float, cross_strength: float, style: str = "natural") -> list[dict]:
    sentences = _split_sentences(text)
    raw_candidates = _single_context_operations(sentences, style)
    raw_candidates.extend(_relation_operations(text))
    raw_candidates.extend(_lexical_variants(text, mask_ratio, cross_strength))

    # 将词语变化与上下文变化进行有限组合，扩大变体空间但控制长度和复杂度。
    lexical = _lexical_variants(text, mask_ratio, cross_strength)
    contextual = _single_context_operations(sentences, style) + _relation_operations(text)
    for (context_strategy, context_text), (lexical_strategy, _) in itertools.islice(
        itertools.product(contextual, lexical), MAX_VARIANTS_PER_SOURCE
    ):
        combined = context_text
        for source, replacements in PHRASE_REPLACEMENTS.items():
            if source in combined:
                combined = combined.replace(source, replacements[0], 1)
                break
        raw_candidates.append((context_strategy + "+" + lexical_strategy, combined))

    unique = {}
    attempts = 0
    for strategy, candidate in raw_candidates:
        attempts += 1
        passed, quality = _quality_check(text, candidate)
        near_duplicate = any(SequenceMatcher(None, candidate, existing).ratio() > 0.975 for existing in unique)
        if passed and candidate not in unique and not near_duplicate:
            unique[candidate] = {
                "text": candidate, "strategy": strategy, "quality": quality, "attempts": attempts,
            }
        if len(unique) >= MAX_VARIANTS_PER_SOURCE:
            break
    return list(unique.values())


def _balance_by_strategy(variants: list[dict]) -> list[dict]:
    """按策略轮询，避免输出被单一模板占满。"""
    groups = defaultdict(deque)
    for variant in variants:
        groups[variant["strategy"].split("+", 1)[0]].append(variant)
    balanced = []
    while groups:
        for strategy in list(groups):
            balanced.append(groups[strategy].popleft())
            if not groups[strategy]:
                del groups[strategy]
    return balanced


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    mask_ratio = _clamp_float(parameters.get("mask_ratio", 0.25), 0.0, 1.0)
    cross_strength = _clamp_float(parameters.get("cross_lingual_strength", parameters.get("cross", 0.35)), 0.0, 1.0)
    style = str(parameters.get("context_style", "natural") or "natural").strip().lower()
    if style not in STYLE_PREFIXES:
        style = "natural"

    source_items = []
    for sample in samples:
        sample_path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = sample_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        variants = _balance_by_strategy(_source_variants(text, mask_ratio, cross_strength, style))
        if variants:
            source_items.append({"sample": sample, "path": sample_path, "source": text, "variants": variants, "cursor": 0})

    estimated_total = sum(len(item["variants"]) for item in source_items)
    outputs = []
    output_index = 0
    while len(outputs) < target_count and source_items:
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        remaining = []
        for item in source_items:
            if len(outputs) >= target_count:
                break
            cursor = item["cursor"]
            if cursor >= len(item["variants"]):
                continue
            variant = item["variants"][cursor]
            item["cursor"] += 1
            remaining.append(item)
            output_path = output_dir / f"{item['path'].stem}_ctxemb_{output_index:04d}{item['path'].suffix or '.txt'}"
            output_path.write_text(variant["text"], encoding="utf-8")
            outputs.append({
                "source_sample_id": item["sample"].get("id"), "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "context_embedding", "mask_ratio": mask_ratio,
                    "cross_lingual_strength": cross_strength, "context_style": style, "changed": True,
                    "unique_for_source": True, "strategy": variant["strategy"],
                    "quality_check": variant["quality"], "generation_attempts": variant["attempts"],
                    "estimated_max_variants": len(item["variants"]),
                },
                "status": "created",
            })
            output_index += 1
            context.set_progress(len(outputs) * 100 / target_count, f"上下文增强 {len(outputs)}/{target_count}")
        source_items = remaining

    logs = [f"根据当前源文本和质量阈值，建议最大生成数量约为 {estimated_total} 条。"]
    if len(outputs) < target_count:
        logs.append(f"可用的唯一上下文变体已耗尽，目标 {target_count} 条，实际生成 {len(outputs)} 条。")
    return {"ok": True, "outputs": outputs, "logs": logs}


def _clamp_float(value, low, high):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = low
    return max(low, min(parsed, high))
