"""船舰追踪评估算法：比较预测轨迹与真实轨迹。"""

from __future__ import annotations

import json
import math
import re
import traceback
from collections import Counter, defaultdict
from pathlib import Path

from PIL import Image

from plugins.tracking import bbox_iou


_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}

PARAMETERS = [
    {
        "name": "model_checkpoint_path",
        "type": "string",
        "label": "追踪结果 manifest 路径",
        "default": "",
        "options": [],
        "description": "选择船舰追踪算法产生的 ship_tracking_manifest.json。",
        "required": True,
    },
    {
        "name": "match_iou",
        "type": "float",
        "label": "真实框匹配 IoU",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "预测框与真实框达到该 IoU 才算同一目标。",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        return _run_evaluation(payload, context)
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "TRACKING_EVALUATION_CRASH",
            "message": f"船舰追踪评估失败: {exc}\n{traceback.format_exc()}",
        }


def _run_evaluation(payload: dict, context) -> dict:
    params = payload.get("parameters", {}) or {}
    checkpoint = Path(str(params.get("model_checkpoint_path", ""))).expanduser()
    if not checkpoint.is_file():
        return {"ok": False, "error_code": "MISSING_CHECKPOINT", "message": f"找不到追踪结果文件：{checkpoint}"}

    predictions = _load_predictions(checkpoint)
    class_names = [str(item) for item in (predictions.get("class_names", []) if isinstance(predictions, dict) else [])]
    target = (payload.get("input", {}) or {}).get("target_dataset", {}) or {}
    baseline = (payload.get("input", {}) or {}).get("baseline_dataset", {}) or {}
    ground_truth = _collect_ground_truth(target, class_names)
    ground_truth_dataset = target
    if not ground_truth:
        ground_truth = _collect_ground_truth(baseline, class_names)
        ground_truth_dataset = baseline
    if not ground_truth:
        return {
            "ok": False,
            "error_code": "NO_GROUND_TRUTH",
            "message": "真实轨迹为空：请在图片样本 labels_json 中填写 bbox 和 track_id，或提供 tracking_annotations.json",
        }

    metrics = compute_tracking_metrics(
        predictions,
        ground_truth,
        iou_threshold=float(params.get("match_iou", 0.5)),
    )
    metrics["ground_truth_dataset"] = ground_truth_dataset.get("name", "")
    metrics["prediction_manifest"] = str(checkpoint)

    output_dir = Path((payload.get("output", {}) or {}).get("output_dir", ""))
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "ship_tracking_metrics.json"
    report_path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    progress = getattr(context, "set_progress", None)
    if progress:
        progress(100.0, f"船舰追踪评估完成：HOTA={metrics['HOTA']:.4f}，IDF1={metrics['IDF1']:.4f}")

    return {
        "ok": True,
        "results": [{
            "model_name": "船舰追踪评估算法",
            "metrics": metrics,
            "summary": (
                f"船舰追踪评估完成：HOTA {metrics['HOTA']:.4f}，IDF1 {metrics['IDF1']:.4f}，"
                f"MOTA {metrics['MOTA']:.4f}，ID 切换 {metrics['IDSW']} 次"
            ),
            "artifacts": [{"type": "report", "path": str(report_path)}],
        }],
    }


def compute_tracking_metrics(predictions: dict, ground_truth: dict, iou_threshold: float = 0.5) -> dict:
    """计算检测、身份和关联指标。

    这里使用逐帧 IoU 匹配，并对身份对进行全局一对一计数，
    足以评估本插件生成的单摄像头船舰轨迹。
    """
    prediction_frames = _normalize_frame_map(predictions)
    ground_truth_frames = _normalize_frame_map(ground_truth)
    frame_ids = sorted(set(prediction_frames) | set(ground_truth_frames))
    total_gt = sum(len(ground_truth_frames.get(frame_id, [])) for frame_id in frame_ids)
    total_pred = sum(len(prediction_frames.get(frame_id, [])) for frame_id in frame_ids)
    true_positive = 0
    id_switches = 0
    previous_prediction_by_gt: dict[int, int] = {}
    pair_counts: Counter[tuple[int, int]] = Counter()
    pair_frames: defaultdict[tuple[int, int], set[int]] = defaultdict(set)
    gt_frames: defaultdict[int, set[int]] = defaultdict(set)
    pred_frames: defaultdict[int, set[int]] = defaultdict(set)

    for frame_id in frame_ids:
        gt_items = ground_truth_frames.get(frame_id, [])
        pred_items = prediction_frames.get(frame_id, [])
        matches = _match_frame(gt_items, pred_items, iou_threshold)
        true_positive += len(matches)
        for gt_index, pred_index in matches:
            gt_id = int(gt_items[gt_index]["track_id"])
            pred_id = int(pred_items[pred_index]["track_id"])
            if gt_id in previous_prediction_by_gt and previous_prediction_by_gt[gt_id] != pred_id:
                id_switches += 1
            previous_prediction_by_gt[gt_id] = pred_id
            pair = (gt_id, pred_id)
            pair_counts[pair] += 1
            pair_frames[pair].add(frame_id)
            gt_frames[gt_id].add(frame_id)
            pred_frames[pred_id].add(frame_id)

    false_positive = total_pred - true_positive
    false_negative = total_gt - true_positive
    id_true_positive = _global_identity_matches(pair_counts)
    id_false_positive = total_pred - id_true_positive
    id_false_negative = total_gt - id_true_positive
    idf1 = _ratio(2 * id_true_positive, 2 * id_true_positive + id_false_positive + id_false_negative)
    precision = _ratio(true_positive, true_positive + false_positive)
    recall = _ratio(true_positive, true_positive + false_negative)
    mota = 1.0 - _ratio(false_positive + false_negative + id_switches, total_gt)

    association_sum = 0.0
    for pair, matched_count in pair_counts.items():
        gt_id, pred_id = pair
        tpa = matched_count
        fpa = len(pred_frames[pred_id] - pair_frames[pair])
        fna = len(gt_frames[gt_id] - pair_frames[pair])
        association_sum += matched_count * _ratio(tpa, tpa + fpa + fna)
    association_accuracy = _ratio(association_sum, true_positive)
    detection_accuracy = _ratio(
        true_positive,
        math.sqrt((true_positive + false_positive) * (true_positive + false_negative)),
    )
    hota = math.sqrt(max(0.0, detection_accuracy * association_accuracy))

    return {
        "HOTA": round(hota, 6),
        "IDF1": round(idf1, 6),
        "MOTA": round(mota, 6),
        "IDSW": int(id_switches),
        "FP": int(false_positive),
        "FN": int(false_negative),
        "TP": int(true_positive),
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "frames": len(frame_ids),
        "ground_truth_detections": int(total_gt),
        "predicted_detections": int(total_pred),
        "identity_true_positive": int(id_true_positive),
    }


def _match_frame(gt_items: list[dict], pred_items: list[dict], threshold: float):
    candidates = []
    for gt_index, gt_item in enumerate(gt_items):
        for pred_index, pred_item in enumerate(pred_items):
            if int(gt_item.get("class_id", 0)) != int(pred_item.get("class_id", 0)):
                continue
            overlap = bbox_iou(gt_item["bbox"], pred_item["bbox"])
            if overlap >= threshold:
                candidates.append((overlap, gt_index, pred_index))
    candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
    used_gt: set[int] = set()
    used_pred: set[int] = set()
    matches = []
    for _, gt_index, pred_index in candidates:
        if gt_index in used_gt or pred_index in used_pred:
            continue
        used_gt.add(gt_index)
        used_pred.add(pred_index)
        matches.append((gt_index, pred_index))
    return matches


def _global_identity_matches(pair_counts: Counter[tuple[int, int]]) -> int:
    used_gt: set[int] = set()
    used_pred: set[int] = set()
    total = 0
    for (gt_id, pred_id), count in sorted(pair_counts.items(), key=lambda item: (-item[1], item[0])):
        if gt_id in used_gt or pred_id in used_pred:
            continue
        used_gt.add(gt_id)
        used_pred.add(pred_id)
        total += count
    return total


def _normalize_frame_map(value: dict) -> dict[int, list[dict]]:
    if isinstance(value, dict) and "frames" in value:
        value = value["frames"]
    result: defaultdict[int, list[dict]] = defaultdict(list)
    if isinstance(value, dict):
        value = [{"frame_id": key, "tracks": items} for key, items in value.items()]
    for frame in value or []:
        if not isinstance(frame, dict):
            continue
        try:
            frame_id = int(frame.get("frame_id", frame.get("frame_index", 0)))
        except (TypeError, ValueError):
            continue
        items = frame.get("tracks") or frame.get("objects") or frame.get("detections") or []
        for item in items:
            normalized = _normalize_track_item(item)
            if normalized is not None:
                result[frame_id].append(normalized)
    return dict(result)


def _normalize_track_item(item: dict | None) -> dict | None:
    if not isinstance(item, dict):
        return None
    track_value = item.get("track_id", item.get("trackId", item.get("object_id", item.get("id"))))
    try:
        track_id = int(track_value)
        class_id = int(item.get("class_id", item.get("classId", 0)))
        bbox = [float(value) for value in list(item.get("bbox", []))[:4]]
    except (TypeError, ValueError):
        return None
    if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return None
    return {"track_id": track_id, "class_id": class_id, "bbox": bbox}


def _load_predictions(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if isinstance(data, dict) and data.get("predictions_path"):
        prediction_path = Path(str(data["predictions_path"]))
        if not prediction_path.is_absolute():
            prediction_path = path.parent / prediction_path
        data = json.loads(prediction_path.read_text(encoding="utf-8-sig"))
    return data


def _collect_ground_truth(dataset: dict, class_names: list[str] | None = None) -> dict:
    frames = []
    class_to_id = {name: index for index, name in enumerate(class_names or [])}
    for index, sample in enumerate(dataset.get("samples", []) or []):
        if not isinstance(sample, dict):
            continue
        path = _sample_path(sample, dataset.get("path", ""))
        metadata = sample.get("metadata") or sample.get("metadata_json") or {}
        frame_id = _frame_id(sample, metadata, index)
        labels = _as_list(sample.get("labels") or sample.get("labels_json") or metadata.get("tracking_labels"))
        tracks = []
        image_size = _image_size(path)
        for label in labels:
            item = _ground_truth_item(label, image_size, class_to_id)
            if item is not None:
                tracks.append(item)
        if tracks:
            frames.append({"frame_id": frame_id, "tracks": tracks})
    if frames:
        return {"frames": frames}
    return _load_external_ground_truth(dataset)


def _load_external_ground_truth(dataset: dict) -> dict:
    root = Path(str(dataset.get("path", "")))
    candidates = [root / name for name in ("tracking_annotations.json", "ground_truth.json", "annotations.json")]
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            data = json.loads(candidate.read_text(encoding="utf-8-sig"))
        except (OSError, ValueError):
            continue
        normalized = _normalize_frame_map(data)
        if normalized:
            return {"frames": [{"frame_id": key, "tracks": items} for key, items in normalized.items()]}
    return {}


def _ground_truth_item(
    label: dict,
    image_size: tuple[int, int] | None,
    class_to_id: dict[str, int] | None = None,
) -> dict | None:
    if not isinstance(label, dict):
        return None
    track_value = label.get("track_id", label.get("trackId", label.get("object_id", label.get("objectId", label.get("id")))))
    if track_value is None:
        return None
    try:
        track_id = int(track_value)
        class_value = label.get("class_id", label.get("classId"))
        if class_value is None:
            class_name = str(label.get("class_name") or label.get("name") or label.get("label") or "").strip()
            class_id = int((class_to_id or {}).get(class_name, 0))
        else:
            class_id = int(class_value)
        values = [float(value) for value in list(label.get("bbox", []))[:4]]
    except (TypeError, ValueError):
        return None
    if len(values) != 4:
        return None
    fmt = str(label.get("bbox_format", "cxcywh")).casefold()
    normalized = all(0.0 <= value <= 1.0 for value in values)
    if normalized and image_size:
        width, height = image_size
        if fmt in {"xyxy", "normalized_xyxy"}:
            values = [values[0] * width, values[1] * height, values[2] * width, values[3] * height]
        else:
            values = [
                (values[0] - values[2] / 2) * width,
                (values[1] - values[3] / 2) * height,
                (values[0] + values[2] / 2) * width,
                (values[1] + values[3] / 2) * height,
            ]
    elif fmt in {"cxcywh", "pixel_cxcywh"}:
        values = [values[0] - values[2] / 2, values[1] - values[3] / 2, values[0] + values[2] / 2, values[1] + values[3] / 2]
    if values[2] <= values[0] or values[3] <= values[1]:
        return None
    return {"track_id": track_id, "class_id": class_id, "bbox": values}


def _sample_path(sample: dict, dataset_path: str) -> Path:
    value = sample.get("path") or sample.get("file_path") or sample.get("sample_path") or ""
    path = Path(str(value))
    if not path.is_absolute() and dataset_path:
        path = Path(str(dataset_path)) / path
    return path


def _image_size(path: Path) -> tuple[int, int] | None:
    if path.suffix.casefold() not in _IMAGE_EXTENSIONS or not path.is_file():
        return None
    try:
        with Image.open(path) as image:
            return image.size
    except (OSError, ValueError):
        return None


def _frame_id(sample: dict, metadata: dict, fallback: int) -> int:
    for key in ("frame_id", "frame_index", "frame_number"):
        value = metadata.get(key, sample.get(key))
        try:
            if value is not None:
                return int(value)
        except (TypeError, ValueError):
            pass
    numbers = re.findall(r"\d+", str(sample.get("relative_path") or sample.get("name") or ""))
    return int(numbers[-1]) if numbers else fallback


def _as_list(value) -> list:
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except ValueError:
            return []
    return list(value) if isinstance(value, (list, tuple)) else []


def _ratio(numerator: float, denominator: float) -> float:
    return float(numerator) / float(denominator) if denominator else 0.0
