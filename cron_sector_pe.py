"""
cron_sector_pe.py — Cron job harian untuk menghitung Fair P/E dan Fair P/BV
per sektor IDX dari data aktual pasar.

Jadwal default: setiap hari kerja pukul 18:00 WIB (setelah bursa tutup 15:30).

Cara jalankan manual:
    python cron_sector_pe.py

Cara jadwalkan (APScheduler dijalankan dari app.py):
    Scheduler akan memanggil run_sector_cron() secara otomatis.
"""

import time
import statistics
import logging
from datetime import datetime, timezone

import yfinance as yf

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [CRON] %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("cron_sector_pe")


# ── Impor setelah logging siap ───────────────────────────────────────────────
def _get_sector_data():
    """Import lazy untuk menghindari circular import."""
    from app import SECTORS, SECTOR_MAP, _apply_currency_fix
    return SECTORS, SECTOR_MAP, _apply_currency_fix


def _fetch_price_eps_bvps(ticker_root: str, apply_fix_fn):
    """
    Ambil harga, EPS, BVPS satu saham dari Yahoo Finance.
    Return (price, eps, bvps) atau None jika gagal.
    """
    try:
        t  = yf.Ticker(ticker_root + ".JK")
        fi = t.fast_info
        price = fi.get("lastPrice") or fi.get("previousClose")
        if not price or price <= 0:
            return None

        eps = bvps = None
        try:
            inc = t.income_stmt
            bs  = t.balance_sheet
            if inc is not None and not inc.empty and bs is not None and not bs.empty:
                ni_keys = [k for k in inc.index
                           if "Net Income" in str(k)
                           and "Continuing" not in str(k)
                           and "Including"  not in str(k)]
                if not ni_keys:
                    ni_keys = [k for k in inc.index if "Net Income" in str(k)]
                sh_keys = [k for k in bs.index if "Ordinary Shares Number" in str(k)]
                eq_keys = [k for k in bs.index if "Common Stock Equity"    in str(k)]

                if ni_keys and sh_keys:
                    ni_s = inc.loc[ni_keys[0]]
                    sh   = float(bs.loc[sh_keys[0]].iloc[0])
                    if sh > 0:
                        eps = float(ni_s.iloc[0]) / sh

                if eq_keys and sh_keys:
                    sh  = float(bs.loc[sh_keys[0]].iloc[0])
                    if sh > 0:
                        bvps = float(bs.loc[eq_keys[0]].iloc[0]) / sh
        except Exception:
            pass

        # Koreksi kurs USD → IDR
        eps, bvps = apply_fix_fn(eps, bvps, float(price))
        return float(price), eps, bvps

    except Exception as e:
        log.debug(f"  {ticker_root}: {e}")
        return None


def run_sector_cron():
    """
    Hitung Fair P/E dan Fair P/BV per sektor, simpan ke tabel sector_metrics.
    Dipanggil oleh APScheduler dan bisa dipanggil manual.
    """
    from database import SessionLocal
    from models import SectorMetrics

    SECTORS, SECTOR_MAP, apply_fix_fn = _get_sector_data()

    # Balik map: sector_key → list ticker
    sector_tickers: dict[str, list[str]] = {}
    for tk, sec in SECTOR_MAP.items():
        sector_tickers.setdefault(sec, []).append(tk)

    db = SessionLocal()
    updated = 0

    try:
        for sec_key, tickers in sector_tickers.items():
            log.info(f"Menghitung sektor: {sec_key} ({len(tickers)} saham)")
            pe_list: list[float]  = []
            pbv_list: list[float] = []

            for tk in tickers:
                result = _fetch_price_eps_bvps(tk, apply_fix_fn)
                if not result:
                    continue
                price, eps, bvps = result

                if eps and eps > 0:
                    ratio = price / eps
                    # Filter outlier: P/E antara 2× dan 100×
                    if 2 <= ratio <= 100:
                        pe_list.append(ratio)

                if bvps and bvps > 0:
                    ratio = price / bvps
                    # Filter outlier: P/BV antara 0.1× dan 20×
                    if 0.1 <= ratio <= 20:
                        pbv_list.append(ratio)

                time.sleep(1.0)

            fair_pe  = round(statistics.median(pe_list),  2) if len(pe_list)  >= 3 else None
            fair_pbv = round(statistics.median(pbv_list), 2) if len(pbv_list) >= 3 else None

            log.info(
                f"  {sec_key}: fair P/E={fair_pe} "
                f"(n={len(pe_list)}), fair P/BV={fair_pbv} (n={len(pbv_list)})"
            )

            # Upsert ke sector_metrics
            row = db.get(SectorMetrics, sec_key)
            if row is None:
                row = SectorMetrics(sector_key=sec_key)
                db.add(row)

            row.fair_pe       = fair_pe
            row.fair_pbv      = fair_pbv
            row.median_pe     = fair_pe
            row.median_pbv    = fair_pbv
            row.sample_pe     = len(pe_list)
            row.sample_pbv    = len(pbv_list)
            row.calculated_at = datetime.now(timezone.utc)
            db.commit()
            updated += 1

    except Exception as e:
        log.error(f"Cron error: {e}")
        db.rollback()
    finally:
        db.close()

    log.info(f"Cron selesai. {updated} sektor diperbarui.")
    return updated


if __name__ == "__main__":
    log.info("Memulai cron_sector_pe secara manual...")
    run_sector_cron()
