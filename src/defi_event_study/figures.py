"""All figure generation for the paper (Figures 1-8).

Figure numbering follows the manuscript:

1. TVL trajectories (Aave V3, Spark, Morpho)
2. Two-phase stablecoin migration (Aave vs. Spark)
3. Rolling DiD coefficient scan (event intensity, Spec B)
4. APY series by matched pools
5. Rolling 30-day APY volatility
6. Rate architecture schematic (Aave kinked curve vs. Spark DSR floor)
7. APY stress vs. next-day TVL growth (scatter)
8. Sky/MakerDAO collateral composition (RWA pie chart)
"""

from __future__ import annotations

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .config import COLORS, EVENT_TS, MPL_RC, PAIR_MAP, RESULTS_FIGURES, STABLECOINS

plt.rcParams.update(MPL_RC)


def _save(fig, name: str) -> None:
    fig.savefig(RESULTS_FIGURES / name, bbox_inches="tight")
    plt.close(fig)


def fig1_tvl_trajectories(panel: pd.DataFrame, table3: pd.DataFrame) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), gridspec_kw={"width_ratios": [1.5, 1]})
    ax = axes[0]
    for p in ["Aave_V3", "Spark", "Morpho"]:
        d = panel[panel["protocol"] == p]
        ax.plot(d["date"], d["tvlUsd"] / 1e9, lw=2.2, label=p.replace("_", " "), color=COLORS[p])
    ax.axvline(EVENT_TS, color=COLORS["event"], ls="--", lw=1.8)
    ax.set_title("Figure 1. TVL Trajectories — Aave V3, Spark, and Morpho")
    ax.set_ylabel("TVL (USD bn)")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False)
    axes[1].axis("off")
    axes[1].table(cellText=table3.values, colLabels=table3.columns, loc="center")
    axes[1].set_title("Table 3. TVL event summary")
    fig.tight_layout()
    _save(fig, "fig1_tvl_trajectories.png")


def fig2_stablecoin_migration(aave_flows: pd.DataFrame, spark_flows: pd.DataFrame) -> None:
    def stable_daily(df: pd.DataFrame) -> pd.Series:
        if df.empty:
            return pd.Series(dtype=float)
        s = df[df["token"].isin(STABLECOINS)].groupby("date")["valueUsd"].sum() / 1e9
        w = (s.index >= EVENT_TS - pd.Timedelta(days=30)) & (s.index <= EVENT_TS + pd.Timedelta(days=10))
        return s.loc[w]

    sa, ss = stable_daily(aave_flows), stable_daily(spark_flows)
    fig, axes = plt.subplots(1, 2, figsize=(14, 5), sharey=True)
    for ax, s, title, color in [
        (axes[0], sa, "Aave V3", COLORS["Aave_V3"]),
        (axes[1], ss, "Spark", COLORS["Spark"]),
    ]:
        if len(s):
            ax.bar(s.index, s.values, color=color, alpha=0.9)
        ax.axvline(EVENT_TS, color=COLORS["event"], ls="--", lw=1.8, label="Event (T)")
        ax.axvline(EVENT_TS + pd.Timedelta(days=2), color="orange", ls=":", lw=1.8, label="T+2")
        ax.set_title(title)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.tick_params(axis="x", rotation=45)
        ax.legend(frameon=False, fontsize=8)
    axes[0].set_ylabel("Stablecoin TVL (USD bn)")
    fig.suptitle("Figure 2. Two-Phase Stablecoin Migration — Aave vs. Spark", y=1.02, fontsize=13)
    fig.tight_layout()
    _save(fig, "fig2_stablecoin_migration.png")


def fig3_rolling_event_intensity(scan: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(13, 5))
    ax.plot(scan["date"], scan["did"], color=COLORS["Aave_V3"], lw=2)
    ax.fill_between(
        scan["date"],
        scan["did"] - 1.96 * scan["se"],
        scan["did"] + 1.96 * scan["se"],
        color=COLORS["Aave_V3"],
        alpha=0.2,
    )
    sig = scan["p"] < 0.05
    ax.scatter(scan.loc[sig, "date"], scan.loc[sig, "did"], color=COLORS["Aave_V3"], s=25)
    ax.axvline(EVENT_TS, color=COLORS["event"], ls="--", lw=1.8, label="Event")
    ax.axhline(0, color="gray", lw=0.8)
    ax.set_title("Figure 3. Event Intensity — Rolling DiD Scan (Spec B)")
    ax.set_ylabel("DiD coefficient")
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
    ax.tick_params(axis="x", rotation=45)
    ax.legend(frameon=False)
    fig.tight_layout()
    _save(fig, "fig3_rolling_event_intensity.png")


def fig4_apy_series(apy: dict) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for ax, (a_key, s_key, pair) in zip(axes, PAIR_MAP):
        da, ds = apy[a_key], apy[s_key]
        ax.plot(da["date"], da["apy"], label=a_key, color=COLORS["Aave_V3"], lw=1.7)
        ax.plot(ds["date"], ds["apy"], label=s_key, color=COLORS["Spark"], lw=1.7)
        ax.axvline(EVENT_TS, color=COLORS["event"], ls="--", lw=1.5)
        ax.set_title(pair)
        ax.set_ylabel("APY (%)")
        ax.legend(frameon=False, fontsize=8)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.suptitle("Figure 4. APY Series by Matched Pools", y=1.02)
    fig.tight_layout()
    _save(fig, "fig4_apy_series.png")


def fig5_rolling_apy_volatility(apy: dict, window: int = 30) -> None:
    def rolling_vol(df: pd.DataFrame) -> pd.DataFrame:
        d = df[["date", "apy"]].copy().sort_values("date")
        d["roll_sd"] = d["apy"].rolling(window).std()
        return d

    fig, axes = plt.subplots(2, 1, figsize=(13, 8), sharex=True)
    for ax, (a_key, s_key, pair) in zip(axes, PAIR_MAP):
        ra, rs = rolling_vol(apy[a_key]), rolling_vol(apy[s_key])
        ax.plot(ra["date"], ra["roll_sd"], label=f"{a_key} {window}d sd", color=COLORS["Aave_V3"], lw=1.8)
        ax.plot(rs["date"], rs["roll_sd"], label=f"{s_key} {window}d sd", color=COLORS["Spark"], lw=1.8)
        ax.axvline(EVENT_TS, color=COLORS["event"], ls="--", lw=1.5)
        ax.set_title(pair)
        ax.set_ylabel(f"Rolling {window}d sd")
        ax.legend(frameon=False, fontsize=8)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.suptitle("Figure 5. Rolling 30-Day APY Volatility — Aave vs. Spark", y=1.02)
    fig.tight_layout()
    _save(fig, "fig5_rolling_apy_volatility.png")


def fig6_rate_architecture() -> None:
    """Stylized schematic: Aave kinked utilization curve vs. Spark DSR floor."""
    U = np.linspace(0, 1, 300)
    u_opt, r_base, slope1, slope2 = 0.80, 0.02, 0.08, 1.20
    r_aave = np.where(
        U <= u_opt,
        r_base + (U / u_opt) * slope1,
        r_base + slope1 + ((U - u_opt) / (1 - u_opt)) * slope2,
    )
    dsr_floor = 0.0375
    r_spark = np.maximum(dsr_floor, r_base + 0.03 * U)

    fig, ax = plt.subplots(figsize=(8.5, 5))
    ax.plot(U, r_aave * 100, color=COLORS["Aave_V3"], lw=2.4, label="Aave kinked curve")
    ax.plot(U, r_spark * 100, color=COLORS["Spark"], lw=2.4, label="Spark DSR floor")
    ax.axvline(u_opt, color="gray", ls="--", lw=1, label="U* = 0.80")
    ax.axhline(dsr_floor * 100, color=COLORS["Spark"], ls=":", lw=1.5)
    ax.set_xlabel("Utilization rate (U)")
    ax.set_ylabel("Borrow rate (%)")
    ax.set_title("Figure 6. Rate Architecture: Aave Kinked Curve vs. Spark DSR Floor")
    ax.legend(frameon=False)
    fig.tight_layout()
    _save(fig, "fig6_rate_architecture.png")


def fig7_apy_stress_scatter(mech: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    plot_df = mech.dropna(subset=["apy_stress", "next_day_log_tvl_growth"]).copy()
    for proto, color in [("Aave_V3", COLORS["Aave_V3"]), ("Spark", COLORS["Spark"])]:
        d = plot_df[plot_df["protocol"] == proto]
        ax.scatter(d["apy_stress"], d["next_day_log_tvl_growth"], alpha=0.7, s=35, color=color,
                   label=proto.replace("_", " "))
    ax.axhline(0, color="gray", lw=0.8)
    ax.axvline(0, color="gray", lw=0.8)
    ax.set_xlabel("APY stress (APY − protocol pre-event mean, pp)")
    ax.set_ylabel("Next-day log TVL growth")
    ax.set_title("Figure 7. APY Stress vs. Next-Day TVL Growth")
    ax.legend(frameon=False)
    fig.tight_layout()
    _save(fig, "fig7_apy_stress_vs_tvl_growth.png")


def fig8_rwa_collateral(rwa: pd.DataFrame) -> None:
    """Sky collateral composition (source: Steakhouse Financial Q1 2026 and
    the Sky governance portal). Component values must sum to the stated
    $12.4B total."""
    total = rwa["Value_B"].sum()
    fig, ax = plt.subplots(figsize=(7, 7))
    ax.pie(
        rwa["Value_B"],
        labels=rwa["Asset_class"],
        autopct="%1.1f%%",
        startangle=130,
        colors=["#3B82F6", "#67E8F9", "#F4A261", "#E04B4B", "#A78BFA"],
    )
    ax.set_title(f"Figure 8. Sky Collateral Composition\n(Total ${total:.1f}B)")
    fig.tight_layout()
    _save(fig, "fig8_sky_collateral_composition.png")
