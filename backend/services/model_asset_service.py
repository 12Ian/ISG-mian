from __future__ import annotations

import shutil
import re
from dataclasses import field
from pathlib import Path

from .._compat import slots_dataclass
from ..errors import NotFoundError, ValidationError
from .base import ServiceBase


@slots_dataclass
class ModelAssetService(ServiceBase):
    ALLOWED_FAMILIES: tuple[str, ...] = field(
        default=("yolov5", "yolov8", "yolo11", "custom"), init=False
    )
    ALLOWED_EXTENSIONS: tuple[str, ...] = field(
        default=(".pt", ".pth", ".onnx", ".engine", ".yaml", ".yml"), init=False
    )

    def list_assets(self, family: str = "") -> dict:
        normalized_family = self._normalize_family(family, allow_empty=True)
        root = self.paths.models_dir
        root.mkdir(parents=True, exist_ok=True)
        items = []
        families = [normalized_family] if normalized_family else list(self.ALLOWED_FAMILIES)
        for family_name in families:
            family_dir = root / family_name
            if not family_dir.is_dir():
                continue
            for path in sorted(family_dir.iterdir(), key=lambda item: item.name.casefold()):
                if (
                    not path.is_symlink()
                    and path.is_file()
                    and path.suffix.casefold() in self.ALLOWED_EXTENSIONS
                ):
                    items.append(self._serialize(path, family_name))
        return {
            "ok": True,
            "data": {
                "root_dir": str(root),
                "families": list(self.ALLOWED_FAMILIES),
                "extensions": list(self.ALLOWED_EXTENSIONS),
                "items": items,
            },
        }

    def import_asset(self, source_path: str, family: str) -> dict:
        source = Path(str(source_path or "")).expanduser()
        if not source.is_file():
            raise NotFoundError(f"模型文件不存在: {source}")
        if source.suffix.casefold() not in self.ALLOWED_EXTENSIONS:
            raise ValidationError(
                f"不支持的模型格式 {source.suffix or '(无扩展名)'}，允许: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        normalized_family = self._normalize_family(family)
        if normalized_family == "yolov5" and self._is_yolov5u_name(source.name):
            raise ValidationError(
                f"{source.name} 是 anchor-free YOLOv5u 模型，不能由当前传统 YOLOv5 "
                "训练引擎加载。请导入 yolov5n.pt、yolov5s.pt 等传统 YOLOv5 权重，"
                "或使用独立的 Ultralytics 训练插件。"
            )
        target_dir = self.paths.models_dir / normalized_family
        target_dir.mkdir(parents=True, exist_ok=True)
        target = self._available_target(target_dir, source.name)
        shutil.copy2(source, target)
        return {"ok": True, "data": self._serialize(target, normalized_family)}

    def delete_asset(self, asset_id: str) -> dict:
        target = self._asset_path(asset_id)
        if not target.is_file():
            raise NotFoundError(f"模型文件不存在: {asset_id}")
        target.unlink()
        try:
            target.parent.rmdir()
        except OSError:
            pass
        return {"ok": True, "data": {"id": asset_id}}

    def paths_for_family(self, family: str, *, include_custom: bool = True) -> list[str]:
        normalized_family = self._normalize_family(family)
        families = [normalized_family]
        if include_custom and normalized_family != "custom":
            families.append("custom")
        paths = []
        for family_name in families:
            family_dir = self.paths.models_dir / family_name
            if not family_dir.is_dir():
                continue
            paths.extend(
                str(path.resolve())
                for path in sorted(family_dir.iterdir(), key=lambda item: item.name.casefold())
                if not path.is_symlink()
                and path.is_file()
                and path.suffix.casefold() in self.ALLOWED_EXTENSIONS
                and not (
                    normalized_family == "yolov5" and self._is_yolov5u_name(path.name)
                )
            )
        return paths

    @staticmethod
    def _is_yolov5u_name(filename: str) -> bool:
        """识别 Ultralytics 新版 anchor-free YOLOv5u 官方权重名。"""
        return bool(
            re.fullmatch(
                r"yolov5(?:n|s|m|l|x)(?:6)?u(?:_\d+)?\.pt",
                Path(str(filename or "")).name.casefold(),
            )
        )

    @staticmethod
    def family_for_algorithm_key(algorithm_key: str) -> str:
        key = str(algorithm_key or "").casefold()
        if "yolov5" in key:
            return "yolov5"
        if "yolov8" in key:
            return "yolov8"
        if "yolo11" in key or "yolov11" in key:
            return "yolo11"
        return ""

    def _asset_path(self, asset_id: str) -> Path:
        relative = Path(str(asset_id or "").replace("\\", "/"))
        if relative.is_absolute() or len(relative.parts) != 2:
            raise ValidationError("模型标识无效")
        root = self.paths.models_dir.resolve()
        target = (root / relative).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ValidationError("模型路径超出模型库目录") from exc
        return target

    def _normalize_family(self, family: str, *, allow_empty: bool = False) -> str:
        value = str(family or "").strip().casefold()
        if allow_empty and not value:
            return ""
        if value not in self.ALLOWED_FAMILIES:
            raise ValidationError(f"不支持的模型系列: {family}")
        return value

    @staticmethod
    def _available_target(target_dir: Path, filename: str) -> Path:
        target = target_dir / filename
        index = 2
        while target.exists():
            target = target_dir / f"{Path(filename).stem}_{index}{Path(filename).suffix}"
            index += 1
        return target

    def _serialize(self, path: Path, family: str) -> dict:
        stat = path.stat()
        relative = path.relative_to(self.paths.models_dir).as_posix()
        return {
            "id": relative,
            "name": path.name,
            "family": family,
            "format": path.suffix.casefold().lstrip("."),
            "path": str(path.resolve()),
            "size_bytes": stat.st_size,
            "size_text": self._format_size(stat.st_size),
            "modified_at": int(stat.st_mtime),
        }

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        size = float(max(size_bytes, 0))
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if size < 1024.0 or unit == "TB":
                return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size_bytes} B"
