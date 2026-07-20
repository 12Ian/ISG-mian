import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np
from PIL import Image

from backend.errors import ValidationError
from backend.plugins.builtin import agl_generation
from backend.services.generation_service import GenerationService
from core.sample_generation.detection_label_transform import (
    transform_affine_labels,
    transform_crop_labels,
    transform_remap_labels,
)
from plugins.generation import (
    copy_augmenter,
    crop_image_augmenter,
    deformation_distortion_image_augmenter,
    geometric_image_augmenter,
)


class DetectionLabelTransformTests(unittest.TestCase):
    def test_all_supported_source_formats_use_the_same_crop_transform(self):
        labels = [
            _label("cat", source_format, [0.25, 0.4, 0.3, 0.4])
            for source_format in ("yolo", "coco", "voc", "labelme")
        ]

        transformed = transform_crop_labels(
            labels,
            image_width=100,
            image_height=100,
            crop_x=0,
            crop_y=0,
            crop_width=50,
            crop_height=100,
        )

        self.assertEqual([item["source_format"] for item in transformed], ["yolo", "coco", "voc", "labelme"])
        for label in transformed:
            self.assert_bbox_close(label["bbox"], [0.5, 0.4, 0.6, 0.4])

    def test_crop_removes_boxes_below_visibility_threshold(self):
        transformed = transform_crop_labels(
            [_label("cat", "yolo", [0.5, 0.5, 0.2, 0.2])],
            image_width=100,
            image_height=100,
            crop_x=0,
            crop_y=0,
            crop_width=42,
            crop_height=100,
        )

        self.assertEqual(transformed, [])

    def test_affine_horizontal_flip_keeps_multiple_classes(self):
        labels = [
            _label("cat", "coco", [0.25, 0.4, 0.3, 0.4]),
            _label("dog", "voc", [0.7, 0.6, 0.2, 0.2]),
        ]
        matrix = np.asarray([[-1.0, 0.0, 100.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]])

        transformed = transform_affine_labels(
            labels,
            image_width=100,
            image_height=100,
            matrix=matrix,
        )

        self.assertEqual([item["class_name"] for item in transformed], ["cat", "dog"])
        self.assert_bbox_close(transformed[0]["bbox"], [0.75, 0.4, 0.3, 0.4])
        self.assert_bbox_close(transformed[1]["bbox"], [0.3, 0.6, 0.2, 0.2])

    def test_affine_rotation_rebuilds_the_bounding_box(self):
        matrix = np.asarray([[0.0, -1.0, 100.0], [1.0, 0.0, 0.0]])

        transformed = transform_affine_labels(
            [_label("cat", "labelme", [0.2, 0.3, 0.2, 0.4])],
            image_width=100,
            image_height=100,
            matrix=matrix,
        )

        self.assert_bbox_close(transformed[0]["bbox"], [0.7, 0.2, 0.4, 0.2])

    def test_affine_clips_a_partially_out_of_bounds_box(self):
        matrix = np.asarray([[1.0, 0.0, 50.0], [0.0, 1.0, 0.0]])

        transformed = transform_affine_labels(
            [_label("dog", "voc", [0.5, 0.5, 0.4, 0.4])],
            image_width=100,
            image_height=100,
            matrix=matrix,
        )

        self.assert_bbox_close(transformed[0]["bbox"], [0.9, 0.5, 0.2, 0.4])

    def test_remap_moves_boxes_using_the_actual_pixel_mapping(self):
        grid_x, grid_y = np.meshgrid(
            np.arange(100, dtype=np.float32),
            np.arange(100, dtype=np.float32),
        )

        transformed = transform_remap_labels(
            [_label("cat", "coco", [0.3, 0.5, 0.2, 0.2])],
            image_width=100,
            image_height=100,
            map_x=grid_x - 10.0,
            map_y=grid_y,
        )

        self.assert_bbox_close(transformed[0]["bbox"], [0.4, 0.5, 0.2, 0.2])

    def assert_bbox_close(self, actual, expected):
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=6)


class GenerationPluginLabelTests(unittest.TestCase):
    def test_copy_augmenter_keeps_image_position_and_inherits_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.png"
            image = np.zeros((100, 100, 3), dtype=np.uint8)
            image[40:60, 10:30] = 160
            Image.fromarray(image).save(source)
            source_labels = [_label("cat", "yolo", [0.2, 0.5, 0.2, 0.2])]

            result = copy_augmenter.run(
                {
                    "algorithm_key": "generation.copy_augmenter",
                    "target_count": 1,
                    "input": {"samples": [{"id": 1, "sample_path": str(source), "labels": source_labels}]},
                    "output": {"output_dir": str(root / "out")},
                },
                _Context(),
            )

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["label_policy"], "inherit")
            self.assertEqual(output["labels"], source_labels)
            generated = np.asarray(Image.open(output["output_path"]).convert("L"))
            ys, xs = np.nonzero(generated > 50)
            self.assertEqual((int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())), (10, 29, 40, 59))

    def test_deformation_transforms_detection_labels_with_remap(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jpg"
            Image.new("RGB", (100, 100), color=(20, 30, 40)).save(source)

            result = deformation_distortion_image_augmenter.run(
                {
                    "algorithm_key": "generation.image.deformation_distortion",
                    "parameters": {"elastic_strength": 0, "distortion_k1": 0.3, "distortion_k2": 0},
                    "target_count": 1,
                    "input": {"samples": [{"id": 1, "sample_path": str(source), "labels": [_label("cat", "coco", [0.2, 0.5, 0.2, 0.2])]}]},
                    "output": {"output_dir": str(root / "out")},
                },
                _Context(),
            )

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["label_policy"], "transformed")
            self.assertEqual(output["metadata"]["label_transform"], "remap")
            self.assertEqual(output["metadata"]["parameters"]["elastic_strength"], 0.0)
            self.assertGreater(output["labels"][0]["bbox"][0], 0.2)
            self.assertLess(output["labels"][0]["bbox"][2], 0.2)

    def test_crop_plugin_returns_transformed_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jpg"
            Image.new("RGB", (100, 100), color=(20, 30, 40)).save(source)
            payload = {
                "algorithm_key": "generation.image.crop",
                "parameters": {"crop_ratio": 0.5, "crop_mode": "center"},
                "target_count": 1,
                "input": {"samples": [{"id": 1, "sample_path": str(source), "labels": [_label("cat", "labelme", [0.5, 0.5, 0.4, 0.4])]}]},
                "output": {"output_dir": str(root / "out")},
            }

            result = crop_image_augmenter.run(payload, _Context())

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["label_policy"], "transformed")
            self.assert_bbox_close(output["labels"][0]["bbox"], [0.5, 0.5, 0.8, 0.8])

    def test_geometric_plugin_flips_labels_with_the_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jpg"
            Image.new("RGB", (100, 100), color=(20, 30, 40)).save(source)
            payload = {
                "algorithm_key": "generation.image.geometric_transform",
                "parameters": {
                    "rotation_degrees": 0,
                    "scale": 1,
                    "translate_x_pct": 0,
                    "translate_y_pct": 0,
                    "flip_horizontal": True,
                    "flip_vertical": False,
                },
                "target_count": 1,
                "input": {"samples": [{"id": 1, "sample_path": str(source), "labels": [_label("cat", "yolo", [0.25, 0.5, 0.2, 0.4])]}]},
                "output": {"output_dir": str(root / "out")},
            }

            result = geometric_image_augmenter.run(payload, _Context())

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["label_policy"], "transformed")
            self.assert_bbox_close(output["labels"][0]["bbox"], [0.75, 0.5, 0.2, 0.4])

    def assert_bbox_close(self, actual, expected):
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=6)


class GenerationServiceLabelPolicyTests(unittest.TestCase):
    def test_transformed_policy_accepts_an_empty_label_list(self):
        labels, policy = GenerationService._resolve_output_labels(
            None,
            {"label_policy": "transformed", "labels": []},
            [_label("cat", "yolo", [0.5, 0.5, 0.2, 0.2])],
        )

        self.assertEqual(labels, [])
        self.assertEqual(policy, "transformed")

    def test_unsupported_policy_rejects_detection_labels(self):
        with self.assertRaises(ValidationError):
            GenerationService._resolve_output_labels(
                None,
                {"label_policy": "unsupported"},
                [_label("cat", "coco", [0.5, 0.5, 0.2, 0.2])],
            )

    def test_pipeline_keeps_labels_for_repeated_source_ids_by_position(self):
        service = object.__new__(GenerationService)
        input_samples = [
            {"id": 1, "labels": [_label("cat", "yolo", [0.2, 0.5, 0.2, 0.2])]},
            {"id": 1, "labels": [_label("cat", "yolo", [0.8, 0.5, 0.2, 0.2])]},
        ]
        outputs = [
            {"source_sample_id": 1, "output_path": "first.jpg"},
            {"source_sample_id": 1, "output_path": "second.jpg"},
        ]

        result = service._outputs_as_pipeline_samples(
            outputs,
            input_samples,
            SimpleNamespace(key="generation.image.color"),
        )

        self.assertEqual(result[0]["labels"][0]["bbox"][0], 0.2)
        self.assertEqual(result[1]["labels"][0]["bbox"][0], 0.8)


class AGLGenerationLabelTests(unittest.TestCase):
    def test_agl_geometric_transforms_labels_and_output_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jpg"
            Image.new("RGB", (100, 100), color=(20, 30, 40)).save(source)

            result = agl_generation.run(
                {
                    "algorithm_key": "agl.image.geometric",
                    "parameters": {
                        "rotation_degrees": 0,
                        "scale": 2,
                        "flip_horizontal": True,
                        "flip_vertical": False,
                    },
                    "target_count": 1,
                    "input": {"samples": [{"id": 1, "path": str(source), "labels": [_label("cat", "yolo", [0.25, 0.5, 0.2, 0.4])]}]},
                    "output": {"output_dir": str(root / "out")},
                },
                _Context(),
            )

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["label_policy"], "transformed")
            self.assert_bbox_close(output["labels"][0]["bbox"], [0.75, 0.5, 0.2, 0.4])
            self.assertEqual(Image.open(output["output_path"]).size, (200, 200))

    def test_agl_deformation_uses_returned_remap_for_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source.jpg"
            Image.new("RGB", (100, 100), color=(20, 30, 40)).save(source)

            result = agl_generation.run(
                {
                    "algorithm_key": "agl.image.deformation",
                    "parameters": {"elastic_strength": 0, "distortion_k1": 0.3, "distortion_k2": 0},
                    "target_count": 1,
                    "input": {"samples": [{"id": 1, "path": str(source), "labels": [_label("dog", "voc", [0.2, 0.5, 0.2, 0.2])]}]},
                    "output": {"output_dir": str(root / "out")},
                },
                _Context(),
            )

            self.assertTrue(result["ok"])
            output = result["outputs"][0]
            self.assertEqual(output["metadata"]["label_transform"], "remap")
            self.assertGreater(output["labels"][0]["bbox"][0], 0.2)
            self.assertLess(output["labels"][0]["bbox"][2], 0.2)

    def test_agl_gan_uses_affine_metadata_for_detection_labels(self):
        labels, policy = agl_generation._resolve_agl_labels(
            "agl.image.gan",
            [_label("cat", "labelme", [0.25, 0.5, 0.2, 0.4])],
            {
                "label_transform": "affine",
                "matrix": np.asarray([[-1.0, 0.0, 100.0], [0.0, 1.0, 0.0]]),
                "source_width": 100,
                "source_height": 100,
                "output_width": 100,
                "output_height": 100,
            },
        )

        self.assertEqual(policy, "transformed")
        self.assert_bbox_close(labels[0]["bbox"], [0.75, 0.5, 0.2, 0.4])

    def test_agl_transformer_rejects_detection_labels(self):
        result = agl_generation.run(
            {
                "algorithm_key": "agl.image.transformer",
                "target_count": 1,
                "input": {"samples": [{"id": 1, "path": "unused.jpg", "labels": [_label("cat", "yolo", [0.5, 0.5, 0.2, 0.2])]}]},
                "output": {"output_dir": tempfile.gettempdir()},
            },
            _Context(),
        )

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "UNSUPPORTED_LABEL_TRANSFORM")

    def assert_bbox_close(self, actual, expected):
        for actual_value, expected_value in zip(actual, expected):
            self.assertAlmostEqual(actual_value, expected_value, places=6)


class _Context:
    def is_cancel_requested(self):
        return False

    def set_progress(self, *_args, **_kwargs):
        return None

    def log(self, *_args, **_kwargs):
        return None


def _label(class_name, source_format, bbox):
    return {
        "type": "detection",
        "class_name": class_name,
        "bbox": list(bbox),
        "bbox_format": "cxcywh_normalized",
        "source_format": source_format,
    }


if __name__ == "__main__":
    unittest.main()
