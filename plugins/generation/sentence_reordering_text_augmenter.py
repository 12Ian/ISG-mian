from __future__ import annotations

import itertools
import math
import re
from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": "reorder_granularity",
        "type": "select",
        "label": "重排粒度",
        "default": "sentence",
        "min": None,
        "max": None,
        "options": ["sentence", "paragraph"],
        "description": "sentence: 句子级; paragraph: 段落级",
        "required": False,
    },
    {
        "name": "shuffle_strength",
        "type": "float",
        "label": "打乱强度",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "打乱的比例强度",
        "required": False,
    },
    {
        "name": "preserve_first_last",
        "type": "bool",
        "label": "保留首尾",
        "default": True,
        "min": None,
        "max": None,
        "options": [],
        "description": "是否保留首句/首段和尾句/尾段不变",
        "required": False,
    },
]

MAX_VARIANTS_PER_SOURCE = 5000


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "否"}
    return bool(value)


def _split_units(text: str, granularity: str) -> tuple[list[str], str]:
    if granularity == "paragraph":
        return [block for block in re.split(r"\n\s*\n", text.strip()) if block.strip()], "\n\n"

    pattern = r"[^。！？!?]+[。！？!?]"
    sentences = re.findall(pattern, text)
    remainder = re.sub(pattern, "", text).strip()
    if remainder:
        sentences.append(remainder)
    return sentences, ""


def _build_variants(units: list[str], strength: float, keep_ends: bool) -> list[list[str]]:
    if len(units) < 2 or strength <= 0:
        return []

    # 先排除首尾，再决定抽取数量，避免抽到受保护位置后只剩一项。
    eligible = list(range(1, len(units) - 1)) if keep_ends else list(range(len(units)))
    if len(eligible) < 2:
        return []

    selected_count = max(2, math.ceil(len(eligible) * strength))
    selected_count = min(selected_count, len(eligible))
    variants = []

    for positions in itertools.combinations(eligible, selected_count):
        original = tuple(units[index] for index in positions)
        for reordered in itertools.permutations(original):
            if reordered == original:
                continue
            candidate = units[:]
            for position, value in zip(positions, reordered):
                candidate[position] = value
            variants.append(candidate)
            if len(variants) >= MAX_VARIANTS_PER_SOURCE:
                return variants
    return variants


def _source_variants(text: str, granularity: str, strength: float, keep_ends: bool) -> list[str]:
    units, separator = _split_units(text, granularity)
    variants = [separator.join(items) for items in _build_variants(units, strength, keep_ends)]
    # 理论上排列不会重复；内容相同的句子可能导致相同文本，因此仍做一次稳定去重。
    return list(dict.fromkeys(candidate for candidate in variants if candidate != text))


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    raw_granularity = str(parameters.get("reorder_granularity", parameters.get("gran", parameters.get("重排粒度", "sentence"))) or "sentence").strip().lower()
    granularity = "paragraph" if raw_granularity in {"paragraph", "段落"} else "sentence"
    strength = max(0.0, min(float(parameters.get("shuffle_strength", parameters.get("shuf", parameters.get("打乱强度", 0.5))) or 0.0), 1.0))
    keep_ends = _as_bool(parameters.get("preserve_first_last", parameters.get("keep_ends", parameters.get("保留首尾", True))))

    source_items = []
    for sample in samples:
        sample_path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = sample_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if not text:
            continue
        variants = _source_variants(text, granularity, strength, keep_ends)
        np.random.shuffle(variants)
        if variants:
            source_items.append({"sample": sample, "path": sample_path, "text": text, "variants": variants, "cursor": 0})

    outputs = []
    output_index = 0
    while len(outputs) < target_count and source_items:
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}

        remaining_sources = []
        for item in source_items:
            if len(outputs) >= target_count:
                break
            cursor = item["cursor"]
            variants = item["variants"]
            if cursor >= len(variants):
                continue

            out = variants[cursor]
            item["cursor"] = cursor + 1
            remaining_sources.append(item)
            sample = item["sample"]
            sample_path = item["path"]
            output_path = output_dir / f"{sample_path.stem}_reorder_{output_index:04d}{sample_path.suffix or '.txt'}"
            output_path.write_text(out, encoding="utf-8")
            outputs.append({
                "source_sample_id": sample.get("id"),
                "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "sentence_reordering",
                    "granularity": granularity,
                    "changed": out != item["text"],
                    "unique_for_source": True,
                    "generation_attempts": cursor + 1,
                },
                "status": "created",
            })
            output_index += 1
            context.set_progress(len(outputs) * 100 / target_count, f"篇章重排 {len(outputs)}/{target_count}")

        source_items = remaining_sources

    logs = []
    if len(outputs) < target_count:
        logs.append(f"可用的唯一重排结果已耗尽，目标 {target_count} 条，实际生成 {len(outputs)} 条。")
    return {"ok": True, "outputs": outputs, "logs": logs}
