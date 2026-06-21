import os

with open('app.py', 'r') as f:
    app_lines = f.readlines()

# Extract functions from app.py
def extract_function(func_name):
    start = -1
    for i, line in enumerate(app_lines):
        if line.startswith(f"def {func_name}("):
            start = i
            break
    if start == -1: return ""
    end = start + 1
    while end < len(app_lines):
        if app_lines[end].startswith("def ") or app_lines[end].startswith("@"):
            if app_lines[end-1].strip() == "":
                break
        end += 1
    return "".join(app_lines[start:end])

extract_adv = extract_function("extract_advanced_data")
all_methods = extract_function("all_methods_result")

new_calc_best = """
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
"""

with open('fetch_engine.py', 'r') as f:
    engine_content = f.read()

import re
# Remove pick_method
engine_content = re.sub(r"def pick_method\(.*?(?=\n# ══════════════════════════════════════════════════════════════════════════════\n#  FETCH FUNDAMENTAL)", "", engine_content, flags=re.DOTALL)

# Inject functions before fetch_stock
parts = engine_content.split("def fetch_stock(ticker_root: str) -> dict:")
new_engine = parts[0] + "\n\n" + extract_adv + "\n" + all_methods + "\n" + new_calc_best + "\n\ndef fetch_stock(ticker_root: str) -> dict:\n" + parts[1]

with open('fetch_engine.py', 'w') as f:
    f.write(new_engine)

print("Injected functions.")
