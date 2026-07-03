# ISG 算法插件接入说明

## 1. 文档定位

本文面向 ISG 桌面端算法插件开发与接入，说明插件入口、参数声明、输入输出契约和运行约定。插件应通过后端服务注册和调用，不直接绕过 `BackendService` 访问界面层。

## 2. 第一版支持范围

第一版支持清洗、生成、训练和评估四类插件。插件通过统一任务 payload 运行，界面侧只读取后端注册信息和参数 schema。

## 3. 注册字段

算法注册字段应包含 `key`、`name`、`category`、`module_path`、`description`、`parameters_schema` 等信息。示例：

```json
{
  "key": "cleaning.image_denoise",
  "name": "图像去噪",
  "category": "cleaning",
  "module_path": "plugins.cleaning.image_denoise"
}
```

## 4. 插件函数签名

每个插件提供统一入口：

```python
def run(payload: dict, context) -> dict:
    ...
```

`payload` 由后端任务服务生成，`context` 提供日志、进度和取消检查能力。

## 5. 通用输入 payload

插件通过 `payload["input"]` 获取数据集和样本信息。典型输入结构如下：

```json
{
  "input_contract": {
    "dataset_id": 1,
    "samples": [
      {"id": 1, "path": "data/datasets/example/a.jpg", "labels": []}
    ]
  }
}
```

## 6. 清洗算法输出

清洗算法输出建议包含 `suggestions` 列表，每条建议描述样本问题、处理动作和置信度。

```json
{
  "output_contract": {
    "ok": true,
    "suggestions": [
      {"sample_id": 1, "issue_type": "blur", "suggested_action": "review", "confidence": 0.9}
    ]
  }
}
```

## 7. 生成算法输出

生成算法输出应提供文件路径和相对路径：

```json
{
  "output_contract": {
    "ok": true,
    "outputs": [
      {
        "source_sample_id": 1,
        "output_path": "data/tasks/1/output/a_aug.jpg",
        "relative_path": "a_aug.jpg",
        "status": "created"
      }
    ]
  }
}
```

## 8. 评估算法输出

评估算法输出建议包含 `metrics`、`summary` 和 `artifacts`，用于评估页展示指标和报告文件。

```json
{
  "output_contract": {
    "ok": true,
    "metrics": {"accuracy": 0.95},
    "summary": "评估完成",
    "artifacts": []
  }
}
```

## 9. 分类字段

注册算法时使用 `category` 区分模块，例如：

```json
{
  "category": "cleaning"
}
```

常用分类包括 `cleaning`、`generation`、`training`、`evaluation`。

## 9.1 进度与日志

长任务应定期调用 `context.set_progress(percent, message)`，并通过 `context.is_cancel_requested()` 响应取消请求。错误信息返回给界面，详细异常由后端日志记录。

## 9.2 文件输出约定

生成算法应把新文件写入 `payload["output"]["output_dir"]`，返回 `outputs` 列表。不要覆盖源样本文件，不要把绝对临时路径写入数据集元数据。

## 10. 参数 schema

参数 schema 应保持稳定，避免随意改名。新增参数优先提供默认值，保证历史任务可以继续运行。
