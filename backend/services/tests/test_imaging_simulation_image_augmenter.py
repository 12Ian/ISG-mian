import numpy as np

from backend.seed_data import DEFAULT_ALGORITHMS
from plugins.generation import imaging_simulation_image_augmenter as augmenter
from plugins.generation._image_io import read_image, write_image


class Context:
    def is_cancel_requested(self):
        return False

    def set_progress(self, *_args):
        pass


def _run(tmp_path, output_name):
    source = tmp_path / "source.png"
    image = np.full((64, 64, 3), 128, dtype=np.uint8)
    assert write_image(source, image)

    return augmenter.run(
        {
            "task_id": 42,
            "parameters": {
                "blur_kernel": 0,
                "downsample": 1.0,
                "noise_std": 0.03,
                "brightness_shift": 0.05,
                "color_shift": 0.05,
            },
            "input": {"samples": [{"id": 1, "sample_path": str(source)}]},
            "output": {"output_dir": str(tmp_path / output_name)},
            "target_count": 2,
        },
        Context(),
    )


def test_sensor_degradation_varies_repeated_outputs_and_is_reproducible(tmp_path):
    first = _run(tmp_path, "first")
    second = _run(tmp_path, "second")

    assert first["ok"] is True
    assert second["ok"] is True
    first_images = [read_image(item["output_path"]) for item in first["outputs"]]
    second_images = [read_image(item["output_path"]) for item in second["outputs"]]

    assert not np.array_equal(first_images[0], first_images[1])
    assert np.array_equal(first_images[0], second_images[0])
    assert np.array_equal(first_images[1], second_images[1])
    assert first["outputs"][0]["metadata"]["parameters"] == {
        "blur_kernel": 0,
        "downsample": 1.0,
        "noise_std": 0.03,
        "brightness_shift": 0.05,
        "color_shift": 0.05,
    }


def test_parameter_contract_includes_sensor_degradation_controls():
    plugin_parameters = {item["name"]: item for item in augmenter.PARAMETERS}
    seed_algorithm = next(
        item for item in DEFAULT_ALGORITHMS if item["key"] == "generation.image.imaging_simulation"
    )
    seed_parameters = {item["name"]: item for item in seed_algorithm["parameters"]}

    expected = {
        "noise_std": (0.03, 0.0, 0.2),
        "brightness_shift": (0.05, 0.0, 0.3),
        "color_shift": (0.05, 0.0, 0.3),
    }
    for name, (default, minimum, maximum) in expected.items():
        plugin_parameter = plugin_parameters[name]
        seed_parameter = seed_parameters[name]
        assert (plugin_parameter["default"], plugin_parameter["min"], plugin_parameter["max"]) == (
            default,
            minimum,
            maximum,
        )
        assert seed_parameter["default"] == default
        assert seed_parameter["min"] == minimum
        assert seed_parameter["max"] == maximum


def test_output_offset_changes_random_sensor_effects(tmp_path):
    source_path = tmp_path / "offset_source.png"
    assert write_image(source_path, np.full((32, 32, 3), 128, dtype=np.uint8))
    parameters = {
        "blur_kernel": 0,
        "downsample": 1.0,
        "noise_std": 0.05,
        "brightness_shift": 0.05,
        "color_shift": 0.05,
    }

    def generate(offset, folder):
        return augmenter.run(
            {
                "task_id": 10,
                "output_index": offset,
                "target_count": 1,
                "parameters": parameters,
                "input": {"samples": [{"id": 1, "sample_path": str(source_path)}]},
                "output": {"output_dir": str(folder)},
            },
            Context(),
        )

    first = generate(0, tmp_path / "offset_first")
    second = generate(1, tmp_path / "offset_second")
    first_image = read_image(first["outputs"][0]["output_path"])
    second_image = read_image(second["outputs"][0]["output_path"])
    assert not np.array_equal(first_image, second_image)
