import re

with open("fetch_engine.py", "r") as f:
    content = f.read()

# We will replace the block from calc_graham to calc_peter_lynch
old_block = """def calc_graham(eps, bvps):
    if eps and eps > 0 and bvps and bvps > 0:
        return (22.5 * eps * bvps) ** 0.5

def calc_pe(eps, sector):
    fair_pe = SECTOR_FAIR_PE.get(sector, SECTOR_FAIR_PE["default"])
    if eps and eps > 0:
        return eps * fair_pe

def calc_pbv(bvps, sector):
    fair_pb = SECTOR_FAIR_PBV.get(sector, SECTOR_FAIR_PBV["default"])
    if bvps and bvps > 0:
        return bvps * fair_pb

def calc_ddm(dps, r=0.10, g=0.05):
    if dps and dps > 0:
        return dps * (1 + g) / (r - g)

def calc_peter_lynch(eps, eps_growth):
    if eps and eps > 0 and eps_growth and eps_growth > 0:
        g = max(5.0, min(float(eps_growth), 50.0))
        return eps * g"""

new_block = """def calc_graham(eps, bvps):
    # Flag: Dilarang untuk emiten dengan EPS atau BVPS negatif.
    if eps and eps > 0 and bvps and bvps > 0:
        return (22.5 * eps * bvps) ** 0.5
    return None

def calc_pe(eps, sector):
    # Relevan untuk consumer goods, berisiko untuk komoditas (tapi kita handle flag di app.py)
    fair_pe = SECTOR_FAIR_PE.get(sector, SECTOR_FAIR_PE["default"])
    if eps and eps > 0:
        return eps * fair_pe
    return None

def calc_pbv(bvps, sector):
    fair_pb = SECTOR_FAIR_PBV.get(sector, SECTOR_FAIR_PBV["default"])
    if bvps and bvps > 0:
        return bvps * fair_pb
    return None

def calc_ddm(dps, eps, r=0.10, g=0.05):
    # Flag: Dilarang jika Payout Ratio > 100%
    if dps and dps > 0:
        if eps and eps > 0 and (dps / eps) > 1.0:
            return None # Payout > 100%
        return dps * (1 + g) / (r - g)
    return None

def calc_peter_lynch(eps, eps_growth):
    # Flag: Dilarang untuk emiten dengan pertumbuhan EPS di bawah 5%.
    if eps and eps > 0 and eps_growth and eps_growth >= 5.0:
        g = min(float(eps_growth), 50.0)
        return eps * g
    return None

def calc_sotp(segments_data, net_debt, shares_out):
    # segments_data: list of dict {'revenue': x, 'peer_ps': y} atau EV
    if not segments_data or not shares_out or shares_out <= 0:
        return None
    total_ev = 0
    for seg in segments_data:
        total_ev += seg.get('ev', 0)
    intrinsic_equity = total_ev - (net_debt if net_debt else 0)
    if intrinsic_equity <= 0:
        return None
    return intrinsic_equity / shares_out

def calc_epv(adjusted_earnings, cost_of_capital, shares_out):
    # EPV = Adjusted Earnings / WACC
    if not adjusted_earnings or not cost_of_capital or cost_of_capital <= 0 or not shares_out or shares_out <= 0:
        return None
    if adjusted_earnings <= 0:
        return None
    intrinsic_equity = adjusted_earnings / cost_of_capital
    return intrinsic_equity / shares_out

def calc_rim(bvps, eps, cost_of_equity, years=5):
    # RIM = BVPS + PV of Residual Income
    if not bvps or bvps <= 0 or not eps or not cost_of_equity or cost_of_equity <= 0:
        return None
    residual_value = 0
    current_eps = eps
    current_bvps = bvps
    # Proyeksi sederhana
    for i in range(1, years + 1):
        equity_charge = current_bvps * cost_of_equity
        ri = current_eps - equity_charge
        residual_value += ri / ((1 + cost_of_equity) ** i)
        # Asumsi EPS stabil, BVPS bertambah dari retained earnings (simplifikasi)
        current_bvps += (current_eps * 0.5) # Asumsi payout 50%
    
    val = bvps + residual_value
    return val if val > 0 else None"""

if old_block in content:
    content = content.replace(old_block, new_block)
    with open("fetch_engine.py", "w") as f:
        f.write(content)
    print("Successfully patched heuristic models & added SOTP, EPV, RIM.")
else:
    print("Failed to find old block.")

