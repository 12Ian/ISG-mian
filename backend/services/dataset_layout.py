from __future__ import annotations

from pathlib import Path, PurePosixPath


DATASET_STAGE_DIR_NAMES = ("raw", "cleaned", "generated", "preview")
_DATASET_STAGE_DIR_SET = frozenset(DATASET_STAGE_DIR_NAMES)


def dataset_content_roots(root: Path) -> list[Path]:
    """阶段化目录只扫描阶段目录内部，普通目录保持原有行为。"""
    stage_roots = [root / name for name in DATASET_STAGE_DIR_NAMES if (root / name).is_dir()]
    return stage_roots or [root]


def normalize_dataset_relative_path(relative_path: str | Path) -> str:
    """移除重复的阶段目录前缀，避免数据集流转后形成 raw/raw 等嵌套。"""
    normalized = str(relative_path or "").replace("\\", "/").lstrip("/")
    parts = list(PurePosixPath(normalized).parts)
    while parts and parts[0].lower() in _DATASET_STAGE_DIR_SET:
        parts.pop(0)
    return PurePosixPath(*parts).as_posix() if parts else ""


def normalize_generated_source_relative_path(relative_path: str | Path) -> str:
    """生成数据合并原图时固定为一层 source 目录。"""
    normalized = normalize_dataset_relative_path(relative_path)
    parts = list(PurePosixPath(normalized).parts)
    while parts and parts[0].lower() == "source":
        parts.pop(0)
    return normalize_dataset_relative_path(PurePosixPath(*parts)) if parts else ""
