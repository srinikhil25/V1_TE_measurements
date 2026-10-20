"""
Seebeck analysis: binned S from linear fit of ΔV vs ΔT per T₀ bin, with uncertainty.

Sign convention (kept from the original app, validated on constantan,
S ≈ −38 µV/K): T1 is the HOT side, T2 the COLD side, ΔT = T2 − T1, so ΔT is
negative while heating and S = TEMF / ΔT. :func:`polarity_check` flags runs
where the two thermocouples look swapped.
"""
from typing import Dict, List, Optional, Tuple

#: Spike rejection: points whose residual exceeds CLIP_SIGMA robust standard
#: deviations (1.4826 × median absolute deviation) are rejected, repeatedly,
#: up to MAX_CLIP_ITERATIONS times — but only while they are RARE. If more than
#: MAX_REJECT_FRACTION of a bin would go, the residuals are structured (e.g.
#: heating/cooling hysteresis, thermal lag), not spikes: nothing is rejected,
#: the plain fit is kept and the bin is flagged instead. Dropping a quarter of
#: a bin would silently change the method and bias S. Clean data loses no
#: points, so the result equals the plain least-squares fit.
CLIP_SIGMA = 5.0
MAX_CLIP_ITERATIONS = 5
MAX_REJECT_FRACTION = 0.05

STRUCTURED_RESIDUALS = ("Residuals are not a straight line plus rare spikes "
                        "({k} of {n} points beyond {sig:g}σ) — check for heating/cooling "
                        "hysteresis or thermal lag. No points were rejected.")

#: Polarity check: heating rows with ΔT above this (K) count as "wrong sign".
POLARITY_MIN_DT_K = 0.5


def linear_fit_slope_and_uncertainty(x: List[float], y: List[float]) -> Tuple[Optional[float], Optional[float]]:
    """Least-squares slope and its standard error. Returns (slope, std_error) or (None, None) if insufficient data."""
    fit = _linear_fit(x, y)
    if fit is None:
        return None, None
    slope, _intercept, se_slope = fit
    return slope, se_slope


def _linear_fit(x: List[float], y: List[float]) -> Optional[Tuple[float, float, Optional[float]]]:
    """(slope, intercept, slope standard error) or None if not computable."""
    n = len(x)
    if n < 3 or len(y) != n:
        return None
    sum_x = sum(x)
    sum_y = sum(y)
    sum_xx = sum(xi * xi for xi in x)
    sum_xy = sum(xi * yi for xi, yi in zip(x, y))
    denom = n * sum_xx - sum_x * sum_x
    if abs(denom) < 1e-20:
        return None
    slope = (n * sum_xy - sum_x * sum_y) / denom
    intercept = (sum_y - slope * sum_x) / n
    residuals = [yi - (slope * xi + intercept) for xi, yi in zip(x, y)]
    rss = sum(r * r for r in residuals)
    se_slope = (rss / (n - 2)) ** 0.5 / (sum_xx - sum_x * sum_x / n) ** 0.5
    return slope, intercept, se_slope


def _median(v: List[float]) -> float:
    s = sorted(v)
    n = len(s)
    return s[n // 2] if n % 2 else 0.5 * (s[n // 2 - 1] + s[n // 2])


def robust_linear_fit(
    x: List[float], y: List[float],
    clip_sigma: float = CLIP_SIGMA, max_iter: int = MAX_CLIP_ITERATIONS,
    max_reject_fraction: float = MAX_REJECT_FRACTION,
) -> Optional[Dict]:
    """Least-squares fit with iterative MAD-based rejection of rare spikes.

    Returns {"slope", "se_slope", "n_used", "n_rejected", "warning"} or None.
    At least 3 points are always kept. If more than ``max_reject_fraction`` of
    the points would be rejected, none are: the plain fit is returned with a
    ``warning`` explaining why.
    """
    all_pts = pts = list(zip(x, y))
    rejected = 0
    for _ in range(max_iter):
        fit = _linear_fit([p[0] for p in pts], [p[1] for p in pts])
        if fit is None:
            return None
        slope, intercept, _se = fit
        res = [py - (slope * px + intercept) for px, py in pts]
        # Measure from the median residual: an outlier also shifts the
        # least-squares intercept, so the good points' residuals are offset.
        centre = _median(res)
        dev = [abs(r - centre) for r in res]
        mad = _median(dev)
        if mad <= 0:
            break
        limit = clip_sigma * 1.4826 * mad
        keep = [p for p, d in zip(pts, dev) if d <= limit]
        if len(keep) == len(pts) or len(keep) < 3:
            break
        rejected += len(pts) - len(keep)
        pts = keep
    warning = None
    if rejected > max_reject_fraction * len(all_pts):
        warning = STRUCTURED_RESIDUALS.format(k=rejected, n=len(all_pts), sig=clip_sigma)
        pts, rejected = all_pts, 0
    fit = _linear_fit([p[0] for p in pts], [p[1] for p in pts])
    if fit is None:
        return None
    slope, _intercept, se = fit
    return {"slope": slope, "se_slope": se, "n_used": len(pts), "n_rejected": rejected,
            "warning": warning}


def binned_seebeck_analysis(
    data: List[Dict],
    bin_width_k: float = 10.0,
    delta_t_key: str = "Delta Temp [oC]",
    temf_key: str = "TEMF [mV]",
    t0_k_key: str = "T0 [K]",
    reject_outliers: bool = True,
) -> List[Dict]:
    """
    Group rows by T₀ (K) into bins of width bin_width_k, fit ΔV (TEMF) vs ΔT in each bin;
    return list of {T0_center_K, T0_min_K, T0_max_K, S_uV_per_K, S_uncertainty_uV_per_K,
    n_points, n_rejected, fit_warning}. ``n_points`` counts the points used in
    the fit; ``n_rejected`` the spikes removed (0 when disabled); ``fit_warning``
    is set when the residuals look structured rather than spiky.
    """
    if not data:
        return []
    # Collect (T0_K, delta_T, TEMF) - TEMF in mV, delta_T in °C (= K for diff)
    points = []
    for row in data:
        if row.get("valid") is False:
            continue
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
    bins: Dict[int, List[Tuple[float, float]]] = {}  # bin_idx -> [(delta_T, TEMF), ...]
    for t0, dt, temf in points:
        bin_idx = int((t0 - t0_min) // bin_width_k)
        bins.setdefault(bin_idx, []).append((dt, temf))
    result = []
    for bin_idx in sorted(bins.keys()):
        pts = bins[bin_idx]
        if len(pts) < 3:
            continue
        x = [p[0] for p in pts]
        y = [p[1] for p in pts]  # TEMF in mV
        if reject_outliers:
            fit = robust_linear_fit(x, y)
        else:
            plain = _linear_fit(x, y)
            fit = None if plain is None else {"slope": plain[0], "se_slope": plain[2],
                                              "n_used": len(pts), "n_rejected": 0,
                                              "warning": None}
        if fit is None:
            continue
        # slope = d(TEMF_mV)/d(delta_T_C) = mV/K → S in µV/K = slope * 1000
        s_uv = fit["slope"] * 1000.0
        s_unc = (fit["se_slope"] * 1000.0) if fit["se_slope"] is not None else None
        t0_center = t0_min + (bin_idx + 0.5) * bin_width_k
        t0_lo = t0_min + bin_idx * bin_width_k
        t0_hi = t0_lo + bin_width_k
        result.append({
            "T0_center_K": round(t0_center, 2),
            "T0_min_K": round(t0_lo, 2),
            "T0_max_K": round(t0_hi, 2),
            "S_uV_per_K": round(s_uv, 3),
            "S_uncertainty_uV_per_K": round(s_unc, 3) if s_unc is not None else None,
            "n_points": fit["n_used"],
            "n_rejected": fit["n_rejected"],
            "fit_warning": fit["warning"],
        })
    return result


POLARITY_MESSAGE = (
    "ΔT is positive while heating: the hot (T1) and cold (T2) thermocouples look "
    "swapped for this geometry, so S has the wrong sign. Check the channels in "
    "Settings → Thermocouples.")


def polarity_vote(row: Dict) -> int:
    """+1 if a heating row has the wrong ΔT sign, −1 if the right one, 0 if it
    doesn't count (cooling, invalid, or |ΔT| < POLARITY_MIN_DT_K)."""
    if row.get("branch") == "cooling" or row.get("valid") is False:
        return 0
    dt = row.get("Delta Temp [oC]")
    if dt is None or abs(dt) < POLARITY_MIN_DT_K:
        return 0
    return 1 if dt > 0 else -1


def polarity_verdict(wrong: int, right: int, min_rows: int = 5) -> Optional[str]:
    """Message if the wrong-sign rows clearly dominate, else None."""
    if wrong >= min_rows and wrong > 2 * right:
        return POLARITY_MESSAGE
    return None


def polarity_check(data: List[Dict], min_rows: int = 5) -> Optional[str]:
    """Warn when the hot/cold thermocouples look swapped.

    While heating, T1 (hot) must exceed T2 (cold), i.e. ΔT = T2 − T1 < 0. If
    most heating rows with a clear gradient (|ΔT| ≥ POLARITY_MIN_DT_K) show
    ΔT > 0 instead, the channels are probably swapped for this geometry and
    every S would have the wrong sign. Returns a message, or None if fine or
    not decidable.
    """
    wrong = right = 0
    for r in data:
        v = polarity_vote(r)
        wrong += v > 0
        right += v < 0
    return polarity_verdict(wrong, right, min_rows)
