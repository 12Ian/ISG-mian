from __future__ import annotations

from pathlib import Path
import re

import numpy as np


PARAMETERS = [
    {
        "name": 'mask_ratio',
        "type": 'float',
        "label": 'Mask比例',
        "default": 0.1,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '被替换的词语比例',
        "required": False,
    },
    {
        "name": 'cross_lingual_strength',
        "type": 'float',
        "label": '跨语言增强强度',
        "default": 0.0,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": '跨语言增强强度',
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
    cross = max(0.0, min(float(parameters.get("cross", parameters.get("跨语言增强强度", 0.0)) or 0.0), 1.0))

    synonyms = {
        "好": ["优秀", "良好", "出色"], "坏": ["糟糕", "差", "恶劣"],
        "大": ["巨大", "庞大", "大型"], "小": ["微小", "细小", "小型"],
        "快": ["迅速", "快速", "敏捷"], "慢": ["缓慢", "迟缓", "低速"],
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
        if not text:
            continue

        cleaned = re.sub(r"\s+", "", text)
        bigram = {}
        for i in range(len(cleaned) - 1):
            bg = cleaned[i:i + 2]
            bigram[bg] = bigram.get(bg, 0) + 1
        total = max(1, sum(bigram.values()))

        out = list(text)
        candidates = [i for i, ch in enumerate(out) if ch in synonyms]
        if not candidates:
            out_text = "".join(out)
        else:
            num_mask = max(1, int(len(candidates) * mask_ratio))
            np.random.shuffle(candidates)
            selected = candidates[:num_mask]

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
                    if left and cand:
                        sc += np.log((bigram.get(left + cand[0], 0) + 1) / (total + 1))
                    for j in range(len(cand) - 1):
                        sc += np.log((bigram.get(cand[j:j + 2], 0) + 1) / (total + 1))
                    if cand and right:
                        sc += np.log((bigram.get(cand[-1] + right, 0) + 1) / (total + 1))
                    if sc > best_score:
                        best_score, best = sc, cand
                out[pos] = best

            out_text = "".join(out)

        of = output_dir / f"{sp.stem}_ctxemb_{index:04d}{sp.suffix or '.txt'}"
        of.write_text(out_text, encoding="utf-8")
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(of),
            "relative_path": of.name,
            "metadata": {"method": "context_embedding", "mask_ratio": mask_ratio},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"Ctx embed {index+1}/{target_count}")

    return {"ok": True, "outputs": outputs, "logs": []}
