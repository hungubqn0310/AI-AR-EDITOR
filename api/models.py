import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from api.db import Base


class GenerationStatus(str, enum.Enum):
    processing = "processing"
    completed = "completed"
    failed = "failed"


class Generation(Base):
    __tablename__ = "generations"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=lambda: uuid.uuid4().hex[:12])
    status: Mapped[GenerationStatus] = mapped_column(
        Enum(GenerationStatus, name="generation_status"),
        default=GenerationStatus.processing,
        nullable=False,
    )
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    video_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    target_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    qr_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON string: [{x, y, title, text}], x/y là tỉ lệ 0..1 theo chiều
    # rộng/cao ảnh gốc — chấm hotspot bấm vào hiện popup khi xem AR.
    hotspots: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
