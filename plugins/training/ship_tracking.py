"""船舰追踪算法：YOLOv5 检测与 ByteTrack 轨迹执行。"""

from __future__ import annotations

import json
import re
import sys
import time
import traceback
from pathlib import Path

from plugins.tracking import ByteTrack


_IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
_YOLOV5_ROOT = Path(__file__).resolve().parent.parent / "detection" / "yolov5_core"

PARAMETERS = [
    {
        "name": "model_checkpoint_path",
        "type": "string",
        "label": "YOLOv5 权重路径",
        "default": "",
        "options": [],
        "description": "已训练的 YOLOv5 .pt 文件路径；也可填写 weights 参数。",
        "required": False,
    },
    {
        "name": "weights",
        "type": "select",
        "label": "YOLOv5 权重路径（备用）",
        "default": "",
        "options": [""],
        "description": "从已完成的 YOLOv5 训练历史中选择 best.pt；当未填写手动路径时使用。",
        "required": False,
    },
    {
        "name": "has_correct_tracking_labels",
        "type": "select",
        "label": "是否携带正确标注",
        "default": "是",
        "options": ["是", "否"],
        "description": "选择“是”时要求每个检测框已有 track_id；选择“否”时由 ByteTrack 自动生成追踪序号。",
        "required": False,
    },
    {
        "name": "conf_thres",
        "type": "float",
        "label": "检测置信度阈值",
        "default": 0.25,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "送入 ByteTrack 的最低检测置信度。",
        "required": False,
    },
    {
        "name": "iou_thres",
        "type": "float",
        "label": "NMS IoU 阈值",
        "default": 0.45,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "YOLOv5 NMS 的 IoU 阈值。",
        "required": False,
    },
    {
        "name": "img_size",
        "type": "int",
        "label": "推理图像尺寸",
        "default": 640,
        "min": 320,
        "max": 1280,
        "options": [],
        "description": "YOLOv5 推理输入尺寸。",
        "required": False,
    },
    {
        "name": "track_thresh",
        "type": "float",
        "label": "轨迹高置信度阈值",
        "default": 0.5,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "高置信度阶段用于新建和关联轨迹的阈值。",
        "required": False,
    },
    {
        "name": "low_thresh",
        "type": "float",
        "label": "轨迹低置信度阈值",
        "default": 0.1,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "低置信度阶段允许用于找回旧轨迹的下限。",
        "required": False,
    },
    {
        "name": "match_thresh",
        "type": "float",
        "label": "轨迹匹配 IoU 阈值",
        "default": 0.3,
        "min": 0.0,
        "max": 1.0,
        "options": [],
        "description": "检测框与已有轨迹的最小 IoU。",
        "required": False,
    },
    {
        "name": "track_buffer",
        "type": "int",
        "label": "轨迹保留帧数",
        "default": 30,
        "min": 0,
        "max": 300,
        "options": [],
        "description": "检测暂时丢失时保留轨迹的帧数。",
        "required": False,
    },
    {
        "name": "fps",
        "type": "int",
        "label": "输出视频帧率",
        "default": 10,
        "min": 1,
        "max": 120,
        "options": [],
        "description": "输入图片序列生成视频时使用的帧率。",
        "required": False,
    },
    {
        "name": "device",
        "type": "string",
        "label": "推理设备",
        "default": "",
        "options": ["", "cpu", "0"],
        "description": "空值自动选择；也可填写 cpu 或 GPU 编号。",
        "required": False,
    },
    {
        "name": "save_video",
        "type": "bool",
        "label": "保存跟踪视频",
        "default": True,
        "options": [],
        "description": "将带 track_id 的结果写入 MP4 视频。",
        "required": False,
    },
]


def run(payload: dict, context) -> dict:
    try:
        return _run_tracking(payload, context)
    except Exception as exc:
        return {
            "ok": False,
            "error_code": "TRACKING_CRASH",
            "message": f"船舰追踪算法执行失败: {exc}\n{traceback.format_exc()}",
        }


def _run_tracking(payload: dict, context) -> dict:
    params = payload.get("parameters", {}) or {}
    input_data = payload.get("input", {}) or {}
    output_dir = Path((payload.get("output", {}) or {}).get("output_dir", ""))
    if not str(output_dir):
        return {"ok": False, "error_code": "MISSING_OUTPUT_DIR", "message": "缺少输出目录"}
    output_dir.mkdir(parents=True, exist_ok=True)

    frames = _collect_frames(input_data.get("samples", []), input_data.get("dataset_path", ""))
    if len(frames) < 2:
        return {"ok": False, "error_code": "INSUFFICIENT_FRAMES", "message": "船舰追踪至少需要 2 张按顺序排列的图片帧"}

    weight_value = params.get("model_checkpoint_path") or params.get("weights")
    weights_path = _resolve_path(weight_value, input_data.get("dataset_path", ""))
    if not weights_path or not weights_path.is_file() or weights_path.suffix.casefold() != ".pt":
        return {
            "ok": False,
            "error_code": "MISSING_CHECKPOINT",
            "message": f"找不到 YOLOv5 .pt 权重，请填写 model_checkpoint_path：{weight_value or '未填写'}",
        }

    if _has_correct_tracking_labels(params):
        missing = _find_missing_tracking_label(input_data.get("samples", []))
        if missing:
            return {
                "ok": False,
                "error_code": "MISSING_TRACK_LABELS",
                "message": "未携带正确标注：检测框缺少追踪序号 track_id，请选择“不携带正确标注”后由 ByteTrack 自动生成。",
            }

    progress = getattr(context, "set_progress", None)
    _set_progress(progress, 1.0, f"已读取 {len(frames)} 张图片帧")
    model = _load_detector(weights_path, params)
    class_names = _class_names(getattr(model, "names", {}))
    tracker = ByteTrack(
        track_thresh=float(params.get("track_thresh", 0.5)),
        low_thresh=float(params.get("low_thresh", 0.1)),
        match_thresh=float(params.get("match_thresh", 0.3)),
        track_buffer=int(params.get("track_buffer", 30)),
    )
    conf_thres = float(params.get("conf_thres", 0.25))
    observations = []
    started = time.perf_counter()
    for index, frame in enumerate(frames):
        if _is_cancelled(context):
            return {"ok": False, "error_code": "CANCELLED", "message": "追踪任务已取消"}
        detections = _detect(model, frame["path"], int(params.get("img_size", 640)), conf_thres)
        tracks = tracker.update(detections)
        observations.append({
            "frame_id": frame["frame_id"],
            "image_path": str(frame["path"]),
            "tracks": tracks,
        })
        _set_progress(progress, 5.0 + (index + 1) / len(frames) * 80.0, f"正在追踪 {index + 1}/{len(frames)}")

    elapsed = max(time.perf_counter() - started, 1e-9)
    fps = int(params.get("fps", 10))
    video_path = ""
    if bool(params.get("save_video", True)):
        video_file = output_dir / "ship_tracking.mp4"
        if _write_video(observations, video_file, fps):
            video_path = str(video_file)

    predictions_path = output_dir / "tracking_predictions.json"
    prediction_payload = {
        "type": "ship_tracking_predictions",
        "version": 1,
        "fps": fps,
        "class_names": class_names,
        "frames": observations,
    }
    predictions_path.write_text(json.dumps(prediction_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    manifest_path = output_dir / "ship_tracking_manifest.json"
    manifest = {
        "type": "ship_tracking_result",
        "version": 1,
        "detector_checkpoint": str(weights_path),
        "predictions_path": str(predictions_path),
        "video_path": video_path,
        "fps": fps,
        "class_names": class_names,
        "frame_count": len(frames),
        "processing_fps": round(len(frames) / elapsed, 3),
        "parameters": {key: value for key, value in params.items() if key != "model_checkpoint_path"},
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _set_progress(progress, 100.0, "船舰追踪完成")

    metrics = {
        "frames": len(frames),
        "tracked_detections": sum(len(item["tracks"]) for item in observations),
        "track_count": len({track["track_id"] for item in observations for track in item["tracks"]}),
        "processing_fps": manifest["processing_fps"],
    }
    video_note = "，已生成跟踪视频" if video_path else "，视频编码不可用，已保留轨迹配置文件"
    outputs = [{
        "artifact_path": str(manifest_path),
        "artifact_type": "tracking_manifest",
        "metrics": metrics,
        "metadata": {
            "predictions_path": str(predictions_path),
            "video_path": video_path,
            "detector_checkpoint": str(weights_path),
        },
        "summary": f"船舰追踪完成：处理 {len(frames)} 帧，生成 {metrics['track_count']} 条轨迹{video_note}",
    }]
    if video_path:
        outputs.append({"artifact_path": video_path, "artifact_type": "video"})
    outputs.append({"artifact_path": str(predictions_path), "artifact_type": "predictions"})
    return {
        "ok": True,
        "outputs": outputs,
    }


def _collect_frames(samples, dataset_path: str) -> list[dict]:
    result = []
    for index, sample in enumerate(samples or []):
        if not isinstance(sample, dict):
            continue
        path = _resolve_path(sample.get("path") or sample.get("file_path") or sample.get("sample_path"), dataset_path)
        if not path or path.suffix.casefold() not in _IMAGE_EXTENSIONS or not path.is_file():
            continue
        metadata = sample.get("metadata") or sample.get("metadata_json") or {}
        frame_id = _frame_id(sample, metadata, index)
        result.append({"frame_id": frame_id, "path": path, "name": sample.get("name", path.name), "index": index})
    ordered = sorted(result, key=lambda item: (item["frame_id"], _natural_key(item["name"]), item["index"]))
    unique = {}
    for item in ordered:
        # 数据集导入可能同时保留 images 根目录和 train/val 副本，同一帧只追踪一次。
        unique.setdefault(item["frame_id"], item)
    return list(unique.values())


def _has_correct_tracking_labels(params: dict) -> bool:
    value = params.get("has_correct_tracking_labels", "是")
    if isinstance(value, bool):
        return value
    return str(value).strip().casefold() not in {"否", "no", "false", "0", "n"}


def _find_missing_tracking_label(samples) -> bool:
    samples = list(samples or [])
    if not samples:
        return True
    found_detection = False
    for sample in samples:
        labels = sample.get("labels") or sample.get("labels_json") or []
        if not isinstance(labels, list):
            return True
        for label in labels:
            if not isinstance(label, dict):
                return True
            bbox = label.get("bbox") or []
            if len(bbox) < 4 and label.get("type") not in {"detection", "bbox"}:
                continue
            found_detection = True
            if label.get("track_id") is None or str(label.get("track_id")).strip() == "":
                return True
    return not found_detection


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


def _natural_key(value: str):
    return [int(item) if item.isdigit() else item.casefold() for item in re.split(r"(\d+)", str(value))]


def _resolve_path(value, base: str | Path = "") -> Path | None:
    if not value:
        return None
    candidate = Path(str(value)).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    if not candidate.is_absolute() and base:
        joined = Path(str(base)) / candidate
        if joined.is_file():
            return joined.resolve()
    return candidate.resolve() if candidate.exists() else candidate


def _load_detector(weights_path: Path, params: dict):
    import torch
    from core.hardware_adapter import resolve_yolo_device

    if str(_YOLOV5_ROOT) not in sys.path:
        sys.path.insert(0, str(_YOLOV5_ROOT))
    from models.common import AutoShape, DetectMultiBackend
    from utils.torch_utils import select_device

    device_name, _ = resolve_yolo_device(params.get("device", ""), torch)
    device = select_device(device_name)
    backend = DetectMultiBackend(str(weights_path), device=device, dnn=False, fp16=False)
    detector = AutoShape(backend, verbose=False)
    detector.conf = float(params.get("conf_thres", 0.25))
    detector.iou = float(params.get("iou_thres", 0.45))
    return detector


def _detect(model, image_path: Path, img_size: int, conf_thres: float) -> list[dict]:
    result = model(str(image_path), size=img_size)
    detections = []
    for row in result.pred[0].detach().cpu().tolist():
        if len(row) < 6 or float(row[4]) < conf_thres:
            continue
        detections.append({
            "bbox": [float(value) for value in row[:4]],
            "score": float(row[4]),
            "class_id": int(row[5]),
        })
    return detections


def _class_names(value) -> list[str]:
    if isinstance(value, dict):
        return [str(value[key]) for key in sorted(value, key=lambda item: int(item) if str(item).isdigit() else str(item))]
    return [str(item) for item in (value or [])]


def _write_video(observations: list[dict], video_path: Path, fps: int) -> bool:
    import cv2

    first = cv2.imread(str(observations[0]["image_path"]))
    if first is None:
        return False
    height, width = first.shape[:2]
    writer = cv2.VideoWriter(str(video_path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        return False
    try:
        for observation in observations:
            frame = cv2.imread(str(observation["image_path"]))
            if frame is None:
                continue
            for track in observation["tracks"]:
                x1, y1, x2, y2 = [int(round(value)) for value in track["bbox"]]
                color = _track_color(track["track_id"])
                cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
                label = f"ID {track['track_id']}"
                label_size = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.55, 2)[0]
                label_x = max(0, x2 - label_size[0] - 4)
                label_y = min(height - 2, max(label_size[1] + 2, y1 + label_size[1] + 2))
                cv2.rectangle(frame, (label_x, label_y - label_size[1] - 4), (label_x + label_size[0] + 6, label_y + 2), color, -1)
                cv2.putText(frame, label, (label_x + 3, label_y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (17, 24, 39), 2)
            writer.write(frame)
    finally:
        writer.release()
    return video_path.is_file() and video_path.stat().st_size > 0


def _track_color(track_id: int) -> tuple[int, int, int]:
    colors = (
        (238, 211, 34),
        (21, 115, 249),
        (186, 126, 167),
        (105, 211, 52),
        (90, 63, 244),
        (15, 202, 250),
        (250, 165, 96),
        (133, 113, 251),
    )
    return colors[abs(int(track_id)) % len(colors)]


def _set_progress(callback, value: float, message: str) -> None:
    if callback:
        callback(float(value), message)


def _is_cancelled(context) -> bool:
    callback = getattr(context, "is_cancel_requested", None)
    return bool(callback and callback())
