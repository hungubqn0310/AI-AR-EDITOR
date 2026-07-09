"""Ghép video AR cho ảnh banner dài/tỷ lệ bất thường (case AEON): Veo chỉ
sinh được video 16:9/9:16, nên với ảnh dài hơn nhiều, ta cắt riêng từng
vùng cần "động" ra generate qua Veo, rồi overlay từng đoạn video đó lên
đúng vị trí trên nền ảnh gốc đứng yên — thay cho việc tự tay dùng
ffmpeg crop/hstack như trước (xem README mục AEON).
"""
import logging
import subprocess
from pathlib import Path

from PIL import Image as PILImage

logger = logging.getLogger("ar-qr-api")


class Region:
    __slots__ = ("x", "y", "w", "h", "prompt")

    def __init__(self, x: int, y: int, w: int, h: int, prompt: str):
        self.x, self.y, self.w, self.h, self.prompt = x, y, w, h, prompt


def crop_region(src_path: Path, region: Region, out_path: Path) -> Path:
    with PILImage.open(src_path) as im:
        im = im.convert("RGB")
        box = (region.x, region.y, region.x + region.w, region.y + region.h)
        im.crop(box).save(out_path, "JPEG", quality=95)
    return out_path


def probe_duration_seconds(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed on {path}: {result.stderr[-1000:]}")
    return float(result.stdout.strip())


def compose_banner_video(
    original_image_path: Path,
    regions: list[Region],
    region_video_paths: list[Path],
    out_path: Path,
) -> Path:
    """Nền = ảnh gốc đứng yên (loop); mỗi vùng động = video Veo tương ứng,
    scale đúng kích thước vùng crop rồi overlay lên đúng toạ độ (x, y).
    eof_action=repeat: vùng đóng băng ở frame cuối sau khi video đó hết,
    không revert về ảnh tĩnh giữa chừng nếu các vùng có độ dài khác nhau.
    """
    duration = max(probe_duration_seconds(p) for p in region_video_paths)

    inputs = ["-loop", "1", "-i", str(original_image_path)]
    for p in region_video_paths:
        inputs += ["-i", str(p)]

    filter_parts = []
    last_label = "0:v"
    for i, region in enumerate(regions, start=1):
        scaled = f"r{i}"
        merged = f"m{i}"
        filter_parts.append(f"[{i}:v]scale={region.w}:{region.h}[{scaled}]")
        filter_parts.append(
            f"[{last_label}][{scaled}]overlay={region.x}:{region.y}:eof_action=repeat[{merged}]"
        )
        last_label = merged
    filter_complex = ";".join(filter_parts)

    cmd = [
        "ffmpeg", "-y",
        *inputs,
        "-filter_complex", filter_complex,
        "-map", f"[{last_label}]",
        "-t", f"{duration:.3f}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
        "-an",
        str(out_path),
    ]
    logger.info("composing banner video: %s", " ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg compose failed: {result.stderr[-2000:]}")
    return out_path
