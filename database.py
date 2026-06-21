"""
database.py — Koneksi SQLAlchemy ke PostgreSQL untuk caching fundamental.
"""
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

# Bisa di-override via environment variable
DATABASE_URL = os.environ.get(
    "IDX_DB_URL",
    "postgresql://localhost/idx_scanner"
)

engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,    # cek koneksi sebelum dipakai
    pool_size=5,
    max_overflow=10,
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """Dependency injection — gunakan sebagai context manager."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Buat semua tabel jika belum ada."""
    from models import Base as ModelBase  # noqa: F401 — import agar tabel terdaftar
    ModelBase.metadata.create_all(bind=engine)
    print("[DB] Schema initialized.")
