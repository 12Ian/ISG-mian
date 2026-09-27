"""Lightweight text classification training with TF-IDF and LinearSVC."""
from __future__ import annotations

import json
import os
import pickle
import random
import traceback
from pathlib import Path

PARAMETERS = [
    {"name": "analyzer", "type": "select", "label": "文本特征粒度", "default": "char", "options": ["char", "char_wb", "word"], "description": "中文文本推荐 char", "required": False},
    {"name": "ngram_max", "type": "int", "label": "最大 n-gram", "default": 5, "min": 1, "max": 8, "description": "TF-IDF 特征的最大 n-gram 长度", "required": False},
    {"name": "train_ratio", "type": "float", "label": "训练集比例", "default": 0.8, "min": 0.5, "max": 0.9, "description": "训练集占比", "required": False},
    {"name": "c", "type": "float", "label": "分类器强度", "default": 1.0, "min": 0.01, "max": 100.0, "description": "LinearSVC 的 C 参数", "required": False},
]

_TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".json", ".yaml", ".yml"}


def _samples(samples: list[dict], dataset_path: str | None) -> list[dict]:
    result = []
    for sample in samples:
        labels = sample.get("labels") or []
        path = sample.get("path") or sample.get("file_path") or ""
        if not labels or Path(path).suffix.casefold() not in _TEXT_EXTS:
            continue
        path = os.path.join(dataset_path, path) if dataset_path and not os.path.isabs(path) else path
        if not os.path.isfile(path):
            continue
        label = labels[0]
        if isinstance(label, dict):
            label = label.get("class_name") or label.get("name") or label.get("label")
        if label is not None and str(label).strip():
            result.append({"path": path, "label": str(label)})
    return result


def run(payload: dict, context) -> dict:
    try:
        return _train(payload, context)
    except Exception as exc:
        return {"ok": False, "error_code": "TRAINING_CRASH", "message": f"文本训练失败: {exc}\n{traceback.format_exc()}"}


def _train(payload, context):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics import accuracy_score, f1_score
    from sklearn.model_selection import train_test_split
    from sklearn.svm import LinearSVC

    params = payload.get("parameters", {}) or {}
    inp = payload.get("input", {}) or {}
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)
    items = _samples(inp.get("samples", []), inp.get("dataset_path", ""))
    if len(items) < 10:
        return {"ok": False, "error_code": "INSUFFICIENT_DATA", "message": f"文本训练至少需要10个有标签样本，当前{len(items)}个"}
    classes = sorted({item["label"] for item in items})
    counts = {label: sum(item["label"] == label for item in items) for label in classes}
    if len(classes) < 2 or min(counts.values()) < 2:
        return {"ok": False, "error_code": "INSUFFICIENT_DATA", "message": "文本分类至少需要2个类别，且每类至少2个样本"}
    texts = [Path(item["path"]).read_text(encoding="utf-8", errors="ignore") for item in items]
    labels = [item["label"] for item in items]
    indices = list(range(len(items))); random.Random(42).shuffle(indices)
    train_idx, test_idx = [], []
    ratio = float(params.get("train_ratio", 0.8))
    for label in classes:
        group = [i for i in indices if labels[i] == label]
        cut = max(1, min(len(group) - 1, int(len(group) * ratio)))
        train_idx.extend(group[:cut]); test_idx.extend(group[cut:])
    vectorizer = TfidfVectorizer(analyzer=params.get("analyzer", "char"), ngram_range=(1, int(params.get("ngram_max", 5))), min_df=1, sublinear_tf=True)
    x_train = vectorizer.fit_transform([texts[i] for i in train_idx]); x_test = vectorizer.transform([texts[i] for i in test_idx])
    classifier = LinearSVC(C=float(params.get("c", 1.0)))
    classifier.fit(x_train, [labels[i] for i in train_idx])
    predictions = classifier.predict(x_test)
    accuracy = float(accuracy_score([labels[i] for i in test_idx], predictions))
    f1 = float(f1_score([labels[i] for i in test_idx], predictions, average="weighted", zero_division=0))
    checkpoint = output_dir / "model_checkpoints" / "text_classifier.pkl"; checkpoint.parent.mkdir(parents=True, exist_ok=True)
    with checkpoint.open("wb") as handle:
        pickle.dump({"vectorizer": vectorizer, "classifier": classifier, "class_names": classes, "model_name": "TF-IDF + LinearSVC"}, handle)
    metadata = {"model_name": "TF-IDF + LinearSVC", "class_names": classes, "num_classes": len(classes), "num_samples": len(items), "accuracy": accuracy, "f1": f1}
    (checkpoint.parent / "model_meta.json").write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    context.set_progress(100.0, f"文本训练完成: accuracy={accuracy:.4f}")
    return {"ok": True, "outputs": [{"artifact_path": str(checkpoint), "artifact_type": "model_checkpoint", "metadata": metadata, "summary": f"文本分类训练完成，{len(classes)}类，{len(items)}样本，准确率: {accuracy:.4f}"}]}
