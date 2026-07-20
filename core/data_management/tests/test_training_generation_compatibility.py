from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.repositories import DatasetRepository, LogRepository
from backend.services.dataset_service import DatasetService
from backend.services.generation_service import GenerationService
from backend.services.training_service import TrainingService
from backend.services.training_compatibility import analyze_training_compatibility
from backend.storage import FileIndexer
from backend.plugins.reflector import reflect_parameters
from core.data_management.dataset_requirements import normalize_dataset_requirements
from core.data_management.multimodal_association import (
    multimodal_group_id,
    sample_role,
)
from plugins.training.multimodal_fusion_detector import _collect_training_pairs
from plugins.training.multimodal_seg import _collect_associated_pairs


class MultimodalAssociationTests(unittest.TestCase):
    def test_generated_group_path_restores_group_and_role(self):
        path = "groups/case_01__generated_9_000001/mask/case_01.png"
        sample = {"relative_path": path, "metadata": {}}

        self.assertEqual(multimodal_group_id(path), "case_01__generated_9_000001")
        self.assertEqual(sample_role(sample), "mask")

    def test_fusion_uses_all_labels_json_boxes_and_global_classes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "images" / "case.jpg"
            radar_path = root / "radar" / "case.npz"
            _write_image(image_path)
            radar_path.parent.mkdir(parents=True)
            radar_path.write_bytes(b"npz")
            metadata_image = {"multimodal_group_id": "case", "multimodal_role": "image"}
            metadata_radar = {"multimodal_group_id": "case", "multimodal_role": "radar"}
            samples = [
                {
                    "file_path": str(image_path),
                    "relative_path": "images/case.jpg",
                    "metadata": metadata_image,
                    "labels": [_label("dog", 0.3), _label("cat", 0.7)],
                },
                {
                    "file_path": str(radar_path),
                    "relative_path": "radar/case.npz",
                    "metadata": metadata_radar,
                    "labels": [],
                },
            ]

            pairs, class_names = _collect_training_pairs(samples, str(root))

            self.assertEqual(class_names, ["cat", "dog"])
            self.assertEqual(len(pairs), 1)
            self.assertEqual(len(pairs[0]["labels"]), 2)
            self.assertEqual(
                [item["class_id"] for item in pairs[0]["labels"]],
                [1, 0],
            )
            self.assertEqual(pairs[0]["radar"], str(radar_path))

    def test_segmentation_pairs_by_group_without_fixed_directories(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            image_path = root / "generated_rgb.jpg"
            mask_path = root / "original_mask.png"
            radar_path = root / "radar_data.npz"
            _write_image(image_path)
            _write_image(mask_path)
            radar_path.write_bytes(b"npz")
            samples = [
                _sample_dict(image_path, "image"),
                _sample_dict(mask_path, "mask"),
                _sample_dict(radar_path, "radar"),
            ]

            pairs = _collect_associated_pairs(samples)

            self.assertEqual(len(pairs), 1)
            self.assertEqual(pairs[0]["img"], str(image_path))
            self.assertEqual(pairs[0]["seg"], str(mask_path))
            self.assertEqual(pairs[0]["radar"], str(radar_path))


class TrainingCompatibilityTests(unittest.TestCase):
    def test_custom_algorithm_uses_declared_detection_requirements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            samples = []
            for index in range(6):
                image_path = root / f"{index}.jpg"
                _write_image(image_path)
                samples.append(_sample_model(image_path, "image", str(index), [_label("cat" if index < 3 else "dog", 0.5)]))
            algorithm = SimpleNamespace(
                key="training.custom.any_key",
                modality="multimodal",
                validation_rules_json={
                    "dataset_requirements": {
                        "modalities": ["image"],
                        "label_types": ["detection"],
                        "min_samples": 6,
                        "min_classes": 2,
                        "min_samples_per_class": 3,
                        "bbox_required": True,
                        "allow_unlabeled": False,
                    }
                },
            )

            result = analyze_training_compatibility(
                SimpleNamespace(modality="image"), samples, algorithm
            )

            self.assertTrue(result["compatible"])

    def test_custom_algorithm_rejects_wrong_label_type(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            _write_image(image_path)
            algorithm = SimpleNamespace(
                key="training.custom.classifier",
                modality="image",
                validation_rules_json={
                    "dataset_requirements": {
                        "modalities": ["image"],
                        "label_types": ["classification"],
                        "min_samples": 1,
                    }
                },
            )

            result = analyze_training_compatibility(
                SimpleNamespace(modality="image"),
                [_sample_model(image_path, "image", "sample", [_label("ship", 0.5)])],
                algorithm,
            )

            self.assertFalse(result["compatible"])

    def test_detection_labels_do_not_enable_classification_algorithms(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            image_path = Path(temp_dir) / "sample.jpg"
            _write_image(image_path)
            samples = [_sample_model(image_path, "image", "sample", [_label("ship", 0.5)]) for _ in range(10)]
            dataset = SimpleNamespace(modality="image")

            ship = analyze_training_compatibility(
                dataset,
                samples,
                SimpleNamespace(key="training.ship_classifier", modality="image"),
            )
            sonar = analyze_training_compatibility(
                dataset,
                samples,
                SimpleNamespace(key="training.image.sonar_oltr_classifier", modality="image"),
            )

            self.assertFalse(ship["compatible"])
            self.assertFalse(sonar["compatible"])

    def test_fusion_requires_image_box_and_radar_groups(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            samples = []
            for index in range(10):
                image_path = root / f"{index}.jpg"
                radar_path = root / f"{index}.npz"
                _write_image(image_path)
                radar_path.write_bytes(b"npz")
                samples.extend(
                    [
                        _sample_model(image_path, "image", str(index), [_label("ship", 0.5)]),
                        _sample_model(radar_path, "radar", str(index), []),
                    ]
                )
            result = analyze_training_compatibility(
                SimpleNamespace(modality="multimodal"),
                samples,
                SimpleNamespace(key="training.multimodal.fusion_detector", modality="multimodal"),
            )
            self.assertTrue(result["compatible"])


class MultimodalImportTests(unittest.TestCase):
    def test_import_keeps_detection_image_mask_and_radar_in_one_dataset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "source"
            image_path = source / "images" / "case.jpg"
            mask_path = source / "semantic" / "SegmentationClass" / "case.png"
            radar_path = source / "radar" / "VOCradar320" / "case.npz"
            _write_image(image_path)
            _write_image(mask_path)
            radar_path.parent.mkdir(parents=True)
            radar_path.write_bytes(b"npz")
            coco = {
                "images": [{"id": 1, "file_name": "images/case.jpg", "width": 100, "height": 100}],
                "categories": [{"id": 1, "name": "ship"}],
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
            dataset_id = service.create_dataset("multi-test", "multimodal")["data"]["id"]

            service.import_folder(dataset_id, str(source), include_subfolders=True)

            with session_factory() as session:
                samples = repository.get_all_samples(session, dataset_id)
                roles = {sample.metadata_json.get("multimodal_role") for sample in samples}
                image_sample = next(sample for sample in samples if sample.metadata_json.get("multimodal_role") == "image")
                self.assertTrue({"image", "mask", "radar"}.issubset(roles))
                self.assertEqual(image_sample.labels_json[0]["class_name"], "ship")


class DatasetRequirementReflectionTests(unittest.TestCase):
    def test_reflector_reads_dataset_requirements(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            script = Path(temp_dir) / "custom_training.py"
            script.write_text(
                "PARAMETERS = [{'name': 'epochs', 'type': 'int', 'default': 2}]\n"
                "DATASET_REQUIREMENTS = {\n"
                "    'modalities': ['image'],\n"
                "    'label_types': ['detection'],\n"
                "    'min_samples': 5,\n"
                "    'bbox_required': True,\n"
                "}\n"
                "def run(payload, context):\n"
                "    return {'ok': True, 'outputs': []}\n"
                "def validate_dataset(summary):\n"
                "    return {'compatible': summary['sample_count'] >= 5, 'reason': 'custom'}\n",
                encoding="utf-8",
            )

            result = reflect_parameters(script)

            self.assertTrue(result["ok"])
            self.assertEqual(result["dataset_requirements"]["modalities"], ["image"])
            self.assertTrue(result["dataset_requirements"]["bbox_required"])
            self.assertTrue(result["custom_dataset_validator"])

    def test_requirement_schema_rejects_unknown_fields(self):
        with self.assertRaises(ValueError):
            normalize_dataset_requirements({"modalities": ["image"], "unknown": True})

    def test_training_service_runs_custom_dataset_validator(self):
        def run(payload, context):
            return {"ok": True}

        run.__globals__["validate_dataset"] = lambda summary: {
            "compatible": summary["sample_count"] >= 2,
            "reason": "custom check",
        }
        service = SimpleNamespace(
            plugin_runner=SimpleNamespace(load_callable=lambda **kwargs: run)
        )
        algorithm = SimpleNamespace(
            validation_rules_json={"custom_dataset_validator": True},
            module_path="custom.module",
            callable_name="run",
            script_path=None,
        )
        samples = [SimpleNamespace(status="raw", file_path="a.jpg", relative_path="a.jpg", labels_json=[], metadata_json={})]

        result = TrainingService._apply_custom_dataset_validator(
            service,
            SimpleNamespace(id=1, modality="image"),
            samples,
            algorithm,
            {"compatible": True, "reason": "base"},
        )

        self.assertFalse(result["compatible"])
        self.assertEqual(result["reason"], "custom check")


class MultimodalGenerationPersistenceTests(unittest.TestCase):
    def test_generated_image_copies_mask_and_radar_with_new_group(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            engine = create_engine("sqlite:///:memory:", future=True)
            Base.metadata.create_all(engine)
            session_factory = sessionmaker(bind=engine, future=True)
            repository = DatasetRepository(session_factory)
            source_image = root / "source" / "case.jpg"
            source_mask = root / "source" / "case_mask.png"
            source_radar = root / "source" / "case.npz"
            _write_image(source_image)
            _write_image(source_mask)
            source_radar.write_bytes(b"npz")

            with session_factory() as session:
                source_dataset = repository.create_dataset(
                    session,
                    name="source",
                    modality="multimodal",
                    storage_path=str(root / "source_dataset"),
                )
                target_dataset = repository.create_dataset(
                    session,
                    name="target",
                    modality="multimodal",
                    storage_path=str(root / "target_dataset"),
                )
                source_sample = repository.create_sample(
                    session,
                    dataset_id=source_dataset.id,
                    name=source_image.name,
                    modality="multimodal",
                    file_path=str(source_image),
                    relative_path="images/case.jpg",
                    metadata_json={"multimodal_group_id": "case", "multimodal_role": "image"},
                    labels_json=[_label("ship", 0.5)],
                )
                for path, role in ((source_mask, "mask"), (source_radar, "radar")):
                    repository.create_sample(
                        session,
                        dataset_id=source_dataset.id,
                        name=path.name,
                        modality="multimodal",
                        file_path=str(path),
                        relative_path=path.name,
                        metadata_json={"multimodal_group_id": "case", "multimodal_role": role},
                        labels_json=[],
                    )
                session.commit()

                service = SimpleNamespace(
                    dataset_repository=repository,
                    file_indexer=FileIndexer(),
                )
                generated_root = Path(target_dataset.storage_path) / "generated"
                GenerationService._copy_multimodal_companions(
                    service,
                    session=session,
                    source_sample=source_sample,
                    target_dataset=target_dataset,
                    generated_root=generated_root,
                    generated_group_id="case__generated_1",
                    indexes={},
                )
                session.commit()

                copied = repository.get_all_samples(session, target_dataset.id)
                self.assertEqual({sample.metadata_json["multimodal_role"] for sample in copied}, {"mask", "radar"})
                self.assertTrue(all(sample.metadata_json["multimodal_group_id"] == "case__generated_1" for sample in copied))
                self.assertTrue(all(Path(sample.file_path).is_file() for sample in copied))


def _label(class_name: str, center_x: float) -> dict:
    return {
        "type": "detection",
        "class_name": class_name,
        "bbox": [center_x, 0.5, 0.2, 0.2],
        "bbox_format": "cxcywh_normalized",
    }


def _sample_dict(path: Path, role: str) -> dict:
    return {
        "file_path": str(path),
        "relative_path": path.name,
        "metadata": {"multimodal_group_id": "shared", "multimodal_role": role},
    }


def _sample_model(path: Path, role: str, group_id: str, labels: list[dict]):
    return SimpleNamespace(
        file_path=str(path),
        relative_path=path.name,
        metadata_json={"multimodal_group_id": group_id, "multimodal_role": role},
        labels_json=labels,
        status="raw",
    )


def _write_image(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (100, 100), color=(20, 30, 40)).save(path)


if __name__ == "__main__":
    unittest.main()
