"""本地音频分类训练插件。

使用仓库已有的 PyTorch、librosa 和 soundfile 依赖训练轻量 1D CNN，
不依赖外部 AudioClassification-Pytorch 项目或预训练权重。
"""
from __future__ import annotations

import json
import os
import random
import traceback
from pathlib import Path

_AUDIO_EXTS = {".wav", ".mp3", ".flac", ".ogg", ".aac", ".m4a"}

PARAMETERS = [
    {"name": "model_name", "type": "select", "label": "模型", "default": "AudioCNN", "options": ["AudioCNN"], "description": "本地音频分类模型", "required": False},
    {"name": "feature_method", "type": "select", "label": "特征提取方法", "default": "MelSpectrogram", "options": ["MelSpectrogram", "MFCC", "Spectrogram"], "description": "音频频谱特征", "required": False},
    {"name": "batch_size", "type": "int", "label": "批大小", "default": 8, "min": 1, "max": 256, "description": "训练批次大小", "required": False},
    {"name": "epochs", "type": "int", "label": "训练轮次", "default": 10, "min": 1, "max": 500, "description": "训练 epoch 数量", "required": False},
    {"name": "learning_rate", "type": "float", "label": "学习率", "default": 0.001, "min": 1e-6, "max": 0.1, "description": "Adam 优化器学习率", "required": False},
    {"name": "max_duration", "type": "float", "label": "音频最大时长(秒)", "default": 3.0, "min": 0.5, "max": 30.0, "description": "统一裁剪或补零的音频时长", "required": False},
    {"name": "train_ratio", "type": "float", "label": "训练集比例", "default": 0.75, "min": 0.3, "max": 0.9, "description": "训练集占比，剩余为测试集", "required": False},
]


def _build_samples_map(samples: list[dict], dataset_path: str | None = None) -> list[dict]:
    result = []
    for sample in samples:
        labels = sample.get("labels") or []
        path = sample.get("path") or sample.get("file_path") or ""
        if not labels or not path or Path(path).suffix.casefold() not in _AUDIO_EXTS:
            continue
        path = os.path.join(dataset_path, path) if dataset_path and not os.path.isabs(path) else path
        if not os.path.isfile(path):
            continue
        label = labels[0]
        if isinstance(label, dict):
            label = label.get("class_name") or label.get("name") or label.get("label")
        if label is not None and str(label).strip():
            result.append({"label": str(label), "path": path})
    return result


def _load_feature(path: str, feature_method: str, sample_rate: int, target_len: int):
    import librosa
    import numpy as np

    audio, _ = librosa.load(path, sr=sample_rate, mono=True, duration=target_len / sample_rate)
    audio = np.asarray(audio, dtype=np.float32)
    if len(audio) < target_len:
        audio = np.pad(audio, (0, target_len - len(audio)))
    else:
        audio = audio[:target_len]
    if feature_method == "MFCC":
        feature = librosa.feature.mfcc(y=audio, sr=sample_rate, n_mfcc=40)
    elif feature_method == "Spectrogram":
        feature = np.abs(librosa.stft(audio, n_fft=512, hop_length=256))
    else:
        feature = librosa.feature.melspectrogram(y=audio, sr=sample_rate, n_mels=64, n_fft=512, hop_length=256)
        feature = librosa.power_to_db(feature, ref=np.max)
    return feature.astype(np.float32)


def run(payload: dict, context) -> dict:
    try:
        return _run_training(payload, context)
    except Exception as exc:
        return {"ok": False, "error_code": "TRAINING_CRASH", "message": f"训练失败: {exc}\n{traceback.format_exc()}"}


def _run_training(payload: dict, context) -> dict:
    import numpy as np
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    params = payload.get("parameters", {}) or {}
    inp = payload.get("input", {}) or {}
    out_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    out_dir.mkdir(parents=True, exist_ok=True)
    samples = _build_samples_map(inp.get("samples", []), inp.get("dataset_path", ""))
    if len(samples) < 10:
        return {"ok": False, "error_code": "INSUFFICIENT_DATA", "message": f"训练至少需要10个样本，当前仅{len(samples)}个"}

    classes = sorted({item["label"] for item in samples})
    if len(classes) < 2:
        return {"ok": False, "error_code": "INSUFFICIENT_DATA", "message": "音频分类至少需要2个类别"}
    label_to_id = {name: index for index, name in enumerate(classes)}
    train_ratio = float(params.get("train_ratio", 0.75))
    rng = random.Random(42)
    class_samples = {name: [item for item in samples if item["label"] == name] for name in classes}
    if any(len(items) < 2 for items in class_samples.values()):
        return {"ok": False, "error_code": "INSUFFICIENT_DATA", "message": "音频分类每个类别至少需要2个样本"}
    train_items, test_items = [], []
    for items in class_samples.values():
        rng.shuffle(items)
        split = max(1, min(len(items) - 1, int(len(items) * train_ratio)))
        train_items.extend(items[:split])
        test_items.extend(items[split:])
    feature_method = params.get("feature_method", "MelSpectrogram")
    sample_rate, target_len = 16000, int(float(params.get("max_duration", 3.0)) * 16000)

    def tensors(items):
        values = [_load_feature(item["path"], feature_method, sample_rate, target_len) for item in items]
        shape = max(value.shape[0] for value in values), max(value.shape[1] for value in values)
        padded = [np.pad(value, ((0, shape[0] - value.shape[0]), (0, shape[1] - value.shape[1]))) for value in values]
        return torch.tensor(np.stack(padded)[:, None], dtype=torch.float32), torch.tensor([label_to_id[item["label"]] for item in items])

    x_train, y_train = tensors(train_items)
    x_test, y_test = tensors(test_items)
    class AudioCNN(nn.Module):
        def __init__(self, n_classes):
            super().__init__()
            self.features = nn.Sequential(nn.Conv2d(1, 16, 3, padding=1), nn.ReLU(), nn.MaxPool2d(2), nn.Conv2d(16, 32, 3, padding=1), nn.ReLU(), nn.AdaptiveAvgPool2d((1, 1)))
            self.classifier = nn.Linear(32, n_classes)
        def forward(self, value):
            return self.classifier(self.features(value).flatten(1))

    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = AudioCNN(len(classes)).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=float(params.get("learning_rate", 0.001)))
    criterion = nn.CrossEntropyLoss()
    loader = DataLoader(TensorDataset(x_train, y_train), batch_size=int(params.get("batch_size", 8)), shuffle=True)
    best_accuracy, best_state = -1.0, None
    epochs = int(params.get("epochs", 10))
    for epoch in range(epochs):
        if context.is_cancel_requested():
            return {"ok": False, "error_code": "CANCELLED", "message": "训练已取消"}
        model.train()
        for features, labels in loader:
            optimizer.zero_grad()
            loss = criterion(model(features.to(device)), labels.to(device))
            loss.backward(); optimizer.step()
        model.eval()
        with torch.no_grad():
            predictions = model(x_test.to(device)).argmax(1).cpu()
        accuracy = float((predictions == y_test).float().mean().item())
        if accuracy >= best_accuracy:
            best_accuracy, best_state = accuracy, {key: value.detach().cpu().clone() for key, value in model.state_dict().items()}
        context.set_progress(5 + 90 * (epoch + 1) / epochs, f"Epoch {epoch + 1}/{epochs}, test_acc={accuracy:.4f}")

    checkpoint = out_dir / "model_checkpoints" / "best_model" / "model.pth"
    checkpoint.parent.mkdir(parents=True, exist_ok=True)
    torch.save({"model_state_dict": best_state, "model_name": "AudioCNN", "feature_method": feature_method, "sample_rate": sample_rate, "class_names": classes}, checkpoint)
    metadata = {"model_name": "AudioCNN", "feature_method": feature_method, "num_classes": len(classes), "class_names": classes, "best_accuracy": best_accuracy, "device": device}
    (checkpoint.parent.parent / "model_meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    context.set_progress(100.0, f"训练完成: best_accuracy={best_accuracy:.4f}")
    return {"ok": True, "outputs": [{"artifact_path": str(checkpoint), "artifact_type": "model_checkpoint", "metadata": metadata, "summary": f"音频分类模型训练完成，{len(classes)}类，{len(samples)}样本，最佳准确率: {best_accuracy:.4f}"}]}
