"""
tasks.py — Celery tasks untuk scan IDX per sesi pengguna.

Setiap task menyimpan progress dan hasil ke Redis dengan kunci:
  scan:{session_id}:meta     → status, total, done count
  scan:{session_id}:events   → Redis List, tiap item = SSE JSON string
  scan:{session_id}:results  → Redis String, JSON array hasil akhir

TTL semua kunci: 7200 detik (2 jam).
"""
import json
import math
import time
import sys
import os
import redis as redis_lib

# Pastikan direktori proyek ada di sys.path
_PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from celery_app import celery
from fetch_engine import fetch_stock, calc_piotroski, calc_altman_beneish, calc_technical, detect_accumulation

# ── Redis client (shared oleh task) ─────────────────────────────────────────
_redis = redis_lib.Redis(host="localhost", port=6379, db=0, decode_responses=True)
SCAN_TTL = 7200  # 2 jam


def _key(session_id: str, suffix: str) -> str:
    return f"scan:{session_id}:{suffix}"


def _clean_nan(obj):
    """Recursively replace NaN/Infinity with None so json.dumps won't fail."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: _clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_clean_nan(v) for v in obj]
    return obj


def _push_event(session_id: str, payload: dict):
    """Simpan event ke Redis List + perbarui TTL."""
    k = _key(session_id, "events")
    _redis.rpush(k, json.dumps(payload))
    _redis.expire(k, SCAN_TTL)


@celery.task(bind=True, name="tasks.scan_sector")
def scan_sector(self, session_id: str, tickers: list):
    """
    Task utama: scan daftar ticker dan simpan hasil ke Redis.
    Dipanggil dari /api/scan dengan session_id unik per pengguna.
    """

    meta_key    = _key(session_id, "meta")
    result_key  = _key(session_id, "results")

    total = len(tickers)

    # Inisialisasi meta
    _redis.hset(meta_key, mapping={
        "status": "running",
        "total":  total,
        "done":   0,
    })
    _redis.expire(meta_key, SCAN_TTL)

    _push_event(session_id, {"type": "start", "data": {"total": total}})

    results = []

    for i, ticker in enumerate(tickers):
        _push_event(session_id, {
            "type": "progress",
            "data": {"index": i + 1, "total": total, "ticker": ticker},
        })
        # Update current ticker di meta
        _redis.hset(meta_key, "ticker", ticker)

        data = fetch_stock(ticker)
        time.sleep(1.2)  # rate-limit Yahoo Finance

        if data["status"] == "ok":
            results.append(data)
            _push_event(session_id, {
                "type": "ticker_done",
                "data": {
                    "ticker":           data["ticker"],
                    "status":           "ok",
                    "method_label":     data.get("method_label", ""),
                    "margin_of_safety": data.get("margin_of_safety", 0),
                },
            })
        else:
            _push_event(session_id, {
                "type": "ticker_done",
                "data": {
                    "ticker":    data["ticker"],
                    "status":    "error",
                    "error_msg": data.get("error_msg", ""),
                },
            })

        _redis.hset(meta_key, "done", i + 1)

    # Sort by MoS descending & tambah rank
    results.sort(key=lambda r: r.get("margin_of_safety", -9999), reverse=True)
    for idx, r in enumerate(results):
        r["rank"] = idx + 1

    # Simpan hasil final
    _redis.set(result_key, json.dumps(_clean_nan(results), ensure_ascii=False), ex=SCAN_TTL)
    _redis.hset(meta_key, "status", "done")
    _redis.expire(meta_key, SCAN_TTL)

    _push_event(session_id, {
        "type": "done",
        "data": {"total": total, "success": len(results)},
    })

    return {"session_id": session_id, "total": total, "success": len(results)}


@celery.task(bind=True, name="tasks.scan_advanced")
def scan_advanced(self, session_id: str, tickers: list):
    """
    Task pemindaian lanjutan untuk fitur High-Probability.
    Mengambil data valuasi dasar ditambah Piotroski, Z-Score, Trend, OBV.
    """
    meta_key    = _key(session_id, "meta")
    result_key  = _key(session_id, "results")

    total = len(tickers)

    _redis.hset(meta_key, mapping={
        "status": "running",
        "total":  total,
        "done":   0,
    })
    _redis.expire(meta_key, SCAN_TTL)

    _push_event(session_id, {"type": "start", "total": total})

    final_results = []
    
    for i, tk in enumerate(tickers):
        # --- GRACEFUL CANCELLATION CHECK ---
        if _redis.hget(meta_key, "cancelled") == "1" or _redis.get("scan:force_cancel_all") == "1":
            print(f"[CELERY] Task {session_id} dibatalkan oleh pengguna. Menghentikan loop.")
            break
        # -----------------------------------

        # Update current ticker di meta untuk live overlay
        _redis.hset(meta_key, "ticker", tk)
        
        # 1. Fetch dasar
        res = fetch_stock(tk)
        
        # Jika fetch dasar sukses, tambahkan advanced metrics
        if res.get("status") == "ok":
            # Piotroski
            res["piotroski"] = calc_piotroski(tk)
            
            # Z-Score & Beneish
            price = res.get("current_price") or 0.0
            res["altman_beneish"] = calc_altman_beneish(tk, price)
            
            # Technical (termasuk MACD)
            res["technical"] = calc_technical(tk)
            
            # Accumulation (OBV proxy)
            res["accumulation"] = detect_accumulation(tk)
            
            is_cheap = bool(res.get("recommended_method"))
            f_score = res.get("piotroski", {}).get("score", 0) if res.get("piotroski") else 0
            is_quality = f_score >= 7
            
            tech = res.get("technical", {})
            is_uptrend = tech.get("is_uptrend", False) if tech else False
            macd_stat = tech.get("macd", {}).get("status", "") if tech and "macd" in tech else ""
            is_momentum = is_uptrend and "death_cross" not in macd_stat
            
            acc_score = res.get("accumulation", {}).get("score", 0) if res.get("accumulation") else 0
            is_accumulated = acc_score >= 60
            
            if is_cheap and is_quality and is_momentum and is_accumulated:
                res["high_probability_status"] = "🔥 High Probability"
            else:
                res["high_probability_status"] = "Normal"

        final_results.append(res)
        
        _redis.hincrby(meta_key, "done", 1)
        _push_event(session_id, {"type": "progress", "ticker": tk, "done": i + 1, "total": total})
        time.sleep(1)

    _redis.hset(meta_key, "ticker", "Selesai")
    _redis.set(result_key, json.dumps(_clean_nan(final_results)))
    _redis.expire(result_key, SCAN_TTL)

    _push_event(session_id, {
        "type": "done",
        "data": {"total": total, "success": len(final_results)},
    })

    _redis.hset(meta_key, "status", "done")
    _redis.expire(meta_key, SCAN_TTL)
    
    return {"session_id": session_id, "total": total, "success": len(final_results)}

