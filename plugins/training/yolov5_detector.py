"""
YOLOv5 目标检测训练插件。

从数据集样本的 labels_json 中提取 bbox 标注，生成 YOLO 格式数据，
调用内嵌 YOLOv5 引擎进行训练。
"""
from __future__ import annotations
from pathlib import Path
import os, sys, shutil, json, re, yaml

import utils as _shared_utils  # 预加载合并后的项目/YOLOv5 utils，避免同名模块抢占。
from core.data_management.detection_annotations import sanitize_normalized_bbox
from core.hardware_adapter import resolve_yolo_device
from PIL import Image


_YOLOV5_ROOT = Path(__file__).resolve().parent.parent / "detection" / "yolov5_core"
os.environ.setdefault("CUBLAS_WORKSPACE_CONFIG", ":4096:8")
os.environ.setdefault("NO_ALBUMENTATIONS_UPDATE", "1")
os.environ.setdefault("YOLO_OFFLINE", "true")

PARAMETERS = [
    {
        "name": "weights",
        "type": "string",
        "label": "预训练权重",
        "default": "yolov5n.pt",
        "min": None,
        "max": None,
        "options": ["yolov5n.pt"],
        "description": "固定使用内置 yolov5n.pt",
        "required": False,
    },
    {
        "name": "model_yaml",
        "type": "string",
        "label": "模型配置",
        "default": "models/yolov5n.yaml",
        "min": None,
        "max": None,
        "options": ["models/yolov5n.yaml"],
        "description": "固定使用 yolov5n 模型配置",
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
        "description": "训练输入图像尺寸 (像素)",
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
        "description": "数据集划分中训练集占比",
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
        "description": "数据集划分中验证集占比 (测试集=1-train_ratio-val_ratio)",
        "required": False,
    },
    {
        "name": "device",
        "type": "string",
        "label": "训练设备",
        "default": "",
        "min": None,
        "max": None,
        "options": ["", "0", "1", "0,1", "cpu"],
        "description": "训练设备：支持自动、单显卡、双显卡和 CPU",
        "required": False,
    },
]


def _normalize_bbox_for_sample(bbox, label: dict, sample: dict):
    """兼容像素级 cxcywh 标注；归一化标注仍按原规则校验。"""
    try:
        numeric = [float(value) for value in list(bbox[:4])]
    except (TypeError, ValueError):
        return None
    if all(0.0 <= value <= 1.0 for value in numeric):
        return sanitize_normalized_bbox(numeric, tolerance=0.01)

    image_path = sample.get("file_path") or sample.get("path")
    if not image_path:
        return None
    try:
        with Image.open(image_path) as image:
            image_width, image_height = image.size
    except (OSError, ValueError):
        return None
    if image_width <= 0 or image_height <= 0:
        return None

    bbox_format = str(label.get("bbox_format") or "cxcywh").strip().lower()
    if bbox_format in {"xyxy", "pixel_xyxy", "absolute_xyxy"}:
        xmin, ymin, xmax, ymax = numeric
        converted = [
            (xmin + xmax) / 2.0 / image_width,
            (ymin + ymax) / 2.0 / image_height,
            (xmax - xmin) / image_width,
            (ymax - ymin) / image_height,
        ]
    else:
        converted = [
            numeric[0] / image_width,
            numeric[1] / image_height,
            numeric[2] / image_width,
            numeric[3] / image_height,
        ]
    return sanitize_normalized_bbox(converted, tolerance=0.01)


def run(payload: dict, context) -> dict:
    try:
        return _run_training(payload, context)
    except Exception as exc:
        import traceback
        return {
            "ok": False,
            "error_code": "TRAINING_CRASH",
            "message": f"Training crashed: {exc}\n{traceback.format_exc()}",
        }


def _run_training(payload: dict, context) -> dict:
    # PyInstaller 无控制台模式下标准输出流为 None，tqdm 写入进度时会直接崩溃。
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w", encoding="utf-8")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w", encoding="utf-8")

    params = payload.get("parameters", {}) or {}
    inp = payload.get("input", {})
    out_dir = Path(payload["output"]["output_dir"])
    out_dir.mkdir(parents=True, exist_ok=True)

    epochs = int(params.get("epochs", 100))
    batch_size = int(params.get("batch_size", 16))
    img_size = int(params.get("img_size", 640))
    device = str(params.get("device", "") or "")
    # 当前应用统一固定使用 yolov5n，避免权重和模型结构不匹配。
    weights = "yolov5n.pt"
    model_cfg = "models/yolov5n.yaml"
    train_ratio = float(params.get("train_ratio", 0.7))
    val_ratio = float(params.get("val_ratio", 0.15))

    samples = inp.get("samples", [])
    if not samples:
        return {"ok": False, "error_code": "NO_SAMPLES", "message": "数据集无样本"}

    # 检测数据允许显式的无目标负样本，但普通无标签图片不能混入训练。
    valid_samples = []
    for s in samples:
        labels = _parse_labels(s.get("labels", []))
        bboxes = []
        for label in labels:
            bbox = label.get("bbox", [])
            if len(bbox) < 4:
                continue
            normalized_bbox = _normalize_bbox_for_sample(bbox, label, s)
            if normalized_bbox is None:
                return {
                    "ok": False,
                    "error_code": "INVALID_BBOX",
                    "message": f"样本 {s.get('name', '')} 包含无效或未归一化的 bbox: {bbox}",
                }
            bboxes.append({
                **label,
                "class_name": _label_class_name(label),
                "bbox": normalized_bbox,
                "bbox_format": "cxcywh_normalized",
            })
        metadata = s.get("metadata", {}) or {}
        is_detection_sample = any(label.get("type") == "detection" for label in labels) or bool(
            metadata.get("annotation_format")
        )
        if bboxes or is_detection_sample:
            valid_samples.append({**s, "_bboxes": bboxes})
    if not valid_samples:
        return {"ok": False, "error_code": "NO_BBOX",
                "message": f"数据集 {len(samples)} 个样本中未找到 bbox 标注，YOLOv5 需要目标检测标注"}

    context.set_progress(1.0, f"有效样本: {len(valid_samples)}/{len(samples)}")

    class_names = _collect_class_names(valid_samples)
    if not class_names:
        return {"ok": False, "error_code": "NO_CLASS", "message": "检测标注中没有有效类别名称"}
    class_to_id = {class_name: index for index, class_name in enumerate(class_names)}

    # 优先保留来源数据划分；否则执行确定性的多标签分层划分。
    train_samples, val_samples, test_samples = _split_train_val_test(valid_samples, train_ratio, val_ratio)
    context.set_progress(2.0, f"train={len(train_samples)} val={len(val_samples)} test={len(test_samples)}")

    # 保存测试集文件路径，供评估插件读取
    test_paths_file = out_dir / "test_split.json"
    test_paths_file.write_text(json.dumps([s.get("file_path", s.get("path", "")) for s in test_samples]),
                               encoding="utf-8")

    context.set_progress(3.0, f"类别: {class_names}")

    # 生成 YOLO 数据目录
    yolo_dir = out_dir / "yolo_data"
    if yolo_dir.is_dir():
        shutil.rmtree(yolo_dir)
    yolo_dir.mkdir(parents=True, exist_ok=True)
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

    # 生成 data.yaml
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
    with open(data_yaml, "w", encoding="utf-8") as f:
        yaml.safe_dump(yaml_data, f, allow_unicode=True, sort_keys=False)

    conversion_report = _build_conversion_report(
        valid_samples,
        class_to_id,
        train_samples,
        val_samples,
        test_samples,
        train_ratio,
        val_ratio,
    )
    conversion_report_path = out_dir / "conversion_report.json"
    conversion_report_path.write_text(
        json.dumps(conversion_report, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 权重和模型配置路径
    weights_arg = _resolve_weights_path(weights)
    if weights and not Path(weights_arg).is_file():
        return {
            "ok": False,
            "error_code": "OFFLINE_WEIGHT_MISSING",
            "message": f"离线权重不存在: {weights}。请选择内置 yolov5n.pt 或从头训练。",
        }
    incompatible_message = _yolov5_weights_incompatibility(weights_arg)
    if incompatible_message:
        return {
            "ok": False,
            "error_code": "INCOMPATIBLE_MODEL",
            "message": incompatible_message,
        }
    model_cfg_path = _YOLOV5_ROOT / model_cfg
    # 预训练 checkpoint 自带网络结构；model_yaml 只用于空权重的从头训练。
    model_cfg_arg = "" if weights else (str(model_cfg_path) if model_cfg_path.is_file() else "")

    # 导入 YOLOv5
    if str(_YOLOV5_ROOT) not in sys.path:
        sys.path.insert(0, str(_YOLOV5_ROOT))
    import torch
    import train as yolo_train
    from utils.callbacks import Callbacks

    callbacks = Callbacks()

    def _check_cancel(*args, **kwargs):
        if context.is_cancel_requested():
            callbacks.stop_training = True
    callbacks.register_action("on_train_batch_end", callback=_check_cancel)

    class _EpochTracker:
        def __init__(self): self.current = 0
    tracker = _EpochTracker()

    def _report_progress(*args):
        # YOLOv5 回调传入的 epoch 从 0 开始，界面和百分比使用已完成轮数。
        tracker.current = int(args[1]) + 1 if len(args) > 1 else tracker.current + 1
        pct = min(5.0 + tracker.current / epochs * 93.0, 98.0)
        context.set_progress(pct, f"Epoch {tracker.current}/{epochs}")
    callbacks.register_action("on_fit_epoch_end", callback=_report_progress)

    device_str, device_warning = resolve_yolo_device(device, torch)
    context.set_progress(
        4.0,
        f"{device_warning} YOLOv5 训练启动: epochs={epochs} batch={batch_size} "
        f"imgsz={img_size} device={device_str}".strip(),
    )

    try:
        opt = yolo_train.run(
            data=str(data_yaml),
            weights=weights_arg,
            cfg=model_cfg_arg,
            epochs=epochs,
            batch_size=batch_size,
            imgsz=img_size,
            device=device_str,
            project=str(out_dir / "runs"),
            name="train",
            exist_ok=True,
            nosave=False,
            noval=True,
            workers=0,
            cache=False,
            callbacks=callbacks,
        )
    except Exception as exc:
        import traceback
        if isinstance(exc, KeyError) and exc.args == ("anchors",):
            return {
                "ok": False,
                "error_code": "INCOMPATIBLE_MODEL",
                "message": (
                    f"{Path(weights_arg).name} 不包含传统 YOLOv5 所需的 anchors 配置，"
                    "不能由当前训练引擎加载。请改用 yolov5n.pt、yolov5s.pt 等传统 "
                    "YOLOv5 权重；YOLOv5u 权重需要独立的 Ultralytics 训练插件。"
                ),
            }
        return {"ok": False, "error_code": "TRAINING_FAILED",
                "message": f"YOLOv5 训练失败: {exc}\n{traceback.format_exc()}"}

    if context.is_cancel_requested():
        return {"ok": False, "error_code": "CANCELLED", "message": "训练已被用户取消"}

    # 查找 best.pt
    save_dir = Path(opt.save_dir) if hasattr(opt, "save_dir") else (out_dir / "runs" / "train")
    best_pt = save_dir / "weights" / "best.pt"
    if not best_pt.is_file():
        candidates = list(save_dir.rglob("best.pt"))
        if candidates:
            best_pt = candidates[0]
    if not best_pt.is_file():
        return {"ok": False, "error_code": "CHECKPOINT_NOT_FOUND",
                "message": f"未找到 best.pt: {save_dir}"}

    context.set_progress(100.0, "训练完成")
    return {
        "ok": True,
        "outputs": [{
            "artifact_path": str(best_pt),
            "metadata": {
                "backbone": "yolov5",
                "epochs": epochs,
                "img_size": img_size,
                "class_names": class_names,
                "class_to_id": class_to_id,
                "device": device_str,
                "device_warning": device_warning,
                "train_count": len(train_samples),
                "val_count": len(val_samples),
                "test_count": len(test_samples),
                "data_yaml": data_yaml.resolve().as_posix(),
                "conversion_report": conversion_report_path.resolve().as_posix(),
            },
        }],
        "logs": ([device_warning] if device_warning else []) + [f"YOLOv5 complete: {best_pt}"],
    }


def _parse_labels(raw_labels):
    if isinstance(raw_labels, str):
        try:
            raw_labels = json.loads(raw_labels)
        except (json.JSONDecodeError, TypeError):
            return []
    if not isinstance(raw_labels, list):
        return []
    return [l for l in raw_labels if isinstance(l, dict)]


def _resolve_weights_path(weights: str) -> str:
    """优先使用应用内置权重，避免安装目录中的残缺同名下载文件。"""
    requested = Path(weights).expanduser()
    if requested.is_absolute():
        return str(requested)

    candidates = [
        _YOLOV5_ROOT / requested,
        _YOLOV5_ROOT.parents[2] / requested,
    ]
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / requested)
    candidates.append(Path.cwd() / requested)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate.resolve())
    return weights


def _yolov5_weights_incompatibility(weights: str) -> str:
    """在启动训练前拦截官方 anchor-free YOLOv5u 权重。"""
    filename = Path(str(weights or "")).name
    if re.fullmatch(
        r"yolov5(?:n|s|m|l|x)(?:6)?u(?:_\d+)?\.pt",
        filename.casefold(),
    ):
        return (
            f"{filename} 是 anchor-free YOLOv5u 模型，不能由当前传统 YOLOv5训练引擎加载。"
            "请改用 yolov5n.pt、yolov5s.pt 等传统 YOLOv5 权重，"
            "或使用独立的 Ultralytics 训练插件。"
        )
    return ""


def _split_train_val_test(samples, train_ratio, val_ratio):
    """按每个类别的目标框数量联合分层，来源目录划分不覆盖训练比例参数。"""
    return _greedy_multilabel_split(samples, train_ratio, val_ratio)


def _greedy_multilabel_split(samples, train_ratio, val_ratio):
    if not samples:
        return [], [], []

    split_names = ("train", "val", "test")
    target_sizes = dict(zip(split_names, _target_split_sizes(len(samples), train_ratio, val_ratio)))
    ratios = _normalized_split_ratios(train_ratio, val_ratio)
    class_counts = {}
    sample_class_counts = {}
    for sample in samples:
        counts = _sample_class_box_counts(sample)
        sample_class_counts[id(sample)] = counts
        for class_name, count in counts.items():
            class_counts[class_name] = class_counts.get(class_name, 0) + count

    target_class_counts = {
        class_name: dict(zip(split_names, _allocate_integer_targets(total, ratios)))
        for class_name, total in class_counts.items()
    }

    ordered = sorted(
        samples,
        key=lambda sample: (
            min(
                (class_counts[name] for name in sample_class_counts[id(sample)]),
                default=sum(class_counts.values()) + 1,
            ),
            -sum(sample_class_counts[id(sample)].values()),
            -len(sample_class_counts[id(sample)]),
            _sample_key(sample),
        ),
    )
    assigned = {name: [] for name in split_names}
    assigned_class_counts = {name: {} for name in split_names}

    for sample in ordered:
        counts = sample_class_counts[id(sample)]
        candidates = [name for name in split_names if len(assigned[name]) < target_sizes[name]]
        if not candidates:
            candidates = ["train"]

        def score(split_name):
            error_reduction = 0.0
            remaining_need = 0.0
            for class_name, added_count in counts.items():
                target = target_class_counts[class_name][split_name]
                current = assigned_class_counts[split_name].get(class_name, 0)
                before_error = abs(target - current) / class_counts[class_name]
                after_error = abs(target - current - added_count) / class_counts[class_name]
                error_reduction += before_error - after_error
                remaining_need += max(target - current, 0) * added_count / class_counts[class_name]
            size_target = max(target_sizes[split_name], 1)
            size_deficit = (target_sizes[split_name] - len(assigned[split_name])) / size_target
            return error_reduction, remaining_need, size_deficit, -split_names.index(split_name)

        selected = max(candidates, key=score)
        assigned[selected].append(sample)
        for class_name, added_count in counts.items():
            current = assigned_class_counts[selected].get(class_name, 0)
            assigned_class_counts[selected][class_name] = current + added_count

    _improve_multilabel_assignment(
        assigned,
        assigned_class_counts,
        sample_class_counts,
        target_class_counts,
        class_counts,
    )
    return assigned["train"], assigned["val"], assigned["test"]


def _improve_multilabel_assignment(
    assigned,
    assigned_class_counts,
    sample_class_counts,
    target_class_counts,
    class_counts,
):
    """在不改变各集合图片数的前提下交换图片，继续降低各类别比例误差。"""
    split_names = ("train", "val", "test")
    max_iterations = min(sum(len(items) for items in assigned.values()) * 2, 1000)
    for _ in range(max_iterations):
        signature_groups = {}
        for split_name in split_names:
            groups = {}
            for index, sample in enumerate(assigned[split_name]):
                signature = tuple(sorted(sample_class_counts[id(sample)].items()))
                groups.setdefault(signature, (index, sample))
            signature_groups[split_name] = groups

        best_swap = None
        best_improvement = 1e-12
        for left_index, left_name in enumerate(split_names):
            for right_name in split_names[left_index + 1:]:
                left_groups = signature_groups[left_name]
                right_groups = signature_groups[right_name]
                for left_signature in sorted(left_groups):
                    for right_signature in sorted(right_groups):
                        if left_signature == right_signature:
                            continue
                        improvement = _swap_error_improvement(
                            left_name,
                            right_name,
                            dict(left_signature),
                            dict(right_signature),
                            assigned_class_counts,
                            target_class_counts,
                            class_counts,
                        )
                        if improvement > best_improvement:
                            best_improvement = improvement
                            best_swap = (
                                left_name,
                                right_name,
                                left_groups[left_signature],
                                right_groups[right_signature],
                            )

        if best_swap is None:
            break

        left_name, right_name, (left_pos, left_sample), (right_pos, right_sample) = best_swap
        left_counts = sample_class_counts[id(left_sample)]
        right_counts = sample_class_counts[id(right_sample)]
        assigned[left_name][left_pos], assigned[right_name][right_pos] = right_sample, left_sample
        for class_name in set(left_counts) | set(right_counts):
            assigned_class_counts[left_name][class_name] = (
                assigned_class_counts[left_name].get(class_name, 0)
                - left_counts.get(class_name, 0)
                + right_counts.get(class_name, 0)
            )
            assigned_class_counts[right_name][class_name] = (
                assigned_class_counts[right_name].get(class_name, 0)
                - right_counts.get(class_name, 0)
                + left_counts.get(class_name, 0)
            )


def _swap_error_improvement(
    left_name,
    right_name,
    left_counts,
    right_counts,
    assigned_class_counts,
    target_class_counts,
    class_counts,
):
    improvement = 0.0
    for class_name in set(left_counts) | set(right_counts):
        total = class_counts[class_name]
        left_current = assigned_class_counts[left_name].get(class_name, 0)
        right_current = assigned_class_counts[right_name].get(class_name, 0)
        left_target = target_class_counts[class_name][left_name]
        right_target = target_class_counts[class_name][right_name]
        before = (
            abs(left_target - left_current) + abs(right_target - right_current)
        ) / total
        left_after = left_current - left_counts.get(class_name, 0) + right_counts.get(class_name, 0)
        right_after = right_current - right_counts.get(class_name, 0) + left_counts.get(class_name, 0)
        after = (
            abs(left_target - left_after) + abs(right_target - right_after)
        ) / total
        improvement += before - after
    return improvement


def _target_split_sizes(sample_count, train_ratio, val_ratio):
    train_ratio, val_ratio, test_ratio = _normalized_split_ratios(train_ratio, val_ratio)

    train_count = max(1, int(round(sample_count * train_ratio)))
    val_count = int(round(sample_count * val_ratio))
    if sample_count >= 2 and val_ratio > 0:
        val_count = max(1, val_count)
    if train_count + val_count > sample_count:
        train_count = max(1, sample_count - val_count)
    test_count = sample_count - train_count - val_count
    if sample_count >= 3 and test_ratio > 0 and test_count == 0 and train_count > 1:
        train_count -= 1
        test_count = 1
    return train_count, val_count, test_count


def _normalized_split_ratios(train_ratio, val_ratio):
    train_ratio = min(max(float(train_ratio), 0.0), 1.0)
    val_ratio = min(max(float(val_ratio), 0.0), 1.0 - train_ratio)
    return train_ratio, val_ratio, max(0.0, 1.0 - train_ratio - val_ratio)


def _allocate_integer_targets(total, ratios):
    raw_targets = [total * ratio for ratio in ratios]
    targets = [int(value) for value in raw_targets]
    remaining = total - sum(targets)
    order = sorted(
        range(len(ratios)),
        key=lambda index: (
            round(raw_targets[index] - targets[index], 12),
            round(ratios[index], 12),
            -index,
        ),
        reverse=True,
    )
    for index in order[:remaining]:
        targets[index] += 1
    return targets


def _sample_class_box_counts(sample):
    counts = {}
    for label in sample.get("_bboxes", []):
        class_name = _label_class_name(label)
        counts[class_name] = counts.get(class_name, 0) + 1
    return counts


def _collect_class_names(samples):
    return sorted(
        {
            _label_class_name(label)
            for sample in samples
            for label in sample.get("_bboxes", [])
            if _label_class_name(label)
        },
        key=str.casefold,
    )


def _write_yolo_split(samples, img_dir, lbl_dir, class_to_id):
    img_dir.mkdir(parents=True, exist_ok=True)
    lbl_dir.mkdir(parents=True, exist_ok=True)
    used_names = set()

    for s in samples:
        src = s.get("path", s.get("file_path", ""))
        if not src or not os.path.isfile(src):
            continue

        bboxes = s.get("_bboxes", [])
        name = _sample_output_name(s, src, used_names)
        stem = os.path.splitext(name)[0]
        dst_img = img_dir / name
        if not dst_img.exists():
            try:
                os.link(src, dst_img)
            except OSError:
                shutil.copy2(src, dst_img)

        lines = []
        for lbl in bboxes:
            cn = _label_class_name(lbl)
            if cn not in class_to_id:
                raise ValueError(f"标注类别不在全局类别映射中: {cn}")
            cid = class_to_id[cn]
            bbox = lbl.get("bbox", [])
            lines.append(f"{cid} {bbox[0]:.6f} {bbox[1]:.6f} {bbox[2]:.6f} {bbox[3]:.6f}\n")

        with open(lbl_dir / f"{stem}.txt", "w", encoding="utf-8") as f:
            f.writelines(lines)


def _label_class_name(label):
    class_name = str(label.get("class_name") or label.get("name") or "").strip()
    if class_name:
        return class_name
    class_id = label.get("class_id")
    if class_id is not None:
        return f"class_{class_id}"
    return "ship"


def _sample_output_name(sample, source_path, used_names):
    relative = str(sample.get("relative_path") or sample.get("name") or os.path.basename(source_path))
    relative = relative.replace("\\", "/").strip("/")
    name = "__".join(part for part in relative.split("/") if part) or os.path.basename(source_path)
    if not os.path.splitext(name)[1]:
        name += os.path.splitext(source_path)[1]
    candidate = name
    index = 2
    while candidate.casefold() in used_names:
        stem, suffix = os.path.splitext(name)
        candidate = f"{stem}__{index}{suffix}"
        index += 1
    used_names.add(candidate.casefold())
    return candidate


def _sample_key(sample):
    return str(
        sample.get("relative_path")
        or sample.get("file_path")
        or sample.get("path")
        or sample.get("name")
        or ""
    ).casefold()


def _build_conversion_report(
    samples,
    class_to_id,
    train_samples,
    val_samples,
    test_samples,
    train_ratio,
    val_ratio,
):
    source_formats = {}
    class_box_counts = {class_name: 0 for class_name in class_to_id}
    negative_count = 0
    for sample in samples:
        metadata = sample.get("metadata", {}) or {}
        source_format = str(metadata.get("annotation_format") or "internal")
        source_formats[source_format] = source_formats.get(source_format, 0) + 1
        bboxes = sample.get("_bboxes", [])
        if not bboxes:
            negative_count += 1
        for label in bboxes:
            class_name = _label_class_name(label)
            class_box_counts[class_name] = class_box_counts.get(class_name, 0) + 1
    split_names = ("train", "val", "test")
    split_samples = (train_samples, val_samples, test_samples)
    ratios = _normalized_split_ratios(train_ratio, val_ratio)
    actual_class_counts = {
        class_name: {
            split_name: sum(
                _sample_class_box_counts(sample).get(class_name, 0)
                for sample in samples_in_split
            )
            for split_name, samples_in_split in zip(split_names, split_samples)
        }
        for class_name in class_to_id
    }
    label_split_distribution = {}
    max_ratio_error = 0.0
    max_count_deviation = 0
    for class_name, total in class_box_counts.items():
        target_counts = dict(zip(split_names, _allocate_integer_targets(total, ratios)))
        actual_counts = actual_class_counts[class_name]
        actual_ratios = {
            split_name: (actual_counts[split_name] / total if total else 0.0)
            for split_name in split_names
        }
        ratio_errors = {
            split_name: abs(actual_ratios[split_name] - ratios[index])
            for index, split_name in enumerate(split_names)
        }
        count_deviations = {
            split_name: abs(actual_counts[split_name] - target_counts[split_name])
            for split_name in split_names
        }
        max_ratio_error = max(max_ratio_error, *ratio_errors.values())
        max_count_deviation = max(max_count_deviation, *count_deviations.values())
        label_split_distribution[class_name] = {
            "total_boxes": total,
            "target_counts": target_counts,
            "actual_counts": actual_counts,
            "target_ratios": dict(zip(split_names, ratios)),
            "actual_ratios": actual_ratios,
            "ratio_errors": ratio_errors,
            "count_deviations": count_deviations,
        }

    return {
        "source_formats": source_formats,
        "image_count": len(samples),
        "box_count": sum(class_box_counts.values()),
        "negative_image_count": negative_count,
        "class_to_id": class_to_id,
        "class_box_counts": class_box_counts,
        "label_split_distribution": label_split_distribution,
        "max_label_ratio_error": max_ratio_error,
        "max_label_count_deviation": max_count_deviation,
        "split_counts": {
            "train": len(train_samples),
            "val": len(val_samples),
            "test": len(test_samples),
        },
    }
