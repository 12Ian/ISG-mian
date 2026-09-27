"""Evaluator for TF-IDF + LinearSVC text classifiers."""
from __future__ import annotations

import json
import os
import pickle
import traceback
from pathlib import Path

PARAMETERS = [{"name": "model_checkpoint_path", "type": "string", "label": "模型 checkpoint 路径", "default": "", "options": [], "description": "文本训练生成的 text_classifier.pkl", "required": True}]
_TEXT_EXTS = {".txt", ".md", ".log", ".csv", ".json", ".yaml", ".yml"}


def run(payload: dict, context) -> dict:
    try:
        return _evaluate(payload, context)
    except Exception as exc:
        return {"ok": False, "error_code": "EVALUATION_CRASH", "message": f"文本评估失败: {exc}\n{traceback.format_exc()}"}


def _evaluate(payload, context):
    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
    params = payload.get("parameters", {}) or {}
    checkpoint = Path(params.get("model_checkpoint_path", ""))
    if not checkpoint.is_file():
        return {"ok": False, "error_code": "MISSING_CHECKPOINT", "message": f"找不到模型 checkpoint: {checkpoint}"}
    target = payload.get("input", {}).get("target_dataset", {}) or {}
    baseline = payload.get("input", {}).get("baseline_dataset", {}) or {}
    dataset = target if target.get("samples") else baseline
    samples = []
    for sample in dataset.get("samples", []):
        labels = sample.get("labels") or []; path = sample.get("path") or sample.get("file_path") or ""
        if not labels or Path(path).suffix.casefold() not in _TEXT_EXTS: continue
        path = os.path.join(dataset.get("path", ""), path) if dataset.get("path") and not os.path.isabs(path) else path
        label = labels[0].get("class_name") if isinstance(labels[0], dict) else labels[0]
        if os.path.isfile(path) and label is not None: samples.append((path, str(label)))
    if not samples: return {"ok": False, "error_code": "NO_SAMPLES", "message": "没有可评估的有标签文本样本"}
    with checkpoint.open("rb") as handle: model = pickle.load(handle)
    texts = [Path(path).read_text(encoding="utf-8", errors="ignore") for path, _ in samples]
    actual = [label for _, label in samples]; predicted = model["classifier"].predict(model["vectorizer"].transform(texts))
    metrics = {"accuracy": round(float(accuracy_score(actual, predicted)) * 100, 2), "precision": round(float(precision_score(actual, predicted, average="weighted", zero_division=0)) * 100, 2), "recall": round(float(recall_score(actual, predicted, average="weighted", zero_division=0)) * 100, 2), "f1": round(float(f1_score(actual, predicted, average="weighted", zero_division=0)) * 100, 2), "num_samples": len(samples), "num_classes": len(set(actual))}
    output_dir = Path(payload["output"]["output_dir"]); output_dir.mkdir(parents=True, exist_ok=True); report = output_dir / "evaluation_report.json"; report.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    context.set_progress(100.0, f"文本评估完成: accuracy={metrics['accuracy']:.2f}%")
    return {"ok": True, "results": [{"model_name": "TF-IDF + LinearSVC 文本分类评估", "metrics": metrics, "summary": f"文本分类评估完成，准确率 {metrics['accuracy']:.2f}%，F1 {metrics['f1']:.2f}%", "artifacts": [{"type": "report", "path": str(report)}]}]}
