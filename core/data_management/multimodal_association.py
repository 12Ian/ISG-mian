from __future__ import annotations

from pathlib import Path


IMAGE_EXTENSIONS = {".bmp", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}
RADAR_EXTENSIONS = {".npy", ".npz", ".mat", ".h5", ".hdf5"}


def infer_multimodal_role(path_value: str) -> str:
    """根据相对路径和扩展名识别多模态样本角色。"""
    path = Path(str(path_value or "").replace("\\", "/"))
    parts = {part.casefold() for part in path.parts}
    suffix = path.suffix.casefold()
    if suffix in RADAR_EXTENSIONS or "radar" in parts or "vocradar320" in parts:
        return "radar"
    if suffix in IMAGE_EXTENSIONS and parts.intersection(
        {"mask", "masks", "semantic", "segmentation", "segmentationclass", "labels_mask"}
    ):
        return "mask"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    if suffix in {".txt", ".xml", ".json"} and parts.intersection(
        {"label", "labels", "detection", "annotations", "annotation", "yolo"}
    ):
        return "annotation"
    return "auxiliary"


def multimodal_group_id(path_value: str) -> str:
    """同名的图片、mask、雷达和标注归入同一个稳定组。"""
    path = Path(str(path_value or "").replace("\\", "/"))
    parts = list(path.parts)
    for index, part in enumerate(parts[:-1]):
        if part.casefold() == "groups" and index + 1 < len(parts):
            return parts[index + 1].casefold()
    return path.stem.casefold()


def with_multimodal_association(metadata: dict | None, path_value: str) -> dict:
    result = dict(metadata or {})
    result.setdefault("multimodal_group_id", multimodal_group_id(path_value))
    result.setdefault("multimodal_role", infer_multimodal_role(path_value))
    return result


def sample_metadata(sample) -> dict:
    if isinstance(sample, dict):
        return dict(sample.get("metadata") or sample.get("metadata_json") or {})
    return dict(getattr(sample, "metadata_json", None) or {})


def sample_path(sample) -> str:
    if isinstance(sample, dict):
        return str(sample.get("file_path") or sample.get("path") or sample.get("sample_path") or "")
    return str(getattr(sample, "file_path", "") or "")


def sample_relative_path(sample) -> str:
    if isinstance(sample, dict):
        return str(sample.get("relative_path") or sample_path(sample))
    return str(getattr(sample, "relative_path", "") or sample_path(sample))


def sample_group_id(sample) -> str:
    metadata = sample_metadata(sample)
    return str(metadata.get("multimodal_group_id") or multimodal_group_id(sample_relative_path(sample)))


def sample_role(sample) -> str:
    metadata = sample_metadata(sample)
    return str(metadata.get("multimodal_role") or infer_multimodal_role(sample_relative_path(sample)))
