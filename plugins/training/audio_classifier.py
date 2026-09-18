"""Audio classification training plugin entry point."""

# 保留旧插件实现，向已注册的 plugins.training.audio_classifier 路径提供入口。
from plugins.user.training_plugin import PARAMETERS, run

__all__ = ["PARAMETERS", "run"]
