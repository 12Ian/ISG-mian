from __future__ import annotations

from pathlib import Path
from pkgutil import extend_path

from plugins.detection.yolov5_core.utils import TryExcept, emojis, threaded


# 项目工具与内置 YOLOv5 都使用顶层 utils 名称，合并搜索路径避免互相遮蔽。
__path__ = extend_path(__path__, __name__)
_YOLOV5_UTILS = Path(__file__).resolve().parent.parent / "plugins" / "detection" / "yolov5_core" / "utils"
if _YOLOV5_UTILS.is_dir() and str(_YOLOV5_UTILS) not in __path__:
    __path__.append(str(_YOLOV5_UTILS))

__all__ = ["TryExcept", "emojis", "threaded"]
