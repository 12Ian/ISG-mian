from __future__ import annotations

import itertools
import math
import re
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": "replacement_ratio", "type": "float", "label": "替换比例", "default": 0.3,
        "min": 0.0, "max": 1.0, "options": [], "description": "完整词语/短语被替换的比例", "required": False,
    },
    {
        "name": "pos_constraint", "type": "string", "label": "词性约束", "default": "",
        "min": None, "max": None, "options": [], "description": "可选 adjective、verb、noun、conjunction，留空表示不限制", "required": False,
    },
    {
        "name": "phrase_level", "type": "bool", "label": "短语级替换", "default": True,
        "min": None, "max": None, "options": [], "description": "是否允许多词短语级替换", "required": False,
    },
]


# 规则按完整词语或短语定义，不再提供单汉字替换。长规则优先匹配。
RULES = (
    {"source": "进行分析", "targets": ("开展分析", "实施分析"), "pos": "verb", "kind": "phrase"},
    {"source": "进行处理", "targets": ("开展处理", "执行处理"), "pos": "verb", "kind": "phrase"},
    {"source": "进行说明", "targets": ("作出说明", "予以说明"), "pos": "verb", "kind": "phrase"},
    {"source": "采取措施", "targets": ("实施措施", "采用相应措施"), "pos": "verb", "kind": "phrase"},
    {"source": "解决问题", "targets": ("处理问题", "应对问题"), "pos": "verb", "kind": "phrase"},
    {"source": "产生影响", "targets": ("带来影响", "造成影响"), "pos": "verb", "kind": "phrase"},
    {"source": "实现目标", "targets": ("达成目标", "完成目标"), "pos": "verb", "kind": "phrase"},
    {"source": "满足要求", "targets": ("符合要求", "达到要求"), "pos": "verb", "kind": "phrase"},
    {"source": "保持稳定", "targets": ("维持稳定", "确保稳定"), "pos": "verb", "kind": "phrase"},
    {"source": "保持一致", "targets": ("维持一致", "确保一致"), "pos": "verb", "kind": "phrase"},
    {"source": "显著提高", "targets": ("明显提升", "大幅提高"), "pos": "verb", "kind": "phrase"},
    {"source": "逐步完善", "targets": ("持续完善", "逐渐健全"), "pos": "verb", "kind": "phrase"},
    {"source": "主要原因", "targets": ("核心原因", "首要原因"), "pos": "noun", "kind": "phrase"},
    {"source": "实际情况", "targets": ("现实情况", "具体情况"), "pos": "noun", "kind": "phrase"},
    {"source": "相关数据", "targets": ("有关数据", "对应数据"), "pos": "noun", "kind": "phrase"},
    {"source": "关键因素", "targets": ("重要因素", "核心因素"), "pos": "noun", "kind": "phrase"},
    {"source": "技术方案", "targets": ("技术路径", "实施方案"), "pos": "noun", "kind": "phrase"},
    {"source": "工作效率", "targets": ("执行效率", "处理效率"), "pos": "noun", "kind": "phrase"},
    {"source": "质量问题", "targets": ("质量缺陷", "品质问题"), "pos": "noun", "kind": "phrase"},
    {"source": "安全风险", "targets": ("安全隐患", "潜在风险"), "pos": "noun", "kind": "phrase"},
    {"source": "提升", "targets": ("提高", "改善"), "pos": "verb", "kind": "word"},
    {"source": "增强", "targets": ("提升", "加强"), "pos": "verb", "kind": "word"},
    {"source": "降低", "targets": ("减少", "下调"), "pos": "verb", "kind": "word"},
    {"source": "优化", "targets": ("改进", "完善"), "pos": "verb", "kind": "word"},
    {"source": "鲁棒性", "targets": ("稳健性", "抗干扰能力"), "pos": "noun", "kind": "word"},
    {"source": "泛化能力", "targets": ("迁移能力", "普适能力"), "pos": "noun", "kind": "phrase"},
    {"source": "较为明显", "targets": ("比较明显", "相对显著"), "pos": "adjective", "kind": "phrase"},
    {"source": "非常重要", "targets": ("十分重要", "尤为关键"), "pos": "adjective", "kind": "phrase"},
    {"source": "同时", "targets": ("与此同时", "并且"), "pos": "conjunction", "kind": "word"},
    {"source": "因此", "targets": ("所以", "因而"), "pos": "conjunction", "kind": "word"},
    {"source": "此外", "targets": ("另外", "除此之外"), "pos": "conjunction", "kind": "word"},
    {"source": "然而", "targets": ("不过", "但是"), "pos": "conjunction", "kind": "word"},
)
FORBIDDEN_COLLOCATIONS = (
    "做良好", "做优秀", "维持热爱", "强劲大", "显著大", "强宏大", "强庞大", "轻微事", "更新的风景",
)
NEGATION_PATTERN = re.compile(r"没有|不能|不可|并非|未曾|无需|无须|不|未|无|否|非(?!常)")
MAX_VARIANTS_PER_SOURCE = 1000


def _as_bool(value) -> bool:
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "否"}
    return bool(value)


def _find_matches(text: str, pos_constraint: str, phrase_level: bool) -> list[dict]:
    matches = []
    occupied = []
    normalized_pos = pos_constraint.strip().lower()
    for rule in sorted(RULES, key=lambda item: len(item["source"]), reverse=True):
        if normalized_pos and rule["pos"] != normalized_pos:
            continue
        if not phrase_level and rule["kind"] == "phrase":
            continue
        for match in re.finditer(re.escape(rule["source"]), text):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            left_pattern = rule.get("left")
            right_pattern = rule.get("right")
            if left_pattern and not re.search(left_pattern, text[:start]):
                continue
            if right_pattern and not re.match(right_pattern, text[end:]):
                continue
            matches.append({"start": start, "end": end, "rule": rule})
            occupied.append((start, end))
    return sorted(matches, key=lambda item: item["start"])


def _apply_replacements(text: str, selected: tuple[dict, ...], targets: tuple[str, ...]) -> tuple[str, list[dict]]:
    output = text
    records = []
    for match, target in sorted(zip(selected, targets), key=lambda item: item[0]["start"], reverse=True):
        source = match["rule"]["source"]
        output = output[:match["start"]] + target + output[match["end"]:]
        records.append({
            "start": match["start"], "end": match["end"], "source": source,
            "target": target, "pos": match["rule"]["pos"], "kind": match["rule"]["kind"],
        })
    records.reverse()
    return output, records


def _quality_check(source: str, candidate: str) -> tuple[bool, str, float]:
    if not candidate.strip() or candidate == source:
        return False, "unchanged", 1.0
    if any(value in candidate for value in FORBIDDEN_COLLOCATIONS):
        return False, "forbidden_collocation", 0.0
    if re.findall(r"\d+(?:\.\d+)?", source) != re.findall(r"\d+(?:\.\d+)?", candidate):
        return False, "numbers_changed", 0.0
    if len(NEGATION_PATTERN.findall(source)) != len(NEGATION_PATTERN.findall(candidate)):
        return False, "negation_changed", 0.0
    similarity = SequenceMatcher(None, source, candidate).ratio()
    if similarity > 0.98:
        return False, "change_too_small", similarity
    if similarity < 0.72:
        return False, "change_too_large", similarity
    return True, "passed", similarity


def _source_variants(text: str, ratio: float, pos_constraint: str, phrase_level: bool) -> list[dict]:
    matches = _find_matches(text, pos_constraint, phrase_level)
    if not matches or ratio <= 0:
        return []
    replace_count = max(1, math.ceil(len(matches) * ratio))
    replace_count = min(replace_count, len(matches))
    accepted = []
    attempts = 0

    for selected in itertools.combinations(matches, replace_count):
        target_groups = [item["rule"]["targets"] for item in selected]
        for targets in itertools.product(*target_groups):
            attempts += 1
            candidate, records = _apply_replacements(text, selected, targets)
            passed, quality, similarity = _quality_check(text, candidate)
            near_duplicate = any(SequenceMatcher(None, candidate, item["text"]).ratio() > 0.985 for item in accepted)
            if passed and not near_duplicate:
                accepted.append({
                    "text": candidate, "records": records, "similarity": similarity,
                    "quality": quality, "attempts": attempts,
                })
            if len(accepted) >= MAX_VARIANTS_PER_SOURCE:
                return accepted
    return accepted


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    ratio = max(0.0, min(float(parameters.get("replacement_ratio", parameters.get("ratio", 0.3)) or 0.0), 1.0))
    pos_constraint = str(parameters.get("pos_constraint", "") or "")
    phrase_level = _as_bool(parameters.get("phrase_level", True))

    source_items = []
    for sample in samples:
        path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        variants = _source_variants(text, ratio, pos_constraint, phrase_level)
        np.random.shuffle(variants)
        if variants:
            source_items.append({"sample": sample, "path": path, "variants": variants, "cursor": 0})

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
            output_path = output_dir / f"{item['path'].stem}_vocab_{output_index:04d}{item['path'].suffix or '.txt'}"
            output_path.write_text(variant["text"], encoding="utf-8")
            outputs.append({
                "source_sample_id": item["sample"].get("id"), "output_path": str(output_path),
                "relative_path": output_path.name,
                "metadata": {
                    "method": "vocabulary_phrase", "ratio": ratio, "phrase_level": phrase_level,
                    "pos_constraint": pos_constraint, "replacements": variant["records"],
                    "replacement_count": len(variant["records"]), "similarity": round(variant["similarity"], 6),
                    "quality_check": variant["quality"], "changed": True, "unique_for_source": True,
                    "generation_attempts": variant["attempts"],
                },
                "status": "created",
            })
            output_index += 1
            context.set_progress(len(outputs) * 100 / target_count, f"词汇短语替换 {len(outputs)}/{target_count}")
        source_items = remaining

    logs = []
    if len(outputs) < target_count:
        logs.append(f"合格且唯一的词汇短语变体已耗尽，目标 {target_count} 条，实际生成 {len(outputs)} 条。")
    return {"ok": True, "outputs": outputs, "logs": logs}
