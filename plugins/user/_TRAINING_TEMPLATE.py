# -*- coding: utf-8 -*-
"""训练算法插件模板。

本文件可以被软件反射和注册，但必须实现 _train_model() 后才能真正训练。
不要把示例路径或占位 checkpoint 当成真实训练产物返回。
"""
from __future__ import annotations

from pathlib import Path
from typing import Any


PARAMETERS: list[dict[str, Any]] = [
    {
        "name": "model_path",
        "type": "string",
        "label": "模型或预训练权重",
        "default": "",
        "options": [],
        "description": "使用稳定目录或绝对路径；插件注册只复制 .py，不复制模型文件",
        "required": False,
    },
    {
        "name": "epochs",
        "type": "int",
        "label": "训练轮次",
        "default": 100,
        "min": 1,
        "max": 1000,
        "options": [],
        "description": "训练 epoch 数量",
        "required": False,
    },
    {
        "name": "device",
        "type": "string",
        "label": "训练设备",
        "default": "",
        "options": ["", "0", "1", "0,1", "cpu"],
        "description": "支持自动、单显卡、双显卡和 CPU",
        "required": False,
    },
]


# 必须按算法真实输入填写。软件注册时会自动读取并用于数据集筛选和训练前复检。
DATASET_REQUIREMENTS = {
    "modalities": ["image"],
    "label_types": ["detection"],
    "min_samples": 2,
    "min_classes": 1,
    "min_samples_per_class": 1,
    "required_extensions": [".jpg", ".jpeg", ".png"],
    "required_columns": [],
    "required_companion_roles": [],
    "min_complete_groups": 0,
    "allow_unlabeled": False,
    "bbox_required": True,
}


def validate_dataset(summary: dict[str, Any]) -> dict[str, Any]:
    """可选复杂校验；简单条件优先写在 DATASET_REQUIREMENTS。"""
    compatible = int(summary.get("sample_count", 0)) >= 2
    return {"compatible": compatible, "reason": "训练至少需要 2 个有效样本"}


def run(payload: dict[str, Any], context: Any) -> dict[str, Any]:
    """训练入口：准备数据、调用模型、返回真实 checkpoint。"""
    parameters = payload.get("parameters", {}) or {}
    samples = payload.get("input", {}).get("samples", []) or []
    output_dir = Path(payload.get("output", {}).get("output_dir") or ".")
    output_dir.mkdir(parents=True, exist_ok=True)

    if not samples:
        return {"ok": False, "error_code": "NO_INPUT_SAMPLES", "message": "无输入样本"}
    if context.is_cancel_requested():
        return {"ok": False, "error_code": "CANCELLED", "message": "任务已取消"}

    try:
        checkpoint_path, metadata = _train_model(
            samples=samples,
            parameters=parameters,
            output_dir=output_dir,
            context=context,
        )
    except NotImplementedError as exc:
        return {"ok": False, "error_code": "PLUGIN_NOT_IMPLEMENTED", "message": str(exc)}
    except Exception as exc:
        return {"ok": False, "error_code": "TRAINING_FAILED", "message": str(exc)}

    checkpoint = Path(checkpoint_path)
    if not checkpoint.is_file():
        return {
            "ok": False,
            "error_code": "CHECKPOINT_NOT_FOUND",
            "message": f"训练结束但 checkpoint 不存在: {checkpoint}",
        }

    context.set_progress(100.0, "训练完成")
    return {
        "ok": True,
        "outputs": [{
            "artifact_path": str(checkpoint),
            "metadata": dict(metadata or {}),
        }],
        "logs": [],
    }


def _train_model(
    *,
    samples: list[dict[str, Any]],
    parameters: dict[str, Any],
    output_dir: Path,
    context: Any,
) -> tuple[Path, dict[str, Any]]:
    """必须替换为真实训练实现。

    实现要求：
    1. 从 samples[*].path/sample_path 和 samples[*].labels 读取数据及标签。
    2. 如模型需要特定格式，在 output_dir 内生成转换后的训练数据。
    3. 周期性调用 context.is_cancel_requested() 和 context.set_progress()。
    4. 默认关闭 Comet、WandB、ClearML 等在线平台，除非用户显式启用。
    5. 返回真实存在的 checkpoint 路径和可序列化 metadata。
    """
    raise NotImplementedError("请先实现 _train_model()，再注册此训练插件")
