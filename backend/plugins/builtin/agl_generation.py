from __future__ import annotations

from pathlib import Path

from core.sample_generation.detection_label_transform import (
    DetectionLabelTransformError,
    has_detection_labels,
    transform_affine_labels,
    transform_remap_labels,
)

from ...integrations import get_agl_algorithm_spec, run_agl_algorithm


def run(payload: dict, context) -> dict:
    algorithm_key = (payload.get("algorithm_key") or "").strip()
    if not algorithm_key:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "message": "algorithm_key is required."}

    try:
        spec = get_agl_algorithm_spec(algorithm_key)
    except ValueError as exc:
        return {"ok": False, "error_code": "UNSUPPORTED_ALGORITHM", "message": str(exc)}

    samples = list(payload.get("input", {}).get("samples", []))
    if not samples:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "message": "At least one input sample is required."}

    target_count = int(payload.get("target_count") or payload.get("parameters", {}).get("target_count") or len(samples))
    if target_count <= 0:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "message": "target_count must be greater than zero."}

    output_dir_value = payload.get("output", {}).get("output_dir") or getattr(context, "output_dir", "")
    if not output_dir_value:
        return {"ok": False, "error_code": "VALIDATION_ERROR", "message": "output_dir is required."}

    output_dir = Path(output_dir_value).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    outputs: list[dict] = []
    parameters = _normalize_agl_parameters(spec.key, payload.get("parameters", {}) or {})
    contains_detection_labels = any(
        has_detection_labels(sample.get("labels") or sample.get("labels_json") or [])
        for sample in samples
    )
    if spec.key == "agl.image.transformer" and contains_detection_labels:
        return {
            "ok": False,
            "error_code": "UNSUPPORTED_LABEL_TRANSFORM",
            "message": "AGL Transformer 会随机交换图像块，无法生成可靠的目标检测框。",
        }
    if spec.key == "agl.image.deformation" and contains_detection_labels:
        parameters["_capture_label_transform"] = True
    context.log("info", "agl-generation-start", {"algorithm_key": algorithm_key, "target_count": target_count})

    for index in range(target_count):
        if context.is_cancel_requested():
            context.log("warning", "agl-generation-cancelled", {"generated_count": len(outputs)})
            return {"ok": False, "error_code": "CANCELLED", "message": "Generation cancelled by request."}

        sample = samples[index % len(samples)]
        generated_result = run_agl_algorithm(
            algorithm_key=algorithm_key,
            sample_path=sample["path"],
            parameters=parameters,
            output_dir=str(output_dir),
            index=index + 1,
        )
        if not generated_result:
            return {
                "ok": False,
                "error_code": "ALGORITHM_RUNTIME_ERROR",
                "message": f"AGL algorithm failed for key {spec.key}.",
            }

        generated_file = Path(generated_result["output_path"])
        source_labels = sample.get("labels") or sample.get("labels_json") or []
        try:
            labels, label_policy = _resolve_agl_labels(
                spec.key,
                source_labels,
                generated_result.get("transform") or {},
            )
        except DetectionLabelTransformError as exc:
            return {
                "ok": False,
                "error_code": "LABEL_TRANSFORM_ERROR",
                "message": str(exc),
            }
        outputs.append(
            {
                "source_sample_id": sample["id"],
                "output_path": str(generated_file),
                "relative_path": generated_file.name,
                "labels": labels,
                "label_policy": label_policy,
                "metadata": {
                    "algorithm_key": spec.key,
                    "algorithm_name": spec.name,
                    "modality": spec.modality,
                    "label_transform": (generated_result.get("transform") or {}).get("label_transform", "inherit"),
                },
            }
        )
        context.set_progress(((index + 1) / target_count) * 100.0, f"Generated {index + 1}/{target_count}")

    context.log("info", "agl-generation-complete", {"generated_count": len(outputs), "algorithm_key": algorithm_key})
    return {"ok": True, "outputs": outputs}


def _resolve_agl_labels(algorithm_key: str, labels, transform: dict) -> tuple[list, str]:
    if not has_detection_labels(labels):
        return list(labels or []), "inherit"
    if algorithm_key in {"agl.image.geometric", "agl.image.gan"}:
        if transform.get("label_transform") != "affine":
            raise DetectionLabelTransformError("AGL 算法改变了目标位置，但没有返回仿射变换矩阵。")
        return (
            transform_affine_labels(
                labels,
                image_width=int(transform["source_width"]),
                image_height=int(transform["source_height"]),
                output_width=int(transform["output_width"]),
                output_height=int(transform["output_height"]),
                matrix=transform["matrix"],
            ),
            "transformed",
        )
    if algorithm_key == "agl.image.deformation":
        if transform.get("label_transform") != "remap":
            raise DetectionLabelTransformError("AGL 形变没有返回像素映射，无法同步检测框。")
        return (
            transform_remap_labels(
                labels,
                image_width=int(transform["source_width"]),
                image_height=int(transform["source_height"]),
                map_x=transform["map_x"],
                map_y=transform["map_y"],
            ),
            "transformed",
        )
    return list(labels or []), "inherit"


def _normalize_agl_parameters(algorithm_key: str, parameters: dict) -> dict:
    normalized = dict(parameters or {})
    mappings = {
        "agl.image.geometric": {
            "rotation_degrees": "旋转角度",
            "scale": "缩放比例",
            "flip_horizontal": "水平翻转",
            "flip_vertical": "垂直翻转",
        },
        "agl.image.deformation": {
            "elastic_strength": "弹性强度",
            "elastic_gaussian_kernel": "弹性高斯核",
            "elastic_sigma": "弹性高斯核",
            "distortion_k1": "畸变系数k1",
            "distortion_k2": "畸变系数k2",
        },
        "agl.image.transformer": {
            "patch_size": "patch大小",
            "mask_ratio": "掩码比例",
        },
    }
    for source_name, target_name in mappings.get(algorithm_key, {}).items():
        if source_name in normalized and target_name not in normalized:
            normalized[target_name] = normalized[source_name]
    return normalized
