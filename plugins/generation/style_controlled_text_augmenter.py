from __future__ import annotations

import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": "style_label",
        "type": "select",
        "label": "目标风格",
        "default": "formal",
        "min": None,
        "max": None,
        "options": ["formal", "casual", "concise"],
        "description": "formal: 正式; casual: 口语化; concise: 简洁",
        "required": False,
    },
    {
        "name": "conciseness_strength",
        "type": "float",
        "label": "简洁压缩强度",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "简洁风格下的压缩强度",
        "required": False,
    },
]


# 只收录语义偏移风险较低的短语，长短语优先，避免短词先替换破坏上下文。
FORMAL_REPLACEMENTS = (
    ("我觉得", "可以认为"), ("我认为", "可以认为"), ("说白了", "简而言之"),
    ("总的来说", "总体而言"), ("但是", "然而"), ("不过", "然而"),
    ("所以", "因此"), ("另外", "此外"), ("然后", "随后"),
    ("搞清楚", "明确"), ("搞", "进行"), ("挺", "较为"),
    ("特别", "尤其"), ("感觉", "认为"),
)
CASUAL_REPLACEMENTS = (
    ("可以认为", "我觉得"), ("简而言之", "说白了"), ("总体而言", "总的来说"),
    ("然而", "不过"), ("因此", "所以"), ("此外", "另外"),
    ("随后", "然后"), ("进行", "做"), ("较为", "挺"),
    ("十分", "很"), ("尤其", "特别"), ("认为", "觉得"),
)
CONCISE_REPLACEMENTS = (
    ("在这种情况下", "此时"), ("从这个角度来看", "由此看"),
    ("需要注意的是", "需注意"), ("换句话说", "即"),
    ("与此同时", "同时"), ("由于这个原因", "因此"),
    ("并且", "且"), ("同时", "且"),
)

FILLER_PATTERNS = (
    r"(?<!并)其实[，,]?", r"我个人觉得[，,]?", r"某种程度上[，,]?",
    r"可以说[，,]?", r"基本上", r"大概", r"大致", r"真的", r"非常",
)
NEGATION_PATTERN = re.compile(r"没有|不能|不可|并非|未曾|无需|无须|不|未|无|否|非(?!常)")

FORMAL_SENTENCE_RULES = (
    (r"有人([^。！？；]+?)[，,]有人([^。！？；]+)", r"一些人\1，另一些人\2"),
    (r"([^。！？；，,]+?)并不是([^。！？；，,]+?)[，,]而是([^。！？；]+)", r"\1并非\2，而是\3"),
    (r"([^。！？；，,]+?)不必([^。！？；，,]+?)[，,]只需([^。！？；]+)", r"\1无需\2，只需\3"),
    (r"愿([^；。！？]+)[；;]愿([^。！？]+)", r"希望\1；同时也希望\2"),
    (r"如果([^。！？；，,]+?)[，,]那么([^。！？；]+)", r"若\1，则\2"),
    (r"一方面([^。！？；]+?)[，,]另一方面([^。！？；]+)", r"一方面\1；另一方面\2"),
)
CASUAL_SENTENCE_RULES = (
    (r"之所以([^。！？；，,]+?)[，,]是因为([^。！？；]+)", r"\1，主要是因为\2"),
    (r"若([^。！？；，,]+?)[，,]则([^。！？；]+)", r"如果\1，那就\2"),
    (r"一方面([^。！？；]+?)[；;]另一方面([^。！？；]+)", r"一边是\1，另一边是\2"),
    (r"希望([^；。！？]+)[；;]同时也希望([^。！？]+)", r"希望\1，也希望\2"),
)
CONCISE_SENTENCE_RULES = (
    (r"尽管([^。！？；，,]+?)[，,](?:但是|但)([^。！？；]+)", r"虽\1，但\2"),
    (r"如果([^。！？；，,]+?)[，,]那么([^。！？；]+)", r"若\1，则\2"),
    (r"一方面([^。！？；]+?)[，,]另一方面([^。！？；]+)", r"\1；同时\2"),
    (r"之所以([^。！？；，,]+?)[，,]是因为([^。！？；]+)", r"\1，源于\2"),
    (r"([^。！？；，,]+?)不必([^。！？；，,]+?)[，,]只需([^。！？；]+)", r"\1无需\2，只需\3"),
)


def _replace_phrases(text: str, replacements, probability: float = 0.8) -> str:
    out = text
    for source, target in replacements:
        if source in out and np.random.rand() < probability:
            out = out.replace(source, target)
    return out


def _rewrite_sentence_patterns(text: str, rules, probability: float) -> str:
    """按完整句式匹配改写，各规则可独立组合以扩大变体空间。"""
    out = text
    for pattern, replacement in rules:
        if re.search(pattern, out) and np.random.rand() < probability:
            out = re.sub(pattern, replacement, out)
    return out


FORMAL_OPENERS = ("总体而言，", "从整体来看，", "综合来看，")
CASUAL_OPENERS = ("说实话，", "简单来说，", "总的来说，")


def _rewrite_formal(text: str, variant_index: int = 0) -> str:
    out = _replace_phrases(text, FORMAL_REPLACEMENTS)
    out = _rewrite_sentence_patterns(out, FORMAL_SENTENCE_RULES, 0.65)
    if "每个人都" in out and np.random.rand() < 0.7:
        out = out.replace("每个人都", "人们各自")
    # 将常见主观开场改为客观陈述，属于句式改写而非单词替换。
    out = re.sub(r"(?:我|我们)(?:觉得|感觉|看来)[，,]?", "可以认为，", out, count=1)
    if re.search(r"[。！？]", out) and not re.match(r"^(总体而言|综上|因此|此外)", out):
        if np.random.rand() < 0.5:
            out = FORMAL_OPENERS[variant_index % len(FORMAL_OPENERS)] + out
    return out


def _rewrite_casual(text: str, variant_index: int = 0) -> str:
    out = _replace_phrases(text, CASUAL_REPLACEMENTS)
    out = _rewrite_sentence_patterns(out, CASUAL_SENTENCE_RULES, 0.65)
    # 只在句首增加轻量口语标记，避免在每个标点处机械插词。
    if re.search(r"[。！？]", out) and not re.match(r"^(说实话|我觉得|总的来说)", out):
        if np.random.rand() < 0.45:
            out = CASUAL_OPENERS[variant_index % len(CASUAL_OPENERS)] + out
    out = re.sub(r"需要注意的是[，,]?", "要注意的是，", out)
    return out


def _rewrite_concise(text: str, strength: float) -> str:
    out = _replace_phrases(text, CONCISE_REPLACEMENTS, max(0.5, strength))
    out = _rewrite_sentence_patterns(out, CONCISE_SENTENCE_RULES, max(0.55, strength))
    for pattern in FILLER_PATTERNS:
        if np.random.rand() < strength:
            out = re.sub(pattern, "", out)

    # 压缩重复的连接结构，但不盲目删除后半篇文本。
    out = re.sub(r"[，,]\s*(?:而且|并且)\s*", "，且", out)
    out = re.sub(r"([，,。；;])\s*\1+", r"\1", out)
    out = re.sub(r"^[，,；;\s]+|[，,；;\s]+$", "", out)
    return out


def _quality_check(source: str, candidate: str, style: str, strength: float) -> tuple[bool, str]:
    source_clean = source.strip()
    candidate_clean = candidate.strip()
    if not candidate_clean:
        return False, "empty_output"

    # 数字常承载标签、数量和测量结果，增强后必须完整保留。
    if re.findall(r"\d+(?:\.\d+)?", source) != re.findall(r"\d+(?:\.\d+)?", candidate):
        return False, "numbers_changed"

    # 防止规则误删或新增否定，导致语义方向翻转。
    if len(NEGATION_PATTERN.findall(source)) != len(NEGATION_PATTERN.findall(candidate)):
        return False, "negation_changed"

    source_len = max(1, len(source_clean))
    ratio = len(candidate_clean) / source_len
    min_ratio = max(0.45, 0.85 - 0.35 * strength) if style == "concise" else 0.65
    max_ratio = 1.15 if style == "concise" else 1.45
    if not min_ratio <= ratio <= max_ratio:
        return False, "length_out_of_range"
    return True, "passed"


def _augment(text: str, style: str, concise_strength: float, variant_index: int = 0) -> tuple[str, str]:
    if style in ("formal", "academic"):
        candidate = _rewrite_formal(text, variant_index)
    elif style in ("casual", "colloquial"):
        candidate = _rewrite_casual(text, variant_index)
    elif style in ("concise", "succinct"):
        candidate = _rewrite_concise(text, concise_strength)
    else:
        return text, "unknown_style"

    passed, reason = _quality_check(text, candidate, style, concise_strength)
    return (candidate, reason) if passed else (text, f"fallback:{reason}")


def _generate_unique_variant(
    text: str,
    style: str,
    concise_strength: float,
    used_texts: set[str],
    max_attempts: int = 12,
) -> tuple[str, str, bool, int]:
    """优先返回未出现过的合格改写，规则空间耗尽时返回变化最大的候选。"""
    candidates = []
    for attempt in range(max_attempts):
        candidate, quality = _augment(text, style, concise_strength, attempt)
        if candidate not in used_texts:
            return candidate, quality, True, attempt + 1
        candidates.append((candidate, quality))

    candidate, quality = min(
        candidates,
        key=lambda item: SequenceMatcher(None, text, item[0]).ratio(),
    )
    return candidate, quality, False, max_attempts


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    style = str(parameters.get("style_label", parameters.get("style", parameters.get("风格标签", "formal"))) or "formal").strip().lower()
    concise = max(0.0, min(float(parameters.get("conciseness_strength", parameters.get("concise", parameters.get("简洁强度", 0.5))) or 0.5), 1.0))

    outputs = []
    generated_by_source: dict[str, set[str]] = {}
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample = samples[index % len(samples)]
        sp = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        source_key = str(sample.get("id") or sp.resolve())
        used_texts = generated_by_source.setdefault(source_key, set())
        out, quality, unique, attempts = _generate_unique_variant(text, style, concise, used_texts)
        used_texts.add(out)
        output_path = output_dir / f"{sp.stem}_style_{index:04d}{sp.suffix or '.txt'}"
        output_path.write_text(out, encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {
                "method": "style_controlled",
                "style": style,
                "quality_check": quality,
                "changed": out != text,
                "unique_for_source": unique,
                "generation_attempts": attempts,
            },
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Style ctrl {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
