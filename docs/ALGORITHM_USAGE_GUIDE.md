# ISG 算法插件接入说明

## 1. 文档定位

本文说明 ISG 桌面端算法插件的接入约定，用于对齐算法配置页、后端插件运行器和默认算法注册数据。插件通过统一的 `run` 函数接收任务上下文，返回结构化结果，由后端服务负责持久化任务、样本、建议和评估结果。

## 2. 第一版支持范围

第一版支持四类算法：

- 清洗算法：输出清洗建议或修复后的样本。
- 生成算法：基于源样本生成增强样本。
- 评估算法：对基准数据集与目标数据集输出指标和报告。
- 训练算法：基于数据集生成模型产物，并可绑定评估算法。

## 3. 注册字段

算法注册信息至少包含：

```json
{
  "key": "generation.image.geometric_transform",
  "name": "基础几何变换",
  "category": "generation",
  "modality": "image",
  "entry_type": "python_function",
  "module_path": "plugins.generation.geometric_image_augmenter",
  "callable_name": "run",
  "input_contract": {"dataset_required": true, "sample_required": true},
  "output_contract": {"produces": ["generated_samples"]},
  "parameters": []
}
```

清洗算法示例：

```json
{
  "key": "cleaning.image_resolution_filter",
  "name": "图片低分辨率清洗",
  "category": "cleaning",
  "modality": "image",
  "input_contract": {"dataset_required": true, "sample_required": true},
  "output_contract": {"produces": ["suggestions"]}
}
```

## 4. 插件函数签名

插件入口统一为：

```python
def run(payload: dict, context) -> dict:
    ...
```

`payload` 提供任务输入、参数和输出目录；`context` 提供进度、日志和取消状态。

## 5. 通用输入 payload

常见字段：

```json
{
  "algorithm_key": "generation.image.geometric_transform",
  "parameters": {},
  "input": {
    "dataset": {},
    "samples": []
  },
  "output": {
    "output_dir": "data/tasks/1/output"
  },
  "target_count": 10
}
```

插件应优先使用 `payload["parameters"]` 中的参数，并将输出写入 `payload["output"]["output_dir"]`。

## 6. 清洗算法输出

清洗插件返回：

```json
{
  "ok": true,
  "suggestions": [
    {
      "sample_id": 1,
      "issue_type": "low_resolution",
      "suggested_action": "exclude",
      "confidence": 0.92,
      "message": "图片分辨率低于阈值",
      "details": {}
    }
  ],
  "logs": []
}
```

## 7. 生成算法输出

生成插件返回：

```json
{
  "ok": true,
  "outputs": [
    {
      "source_sample_id": 1,
      "output_path": "data/tasks/1/output/generated_0001.jpg",
      "relative_path": "generated_0001.jpg",
      "metadata": {},
      "status": "created"
    }
  ],
  "logs": []
}
```

## 8. 评估算法输出

评估插件返回：

```json
{
  "ok": true,
  "model_name": "sample-count-comparator",
  "metrics": {
    "baseline_samples": 100,
    "target_samples": 120,
    "sample_ratio": 1.2
  },
  "summary": "目标数据集 120 个样本，基准数据集 100 个样本，比例 1.20。",
  "artifacts": [
    {"type": "report", "path": "data/tasks/1/output/report.json"}
  ]
}
```

## 9. 训练算法输出

训练插件返回：

```json
{
  "ok": true,
  "model_name": "classifier",
  "artifacts": [
    {"type": "model", "path": "data/tasks/1/output/model.pt"}
  ],
  "metrics": {},
  "logs": []
}
```

## 10. 参数 schema

参数项使用统一 schema：

```json
{
  "name": "rotation_degrees",
  "label": "旋转角度",
  "type": "float",
  "default": 0.0,
  "min": -180.0,
  "max": 180.0,
  "options": [],
  "description": "图像旋转角度",
  "required": false
}
```

常用 `type` 包括 `string`、`int`、`float`、`bool`、`select`。对于 `select` 参数，应提供 `options`。
