import time, json, io, csv, uuid
from collections import OrderedDict
from datetime import datetime, timezone
from flask import Flask, jsonify, request, Response, stream_with_context
from flask_cors import CORS
import redis as redis_lib
from apscheduler.schedulers.background import BackgroundScheduler

# ── Import semua logika bisnis dari fetch_engine (bebas Flask) ───────────────
from fetch_engine import (
    SECTOR_MAP as _FE_SECTOR_MAP,
    SECTOR_FAIR_PE, SECTOR_FAIR_PBV,
    calc_graham, calc_pe, calc_pbv, calc_ddm, calc_peter_lynch,
    fetch_stock,
    _fetch_fundamentals,
    # Fase 4: DCF + Technical + Accumulation
    calc_dcf, calc_technical, detect_accumulation, calc_sotp, calc_epv, calc_rim,
    get_ohlcv, get_ma_series,
)
import yfinance as yf
import pandas as pd
import os as _os

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
CORS(app)


# ══════════════════════════════════════════════════════════════════════════════
#  DAFTAR SAHAM IDX — Load dari idx_tickers.json (687+ saham)
# ══════════════════════════════════════════════════════════════════════════════

_SECTOR_LABELS = {
    "keuangan":          ("Keuangan & Perbankan", "🏦"),
    "energi_batubara":   ("Energi & Batubara",    "⚡"),
    "tambang_logam":     ("Tambang Logam & Mineral","⛏️"),
    "konsumer_primer":   ("Konsumer Primer",       "🛒"),
    "properti":          ("Properti & Real Estat", "🏢"),
    "kesehatan":         ("Kesehatan & Farmasi",   "🏥"),
    "teknologi_media":   ("Teknologi & Media",     "💻"),
    "industri":          ("Industri & Manufaktur", "🏭"),
    "pertanian":         ("Pertanian & Perkebunan","🌿"),
    "transportasi":      ("Transportasi & Logistik","🚢"),
    "konstruksi":        ("Konstruksi",            "🏗️"),
    "infrastruktur_telko":("Infrastruktur & Telko","📡"),
    "konsumer_ritel":    ("Ritel & Gaya Hidup",    "🏪"),
}

def _build_sectors_from_json():
    """Load 687+ IDX tickers dari idx_tickers.json ke SECTORS OrderedDict."""
    _dir = _os.path.dirname(_os.path.abspath(__file__))
    _path = _os.path.join(_dir, "idx_tickers.json")
    try:
        with open(_path, encoding="utf-8") as f:
            data = json.load(f)
        by_sector = data.get("by_sector", {})
        result = OrderedDict()
        for sec_key, tickers in sorted(by_sector.items()):
            label, icon = _SECTOR_LABELS.get(sec_key, (sec_key.replace("_", " ").title(), "📊"))
            result[sec_key] = {"label": label, "icon": icon, "tickers": sorted(tickers)}
        print(f"[IDX] Loaded {sum(len(v['tickers']) for v in result.values())} tickers dari idx_tickers.json")
        return result, data.get("tickers", {})
    except Exception as e:
        print(f"[IDX] Gagal load idx_tickers.json: {e} — pakai fallback")
        return None, {}

_sectors_result, IDX_TICKER_INFO = _build_sectors_from_json()

if _sectors_result:
    SECTORS   = _sectors_result
    SECTOR_MAP = {sym: info.get("sector", "industri") for sym, info in IDX_TICKER_INFO.items()}
    print(f"[IDX] SECTORS aktif: {sum(len(v['tickers']) for v in SECTORS.values())} tickers di {len(SECTORS)} sektor")
else:
    # Fallback minimal jika idx_tickers.json tidak tersedia
    SECTOR_MAP = _FE_SECTOR_MAP
    SECTORS = OrderedDict([
        ("keuangan",        {"label":"Keuangan & Perbankan","icon":"🏦","tickers":["BBCA","BBRI","BMRI","BBNI","BRIS","BDMN","NISP","MEGA","BTPN","BFIN","ADMF","ARTO","BJBR","BJTM","BNGA","MCOR","BSIM","BTPS","PNLF","AGRO"]}),
        ("konsumer_primer", {"label":"Konsumer Primer","icon":"🛒","tickers":["UNVR","ICBP","INDF","HMSP","CPIN","GGRM","DLTA","ULTJ","MYOR","SIDO","JPFA","ROTI","SKLT","GOOD","HOKI","BUDI","WIIM","MLBI","CAMP","AISA"]}),
        ("industri",        {"label":"Industri & Manufaktur","icon":"🏭","tickers":["ASII","UNTR","SMGR","SMSM","HEXA","TKIM","INKP","ISSP","ARNA","LION","TOTO","KBLI","FASW","BTON","INAI","MLIA","NIKL","ALKA","DPNS","SRIL","EKAD"]}),
        ("energi_batubara", {"label":"Energi & Batubara","icon":"⚡","tickers":["ADRO","BYAN","PTBA","ITMG","HRUM","BSSR","INDY","KKGI","ESSA","PGAS","PGEO","MEDC","ELSA","AKRA","DEWA","ENRG"]}),
        ("properti",        {"label":"Properti & Real Estat","icon":"🏢","tickers":["PWON","CTRA","SMRA","KIJA","BSDE","DMAS","LPKR","JRPT","MDLN","MTLA","SRTG","BKSL","PANI","APLN","ASRI","BEST","DILD","PPRO","RODA"]}),
        ("teknologi_media", {"label":"Teknologi & Media","icon":"💻","tickers":["GOTO","BUKA","EMTK","MNCN","FILM","ARTO","DMMX","MCAS","KREN","MTDL","MLPT","TLKM","EXCL","ISAT","WIFI","FREN","DCII"]}),
        ("kesehatan",       {"label":"Kesehatan & Farmasi","icon":"🏥","tickers":["KLBF","HEAL","MIKA","SOHO","DVLA","TSPC","PEHA","SCPI","PYFA","INAF","KAEF","MERK","SQBI"]}),
        ("tambang_logam",   {"label":"Tambang Logam & Mineral","icon":"⛏️","tickers":["MDKA","ANTM","INCO","TINS","BRMS","MBMA","NCKL","AMMN","PSAB","SMMT"]}),
        ("pertanian",       {"label":"Pertanian & Perkebunan","icon":"🌿","tickers":["AALI","SGRO","SSMS","TAPG","LSIP","BWPT","ANJT","DSNG","PALP","TBLA","UNSP","GZCO"]}),
        ("transportasi",    {"label":"Transportasi & Logistik","icon":"🚢","tickers":["BIRD","BULL","SMDR","MBSS","NELY","TMAS","SAFE","DEAL","LEAD","WINS","TPMA","SHIP","SOCI"]}),
        ("konstruksi",      {"label":"Konstruksi","icon":"🏗️","tickers":["WIKA","WSKT","ADHI","PTPP","NRCA","ACST","IDPR","MTRA","TOTL"]}),
        ("infrastruktur_telko",{"label":"Infrastruktur & Telko","icon":"📡","tickers":["TOWR","TBIG","JSMR","LINK","CENT","META"]}),
        ("konsumer_ritel",  {"label":"Ritel & Gaya Hidup","icon":"🏪","tickers":["AMRT","ACES","LPPF","RALS","MAPI","MIDI","ERAA","MAPA","HERO","RANC","SONA"]}),
    ])



# ══════════════════════════════════════════════════════════════════════════════
#  REDIS CLIENT
# ══════════════════════════════════════════════════════════════════════════════

_redis = redis_lib.Redis(host="localhost", port=6379, db=0, decode_responses=True)
SCAN_TTL = 7200  # 2 jam

def _rkey(sid: str, suffix: str) -> str:
    return f"scan:{sid}:{suffix}"





# ══════════════════════════════════════════════════════════════════════════════
#  FASE 3: LOAD SECTOR METRICS DARI POSTGRESQL
# ══════════════════════════════════════════════════════════════════════════════

def _load_sector_metrics_from_db():
    """
    Saat startup, baca fair P/E dan P/BV per sektor dari PostgreSQL.
    Override SECTOR_FAIR_PE dan SECTOR_FAIR_PBV jika data tidak stale.
    """
    try:
        from database import SessionLocal
        from models import SectorMetrics
        db = SessionLocal()
        try:
            rows = db.query(SectorMetrics).all()
            overridden = 0
            for row in rows:
                if row.is_stale():
                    continue
                if row.fair_pe and row.sector_key in SECTOR_FAIR_PE:
                    SECTOR_FAIR_PE[row.sector_key] = row.fair_pe
                    overridden += 1
                if row.fair_pbv and row.sector_key in SECTOR_FAIR_PBV:
                    SECTOR_FAIR_PBV[row.sector_key] = row.fair_pbv
            if overridden:
                print(f"[SECTOR] {overridden} sektor di-override dari DB")
            else:
                print("[SECTOR] Pakai nilai hardcoded (DB kosong/stale)")
        finally:
            db.close()
    except Exception as e:
        print(f"[SECTOR] Gagal load dari DB: {e} — pakai hardcoded")


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return jsonify({"status": "API Server Running", "frontend": "Next.js on port 3000"})


# ── Penjelasan kenapa suatu metode dipilih ──────────────────────────────────




@app.route("/api/stock/<ticker_input>")
def api_stock(ticker_input):
    """Analisis lengkap satu saham — menggunakan fetch_stock dari engine."""
    ticker_root = ticker_input.upper().replace(".JK", "").strip()
    
    # 1. Gunakan fetch_stock sebagai sumber utama
    from fetch_engine import fetch_stock, calc_technical, detect_accumulation, calc_dcf
    
    data = fetch_stock(ticker_root)
    
    # Jika gagal total
    if data.get("status") == "error":
        return jsonify(clean_nan(data))
        
    price = data.get("current_price")
    eps = data.get("eps")
    bvps = data.get("bvps")
    
    # 2. Rekonstruksi struktur data khusus untuk UI Stock Detail
    data["fundamentals"] = {
        "eps": eps,
        "bvps": bvps,
        "dps": data.get("dps"),
        "eps_growth": data.get("eps_growth"),
        "pe_ratio": round(price / eps, 1) if price and eps and eps > 0 else None,
        "pb_ratio": round(price / bvps, 1) if price and bvps and bvps > 0 else None,
    }
    
    data["price"] = price # UI detail ekspektasi key 'price'
    
    try:
        t = yf.Ticker(data["ticker_jk"])
        info = t.info or {}
        data["name"] = info.get("longName") or info.get("shortName") or ticker_root
        data["market_cap"] = info.get("marketCap")
    except Exception:
        data["name"] = ticker_root
        data["market_cap"] = None
        
    # 3. Tambahkan advanced data yang tidak ada di fetch_stock dasar
    try:
        data["dcf"] = calc_dcf(yf.Ticker(data["ticker_jk"]), float(price)) if price else None
    except Exception:
        data["dcf"] = None
        
    try:
        data["technical"] = calc_technical(ticker_root)
    except Exception:
        data["technical"] = None
        
    try:
        data["accumulation"] = detect_accumulation(ticker_root)
    except Exception:
        data["accumulation"] = None
        
    return jsonify(clean_nan(data))

@app.route("/api/compare")
def api_compare():
    """Return full analysis for 2-4 tickers side by side."""
    raw = request.args.get("tickers", "")
    tickers = [t.strip().upper() for t in raw.split(",") if t.strip()][:4]
    if not tickers:
        return jsonify({"error": "Parameter tickers wajib diisi"}), 400

    import concurrent.futures

    def _fetch_compare_one(tk):
        try:
            ticker_jk  = tk + ".JK"
            t_obj      = yf.Ticker(ticker_jk)
            fi         = t_obj.fast_info
            price      = fi.get("lastPrice") or fi.get("previousClose")
            sector_val = SECTOR_MAP.get(tk, "default")

            eps, bvps, dps, eps_growth, _ = _fetch_fundamentals(t_obj, float(price or 0), tk)

            methods, audit_flags = all_methods_result(eps, bvps, dps, eps_growth, float(price or 0), sector_val, t_obj)
            rec_method, rec_reason = CalculateBestModel(sector_val, eps, bvps, dps, float(price or 0), eps_growth, methods)
            
            dcf  = calc_dcf(t_obj, float(price or 0)) if "DCF" not in methods else methods["DCF"].get("valuation_price")
            tech = calc_technical(tk)
            acc  = detect_accumulation(tk)

            info = t_obj.info or {}
            return {
                "ticker":      tk,
                "name":        info.get("longName") or info.get("shortName") or tk,
                "sector":      sector_val,
                "price":       float(price) if price else None,
                "market_cap":  info.get("marketCap"),
                "fundamentals": {
                    "eps":        round(eps, 2)        if eps        is not None else None,
                    "bvps":       round(bvps, 2)       if bvps       is not None else None,
                    "dps":        round(dps, 2)        if dps        is not None else None,
                    "eps_growth": round(eps_growth, 1) if eps_growth is not None else None,
                    "pe_ratio":   round(price / eps, 1) if price and eps and eps > 0 else None,
                    "pb_ratio":   round(price / bvps, 1) if price and bvps and bvps > 0 else None,
                },
                "methods":        methods,
                "recommended_method": rec_method,
                "recommendation_reason": rec_reason,
                "dcf":            dcf,
                "technical":      tech,
                "accumulation":   acc,
            }
        except Exception as e:
            return {"ticker": tk, "error": str(e)[:100]}

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        data = list(ex.map(_fetch_compare_one, tickers))

    return jsonify({"tickers": tickers, "data": data})


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 5: HALAMAN BARU
# ══════════════════════════════════════════════════════════════════════════════

# HTML routes removed, frontend handled by Next.js



@app.route("/api/sectors")
def get_sectors():
    """Kembalikan daftar sektor + jumlah ticker (urutan terjaga)."""
    data = OrderedDict(
        (key, {
            "label":   val["label"],
            "icon":    val["icon"],
            "count":   len(val["tickers"]),
            "tickers": val["tickers"],
        })
        for key, val in SECTORS.items()
    )
    return Response(
        json.dumps(data, ensure_ascii=False),
        content_type="application/json; charset=utf-8"
    )



@app.route("/api/tickers")
def get_tickers():
    sector = request.args.get("sector", "keuangan")
    sec    = SECTORS.get(sector)
    if not sec:
        return jsonify({"error": "Sektor tidak ditemukan"}), 404
    return jsonify({"tickers": sec["tickers"], "label": sec["label"], "icon": sec["icon"]})

@app.route("/api/scan-advanced", methods=["POST"])
def api_scan_advanced():
    req = request.get_json() or {}
    mode = req.get("mode", "sector")
    ticker = req.get("ticker", "").strip().upper()

    # Prevent concurrent scans
    active_sid = _redis.get("scan:active_session")
    if active_sid:
        status = _redis.hget(_rkey(active_sid, "meta"), "status")
        if status and status not in ("done", "cancelled", "error"):
            return jsonify({"error": "Sistem sedang memproses scan lain. Silakan tunggu atau batalkan melalui indikator di kiri bawah."}), 400

    tickers_to_scan = []
    if mode == "single" and ticker:
        ticker = ticker.replace(".JK", "")
        tickers_to_scan = [ticker]
    else:
        for s_data in SECTORS.values():
            tickers_to_scan.extend(s_data["tickers"])
            
    if not tickers_to_scan:
        return jsonify({"error": "Tidak ada saham untuk di-scan"}), 400

    import uuid
    session_id = str(uuid.uuid4())

    from tasks import scan_advanced
    task = scan_advanced.delay(session_id, tickers_to_scan)

    # Inisialisasi meta & set as active global session
    _redis.hset(_rkey(session_id, "meta"), mapping={
        "status": "queued",
        "total": len(tickers_to_scan),
        "done": 0,
        "celery_task_id": task.id,
        "mode": mode,
        "ticker": ticker if mode == "single" else "Semua Sektor"
    })
    _redis.expire(_rkey(session_id, "meta"), SCAN_TTL)
    _redis.set("scan:active_session", session_id)

    return jsonify({"session_id": session_id})

@app.route("/api/global-status")
def global_status():
    """Mengembalikan status task scan global (untuk memonitor apakah celery macet)."""
    active_sid = _redis.get("scan:active_session")
    if not active_sid:
        return jsonify({"active": False})
    
    meta_key = _rkey(active_sid, "meta")
    meta = _redis.hgetall(meta_key)
    status = meta.get("status")
    
    if not status:
        return jsonify({"active": False})
        
    return jsonify({
        "active": True,
        "session_id": active_sid,
        "status": status,
        "progress_count": int(meta.get("done", 0)),
        "total": int(meta.get("total", 0)),
        "mode": meta.get("mode", ""),
        "ticker": meta.get("ticker", "")
    })

@app.route("/api/dismiss-scan", methods=["POST"])
def dismiss_scan():
    """Menghapus active_session global agar overlay tertutup."""
    _redis.delete("scan:active_session")
    return jsonify({"success": True})

@app.route("/api/cancel-scan", methods=["POST"])
def cancel_scan():
    """Membatalkan (revoke) task Celery yang sedang aktif dengan Graceful Cancellation."""
    req = request.get_json() or {}
    sid = req.get("session_id")
    if not sid:
        sid = _redis.get("scan:active_session")
        if not sid:
            return jsonify({"error": "Tidak ada task aktif"}), 400
            
    meta_key = _rkey(sid, "meta")
    
    # Set bendera 'cancelled' spesifik session ini
    _redis.hset(meta_key, "cancelled", "1")
    _redis.hset(meta_key, "status", "cancelled")
    
    # Set bendera global kill-switch selama 10 detik agar worker apa pun yang sedang jalan ikut mati
    _redis.setex("scan:force_cancel_all", 10, "1")
    
    # Push cancel event to SSE
    ev_key = _rkey(sid, "events")
    _redis.rpush(ev_key, json.dumps({"type": "error", "message": "Dibatalkan oleh pengguna"}))
    
    # Fallback: purge queue dan revoke
    task_id = _redis.hget(meta_key, "celery_task_id")
    from celery_app import celery
    try:
        celery.control.purge()
        if task_id:
            celery.control.revoke(task_id, terminate=True, signal='SIGTERM')
    except:
        pass
            
    _redis.delete("scan:active_session")
    return jsonify({"success": True})

@app.route("/api/scan", methods=["POST"])
def start_scan():
    """Fase 1: Dispatch Celery task; kembalikan session_id unik per request."""
    
    # Prevent concurrent scans
    active_sid = _redis.get("scan:active_session")
    if active_sid:
        status = _redis.hget(_rkey(active_sid, "meta"), "status")
        if status and status not in ("done", "cancelled", "error"):
            return jsonify({"error": "Sistem sedang memproses scan lain. Silakan tunggu atau batalkan melalui indikator di kiri bawah."}), 400

    from tasks import scan_sector  # import lazy agar tidak circular saat startup

    tickers = None

    # Prioritas 1: CSV upload
    if "file" in request.files:
        f = request.files["file"]
        if f and f.filename and f.filename.endswith(".csv"):
            try:
                stream   = io.StringIO(f.stream.read().decode("utf-8"))
                uploaded = []
                for row in csv.reader(stream):
                    for cell in row:
                        val = cell.strip().upper().replace(".JK","")
                        if val and val.replace("-","").isalpha():
                            uploaded.append(val)
                if uploaded:
                    tickers = list(dict.fromkeys(uploaded))
            except Exception as e:
                return jsonify({"error": f"Gagal membaca CSV: {e}"}), 400

    # Prioritas 2: Sektor
    if tickers is None:
        sector = request.form.get("sector", "keuangan")
        sec    = SECTORS.get(sector)
        if not sec:
            return jsonify({"error": "Sektor tidak valid"}), 400
        tickers = sec["tickers"].copy()

    # Generate session ID unik per user/request
    sid = str(uuid.uuid4())

    # Inisialisasi meta di Redis
    _redis.hset(_rkey(sid, "meta"), mapping={
        "status": "queued", "total": len(tickers), "done": 0
    })
    _redis.expire(_rkey(sid, "meta"), SCAN_TTL)

    # Kirim ke Celery worker
    scan_sector.delay(sid, tickers)

    return jsonify({"status": "started", "session_id": sid, "total": len(tickers)})


@app.route("/api/stream")
@app.route("/api/events")
def sse_events():
    """SSE stream per session_id — alias /api/stream dan /api/events."""
    # Accept both ?session_id= (Next.js) and ?sid= (legacy)
    sid        = request.args.get("session_id") or request.args.get("sid", "")
    last_index = int(request.args.get("from", 0))

    if not sid:
        # Fallback legacy: tidak ada sid → kirim keepalive saja
        def _empty():
            yield ": no session\n\n"
        return Response(stream_with_context(_empty()), content_type="text/event-stream")

    def generate():
        sent, last_ka = last_index, time.time()
        ev_key  = _rkey(sid, "events")
        meta_key = _rkey(sid, "meta")
        while True:
            total_in_list = _redis.llen(ev_key)
            while sent < total_in_list:
                raw = _redis.lindex(ev_key, sent)
                if raw:
                    yield f"data: {raw}\n\n"
                sent += 1

            # Cek status: apakah task selesai?
            status = _redis.hget(meta_key, "status")
            if status == "done" and sent >= total_in_list:
                break

            if time.time() - last_ka > 15:
                yield ": keepalive\n\n"
                last_ka = time.time()
            time.sleep(0.4)

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={"Cache-Control":"no-cache", "X-Accel-Buffering":"no", "Connection":"keep-alive"},
    )


import math

def clean_nan(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    elif isinstance(obj, dict):
        return {k: clean_nan(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [clean_nan(v) for v in obj]
    return obj

@app.route("/api/results")
def get_results():
    """Hasil scan dari Redis — accept session_id (Next.js) atau sid (legacy)."""
    sid = request.args.get("session_id") or request.args.get("sid", "")
    if not sid:
        return jsonify({"running": False, "results": []})

    meta_key   = _rkey(sid, "meta")
    result_key = _rkey(sid, "results")

    status  = _redis.hget(meta_key, "status") or "unknown"
    running = status not in ("done", "unknown")

    raw     = _redis.get(result_key)
    results = json.loads(raw) if raw else []
    
    # Fix Invalid JSON di Frontend (NaN / Infinity -> null)
    results = clean_nan(results)
    
    return jsonify({"running": running, "results": results, "status": status})


@app.route("/api/status")
def get_status():
    """Status scan dari Redis meta hash — accept session_id atau sid."""
    sid = request.args.get("session_id") or request.args.get("sid", "")
    if not sid:
        return jsonify({"running": False, "progress_count": 0, "status": "unknown"})

    meta_key = _rkey(sid, "meta")
    meta     = _redis.hgetall(meta_key)
    running  = meta.get("status") not in ("done", "unknown", None)
    return jsonify({
        "running":        running,
        "status":         meta.get("status", "unknown"),
        "progress_count": int(meta.get("done", 0)),
        "total":          int(meta.get("total", 0)),
        "ticker":         meta.get("ticker", ""),
    })


# ══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ══════════════════════════════════════════════════════════════════════════════

def _startup():
    """Inisialisasi DB schema, load sector metrics, dan jadwalkan cron."""
    # Init PostgreSQL schema
    try:
        from database import init_db
        init_db()
    except Exception as e:
        print(f"[STARTUP] DB init warning: {e}")

    # Fase 3: Load sector fair PE/PBV dari DB
    _load_sector_metrics_from_db()

    # Fase 3: Jadwalkan cron harian pukul 18:00 WIB (hari kerja)
    try:
        from cron_sector_pe import run_sector_cron
        scheduler = BackgroundScheduler(timezone="Asia/Jakarta")
        scheduler.add_job(
            run_sector_cron,
            trigger="cron",
            day_of_week="mon-fri",
            hour=18, minute=0,
            id="sector_pe_cron",
            replace_existing=True,
        )
        scheduler.start()
        print("[SCHEDULER] Cron sector PE aktif — setiap hari kerja 18:00 WIB")
    except Exception as e:
        print(f"[SCHEDULER] Warning: {e}")


if __name__ == "__main__":
    _startup()
    app.run(debug=False, port=5050, threaded=True)
