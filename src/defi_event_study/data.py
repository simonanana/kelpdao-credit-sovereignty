"""Data acquisition and panel construction.

All primary data are retrieved from the DefiLlama REST API:

* Protocol-level daily TVL:  https://api.llama.fi/protocol/{slug}
* Pool-level daily APY:      https://yields.llama.fi/chart/{pool_id}

Because the DefiLlama endpoints are continuously updated, every fetch is
cached to ``data/raw/`` as a CSV so the exact snapshot used in the paper
can be committed to the repository and the analysis remains reproducible
even if the live API responses change.
"""

from __future__ import annotations

import time

import numpy as np
import pandas as pd
import requests

from .config import (
    DATA_RAW,
    EVENT_TS,
    LLAMA_API,
    POOL_IDS,
    POST_DAYS,
    PRE_DAYS,
    PROTOCOL_SLUGS,
    YIELDS_API,
)

_HEADERS = {"User-Agent": "Academic-Research/1.0"}


# ---------------------------------------------------------------------------
# Fetchers (with local CSV caching)
# ---------------------------------------------------------------------------
def fetch_tvl(slug: str, retries: int = 3, use_cache: bool = True) -> pd.DataFrame:
    """Fetch the daily total-TVL series for a protocol.

    Returns a DataFrame with columns ``date`` (tz-aware UTC) and ``tvlUsd``.
    """
    cache = DATA_RAW / f"tvl_{slug}.csv"
    if use_cache and cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"], utc=True)
        return df

    for i in range(retries):
        try:
            r = requests.get(f"{LLAMA_API}/protocol/{slug}", timeout=30, headers=_HEADERS)
            r.raise_for_status()
            tv = r.json().get("tvl", [])
            if not tv:
                return pd.DataFrame(columns=["date", "tvlUsd"])
            df = pd.DataFrame(tv)
            df["date"] = pd.to_datetime(df["date"], unit="s", utc=True)
            df = df.rename(columns={"totalLiquidityUSD": "tvlUsd"})
            df = df[["date", "tvlUsd"]].sort_values("date").reset_index(drop=True)
            df.to_csv(cache, index=False)
            return df
        except Exception as exc:  # noqa: BLE001 - network retry loop
            if i == retries - 1:
                print(f"TVL fetch failed for {slug}: {exc}")
                return pd.DataFrame(columns=["date", "tvlUsd"])
            time.sleep(2**i)
    return pd.DataFrame(columns=["date", "tvlUsd"])


def fetch_token_flows(slug: str, use_cache: bool = True) -> pd.DataFrame:
    """Fetch the token-level TVL decomposition (``tokensInUsd``) for a protocol.

    Used to isolate stablecoin balances for the migration analysis (Figure 2).
    Returns a long DataFrame with columns ``date``, ``token``, ``valueUsd``.
    """
    cache = DATA_RAW / f"token_flows_{slug}.csv"
    if use_cache and cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"], utc=True)
        return df

    try:
        r = requests.get(f"{LLAMA_API}/protocol/{slug}", timeout=30, headers=_HEADERS)
        r.raise_for_status()
        d = r.json()
        if "tokensInUsd" not in d:
            return pd.DataFrame(columns=["date", "token", "valueUsd"])
        rows = []
        for entry in d["tokensInUsd"]:
            dt = pd.to_datetime(entry["date"], unit="s", utc=True)
            for tok, val in entry.get("tokens", {}).items():
                rows.append({"date": dt, "token": tok, "valueUsd": val})
        df = pd.DataFrame(rows)
        df.to_csv(cache, index=False)
        return df
    except Exception as exc:  # noqa: BLE001
        print(f"Token-flow fetch failed for {slug}: {exc}")
        return pd.DataFrame(columns=["date", "token", "valueUsd"])


def fetch_pool_apy(pool_id: str, label: str, use_cache: bool = True) -> pd.DataFrame:
    """Fetch the daily APY history for one yield pool.

    Returns a DataFrame with columns ``date``, ``apy``, ``tvlUsd``.
    """
    cache = DATA_RAW / f"apy_{pool_id[:8]}.csv"
    if use_cache and cache.exists():
        df = pd.read_csv(cache, parse_dates=["date"])
        df["date"] = pd.to_datetime(df["date"], utc=True)
        return df

    try:
        r = requests.get(f"{YIELDS_API}/chart/{pool_id}", timeout=30, headers=_HEADERS)
        r.raise_for_status()
        d = r.json()
        if not d.get("data"):
            return pd.DataFrame(columns=["date", "apy", "tvlUsd"])
        df = pd.DataFrame(d["data"])
        df["date"] = pd.to_datetime(df["timestamp"], utc=True)
        df = (
            df[["date", "apy", "tvlUsd"]]
            .dropna(subset=["apy"])
            .sort_values("date")
            .reset_index(drop=True)
        )
        df.to_csv(cache, index=False)
        return df
    except Exception as exc:  # noqa: BLE001
        print(f"APY fetch failed for {label}: {exc}")
        return pd.DataFrame(columns=["date", "apy", "tvlUsd"])


def load_all_sources(use_cache: bool = True) -> tuple[dict, dict]:
    """Load TVL series for all protocols and APY series for all pools.

    Returns
    -------
    (tvl_sources, apy_sources)
        ``tvl_sources`` maps protocol name -> TVL DataFrame;
        ``apy_sources`` maps pool label -> APY DataFrame.
    """
    tvl = {}
    for name, slug in PROTOCOL_SLUGS.items():
        df = fetch_tvl(slug, use_cache=use_cache)
        if name == "Morpho" and df.empty:
            df = fetch_tvl("morpho-blue", use_cache=use_cache)
        tvl[name] = df

    apy = {label: fetch_pool_apy(pid, label, use_cache=use_cache) for label, pid in POOL_IDS.items()}
    return tvl, apy


# ---------------------------------------------------------------------------
# Panel construction
# ---------------------------------------------------------------------------
def build_panel(
    sources: dict,
    event: pd.Timestamp = EVENT_TS,
    pre_days: int = PRE_DAYS,
    post_days: int = POST_DAYS,
) -> pd.DataFrame:
    """Build the balanced protocol-day panel around the event date.

    Adds ``log_tvl`` (natural log of TVL), the ``post`` indicator, and a
    day counter ``t`` measured from the start of the estimation window.
    """
    start = event - pd.Timedelta(days=pre_days)
    end = event + pd.Timedelta(days=post_days)
    frames = []
    for name, df in sources.items():
        if df.empty or df["date"].max() < event:
            continue
        window = df[(df["date"] >= start) & (df["date"] <= end)].copy()
        if len(window) < 10:
            continue
        window["protocol"] = name
        frames.append(window)
    if not frames:
        return pd.DataFrame()
    panel = pd.concat(frames, ignore_index=True)
    panel["log_tvl"] = np.log(panel["tvlUsd"].clip(lower=1))
    panel["post"] = (panel["date"] >= event).astype(int)
    panel["t"] = (panel["date"] - start).dt.days
    return panel.sort_values(["protocol", "date"]).reset_index(drop=True)
