from __future__ import annotations

from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": 'replacement_ratio',
        "type": 'float',
        "label": '替换比例',
        "default": 0.3,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '词汇/短语被替换的比例',
        "required": False,
    },
    {
        "name": 'pos_constraint',
        "type": 'string',
        "label": '词性约束',
        "default": '',
        "min": None,
        "max": None,
        "options": [],
        "description": '限定替换的词性，留空表示无约束',
        "required": False,
    },
    {
        "name": 'phrase_level',
        "type": 'bool',
        "label": '短语级替换',
        "default": True,
        "min": None,
        "max": None,
        "options": [],
        "description": '是否进行短语级别替换',
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
    ratio = max(0.0, min(float(parameters.get("ratio", parameters.get("替换比例", 0.3)) or 0.3), 1.0))
    phrase = bool(parameters.get("phrase", parameters.get("是否短语级替换", True)))

    word_syn = {
        "好": ["优秀", "良好", "出色"], "坏": ["糟糕", "差", "恶劣"],
        "大": ["巨大", "庞大", "大型"], "小": ["微小", "细小", "小型"],
        "快": ["迅速", "快速", "敏捷"], "慢": ["缓慢", "迟缓", "低速"],
    }
    phrase_syn = {
        "提升": ["增强", "改进"], "增强": ["提升", "加固"],
        "鲁棒性": ["可靠性", "适应性"], "泛化": ["泛化能力", "推广"],
        "保持": ["维持", "维系"],
    }

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

        out = text
        if phrase:
            keys = sorted(phrase_syn.keys(), key=len, reverse=True)
            for k in keys:
                if k in out and np.random.rand() < ratio:
                    out = out.replace(k, str(np.random.choice(phrase_syn[k])))

        for k, cands in word_syn.items():
            if k in out and np.random.rand() < ratio:
                out = out.replace(k, str(np.random.choice(cands)))

        of = output_dir / f"{sp.stem}_vocab_{index:04d}{sp.suffix or '.txt'}"
        of.write_text(out, encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(of),
            "relative_path": of.name,
            "metadata": {"method": "vocabulary_phrase", "ratio": ratio},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Vocab/phrase {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
