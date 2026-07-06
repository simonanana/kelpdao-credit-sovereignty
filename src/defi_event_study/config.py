"""Global configuration for the KelpDAO event study.

All constants used across the pipeline are centralized here so that the
event window, estimation parameters, and data-source identifiers can be
audited (and modified for robustness checks) in a single place.
"""

from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_RAW = PROJECT_ROOT / "data" / "raw"
DATA_PROCESSED = PROJECT_ROOT / "data" / "processed"
RESULTS_TABLES = PROJECT_ROOT / "results" / "tables"
RESULTS_FIGURES = PROJECT_ROOT / "results" / "figures"

for _p in (DATA_RAW, DATA_PROCESSED, RESULTS_TABLES, RESULTS_FIGURES):
    _p.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Event definition
# ---------------------------------------------------------------------------
# First on-chain exploit transaction of the KelpDAO LayerZero bridge attack,
# as recorded by Lookonchain and PeckShield.
EVENT_TS = pd.Timestamp("2026-04-18", tz="UTC")

# Estimation window: 120 pre-event days, 10 post-event days.
PRE_DAYS = 120
POST_DAYS = 10

# Newey-West HAC lag length for all regression standard errors.
NW_LAGS = 5

# ---------------------------------------------------------------------------
# Data sources (DefiLlama REST APIs)
# ---------------------------------------------------------------------------
LLAMA_API = "https://api.llama.fi"
YIELDS_API = "https://yields.llama.fi"

# Protocol slugs on the DefiLlama /protocol endpoint.
PROTOCOL_SLUGS = {
    "Aave_V3": "aave-v3",
    "Spark": "spark",
    "Morpho": "morpho",  # falls back to "morpho-blue" if empty
}

# Yield-pool identifiers verified against the DefiLlama yields endpoint
# (April 2026). Matched stablecoin pairs: USDC and DAI/USDS.
POOL_IDS = {
    "Aave V3 USDC Ethereum": "aa70268e-4b52-42bf-a116-608b370f9501",
    "Aave V3 DAI Ethereum": "3665ee7e-6c5d-49d9-abb7-c47ab5d9d4ac",
    "Spark USDS Ethereum": "d8c4eff5-c8a9-46fc-a888-057c4c668e72",
    "Spark Savings USDC ETH": "c5c74dd1-995c-4445-9d84-3e710bad7d52",
}

# Matched asset pairs for the Levene variance tests and APY figures:
# (Aave pool label, Spark pool label, pair name)
PAIR_MAP = [
    ("Aave V3 USDC Ethereum", "Spark Savings USDC ETH", "USDC"),
    ("Aave V3 DAI Ethereum", "Spark USDS Ethereum", "DAI / USDS"),
]

STABLECOINS = {"USDC", "USDT", "DAI", "USDS"}

# Estimated Justin Sun deposit into Spark at T+2, used for the
# whale-adjusted robustness check (Section IV of the paper).
WHALE_DEPOSIT_USD = 174e6

# ---------------------------------------------------------------------------
# Plot styling
# ---------------------------------------------------------------------------
COLORS = {
    "Aave_V3": "#E04B4B",
    "Spark": "#3B82F6",
    "Morpho": "#10B981",
    "event": "#111827",
}

MPL_RC = {
    "figure.dpi": 160,
    "font.size": 11,
    "axes.spines.top": False,
    "axes.spines.right": False,
}
