"""
Seebeck analysis: binned S from linear fit of ΔV vs ΔT per T₀ bin, with uncertainty.
"""
from typing import List, Dict, Optional, Tuple


def linear_fit_slope_and_uncertainty(x: List[float], y: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Least-squares slope and its standard error. Returns (slope, std_error) or (None, None) if insufficient data."""
    n = len(x)
    if n < 3 or len(y) != n:
        return None, None
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-20:
        return None, None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x, y)]
    rss = sum(r * r for r in residuals)
    if n > 2:
        se_slope = (rss / (n - 2)) ** 0.5 / (sum_xx - sum_x * sum_x / n) ** 0.5
    else:
        se_slope = None
    return slope, se_slope


def binned_seebeck_analysis(
    data: List[Dict],
    bin_width_k: float = 10.0,
    delta_t_key: str = "Delta Temp [oC]",
    temf_key: str = "TEMF [mV]",
    t0_k_key: str = "T0 [K]",
) -> List[Dict]:
    """
    Group rows by T₀ (K) into bins of width bin_width_k, fit ΔV (TEMF) vs ΔT in each bin;
    return list of {T0_center_K, T0_min_K, T0_max_K, S_uV_per_K, S_uncertainty_uV_per_K, n_points}.
    """
    if not data:
        return []
    # Collect (T0_K, delta_T, TEMF) - TEMF in mV, delta_T in °C (= K for diff)
    points = []
    for row in data:
        t0 = row.get(t0_k_key)
        dt = row.get(delta_t_key)
        temf = row.get(temf_key)
        if t0 is None or dt is None or temf is None:
            continue
        points.append((float(t0), float(dt), float(temf)))
    if not points:
        return []
    # Bin by T0
    t0_min = min(p[0] for p in points)
    t0_max = max(p[0] for p in points)
    bins: Dict[int, List[Tuple[float, float]]] = {}  # bin_idx -> [(delta_T, TEMF), ...]
    for t0, dt, temf in points:
        bin_idx = int((t0 - t0_min) // bin_width_k)
        if bin_idx not in bins:
            bins[bin_idx] = []
        bins[bin_idx].append((dt, temf))
    result = []
    for bin_idx in sorted(bins.keys()):
        pts = bins[bin_idx]
        if len(pts) < 3:
            continue
        x = [p[0] for p in pts]
        y = [p[1] for p in pts]  # TEMF in mV
        slope, se_slope = linear_fit_slope_and_uncertainty(x, y)
        if slope is None:
            continue
        # slope = d(TEMF_mV)/d(delta_T_C) = mV/K → S in µV/K = slope * 1000
        s_uv = slope * 1000.0
        s_unc = (se_slope * 1000.0) if se_slope is not None else None
        t0_center = t0_min + (bin_idx + 0.5) * bin_width_k
        t0_lo = t0_min + bin_idx * bin_width_k
        t0_hi = t0_lo + bin_width_k
        result.append({
            "T0_center_K": round(t0_center, 2),
            "T0_min_K": round(t0_lo, 2),
            "T0_max_K": round(t0_hi, 2),
            "S_uV_per_K": round(s_uv, 3),
            "S_uncertainty_uV_per_K": round(s_unc, 3) if s_unc is not None else None,
            "n_points": len(pts),
        })
    return result
