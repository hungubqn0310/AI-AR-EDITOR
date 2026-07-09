import argparse
import mimetypes
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types  # pyright: ignore[reportMissingImports]
from PIL import Image as PILImage

load_dotenv(Path(__file__).resolve().parent / ".env")

DEFAULT_PROMPT = (
    "the subject in the image continues its current action naturally, "
    "subtle realistic motion, static camera, no photorealistic style change"
)


class VeoGenerationError(Exception):
    """Raised on any failure calling Veo (missing key, API error, quota...)."""


def generate_video(
    image_path: Path,
    out_path: Path,
    prompt: str,
    model: str = "veo-3.1-fast-generate-preview",
    poll_interval: int = 10,
) -> Path:
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        raise VeoGenerationError("Thiếu biến môi trường GOOGLE_API_KEY")

    client = genai.Client(api_key=api_key)
    mime_type = mimetypes.guess_type(image_path)[0] or "image/jpeg"
    image_bytes = image_path.read_bytes()

    # Veo mặc định xuất 16:9 — nếu ảnh gốc là ảnh dọc (điện thoại chụp,
    # cao hơn rộng) mà không báo trước, video ra sẽ bị chèn viền đen to
    # 2 bên (đã gặp thực tế). Chỉ hỗ trợ đúng 2 tỷ lệ: 16:9 hoặc 9:16.
    with PILImage.open(image_path) as im:
        aspect_ratio = "9:16" if im.height > im.width else "16:9"

    print(f"Đang gửi ảnh {image_path} ({mime_type}, aspect_ratio={aspect_ratio}) tới {model}...")
    operation = client.models.generate_videos(
        model=model,
        image=types.Image(image_bytes=image_bytes, mime_type=mime_type),
        prompt=prompt,
        config=types.GenerateVideosConfig(aspect_ratio=aspect_ratio),
    )
    print("Operation:", operation.name)

    while not operation.done:
        time.sleep(poll_interval)
        operation = client.operations.get(operation)
        print("...đang xử lý")

    if operation.error:
        raise VeoGenerationError(f"Lỗi từ Veo: {operation.error}")

    video = operation.response.generated_videos[0]
    client.files.download(file=video.video)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    video.video.save(str(out_path))
    print(f"Đã lưu: {out_path}")
    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path, help="Đường dẫn ảnh tĩnh nguồn")
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="Mô tả hành động tiếp diễn mong muốn (tiếng Anh cho kết quả ổn định hơn)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="File video output (mặc định: media/videos/<tên ảnh>.mp4)",
    )
    parser.add_argument(
        "--model",
        default="veo-3.1-fast-generate-preview",
        help="Model Veo (vd: veo-3.1-fast-generate-preview, veo-3.1-generate-preview)",
    )
    args = parser.parse_args()

    if not args.image.exists():
        sys.exit(f"Không tìm thấy ảnh: {args.image}")

    out_path = args.out or Path("media/videos") / (args.image.stem + ".mp4")
    try:
        generate_video(args.image, out_path, args.prompt, args.model)
    except VeoGenerationError as e:
        sys.exit(str(e))


if __name__ == "__main__":
    main()
