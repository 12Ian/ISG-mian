import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import yaml
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.repositories.dataset_repository import DatasetRepository
from backend.repositories.log_repository import LogRepository
from backend.services.dataset_service import DatasetService
from core.data_management.detection_annotations import (
    AnnotationFormatError,
    sanitize_normalized_bbox,
    scan_detection_dataset,
)
from plugins.evaluation.yolov5_evaluator import _load_training_class_names
from plugins.training.yolov5_detector import (
    _build_conversion_report,
    _collect_class_names,
    _split_train_val_test,
    _write_yolo_split,
    _yolov5_weights_incompatibility,
)
from core.hardware_adapter import resolve_yolo_device


class DetectionAnnotationScanTests(unittest.TestCase):
    def test_clamps_tiny_normalized_bbox_rounding_overflow(self):
        bbox = sanitize_normalized_bbox([0.968047, 0.391328, 0.063922, 0.083812])

        self.assertIsNotNone(bbox)
        self.assertAlmostEqual(bbox[0] + bbox[2] / 2.0, 1.0)
        self.assertIsNone(sanitize_normalized_bbox([0.968047, 0.391328, 0.08, 0.083812]))

    def test_scans_yolo_with_global_names(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "images" / "train" / "mixed.jpg"
            _write_image(image_path)
            label_path = root / "labels" / "train" / "mixed.txt"
            label_path.parent.mkdir(parents=True)
            label_path.write_text("0 0.25 0.40 0.30 0.40\n1 0.70 0.50 0.20 0.30\n", encoding="utf-8")
            (root / "data.yaml").write_text("names: [cat, dog]\n", encoding="utf-8")

            result = scan_detection_dataset(root)

            self.assertEqual(result["format"], "yolo")
            self.assertEqual(result["report"]["class_names"], ["cat", "dog"])
            self.assertEqual([item["class_name"] for item in result["records"][0]["labels"]], ["cat", "dog"])
            self.assertEqual(result["records"][0]["metadata"]["split"], "train")

    def test_scans_coco_and_normalizes_bbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "images" / "sample.jpg"
            _write_image(image_path)
            payload = {
                "images": [{"id": 1, "file_name": "images/sample.jpg", "width": 100, "height": 100}],
                "categories": [{"id": 7, "name": "cat"}],
                "annotations": [{"id": 1, "image_id": 1, "category_id": 7, "bbox": [10, 20, 30, 40]}],
            }
            (root / "annotations.json").write_text(json.dumps(payload), encoding="utf-8")

            result = scan_detection_dataset(root)

            self.assertEqual(result["format"], "coco")
            self.assertEqual(result["records"][0]["labels"][0]["bbox"], [0.25, 0.4, 0.3, 0.4])

    def test_scans_pascal_voc_and_normalizes_bbox(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_image(root / "JPEGImages" / "sample.jpg")
            xml_path = root / "Annotations" / "sample.xml"
            xml_path.parent.mkdir(parents=True)
            xml_path.write_text(
                """<annotation>
                    <filename>sample.jpg</filename>
                    <size><width>100</width><height>100</height></size>
                    <object><name>cat</name><bndbox>
                        <xmin>10</xmin><ymin>20</ymin><xmax>40</xmax><ymax>60</ymax>
                    </bndbox></object>
                </annotation>""",
                encoding="utf-8",
            )

            result = scan_detection_dataset(root)

            self.assertEqual(result["format"], "voc")
            self.assertEqual(result["records"][0]["labels"][0]["bbox"], [0.25, 0.4, 0.3, 0.4])

    def test_scans_labelme_polygon_as_bounding_box(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_image(root / "sample.jpg")
            payload = {
                "imagePath": "sample.jpg",
                "imageWidth": 100,
                "imageHeight": 100,
                "shapes": [{"label": "cat", "shape_type": "polygon", "points": [[10, 20], [40, 20], [40, 60]]}],
            }
            (root / "sample.json").write_text(json.dumps(payload), encoding="utf-8")

            result = scan_detection_dataset(root)

            self.assertEqual(result["format"], "labelme")
            self.assertEqual(result["records"][0]["labels"][0]["bbox"], [0.25, 0.4, 0.3, 0.4])

    def test_rejects_mixed_annotation_formats(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            _write_image(root / "images" / "sample.jpg")
            label_path = root / "labels" / "sample.txt"
            label_path.parent.mkdir(parents=True)
            label_path.write_text("0 0.5 0.5 0.2 0.2\n", encoding="utf-8")
            coco = {
                "images": [{"id": 1, "file_name": "images/sample.jpg", "width": 100, "height": 100}],
                "categories": [{"id": 1, "name": "cat"}],
                "annotations": [],
            }
            (root / "annotations.json").write_text(json.dumps(coco), encoding="utf-8")

            with self.assertRaises(AnnotationFormatError):
                scan_detection_dataset(root)


class YoloPreparationTests(unittest.TestCase):
    def test_rejects_anchor_free_yolov5u_weights_before_training(self):
        message = _yolov5_weights_incompatibility("C:/models/yolov5su.pt")

        self.assertIn("anchor-free YOLOv5u", message)
        self.assertEqual(_yolov5_weights_incompatibility("C:/models/yolov5s.pt"), "")

    def test_project_utils_namespace_exposes_yolov5_helpers(self):
        import utils
        from utils.callbacks import Callbacks

        self.assertTrue(callable(utils.TryExcept))
        self.assertTrue(callable(utils.threaded))
        self.assertEqual(Callbacks.__module__, "utils.callbacks")

    def test_invalid_cuda_index_falls_back_to_gpu_zero(self):
        class FakeCuda:
            @staticmethod
            def is_available():
                return True

            @staticmethod
            def device_count():
                return 1

        device, warning = resolve_yolo_device("1.0", SimpleNamespace(cuda=FakeCuda()))

        self.assertEqual(device, "0")
        self.assertIn("GPU 0", warning)
        self.assertEqual(resolve_yolo_device("0.0", SimpleNamespace(cuda=FakeCuda())), ("0", ""))

    def test_device_selection_adapts_to_available_gpu_count(self):
        class FakeCuda:
            count = 0

            @classmethod
            def is_available(cls):
                return cls.count > 0

            @classmethod
            def device_count(cls):
                return cls.count

        torch_module = SimpleNamespace(cuda=FakeCuda())

        FakeCuda.count = 2
        self.assertEqual(resolve_yolo_device("0", torch_module), ("0", ""))
        self.assertEqual(resolve_yolo_device("1", torch_module), ("1", ""))
        self.assertEqual(resolve_yolo_device("0,1", torch_module), ("0,1", ""))

        FakeCuda.count = 1
        self.assertEqual(resolve_yolo_device("0", torch_module), ("0", ""))
        self.assertEqual(resolve_yolo_device("1", torch_module)[0], "0")
        self.assertEqual(resolve_yolo_device("0,1", torch_module)[0], "0")

        FakeCuda.count = 0
        self.assertEqual(resolve_yolo_device("0", torch_module)[0], "cpu")
        self.assertEqual(resolve_yolo_device("1", torch_module)[0], "cpu")
        self.assertEqual(resolve_yolo_device("0,1", torch_module)[0], "cpu")

    def test_uses_one_global_class_mapping_for_every_image(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            samples = []
            labels_by_image = [
                [_label("cat"), _label("dog")],
                [_label("dog")],
                [_label("dog"), _label("cat")],
            ]
            for index, labels in enumerate(labels_by_image):
                image_path = root / f"source_{index}.jpg"
                _write_image(image_path)
                samples.append({"name": image_path.name, "file_path": str(image_path), "_bboxes": labels})

            class_names = _collect_class_names(samples)
            class_to_id = {name: index for index, name in enumerate(class_names)}
            _write_yolo_split(samples, root / "out" / "images", root / "out" / "labels", class_to_id)

            self.assertEqual(class_names, ["cat", "dog"])
            self.assertTrue((root / "out" / "labels" / "source_1.txt").read_text().startswith("1 "))
            third_ids = [line.split()[0] for line in (root / "out" / "labels" / "source_2.txt").read_text().splitlines()]
            self.assertEqual(third_ids, ["1", "0"])

    def test_multilabel_split_is_deterministic_and_has_no_duplicates(self):
        samples = [
            {"name": f"sample_{index}.jpg", "_bboxes": [_label("cat"), *([_label("dog")] if index % 2 else [])]}
            for index in range(12)
        ]

        first = _split_train_val_test(samples, 0.7, 0.15)
        second = _split_train_val_test(samples, 0.7, 0.15)

        self.assertEqual([[item["name"] for item in split] for split in first], [[item["name"] for item in split] for split in second])
        all_names = [item["name"] for split in first for item in split]
        self.assertEqual(len(all_names), len(samples))
        self.assertEqual(len(set(all_names)), len(samples))

    def test_multilabel_split_balances_every_class_box_ratio(self):
        samples = []
        for index in range(5):
            samples.append({"name": f"cat_{index}.jpg", "_bboxes": [_label("cat")]})
            samples.append({"name": f"dog_{index}.jpg", "_bboxes": [_label("dog")]})
        for index in range(10):
            samples.append({
                "name": f"mixed_{index}.jpg",
                "_bboxes": [_label("cat"), _label("dog")],
            })

        train, val, test = _split_train_val_test(samples, 0.6, 0.2)
        class_to_id = {"cat": 0, "dog": 1}
        report = _build_conversion_report(
            samples, class_to_id, train, val, test, 0.6, 0.2
        )

        self.assertEqual([len(train), len(val), len(test)], [12, 4, 4])
        for class_name in class_to_id:
            distribution = report["label_split_distribution"][class_name]
            self.assertEqual(distribution["target_counts"], {"train": 9, "val": 3, "test": 3})
            self.assertEqual(distribution["actual_counts"], {"train": 9, "val": 3, "test": 3})
        self.assertEqual(report["max_label_ratio_error"], 0.0)
        self.assertEqual(report["max_label_count_deviation"], 0)

    def test_evaluator_reads_training_class_order(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            checkpoint = output_dir / "runs" / "train" / "weights" / "best.pt"
            checkpoint.parent.mkdir(parents=True)
            checkpoint.write_bytes(b"test")
            (output_dir / "data.yaml").write_text(
                yaml.safe_dump({"names": ["cat", "dog"]}, sort_keys=False), encoding="utf-8"
            )

            self.assertEqual(_load_training_class_names(checkpoint), ["cat", "dog"])


class DatasetServiceDetectionImportTests(unittest.TestCase):
    def test_import_folder_stores_coco_boxes_as_detection_labels(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            _write_image(source / "images" / "sample.jpg")
            coco = {
                "images": [{"id": 1, "file_name": "images/sample.jpg", "width": 100, "height": 100}],
                "categories": [{"id": 1, "name": "cat"}],
                "annotations": [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [10, 20, 30, 40]}],
            }
            (source / "annotations.json").write_text(json.dumps(coco), encoding="utf-8")

            engine = create_engine("sqlite:///:memory:", future=True)
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, future=True)
            repository = DatasetRepository(session_factory)
            service = DatasetService(
                paths=SimpleNamespace(datasets_dir=root / "datasets"),
                session_factory=session_factory,
                dataset_repository=repository,
                log_repository=LogRepository(session_factory),
            )
            dataset_id = service.create_dataset("coco-test", "image")["data"]["id"]

            result = service.import_folder(dataset_id, str(source), include_subfolders=True)

            self.assertEqual(result["data"]["annotation_report"]["format"], "coco")
            with session_factory() as session:
                samples = repository.get_all_samples(session, dataset_id)
                self.assertEqual(len(samples), 1)
                self.assertEqual(samples[0].labels_json[0]["class_name"], "cat")
                self.assertEqual(samples[0].labels_json[0]["bbox"], [0.25, 0.4, 0.3, 0.4])


def _write_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), color=(20, 30, 40)).save(path)


def _label(class_name: str):
    return {
        "type": "detection",
        "class_name": class_name,
        "bbox": [0.5, 0.5, 0.2, 0.2],
        "bbox_format": "cxcywh_normalized",
    }


if __name__ == "__main__":
    unittest.main()
