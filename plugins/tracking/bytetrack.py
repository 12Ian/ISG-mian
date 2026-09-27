"""ByteTrack 的轻量实现。

这里保留 ByteTrack 的关键两阶段关联逻辑：高置信度检测先关联，
再用低置信度检测找回短暂丢失的轨迹。轨迹状态只保存最近一个框，
避免给项目增加额外的跟踪依赖。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


def bbox_iou(left: Iterable[float], right: Iterable[float]) -> float:
    """计算两个 xyxy 框的 IoU。"""
    a = [float(value) for value in list(left)[:4]]
    b = [float(value) for value in list(right)[:4]]
    if len(a) != 4 or len(b) != 4:
        return 0.0
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    inter_width = max(0.0, min(ax2, bx2) - max(ax1, bx1))
    inter_height = max(0.0, min(ay2, by2) - max(ay1, by1))
    intersection = inter_width * inter_height
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - intersection
    return intersection / union if union > 0.0 else 0.0


@dataclass
class _Track:
    track_id: int
    bbox: list[float]
    score: float
    class_id: int
    lost: int = 0

    def update(self, detection: dict) -> None:
        self.bbox = [float(value) for value in detection["bbox"][:4]]
        self.score = float(detection.get("score", self.score))
        self.class_id = int(detection.get("class_id", self.class_id))
        self.lost = 0


class ByteTrack:
    """适用于单帧检测结果的 ByteTrack 关联器。"""

    def __init__(
        self,
        track_thresh: float = 0.5,
        low_thresh: float = 0.1,
        match_thresh: float = 0.8,
        track_buffer: int = 30,
    ) -> None:
        self.track_thresh = float(track_thresh)
        self.low_thresh = float(low_thresh)
        self.match_thresh = float(match_thresh)
        self.track_buffer = max(0, int(track_buffer))
        self._next_id = 1
        self._tracks: list[_Track] = []

    def reset(self) -> None:
        self._next_id = 1
        self._tracks = []

    def update(self, detections: Iterable[dict]) -> list[dict]:
        valid = [self._normalize_detection(item) for item in detections]
        valid = [item for item in valid if item is not None]
        high = [item for item in valid if item["score"] >= self.track_thresh]
        low = [
            item
            for item in valid
            if self.low_thresh <= item["score"] < self.track_thresh
        ]

        active_indices = [
            index for index, track in enumerate(self._tracks)
            if track.lost <= self.track_buffer
        ]
        matched_tracks: set[int] = set()
        output: list[dict] = []

        matches, unmatched_track_indices, unmatched_detection_indices = self._match(
            active_indices, high
        )
        for track_index, detection_index in matches:
            track = self._tracks[track_index]
            track.update(high[detection_index])
            matched_tracks.add(track_index)
            output.append(self._serialize_track(track))

        # 第二阶段只处理第一阶段没有匹配上的旧轨迹，低分框不能新建轨迹。
        second_pool = [index for index in unmatched_track_indices if index not in matched_tracks]
        low_matches, _, _ = self._match(second_pool, low)
        for track_index, detection_index in low_matches:
            track = self._tracks[track_index]
            track.update(low[detection_index])
            matched_tracks.add(track_index)
            output.append(self._serialize_track(track))

        for detection_index in unmatched_detection_indices:
            detection = high[detection_index]
            track = _Track(
                track_id=self._next_id,
                bbox=list(detection["bbox"]),
                score=float(detection["score"]),
                class_id=int(detection["class_id"]),
            )
            self._next_id += 1
            self._tracks.append(track)
            new_index = len(self._tracks) - 1
            matched_tracks.add(new_index)
            output.append(self._serialize_track(track))

        for index, track in enumerate(self._tracks):
            if index not in matched_tracks:
                track.lost += 1

        self._tracks = [track for track in self._tracks if track.lost <= self.track_buffer]
        return sorted(output, key=lambda item: item["track_id"])

    def _match(self, track_indices: list[int], detections: list[dict]):
        candidates = []
        for track_index in track_indices:
            track = self._tracks[track_index]
            for detection_index, detection in enumerate(detections):
                if track.class_id != int(detection["class_id"]):
                    continue
                overlap = bbox_iou(track.bbox, detection["bbox"])
                if overlap >= self.match_thresh:
                    candidates.append((overlap, track_index, detection_index))
        candidates.sort(key=lambda item: (-item[0], item[1], item[2]))
        used_tracks: set[int] = set()
        used_detections: set[int] = set()
        matches = []
        for _, track_index, detection_index in candidates:
            if track_index in used_tracks or detection_index in used_detections:
                continue
            used_tracks.add(track_index)
            used_detections.add(detection_index)
            matches.append((track_index, detection_index))
        unmatched_tracks = [index for index in track_indices if index not in used_tracks]
        unmatched_detections = [index for index in range(len(detections)) if index not in used_detections]
        return matches, unmatched_tracks, unmatched_detections

    @staticmethod
    def _normalize_detection(detection: dict | None) -> dict | None:
        if not isinstance(detection, dict):
            return None
        try:
            bbox = [float(value) for value in list(detection.get("bbox", []))[:4]]
            score = float(detection.get("score", 0.0))
            class_id = int(detection.get("class_id", 0))
        except (TypeError, ValueError):
            return None
        if len(bbox) != 4 or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            return None
        return {"bbox": bbox, "score": score, "class_id": class_id}

    @staticmethod
    def _serialize_track(track: _Track) -> dict:
        return {
            "track_id": track.track_id,
            "bbox": [round(value, 4) for value in track.bbox],
            "score": round(float(track.score), 6),
            "class_id": track.class_id,
        }
