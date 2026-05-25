from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": 'mask_ratio',
        "type": 'float',
        "label": '掩码比例',
        "default": 0.75,
        "min": 0.1,
        "max": 0.95,
        "options": [],
        "description": '图像patch掩码比例',
        "required": False,
    },
    {
        "name": 'learning_rate',
        "type": 'float',
        "label": '学习率',
        "default": 0.0001,
        "min": 1e-06,
        "max": 0.1,
        "options": [],
        "description": '训练学习率',
        "required": False,
    },
    {
        "name": 'training_steps',
        "type": 'int',
        "label": '训练步数',
        "default": 100,
        "min": 10,
        "max": 10000,
        "options": [],
        "description": '模拟训练迭代步数',
        "required": False,
    },
    {
        "name": 'patch_size',
        "type": 'int',
        "label": 'Patch大小',
        "default": 4,
        "min": 2,
        "max": 32,
        "options": [],
        "description": 'ViT patch划分尺寸',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY"}
    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}
    target_count = max(1, int(payload.get("target_count") or len(samples)))
    mask_ratio = max(0.0, min(float(parameters.get("mask_ratio", 0.75) or 0.75), 0.95))
    train_cap = max(5, min(int(parameters.get("train_cap", 100) or 100), 300))
    ps = int(parameters.get("ps", 4) or 4)
    lr = float(parameters.get("lr", 0.0001) or 0.0001)
    device = torch.device("cpu")
    image_size = 32
    if image_size % ps != 0:
        return {"ok": False, "error_code": "INVALID_PATCH_SIZE"}
    max_images = max(2, min(64, int(parameters.get("max_images", 32))))
    tensors = _read_img(samples, image_size, max_images, device)
    if tensors is None or tensors.size(0) < 2:
        return _fb(payload, context, output_dir, samples, target_count, "vit_mae", parameters)
    n, bs = tensors.size(0), min(16, tensors.size(0))
    nps, npatch, pdim = image_size // ps, (image_size // ps) ** 2, 3 * ps * ps
    edim = 128
    el = nn.TransformerEncoderLayer(d_model=edim, nhead=4, dim_feedforward=edim*4, dropout=0.0, activation="gelu", batch_first=True)
    encoder = nn.TransformerEncoder(el, num_layers=4).to(device)
    pe = nn.Linear(pdim, edim).to(device)
    mt = nn.Parameter(torch.zeros(1, 1, edim, device=device))
    pos = nn.Parameter(torch.zeros(1, npatch, edim, device=device))
    hd = nn.Sequential(nn.LayerNorm(edim), nn.Linear(edim, pdim)).to(device)
    torch.nn.init.normal_(pos, 0.0, 0.02)
    torch.nn.init.normal_(mt, 0.0, 0.02)
    opt = optim.Adam(list(pe.parameters())+list(encoder.parameters())+list(hd.parameters())+[mt, pos], lr=lr)
    steps = min(train_cap, max(20, n*2))
    for step in range(steps):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        idx = torch.randint(0, n, (bs,), device=device)
        x0 = tensors[idx]
        m = torch.rand(bs, npatch, device=device) < mask_ratio
        if m.all():
            m = torch.rand(bs, npatch, device=device) < min(0.5, mask_ratio)
        pred, target = _fwd(x0, m, pe, mt, pos, encoder, hd, ps, nps, image_size)
        loss = torch.mean((pred[m] - target[m]) ** 2)
        opt.zero_grad()
        loss.backward()
        opt.step()
        context.set_progress(step * 50 / steps, f"ViT-MAE train {step+1}/{steps}")
    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        ci = int(np.random.randint(0, tensors.size(0)))
        x0 = tensors[ci:ci+1]
        m = torch.rand(1, npatch, device=device) < mask_ratio
        if m.all():
            m = torch.rand(1, npatch, device=device) < min(0.5, mask_ratio)
        patches = _patch(x0, ps, nps)
        tokens = pe(patches)
        tokens = torch.where(m.unsqueeze(-1), mt.expand(tokens.size(0), tokens.size(1), -1), tokens)
        tokens = tokens + pos
        h = encoder(tokens)
        pred = hd(h)
        out_p = torch.where(m.unsqueeze(-1), pred, patches)
        x_rec = _unpatch(out_p, ps, nps, image_size).clamp(-1.0, 1.0)
        img = _to_bgr(x_rec[0])
        out_f = output_dir / f"vit_mae_{index:04d}.jpg"
        if not write_image(out_f, img):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {out_f}"}
        outputs.append({
            "source_sample_id": samples[0].get("id"),
            "output_path": str(out_f),
            "relative_path": out_f.name,
            "metadata": {"method": "vit_mae"},
            "status": "created",
        })
        context.set_progress(50 + (index+1)*50/target_count, f"ViT-MAE gen {index+1}/{target_count}")
    return {"ok": True, "outputs": outputs, "logs": []}


def _fb(payload, context, output_dir, samples, target_count, method, parameters):
    ps = int(parameters.get("ps", 4) or 4)
    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        s = samples[index % len(samples)]
        p = Path(s.get("sample_path") or s.get("path") or "")
        img = read_image(p)
        if img is None:
            continue
        h, w = img.shape[:2]
        if h < ps or w < ps:
            out = cv2.GaussianBlur(img, (3, 3), 0)
        else:
            imr = cv2.resize(img, (32, 32), interpolation=cv2.INTER_AREA)
            pse = ps if 32 % ps == 0 else 4
            blocks = [[imr[y:y+pse, x:x+pse].copy() for x in range(0, 32, pse)] for y in range(0, 32, pse)]
            for _ in range(8):
                y1, x1 = np.random.randint(0, len(blocks)), np.random.randint(0, len(blocks[0]))
                y2, x2 = np.random.randint(0, len(blocks)), np.random.randint(0, len(blocks[0]))
                blocks[y1][x1], blocks[y2][x2] = blocks[y2][x2], blocks[y1][x1]
            out = np.zeros_like(imr)
            for yy in range(0, 32, pse):
                for xx in range(0, 32, pse):
                    out[yy:yy+pse, xx:xx+pse] = blocks[yy//pse][xx//pse]
            out = cv2.GaussianBlur(out, (3, 3), 0)
        of = output_dir / f"{method}_{index:04d}.jpg"
        if not write_image(of, out):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {of}"}
        outputs.append({"source_sample_id": s.get("id"), "output_path": str(of), "relative_path": of.name, "metadata": {"method": method, "fallback": True}, "status": "created"})
        context.set_progress((index+1)*100/target_count, f"{method} fb {index+1}/{target_count}")
    return {"ok": True, "outputs": outputs, "logs": ["fallback mode"]}


def _read_img(samples, image_size, max_images, device):
    import torch
    tensors = []
    for s in samples[:max_images]:
        p = str(Path(s.get("sample_path") or s.get("path") or ""))
        img = read_image(p)
        if img is None:
            continue
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = cv2.resize(img, (image_size, image_size), interpolation=cv2.INTER_AREA)
        x = torch.from_numpy(img).permute(2, 0, 1).to(device=device, dtype=torch.float32) / 255.0
        tensors.append(x * 2.0 - 1.0)
    return torch.stack(tensors, dim=0) if len(tensors) >= 2 else None


def _to_bgr(x):
    import torch
    x = x.detach().cpu().clamp(-1.0, 1.0)
    x = (x + 1.0) / 2.0
    x = (x * 255.0).to(torch.uint8).permute(1, 2, 0).numpy()
    return cv2.cvtColor(x, cv2.COLOR_RGB2BGR)


def _patch(x, ps, nps):
    B, C, H, W = x.shape
    x = x.view(B, C, nps, ps, nps, ps).permute(0, 2, 4, 1, 3, 5).contiguous()
    return x.view(B, nps*nps, C*ps*ps)


def _unpatch(patches, ps, nps, sz):
    B, P, D = patches.shape
    x = patches.view(B, nps, nps, 3, ps, ps).permute(0, 3, 1, 4, 2, 5).contiguous()
    return x.view(B, 3, sz, sz)


def _fwd(x, mask, pe, mt, pos, encoder, hd, ps, nps, sz):
    patches = _patch(x, ps, nps)
    tokens = pe(patches)
    tokens = torch.where(mask.unsqueeze(-1), mt.expand(tokens.size(0), tokens.size(1), -1), tokens)
    tokens = tokens + pos
    h = encoder(tokens)
    pred = hd(h)
    return pred, patches
