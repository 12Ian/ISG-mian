from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import math
import re

import numpy as np


PARAMETERS = [{
    "name": "replacement_ratio", "type": "float", "label": "替换比例", "default": 0.3,
    "min": 0.0, "max": 1.0, "options": [], "description": "按完整词语或短语替换的比例", "required": False,
}]


# 通用词语按词性分组；不提供单汉字规则，避免破坏“强大、做好、大小”等完整词语。
SYNONYM_RULES = (
    # 动词及动宾短语
    ("进行分析", ("开展分析", "作出分析"), "verb"),
    ("进行处理", ("执行处理", "开展处理"), "verb"),
    ("进行说明", ("作出说明", "予以说明"), "verb"),
    ("采取措施", ("实施措施", "采用相应措施"), "verb"),
    ("解决问题", ("处理问题", "应对问题"), "verb"),
    ("产生影响", ("带来影响", "造成影响"), "verb"),
    ("实现目标", ("达成目标", "完成目标"), "verb"),
    ("满足要求", ("符合要求", "达到要求"), "verb"),
    ("保持稳定", ("维持稳定", "确保稳定"), "verb"),
    ("保持一致", ("维持一致", "确保一致"), "verb"),
    ("显著提高", ("明显提升", "大幅提高"), "verb"),
    ("逐步完善", ("持续完善", "逐渐健全"), "verb"),
    ("提升", ("提高", "改善"), "verb"),
    ("增强", ("加强", "提升"), "verb"),
    ("降低", ("减少", "下调"), "verb"),
    ("优化", ("改进", "完善"), "verb"),
    ("发现", ("察觉", "观察到"), "verb"),
    ("表明", ("说明", "显示"), "verb"),
    ("采用", ("使用", "选用"), "verb"),
    ("完成", ("实现", "达成"), "verb"),
    # 名词及名词短语
    ("主要原因", ("核心原因", "首要原因"), "noun"),
    ("实际情况", ("现实情况", "具体情况"), "noun"),
    ("相关数据", ("有关数据", "对应数据"), "noun"),
    ("关键因素", ("重要因素", "核心因素"), "noun"),
    ("技术方案", ("技术路径", "实施方案"), "noun"),
    ("工作效率", ("执行效率", "处理效率"), "noun"),
    ("质量问题", ("质量缺陷", "品质问题"), "noun"),
    ("安全风险", ("安全隐患", "潜在风险"), "noun"),
    ("鲁棒性", ("稳健性", "抗干扰能力"), "noun"),
    ("泛化能力", ("迁移能力", "普适能力"), "noun"),
    ("方法", ("方式", "办法"), "noun"),
    ("结果", ("成果", "结论"), "noun"),
    ("过程", ("流程", "进程"), "noun"),
    ("问题", ("难题", "事项"), "noun"),
    # 形容与程度表达
    ("表现良好", ("表现出色", "表现较好"), "adjective"),
    ("效果明显", ("效果显著", "成效突出"), "adjective"),
    ("较为明显", ("比较明显", "相对显著"), "adjective"),
    ("非常重要", ("十分重要", "尤为关键"), "adjective"),
    ("十分", ("非常", "相当"), "adverb"),
    ("非常", ("十分", "相当"), "adverb"),
    ("更加", ("更为", "进一步"), "adverb"),
    ("明显", ("显著", "突出"), "adjective"),
    ("快速", ("迅速", "较快"), "adjective"),
    ("缓慢", ("迟缓", "较慢"), "adjective"),
    # 连接表达
    ("与此同时", ("同时", "在此期间"), "conjunction"),
    ("同时", ("并且", "与此同时"), "conjunction"),
    ("因此", ("所以", "因而"), "conjunction"),
    ("此外", ("另外", "除此之外"), "conjunction"),
    ("然而", ("不过", "但是"), "conjunction"),
    ("因为", ("由于", "缘于"), "conjunction"),
)

FORBIDDEN = ("维持热爱", "做良好", "做优秀", "造成目标", "达成问题", "结论显示结果")
NEGATION_RE = re.compile(r"没有|不能|不可|并非|未曾|无需|无须|不|未|无|否|非(?!常)")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _find_matches(text: str) -> list[dict]:
    matches, occupied = [], []
    for source, targets, pos in sorted(SYNONYM_RULES, key=lambda item: len(item[0]), reverse=True):
        for match in re.finditer(re.escape(source), text):
            start, end = match.span()
            if any(start < used_end and end > used_start for used_start, used_end in occupied):
                continue
            matches.append({"start": start, "end": end, "source": source, "targets": targets, "pos": pos})
            occupied.append((start, end))
    return sorted(matches, key=lambda item: item["start"])


def _make_candidate(text: str, matches: list[dict], ratio: float) -> tuple[str, list[dict]]:
    count = min(len(matches), max(1, math.ceil(len(matches) * ratio)))
    indexes = np.random.choice(len(matches), size=count, replace=False)
    selected = [matches[int(index)] for index in indexes]
    output, records = text, []
    for item in sorted(selected, key=lambda value: value["start"], reverse=True):
        target = str(np.random.choice(item["targets"]))
        output = output[:item["start"]] + target + output[item["end"]:]
        records.append({
            "start": item["start"], "source": item["source"], "target": target, "pos": item["pos"],
        })
    records.reverse()
    return output, records


def _quality_check(source: str, candidate: str, existing: list[str]) -> tuple[bool, dict]:
    similarity = SequenceMatcher(None, source, candidate).ratio()
    result = {
        "changed": candidate != source,
        "numbers_preserved": NUMBER_RE.findall(source) == NUMBER_RE.findall(candidate),
        "negations_preserved": NEGATION_RE.findall(source) == NEGATION_RE.findall(candidate),
        "forbidden_collocation": next((value for value in FORBIDDEN if value in candidate), ""),
        "similarity": round(similarity, 4),
        "near_duplicate": any(SequenceMatcher(None, candidate, old).ratio() >= 0.985 for old in existing),
    }
    result["passed"] = (
        result["changed"] and result["numbers_preserved"] and result["negations_preserved"]
        and not result["forbidden_collocation"] and 0.72 <= similarity <= 0.98 and not result["near_duplicate"]
    )
    return result["passed"], result


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    ratio = max(0.0, min(float(parameters.get("replacement_ratio", parameters.get("ratio", parameters.get("替换比例", 0.3))) or 0.3), 1.0))
    sources = []
    for sample in samples:
        path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        matches = _find_matches(text)
        if matches:
            sources.append((sample, path, text, matches))

    outputs, unique_by_source = [], defaultdict(list)
    attempts_by_source = defaultdict(int)
    attempts, max_attempts = 0, max(target_count * 15, len(sources) * 15)
    while sources and len(outputs) < target_count and attempts < max_attempts:
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample, path, text, matches = sources[attempts % len(sources)]
        key = str(sample.get("id") or path)
        attempts += 1
        attempts_by_source[key] += 1
        candidate, records = _make_candidate(text, matches, ratio)
        passed, quality = _quality_check(text, candidate, unique_by_source[key])
        if not passed:
            continue
        output_path = output_dir / f"{path.stem}_syn_{len(outputs):04d}{path.suffix or '.txt'}"
        output_path.write_text(candidate, encoding="utf-8")
        unique_by_source[key].append(candidate)
        outputs.append({
            "source_sample_id": sample.get("id"), "output_path": str(output_path), "relative_path": output_path.name,
            "metadata": {
                "method": "synonym_replacement", "ratio": ratio, "replacements": records,
                "replacement_count": len(records), "changed": True, "unique_for_source": True,
                "attempts": attempts_by_source[key], "quality_result": quality,
            },
            "status": "created",
        })
        context.set_progress(len(outputs) * 100 / target_count, f"同义词替换 {len(outputs)}/{target_count}")

    logs = []
    if len(outputs) < target_count:
        logs.append(f"合格且唯一的同义词变体已耗尽，目标 {target_count} 条，实际生成 {len(outputs)} 条。")
    return {"ok": True, "outputs": outputs, "logs": logs}
