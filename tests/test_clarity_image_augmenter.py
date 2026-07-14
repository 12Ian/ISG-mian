import cv2
import numpy as np

from backend.parameter_ranges import normalize_parameter_value, normalized_parameter_range
from backend.seed_data import DEFAULT_ALGORITHMS
from plugins.generation import clarity_image_augmenter as augmenter
from plugins.generation._image_io import read_image, write_image


class Context:
    def is_cancel_requested(self):
        return False

    def set_progress(self, *_args):
        pass


def test_both_effects_alternate_instead_of_stacking(tmp_path):
    source = tmp_path / "source.png"
    image = np.zeros((64, 64, 3), dtype=np.uint8)
    image[:, 32:] = 255
    assert write_image(source, image)

    result = augmenter.run(
        {
            "parameters": {
                "blur_strength": 2.0,
                "sharpen_strength": 1.2,
                "sharpen_amount": 0.55,
            },
            "input": {"samples": [{"id": 1, "sample_path": str(source)}]},
            "output": {"output_dir": str(tmp_path / "outputs")},
            "target_count": 2,
        },
        Context(),
    )

    assert result["ok"] is True
    assert [item["metadata"]["applied_effect"] for item in result["outputs"]] == ["blur", "sharpen"]
    assert all("blur_kernel" not in item["metadata"]["parameters"] for item in result["outputs"])

    blur_output = read_image(result["outputs"][0]["output_path"])
    sharpen_output = read_image(result["outputs"][1]["output_path"])
    source_gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    blur_gray = cv2.cvtColor(blur_output, cv2.COLOR_BGR2GRAY)
    sharpen_gray = cv2.cvtColor(sharpen_output, cv2.COLOR_BGR2GRAY)
    source_variance = cv2.Laplacian(source_gray, cv2.CV_64F).var()

    assert cv2.Laplacian(blur_gray, cv2.CV_64F).var() < source_variance
    assert cv2.Laplacian(sharpen_gray, cv2.CV_64F).var() >= source_variance


def test_parameter_defaults_and_ranges_match_runtime_contract():
    plugin_parameters = {item["name"]: item for item in augmenter.PARAMETERS}
    seed_algorithm = next(item for item in DEFAULT_ALGORITHMS if item["key"] == "generation.image.clarity")
    seed_parameters = {item["name"]: item for item in seed_algorithm["parameters"]}

    expected = {
        "blur_strength": (0.0, 0.0, 10.0),
        "sharpen_strength": (1.2, 0.0, 5.0),
        "sharpen_amount": (0.55, 0.0, 1.0),
    }
    for name, contract in expected.items():
        plugin_parameter = plugin_parameters[name]
        seed_parameter = seed_parameters[name]
        assert (plugin_parameter["default"], plugin_parameter["min"], plugin_parameter["max"]) == contract
        assert (seed_parameter["default"], seed_parameter["min"], seed_parameter["max"]) == contract
        assert normalized_parameter_range(seed_parameter) == {
            "min_value": float(contract[1]),
            "max_value": float(contract[2]),
            "options": [],
        }
        assert normalize_parameter_value(seed_parameter, contract[0]) == contract[0]
