with open('fetch_engine.py', 'r') as f:
    engine_content = f.read()

old_fetch_stock = """def fetch_stock(ticker_root: str) -> dict:
    \"\"\"Fetch satu saham lengkap dengan valuasi terbaik.\"\"\"
    ticker_jk  = ticker_root + ".JK"
    sector_val = SECTOR_MAP.get(ticker_root, "default")

    result = {
        "ticker": ticker_root, "ticker_jk": ticker_jk, "sector": sector_val,
        "current_price": None, "eps": None, "bvps": None, "dps": None, "eps_growth": None,
        "valuation_price": None, "margin_of_safety": None,
        "method": None, "method_label": None, "formula": None,
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
        result["current_price"] = float(price)

        eps, bvps, dps, eps_growth, err = _fetch_fundamentals(t, float(price), ticker_root)
        if err:
            result["error_msg"] = err

        result["eps"]        = eps
        result["bvps"]       = bvps
        result["dps"]        = dps
        result["eps_growth"] = round(eps_growth, 1) if eps_growth is not None else None

        method = pick_method(sector_val, eps, bvps, dps, price, eps_growth)
        if method is None:
            result["error_msg"] = result["error_msg"] or "Data tidak cukup"
            result["status"]    = "partial"
            return result

        val_price = None
        if   method == "Graham":     val_price = calc_graham(eps, bvps)
        elif method == "PBV":        val_price = calc_pbv(bvps, sector_val)
        elif method == "PE":         val_price = calc_pe(eps, sector_val)
        elif method == "DDM":        val_price = calc_ddm(dps)
        elif method == "PeterLynch": val_price = calc_peter_lynch(eps, eps_growth)

        if not val_price or val_price <= 0:
            result["error_msg"] = "Harga valuasi tidak valid"
            result["status"]    = "partial"
            return result

        mos = ((val_price - price) / price) * 100
        result.update({
            "valuation_price":  round(val_price, 2),
            "margin_of_safety": round(mos, 2),
            "method":           method,
            "method_label":     METHOD_INFO[method]["label"],
            "formula":          METHOD_INFO[method]["formula"],
            "status":           "ok",
        })

    except Exception as e:
        result["error_msg"] = str(e)[:120]

    return result"""

new_fetch_stock = """def fetch_stock(ticker_root: str) -> dict:
    \"\"\"Fetch satu saham lengkap dengan valuasi terbaik dan blended fair value.\"\"\"
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

    return result"""

import sys
if old_fetch_stock in engine_content:
    engine_content = engine_content.replace(old_fetch_stock, new_fetch_stock)
    with open('fetch_engine.py', 'w') as f:
        f.write(engine_content)
    print("Patched fetch_stock")
else:
    print("Could not find old_fetch_stock snippet.")
