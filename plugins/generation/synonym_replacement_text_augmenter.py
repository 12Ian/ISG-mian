from __future__ import annotations

from pathlib import Path
import re

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
        "description": '文本中词语被同义词替换的比例',
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

    synonyms = {
        "好": ["优秀", "良好", "出色"],
        "坏": ["糟糕", "差", "恶劣"],
        "大": ["巨大", "庞大", "大型"],
        "小": ["微小", "细小", "小型"],
        "快": ["迅速", "快速", "敏捷"],
        "慢": ["缓慢", "迟缓", "低速"],
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

        words = re.findall(r"\b\w+\b", text)
        new_words = []
        for w in words:
            if w in synonyms and np.random.random() < ratio:
                new_words.append(str(np.random.choice(synonyms[w])))
            else:
                new_words.append(w)

        out = output_dir / f"{sp.stem}_syn_{index:04d}{sp.suffix or '.txt'}"
        out.write_text(" ".join(new_words), encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "synonym_replacement", "ratio": ratio},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Synonym repl {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
