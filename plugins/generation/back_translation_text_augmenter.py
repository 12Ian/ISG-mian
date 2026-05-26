from __future__ import annotations

from pathlib import Path
import re

import numpy as np


PARAMETERS = [
    {
        "name": 'intermediate_language',
        "type": 'select',
        "label": '中间语言',
        "default": 'en',
        "min": None,
        "max": None,
        "options": ['en', 'ja', 'ko'],
        "description": '回译的中间语言代码',
        "required": False,
    },
    {
        "name": 'back_translate_probability',
        "type": 'float',
        "label": '回译概率',
        "default": 1.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '对每个样本执行回译的概率',
        "required": False,
    },
    {
        "name": 'sentence_restructure_strength',
        "type": 'float',
        "label": '句式重构强度',
        "default": 0.3,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '回译后的句式重组强度',
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
    bt_prob = max(0.0, min(float(parameters.get("bt_prob", parameters.get("回译概率", 1.0)) or 1.0), 1.0))
    recon = max(0.0, min(float(parameters.get("recon", parameters.get("句式重构强度", 0.3)) or 0.3), 1.0))

    zh2en = {
        "好": ["good", "great"], "坏": ["bad", "poor"], "优秀": ["excellent", "great"],
        "良好": ["good", "fine"], "出色": ["excellent", "outstanding"], "差": ["bad", "poor"],
        "大": ["big", "large"], "巨大": ["huge", "massive"], "小型": ["small-scale", "small"],
        "小": ["small", "tiny"], "微小": ["tiny", "minute"], "快": ["fast", "quick"],
        "迅速": ["rapid", "quick"], "快速": ["quick", "rapid"], "慢": ["slow", "sluggish"],
        "缓慢": ["slow", "gradual"], "迟缓": ["slow", "delayed"],
        "提升": ["improve", "enhance"], "增强": ["enhance", "boost"],
        "鲁棒性": ["robustness", "reliability"], "泛化": ["generalization"],
        "保持": ["maintain", "preserve"],
    }
    en2zh = {}
    for zh, ens in zh2en.items():
        for en in ens:
            en2zh.setdefault(en, []).append(zh)

    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample = samples[index % len(samples)]
        sp = Path(sample.get("sample_path") or sample.get("path") or "")
        try:
            text = sp.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        if np.random.rand() > bt_prob:
            out_text = text
        else:
            keys = sorted(zh2en.keys(), key=len, reverse=True)
            en_text = text
            for k in keys:
                if k in en_text:
                    en_text = en_text.replace(k, f" {str(np.random.choice(zh2en[k]))} ")
            en_text = re.sub(r"\s+", " ", en_text).strip()

            tokens = re.findall(r"[A-Za-z]+|[^A-Za-z]+", en_text)
            new_tokens = []
            for tok in tokens:
                if re.fullmatch(r"[A-Za-z]+", tok or ""):
                    lo = tok.lower()
                    if lo in en2zh:
                        new_tokens.append(str(np.random.choice(en2zh[lo])))
                    else:
                        new_tokens.append(tok)
                else:
                    new_tokens.append(tok)
            out_text = re.sub(r"\s+", "", "".join(new_tokens))

        if np.random.rand() < recon:
            parts = re.split(r"(，|；|。|！|？)", out_text)
            t_idxs = [i for i in range(0, len(parts)) if i % 2 == 0]
            if len(t_idxs) >= 3:
                segs = [parts[i] for i in t_idxs]
                first, last = segs[0], segs[-1]
                mid = segs[1:-1]
                np.random.shuffle(mid)
                new_segs = [first] + mid + [last]
                for idx, seg in zip(t_idxs, new_segs):
                    parts[idx] = seg
                out_text = "".join(parts)

        out = output_dir / f"{sp.stem}_bt_{index:04d}{sp.suffix or '.txt'}"
        out.write_text(out_text, encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "back_translation"},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Back trans {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
