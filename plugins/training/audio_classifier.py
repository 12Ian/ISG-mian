"""Audio classification training plugin entry point."""

# 保留旧插件实现，向已注册的 plugins.training.audio_classifier 路径提供入口。
# 参数必须在入口文件中静态声明，默认算法同步器才能读取契约。
PARAMETERS = [
    {"name": "model_name", "type": "select", "label": "模型", "default": "AudioCNN", "options": ["AudioCNN"], "description": "本地音频分类模型", "required": False},
    {"name": "feature_method", "type": "select", "label": "特征提取方法", "default": "MelSpectrogram", "options": ["MelSpectrogram", "MFCC", "Spectrogram"], "description": "音频频谱特征", "required": False},
    {"name": "batch_size", "type": "int", "label": "批大小", "default": 8, "min": 1, "max": 256, "description": "训练批次大小", "required": False},
    {"name": "epochs", "type": "int", "label": "训练轮次", "default": 10, "min": 1, "max": 500, "description": "训练 epoch 数量", "required": False},
    {"name": "learning_rate", "type": "float", "label": "学习率", "default": 0.001, "min": 1e-6, "max": 0.1, "description": "Adam 优化器学习率", "required": False},
    {"name": "max_duration", "type": "float", "label": "音频最大时长(秒)", "default": 3.0, "min": 0.5, "max": 30.0, "description": "统一裁剪或补零的音频时长", "required": False},
    {"name": "train_ratio", "type": "float", "label": "训练集比例", "default": 0.75, "min": 0.3, "max": 0.9, "description": "训练集占比，剩余为测试集", "required": False},
]

from plugins.user.training_plugin import run

__all__ = ["PARAMETERS", "run"]
