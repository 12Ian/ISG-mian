"""AudioCNN checkpoint evaluator."""
from __future__ import annotations

import json
import os
import traceback
from pathlib import Path

PARAMETERS = [
    {"name": "model_checkpoint_path", "type": "string", "label": "模型 checkpoint 路径", "default": "", "options": [], "description": "训练产出的 model.pth 文件路径", "required": True},
]

_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}


def _samples(samples, dataset_path):
    result = []
    for sample in samples:
        labels = sample.get("labels") or []
        path = sample.get("path") or sample.get("file_path") or ""
        if not labels or Path(path).suffix.casefold() not in _AUDIO_EXTS:
            continue
        path = os.path.join(dataset_path, path) if dataset_path and not os.path.isabs(path) else path
        if not os.path.isfile(path):
            continue
        label = labels[0]
        if isinstance(label, dict):
            label = label.get("class_name") or label.get("name") or label.get("label")
        if label is not None:
            result.append({"path": path, "label": str(label)})
    return result


def run(payload: dict, context) -> dict:
    try:
        return _evaluate(payload, context)
    except Exception as exc:
        return {"ok": False, "error_code": "EVALUATION_CRASH", "message": f"评估失败: {exc}\n{traceback.format_exc()}"}


def _evaluate(payload, context):
    import librosa
    import numpy as np
    import torch
    from torch import nn

    params = payload.get("parameters", {}) or {}
    checkpoint = Path(params.get("model_checkpoint_path", ""))
    if not checkpoint.is_file():
        return {"ok": False, "error_code": "MISSING_CHECKPOINT", "message": f"找不到模型 checkpoint: {checkpoint}"}
    target = payload.get("input", {}).get("target_dataset", {}) or {}
    baseline = payload.get("input", {}).get("baseline_dataset", {}) or {}
    dataset = target if target.get("samples") else baseline
    samples = _samples(dataset.get("samples", []), dataset.get("path", ""))
    if not samples:
        return {"ok": False, "error_code": "NO_SAMPLES", "message": "没有可评估的有标签音频样本"}

    saved = torch.load(checkpoint, map_location="cpu")
    metadata = saved.get("metadata", {}) if isinstance(saved, dict) else {}
    metadata = metadata or {}
    class_names = list(saved.get("class_names") or metadata.get("class_names") or [])
    feature_method = saved.get("feature_method") or metadata.get("feature_method") or "MelSpectrogram"
    sample_rate = int(saved.get("sample_rate") or metadata.get("sample_rate") or 16000)
    if not class_names:
        return {"ok": False, "error_code": "INVALID_CHECKPOINT", "message": "checkpoint 缺少 class_names"}

    def feature(path):
        audio, _ = librosa.load(path, sr=sample_rate, mono=True, duration=3.0)
        audio = np.asarray(audio, dtype=np.float32)
        target_len = sample_rate * 3
        audio = np.pad(audio[:target_len], (0, max(0, target_len - len(audio))))
        if feature_method == "MFCC":
            value = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=40)
        elif feature_method == "Spectrogram":
            value = np.abs(librosa.stft(audio, n_fft=512, hop_length=256))
        else:
            value = librosa.power_to_db(librosa.feature.melspectrogram(y=audio, sr=sample_rate, n_mels=64, n_fft=512, hop_length=256), ref=np.max)
        return value.astype(np.float32)

    values = [feature(item["path"]) for item in samples]
    shape = max(value.shape[0] for value in values), max(value.shape[1] for value in values)
    inputs = torch.tensor(np.stack([np.pad(value, ((0, shape[0] - value.shape[0]), (0, shape[1] - value.shape[1]))) for value in values])[:, None], dtype=torch.float32)
    labels = torch.tensor([class_names.index(item["label"]) for item in samples if item["label"] in class_names], dtype=torch.long)
    inputs = inputs[[item["label"] in class_names for item in samples]]

    class AudioCNN(nn.Module):
        def __init__(self, n_classes):
            super().__init__()
            self.features = nn.Sequential(nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2), nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d((1, 1)))
            self.classifier = nn.Linear(32, n_classes)
        def forward(self, value):
            return self.classifier(self.features(value).flatten(1))

    model = AudioCNN(len(class_names))
    state = saved.get("model_state_dict") if isinstance(saved, dict) else saved
    model.load_state_dict(state)
    model.eval()
    with torch.no_grad():
        logits = model(inputs)
        accuracy = float((logits.argmax(1) == labels).float().mean().item())
        loss = float(nn.CrossEntropyLoss()(logits, labels).item())
    output_dir = Path(payload["output"]["output_dir"]); output_dir.mkdir(parents=True, exist_ok=True)
    report = {"accuracy": accuracy, "loss": loss, "num_samples": len(samples), "num_classes": len(class_names), "class_names": class_names}
    report_path = output_dir / "evaluation_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    context.set_progress(100.0, f"评估完成: accuracy={accuracy:.4f}")
    return {"ok": True, "results": [{"model_name": "AudioCNN 音频分类评估", "metrics": {"accuracy": round(accuracy * 100, 2), "loss": round(loss, 4), "num_samples": len(samples), "num_classes": len(class_names)}, "summary": f"音频分类评估完成，准确率 {accuracy:.4f}，Loss {loss:.4f}", "artifacts": [{"type": "report", "path": str(report_path)}]}]}
