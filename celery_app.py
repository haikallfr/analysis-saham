"""
celery_app.py — Konfigurasi Celery dengan Redis sebagai broker + result backend.
Semua task scan IDX menggunakan antrean ini.
"""
from celery import Celery

import os
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

celery = Celery(
    "idx_scanner",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="Asia/Jakarta",
    enable_utc=True,
    # Hasil task disimpan 2 jam
    result_expires=7200,
    # Solo pool: hindari konflik fork+thread yfinance di macOS
    # Untuk production Linux, ganti ke worker_prefetch_multiplier=1
    worker_pool="solo",
    task_acks_late=True,
)
