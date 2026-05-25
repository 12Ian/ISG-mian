from __future__ import annotations

from pathlib import Path

import numpy as np


PARAMETERS = [
    {
        "name": 'perturbation_strength',
        "type": 'float',
        "label": '扰动强度',
        "default": 0.1,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '字符级噪声扰动强度',
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
    strength = max(0.0, min(float(parameters.get("strength", parameters.get("扰动强度", 0.1)) or 0.1), 1.0))

    insert_pool = list("的一是在不了有和人这中大为上个国我以要到时由业也能下去向你")
    insert_pool += list("，。！？；：、 ")
    insert_pool = [c for c in insert_pool if c.strip()]

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
        if not text:
            continue

        chars = list(text)
        op_count = int(max(1, len(text) * strength))

        for _ in range(op_count):
            if len(chars) <= 1:
                break
            p = np.random.rand()
            if p < 0.25:
                del_idx = int(np.random.randint(0, len(chars)))
                if len(chars) > 1:
                    del chars[del_idx]
            elif p < 0.50:
                ins_idx = int(np.random.randint(0, len(chars)))
                chars.insert(ins_idx, str(np.random.choice(insert_pool)))
            elif p < 0.75:
                i = int(np.random.randint(0, len(chars) - 1))
                chars[i], chars[i + 1] = chars[i + 1], chars[i]
            else:
                i = int(np.random.randint(0, len(chars)))
                if chars[i] in "，。！？；：":
                    m = {"，": "、", "。": "！", "！": "。", "？": "！", "；": "，", "：": "；"}
                    chars[i] = m.get(chars[i], chars[i])
                elif np.random.rand() < 0.3:
                    chars.insert(i, " ")

        out = output_dir / f"{sp.stem}_noise_{index:04d}{sp.suffix or '.txt'}"
        out.write_text("".join(chars), encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "structure_noise", "strength": strength},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Struct noise {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
