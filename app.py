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

def CalculateBestModel(sector, eps, bvps, dps, price, eps_growth, methods):
    if sector in ("bank", "financial", "properti"):
        if "RIM" in methods and methods["RIM"]["is_applicable"]:
            return "RIM", "Sektor Finansial/Properti dengan data ekuitas solid cocok menggunakan RIM."
        if "PBV" in methods and methods["PBV"]["is_applicable"]:
            return "PBV", "Sektor Finansial/Properti dinilai dari nilai buku aset."
            
    if "SOTP" in methods and methods["SOTP"]["is_applicable"]:
        return "SOTP", "Emiten Holding/Konglomerasi dinilai berdasarkan Sum of the Parts."
        
    div_yield = (dps / price) if (dps and price) else 0
    if "DDM" in methods and methods["DDM"]["is_applicable"] and div_yield > 0.05:
        return "DDM", "Emiten membagikan dividen konsisten dengan yield menarik."
        
    if "DCF" in methods and methods["DCF"]["is_applicable"]:
        return "DCF", "Emiten memiliki arus kas bebas (FCF) positif dan stabil."
        
    if eps_growth and eps_growth > 15:
        if "PeterLynch" in methods and methods["PeterLynch"]["is_applicable"]:
            return "PeterLynch", "Emiten 'Growth Stock' dengan pertumbuhan EPS > 15%."
            
    if bvps and price and (price / bvps) < 1.2:
        if "Graham" in methods and methods["Graham"]["is_applicable"]:
            return "Graham", "Saham Value dengan valuasi PBV rendah."
            
    if eps_growth and 0 <= eps_growth <= 10:
        if "PE" in methods and methods["PE"]["is_applicable"]:
            return "PE", "Emiten Defensif dengan pertumbuhan laba stabil (0-10%)."
            
    if "EPV" in methods and methods["EPV"]["is_applicable"]:
        return "EPV", "Emiten mature/declining dengan asumsi pertumbuhan 0%."
        
    for m in ["PE", "PBV", "Graham", "DDM"]:
        if m in methods and methods[m]["is_applicable"]:
            return m, "Metode fallback karena metode utama tidak memenuhi syarat."
            
    return None, "Data fundamental tidak mencukupi untuk penilaian."


def extract_advanced_data(t):
    info = t.info or {}
    bs = t.balance_sheet
    is_ = t.financials
    
    shares_out = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
    if not shares_out and bs is not None and not bs.empty:
        sh_keys = [k for k in bs.index if "Ordinary Shares Number" in str(k)]
        if sh_keys:
            shares_out = float(bs.loc[sh_keys[0]].iloc[0])
            
    net_debt = info.get("totalDebt", 0) - info.get("totalCash", 0)
    if not info.get("totalDebt") and bs is not None and not bs.empty:
        debt_keys = [k for k in bs.index if "Total Debt" in str(k) or "Long Term Debt" in str(k)]
        cash_keys = [k for k in bs.index if "Cash And Cash Equivalents" in str(k)]
        d = sum([bs.loc[k].iloc[0] for k in debt_keys if not pd.isna(bs.loc[k].iloc[0])]) if debt_keys else 0
        c = sum([bs.loc[k].iloc[0] for k in cash_keys if not pd.isna(bs.loc[k].iloc[0])]) if cash_keys else 0
        net_debt = d - c
        
    beta = float(info.get("beta") or 1.0)
    beta = max(0.5, min(beta, 2.5))
    cost_of_equity = max(0.08, min(0.07 + beta * 0.06, 0.20))
    
    adjusted_earnings = None
    if is_ is not None and not is_.empty:
        ni_keys = [k for k in is_.index if "Net Income" in str(k)]
        if ni_keys:
            adjusted_earnings = float(is_.loc[ni_keys[0]].iloc[0])
            
    return {
        "shares_out": float(shares_out) if shares_out else None,
        "net_debt": float(net_debt) if net_debt else None,
        "cost_of_equity": cost_of_equity,
        "adjusted_earnings": float(adjusted_earnings) if adjusted_earnings else None,
    }


def all_methods_result(eps, bvps, dps, eps_growth, price, sector, t=None):
    methods = {}
    
    adv = extract_advanced_data(t) if t else {}
    shares_out = adv.get("shares_out")
    net_debt = adv.get("net_debt")
    cost_of_equity = adv.get("cost_of_equity")
    adjusted_earnings = adv.get("adjusted_earnings")
    
    # 1. Graham
    g_val = calc_graham(eps, bvps)
    methods["Graham"] = {
        "label": "Graham Number", "formula": "√(22.5 × EPS × BVPS)", "icon": "√",
        "valuation_price": round(g_val, 0) if g_val else None,
        "margin_of_safety": round((g_val - price) / price * 100, 2) if g_val and price else None,
        "is_applicable": bool(g_val is not None),
        "not_applicable_reason": "EPS/BVPS negatif" if g_val is None else None,
        "when_best": "Saham industri & manufaktur dengan EPS dan BVPS positif"
    }
    
    # 2. PBV
    pb_val = calc_pbv(bvps, sector)
    methods["PBV"] = {
        "label": "Price-to-Book (PBV)", "formula": "Fair P/BV × BVPS", "icon": "📚",
        "valuation_price": round(pb_val, 0) if pb_val else None,
        "margin_of_safety": round((pb_val - price) / price * 100, 2) if pb_val and price else None,
        "is_applicable": bool(pb_val is not None),
        "not_applicable_reason": "BVPS tidak tersedia" if pb_val is None else None,
        "when_best": "Perbankan & lembaga keuangan"
    }
    
    # 3. PE
    pe_val = calc_pe(eps, sector)
    methods["PE"] = {
        "label": "Price-to-Earnings (P/E)", "formula": "Fair P/E × EPS", "icon": "💹",
        "valuation_price": round(pe_val, 0) if pe_val else None,
        "margin_of_safety": round((pe_val - price) / price * 100, 2) if pe_val and price else None,
        "is_applicable": bool(pe_val is not None),
        "not_applicable_reason": "EPS negatif atau nol" if pe_val is None else None,
        "when_best": "Perusahaan profitabel dengan laba stabil"
    }
    
    # 4. DDM
    dd_val = calc_ddm(dps, eps)
    methods["DDM"] = {
        "label": "Dividend Discount (DDM)", "formula": "DPS × (1+g) / (r−g)", "icon": "💰",
        "valuation_price": round(dd_val, 0) if dd_val else None,
        "margin_of_safety": round((dd_val - price) / price * 100, 2) if dd_val and price else None,
        "is_applicable": bool(dd_val is not None),
        "not_applicable_reason": "Payout > 100% atau data dividen kosong" if dd_val is None else None,
        "when_best": "Saham dengan dividen yield konsisten"
    }
    
    # 5. Peter Lynch
    pl_val = calc_peter_lynch(eps, eps_growth)
    methods["PeterLynch"] = {
        "label": "Peter Lynch", "formula": "EPS × Growth EPS%", "icon": "📈",
        "valuation_price": round(pl_val, 0) if pl_val else None,
        "margin_of_safety": round((pl_val - price) / price * 100, 2) if pl_val and price else None,
        "is_applicable": bool(pl_val is not None),
        "not_applicable_reason": "Pertumbuhan EPS < 5% atau negatif" if pl_val is None else None,
        "when_best": "Saham growth dengan pertumbuhan EPS > 15%"
    }
    
    # 6. SOTP
    sotp_val = calc_sotp([], net_debt, shares_out) # Kita set kosong untuk fallback
    methods["SOTP"] = {
        "label": "Sum of the Parts", "formula": "Total EV Segmen - Net Debt", "icon": "🧩",
        "valuation_price": round(sotp_val, 0) if sotp_val else None,
        "margin_of_safety": round((sotp_val - price) / price * 100, 2) if sotp_val and price else None,
        "is_applicable": bool(sotp_val is not None),
        "not_applicable_reason": "Data segmen tidak tersedia" if sotp_val is None else None,
        "when_best": "Emiten holding atau konglomerasi"
    }
    
    # 7. EPV
    epv_val = calc_epv(adjusted_earnings, cost_of_equity, shares_out)
    methods["EPV"] = {
        "label": "Earnings Power Value", "formula": "Adj. Earnings / WACC", "icon": "🔋",
        "valuation_price": round(epv_val, 0) if epv_val else None,
        "margin_of_safety": round((epv_val - price) / price * 100, 2) if epv_val and price else None,
        "is_applicable": bool(epv_val is not None),
        "not_applicable_reason": "Earnings negatif atau WACC tidak valid" if epv_val is None else None,
        "when_best": "Emiten mature dengan asumsi pertumbuhan nol"
    }
    
    # 8. RIM
    rim_val = calc_rim(bvps, eps, cost_of_equity)
    methods["RIM"] = {
        "label": "Residual Income Model", "formula": "BVPS + PV(Residual Income)", "icon": "🛡️",
        "valuation_price": round(rim_val, 0) if rim_val else None,
        "margin_of_safety": round((rim_val - price) / price * 100, 2) if rim_val and price else None,
        "is_applicable": bool(rim_val is not None),
        "not_applicable_reason": "BVPS/EPS negatif" if rim_val is None else None,
        "when_best": "Fokus pada penciptaan nilai tambah (EVA)"
    }
    
    # 9. DCF (Moved from external to methods dict)
    dcf_res = calc_dcf(t, price, shares_out) if t else None
    dcf_val = dcf_res["intrinsic_value"] if dcf_res else None
    methods["DCF"] = {
        "label": "Discounted Cash Flow", "formula": "PV(FCF 5-10yr) + Terminal Value", "icon": "💵",
        "valuation_price": round(dcf_val, 0) if dcf_val else None,
        "margin_of_safety": round((dcf_val - price) / price * 100, 2) if dcf_val and price else None,
        "is_applicable": bool(dcf_val is not None),
        "not_applicable_reason": "FCF kronis negatif" if dcf_val is None else None,
        "when_best": "Emiten dengan arus kas positif stabil"
    }

    # Audit Flags
    audit_flags = []
    for k, v in methods.items():
        mos = v.get("margin_of_safety")
        if mos is not None:
            if mos > 500 or mos < -100:
                audit_flags.append(f"Anomali Data pada {k}: Valuasi rentan akibat laba satu waktu atau distorsi akuntansi (MoS {mos}%).")
                
    return methods, audit_flags


@app.route("/api/stock/<ticker_input>")
def api_stock(ticker_input):
    """Analisis lengkap satu saham — semua 5 metode valuasi."""
    ticker_root = ticker_input.upper().replace(".JK", "").strip()
    ticker_jk   = ticker_root + ".JK"
    sector_val  = SECTOR_MAP.get(ticker_root, "default")

    result = {
        "ticker": ticker_root, "ticker_jk": ticker_jk,
        "sector": sector_val, "status": "error",
        "error_msg": "", "price": None, "market_cap": None,
        "fundamentals": {"eps": None, "bvps": None, "dps": None, "eps_growth": None},
        "recommended_method": None, "recommendation_reason": "",
        "methods": {},
    }

    try:
        t  = yf.Ticker(ticker_jk)
        fi = t.fast_info
        price = fi.get("lastPrice") or fi.get("previousClose")
        if not price:
            result["error_msg"] = "Harga tidak tersedia di Yahoo Finance"
            return jsonify(result)
        result["price"] = float(price)
        info = t.info or {}
        result["name"] = info.get("longName") or info.get("shortName") or ticker_root
        result["market_cap"] = info.get("marketCap")

        # 2. Fundamental — gunakan shared helper (termasuk koreksi kurs USD→IDR)
        eps, bvps, dps, eps_growth, err = _fetch_fundamentals(t, float(price), ticker_root)
        if err:
            result["error_msg"] = err

        result["fundamentals"] = {
            "eps":        round(eps, 2)        if eps        is not None else None,
            "bvps":       round(bvps, 2)       if bvps       is not None else None,
            "dps":        round(dps, 2)        if dps        is not None else None,
            "eps_growth": round(eps_growth, 2) if eps_growth is not None else None,
            "pe_ratio":   round(float(price) / eps, 1) if price and eps and eps > 0 else None,
            "pb_ratio":   round(float(price) / bvps, 1) if price and bvps and bvps > 0 else None,
        }


        # Semua 5 metode
        methods, audit_flags = all_methods_result(eps, bvps, dps, eps_growth, price, sector_val, t)

        # Metode terbaik + alasan
        rec_method, rec_reason = CalculateBestModel(sector_val, eps, bvps, dps, price, eps_growth, methods)

        if rec_method and rec_method in methods:
            methods[rec_method]["is_recommended"] = True

        # Tandai semua lainnya tidak recommended
        for k in methods:
            methods[k].setdefault("is_recommended", False)

        # 3. DCF Valuation
        try:
            dcf = calc_dcf(t, float(price))
            result["dcf"] = dcf
        except Exception:
            result["dcf"] = None
            import traceback; traceback.print_exc()

        # 4. Technical Indicators
        try:
            tech = calc_technical(ticker_root)
            result["technical"] = tech
        except Exception:
            result["technical"] = None
            import traceback; traceback.print_exc()

        # 5. Accumulation Score
        try:
            acc = detect_accumulation(ticker_root)
            result["accumulation"] = acc
        except Exception:
            result["accumulation"] = None
            import traceback; traceback.print_exc()

        
        # Blended Valuation
        blended_fair_value = None
        intrinsic_models = ["DCF", "EPV", "RIM", "DDM", "SOTP"]
        relative_models = ["Graham", "PE", "PBV", "PeterLynch"]
        
        best_intrinsic = None
        if rec_method in intrinsic_models:
            best_intrinsic = methods[rec_method]["valuation_price"]
        else:
            for m in intrinsic_models:
                if methods.get(m, {}).get("is_applicable") and methods[m]["valuation_price"]:
                    best_intrinsic = methods[m]["valuation_price"]
                    break
                    
        best_relative = None
        if rec_method in relative_models:
            best_relative = methods[rec_method]["valuation_price"]
        else:
            for m in relative_models:
                if methods.get(m, {}).get("is_applicable") and methods[m]["valuation_price"]:
                    best_relative = methods[m]["valuation_price"]
                    break
                    
        if best_intrinsic and best_relative:
            blended_fair_value = round((0.6 * best_intrinsic) + (0.4 * best_relative), 2)
        elif best_intrinsic:
            blended_fair_value = best_intrinsic
        elif best_relative:
            blended_fair_value = best_relative

        result["blended_fair_value"]   = blended_fair_value
        result["audit_flags"]          = audit_flags

        result["methods"]              = methods
        result["recommended_method"]   = rec_method
        result["recommendation_reason"] = rec_reason
        result["status"]               = "ok"

    except Exception as e:
        result["error_msg"] = str(e)[:150]

    return jsonify(result)


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 4B: /api/technical/<ticker> — OHLCV + MA + RSI untuk TradingView
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/technical/<ticker>")
def api_technical(ticker: str):
    """Return OHLCV candles + MA50/MA200 series + RSI + fair prices."""
    ticker = ticker.upper().replace(".JK", "")
    period = request.args.get("period", "6mo")

    candles = get_ohlcv(ticker, period)
    ma_data = get_ma_series(ticker, period)
    tech    = calc_technical(ticker)
    acc     = detect_accumulation(ticker)

    return jsonify({
        "ticker":  ticker,
        "period":  period,
        "candles": candles,
        "ma50":    ma_data["ma50"],
        "ma200":   ma_data["ma200"],
        "indicators": tech,
        "accumulation": acc,
    })


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 5B: /api/heatmap — data treemap semua sektor
# ══════════════════════════════════════════════════════════════════════════════

@app.route("/api/heatmap")
def api_heatmap():
    """
    Return heatmap data.
    - Jika ada cache heatmap di Redis → pakai itu.
    - Jika ada hasil scan terakhir di Redis → pakai itu.
    - Jika force_refresh=1 atau tidak ada cache → fetch live (hanya 30 saham teratas per sektor).
    """
    force = request.args.get("force_refresh", "0") == "1"
    cache_key = "heatmap:v2:data"

    # 1. Coba cache heatmap
    if not force:
        cached = _redis.get(cache_key)
        if cached:
            return Response(cached, content_type="application/json")

    # 2. Coba ambil dari hasil scan_advanced terakhir yang masih ada di Redis
    #    Kita scan semua kunci scan:*:results
    scan_nodes = []
    try:
        all_result_keys = _redis.keys("scan:*:results")
        all_result_keys_sorted = sorted(all_result_keys, reverse=True)  # newest first
        seen_tickers = set()
        for rk in all_result_keys_sorted[:10]:  # cek 10 sesi terakhir
            raw = _redis.get(rk)
            if not raw:
                continue
            items = json.loads(raw)
            for item in items:
                tk = item.get("ticker")
                if not tk or tk in seen_tickers:
                    continue
                seen_tickers.add(tk)
                sec_key = SECTOR_MAP.get(tk, "industri")
                sec_label = SECTORS.get(sec_key, {}).get("label", sec_key)
                scan_nodes.append({
                    "ticker":     tk,
                    "sector_key": sec_key,
                    "sector":     sec_label,
                    "price":      item.get("current_price"),
                    "mos":        item.get("margin_of_safety"),
                    "method":     item.get("method_label") or item.get("method"),
                    "market_cap": 0,
                    "status":     item.get("status"),
                })
    except Exception:
        pass

    # 3. Jika ada data dari scan → gunakan itu
    if scan_nodes and not force:
        payload = {"nodes": scan_nodes, "source": "scan_cache",
                   "generated_at": datetime.now(timezone.utc).isoformat(),
                   "count": len(scan_nodes)}
        payload = clean_nan(payload)
        _redis.setex(cache_key, 3600, json.dumps(payload))
        return jsonify(payload)

    # 4. Fallback: fetch live max 5 saham per sektor (preview cepat)
    import concurrent.futures
    live_list = []
    for sec_key, sec_data in SECTORS.items():
        tks = sec_data["tickers"][:5]  # hanya top-5 per sektor
        for tk in tks:
            live_list.append((tk, sec_key, sec_data["label"]))

    def _fetch_one(args):
        tk, sec_key, sec_label = args
        try:
            r = fetch_stock(tk)
            fi = yf.Ticker(tk + ".JK").fast_info
            return {
                "ticker": tk, "sector_key": sec_key, "sector": sec_label,
                "price": r.get("current_price"), "mos": r.get("margin_of_safety"),
                "method": r.get("method_label"), "market_cap": int(fi.get("marketCap") or 0),
                "status": r.get("status"),
            }
        except Exception:
            return {"ticker": tk, "sector_key": sec_key, "sector": sec_label,
                    "mos": None, "market_cap": 0, "status": "error"}

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as ex:
        live_results = list(ex.map(_fetch_one, live_list))

    payload = {"nodes": live_results, "source": "live",
               "generated_at": datetime.now(timezone.utc).isoformat(),
               "count": len(live_results)}
    payload = clean_nan(payload)
    _redis.setex(cache_key, 1800, json.dumps(payload))
    return jsonify(payload)


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 5C: /api/compare — side-by-side comparison
# ══════════════════════════════════════════════════════════════════════════════

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
