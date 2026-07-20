"""YOLOv8 目标检测训练插件。"""
from __future__ import annotations

import json
import os
import shutil
import sys
import traceback
from pathlib import Path

import yaml

from core.data_management.detection_annotations import sanitize_normalized_bbox
from core.hardware_adapter import resolve_yolo_device
from plugins.training.yolov5_detector import (
    _build_conversion_report,
    _collect_class_names,
    _label_class_name,
    _parse_labels,
    _split_train_val_test,
    _write_yolo_split,
)


# 桌面本地训练默认不连接第三方实验平台，避免缺少 API Key 导致训练中断。
os.environ.setdefault("COMET_DISABLE_AUTO_LOGGING", "1")
os.environ.setdefault("WANDB_DISABLED", "true")
os.environ.setdefault("WANDB_MODE", "disabled")


PARAMETERS = [
    {
        "name": "model",
        "type": "select",
        "label": "模型规格",
        "default": "yolov8n.pt",
        "options": ["yolov8n.pt", "yolov8s.pt", "yolov8m.pt", "yolov8l.pt", "yolov8x.pt"],
        "description": "本地不存在时由 Ultralytics 下载预训练权重",
        "required": False,
    },
    {
        "name": "epochs",
        "type": "int",
        "label": "训练轮次",
        "default": 100,
        "min": 1,
        "max": 1000,
        "options": [],
        "description": "训练 epoch 数量",
        "required": False,
    },
    {
        "name": "batch_size",
        "type": "int",
        "label": "批大小",
        "default": 16,
        "min": 1,
        "max": 256,
        "options": [],
        "description": "批次大小",
        "required": False,
    },
    {
        "name": "img_size",
        "type": "int",
        "label": "图像尺寸",
        "default": 640,
        "min": 320,
        "max": 1280,
        "options": [],
        "description": "训练输入图像尺寸",
        "required": False,
    },
    {
        "name": "train_ratio",
        "type": "float",
        "label": "训练集比例",
        "default": 0.7,
        "min": 0.1,
        "max": 0.9,
        "options": [],
        "description": "训练集占比",
        "required": False,
    },
    {
        "name": "val_ratio",
        "type": "float",
        "label": "验证集比例",
        "default": 0.15,
        "min": 0.05,
        "max": 0.5,
        "options": [],
        "description": "验证集占比，剩余样本进入测试集",
        "required": False,
    },
    {
        "name": "device",
        "type": "string",
        "label": "训练设备",
        "default": "",
        "options": ["", "0", "1", "0,1", "cpu"],
        "description": "支持自动、单显卡、双显卡和 CPU",
        "required": False,
    },
]


DATASET_REQUIREMENTS = {
    "modalities": ["image"],
    "label_types": ["detection"],
    "min_samples": 2,
    "min_classes": 1,
    "min_samples_per_class": 1,
    "bbox_required": True,
    "allow_unlabeled": False,
}


def run(payload: dict, context) -> dict:
    try:
        return _run_training(payload, context)
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "TRAINING_CRASH",
            "message": f"YOLOv8 训练崩溃: {exc}\n{traceback.format_exc()}",
        }


def _run_training(payload: dict, context) -> dict:
    params = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    out_dir = Path(payload["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    if not samples:
        return {"ok": False, "error_code": "NO_SAMPLES", "message": "数据集无样本"}

    epochs = int(params.get("epochs", 100))
    batch_size = int(params.get("batch_size", 16))
    img_size = int(params.get("img_size", 640))
    train_ratio = float(params.get("train_ratio", 0.7))
    val_ratio = float(params.get("val_ratio", 0.15))
    requested_device = str(params.get("device", "") or "")

    valid_samples = []
    for sample in samples:
        labels = _parse_labels(sample.get("labels", []))
        bboxes = []
        for label in labels:
            bbox = label.get("bbox", [])
            if len(bbox) < 4:
                continue
            normalized_bbox = sanitize_normalized_bbox(bbox)
            if normalized_bbox is None:
                return {
                    "ok": False,
                    "error_code": "INVALID_BBOX",
                    "message": f"样本 {sample.get('name', '')} 包含无效或未归一化的 bbox: {bbox}",
                }
            bboxes.append({
                **label,
                "class_name": _label_class_name(label),
                "bbox": normalized_bbox,
                "bbox_format": "cxcywh_normalized",
            })
        metadata = sample.get("metadata", {}) or {}
        is_detection_sample = any(label.get("type") == "detection" for label in labels) or bool(
            metadata.get("annotation_format")
        )
        if bboxes or is_detection_sample:
            valid_samples.append({**sample, "_bboxes": bboxes})

    if not valid_samples:
        return {
            "ok": False,
            "error_code": "NO_BBOX",
            "message": f"数据集 {len(samples)} 个样本中未找到 bbox 标注，YOLOv8 需要目标检测标注",
        }

    class_names = _collect_class_names(valid_samples)
    if not class_names:
        return {"ok": False, "error_code": "NO_CLASS", "message": "检测标注中没有有效类别名称"}
    class_to_id = {class_name: index for index, class_name in enumerate(class_names)}

    train_samples, val_samples, test_samples = _split_train_val_test(
        valid_samples, train_ratio, val_ratio
    )
    if not train_samples or not val_samples:
        return {
            "ok": False,
            "error_code": "INVALID_SPLIT",
            "message": f"训练集或验证集为空: train={len(train_samples)} val={len(val_samples)}",
        }

    context.set_progress(
        2.0,
        f"有效样本 {len(valid_samples)}，类别 {len(class_names)}，"
        f"train={len(train_samples)} val={len(val_samples)} test={len(test_samples)}",
    )

    yolo_dir = out_dir / "yolo_data"
    if yolo_dir.is_dir():
        shutil.rmtree(yolo_dir)
    _write_yolo_split(
        train_samples, yolo_dir / "train" / "images", yolo_dir / "train" / "labels", class_to_id
    )
    _write_yolo_split(
        val_samples, yolo_dir / "val" / "images", yolo_dir / "val" / "labels", class_to_id
    )
    if test_samples:
        _write_yolo_split(
            test_samples, yolo_dir / "test" / "images", yolo_dir / "test" / "labels", class_to_id
        )

    data_yaml = out_dir / "data.yaml"
    yaml_data = {
        "path": yolo_dir.resolve().as_posix(),
        "train": "train/images",
        "val": "val/images",
        "nc": len(class_names),
        "names": class_names,
    }
    if test_samples:
        yaml_data["test"] = "test/images"
    data_yaml.write_text(
        yaml.safe_dump(yaml_data, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )

    test_paths_file = out_dir / "test_split.json"
    test_paths_file.write_text(
        json.dumps(
            [sample.get("file_path", sample.get("path", "")) for sample in test_samples],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    conversion_report_path = out_dir / "conversion_report.json"
    conversion_report_path.write_text(
        json.dumps(
            _build_conversion_report(
                valid_samples,
                class_to_id,
                train_samples,
                val_samples,
                test_samples,
                train_ratio,
                val_ratio,
            ),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # Ultralytics 默认会自动启用已安装的在线实验平台，桌面本地训练全部关闭。
    try:
        from ultralytics import YOLO, settings
    except ImportError:
        return {
            "ok": False,
            "error_code": "DEPENDENCY_MISSING",
            "message": "YOLOv8 插件需要 ultralytics。请在软件运行环境中安装 ultralytics 后重试。",
        }

    disabled_integrations = {
        name: False
        for name in ("comet", "wandb", "clearml", "mlflow", "neptune", "tensorboard", "raytune", "dvc")
        if name in settings
    }
    if disabled_integrations:
        settings.update(disabled_integrations)

    import torch

    device, device_warning = resolve_yolo_device(requested_device, torch)
    model_name = str(params.get("model", "yolov8n.pt") or "yolov8n.pt")
    requested_model = Path(model_name).expanduser()
    if requested_model.is_absolute() and not requested_model.is_file():
        return {
            "ok": False,
            "error_code": "MODEL_NOT_FOUND",
            "message": f"YOLOv8 模型文件不存在: {requested_model}",
        }
    model_path = _resolve_model_path(model_name)
    context.set_progress(
        4.0,
        f"{device_warning} YOLOv8 训练启动: model={Path(model_path).name} "
        f"epochs={epochs} batch={batch_size} imgsz={img_size} device={device}".strip(),
    )

    try:
        model = YOLO(model_path, task="detect")
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "MODEL_LOAD_FAILED",
            "message": f"YOLOv8 模型加载失败: {Path(model_path).name}；{exc}",
        }

    def _check_cancel(trainer):
        if context.is_cancel_requested():
            trainer.stop = True

    def _report_progress(trainer):
        current_epoch = int(getattr(trainer, "epoch", 0)) + 1
        progress = min(5.0 + current_epoch / max(epochs, 1) * 93.0, 98.0)
        context.set_progress(progress, f"Epoch {current_epoch}/{epochs}")

    model.add_callback("on_train_batch_end", _check_cancel)
    model.add_callback("on_train_epoch_end", _report_progress)
    try:
        model.train(
            data=str(data_yaml.resolve()),
            epochs=epochs,
            batch=batch_size,
            imgsz=img_size,
            device=device,
            project=str(out_dir / "runs"),
            name="train",
            exist_ok=True,
            workers=0,
        )
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "TRAINING_FAILED",
            "message": f"YOLOv8 训练失败: {exc}",
        }

    if context.is_cancel_requested():
        return {"ok": False, "error_code": "CANCELLED", "message": "训练已被用户取消"}

    save_dir = Path(model.trainer.save_dir)
    best_pt = Path(model.trainer.best) if getattr(model.trainer, "best", None) else save_dir / "weights" / "best.pt"
    if not best_pt.is_file():
        candidates = list(save_dir.rglob("best.pt"))
        if candidates:
            best_pt = candidates[0]
    if not best_pt.is_file():
        return {
            "ok": False,
            "error_code": "CHECKPOINT_NOT_FOUND",
            "message": f"未找到 YOLOv8 best.pt: {save_dir}",
        }

    context.set_progress(100.0, "训练完成")
    return {
        "ok": True,
        "outputs": [{
            "artifact_path": str(best_pt),
            "metadata": {
                "backbone": "yolov8",
                "model": Path(model_path).name,
                "epochs": epochs,
                "img_size": img_size,
                "class_names": class_names,
                "class_to_id": class_to_id,
                "device": device,
                "device_warning": device_warning,
                "train_count": len(train_samples),
                "val_count": len(val_samples),
                "test_count": len(test_samples),
                "data_yaml": data_yaml.resolve().as_posix(),
                "conversion_report": conversion_report_path.resolve().as_posix(),
            },
        }],
        "logs": ([device_warning] if device_warning else []) + [f"YOLOv8 complete: {best_pt}"],
    }


def _resolve_model_path(model_name: str) -> str:
    requested = Path(model_name).expanduser()
    if requested.is_absolute():
        return str(requested)

    project_root = Path(__file__).resolve().parents[2]
    candidates = [project_root / requested, Path.cwd() / requested]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / requested)
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return model_name
