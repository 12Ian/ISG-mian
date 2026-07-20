from __future__ import annotations

from typing import Any


ALLOWED_KEYS = {
    "modalities",
    "label_types",
    "min_samples",
    "min_classes",
    "min_samples_per_class",
    "required_extensions",
    "required_columns",
    "required_companion_roles",
    "min_complete_groups",
    "allow_unlabeled",
    "bbox_required",
}
ALLOWED_MODALITIES = {"image", "text", "audio", "tabular", "multimodal", "other"}
ALLOWED_LABEL_TYPES = {"classification", "detection", "segmentation", "none"}
ALLOWED_COMPANION_ROLES = {"image", "mask", "radar", "annotation", "auxiliary"}


def normalize_dataset_requirements(value: Any) -> dict:
    if value in (None, {}):
        return {}
    if not isinstance(value, dict):
        raise ValueError("DATASET_REQUIREMENTS 必须是 dict")
    unknown = set(value) - ALLOWED_KEYS
    if unknown:
        raise ValueError(f"DATASET_REQUIREMENTS 包含未知字段: {sorted(unknown)}")

    result = {}
    for key in ("modalities", "label_types", "required_extensions", "required_columns", "required_companion_roles"):
        if key not in value:
            continue
        raw = value.get(key)
        items = [raw] if isinstance(raw, str) else list(raw or [])
        result[key] = [str(item).strip() for item in items if str(item).strip()]

    for key in ("min_samples", "min_classes", "min_samples_per_class", "min_complete_groups"):
        if key in value:
            number = int(value.get(key) or 0)
            if number < 0:
                raise ValueError(f"{key} 不能小于 0")
            result[key] = number

    for key in ("allow_unlabeled", "bbox_required"):
        if key in value:
            result[key] = bool(value.get(key))

    modalities = set(result.get("modalities", []))
    if modalities - ALLOWED_MODALITIES:
        raise ValueError(f"不支持的数据模态: {sorted(modalities - ALLOWED_MODALITIES)}")
    label_types = set(result.get("label_types", []))
    if label_types - ALLOWED_LABEL_TYPES:
        raise ValueError(f"不支持的标签类型: {sorted(label_types - ALLOWED_LABEL_TYPES)}")
    roles = set(result.get("required_companion_roles", []))
    if roles - ALLOWED_COMPANION_ROLES:
        raise ValueError(f"不支持的多模态角色: {sorted(roles - ALLOWED_COMPANION_ROLES)}")

    if "required_extensions" in result:
        result["required_extensions"] = [
            extension.casefold() if extension.startswith(".") else f".{extension.casefold()}"
            for extension in result["required_extensions"]
        ]
    return result

