"""Standalone API: upload 1 ảnh -> sinh video AI (Veo) + compile AR target + QR code.

Chạy: uvicorn api.main:app --host 0.0.0.0 --port 5556

Env (đọc từ .env, xem .env.example):
  GOOGLE_API_KEY  - bắt buộc, key Veo (cần billing bật)
  PUBLIC_BASE_URL - domain public để build URL trong response/QR
  API_KEY         - tuỳ chọn, nếu đặt thì /api/generate bắt buộc header
                    "X-API-Key" khớp giá trị này
"""
import asyncio
import json
import logging
import os
import subprocess
import sys
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image as PILImage
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))
from generate_video import DEFAULT_PROMPT, VeoGenerationError, generate_video  # noqa: E402

import qrcode  # noqa: E402

from api.banner_compose import Region, compose_banner_video, crop_region  # noqa: E402
from api.db import Base, engine, get_db  # noqa: E402
from api.models import Generation, GenerationStatus  # noqa: E402

logger = logging.getLogger("ar-qr-api")
logging.basicConfig(level=logging.INFO)

PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:5556").rstrip("/")
API_KEY = os.environ.get("API_KEY")


def require_api_key(x_api_key: str = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")


THUMB_MAX_SIZE = 480
COMPILE_MAX_SIZE = 1280


def make_thumbnail(src_path: Path, item_id: str) -> None:
    # Ảnh upload gốc có thể rất nặng (ảnh điện thoại chụp thẳng hay tới
    # chục MB) — tạo bản thu nhỏ riêng để trang lịch sử load nhanh, ảnh
    # gốc vẫn giữ nguyên cho Veo/compile-target.js dùng.
    thumb_path = src_path.parent / f"{item_id}_thumb.jpg"
    with PILImage.open(src_path) as im:
        im = im.convert("RGB")
        im.thumbnail((THUMB_MAX_SIZE, THUMB_MAX_SIZE))
        im.save(thumb_path, "JPEG", quality=82)


def make_compile_source(src_path: Path, item_id: str) -> Path:
    # Ảnh điện thoại chụp thẳng có thể vài nghìn px mỗi chiều — resize
    # xuống trước khi đưa vào compile-target.js để target .mind nhẹ hơn
    # (tải nhanh hơn qua mạng) và MindAR track mượt hơn trên điện thoại.
    # Không ảnh hưởng ảnh gốc dùng cho Veo/hiển thị.
    with PILImage.open(src_path) as im:
        if max(im.size) <= COMPILE_MAX_SIZE:
            return src_path
        im = im.convert("RGB")
        im.thumbnail((COMPILE_MAX_SIZE, COMPILE_MAX_SIZE))
        compile_path = src_path.parent / f"{item_id}_compile.jpg"
        im.save(compile_path, "JPEG", quality=90)
        return compile_path


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(title="AR QR Generator", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/media", StaticFiles(directory=ROOT / "media"), name="media")
app.mount("/qrcodes", StaticFiles(directory=ROOT / "qrcodes"), name="qrcodes")
app.mount("/targets", StaticFiles(directory=ROOT / "targets"), name="targets")
app.mount("/pages", StaticFiles(directory=ROOT / "pages"), name="pages")


@app.get("/upload", response_class=HTMLResponse)
async def upload_page():
    # Template nằm ở api/templates/ (không phải pages/ static) để không ai
    # vô tình mở trực tiếp bản chưa điền API_KEY thật (gây nhầm 401).
    html = (ROOT / "api" / "templates" / "upload.html").read_text(encoding="utf-8")
    html = html.replace("__API_KEY__", API_KEY or "")
    return HTMLResponse(html)


@app.post("/api/generate", dependencies=[Depends(require_api_key)])
async def generate(
    image: UploadFile = File(...),
    prompt: str = Form(DEFAULT_PROMPT),
    db: AsyncSession = Depends(get_db),
):
    item_id = uuid.uuid4().hex[:12]
    ext = Path(image.filename or "upload.jpg").suffix or ".jpg"

    image_path = ROOT / "media" / "images" / f"{item_id}{ext}"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(await image.read())
    make_thumbnail(image_path, item_id)

    record = Generation(
        id=item_id,
        status=GenerationStatus.processing,
        prompt=prompt,
        image_filename=image_path.name,
    )
    db.add(record)
    await db.commit()

    video_path = ROOT / "media" / "videos" / f"{item_id}.mp4"
    logger.info("[%s] generating video via Veo...", item_id)
    try:
        # generate_video là hàm đồng bộ (time.sleep polling, có thể mất vài
        # phút) — chạy trong thread riêng để không khoá event loop, tránh
        # người khác đang quét QR khác bị treo trong lúc này.
        await asyncio.to_thread(generate_video, image_path, video_path, prompt)
    except VeoGenerationError as e:
        record.status = GenerationStatus.failed
        record.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Veo generation failed: {e}") from e

    return await compile_target_and_finalize(db, record, image_path, item_id, video_path)


async def compile_target_and_finalize(
    db: AsyncSession, record: Generation, image_path: Path, item_id: str, video_path: Path
) -> dict:
    # Bước chung cho cả /api/generate (1 ảnh) và /api/generate-banner (banner
    # nhiều vùng): compile AR target từ ảnh gốc + sinh QR + lưu kết quả.
    compile_source = make_compile_source(image_path, item_id)
    target_rel = f"targets/{item_id}.mind"
    logger.info("[%s] compiling AR target (source: %s)...", item_id, compile_source.name)
    # subprocess.run cũng blocking (Puppeteer/Chrome, tới 180s) — chạy trong
    # thread riêng cùng lý do như generate_video ở trên.
    result = await asyncio.to_thread(
        subprocess.run,
        ["node", "compile-target.js", str(compile_source.relative_to(ROOT)), target_rel],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if result.returncode != 0:
        record.status = GenerationStatus.failed
        record.error_message = f"Compile target failed: {result.stderr[-2000:]}"
        await db.commit()
        raise HTTPException(status_code=502, detail=record.error_message)

    ar_page_url = f"{PUBLIC_BASE_URL}/pages/ar-view.html?id={item_id}"

    qr_path = ROOT / "qrcodes" / f"{item_id}.png"
    qr_path.parent.mkdir(parents=True, exist_ok=True)
    qrcode.make(ar_page_url).save(qr_path)

    record.status = GenerationStatus.completed
    record.video_filename = video_path.name
    record.target_filename = f"{item_id}.mind"
    record.qr_filename = qr_path.name
    await db.commit()

    return generation_to_dict(record)


def generation_to_dict(g: Generation) -> dict:
    return {
        "id": g.id,
        "status": g.status,
        "prompt": g.prompt,
        "created_at": g.created_at,
        "error_message": g.error_message,
        "image_url": f"{PUBLIC_BASE_URL}/media/images/{g.image_filename}" if g.image_filename else None,
        "image_thumb_url": f"{PUBLIC_BASE_URL}/media/images/{g.id}_thumb.jpg" if g.image_filename else None,
        "video_url": f"{PUBLIC_BASE_URL}/media/videos/{g.video_filename}" if g.video_filename else None,
        "target_url": f"{PUBLIC_BASE_URL}/targets/{g.target_filename}" if g.target_filename else None,
        "qr_code_url": f"{PUBLIC_BASE_URL}/qrcodes/{g.qr_filename}" if g.qr_filename else None,
        "ar_page_url": f"{PUBLIC_BASE_URL}/pages/ar-view.html?id={g.id}",
        "hotspots": json.loads(g.hotspots) if g.hotspots else [],
    }


@app.get("/banner", response_class=HTMLResponse)
async def banner_page():
    html = (ROOT / "api" / "templates" / "banner.html").read_text(encoding="utf-8")
    html = html.replace("__API_KEY__", API_KEY or "")
    return HTMLResponse(html)


@app.post("/api/generate-banner", dependencies=[Depends(require_api_key)])
async def generate_banner(
    image: UploadFile = File(...),
    regions: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # regions: JSON string, mảng {x, y, w, h, prompt} theo toạ độ pixel gốc
    # của ảnh banner — mỗi vùng là 1 chỗ cần "động", phần còn lại của banner
    # giữ nguyên tĩnh (xem api/banner_compose.py).
    try:
        raw_regions = json.loads(regions)
        if not isinstance(raw_regions, list) or not raw_regions:
            raise ValueError("regions phải là mảng không rỗng")
        region_objs = [
            Region(x=int(r["x"]), y=int(r["y"]), w=int(r["w"]), h=int(r["h"]), prompt=str(r["prompt"]))
            for r in raw_regions
        ]
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
        raise HTTPException(status_code=422, detail=f"regions không hợp lệ: {e}") from e

    item_id = uuid.uuid4().hex[:12]
    ext = Path(image.filename or "upload.jpg").suffix or ".jpg"

    image_path = ROOT / "media" / "images" / f"{item_id}{ext}"
    image_path.parent.mkdir(parents=True, exist_ok=True)
    image_path.write_bytes(await image.read())
    make_thumbnail(image_path, item_id)

    combined_prompt = " | ".join(r.prompt for r in region_objs)
    record = Generation(
        id=item_id,
        status=GenerationStatus.processing,
        prompt=combined_prompt,
        image_filename=image_path.name,
    )
    db.add(record)
    await db.commit()

    region_video_paths = []
    try:
        for i, region in enumerate(region_objs):
            crop_path = ROOT / "media" / "images" / f"{item_id}_region{i}.jpg"
            await asyncio.to_thread(crop_region, image_path, region, crop_path)

            region_video_path = ROOT / "media" / "videos" / f"{item_id}_region{i}.mp4"
            logger.info("[%s] generating video for region %d/%d via Veo...", item_id, i + 1, len(region_objs))
            await asyncio.to_thread(generate_video, crop_path, region_video_path, region.prompt)
            region_video_paths.append(region_video_path)
    except VeoGenerationError as e:
        record.status = GenerationStatus.failed
        record.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Veo generation failed: {e}") from e

    video_path = ROOT / "media" / "videos" / f"{item_id}.mp4"
    logger.info("[%s] composing banner video (%d region(s))...", item_id, len(region_objs))
    try:
        await asyncio.to_thread(compose_banner_video, image_path, region_objs, region_video_paths, video_path)
    except RuntimeError as e:
        record.status = GenerationStatus.failed
        record.error_message = str(e)
        await db.commit()
        raise HTTPException(status_code=502, detail=f"Compose video failed: {e}") from e

    return await compile_target_and_finalize(db, record, image_path, item_id, video_path)


@app.get("/history", response_class=HTMLResponse)
async def history_page():
    html = (ROOT / "api" / "templates" / "history.html").read_text(encoding="utf-8")
    html = html.replace("__API_KEY__", API_KEY or "")
    return HTMLResponse(html)


@app.get("/api/generations", dependencies=[Depends(require_api_key)])
async def list_generations(db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Generation).order_by(Generation.created_at.desc()))
    return [generation_to_dict(g) for g in result.scalars().all()]


@app.get("/api/generations/{item_id}", dependencies=[Depends(require_api_key)])
async def get_generation(item_id: str, db: AsyncSession = Depends(get_db)):
    record = await db.get(Generation, item_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy generation")
    return generation_to_dict(record)


class HotspotIn(BaseModel):
    x: float  # tỉ lệ 0..1 theo chiều rộng ảnh gốc
    y: float  # tỉ lệ 0..1 theo chiều cao ảnh gốc
    # simple | promo | product | contact — chỉ đổi giao diện popup (màu/icon/
    # bố cục) khi hiện lúc xem AR, nội dung vẫn luôn là title/text thuần,
    # không có field riêng nào khác. Xem ar-view.html showHotspotPopup().
    template: str = "simple"
    title: str
    text: str


class HotspotsPatch(BaseModel):
    hotspots: list[HotspotIn]


@app.patch("/api/generations/{item_id}/hotspots", dependencies=[Depends(require_api_key)])
async def update_hotspots(item_id: str, payload: HotspotsPatch, db: AsyncSession = Depends(get_db)):
    record = await db.get(Generation, item_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy generation")
    record.hotspots = json.dumps([h.model_dump() for h in payload.hotspots])
    await db.commit()
    return generation_to_dict(record)


@app.get("/api/generations/{item_id}/public")
async def get_generation_public(item_id: str, db: AsyncSession = Depends(get_db)):
    # Không yêu cầu X-API-Key: trang ar-view.html do người quét QR (ẩn danh,
    # không có key) mở, cần đọc hotspots + kích thước ảnh gốc để định vị
    # đúng chấm bấm trong không gian AR. Chỉ trả đúng phần cần cho việc đó,
    # không lộ prompt/thông tin nội bộ như /api/generations.
    record = await db.get(Generation, item_id)
    if not record:
        raise HTTPException(status_code=404, detail="Không tìm thấy generation")
    hotspots = json.loads(record.hotspots) if record.hotspots else []
    width = height = None
    image_path = ROOT / "media" / "images" / record.image_filename
    if image_path.exists():
        with PILImage.open(image_path) as im:
            width, height = im.size
    return {"hotspots": hotspots, "image_width": width, "image_height": height}


@app.get("/edit/{item_id}", response_class=HTMLResponse)
async def edit_page(item_id: str):
    html = (ROOT / "api" / "templates" / "edit.html").read_text(encoding="utf-8")
    html = html.replace("__API_KEY__", API_KEY or "")
    html = html.replace("__ITEM_ID__", item_id)
    return HTMLResponse(html)


class ClientLog(BaseModel):
    id: str | None = None
    message: str


@app.post("/api/client-log")
async def client_log(payload: ClientLog):
    # Log JS chạy trên điện thoại của người dùng gửi về — chỉ để debug
    # (vd trang ar-view.html), không lưu DB, chỉ in ra docker logs.
    logger.info("[client %s] %s", payload.id or "-", payload.message)
    return {"ok": True}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
