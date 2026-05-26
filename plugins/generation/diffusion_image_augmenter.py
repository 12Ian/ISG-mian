from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ._image_io import read_image, write_image


PARAMETERS = [
    {
        "name": 'diffusion_steps',
        "type": 'int',
        "label": '扩散步数',
        "default": 1000,
        "min": 10,
        "max": 5000,
        "options": [],
        "description": '扩散过程的最大时间步数',
        "required": False,
    },
    {
        "name": 'cfg_guidance_scale',
        "type": 'float',
        "label": 'CFG引导强度',
        "default": 7.5,
        "min": 0.0,
        "max": 20.0,
        "options": [],
        "description": '无分类器引导的引导强度',
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        import torch
        import torch.nn as nn
        import torch.optim as optim
    except ImportError:
        return {"ok": False, "error_code": "MISSING_DEPENDENCY", "message": "Missing PyTorch"}

    parameters = payload.get("parameters", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    samples = payload.get("input", {}).get("samples", []) or []
    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES"}

    target_count = max(1, int(payload.get("target_count") or len(samples)))
    cfg_scale = float(parameters.get("cfg_scale", parameters.get("CFG引导阶数", 1.0)) or 1.0)
    inference_steps = int(parameters.get("inference_steps", parameters.get("扩散步数上限", 50)) or 50)
    lr = float(parameters.get("lr", parameters.get("学习率", 0.0001)) or 0.0001)

    device = torch.device("cpu")
    image_size = 32
    max_images = int(parameters.get("max_images", 32))
    max_images = max(2, min(max_images, 64))
    T = 200

    beta_start = 1e-4
    beta_end = 0.02
    betas = torch.linspace(beta_start, beta_end, T, device=device)
    alphas = 1.0 - betas
    alphas_cumprod = torch.cumprod(alphas, dim=0)

    tensors = _read_images(samples, image_size, max_images, device)
    if tensors is None or tensors.size(0) < 2:
        return _fallback(payload, context, output_dir, samples, target_count, "diffusion", parameters)

    n = tensors.size(0)
    batch_size = min(16, n)
    model = _build_model(device).to(device)
    opt = optim.Adam(model.parameters(), lr=lr)
    train_steps = max(20, min(120, n * 3))

    for step in range(train_steps):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "Cancelled"}
        idx = torch.randint(0, n, (batch_size,), device=device)
        x0 = tensors[idx]
        t = torch.randint(0, T, (batch_size,), device=device)
        noise = torch.randn_like(x0)
        a_bar = alphas_cumprod[t].view(-1, 1, 1, 1)
        x_t = torch.sqrt(a_bar) * x0 + torch.sqrt(1.0 - a_bar) * noise
        loss = torch.mean((model(x_t, t) - noise) ** 2)
        opt.zero_grad()
        loss.backward()
        opt.step()
        context.set_progress(step * 50 / train_steps, f"Diffusion train {step+1}/{train_steps}")

    inference_steps = max(1, min(inference_steps, 50, T))
    model.eval()
    labeled_samples = [s for s in samples if (s.get("labels") or s.get("labels_json") or [])]
    if not labeled_samples:
        labeled_samples = samples
    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "Cancelled"}
        with torch.no_grad():
            x = torch.randn(1, 3, image_size, image_size, device=device)
            for i in reversed(range(inference_steps)):
                t_val = int(i * (T - 1) / max(1, inference_steps - 1))
                t_tensor = torch.tensor([t_val], device=device, dtype=torch.long)
                a_t = alphas[t_val].view(1, 1, 1, 1)
                a_bar_t = alphas_cumprod[t_val].view(1, 1, 1, 1)
                beta_t = 1.0 - a_t
                pred = model(x, t_tensor) * cfg_scale
                coef = (1.0 - a_t) / torch.sqrt(1.0 - a_bar_t)
                mean = (1.0 / torch.sqrt(a_t)) * (x - coef * pred)
                x = mean + (torch.sqrt(beta_t) * torch.randn_like(x) if t_val > 0 else 0)
        img = _to_bgr(x[0])
        out = output_dir / f"diffusion_{index:04d}.jpg"
        if not write_image(out, img):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {out}"}
        outputs.append({
            "source_sample_id": labeled_samples[index % len(labeled_samples)].get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": "diffusion", "algorithm_key": payload.get("algorithm_key", "generation.image.diffusion")},
            "status": "created",
        })
        context.set_progress(50 + (index + 1) * 50 / target_count, f"Diffusion gen {index+1}/{target_count}")
    return {"ok": True, "outputs": outputs, "logs": []}


def _fallback(payload, context, output_dir, samples, target_count, method, parameters):
    steps = int(parameters.get("扩散步数上限", 50))
    outputs = []
    for index in range(target_count):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED"}
        sample = samples[index % len(samples)]
        p = Path(sample.get("sample_path") or sample.get("path") or sample.get("file_path") or "")
        img = read_image(p)
        if img is None:
            continue
        for _ in range(max(1, steps // 10)):
            noise = np.random.normal(0, 0.1, img.shape)
            img = np.clip(img + noise, 0, 255).astype(np.uint8)
        out = output_dir / f"{method}_{index:04d}.jpg"
        if not write_image(out, img):
            return {"ok": False, "error_code": "IMAGE_WRITE_ERROR", "message": f"Cannot write image: {out}"}
        outputs.append({
            "source_sample_id": sample.get("id"),
            "output_path": str(out),
            "relative_path": out.name,
            "metadata": {"method": method, "fallback": True},
            "status": "created",
        })
        context.set_progress((index + 1) * 100 / target_count, f"{method} fb {index+1}/{target_count}")
    return {"ok": True, "outputs": outputs, "logs": ["fallback mode"]}


def _read_images(samples, image_size, max_images, device):
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
        x = x * 2.0 - 1.0
        tensors.append(x)
    return torch.stack(tensors, dim=0) if len(tensors) >= 2 else None


def _to_bgr(x):
    import torch
    x = x.detach().cpu().clamp(-1.0, 1.0)
    x = (x + 1.0) / 2.0
    x = (x * 255.0).to(torch.uint8).permute(1, 2, 0).numpy()
    return cv2.cvtColor(x, cv2.COLOR_RGB2BGR)


def _build_model(device):
    import torch
    import torch.nn as nn
    import numpy as _np
    base_ch = 64
    time_dim = 128

    def _temb(t, dim):
        half = dim // 2
        esc = _np.log(10000.0) / (half - 1)
        emb = torch.exp(torch.arange(half, device=device, dtype=torch.float32) * -esc)
        emb = t.float().unsqueeze(1) * emb.unsqueeze(0)
        return torch.cat([torch.sin(emb), torch.cos(emb)], dim=1)

    class NoisePredictor(nn.Module):
        def __init__(self):
            super().__init__()
            self.c1 = nn.Conv2d(3, base_ch, 3, 1, 1)
            self.c2 = nn.Conv2d(base_ch, base_ch * 2, 4, 2, 1)
            self.c3 = nn.Conv2d(base_ch * 2, base_ch * 2, 3, 1, 1)
            self.tmlp = nn.Sequential(nn.Linear(time_dim, base_ch * 2), nn.ReLU(inplace=True), nn.Linear(base_ch * 2, base_ch * 2))
            self.up = nn.ConvTranspose2d(base_ch * 2, base_ch, 4, 2, 1)
            self.cout = nn.Conv2d(base_ch, 3, 3, 1, 1)
        def forward(self, xt, t):
            h1 = torch.relu(self.c1(xt))
            h2 = torch.relu(self.c2(h1))
            h2 = self.c3(h2)
            temb = _temb(t, time_dim)
            h2 = h2 + self.tmlp(temb).unsqueeze(-1).unsqueeze(-1)
            return self.cout(torch.relu(self.up(h2)))
    return NoisePredictor()
