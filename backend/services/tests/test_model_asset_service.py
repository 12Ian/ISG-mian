from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from backend.errors import NotFoundError, ValidationError
from backend.services.algorithm_service import AlgorithmService
from backend.services.model_asset_service import ModelAssetService


class ModelAssetServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        paths = SimpleNamespace(models_dir=self.root / "models")
        self.service = ModelAssetService(paths=paths, session_factory=None)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_import_list_and_delete_model(self):
        source = self.root / "yolov8n.pt"
        source.write_bytes(b"weights")

        imported = self.service.import_asset(str(source), "yolov8")
        item = imported["data"]
        self.assertEqual(item["family"], "yolov8")
        self.assertTrue(Path(item["path"]).is_file())

        listed = self.service.list_assets("yolov8")["data"]["items"]
        self.assertEqual([entry["id"] for entry in listed], ["yolov8/yolov8n.pt"])

        deleted = self.service.delete_asset(item["id"])
        self.assertTrue(deleted["ok"])
        self.assertEqual(self.service.list_assets("yolov8")["data"]["items"], [])

    def test_duplicate_import_gets_unique_name(self):
        source = self.root / "model.pt"
        source.write_bytes(b"weights")
        first = self.service.import_asset(str(source), "yolov5")["data"]
        second = self.service.import_asset(str(source), "yolov5")["data"]
        self.assertEqual(first["name"], "model.pt")
        self.assertEqual(second["name"], "model_2.pt")

    def test_rejects_yolov5u_for_legacy_yolov5_family(self):
        source = self.root / "yolov5su.pt"
        source.write_bytes(b"anchor-free weights")

        with self.assertRaisesRegex(ValidationError, "anchor-free YOLOv5u"):
            self.service.import_asset(str(source), "yolov5")

    def test_existing_yolov5u_is_not_offered_to_legacy_yolov5(self):
        family_dir = self.service.paths.models_dir / "yolov5"
        family_dir.mkdir(parents=True)
        (family_dir / "yolov5su.pt").write_bytes(b"anchor-free weights")
        compatible = family_dir / "yolov5s.pt"
        compatible.write_bytes(b"legacy weights")

        self.assertEqual(self.service.paths_for_family("yolov5"), [str(compatible.resolve())])

    def test_rejects_invalid_extension_and_family(self):
        source = self.root / "model.txt"
        source.write_text("bad", encoding="utf-8")
        with self.assertRaises(ValidationError):
            self.service.import_asset(str(source), "yolov8")
        source = self.root / "model.pt"
        source.write_bytes(b"weights")
        with self.assertRaises(ValidationError):
            self.service.import_asset(str(source), "unknown")

    def test_delete_rejects_path_escape(self):
        with self.assertRaises(ValidationError):
            self.service.delete_asset("../outside.pt")
        with self.assertRaises(NotFoundError):
            self.service.delete_asset("yolov8/missing.pt")

    def test_family_detection(self):
        self.assertEqual(
            self.service.family_for_algorithm_key("training.image.yolov5_detector"), "yolov5"
        )
        self.assertEqual(self.service.family_for_algorithm_key("training.image.yolov8"), "yolov8")
        self.assertEqual(self.service.family_for_algorithm_key("training.image.yolo11"), "yolo11")

    def test_algorithm_parameters_include_imported_model_paths(self):
        source = self.root / "yolov8s.pt"
        source.write_bytes(b"weights")
        imported_path = self.service.import_asset(str(source), "yolov8")["data"]["path"]
        algorithm_service = AlgorithmService(
            paths=self.service.paths,
            session_factory=None,
            algorithm_repository=None,
            log_repository=None,
            model_asset_service=self.service,
        )
        data = {
            "category": "training",
            "key": "training.image.yolov8_detector",
            "parameters": [{"name": "model", "options": ["yolov8n.pt"]}],
        }
        algorithm_service._append_model_asset_options(data)
        self.assertEqual(data["parameters"][0]["options"], ["yolov8n.pt", imported_path])

        matching = self.root / "yolov8n.pt"
        matching.write_bytes(b"weights")
        matching_path = self.service.import_asset(str(matching), "yolov8")["data"]["path"]
        data["parameters"][0]["options"] = ["yolov8n.pt"]
        algorithm_service._append_model_asset_options(data)
        self.assertEqual(data["parameters"][0]["options"][0], matching_path)

        config = self.root / "custom.yaml"
        config.write_text("nc: 2", encoding="utf-8")
        config_path = self.service.import_asset(str(config), "custom")["data"]["path"]
        data["parameters"].append({"name": "model_yaml", "options": []})
        algorithm_service._append_model_asset_options(data)
        self.assertEqual(data["parameters"][1]["options"], [config_path])
