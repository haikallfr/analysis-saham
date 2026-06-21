with open('app.py', 'r') as f:
    app_content = f.read()

import re

# Remove functions
app_content = re.sub(r"def CalculateBestModel\(.*?(?=\ndef extract_advanced_data\()", "", app_content, flags=re.DOTALL)
app_content = re.sub(r"def extract_advanced_data\(.*?(?=\ndef all_methods_result\()", "", app_content, flags=re.DOTALL)
app_content = re.sub(r"def all_methods_result\(.*?(?=\n@app\.route\(\"/api/stock/<ticker_input>\"\))", "", app_content, flags=re.DOTALL)

old_api_stock = """@app.route("/api/stock/<ticker_input>")
def api_stock(ticker_input):"""

# find where it ends
start_idx = app_content.find(old_api_stock)
if start_idx != -1:
    end_idx = app_content.find("\n@app.route(\"/api/compare\")", start_idx)
    
    new_api_stock = """@app.route("/api/stock/<ticker_input>")
def api_stock(ticker_input):
    \"\"\"Analisis lengkap satu saham — menggunakan fetch_stock dari engine.\"\"\"
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
"""
    app_content = app_content[:start_idx] + new_api_stock + app_content[end_idx:]
    with open('app.py', 'w') as f:
        f.write(app_content)
    print("Patched app.py")
else:
    print("Could not find api_stock")
