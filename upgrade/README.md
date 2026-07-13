# `upgrade/` — Submission-Ready Methodological Upgrades

This folder implements the methodological additions required by the working paper
*"Credit Sovereignty in DeFi Lending: An On-Chain Lender of Last Resort and Capital
Flight after the KelpDAO Exploit"* (2026, submitted).

It sits **on top of** the original `src/defi_event_study/` package: `config`,
`data`, and the core `did_core` / `run_four_specs` helpers from `models` are
reused unchanged. The upgrades address the P0/P1 concerns raised by a reviewer
audit of v1 of the paper and are documented one-to-one in the manuscript.

## What lives here

| File | Purpose |
|---|---|
| `upgrade_analysis.py` | All new methods (importable module) |
| `run_upgrade.py` | Driver: reproduces `FINAL_*` tables and figures |
| `README.md` | This file |

The upgrade layer never modifies `src/`. The original `scripts/run_analysis.py`
still reproduces the *v1* paper's numbers; `run_upgrade.py` produces the
*submission-ready* numbers on the July 8, 2026 data snapshot.

## Manuscript ↔ code map

| Paper section | Function(s) in `upgrade_analysis.py` |
|---|---|
| §3.2 Event-study (Fig. 3, panels a–b) | `event_study_detrended`, `event_study_first_diff` |
| §4.4 Price–flow decomposition (Table 5) | `laspeyres_tvl`, `stable_tvl`, `decompose_flow_vs_price` |
| §4.5 Design-robust inference (Figs. 4–5) | `randomization_inference`, `synthetic_control`, `rmspe_ratio_inference`, `synthetic_did` |
| §4.6 SUTVA bounds and external controls | `sutva_attribution_bounds`, `external_control_estimates` |
| §4.7 Persistence, whale, SSR truncation | `persistence_across_windows`, `whale_adjustment_check`, `ssr_truncation_robustness` |
| §5 Variance tests (Table 9) | `variance_tests_upgraded` (Brown–Forsythe + bootstrap CI) |
| §5.2 On-chain utilization (Fig. 7) | `fetch_onchain_reserve_history`, `plot_utilization`, `reconcile_supply_borrow_apy` |
| §4 Table regeneration | `regenerate_final_tables` |

All numeric results in the paper trace to a single call to `run_upgrade.py` on the
committed data snapshot; the outputs are written with a `FINAL_` prefix so they
never collide with the v1 outputs.

## What changed relative to v1 (and why)

**Design-robust inference (P0).** The v1 two-unit DiD carried inference risk under
few-treated asymptotics (Conley & Taber 2011; Ferman & Pinto 2019). We add:
randomization inference over a 20-protocol donor pool, synthetic control with
RMSPE-ratio placebo p-values, and a simplified synthetic DiD estimator.

**SUTVA bounds (P0).** Because Spark is the destination of migrating capital, the
DiD is best interpreted as a relative reallocation effect. Attributing 0%, 50%,
or 100% of Spark's abnormal inflow to Aave outflows produces bounds on Aave's
standalone effect. External controls (Kamino on Solana, Venus on BSC) sit outside
the Ethereum migration path and provide a further check.

**Price–flow decomposition (P0).** In USD, TVL can move on price alone (Luo et al.
FC 2025; Saggese et al. BIS WP 1268). We use DefiLlama's `tokensInUsd` and `tokens`
fields to attribute Aave's decline to flows vs. prices; a Laspeyres quantity index
and a stablecoin-only subsample re-estimate Spec D immune to price effects.

**Event-study — corrections (P1).** The v1-F2 event-study absorbed post-event
drops into the fitted trend, producing a spurious pre-event drift. The two
correct versions (pre-period-only detrending; first differences) are implemented
here as `event_study_detrended` and `event_study_first_diff`. **The v1-F2 output
should not be used.**

**On-chain utilization (P1).** DefiLlama's `chartLendBorrow` endpoint has moved
to a paid tier. We replace it with archival `eth_call` reads to Aave V3's
`ProtocolDataProvider.getReserveData(...)` via free public archive-capable RPCs,
sampled daily around the event. This is a one-time-effort primary-source
improvement.

**Brown–Forsythe with bootstrap CI (P1).** v1 used `scipy.stats.levene` (mean-
centered, two-sided). Because APY series are heavy-tailed, we use the median-
centered Brown–Forsythe (Brown & Forsythe 1974), report the one-sided p-value
for the alternative $H_1:\sigma^2_\text{Aave} > \sigma^2_\text{Spark}$, and
add bootstrap 95% confidence intervals for the variance ratio.

**Persistence window (P1).** The paper's original 9-day post window was extended
to T+60 to show persistence. Because a scheduled Sky Savings Rate reduction fell
inside the extended window (2026-05-26), we also report a truncated
robustness estimate ending 2026-05-25.

**Whale adjustment reframing (P0, factual).** The media-reported $174M
"Justin Sun" deposit to Spark at T+2 was not confirmed by on-chain entity
tracing within the event window (Arkham). The upgrade layer therefore treats
$174M only as a conservative upper-bound removal; the whale-adjusted DiD
remains unchanged in sign and significance.

## Usage

Everything runs from the repository root with your existing environment
(`pip install -r requirements.txt`).

```bash
# Use the committed 2026-07-08 data snapshot in data/raw/
python upgrade/run_upgrade.py

# Refresh from live APIs (DefiLlama + public Ethereum RPCs)
python upgrade/run_upgrade.py --no-cache

# Skip the archival eth_call step (see note below on Figure 7)
python upgrade/run_upgrade.py --skip-onchain
```

Outputs are written to:

* `results/tables/FINAL_table3_tvl_summary.csv`
* `results/tables/FINAL_table4_did.csv`
* `results/tables/FINAL_table5_apy_stats.csv`
* `results/tables/FINAL_randomization.csv`
* `results/tables/FINAL_sutva_bounds.csv`
* `results/tables/FINAL_external_controls.csv`
* `results/tables/FINAL_persistence.csv`
* `results/tables/FINAL_variance_tests.csv`
* `results/tables/FINAL_eventstudy_{detrended,firstdiff}.csv`
* `results/figures/fig7_utilization.png`

## Notes and manual steps

**Aave `ProtocolDataProvider` address.** The address at the top of
`upgrade_analysis.py` (`AAVE_DATA_PROVIDER`) needs to match the currently
deployed Aave V3 instance on Ethereum. Verify against `docs.aave.com` →
Developers → Deployed Contracts → Ethereum Mainnet before running with
`--no-cache`. A stale address returns empty `eth_call` results without raising.

**Public RPCs.** Archive queries require an archive-capable node. The RPC list
in `PUBLIC_RPCS` is rotated automatically; if all fail, `--skip-onchain` allows
the rest of the pipeline to run and the paper's Figure 7 can be reproduced from
`data/raw/onchain_*.csv` if a cached snapshot is present.

**Reserve factor for the reconciliation.** `reconcile_supply_borrow_apy`
defaults to `reserve_factor=0.25` (Aave DAI). If Aave governance changes this,
confirm the current value at `app.aave.com` and pass it explicitly.

**Simplified synthetic DiD.** `synthetic_did` is an educational implementation
(no regularization, no jackknife SEs). For a journal-version replication,
substitute `pysyncon` or the R `synthdid` package.

**Extended donor pool.** `DONOR_SLUGS_EXTENDED` contains 22 slugs; ~19 are
consistently usable (some fail the pre-event depth screen). The exact composition
of the pool used in the paper is listed in Appendix B of the manuscript and
saved to `results/tables/FINAL_randomization.csv` at runtime.

## References for the methods

- Abadie, A., Diamond, A., & Hainmueller, J. (2010). Synthetic control methods. *JASA*.
- Arkhangelsky, D., et al. (2021). Synthetic difference-in-differences. *AER*.
- Brown, M. B., & Forsythe, A. B. (1974). Robust tests for equality of variances. *JASA*.
- Conley, T. G., & Taber, C. R. (2011). Inference with DiD with few policy changes. *REStat*.
- Ferman, B., & Pinto, C. (2019). DiD with few treated groups. *REStat*.
- Newey, W. K., & West, K. D. (1987). HAC covariance matrix. *Econometrica*.
