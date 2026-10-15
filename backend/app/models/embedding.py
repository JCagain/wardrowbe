import uuid
from datetime import datetime

from sqlalchemy import REAL, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class ItemEmbedding(Base):
    """Archive-side vector for AI-suggested linking (spec §3.2, fixes #29, D5).

    One row per item. Stale when `model` differs from the configured model or
    `source_fingerprint` no longer matches the item's current pixels (Ruling 81).
    """

    __tablename__ = "item_embeddings"

    item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("clothing_items.id", ondelete="CASCADE"), primary_key=True
    )
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(String(1200), nullable=False)
    dim: Mapped[int] = mapped_column(Integer, nullable=False)
    vector: Mapped[list[float]] = mapped_column(ARRAY(REAL), nullable=False)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
