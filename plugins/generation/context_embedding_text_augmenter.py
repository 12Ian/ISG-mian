from __future__ import annotations

from pathlib import Path
import re

import numpy as np


PARAMETERS = [
    {
        "name": "mask_ratio",
        "type": "float",
        "label": "Mask比例",
        "default": 0.1,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "被替换的词语比例",
        "required": False,
    },
    {
        "name": "cross_lingual_strength",
        "type": "float",
        "label": "跨语言增强强度",
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "跨语言增强强度",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    mask_ratio = max(0.0, min(float(parameters.get("mask_ratio", parameters.get("mask比例", 0.1)) or 0.1), 1.0))
    cross = max(0.0, min(float(parameters.get("cross_lingual_strength", parameters.get("cross", parameters.get("跨语言增强强度", 0.0))) or 0.0), 1.0))

    synonyms = {
        "好": ["优秀", "良好", "不错"],
        "坏": ["糟糕", "恶劣", "不佳"],
        "大": ["巨大", "庞大", "大规模"],
        "小": ["微小", "细小", "小型"],
        "快": ["迅速", "快速", "敏捷"],
        "慢": ["缓慢", "迟缓", "较慢"],
        "高": ["较高", "更高", "高水平"],
        "低": ["较低", "更低", "低水平"],
        "新": ["崭新", "更新", "全新"],
        "旧": ["陈旧", "老旧", "过时"],
        "强": ["强劲", "显著", "有力"],
        "弱": ["较弱", "微弱", "有限"],
        "明": ["明亮", "清晰", "鲜明"],
        "暗": ["昏暗", "暗淡", "阴暗"],
        "增": ["增强", "提升", "加强"],
        "减": ["减少", "降低", "削减"],
    }

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}

        sample = samples[index % len(samples)]
        sp = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text:
            continue

        cleaned = re.sub(r"\s+", "", text)
        bigram = {}
        for i in range(len(cleaned) - 1):
            bg = cleaned[i : i + 2]
            bigram[bg] = bigram.get(bg, 0) + 1
        total = max(1, sum(bigram.values()))

        out = list(text)
        candidates = [i for i, ch in enumerate(out) if ch in synonyms]
        if candidates:
            num_mask = max(1, int(len(candidates) * mask_ratio))
            if cross > 0:
                num_mask = max(num_mask, int(len(out) * 0.02 * cross))
            np.random.shuffle(candidates)
            selected = candidates[: min(len(candidates), num_mask)]

            for pos in selected:
                key = out[pos]
                cands = synonyms[key]
                left = right = None
                for li in range(pos - 1, -1, -1):
                    if out[li] not in [" ", "\n", "\t", "\r"]:
                        left = out[li]
                        break
                for ri in range(pos + 1, len(out)):
                    if out[ri] not in [" ", "\n", "\t", "\r"]:
                        right = out[ri]
                        break

                best, best_score = key, -1e18
                for cand in cands:
                    if not cand:
                        continue
                    sc = 0.0
                    if left:
                        sc += np.log((bigram.get(left + cand[0], 0) + 1) / (total + 1))
                    for j in range(len(cand) - 1):
                        sc += np.log((bigram.get(cand[j : j + 2], 0) + 1) / (total + 1))
                    if right:
                        sc += np.log((bigram.get(cand[-1] + right, 0) + 1) / (total + 1))
                    if cross > 0:
                        sc += 0.1 * cross
                    if sc > best_score:
                        best_score, best = sc, cand
                out[pos] = best

        out_text = "".join(out)
        if cross > 0:
            if "和" in out_text and np.random.rand() < cross:
                out_text = out_text.replace("和", "以及", 1)
            if "同时" in out_text and np.random.rand() < cross:
                out_text = out_text.replace("同时", "并且", 1)
            if "此外" in out_text and np.random.rand() < cross:
                out_text = out_text.replace("此外", "另外", 1)

        of = output_dir / f"{sp.stem}_ctxemb_{index:04d}{sp.suffix or '.txt'}"
        of.write_text(out_text, encoding="utf-8")
        outputs.append(
            {
                "source_sample_id": sample.get("id"),
                "output_path": str(of),
                "relative_path": of.name,
                "metadata": {
                    "method": "context_embedding",
                    "mask_ratio": mask_ratio,
                    "cross_lingual_strength": cross,
                },
                "status": "created",
            }
        )
        context.set_progress((index + 1) * 100 / target_count, f"Ctx embed {index + 1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
