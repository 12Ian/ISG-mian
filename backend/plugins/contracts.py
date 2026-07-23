from __future__ import annotations

import ast
from pathlib import Path
from typing import Any, Iterable

from .reflector import _normalize_parameters, validate_parameters


class PluginContractError(ValueError):
    pass


def load_plugin_parameters(root: Path, module_path: str) -> list[dict[str, Any]]:
    script_path = Path(root).joinpath(*module_path.split(".")).with_suffix(".py")
    if not script_path.is_file():
        raise PluginContractError(f"插件参数文件不存在: {script_path}")

    try:
        tree = ast.parse(script_path.read_text(encoding="utf-8-sig"), filename=str(script_path))
    except (OSError, SyntaxError) as exc:
        raise PluginContractError(f"无法解析插件参数文件 {script_path}: {exc}") from exc

    raw_parameters = _find_parameter_literal(tree, script_path)
    valid, error = validate_parameters(raw_parameters)
    if not valid:
        raise PluginContractError(f"{module_path}.PARAMETERS 格式错误: {error}")

    parameters = _normalize_parameters(raw_parameters)
    _validate_contract_values(module_path, parameters)
    return parameters


def synchronize_default_algorithm_contracts(
    algorithms: Iterable[dict[str, Any]],
    root: Path,
) -> tuple[dict[str, Any], ...]:
    synchronized = []
    for algorithm in algorithms:
        item = dict(algorithm)
        item["parameters"] = load_plugin_parameters(root, item["module_path"])
        synchronized.append(item)
    return tuple(synchronized)


def _find_parameter_literal(tree: ast.Module, script_path: Path) -> list[dict[str, Any]]:
    for node in tree.body:
        value = None
        targets = []
        if isinstance(node, ast.Assign):
            value = node.value
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            value = node.value
            targets = [node.target]
        if not any(isinstance(target, ast.Name) and target.id == "PARAMETERS" for target in targets):
            continue
        try:
            parameters = ast.literal_eval(value)
        except (TypeError, ValueError) as exc:
            raise PluginContractError(f"{script_path} 中的 PARAMETERS 必须是静态字面量") from exc
        return parameters
    raise PluginContractError(f"{script_path} 中未找到 PARAMETERS")


def _validate_contract_values(module_path: str, parameters: list[dict[str, Any]]) -> None:
    names = [parameter["name"] for parameter in parameters]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise PluginContractError(f"{module_path}.PARAMETERS 包含重复参数: {', '.join(duplicates)}")

    for parameter in parameters:
        if parameter["type"] == "select" and parameter["default"] not in parameter["options"]:
            raise PluginContractError(f"{module_path}.{parameter['name']} 的默认值不在选项中")
        if parameter["type"] == "bool" and not isinstance(parameter["default"], bool):
            raise PluginContractError(f"{module_path}.{parameter['name']} 的默认值不是布尔值")
        if parameter["type"] not in {"int", "float"}:
            continue
        default = parameter["default"]
        min_value = parameter["min"]
        max_value = parameter["max"]
        if not isinstance(default, (int, float)) or isinstance(default, bool):
            raise PluginContractError(f"{module_path}.{parameter['name']} 的默认值不是数值")
        if min_value is not None and default < min_value:
            raise PluginContractError(f"{module_path}.{parameter['name']} 的默认值小于最小值")
        if max_value is not None and default > max_value:
            raise PluginContractError(f"{module_path}.{parameter['name']} 的默认值大于最大值")
        if min_value is not None and max_value is not None and min_value > max_value:
            raise PluginContractError(f"{module_path}.{parameter['name']} 的最小值大于最大值")
