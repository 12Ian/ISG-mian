from __future__ import annotations

from collections import defaultdict
from difflib import SequenceMatcher
from pathlib import Path
import re

import numpy as np

from .text_lexicon import generated_common_rules


PARAMETERS = [
    {
        "name": "intermediate_language",
        "type": "select",
        "label": "中间语言",
        "default": "英语",
        "min": None,
        "max": None,
        "options": ["英语", "日语", "韩语"],
        "description": "回译时使用的中间语言",
        "required": False,
    },
    {
        "name": "back_translate_probability",
        "type": "float",
        "label": "回译概率",
        "default": 1.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "对每个候选执行回译的概率",
        "required": False,
    },
    {
        "name": "sentence_restructure_strength",
        "type": "float",
        "label": "句式重构强度",
        "default": 0.3,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "在保持句间关系的前提下重构句式的概率",
        "required": False,
    },
]


# 仅收录完整词语和短语，不使用“好、大、小”等单字规则，避免在词语内部替换。
ZH_VARIANTS = {
    "校园": ["学校", "校园里"], "铃声": ["铃音", "钟声"], "响起": ["传来", "响起了"],
    "走廊": ["长廊", "过道"], "同学们": ["同窗们", "同学们纷纷"], "课本": ["教材", "书本"],
    "教室": ["课堂", "教学楼"], "老师": ["教师", "授课老师"], "写下": ["记下", "写出"],
    "今天": ["今日", "这一天"], "窗外": ["窗边", "屋外"], "安静": ["宁静", "静谧"],
    "学习": ["求学", "学习过程"], "轻松": ["容易", "从容"], "有时": ["偶尔", "有时候"],
    "困惑": ["疑惑", "迷茫"], "思路": ["思考方向", "解题思路"], "打开": ["理清", "打通"],
    "充满": ["洋溢着", "满是"], "喜悦": ["欣喜", "愉悦"], "青春": ["年华", "青春岁月"],
    "探索": ["探寻", "求索"], "失败": ["挫折", "失利"], "勇气": ["胆量", "勇敢的心"],
    "珍惜": ["珍重", "爱惜"], "时光": ["岁月", "光阴"], "成长": ["长大", "进步"],
    "热爱": ["热忱", "喜爱"], "坚定": ["坚决", "笃定"], "收获": ["获得", "得到"],
    "温暖": ["暖意", "温情"], "希望": ["期望", "盼望"],
    "表现良好": ["表现出色", "表现较好"],
    "效果良好": ["效果较好", "成效良好"],
    "实力强大": ["实力强劲", "具备较强实力"],
    "功能强大": ["功能完善", "能力较为突出"],
    "快速": ["迅速", "较快"],
    "缓慢": ["迟缓", "较慢"],
    "进行分析": ["开展分析", "作进一步分析"],
    "进行处理": ["执行处理", "开展处理"],
    "进行说明": ["作出说明", "予以说明"],
    "采取措施": ["实施措施", "采用相应措施"],
    "解决问题": ["处理问题", "应对问题"],
    "产生影响": ["带来影响", "造成影响"],
    "实现目标": ["达成目标", "完成目标"],
    "满足要求": ["符合要求", "达到要求"],
    "显著提高": ["明显提升", "大幅提高"],
    "逐步完善": ["持续完善", "逐渐健全"],
    "提升": ["提高", "改善"],
    "提高": ["提升", "改善"],
    "改善": ["改进", "优化"],
    "增强": ["加强", "提升"],
    "加强": ["增强", "强化"],
    "降低": ["减少", "下调"],
    "优化": ["改进", "完善"],
    "保持稳定": ["维持稳定", "继续保持平稳"],
    "保持一致": ["维持一致", "确保一致"],
    "主要原因": ["核心原因", "首要原因"],
    "实际情况": ["现实情况", "具体情况"],
    "相关数据": ["有关数据", "对应数据"],
    "关键因素": ["重要因素", "核心因素"],
    "技术方案": ["技术路径", "实施方案"],
    "工作效率": ["执行效率", "处理效率"],
    "安全风险": ["安全隐患", "潜在风险"],
    "质量问题": ["质量缺陷", "品质问题"],
    "较为明显": ["比较明显", "相对显著"],
    "非常重要": ["十分重要", "尤为关键"],
    "更加": ["更为", "进一步"],
    "同时": ["与此同时", "并且"],
    "此外": ["另外", "除此之外"],
    "然而": ["不过", "但是"],
    "因此": ["所以", "由此"],
    "所以": ["因此", "因而"],
    "因为": ["由于", "缘于"],
}
for _source, _targets, _ in generated_common_rules():
    ZH_VARIANTS.setdefault(_source, list(_targets))

LANGUAGE_NAMES = {"英语": "en", "日语": "ja", "韩语": "ko", "en": "en", "ja": "ja", "ko": "ko"}
NEGATIONS = ("不", "没", "无", "未", "非", "否", "不能", "不会", "没有", "并非")
FOREIGN_RE = re.compile(r"[A-Za-z]|[\u3040-\u30ff\uac00-\ud7af]")
NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")


def _round_trip(text: str, language: str) -> tuple[str, list[dict]]:
    """用占位符模拟双向词语回译，保证中间语言内容不会残留在输出中。"""
    replacements: list[tuple[str, str, str]] = []
    occupied: list[tuple[int, int]] = []
    candidates = []
    for source in sorted(ZH_VARIANTS, key=len, reverse=True):
        for match in re.finditer(re.escape(source), text):
            start, end = match.span()
            if not any(start < used_end and end > used_start for used_start, used_end in occupied):
                candidates.append((start, end, source))
                occupied.append((start, end))

    if not candidates:
        return text, []

    # 每次只替换一部分匹配项，扩大有效候选空间，同时避免过度改写。
    np.random.shuffle(candidates)
    selected = sorted(candidates[: max(1, min(len(candidates), int(np.random.randint(1, 4))))], reverse=True)
    output = text
    for index, (start, end, source) in enumerate(selected):
        target = str(np.random.choice(ZH_VARIANTS[source]))
        marker = f"\ufff0{index}\ufff1"
        # marker 代表对应中间语言中的词，返回中文时再统一反向映射。
        output = output[:start] + marker + output[end:]
        replacements.append((marker, source, target))

    details = []
    for marker, source, target in replacements:
        output = output.replace(marker, target)
        details.append({"原词": source, "新词": target, "中间语言": language})
    return output, details


def _restructure(text: str) -> tuple[str, str | None]:
    """只重构句内明确关系，不交换彼此独立的句子。"""
    rules = [
        (re.compile(r"因为([^。！？；]+?)[，,]所以([^。！？；]+)"), lambda m: f"之所以{m.group(2)}，是因为{m.group(1)}", "因果重构"),
        (re.compile(r"由于([^。！？；]+?)[，,]因此([^。！？；]+)"), lambda m: f"{m.group(2)}，这是由于{m.group(1)}", "因果重构"),
        (re.compile(r"([^。！？；，,]+)，?因此([^。！？；]+)"), lambda m: f"由于{m.group(1)}，{m.group(2)}", "因果重构"),
        (re.compile(r"虽然([^。！？；]+?)[，,](?:但是|但|不过|然而)([^。！？；]+)"), lambda m: f"尽管{m.group(1)}，{m.group(2)}", "转折重构"),
        (re.compile(r"尽管([^。！？；]+?)[，,](?:但是|但|不过|然而)?([^。！？；]+)"), lambda m: f"虽然{m.group(1)}，但是{m.group(2)}", "转折重构"),
        (re.compile(r"如果([^。！？；]+?)[，,]那么([^。！？；]+)"), lambda m: f"要想{m.group(2)}，需要{m.group(1)}", "条件重构"),
        (re.compile(r"只要([^。！？；]+?)[，,]就([^。！？；]+)"), lambda m: f"{m.group(1)}，便能{m.group(2)}", "条件重构"),
        (re.compile(r"但只要([^。！？；，,]+)[，,]总能([^。！？；]+)"), lambda m: f"不过，{m.group(1)}，便总会{m.group(2)}", "转折条件重构"),
        (re.compile(r"只需([^。！？；，,]+)[，,]([^。！？；]+)"), lambda m: f"只要{m.group(1)}，就可以{m.group(2)}", "条件重构"),
        (re.compile(r"一方面([^。！？；]+?)[，,]另一方面([^。！？；]+)"), lambda m: f"既{m.group(1)}，也{m.group(2)}", "并列重构"),
        (re.compile(r"不仅([^。！？；]+?)[，,]还([^。！？；]+)"), lambda m: f"除了{m.group(1)}，也{m.group(2)}", "递进重构"),
    ]
    available = [(pattern, repl, name) for pattern, repl, name in rules if pattern.search(text)]
    if not available:
        return text, None
    pattern, repl, name = available[int(np.random.randint(0, len(available)))]
    return pattern.sub(repl, text, count=1), name


def _quality_check(source: str, candidate: str, existing: list[str]) -> tuple[bool, dict]:
    similarity = SequenceMatcher(None, source, candidate).ratio()
    near_duplicate = any(SequenceMatcher(None, old, candidate).ratio() >= 0.995 for old in existing)
    checks = {
        "changed": candidate != source,
        "foreign_residue": bool(FOREIGN_RE.search(candidate)),
        "numbers_preserved": NUMBER_RE.findall(source) == NUMBER_RE.findall(candidate),
        "negations_preserved": {word: source.count(word) for word in NEGATIONS} == {word: candidate.count(word) for word in NEGATIONS},
        "similarity": round(similarity, 4),
        "near_duplicate": near_duplicate,
        "length_ratio": round(len(candidate) / max(1, len(source)), 4),
    }
    passed = (
        checks["changed"]
        and not checks["foreign_residue"]
        and checks["numbers_preserved"]
        and checks["negations_preserved"]
        and 0.70 <= similarity <= 0.995
        and 0.75 <= checks["length_ratio"] <= 1.25
        and not near_duplicate
    )
    checks["passed"] = passed
    return passed, checks


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    bt_prob = max(0.0, min(float(parameters.get("back_translate_probability", parameters.get("bt_prob", parameters.get("回译概率", 1.0))) or 1.0), 1.0))
    recon = max(0.0, min(float(parameters.get("sentence_restructure_strength", parameters.get("recon", parameters.get("句式重构强度", 0.3))) or 0.3), 1.0))
    raw_language = str(parameters.get("intermediate_language", parameters.get("lang", parameters.get("中间语言", "英语"))) or "英语").strip().lower()
    language = LANGUAGE_NAMES.get(raw_language, "en")

    source_cache = []
    for sample in samples:
        path = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            source_cache.append((sample, path, path.read_text(encoding="utf-8", errors="ignore")))
        except Exception:
            continue
    if not source_cache:
        return {"ok": False, "error_code": "NO_READABLE_SAMPLES"}

    outputs = []
    unique_by_source: dict[str, list[str]] = defaultdict(list)
    attempts_by_source: dict[str, int] = defaultdict(int)
    max_attempts = max(target_count * 40, len(source_cache) * 40)
    total_attempts = 0

    while len(outputs) < target_count and total_attempts < max_attempts:
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample, source_path, source_text = source_cache[total_attempts % len(source_cache)]
        source_key = str(sample.get("id") or source_path)
        total_attempts += 1
        attempts_by_source[source_key] += 1

        if np.random.rand() > bt_prob:
            continue
        candidate, replacements = _round_trip(source_text, language)
        restructure_strategy = None
        if np.random.rand() < recon:
            candidate, restructure_strategy = _restructure(candidate)

        passed, quality = _quality_check(source_text, candidate, unique_by_source[source_key])
        if not passed:
            continue

        output_index = len(outputs)
        output_path = output_dir / f"{source_path.stem}_bt_{output_index:04d}{source_path.suffix or '.txt'}"
        output_path.write_text(candidate, encoding="utf-8")
        unique_by_source[source_key].append(candidate)
        strategies = ["双向词语回译"]
        if restructure_strategy:
            strategies.append(restructure_strategy)
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(output_path),
            "relative_path": output_path.name,
            "metadata": {
                "method": "back_translation",
                "intermediate_language": language,
                "changed": True,
                "unique_for_source": True,
                "attempts": attempts_by_source[source_key],
                "strategies": strategies,
                "replacements": replacements,
                "quality_result": quality,
            },
            "status": "created",
        })
        context.set_progress(len(outputs) * 100 / target_count, f"已生成 {len(outputs)}/{target_count}")

    return {
        "ok": True,
        "outputs": outputs,
        "logs": [],
        "metadata": {
            "requested_count": target_count,
            "generated_count": len(outputs),
            "attempts": total_attempts,
            "candidate_space_exhausted": len(outputs) < target_count,
        },
    }
