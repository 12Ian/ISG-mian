# -*- coding: utf-8 -*-
"""读取插件脚本中的 PARAMETERS。"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import Any

from core.data_management.dataset_requirements import normalize_dataset_requirements


_ALLOWED_TYPES = {"string", "int", "float", "bool", "select"}


def _setup_package_context(module, path: Path) -> None:
    """给带相对导入的插件补上包名。"""
    try:
        content = path.read_text(encoding="utf-8")
    except Exception:
        return

    has_relative_import = any(
        line.strip().startswith(("from .", "from .."))
        for line in content.split("\n")
    )
    if not has_relative_import:
        return

    parts = list(path.parts)
    try:
        plugins_idx = parts.index("plugins")
    except ValueError:
        return

    package_parts = parts[plugins_idx:-1]
    if package_parts:
        module.__package__ = ".".join(package_parts)


def reflect_parameters(script_path: Path) -> dict[str, Any]:
    """加载脚本并返回规范化后的参数列表。"""
    path = Path(script_path).resolve()
    if not path.exists():
        return {"ok": False, "error": f"文件不存在: {path}"}
    if path.suffix.lower() != ".py":
        return {"ok": False, "error": "仅支持 .py 文件"}

    module_name = f"_isg_reflect_{path.stem}"

    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return {"ok": False, "error": f"无法解析模块: {path}"}

        module = importlib.util.module_from_spec(spec)

        _setup_package_context(module, path)

        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        parameters = getattr(module, "PARAMETERS", None)
        if parameters is None:
            return {"ok": False, "error": "脚本中未找到 PARAMETERS 变量。请在 .py 文件中声明 PARAMETERS = [...]"}

        valid, error = validate_parameters(parameters)
        if not valid:
            return {"ok": False, "error": f"PARAMETERS 格式错误: {error}"}

        normalized = _normalize_parameters(parameters)
        try:
            dataset_requirements = normalize_dataset_requirements(
                getattr(module, "DATASET_REQUIREMENTS", {})
            )
        except ValueError as exc:
            return {"ok": False, "error": f"DATASET_REQUIREMENTS 格式错误: {exc}"}
        return {
            "ok": True,
            "parameters": normalized,
            "dataset_requirements": dataset_requirements,
            "custom_dataset_validator": callable(getattr(module, "validate_dataset", None)),
        }

    except Exception as exc:
        return {"ok": False, "error": f"脚本加载失败: {exc}"}
    finally:
        sys.modules.pop(module_name, None)


def validate_parameters(params: Any) -> tuple[bool, str]:
    if not isinstance(params, list):
        return False, "PARAMETERS 必须是 list 类型"
    names: set[str] = set()
    for i, item in enumerate(params):
        if not isinstance(item, dict):
            return False, f"第 {i} 项不是 dict 类型"
        name = str(item.get("name", "")).strip()
        if not name:
            return False, f"第 {i} 项参数名不能为空"
        if name in names:
            return False, f"参数名重复: {name}"
        names.add(name)
        if "type" not in item:
            return False, f"第 {i} 项缺少必填字段: type"
        if "default" not in item and "default_value" not in item:
            return False, f"第 {i} 项缺少必填字段: default"
        ptype = str(item.get("type", "")).lower()
        if ptype not in _ALLOWED_TYPES:
            return False, f"第 {i} 项 type='{ptype}' 不合法，允许: {_ALLOWED_TYPES}"
        default = item.get("default", item.get("default_value"))
        if ptype == "select":
            options = item.get("options", item.get("options_json", []))
            if not isinstance(options, list) or len(options) == 0:
                return False, f"第 {i} 项 type='select' 但 options 为空或非列表"
            if not any(default == option or str(default) == str(option) for option in options):
                return False, f"第 {i} 项默认值不在 options 中"
        if ptype == "bool" and not isinstance(default, bool):
            return False, f"第 {i} 项默认值不是 bool 类型"
        if ptype in ("int", "float"):
            if isinstance(default, bool) or not isinstance(default, (int, float)):
                return False, f"第 {i} 项默认值不是数值类型"
            if ptype == "int" and not float(default).is_integer():
                return False, f"第 {i} 项 int 默认值必须是整数"
            min_value = item.get("min", item.get("min_value"))
            max_value = item.get("max", item.get("max_value"))
            for key, value in (("min", min_value), ("max", max_value)):
                if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))):
                    return False, f"第 {i} 项 {key}={value} 不是数值类型"
            if min_value is not None and max_value is not None and min_value > max_value:
                return False, f"第 {i} 项 min 不能大于 max"
            if min_value is not None and default < min_value:
                return False, f"第 {i} 项默认值小于 min"
            if max_value is not None and default > max_value:
                return False, f"第 {i} 项默认值大于 max"
            if ptype == "int" and min_value is not None and max_value is not None:
                if math.ceil(min_value) > math.floor(max_value):
                    return False, f"第 {i} 项范围内没有可用整数"
    return True, ""


def _normalize_parameters(params: list[dict]) -> list[dict]:
    result = []
    for item in params:
        normalized = {
            "name": str(item.get("name", "")),
            "type": str(item.get("type", "string")),
            "label": str(item.get("label", item.get("name", ""))),
            "default": item.get("default", ""),
            "min": item.get("min"),
            "max": item.get("max"),
            "options": list(item.get("options") or []),
            "description": str(item.get("description", "")),
            "required": bool(item.get("required", False)),
        }
        result.append(normalized)
    return result
