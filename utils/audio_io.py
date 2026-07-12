from __future__ import annotations

from io import BytesIO
from pathlib import Path
import subprocess


def _find_ffmpeg() -> str:
    # 按当前配置仅使用虚拟环境依赖或系统 PATH，不启用项目 vendor/ffmpeg.exe。
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def load_audio(path: Path | str, *, mono: bool = True):
    """优先使用 soundfile，失败时通过 FFmpeg 解码，返回 librosa 风格数组。"""
    import numpy as np
    import soundfile as sf

    source = Path(path)
    try:
        data, sample_rate = sf.read(str(source), dtype="float32", always_2d=True)
    except Exception as soundfile_error:
        try:
            import audioread

            with audioread.audio_open(str(source)) as audio_file:
                sample_rate = int(audio_file.samplerate)
                channels = int(audio_file.channels)
                pcm = b"".join(audio_file)
            decoded = np.frombuffer(pcm, dtype="<i2").astype(np.float32) / 32768.0
            data = decoded.reshape(-1, channels)
        except Exception as audioread_error:
            try:
                ffmpeg_executable = _find_ffmpeg()
                process = subprocess.run(
                    [ffmpeg_executable, "-v", "error", "-i", str(source), "-f", "wav", "-"],
                    check=True, capture_output=True,
                )
                data, sample_rate = sf.read(BytesIO(process.stdout), dtype="float32", always_2d=True)
            except Exception as ffmpeg_error:
                raise RuntimeError(f"无法解码音频文件“{source.name}”，请确认文件未损坏且格式受支持。") from ffmpeg_error

    if mono:
        return np.mean(data, axis=1, dtype=np.float32), int(sample_rate)
    return data.T.astype(np.float32, copy=False), int(sample_rate)
