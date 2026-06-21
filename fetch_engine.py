"""
fetch_engine.py — Logika bisnis fetch saham + valuasi.

Modul ini TIDAK mengimpor Flask sehingga aman diimpor oleh:
- app.py      (Flask web server)
- tasks.py    (Celery worker)
- cron_sector_pe.py (cron job)

Semua data (SECTORS, SECTOR_MAP, calc_*, pick_method, fetch_stock, dll.)
dipusatkan di sini untuk menghindari duplikasi dan circular import.
"""

import math
import threading
from collections import OrderedDict
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf
import requests

# ══════════════════════════════════════════════════════════════════════════════
#  TRADINGVIEW SCANNER FALLBACK
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_from_tradingview(ticker_root: str):
    """
    Mengambil data fundamental dari TradingView Scanner (tanpa API key).
    Mengembalikan dict: { "price": ..., "eps": ..., "bvps": ..., "dps": ... }
    atau None jika gagal.
    """
    try:
        url = 'https://scanner.tradingview.com/indonesia/scan'
        payload = {
            'symbols': {'tickers': [f'IDX:{ticker_root.upper()}']},
            'columns': ['close', 'earnings_per_share_basic_ttm', 'price_book_ratio', 'dividend_yield_recent']
        }
        r = requests.post(url, json=payload, timeout=5)
        if r.status_code == 200:
            data = r.json().get('data', [])
            if data and len(data) > 0:
                d = data[0].get('d', [])
                if len(d) >= 4:
                    price, eps, pb, div_yield = d[0], d[1], d[2], d[3]
                    bvps = None
                    if price and pb and pb > 0:
                        bvps = price / pb
                    dps = None
                    if price and div_yield and div_yield > 0:
                        dps = (div_yield / 100) * price
                    return {
                        "price": price,
                        "eps": eps,
                        "bvps": bvps,
                        "dps": dps
                    }
    except Exception as e:
        print(f"[TRADINGVIEW] Gagal mengambil data untuk {ticker_root}: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
#  KURS USD/IDR — di-refresh saat modul pertama kali diload
# ══════════════════════════════════════════════════════════════════════════════

USD_IDR_RATE: float = 16_200.0  # fallback default

def _refresh_usd_idr():
    global USD_IDR_RATE
    try:
        rate = yf.Ticker("USDIDR=X").fast_info.get("lastPrice")
        if rate and 13_000 < rate < 22_000:
            USD_IDR_RATE = round(float(rate), 2)
            print(f"[ENGINE] USD/IDR: {USD_IDR_RATE}")
    except Exception as exc:
        print(f"[ENGINE] Gagal ambil USD/IDR: {exc}")

threading.Thread(target=_refresh_usd_idr, daemon=True).start()


# ══════════════════════════════════════════════════════════════════════════════
#  DAFTAR SAHAM PER SEKTOR IDX
# ══════════════════════════════════════════════════════════════════════════════

SECTORS = OrderedDict([
    ("keuangan", {
        "label": "Keuangan", "icon": "🏦",
        "tickers": [
            "BBCA","BBRI","BMRI","BBNI","BRIS","ARTO",
            "BDMN","BJBR","BJTM","BNII","NISP","BNGA",
            "MEGA","BTPN","BTPS","PNLF","ADMF","BFIN",
            "AGRO","MCOR","BMAS","BBKP","BSIM",
        ],
    }),
    ("konsumer_primer", {
        "label": "Konsumer Primer", "icon": "🛒",
        "tickers": [
            "UNVR","ICBP","INDF","HMSP","CPIN",
            "GGRM","DLTA","MLBI","ULTJ","MYOR",
            "SIDO","WIIM","JPFA","ROTI","SKLT",
            "AISA","BUDI","GOOD","HOKI","CAMP",
        ],
    }),
    ("konsumer_ritel", {
        "label": "Ritel & Gaya Hidup", "icon": "🏪",
        "tickers": [
            "AMRT","ACES","LPPF","RALS","MAPI",
            "MIDI","ERAA","MAPA","HERO","RANC",
            "SONA","KOIN",
        ],
    }),
    ("energi_batubara", {
        "label": "Energi & Batubara", "icon": "⚡",
        "tickers": [
            "ADRO","BYAN","PTBA","ITMG","HRUM",
            "BSSR","INDY","KKGI","ESSA","PGAS",
            "PGEO","MEDC","ELSA","AKRA","DEWA",
            "ENRG","RATU",
        ],
    }),
    ("tambang_logam", {
        "label": "Tambang Logam & Mineral", "icon": "⛏️",
        "tickers": [
            "MDKA","ANTM","INCO","TINS","BRMS",
            "MBMA","NCKL","AMMN","HRUM","PSAB",
            "ITMG","SMMT",
        ],
    }),
    ("industri", {
        "label": "Industri & Manufaktur", "icon": "🏭",
        "tickers": [
            "ASII","UNTR","SMGR","SMSM","HEXA",
            "TKIM","INKP","ISSP","ARNA","EKAD",
            "LION","TOTO","KBLI","FASW","BTON",
            "INAI","MLIA","NIKL","ALKA","DPNS",
            "SRIL","PBRX","ARGO","CNTB",
        ],
    }),
    ("properti", {
        "label": "Properti & Real Estat", "icon": "🏢",
        "tickers": [
            "PWON","CTRA","SMRA","KIJA","BSDE",
            "DMAS","LPKR","JRPT","MDLN","MTLA",
            "SRTG","BKSL","PANI","APLN","ASRI",
            "BEST","DILD","GMTD","PPRO","RODA",
        ],
    }),
    ("konstruksi", {
        "label": "Konstruksi", "icon": "🏗️",
        "tickers": [
            "WIKA","WSKT","ADHI","PTPP","NRCA",
            "ACST","IDPR","MTRA","PBSA","TOTL",
        ],
    }),
    ("infrastruktur_telko", {
        "label": "Infrastruktur & Telko", "icon": "📡",
        "tickers": [
            "TLKM","EXCL","ISAT","TOWR","TBIG",
            "WIFI","JSMR","FREN","LINK","CENT","META",
        ],
    }),
    ("teknologi_media", {
        "label": "Teknologi & Media", "icon": "💻",
        "tickers": [
            "GOTO","BUKA","EMTK","MNCN","FILM",
            "ARTO","DMMX","MCAS","KREN","MTDL",
            "MLPT","JSKY",
        ],
    }),
    ("kesehatan", {
        "label": "Kesehatan & Farmasi", "icon": "🏥",
        "tickers": [
            "KLBF","HEAL","MIKA","SOHO","DVLA",
            "TSPC","PEHA","SCPI","PYFA","INAF",
            "KAEF","MERK","SQBI","SIDO",
        ],
    }),
    ("pertanian", {
        "label": "Pertanian & Perkebunan", "icon": "🌿",
        "tickers": [
            "AALI","SGRO","SSMS","TAPG","LSIP",
            "BWPT","ANJT","DSNG","PALP","TBLA",
            "UNSP","GZCO",
        ],
    }),
    ("transportasi", {
        "label": "Transportasi & Logistik", "icon": "🚢",
        "tickers": [
            "BIRD","BULL","SMDR","MBSS","NELY",
            "TMAS","SAFE","DEAL","LEAD","WINS",
            "TPMA","SHIP",
        ],
    }),
])

# Lookup ticker → sektor UI
TICKER_TO_SECTOR_UI: dict[str, str] = {}
for _sk, _sd in SECTORS.items():
    for _tk in _sd["tickers"]:
        TICKER_TO_SECTOR_UI[_tk] = _sk

# Lookup ticker → sektor valuasi
SECTOR_MAP: dict[str, str] = {
    "BBCA":"bank","BBRI":"bank","BMRI":"bank","BBNI":"bank","BRIS":"bank",
    "ARTO":"bank","BDMN":"bank","BJBR":"bank","BJTM":"bank","BNII":"bank",
    "NISP":"bank","BNGA":"bank","MEGA":"bank","BTPN":"bank","BTPS":"bank",
    "PNLF":"financial","ADMF":"financial","BFIN":"financial","AGRO":"bank",
    "MCOR":"bank","BMAS":"bank","BBKP":"bank","BSIM":"bank",
    "UNVR":"consumer","ICBP":"consumer","INDF":"consumer","HMSP":"consumer",
    "CPIN":"consumer","GGRM":"consumer","DLTA":"consumer","MLBI":"consumer",
    "ULTJ":"consumer","MYOR":"consumer","SIDO":"consumer","WIIM":"consumer",
    "JPFA":"consumer","ROTI":"consumer","SKLT":"consumer","AISA":"consumer",
    "BUDI":"consumer","GOOD":"consumer","HOKI":"consumer","CAMP":"consumer",
    "AMRT":"retail","ACES":"retail","LPPF":"retail","RALS":"retail",
    "MAPI":"retail","MIDI":"retail","ERAA":"retail","MAPA":"retail",
    "HERO":"retail","RANC":"retail","SONA":"retail","KOIN":"retail",
    "ADRO":"mining","BYAN":"mining","PTBA":"mining","ITMG":"mining",
    "HRUM":"mining","BSSR":"mining","INDY":"mining","KKGI":"mining",
    "ESSA":"energy","PGAS":"utilities","PGEO":"energy","MEDC":"energy",
    "ELSA":"energy","AKRA":"energy","DEWA":"energy","ENRG":"energy","RATU":"energy",
    "MDKA":"mining","ANTM":"mining","INCO":"mining","TINS":"mining",
    "BRMS":"mining","MBMA":"mining","NCKL":"mining","AMMN":"mining",
    "PSAB":"mining","SMMT":"mining",
    "ASII":"industrial","UNTR":"industrial","SMGR":"industrial","SMSM":"industrial",
    "HEXA":"industrial","TKIM":"industrial","INKP":"industrial","ISSP":"industrial",
    "ARNA":"industrial","EKAD":"industrial","LION":"industrial","TOTO":"industrial",
    "KBLI":"industrial","FASW":"industrial","BTON":"industrial","INAI":"industrial",
    "MLIA":"industrial","NIKL":"industrial","ALKA":"industrial","DPNS":"industrial",
    "SRIL":"industrial","PBRX":"industrial","ARGO":"industrial","CNTB":"industrial",
    "PWON":"property","CTRA":"property","SMRA":"property","KIJA":"property",
    "BSDE":"property","DMAS":"property","LPKR":"property","JRPT":"property",
    "MDLN":"property","MTLA":"property","SRTG":"property","BKSL":"property",
    "PANI":"property","APLN":"property","ASRI":"property","BEST":"property",
    "DILD":"property","GMTD":"property","PPRO":"property","RODA":"property",
    "WIKA":"construction","WSKT":"construction","ADHI":"construction",
    "PTPP":"construction","NRCA":"construction","ACST":"construction",
    "IDPR":"construction","MTRA":"construction","PBSA":"construction","TOTL":"construction",
    "TLKM":"telecom","EXCL":"telecom","ISAT":"telecom","TOWR":"telecom",
    "TBIG":"telecom","WIFI":"telecom","JSMR":"infrastructure","FREN":"telecom",
    "LINK":"telecom","CENT":"telecom","META":"telecom",
    "GOTO":"tech","BUKA":"tech","EMTK":"media","MNCN":"media","FILM":"media",
    "DMMX":"tech","MCAS":"tech","KREN":"tech","MTDL":"tech",
    "MLPT":"tech","JSKY":"telecom",
    "KLBF":"healthcare","HEAL":"healthcare","MIKA":"healthcare","SOHO":"healthcare",
    "DVLA":"healthcare","TSPC":"healthcare","PEHA":"healthcare","SCPI":"healthcare",
    "PYFA":"healthcare","INAF":"healthcare","KAEF":"healthcare","MERK":"healthcare",
    "SQBI":"healthcare",
    "AALI":"agri","SGRO":"agri","SSMS":"agri","TAPG":"agri","LSIP":"agri",
    "BWPT":"agri","ANJT":"agri","DSNG":"agri","PALP":"agri","TBLA":"agri",
    "UNSP":"agri","GZCO":"agri",
    "BIRD":"transportation","BULL":"transportation","SMDR":"industrial",
    "MBSS":"transportation","NELY":"transportation","TMAS":"transportation",
    "SAFE":"transportation","DEAL":"transportation","LEAD":"transportation",
    "WINS":"transportation","TPMA":"transportation","SHIP":"transportation",
}

# P/E wajar per sektor — bisa di-override oleh DB (cron harian)
SECTOR_FAIR_PE: dict[str, float] = {
    "bank":10,"financial":11,"telecom":17,"media":14,"tech":25,
    "consumer":18,"healthcare":22,"retail":14,
    "mining":9,"energy":10,"agri":11,"utilities":16,
    "industrial":14,"chemical":12,"property":9,
    "infrastructure":16,"transportation":11,"construction":7,"default":14,
}

# P/BV wajar per sektor
SECTOR_FAIR_PBV: dict[str, float] = {
    "bank":1.5,"financial":1.2,"property":0.7,"construction":0.6,"default":1.5,
}

METHOD_INFO = {
    "Graham":     {"label":"Graham #", "formula":"√(22.5 × EPS × BVPS)"},
    "PBV":        {"label":"P/BV",     "formula":"Fair P/BV Sektor × Nilai Buku"},
    "PE":         {"label":"P/E",      "formula":"Fair P/E Sektor × EPS"},
    "DDM":        {"label":"DDM",      "formula":"DPS(1+g)/(r−g), r=10%, g=5%"},
    "PeterLynch": {"label":"P.Lynch",  "formula":"EPS × Pertumbuhan EPS%"},
}


# ══════════════════════════════════════════════════════════════════════════════
#  KALKULASI VALUASI
# ══════════════════════════════════════════════════════════════════════════════

def calc_graham(eps, bvps):
    if eps and bvps and eps > 0 and bvps > 0:
        return math.sqrt(22.5 * eps * bvps)
    return None

def calc_pe(eps, sector):
    fair_pe = SECTOR_FAIR_PE.get(sector, SECTOR_FAIR_PE["default"])
    if eps and eps > 0:
        return fair_pe * eps
    return None

def calc_pbv(bvps, sector):
    fair_pbv = SECTOR_FAIR_PBV.get(sector, SECTOR_FAIR_PBV["default"])
    if bvps and bvps > 0:
        return fair_pbv * bvps
    return None

def calc_ddm(dps, eps, r=0.10, g=0.05):
    if dps and dps > 0 and r > g:
        if eps and eps > 0 and (dps / eps) > 1.0:
            return None # Payout > 100%
        return dps * (1 + g) / (r - g)
    return None

def calc_peter_lynch(eps, eps_growth):
    if eps and eps > 0 and eps_growth and eps_growth >= 5.0:
        g = max(5.0, min(float(eps_growth), 50.0))
        return eps * g
    return None

def calc_sotp(segments_data, net_debt, shares_out):
    if not segments_data or not shares_out or shares_out <= 0:
        return None
    total_ev = sum([s.get('ev', 0) for s in segments_data])
    intrinsic_equity = total_ev - (net_debt if net_debt else 0)
    if intrinsic_equity <= 0:
        return None
    return intrinsic_equity / shares_out

def calc_epv(adjusted_earnings, cost_of_capital, shares_out):
    if not adjusted_earnings or not cost_of_capital or cost_of_capital <= 0 or not shares_out or shares_out <= 0:
        return None
    if adjusted_earnings <= 0:
        return None
    intrinsic_equity = adjusted_earnings / cost_of_capital
    return intrinsic_equity / shares_out

def calc_rim(bvps, eps, cost_of_equity, years=5):
    if not bvps or bvps <= 0 or not eps or not cost_of_equity or cost_of_equity <= 0:
        return None
    residual_value = 0
    current_eps = eps
    current_bvps = bvps
    for i in range(1, years + 1):
        equity_charge = current_bvps * cost_of_equity
        ri = current_eps - equity_charge
        residual_value += ri / ((1 + cost_of_equity) ** i)
        current_bvps += (current_eps * 0.5)
    val = bvps + residual_value
    return val if val > 0 else None


# ══════════════════════════════════════════════════════════════════════════════
#  FETCH FUNDAMENTAL
# ══════════════════════════════════════════════════════════════════════════════

def _apply_currency_fix(eps, bvps, price):
    """Koreksi kurs USD→IDR jika implied P/E > 10.000."""
    if not price or price <= 0:
        return eps, bvps
    needs = False
    if eps  and eps  > 0 and (price / eps)  > 10_000: needs = True
    elif bvps and bvps > 0 and (price / bvps) > 10_000: needs = True
    if needs:
        print(f"[ENGINE] USD→IDR fix (rate {USD_IDR_RATE}): eps={eps:.6f} price={price:.0f}")
        if eps  is not None: eps  *= USD_IDR_RATE
        if bvps is not None: bvps *= USD_IDR_RATE
    return eps, bvps


def _fetch_fundamentals(t, price, ticker_root: str = ""):
    """
    Ambil EPS, BVPS, DPS, eps_growth.
    Fase 2: cek PostgreSQL cache (TTL 24 jam) sebelum hit Yahoo Finance.
    Koreksi kurs USD→IDR otomatis.
    """
    # ── Cache check ──────────────────────────────────────────────────────────
    if ticker_root:
        try:
            from database import SessionLocal
            from models import FundamentalCache
            db = SessionLocal()
            try:
                cached = db.get(FundamentalCache, ticker_root.upper())
                if cached and not cached.is_stale():
                    print(f"[CACHE HIT] {ticker_root}")
                    return cached.eps, cached.bvps, cached.dps, cached.eps_growth, ""
            finally:
                db.close()
        except Exception as e:
            print(f"[CACHE] Warning: {e}")

    eps = bvps = eps_growth = dps = None
    err = ""

    # ── Laporan keuangan ─────────────────────────────────────────────────────
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
                    ni0 = float(ni_s.iloc[0])
                    eps = ni0 / sh
                    if len(ni_s) >= 2:
                        ni1 = float(ni_s.iloc[1])
                        if ni1 != 0:
                            eps_growth = (ni0 - ni1) / abs(ni1) * 100

            if eq_keys and sh_keys:
                eq = float(bs.loc[eq_keys[0]].iloc[0])
                sh = float(bs.loc[sh_keys[0]].iloc[0])
                if sh > 0:
                    bvps = eq / sh
    except Exception as e:
        err = f"Lap. keuangan: {str(e)[:60]}"

    # ── Fallback menggunakan t.info ──────────────────────────────────────────
    if eps is None or bvps is None or eps_growth is None:
        try:
            info_dict = t.info if hasattr(t, "info") else {}
            
            if eps is None and info_dict.get("trailingEps"):
                eps = float(info_dict.get("trailingEps"))
            if bvps is None and info_dict.get("bookValue"):
                bvps = float(info_dict.get("bookValue"))
            if eps_growth is None and info_dict.get("earningsGrowth"):
                eps_growth = float(info_dict.get("earningsGrowth")) * 100
        except Exception:
            pass

    # ── Fallback menggunakan TradingView ─────────────────────────────────────
    if (eps is None or bvps is None) and ticker_root:
        tv_data = _fetch_from_tradingview(ticker_root)
        if tv_data:
            print(f"[INFO] Menggunakan data fundamental dari TradingView untuk {ticker_root}")
            if eps is None and tv_data.get("eps") is not None:
                eps = tv_data["eps"]
            if bvps is None and tv_data.get("bvps") is not None:
                bvps = tv_data["bvps"]
            if dps is None and tv_data.get("dps") is not None:
                dps = tv_data["dps"]

    eps, bvps = _apply_currency_fix(eps, bvps, price)

    try:
        divs = t.dividends
        if divs is not None and not divs.empty:
            cutoff = pd.Timestamp.now(tz="UTC") - pd.DateOffset(years=1)
            recent = divs[divs.index >= cutoff]
            if not recent.empty:
                dps = float(recent.sum())
    except Exception:
        pass

    # ── Simpan ke cache ───────────────────────────────────────────────────────
    if ticker_root:
        try:
            from database import SessionLocal
            from models import FundamentalCache
            db = SessionLocal()
            try:
                row = db.get(FundamentalCache, ticker_root.upper())
                if row is None:
                    row = FundamentalCache(ticker=ticker_root.upper())
                    db.add(row)
                row.eps        = eps
                row.bvps       = bvps
                row.dps        = dps
                row.eps_growth = eps_growth
                row.price_at   = float(price)
                row.fetched_at = datetime.now(timezone.utc)
                db.commit()
                print(f"[CACHE SAVE] {ticker_root}")
            finally:
                db.close()
        except Exception as e:
            print(f"[CACHE SAVE] Warning: {e}")

    return eps, bvps, dps, eps_growth, err




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




def CalculateBestModel(sector, eps, bvps, dps, price, eps_growth, methods):
    cyclical_sectors = ["mining", "energy", "industrial", "chemical", "basic materials", "energi", "industri_dasar", "industri", "pertambangan"]
    is_cyclical = any(s in sector.lower() for s in cyclical_sectors)
    
    # Prioritas 1: Finansial/Properti
    if sector.lower() in ("bank", "financial", "properti", "keuangan", "property"):
        if "RIM" in methods and methods["RIM"]["is_applicable"]:
            return "RIM", "Sektor Finansial/Properti dengan data ekuitas solid cocok menggunakan RIM."
        if "PBV" in methods and methods["PBV"]["is_applicable"]:
            return "PBV", "Sektor Finansial/Properti dinilai dari nilai buku aset."
            
    # Prioritas 2: Dividen Kuat
    div_yield = (dps / price) if (dps and price) else 0
    if "DDM" in methods and methods["DDM"]["is_applicable"] and div_yield >= 0.04:
        return "DDM", "Emiten membagikan dividen konsisten dengan yield sehat (>= 4%)."
        
    # Prioritas 3: Growth Non-Siklikal
    if eps_growth and eps_growth >= 15 and not is_cyclical:
        if "PeterLynch" in methods and methods["PeterLynch"]["is_applicable"]:
            return "PeterLynch", "Emiten 'Growth Stock' Non-Siklikal dengan pertumbuhan EPS >= 15%."
            
    # Prioritas 4: Defensif Stabil
    if eps_growth and 0 <= eps_growth < 15 and not is_cyclical:
        if "PE" in methods and methods["PE"]["is_applicable"]:
            return "PE", "Emiten Defensif dengan pertumbuhan laba stabil (0-15%)."
            
    # Prioritas 5: Value/Cigar Butt
    pb_ratio = (price / bvps) if (bvps and price and bvps > 0) else 999
    if pb_ratio <= 1.5 and eps and eps > 0:
        if "Graham" in methods and methods["Graham"]["is_applicable"]:
            return "Graham", "Saham Value (PBV <= 1.5 & EPS positif), cocok untuk value investing/cigar butt."
            
    # Prioritas 6: Cash Flow Kuat
    if "DCF" in methods and methods["DCF"]["is_applicable"]:
        return "DCF", "Emiten memiliki arus kas bebas (FCF) positif dan stabil."
        
    # Prioritas 7: Mature/Stagnan
    if "EPV" in methods and methods["EPV"]["is_applicable"]:
        return "EPV", "Emiten mature/declining dengan asumsi pertumbuhan 0%."
        
    # Fallback
    for m in ["Graham", "PE", "PBV", "DDM", "SOTP"]:
        if m in methods and methods[m]["is_applicable"]:
            return m, "Metode fallback karena metode utama tidak memenuhi syarat."
            
    return None, "Data fundamental tidak mencukupi untuk penilaian."


def fetch_stock(ticker_root: str) -> dict:
    """Fetch satu saham lengkap dengan valuasi terbaik dan blended fair value."""
    ticker_jk  = ticker_root + ".JK"
    sector_val = SECTOR_MAP.get(ticker_root, "default")

    result = {
        "ticker": ticker_root, "ticker_jk": ticker_jk, "sector": sector_val,
        "current_price": None, "eps": None, "bvps": None, "dps": None, "eps_growth": None,
        "valuation_price": None, "margin_of_safety": None,
        "method": None, "method_label": None, "formula": None,
        "blended_fair_value": None,
        "methods": {},
        "audit_flags": [],
        "recommended_method": None, "recommendation_reason": "",
        "status": "error", "error_msg": "",
    }

    try:
        t  = yf.Ticker(ticker_jk)
        fi = t.fast_info
        price = fi.get("lastPrice") or fi.get("previousClose")
        if not price:
            result["error_msg"] = "Harga tidak tersedia"
            result["status"]    = "partial"
            return result
        
        price = float(price)
        result["current_price"] = price

        eps, bvps, dps, eps_growth, err = _fetch_fundamentals(t, price, ticker_root)
        if err:
            result["error_msg"] = err

        result["eps"]        = eps
        result["bvps"]       = bvps
        result["dps"]        = dps
        result["eps_growth"] = round(eps_growth, 1) if eps_growth is not None else None

        # Hitung semua metode
        methods, audit_flags = all_methods_result(eps, bvps, dps, eps_growth, price, sector_val, t)
        
        # Tentukan metode terbaik
        rec_method, rec_reason = CalculateBestModel(sector_val, eps, bvps, dps, price, eps_growth, methods)
        
        if rec_method and rec_method in methods:
            methods[rec_method]["is_recommended"] = True
            
            val_price = methods[rec_method]["valuation_price"]
            mos = methods[rec_method]["margin_of_safety"]
            
            result.update({
                "valuation_price":  round(val_price, 2) if val_price else None,
                "margin_of_safety": round(mos, 2) if mos is not None else None,
                "method":           rec_method,
                "method_label":     methods[rec_method]["label"],
                "formula":          methods[rec_method]["formula"],
                "status":           "ok",
            })
            
        for k in methods:
            methods[k].setdefault("is_recommended", False)
            
        result["methods"] = methods
        result["audit_flags"] = audit_flags
        result["recommended_method"] = rec_method
        result["recommendation_reason"] = rec_reason
        
        # Blended Valuation (60% Intrinsic + 40% Relative)
        intrinsic_models = ["DCF", "EPV", "RIM", "DDM", "SOTP"]
        relative_models = ["Graham", "PE", "PBV", "PeterLynch"]
        
        best_intrinsic = None
        if rec_method in intrinsic_models:
            best_intrinsic = methods[rec_method]["valuation_price"]
        else:
            for m in intrinsic_models:
                if methods.get(m, {}).get("is_applicable") and methods[m].get("valuation_price"):
                    best_intrinsic = methods[m]["valuation_price"]
                    break
                    
        best_relative = None
        if rec_method in relative_models:
            best_relative = methods[rec_method]["valuation_price"]
        else:
            for m in relative_models:
                if methods.get(m, {}).get("is_applicable") and methods[m].get("valuation_price"):
                    best_relative = methods[m]["valuation_price"]
                    break
                    
        if best_intrinsic and best_relative:
            result["blended_fair_value"] = round((best_intrinsic * 0.6) + (best_relative * 0.4), 2)
        elif best_intrinsic:
            result["blended_fair_value"] = round(best_intrinsic, 2)
        elif best_relative:
            result["blended_fair_value"] = round(best_relative, 2)

    except Exception as e:
        result["error_msg"] = str(e)[:120]

    return result
# ══════════════════════════════════════════════════════════════════════════════
#  FASE 4A: DISCOUNTED CASH FLOW (DCF)
# ══════════════════════════════════════════════════════════════════════════════

def calc_dcf(t, price: float, shares: float | None = None) -> dict | None:
    """
    Valuasi DCF menggunakan Free Cash Flow historis.

    Asumsi:
    - Horizon 5 tahun
    - Growth rate = FCF CAGR historis, dibatasi [-10%, +25%]
    - Terminal growth = 4% (GDP Indonesia jangka panjang)
    - WACC = risk-free 7% + beta × risk premium 6%, dibatasi [8%, 20%]

    Return dict atau None jika data tidak mencukupi.
    """
    try:
        cf  = t.cashflow
        bs  = t.balance_sheet
        if cf is None or cf.empty:
            print(f"DCF debug: cashflow is None or empty for {t.ticker}")
            return None

        # ── Operating CF ──────────────────────────────────────────────────────
        ocf_keys = [k for k in cf.index if "Operating" in str(k) and "Cash" in str(k)]
        if not ocf_keys:
            ocf_keys = [k for k in cf.index if "Cash From Operations" in str(k)]
        if not ocf_keys:
            print(f"DCF debug: no OCF found for {t.ticker}")
            return None

        # ── CapEx ─────────────────────────────────────────────────────────────
        capex_keys = [k for k in cf.index if "Capital Expenditure" in str(k)
                      or ("Purchase" in str(k) and "Property" in str(k))]

        ocf_row   = cf.loc[ocf_keys[0]].dropna()
        capex_row = cf.loc[capex_keys[0]].dropna() if capex_keys else pd.Series(dtype=float)

        if len(ocf_row) < 2:
            print(f"DCF debug: insufficient OCF data for {t.ticker}")
            return None

        # Ambil FCF historis (max 5 tahun, urutkan dari paling lama)
        n_years = min(len(ocf_row), 5)
        ocf_vals   = ocf_row.iloc[:n_years].values[::-1]   # dari lama ke baru
        capex_vals = capex_row.reindex(ocf_row.index[:n_years]).values[::-1] if not capex_row.empty else [0]*n_years

        fcf_hist = []
        for ocf, capex in zip(ocf_vals, capex_vals):
            capex = capex if (capex == capex and capex is not None) else 0  # NaN guard
            fcf = float(ocf) + float(capex)  # capex adalah negatif di laporan
            fcf_hist.append(fcf)

        if not fcf_hist or fcf_hist[-1] <= 0:
            print(f"DCF debug: FCF <= 0 for {t.ticker}")
            return None

        # ── FCF CAGR historis ────────────────────────────────────────────────
        if len(fcf_hist) >= 2 and fcf_hist[0] > 0 and fcf_hist[-1] > 0:
            cagr = (fcf_hist[-1] / fcf_hist[0]) ** (1 / (len(fcf_hist) - 1)) - 1
        else:
            cagr = 0.05  # default 5%
        g_proj = max(-0.10, min(cagr, 0.25))  # batasi -10% s/d +25%

        # ── Shares outstanding ───────────────────────────────────────────────
        sh_keys = [k for k in bs.index if "Ordinary Shares Number" in str(k)] if bs is not None else []
        if sh_keys:
            shares_out = float(bs.loc[sh_keys[0]].iloc[0])
        else:
            info = t.info or {}
            shares_out = info.get("sharesOutstanding") or info.get("impliedSharesOutstanding")
            if shares_out:
                shares_out = float(shares_out)
            else:
                print(f"DCF debug: shares outstanding not found for {t.ticker}")
                return None

        # ── WACC ─────────────────────────────────────────────────────────────
        info = t.info or {}
        beta = float(info.get("beta") or 1.0)
        beta = max(0.5, min(beta, 2.5))
        rf, mrp = 0.07, 0.06
        wacc = max(0.08, min(rf + beta * mrp, 0.20))

        # ── DCF 5 tahun + Terminal Value ─────────────────────────────────────
        g_term   = 0.04
        fcf_base = fcf_hist[-1]  # FCF terbaru
        pv_sum   = 0.0
        fcf_t    = fcf_base
        projections = []
        for yr in range(1, 6):
            fcf_t = fcf_t * (1 + g_proj)
            pv    = fcf_t / (1 + wacc) ** yr
            pv_sum += pv
            projections.append({"year": yr, "fcf": round(fcf_t), "pv": round(pv)})

        terminal_fcf = fcf_t * (1 + g_term)
        terminal_val = terminal_fcf / (wacc - g_term)
        pv_terminal  = terminal_val / (1 + wacc) ** 5

        total_pv = pv_sum + pv_terminal

        # ── Per-share intrinsic value ─────────────────────────────────────────
        # Koreksi kurs jika FCF dalam USD
        intrinsic_raw = total_pv / shares_out
        intrinsic, _  = _apply_currency_fix(intrinsic_raw, None, price)
        if intrinsic is None:
            intrinsic = intrinsic_raw

        if intrinsic <= 0:
            print(f"DCF debug: intrinsic <= 0 for {t.ticker}")
            return None

        mos = ((intrinsic - price) / price) * 100

        return {
            "intrinsic_value": round(intrinsic, 2),
            "margin_of_safety": round(mos, 2),
            "wacc":             round(wacc * 100, 1),
            "g_projected":      round(g_proj * 100, 1),
            "g_terminal":       round(g_term * 100, 1),
            "fcf_latest":       round(fcf_base),
            "projections":      projections,
            "pv_terminal":      round(pv_terminal),
            "beta":             round(beta, 2),
        }

    except Exception as e:
        print(f"[DCF] Error: {e}")
        return None


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 4B: TECHNICAL INDICATORS — MA50, MA200, RSI14
# ══════════════════════════════════════════════════════════════════════════════

def calc_technical(ticker_root: str) -> dict | None:
    """
    Hitung MA50, MA200, RSI14 dari histori harian 1 tahun.
    Return dict indikator atau None jika data tidak cukup.
    """
    try:
        t    = yf.Ticker(ticker_root + ".JK")
        hist = t.history(period="1y", interval="1d", auto_adjust=True)

        if hist.empty or len(hist) < 50:
            print(f"TECH debug: hist empty or < 50 for {ticker_root}. Len: {len(hist)}")
            return None

        close  = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)
        price  = float(close.iloc[-1])

        # ── MA ───────────────────────────────────────────────────────────────
        ma50  = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1]) if len(hist) >= 200 else None

        # ── RSI(14) ──────────────────────────────────────────────────────────
        delta = close.diff()
        gain  = delta.clip(lower=0).rolling(14).mean()
        loss  = (-delta.clip(upper=0)).rolling(14).mean()
        rs    = gain / loss.replace(0, float("nan"))
        rsi   = float((100 - 100 / (1 + rs)).iloc[-1])

        # ── Trend ─────────────────────────────────────────────────────────────
        if ma200 and ma50 > ma200 * 1.02:
            trend = "bullish"       # Golden cross zone
        elif ma200 and ma50 < ma200 * 0.98:
            trend = "bearish"       # Death cross zone
        else:
            trend = "sideways"
            
        is_uptrend = (ma50 > ma200) if ma200 else (price > ma50)

        # ── MACD ─────────────────────────────────────────────────────────────
        ema12 = close.ewm(span=12, adjust=False).mean()
        ema26 = close.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        
        macd_val = float(macd_line.iloc[-1])
        sig_val = float(signal_line.iloc[-1])
        
        if macd_val > sig_val and macd_line.iloc[-2] <= signal_line.iloc[-2]:
            macd_status = "bullish_cross"
        elif macd_val < sig_val and macd_line.iloc[-2] >= signal_line.iloc[-2]:
            macd_status = "death_cross"
        elif macd_val > sig_val:
            macd_status = "bullish"
        else:
            macd_status = "bearish"
            
        macd_dict = {"value": round(macd_val, 3), "signal": round(sig_val, 3), "status": macd_status}

        # ── Volume signal ─────────────────────────────────────────────────────
        vol_5  = float(volume.iloc[-5:].mean())
        vol_20 = float(volume.iloc[-20:].mean())
        p_5d   = float(close.iloc[-5])

        if vol_5 > vol_20 * 1.15:
            vol_signal = "accumulation" if price <= p_5d * 1.01 else "breakout"
        elif vol_5 < vol_20 * 0.85:
            vol_signal = "drying_up"
        else:
            vol_signal = "neutral"

        return {
            "ma50":          round(ma50, 2),
            "ma200":         round(ma200, 2) if ma200 else None,
            "rsi14":         round(rsi, 1),
            "trend":         trend,
            "is_uptrend":    is_uptrend,
            "macd":          macd_dict,
            "price_vs_ma50":  round((price - ma50)  / ma50  * 100, 1),
            "price_vs_ma200": round((price - ma200) / ma200 * 100, 1) if ma200 else None,
            "volume_signal": vol_signal,
        }

    except Exception as e:
        print(f"[TECH] {ticker_root}: {e}")
        return None


def get_ohlcv(ticker_root: str, period: str = "6mo") -> list[dict]:
    """
    Ambil data OHLCV untuk TradingView Lightweight Charts.
    Return list of {time, open, high, low, close, volume}.
    """
    try:
        t    = yf.Ticker(ticker_root + ".JK")
        hist = t.history(period=period, interval="1d", auto_adjust=True)
        if hist.empty:
            return []

        rows = []
        for dt, row in hist.iterrows():
            ts = int(dt.timestamp())
            rows.append({
                "time":   ts,
                "open":   round(float(row["Open"]),  2),
                "high":   round(float(row["High"]),  2),
                "low":    round(float(row["Low"]),   2),
                "close":  round(float(row["Close"]), 2),
                "volume": int(row["Volume"]),
            })
        return rows

    except Exception as e:
        print(f"[OHLCV] {ticker_root}: {e}")
        return []


def get_ma_series(ticker_root: str, period: str = "6mo") -> dict:
    """
    Hitung MA50 dan MA200 series untuk overlay chart.
    Return {ma50: [{time, value}], ma200: [{time, value}]}.
    """
    try:
        t    = yf.Ticker(ticker_root + ".JK")
        hist = t.history(period="1y", interval="1d", auto_adjust=True)
        if hist.empty:
            return {"ma50": [], "ma200": []}

        close = hist["Close"].astype(float)
        ma50_s  = close.rolling(50).mean()
        ma200_s = close.rolling(200).mean() if len(hist) >= 200 else pd.Series(dtype=float)

        # Batasi ke period yang diminta
        cutoff_days = {"1mo": 30, "3mo": 90, "6mo": 180, "1y": 365}.get(period, 180)
        hist_cut = hist.iloc[-cutoff_days:]

        ma50_out, ma200_out = [], []
        for dt in hist_cut.index:
            ts = int(dt.timestamp())
            v50 = ma50_s.get(dt)
            if v50 and v50 == v50:  # not NaN
                ma50_out.append({"time": ts, "value": round(float(v50), 2)})
            if not ma200_s.empty:
                v200 = ma200_s.get(dt)
                if v200 and v200 == v200:
                    ma200_out.append({"time": ts, "value": round(float(v200), 2)})

        return {"ma50": ma50_out, "ma200": ma200_out}

    except Exception as e:
        print(f"[MA] {ticker_root}: {e}")
        return {"ma50": [], "ma200": []}


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 4C: ACCUMULATION SCORE (OBV-based proxy)
# ══════════════════════════════════════════════════════════════════════════════

def detect_accumulation(ticker_root: str) -> dict:
    """
    Hitung Accumulation Score (0-100) berbasis On-Balance Volume (OBV).

    Interpretasi:
    - 70-100 : Akumulasi kuat (volume mendukung kenaikan)
    - 40-70  : Netral / sideways
    - 0-40   : Distribusi (volume mendukung penurunan)
    """
    try:
        t    = yf.Ticker(ticker_root + ".JK")
        hist = t.history(period="3mo", interval="1d", auto_adjust=True)

        if hist.empty or len(hist) < 30:
            print(f"ACC debug: hist empty or < 30 for {ticker_root}. Len: {len(hist)}")
            return {"score": 50, "signal": "neutral", "obv_trend": "flat"}

        close  = hist["Close"].astype(float)
        volume = hist["Volume"].astype(float)

        # ── On-Balance Volume ─────────────────────────────────────────────────
        obv = [0.0]
        for i in range(1, len(hist)):
            if close.iloc[i] > close.iloc[i - 1]:
                obv.append(obv[-1] + volume.iloc[i])
            elif close.iloc[i] < close.iloc[i - 1]:
                obv.append(obv[-1] - volume.iloc[i])
            else:
                obv.append(obv[-1])

        obv_s = pd.Series(obv, index=hist.index)

        # ── OBV trend (linear regression slope) ──────────────────────────────
        n = len(obv_s)
        x = list(range(n))
        x_mean = sum(x) / n
        y_mean = sum(obv_s) / n
        num    = sum((xi - x_mean) * (yi - y_mean) for xi, yi in zip(x, obv_s))
        den    = sum((xi - x_mean) ** 2 for xi in x)
        slope  = num / den if den != 0 else 0

        # Normalkan slope terhadap volume rata-rata
        avg_vol = float(volume.mean())
        norm_slope = slope / avg_vol if avg_vol > 0 else 0

        # ── Price change 3 bulan ──────────────────────────────────────────────
        price_change = (float(close.iloc[-1]) - float(close.iloc[0])) / float(close.iloc[0])

        # ── Score: OBV tren positif vs harga diam = akumulasi ────────────────
        divergence = norm_slope - price_change * 0.5
        score = max(0, min(100, round(50 + divergence * 300)))

        if score >= 65:
            signal = "accumulation"
            obv_trend = "rising"
        elif score <= 35:
            signal = "distribution"
            obv_trend = "falling"
        else:
            signal = "neutral"
            obv_trend = "flat"

        return {"score": score, "signal": signal, "obv_trend": obv_trend}

    except Exception as e:
        print(f"[ACC] {ticker_root}: {e}")
        return {"score": 50, "signal": "neutral", "obv_trend": "flat"}


# ══════════════════════════════════════════════════════════════════════════════
#  FASE 6: QUALITY CHECKS (PIOTROSKI, ALTMAN, BENEISH)
# ══════════════════════════════════════════════════════════════════════════════

def calc_piotroski(ticker_root: str) -> dict | None:
    """Hitung Piotroski F-Score (0-9)."""
    try:
        t = yf.Ticker(ticker_root + ".JK")
        bs = t.balance_sheet
        cf = t.cashflow
        is_ = t.financials
        
        if bs is None or bs.empty or is_ is None or is_.empty or cf is None or cf.empty:
            return None
        
        # P1: ROA > 0
        ni = is_.loc['Net Income'].iloc[0] if 'Net Income' in is_.index else 0
        ta = bs.loc['Total Assets'].iloc[0] if 'Total Assets' in bs.index else 1
        roa = ni / ta
        
        # P2: CFO > 0
        cfo_keys = [k for k in cf.index if "Operating Cash Flow" in str(k) or "Cash From Operations" in str(k)]
        cfo = cf.loc[cfo_keys[0]].iloc[0] if cfo_keys else 0
        
        # P3: Delta ROA > 0
        ni_prev = is_.loc['Net Income'].iloc[1] if ('Net Income' in is_.index and len(is_.columns) > 1) else ni
        ta_prev = bs.loc['Total Assets'].iloc[1] if ('Total Assets' in bs.index and len(bs.columns) > 1) else ta
        roa_prev = ni_prev / ta_prev
        
        # P4: CFO > Net Income
        accrual = cfo > ni
        
        # P5: Delta Leverage
        ltd_keys = [k for k in bs.index if "Long Term Debt" in str(k)]
        ltd = bs.loc[ltd_keys[0]].iloc[0] if ltd_keys else 0
        ltd_prev = bs.loc[ltd_keys[0]].iloc[1] if (ltd_keys and len(bs.columns) > 1) else ltd
        lev = ltd / ta
        lev_prev = ltd_prev / ta_prev
        
        # P6: Delta Liquidity
        ca = bs.loc['Current Assets'].iloc[0] if 'Current Assets' in bs.index else None
        cl = bs.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in bs.index else None
        if ca is not None and cl is not None and cl > 0:
            cr = ca / cl
            ca_prev = bs.loc['Current Assets'].iloc[1] if len(bs.columns) > 1 else ca
            cl_prev = bs.loc['Current Liabilities'].iloc[1] if len(bs.columns) > 1 else cl
            cr_prev = ca_prev / cl_prev if cl_prev > 0 else cr
            delta_liquidity = cr > cr_prev
        else:
            delta_liquidity = True # Neutral fallback
            
        # P7: Delta Equity
        sh_keys = [k for k in bs.index if "Ordinary Shares" in str(k) or "Share Issued" in str(k)]
        sh = bs.loc[sh_keys[0]].iloc[0] if sh_keys else 0
        sh_prev = bs.loc[sh_keys[0]].iloc[1] if (sh_keys and len(bs.columns) > 1) else sh
        delta_eq = sh <= sh_prev
        
        # P8: Delta Margin
        gp_keys = [k for k in is_.index if "Gross Profit" in str(k) or "Net Interest Income" in str(k)]
        rev_keys = [k for k in is_.index if "Total Revenue" in str(k) or "Operating Revenue" in str(k)]
        gp = is_.loc[gp_keys[0]].iloc[0] if gp_keys else ni
        gp_prev = is_.loc[gp_keys[0]].iloc[1] if (gp_keys and len(is_.columns) > 1) else gp
        rev = is_.loc[rev_keys[0]].iloc[0] if rev_keys else ta
        rev_prev = is_.loc[rev_keys[0]].iloc[1] if (rev_keys and len(is_.columns) > 1) else ta
        gm = gp / rev if rev > 0 else 0
        gm_prev = gp_prev / rev_prev if rev_prev > 0 else 0
        delta_gm = gm > gm_prev
        
        # P9: Delta Turnover
        turnover = rev / ta if ta > 0 else 0
        turnover_prev = rev_prev / ta_prev if ta_prev > 0 else 0
        delta_turnover = turnover > turnover_prev
        
        score = int(sum([roa > 0, cfo > 0, roa > roa_prev, accrual, lev < lev_prev, delta_liquidity, delta_eq, delta_gm, delta_turnover]))
        
        return {
            "score": score,
            "details": {
                "roa_positive": bool(roa > 0),
                "cfo_positive": bool(cfo > 0),
                "roa_increase": bool(roa > roa_prev),
                "accrual": bool(accrual),
                "leverage_decrease": bool(lev < lev_prev),
                "liquidity_increase": bool(delta_liquidity),
                "no_new_shares": bool(delta_eq),
                "margin_increase": bool(delta_gm),
                "turnover_increase": bool(delta_turnover)
            }
        }
    except Exception as e:
        print(f"[PIOTROSKI] Error {ticker_root}: {e}")
        return None

def calc_altman_beneish(ticker_root: str, price: float) -> dict | None:
    """Hitung Altman Z-Score & Beneish M-Score."""
    try:
        t = yf.Ticker(ticker_root + ".JK")
        bs = t.balance_sheet
        is_ = t.financials
        info = t.info or {}
        
        if bs is None or bs.empty or is_ is None or is_.empty:
            return None
            
        ta = bs.loc['Total Assets'].iloc[0] if 'Total Assets' in bs.index else 1
        tl = bs.loc['Total Liabilities Net Minority Interest'].iloc[0] if 'Total Liabilities Net Minority Interest' in bs.index else 1
        ca = bs.loc['Current Assets'].iloc[0] if 'Current Assets' in bs.index else 0
        cl = bs.loc['Current Liabilities'].iloc[0] if 'Current Liabilities' in bs.index else 0
        wc = ca - cl
        re = bs.loc['Retained Earnings'].iloc[0] if 'Retained Earnings' in bs.index else 0
        ebit = is_.loc['EBIT'].iloc[0] if 'EBIT' in is_.index else (is_.loc['Pretax Income'].iloc[0] if 'Pretax Income' in is_.index else 0)
        
        sh_keys = [k for k in bs.index if "Ordinary Shares" in str(k) or "Share Issued" in str(k)]
        shares = bs.loc[sh_keys[0]].iloc[0] if sh_keys else (info.get('sharesOutstanding') or 1)
        me = shares * price
        
        rev_keys = [k for k in is_.index if "Total Revenue" in str(k) or "Operating Revenue" in str(k)]
        sales = is_.loc[rev_keys[0]].iloc[0] if rev_keys else 0
        
        # Z-Score
        if ta > 0:
            x1 = wc / ta
            x2 = re / ta
            x3 = ebit / ta
            x4 = me / tl if tl > 0 else 0
            x5 = sales / ta
            z_score = 1.2*x1 + 1.4*x2 + 3.3*x3 + 0.6*x4 + 1.0*x5
        else:
            z_score = 0
            
        # Beneish M-Score Proksi Sederhana
        rect_keys = [k for k in bs.index if "Receivables" in str(k)]
        rect = bs.loc[rect_keys[0]].iloc[0] if rect_keys else 0
        rect_prev = bs.loc[rect_keys[0]].iloc[1] if (rect_keys and len(bs.columns) > 1) else rect
        sales_prev = is_.loc[rev_keys[0]].iloc[1] if (rev_keys and len(is_.columns) > 1) else sales
        dsri = (rect / sales) / (rect_prev / sales_prev) if (sales > 0 and sales_prev > 0 and rect_prev > 0) else 1.0
        
        gp_keys = [k for k in is_.index if "Gross Profit" in str(k) or "Net Interest Income" in str(k)]
        gp = is_.loc[gp_keys[0]].iloc[0] if gp_keys else 0
        gp_prev = is_.loc[gp_keys[0]].iloc[1] if (gp_keys and len(is_.columns) > 1) else gp
        gm = gp / sales if sales > 0 else 0
        gm_prev = gp_prev / sales_prev if sales_prev > 0 else 0
        gmi = gm_prev / gm if gm > 0 else 1.0
        
        ca_prev = bs.loc['Current Assets'].iloc[1] if (len(bs.columns) > 1 and 'Current Assets' in bs.index) else ca
        ppe_keys = [k for k in bs.index if "PPE" in str(k) or "Properties" in str(k)]
        ppe = bs.loc[ppe_keys[0]].iloc[0] if ppe_keys else 0
        ppe_prev = bs.loc[ppe_keys[0]].iloc[1] if (ppe_keys and len(bs.columns) > 1) else ppe
        ta_prev = bs.loc['Total Assets'].iloc[1] if (len(bs.columns) > 1 and 'Total Assets' in bs.index) else ta
        aq = 1 - ((ca + ppe) / ta) if ta > 0 else 0
        aq_prev = 1 - ((ca_prev + ppe_prev) / ta_prev) if ta_prev > 0 else 0
        aqi = aq / aq_prev if aq_prev > 0 else 1.0
        
        sgi = sales / sales_prev if sales_prev > 0 else 1.0
        
        m_score = -4.84 + (0.92 * dsri) + (0.528 * gmi) + (0.404 * aqi) + (0.892 * sgi)
        
        return {
            "z_score": round(float(z_score), 2),
            "z_status": "Safe" if z_score > 2.99 else ("Grey" if z_score > 1.8 else "Distress"),
            "m_score": round(float(m_score), 2),
            "m_status": "Manipulator" if m_score > -1.78 else "Safe",
        }
    except Exception as e:
        print(f"[ALTMAN_BENEISH] Error {ticker_root}: {e}")
        return None
