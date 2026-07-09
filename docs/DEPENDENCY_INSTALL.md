# 依赖安装说明

本文档将仓库依赖拆成三层：

- `requirements.txt`：Windows 主环境，可运行桌面程序和绝大多数内置插件
- `requirements-linux.txt`：Linux 专用补充
- `requirements-macos.txt`：macOS 专用补充

## 1. 推荐安装顺序

### Windows 主环境

适用场景：
- 运行 PySide6 桌面程序
- 使用大部分清洗、生成、训练、评估插件
- 使用 YOLO 的常见 PyTorch / ONNX / OpenVINO 路径

推荐命令：

```powershell
.\.venv\Scripts\python.exe -m pip install --upgrade pip setuptools wheel
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### Linux 补充环境

适用场景：
- 需要 `tflite-runtime`
- 需要 `torch-npu`

推荐命令：

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-linux.txt
```

### macOS 补充环境

适用场景：
- 需要 `coremltools`

推荐命令：

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-macos.txt
```

## 2. 特殊依赖说明

以下依赖虽然在仓库代码里被引用，但不建议放进主环境的一条 `pip install -r requirements.txt` 里强装。

### `libmr`

使用位置：
- `plugins/evaluation/sonar_oltr_plud.py`

原因：
- 在部分 Windows + Python 3.10 环境下，`libmr` 会因为构建隔离环境缺少 `numpy` 而失败
- `libmr` 构建 Python 绑定时还需要 `Cython`
- 如果已经安装 `numpy` 和 `Cython` 后仍失败，通常是缺少本机 C/C++ 编译工具链

推荐安装方式：

```powershell
.\.venv\Scripts\python.exe -m pip install Cython numpy
.\.venv\Scripts\python.exe -m pip install --no-build-isolation libmr
```

Windows 上如继续出现编译相关错误，请先安装 Microsoft C++ Build Tools，并勾选：

- Desktop development with C++
- MSVC v143 build tools
- Windows 10/11 SDK

### `macls`

使用位置：
- `plugins/user/training_plugin.py`
- `plugins/user/evaluation_plugin.py`

原因：
- 代码中把它当作外部 `AudioClassification-Pytorch` 项目依赖使用，不是当前仓库自带的普通 PyPI 根依赖

推荐做法：
- 单独准备 `AudioClassification-Pytorch`
- 确保 `macls` 可被 Python 导入
- 在插件参数中配置 `ac_project_path`

### `tensorrt`

使用位置：
- `plugins/detection/yolov5_core/models/common.py`

原因：
- 属于特定部署后端依赖，通常还要求额外的 NVIDIA 运行时和驱动环境

推荐做法：
- 先按 NVIDIA 官方文档准备 TensorRT 运行环境
- 再在对应环境中单独安装和验证 Python 绑定

## 3. 为什么要拆分

拆分的核心目标不是“把依赖变少”，而是“让主环境先稳定安装成功”。

当前仓库里有几类依赖天然不适合混在一起一把安装：

- 平台专属依赖：
  `tflite-runtime`、`torch-npu`、`coremltools`
- 构建敏感依赖：
  `libmr`
- 外部项目依赖：
  `macls`
- 特定部署后端依赖：
  `tensorrt`

把这些包全部塞进一个主 `requirements.txt`，会显著提高首次安装失败率。

## 4. 已知平台边界

以下边界基于 2026-07-09 查到的官方页面整理：

- `tflite-runtime` 的 PyPI 页面当前只提供 Linux 相关发行包
- `torch-npu` 的 PyPI 页面当前只提供 Linux manylinux 发行包
- `coremltools` 不适合作为 Windows 主环境依赖
- TensorFlow 官方安装文档对 Windows 原生 GPU 支持有额外限制，必要时应改用 WSL2 / Linux

参考：
- [pip requirements file format](https://pip.pypa.io/en/stable/reference/requirements-file-format/)
- [pip install options](https://pip.pypa.io/en/stable/cli/pip_install/)
- [TensorFlow pip install](https://www.tensorflow.org/install/pip)
- [tflite-runtime on PyPI](https://pypi.org/project/tflite-runtime/)
- [torch-npu on PyPI](https://pypi.org/project/torch-npu/)
- [TensorRT](https://developer.nvidia.com/tensorrt)

## 5. 最常见的安装组合

### 只跑桌面程序和常规算法

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 在 Linux 上补充 TFLite / NPU

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-linux.txt
```

### 启用 `sonar_oltr_plud`

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pip install Cython numpy
.\.venv\Scripts\python.exe -m pip install --no-build-isolation libmr
```
