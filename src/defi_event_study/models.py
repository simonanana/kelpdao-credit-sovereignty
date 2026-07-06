"""Econometric models: DiD specifications, placebo tests, variance tests,
and the Baron-Kenny mediation (mechanism) analysis.

All regressions use Newey-West HAC standard errors (5 lags). Four DiD
specifications are estimated (paper Section II-C):

* Spec A - Baseline with common time trend (descriptive upper bound; low DW)
* Spec B - Protocol-specific linear trends (descriptive upper bound; low DW)
* Spec C - First differences (eliminates level non-stationarity)
* Spec D - Lagged dependent variable (preferred conservative specification)
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.stats.stattools as stools
from scipy.stats import levene

from .config import EVENT_TS, NW_LAGS


# ---------------------------------------------------------------------------
# Core OLS wrapper
# ---------------------------------------------------------------------------
def did_core(df: pd.DataFrame, y: str, xcols: list[str], nw_lags: int = NW_LAGS, label: str = "") -> dict | None:
    """Estimate one OLS specification with HAC (Newey-West) standard errors.

    Returns a dict with the fitted model, N, R^2, Durbin-Watson statistic,
    and the DiD coefficient / SE / p-value, or None if too few observations.
    """
    d = df.dropna(subset=[y] + xcols).copy()
    if len(d) < 20:
        return None
    for c in [y] + xcols:
        d = d[np.isfinite(d[c])]
    if len(d) < 20:
        return None
    X = sm.add_constant(d[xcols])
    m = sm.OLS(d[y], X).fit(cov_type="HAC", cov_kwds={"maxlags": nw_lags})
    return {
        "label": label,
        "model": m,
        "N": len(d),
        "R2": m.rsquared,
        "DW": stools.durbin_watson(m.resid),
        "did_coef": m.params.get("did", np.nan),
        "did_se": m.bse.get("did", np.nan),
        "did_p": m.pvalues.get("did", np.nan),
    }


def run_four_specs(panel: pd.DataFrame, treat: str = "Aave_V3", ctrl: str = "Spark") -> list[dict]:
    """Run the four DiD specifications on one treated/control pair."""
    df = panel[panel["protocol"].isin([treat, ctrl])].copy()
    df = df.sort_values(["protocol", "date"]).reset_index(drop=True)
    df["treated"] = (df["protocol"] == treat).astype(int)
    df["did"] = df["treated"] * df["post"]
    df["treat_t"] = df["treated"] * df["t"]

    out = [
        did_core(df, "log_tvl", ["post", "treated", "did", "t"], label="Spec A Baseline"),
        did_core(df, "log_tvl", ["post", "treated", "did", "t", "treat_t"], label="Spec B Trends"),
    ]

    dfd = df.copy()
    dfd["d_log_tvl"] = dfd.groupby("protocol")["log_tvl"].diff()
    out.append(did_core(dfd, "d_log_tvl", ["did", "treated", "post"], label="Spec C FirstDiff"))

    dfl = df.copy()
    dfl["lag_log_tvl"] = dfl.groupby("protocol")["log_tvl"].shift(1)
    out.append(
        did_core(dfl, "log_tvl", ["lag_log_tvl", "post", "treated", "did"], label="Spec D LaggedDV (preferred)")
    )
    return out


def pct_effect(log_coef: float) -> float:
    """Convert a log-scale DiD coefficient to an approximate percentage effect."""
    return (np.exp(log_coef) - 1) * 100


def sigstar(p: float) -> str:
    if p < 0.01:
        return "***"
    if p < 0.05:
        return "**"
    if p < 0.1:
        return "*"
    return "ns"


# ---------------------------------------------------------------------------
# Placebo tests and rolling event-intensity scan
# ---------------------------------------------------------------------------
def placebo_tests(
    sources: dict,
    build_panel_fn,
    true_results: list[dict],
    placebo_dates: list[pd.Timestamp] | None = None,
) -> pd.DataFrame:
    """Re-estimate Spec B and Spec D at pseudo event dates.

    Note (honest framing, paper Section IV): Spec B *can* be significant at
    pseudo-dates because of residual autocorrelation; the clean placebo
    benchmark is Spec D.
    """
    if placebo_dates is None:
        placebo_dates = [
            pd.Timestamp("2026-01-15", tz="UTC"),
            pd.Timestamp("2026-02-15", tz="UTC"),
            pd.Timestamp("2026-03-15", tz="UTC"),
        ]
    rows = []
    for pdt in placebo_dates:
        pp = build_panel_fn(sources, event=pdt, pre_days=60, post_days=10)
        if pp.empty:
            continue
        tmp = run_four_specs(pp, "Aave_V3", "Spark")
        rb = next(r for r in tmp if r and "Trends" in r["label"])
        rd = next(r for r in tmp if r and "LaggedDV" in r["label"])
        rows.append(
            [
                pdt.date().isoformat(),
                round(rb["did_coef"], 4), round(rb["did_p"], 5), sigstar(rb["did_p"]),
                round(rd["did_coef"], 4), round(rd["did_p"], 5), sigstar(rd["did_p"]),
            ]
        )

    rb_true = next(r for r in true_results if r and "Trends" in r["label"])
    rd_true = next(r for r in true_results if r and "LaggedDV" in r["label"])
    rows.append(
        [
            f"TRUE {EVENT_TS.date()}",
            round(rb_true["did_coef"], 4), round(rb_true["did_p"], 5), sigstar(rb_true["did_p"]),
            round(rd_true["did_coef"], 4), round(rd_true["did_p"], 5), sigstar(rd_true["did_p"]),
        ]
    )
    return pd.DataFrame(
        rows,
        columns=["Date", "SpecB_coef", "SpecB_p", "SpecB_sig", "SpecD_coef", "SpecD_p", "SpecD_sig"],
    )


def rolling_did_scan(
    sources: dict,
    build_panel_fn,
    start_offset: int = -30,
    end_offset: int = 5,
) -> pd.DataFrame:
    """Rolling DiD coefficient scan (Spec B) across candidate event dates.

    Confirms the coefficient spikes uniquely at the true event date
    (paper Figure 3)."""
    rows = []
    for sd in pd.date_range(
        EVENT_TS + pd.Timedelta(days=start_offset),
        EVENT_TS + pd.Timedelta(days=end_offset),
        freq="D",
        tz="UTC",
    ):
        pp = build_panel_fn(sources, event=sd, pre_days=30, post_days=7)
        if pp.empty:
            continue
        rr = run_four_specs(pp, "Aave_V3", "Spark")
        rb = next(r for r in rr if r and "Trends" in r["label"])
        rows.append([sd, rb["did_coef"], rb["did_se"], rb["did_p"]])
    return pd.DataFrame(rows, columns=["date", "did", "se", "p"])


# ---------------------------------------------------------------------------
# Levene variance tests (paper Table 6)
# ---------------------------------------------------------------------------
def levene_variance_tests(apy: dict, pair_map: list[tuple]) -> pd.DataFrame:
    """Asset-paired APY variance tests on the matched pre-event window.

    ``Overlap_days`` = number of calendar days on which BOTH pools have
    simultaneous APY observations in the pre-event window.
    """
    rows = []
    for a_key, s_key, pair in pair_map:
        da, ds = apy[a_key].copy(), apy[s_key].copy()
        pre_a = da[da["date"] < EVENT_TS]
        pre_s = ds[ds["date"] < EVENT_TS]
        overlap_start = max(pre_a["date"].min(), pre_s["date"].min())
        av = pre_a[pre_a["date"] >= overlap_start]["apy"].dropna()
        sv = pre_s[pre_s["date"] >= overlap_start]["apy"].dropna()
        _, lp = levene(av, sv)
        f_ratio = av.var(ddof=1) / sv.var(ddof=1)
        post_a = da[da["date"] >= EVENT_TS]["apy"].dropna()
        post_s = ds[ds["date"] >= EVENT_TS]["apy"].dropna()
        rows.append(
            [
                pair,
                int((EVENT_TS - overlap_start).days),
                len(av), len(sv),
                round(av.std(), 3), round(sv.std(), 3),
                round(f_ratio, 1), round(lp, 6),
                round(post_a.std(), 3) if len(post_a) > 1 else np.nan,
                round(post_s.std(), 3) if len(post_s) > 1 else np.nan,
            ]
        )
    return pd.DataFrame(
        rows,
        columns=[
            "Pair", "Overlap_days", "N_Aave_pre", "N_Spark_pre",
            "sigma_Aave_pre", "sigma_Spark_pre", "F_ratio_pre",
            "Levene_p_pre", "sigma_Aave_post", "sigma_Spark_post",
        ],
    )


# ---------------------------------------------------------------------------
# Mechanism (Baron-Kenny mediation) analysis - paper Section III-C
# ---------------------------------------------------------------------------
def protocol_daily_apy(apy: dict) -> pd.DataFrame:
    """Aggregate pool-level APY to a protocol-day panel and compute
    ``apy_stress`` = APY minus the protocol's pre-event mean APY."""
    proto_map = {
        "Aave_V3": ["Aave V3 USDC Ethereum", "Aave V3 DAI Ethereum"],
        "Spark": ["Spark USDS Ethereum", "Spark Savings USDC ETH"],
    }
    pieces = []
    for proto, keys in proto_map.items():
        temp = []
        for k in keys:
            d = apy[k][["date", "apy"]].copy()
            # Cast to pure date BEFORE grouping to avoid intraday duplicates.
            d["date"] = pd.to_datetime(d["date"], utc=True).dt.date
            temp.append(d)
        d = pd.concat(temp, ignore_index=True)
        x = d.groupby("date", as_index=False)["apy"].mean()
        x["protocol"] = proto
        pieces.append(x)
    out = pd.concat(pieces, ignore_index=True)

    event_date = pd.to_datetime(EVENT_TS, utc=True).date()
    pre_means = out[out["date"] < event_date].groupby("protocol")["apy"].mean().to_dict()
    out["pre_event_mean_apy"] = out["protocol"].map(pre_means)
    out["apy_stress"] = out["apy"] - out["pre_event_mean_apy"]
    return out


def build_mechanism_panel(panel: pd.DataFrame, apy: dict) -> pd.DataFrame:
    """Merge the TVL panel with the protocol-day APY-stress panel (1-to-1)."""
    proto_apy = protocol_daily_apy(apy)

    mech = panel[panel["protocol"].isin(["Aave_V3", "Spark"])].copy()
    mech["date"] = pd.to_datetime(mech["date"], utc=True).dt.date

    # Force 1-to-1 matching to prevent a merge explosion.
    proto_apy = proto_apy.groupby(["date", "protocol"], as_index=False).mean(numeric_only=True)
    mech = mech.drop_duplicates(subset=["date", "protocol"])
    mech = mech.merge(
        proto_apy[["date", "protocol", "apy", "apy_stress"]],
        on=["date", "protocol"],
        how="left",
    )
    mech = mech.sort_values(["protocol", "date"]).reset_index(drop=True)
    mech.replace([np.inf, -np.inf], np.nan, inplace=True)

    mech["next_day_log_tvl_growth"] = mech.groupby("protocol")["log_tvl"].shift(-1) - mech["log_tvl"]
    mech["treated"] = (mech["protocol"] == "Aave_V3").astype(int)
    mech["did"] = mech["treated"] * mech["post"]
    mech["lag_log_tvl"] = mech.groupby("protocol")["log_tvl"].shift(1)

    # Force numeric dtypes: statsmodels silently returns NaN on object columns.
    for col in ["log_tvl", "lag_log_tvl", "next_day_log_tvl_growth", "apy_stress", "treated", "post", "did"]:
        mech[col] = pd.to_numeric(mech[col], errors="coerce")
    return mech


def mediation_analysis(mech: pd.DataFrame, nw_lags: int = NW_LAGS) -> tuple[pd.DataFrame, float]:
    """Baron-Kenny style attenuation analysis (paper Table 7).

    M1 : APY stress -> next-day log TVL growth (with protocol FE and post).
    M2a: preferred Spec D DiD without the rate channel.
    M2b: Spec D DiD plus APY stress; the attenuation of the DiD coefficient
         between M2a and M2b measures the share of the effect mediated by
         the interest-rate channel.

    Caveat (paper Section III-C): the high attenuation partly reflects the
    mechanical correlation between APY stress and the post-event DiD
    indicator; it is interpreted as consistent with near-complete mediation
    via the rate channel, not as evidence of no direct effect.
    """
    # M1
    m1_df = mech.dropna(subset=["next_day_log_tvl_growth", "apy_stress", "post"]).copy()
    dummies = pd.get_dummies(m1_df["protocol"], drop_first=True, dtype=float)
    X1 = sm.add_constant(pd.concat([m1_df[["apy_stress", "post"]], dummies], axis=1))
    m1 = sm.OLS(
        np.asarray(m1_df["next_day_log_tvl_growth"], dtype=float),
        np.asarray(X1, dtype=float),
    ).fit(cov_type="HAC", cov_kwds={"maxlags": nw_lags})

    # M2a
    m2a_df = mech.dropna(subset=["log_tvl", "lag_log_tvl", "post", "treated", "did"]).copy()
    X2a = sm.add_constant(m2a_df[["lag_log_tvl", "post", "treated", "did"]])
    m2a = sm.OLS(np.asarray(m2a_df["log_tvl"], dtype=float), np.asarray(X2a, dtype=float)).fit(
        cov_type="HAC", cov_kwds={"maxlags": nw_lags}
    )

    # M2b
    m2b_df = mech.dropna(subset=["log_tvl", "lag_log_tvl", "post", "treated", "did", "apy_stress"]).copy()
    X2b = sm.add_constant(m2b_df[["lag_log_tvl", "post", "treated", "did", "apy_stress"]])
    m2b = sm.OLS(np.asarray(m2b_df["log_tvl"], dtype=float), np.asarray(X2b, dtype=float)).fit(
        cov_type="HAC", cov_kwds={"maxlags": nw_lags}
    )

    did_m2a = m2a.params[X2a.columns.get_loc("did")]
    did_m2b = m2b.params[X2b.columns.get_loc("did")]
    attenuation = (
        round(100 * (abs(did_m2a) - abs(did_m2b)) / abs(did_m2a), 2)
        if pd.notna(did_m2a) and did_m2a != 0
        else np.nan
    )

    table = pd.DataFrame(
        [
            [
                "M1: APY stress -> next-day TVL growth", "apy_stress",
                round(m1.params[X1.columns.get_loc("apy_stress")], 4),
                round(m1.bse[X1.columns.get_loc("apy_stress")], 4),
                round(m1.pvalues[X1.columns.get_loc("apy_stress")], 5), np.nan,
            ],
            [
                "M2a: Preferred DiD (no rate control)", "did",
                round(did_m2a, 4),
                round(m2a.bse[X2a.columns.get_loc("did")], 4),
                round(m2a.pvalues[X2a.columns.get_loc("did")], 5), np.nan,
            ],
            [
                "M2b: Preferred DiD + APY stress", "did",
                round(did_m2b, 4),
                round(m2b.bse[X2b.columns.get_loc("did")], 4),
                round(m2b.pvalues[X2b.columns.get_loc("did")], 5), attenuation,
            ],
            [
                "M2b: Preferred DiD + APY stress", "apy_stress",
                round(m2b.params[X2b.columns.get_loc("apy_stress")], 4),
                round(m2b.bse[X2b.columns.get_loc("apy_stress")], 4),
                round(m2b.pvalues[X2b.columns.get_loc("apy_stress")], 6), np.nan,
            ],
        ],
        columns=["Model", "Variable", "Coef", "SE_HAC", "p_value", "DiD_attenuation_pct"],
    )
    return table, attenuation
