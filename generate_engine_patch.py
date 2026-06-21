import re

with open("app.py", "r") as f:
    app_py = f.read()

# We need to import the new methods in app.py from fetch_engine
if "calc_sotp" not in app_py:
    app_py = app_py.replace("calc_dcf, calc_technical, detect_accumulation,", 
                            "calc_dcf, calc_technical, detect_accumulation, calc_sotp, calc_epv, calc_rim,")

# Now let's completely replace all_methods_result and pick_method_with_reason
new_code = """
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

"""

# Regex replacement
pattern = re.compile(r'METHOD_PICK_REASONS = \{.*?return methods', re.DOTALL)
app_py = pattern.sub(new_code.strip(), app_py)

# We must also update api_stock and api_compare where all_methods_result is called
app_py = app_py.replace(
    "methods = all_methods_result(eps, bvps, dps, eps_growth, price, sector_val)",
    "methods, audit_flags = all_methods_result(eps, bvps, dps, eps_growth, price, sector_val, t)"
)

app_py = app_py.replace(
    "rec_method, _, rec_reason = pick_method_with_reason(\n            sector_val, eps, bvps, dps, price, eps_growth)",
    "rec_method, rec_reason = CalculateBestModel(sector_val, eps, bvps, dps, price, eps_growth, methods)"
)
# And the single-line version of pick_method_with_reason if exists
app_py = app_py.replace(
    "rec_method, _, rec_reason = pick_method_with_reason(sector_val, eps, bvps, dps, float(price or 0), eps_growth)",
    "rec_method, rec_reason = CalculateBestModel(sector_val, eps, bvps, dps, float(price or 0), eps_growth, methods)"
)

# And add blended_fair_value to api_stock
api_stock_add = """
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
"""

app_py = app_py.replace('result["methods"]              = methods', api_stock_add + '\n        result["methods"]              = methods')

with open("app.py", "w") as f:
    f.write(app_py)
    
print("Successfully patched app.py")
