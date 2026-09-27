from __future__ import annotations

import json
from pathlib import Path

from PIL import Image

from plugins.evaluation.ship_tracking_evaluator import compute_tracking_metrics, run as evaluate_tracking
from plugins.training.ship_tracking import PARAMETERS, run
from plugins.tracking.bytetrack import ByteTrack, bbox_iou


def test_bytetrack_keeps_identity_through_low_confidence_detection():
    tracker = ByteTrack(track_thresh=0.5, low_thresh=0.1, match_thresh=0.3, track_buffer=1)
    first = tracker.update([{"bbox": [0, 0, 20, 20], "score": 0.9, "class_id": 0}])
    second = tracker.update([{"bbox": [1, 1, 21, 21], "score": 0.3, "class_id": 0}])

    assert first[0]["track_id"] == 1
    assert second[0]["track_id"] == 1
    assert bbox_iou(first[0]["bbox"], second[0]["bbox"]) > 0.8


def test_tracking_metrics_detect_id_switch():
    ground_truth = {
        "frames": [
            {"frame_id": 1, "tracks": [{"track_id": 7, "class_id": 0, "bbox": [0, 0, 10, 10]}]},
            {"frame_id": 2, "tracks": [{"track_id": 7, "class_id": 0, "bbox": [1, 0, 11, 10]}]},
        ]
    }
    predictions = {
        "frames": [
            {"frame_id": 1, "tracks": [{"track_id": 1, "class_id": 0, "bbox": [0, 0, 10, 10]}]},
            {"frame_id": 2, "tracks": [{"track_id": 2, "class_id": 0, "bbox": [1, 0, 11, 10]}]},
        ]
    }

    metrics = compute_tracking_metrics(predictions, ground_truth)

    assert metrics["TP"] == 2
    assert metrics["FP"] == 0
    assert metrics["FN"] == 0
    assert metrics["IDSW"] == 1
    assert metrics["HOTA"] < 1.0
    assert metrics["IDF1"] == 0.5


def test_ship_tracking_rejects_missing_checkpoint_after_frame_validation(tmp_path: Path):
    for index in (1, 2):
        image_path = tmp_path / f"frame_{index:06d}.jpg"
        Image.new("RGB", (32, 32), (index, index, index)).save(image_path)

    result = run(
        {
            "parameters": {},
            "input": {
                "dataset_path": str(tmp_path),
                "samples": [
                    {"name": "frame_000001.jpg", "path": str(tmp_path / "frame_000001.jpg")},
                    {"name": "frame_000002.jpg", "path": str(tmp_path / "frame_000002.jpg")},
                ],
            },
            "output": {"output_dir": str(tmp_path / "out")},
        },
        None,
    )

    assert result["ok"] is False
    assert result["error_code"] == "MISSING_CHECKPOINT"


def test_tracking_evaluator_maps_existing_class_name_labels(tmp_path: Path):
    image_path = tmp_path / "frame_000001.jpg"
    Image.new("RGB", (100, 100), (20, 20, 20)).save(image_path)
    predictions_path = tmp_path / "tracking_predictions.json"
    predictions_path.write_text(
        '{"class_names": ["ship"], "frames": [{"frame_id": 1, "tracks": [{"track_id": 3, "class_id": 0, "bbox": [25, 25, 75, 75]}]}]}',
        encoding="utf-8",
    )
    manifest_path = tmp_path / "ship_tracking_manifest.json"
    manifest_path.write_text(json.dumps({"predictions_path": str(predictions_path)}), encoding="utf-8")

    result = evaluate_tracking(
        {
            "parameters": {"model_checkpoint_path": str(manifest_path)},
            "input": {
                "target_dataset": {
                    "name": "truth",
                    "path": str(tmp_path),
                    "samples": [{
                        "name": image_path.name,
                        "path": str(image_path),
                        "labels": [{"class_name": "ship", "track_id": 3, "bbox": [0.5, 0.5, 0.5, 0.5]}],
                    }],
                },
                "baseline_dataset": {"samples": []},
            },
            "output": {"output_dir": str(tmp_path / "report")},
        },
        None,
    )

    assert result["ok"] is True
    assert result["results"][0]["metrics"]["HOTA"] == 1.0


def test_seed_contains_tracking_algorithms_and_binding():
    seed = Path("backend/seed_data.py").read_text(encoding="utf-8")
    scenario = Path("backend/services/evaluation_service.py").read_text(encoding="utf-8")

    assert '"name": "船舰追踪算法"' in seed
    assert '"name": "船舰追踪评估算法"' in seed
    assert '"training.image.ship_tracking": "evaluation.image.ship_tracking"' in seed
    assert '"key": "ship_target_recognition_tracking"' in scenario
    assert all(item["name"] for item in PARAMETERS)
