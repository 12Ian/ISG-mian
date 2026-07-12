from __future__ import annotations

import re


_EXACT_MESSAGES = {
    "At least one generation algorithm is required.": "请至少选择一个生成算法。",
    "At least one cleaning algorithm is required.": "请至少选择一个清洗算法。",
    "A training algorithm is required.": "请选择训练算法。",
    "target_count must be greater than zero.": "目标生成数量必须大于 0。",
    "Dataset name is required.": "数据集名称不能为空。",
    "Dataset modality is required.": "请选择数据集模态。",
    "Source dataset must be active for generation.": "用于生成的源数据集必须处于可用状态。",
    "Source dataset must contain at least one active sample.": "源数据集至少需要包含一个可用样本。",
    "Dataset must contain at least one active sample.": "数据集至少需要包含一个可用样本。",
    "Dataset must be active for cleaning.": "用于清洗的数据集必须处于可用状态。",
    "Dataset must be active for training.": "用于训练的数据集必须处于可用状态。",
    "All algorithms must be generation algorithms.": "所选算法必须全部为生成算法。",
    "All algorithms must be cleaning algorithms.": "所选算法必须全部为清洗算法。",
    "All algorithms must be enabled.": "所选算法必须全部处于启用状态。",
    "Algorithm must be enabled.": "所选算法未启用。",
    "Algorithm must be a training algorithm.": "所选算法必须为训练算法。",
    "Algorithm must be an evaluation algorithm.": "所选算法必须为评估算法。",
    "Algorithm must be an evaluation or training algorithm.": "所选算法必须为评估或训练算法。",
    "Algorithm modality must match the source dataset modality.": "算法模态必须与源数据集模态一致。",
    "Algorithm modality must match the dataset modality.": "算法模态必须与数据集模态一致。",
    "Target dataset modality must match the source dataset modality.": "目标数据集模态必须与源数据集模态一致。",
    "Baseline and target dataset modalities must match.": "基准数据集与目标数据集的模态必须一致。",
    "Scenario modality must match the dataset modality.": "评估场景模态必须与数据集模态一致。",
    "Generation source dataset is not active.": "生成任务的源数据集当前不可用。",
    "Generation target dataset is not active.": "生成任务的目标数据集当前不可用。",
    "Cleaning source dataset is not active.": "清洗任务的源数据集当前不可用。",
    "Training dataset is not active.": "训练数据集当前不可用。",
    "Baseline dataset is not active.": "基准数据集当前不可用。",
    "Target dataset is not active.": "目标数据集当前不可用。",
    "Generation plugin failed.": "生成插件执行失败。",
    "Cleaning plugin failed.": "清洗插件执行失败。",
    "Evaluation plugin failed.": "评估插件执行失败。",
    "Training plugin failed.": "训练插件执行失败。",
    "algorithm_key is required.": "缺少算法标识。",
    "At least one input sample is required.": "至少需要提供一个输入样本。",
    "output_dir is required.": "缺少输出目录。",
    "Generation cancelled by request.": "生成任务已按请求取消。",
    "Export target directory is required.": "请选择导出目标目录。",
    "Export target path must be a directory.": "导出目标路径必须是文件夹。",
    "Dataset storage path is empty.": "数据集存储路径为空。",
    "Dataset storage directory does not exist.": "数据集存储目录不存在。",
    "Import folder does not exist.": "导入文件夹不存在。",
    "Import path does not exist.": "导入路径不存在。",
    "Source path does not exist.": "源路径不存在。",
    "Source dataset does not contain importable samples.": "源数据集中没有可导入的样本。",
    "Manifest contains no samples.": "清单文件中不包含样本。",
    "No valid samples found in manifest (all paths missing).": "清单中没有有效样本，所有样本路径均不存在。",
    "Training set path does not exist.": "训练集路径不存在。",
    "Training parameter file does not exist.": "训练参数文件不存在。",
    "Training parameter file must contain a JSON object.": "训练参数文件必须包含 JSON 对象。",
    "Either module_path or script_path is required.": "模块路径和脚本路径至少需要填写一个。",
    "callable_name is required.": "调用函数名称不能为空。",
    "Task title cannot be empty.": "任务名称不能为空。",
}

_PATTERN_MESSAGES = (
    (re.compile(r"^Dataset (\d+) not found\.$"), lambda m: f"未找到数据集（ID：{m.group(1)}）。"),
    (re.compile(r"^Algorithm (\d+) not found\.$"), lambda m: f"未找到算法（ID：{m.group(1)}）。"),
    (re.compile(r"^Task (\d+) not found\.$"), lambda m: f"未找到任务（ID：{m.group(1)}）。"),
    (re.compile(r"^Sample (\d+) not found\.$"), lambda m: f"未找到样本（ID：{m.group(1)}）。"),
    (re.compile(r"^Scenario (\d+) not found\.$"), lambda m: f"未找到评估场景（ID：{m.group(1)}）。"),
    (re.compile(r"^Suggestion (\d+) not found\.$"), lambda m: f"未找到清洗建议（ID：{m.group(1)}）。"),
    (re.compile(r"^Dataset name '(.+)' already exists\.$"), lambda m: f"数据集名称“{m.group(1)}”已存在。"),
    (re.compile(r"^Algorithm key already exists: (.+)$"), lambda m: f"算法标识已存在：{m.group(1)}"),
    (re.compile(r"^Generated output file does not exist: (.+)$"), lambda m: f"生成结果文件不存在：{m.group(1)}"),
    (re.compile(r"^Dataset directory already exists: (.+)$"), lambda m: f"数据集目录已存在：{m.group(1)}"),
    (re.compile(r"^Training parameter file is not valid JSON: (.+)$"), lambda m: f"训练参数文件不是有效的 JSON：{m.group(1)}"),
    (re.compile(r"^Algorithm (.+) does not support pipeline generation\.$"), lambda m: f"算法“{m.group(1)}”不支持串行叠加生成。"),
    (re.compile(r"^.* task (\d+) cannot run from status '(.+)'\.$", re.I), lambda m: f"任务 {m.group(1)} 当前状态为“{m.group(2)}”，无法运行。"),
    (re.compile(r"^Task (\d+) cannot (start|complete|fail) from status '(.+)'\.$"), lambda m: f"任务 {m.group(1)} 当前状态为“{m.group(3)}”，无法执行该操作。"),
)


def localize_user_message(message: object, fallback: str = "操作失败，请查看日志了解详细信息。") -> str:
    text = str(message or "").strip()
    if not text:
        return fallback
    if re.search(r"[\u4e00-\u9fff]", text):
        return text
    translated = _EXACT_MESSAGES.get(text)
    if translated:
        return translated
    for pattern, formatter in _PATTERN_MESSAGES:
        match = pattern.match(text)
        if match:
            return formatter(match)
    return fallback
