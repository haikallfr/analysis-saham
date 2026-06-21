"""
models.py — SQLAlchemy ORM models:
  - FundamentalCache : cache data fundamental per ticker (TTL 24 jam)
  - SectorMetrics    : fair P/E dan P/BV per sektor (diperbarui oleh cron harian)
"""
from datetime import datetime, timezone
from sqlalchemy import (
    Column, String, Float, Boolean, Integer,
    DateTime, Index
)
from database import Base


class FundamentalCache(Base):
    """
    Menyimpan data fundamental saham yang sudah diambil dari Yahoo Finance.
    Satu baris per ticker; diperbarui jika data sudah lebih dari 24 jam.
    """
    __tablename__ = "fundamental_cache"

    ticker       = Column(String(12), primary_key=True, index=True)
    eps          = Column(Float, nullable=True)
    bvps         = Column(Float, nullable=True)
    dps          = Column(Float, nullable=True)
    eps_growth   = Column(Float, nullable=True)
    price_at     = Column(Float, nullable=True)    # harga saat data diambil
    currency_fix = Column(Boolean, default=False)  # apakah koreksi USD diterapkan
    fetched_at   = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def is_stale(self, max_age_hours: int = 24) -> bool:
        """True jika data sudah lebih dari max_age_hours."""
        if self.fetched_at is None:
            return True
        now = datetime.now(timezone.utc)
        fetched = self.fetched_at
        if fetched.tzinfo is None:
            fetched = fetched.replace(tzinfo=timezone.utc)
        return (now - fetched).total_seconds() > max_age_hours * 3600

    def to_dict(self) -> dict:
        return {
            "eps":        self.eps,
            "bvps":       self.bvps,
            "dps":        self.dps,
            "eps_growth": self.eps_growth,
            "price_at":   self.price_at,
            "currency_fix": self.currency_fix,
            "fetched_at": self.fetched_at.isoformat() if self.fetched_at else None,
        }


class SectorMetrics(Base):
    """
    Menyimpan fair P/E dan fair P/BV per sektor IDX.
    Diisi/diperbarui oleh cron_sector_pe.py setiap hari kerja pukul 18:00.
    app.py membaca tabel ini saat startup untuk menggantikan nilai hardcoded.
    """
    __tablename__ = "sector_metrics"

    sector_key    = Column(String(30), primary_key=True)
    fair_pe       = Column(Float, nullable=True)
    fair_pbv      = Column(Float, nullable=True)
    median_pe     = Column(Float, nullable=True)   # alias, untuk kejelasan
    median_pbv    = Column(Float, nullable=True)
    sample_pe     = Column(Integer, default=0)     # jumlah saham dalam hitung P/E
    sample_pbv    = Column(Integer, default=0)
    calculated_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    def is_stale(self, max_age_hours: int = 48) -> bool:
        if self.calculated_at is None:
            return True
        now = datetime.now(timezone.utc)
        calc = self.calculated_at
        if calc.tzinfo is None:
            calc = calc.replace(tzinfo=timezone.utc)
        return (now - calc).total_seconds() > max_age_hours * 3600


# ── Index tambahan ──────────────────────────────────────────────────────────
Index("ix_fundamental_cache_fetched_at", FundamentalCache.fetched_at)
Index("ix_sector_metrics_calculated_at", SectorMetrics.calculated_at)
