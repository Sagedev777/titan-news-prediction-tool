"""
Series registry — maps internal feature names to provider series IDs.

The forecasting feature engineering layer uses these mappings to fetch
the correct series from DataObservation without hard-coding series IDs
in the model files.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SeriesDefinition:
    internal_name: str
    provider: str
    series_id: str
    unit: str
    seasonal_adjustment: str
    description: str
    publication_lag_days: int = 0   # typical lag between observation date and publication
    is_leading_indicator: bool = False
    notes: str = ""


# ── CPI feature series ─────────────────────────────────────────────────────────
CPI_FEATURE_SERIES: list[SeriesDefinition] = [
    SeriesDefinition("cpi_headline_sa",       "bls",  "CUSR0000SA0",     "index", "SA",  "CPI All Items (SA)"),
    SeriesDefinition("cpi_core_sa",           "bls",  "CUSR0000SA0L1E",  "index", "SA",  "CPI Core (SA)"),
    SeriesDefinition("cpi_food_sa",           "bls",  "CUSR0000SAF",     "index", "SA",  "CPI Food (SA)"),
    SeriesDefinition("cpi_energy_sa",         "bls",  "CUSR0000SA0E",    "index", "SA",  "CPI Energy (SA)"),
    SeriesDefinition("cpi_gasoline_sa",       "bls",  "CUSR0000SETB01",  "index", "SA",  "CPI Gasoline (SA)",   is_leading_indicator=True),
    SeriesDefinition("cpi_shelter_sa",        "bls",  "CUSR0000SAH1",    "index", "SA",  "CPI Shelter (SA)"),
    SeriesDefinition("cpi_rent_sa",           "bls",  "CUSR0000SEHA",    "index", "SA",  "CPI Rent (SA)"),
    SeriesDefinition("cpi_oer_sa",            "bls",  "CUSR0000SEHC",    "index", "SA",  "CPI Owners Equiv Rent (SA)"),
    SeriesDefinition("cpi_used_vehicles_sa",  "bls",  "CUSR0000SETA02",  "index", "SA",  "CPI Used Vehicles (SA)", is_leading_indicator=True),
    SeriesDefinition("cpi_new_vehicles_sa",   "bls",  "CUSR0000SETA01",  "index", "SA",  "CPI New Vehicles (SA)"),
    SeriesDefinition("cpi_medical_sa",        "bls",  "CUSR0000SAM",     "index", "SA",  "CPI Medical (SA)"),
    SeriesDefinition("cpi_headline_nsa",      "bls",  "CUUR0000SA0",     "index", "NSA", "CPI All Items (NSA)"),
    SeriesDefinition("cpi_core_nsa",          "bls",  "CUUR0000SA0L1E",  "index", "NSA", "CPI Core (NSA)"),
    SeriesDefinition("oil_wti",               "fred", "DCOILWTICO",      "$/bbl", "",    "WTI Oil Price",        is_leading_indicator=True),
    SeriesDefinition("gasoline_price_us",     "fred", "GASREGCOVW",      "$/gal", "",    "US Gasoline Retail",   is_leading_indicator=True),
    SeriesDefinition("ppi_final_demand",      "bls",  "WPUFD49104",      "index", "SA",  "PPI Final Demand",     is_leading_indicator=True),
    SeriesDefinition("ppi_core",              "bls",  "WPUFD4131",       "index", "SA",  "PPI Core",             is_leading_indicator=True),
    SeriesDefinition("import_prices",         "fred", "IR",              "index", "",    "Import Price Index",   is_leading_indicator=True),
    SeriesDefinition("inflation_exp_mich",    "fred", "MICH",            "pct",   "",    "Michigan Inflation Expectations", is_leading_indicator=True),
    SeriesDefinition("inflation_exp_1yr",     "fred", "EXPINF1YR",       "pct",   "",    "1-Year Inflation Expectations",  is_leading_indicator=True),
    SeriesDefinition("cleveland_headline_mom","cleveland_fed", "CLEVELAND_FED__HEADLINE_CPI_MOM", "pct", "SA", "Cleveland Fed Headline CPI MoM Nowcast", is_leading_indicator=True, notes="External nowcast — use as feature only"),
    SeriesDefinition("cleveland_core_mom",    "cleveland_fed", "CLEVELAND_FED__CORE_CPI_MOM",     "pct", "SA", "Cleveland Fed Core CPI MoM Nowcast",     is_leading_indicator=True, notes="External nowcast — use as feature only"),
]

# ── NFP feature series ─────────────────────────────────────────────────────────
NFP_FEATURE_SERIES: list[SeriesDefinition] = [
    SeriesDefinition("nfp_total_sa",          "bls",  "CES0000000001",  "K",     "SA",  "Total NFP"),
    SeriesDefinition("nfp_private_sa",        "bls",  "CES0500000001",  "K",     "SA",  "Private NFP"),
    SeriesDefinition("awh_sa",                "bls",  "CES0000000003",  "hours", "SA",  "Average Weekly Hours"),
    SeriesDefinition("ahe_sa",                "bls",  "CES0000000008",  "$/hr",  "SA",  "Average Hourly Earnings"),
    SeriesDefinition("unemployment_rate",     "bls",  "LNS14000000",    "pct",   "SA",  "Unemployment Rate"),
    SeriesDefinition("lfpr",                  "bls",  "LNS11300000",    "pct",   "SA",  "Labor Force Participation Rate"),
    SeriesDefinition("adp_employment",        "fred", "ADPWNUSNERSA",   "K",     "SA",  "ADP Employment", is_leading_indicator=True, publication_lag_days=-1, notes="Released ~2 days before NFP — use as leading indicator"),
    SeriesDefinition("jolts_openings",        "fred", "JTSJOL",         "K",     "SA",  "JOLTS Job Openings", is_leading_indicator=True, publication_lag_days=35),
    SeriesDefinition("jolts_hires",           "fred", "JTSHIR",         "K",     "SA",  "JOLTS Hires",        is_leading_indicator=True),
    SeriesDefinition("jolts_quits",           "fred", "JTSQUR",         "K",     "SA",  "JOLTS Quits",        is_leading_indicator=True),
    SeriesDefinition("jolts_layoffs",         "fred", "JTSLDR",         "K",     "SA",  "JOLTS Layoffs",      is_leading_indicator=True),
    SeriesDefinition("nfci",                  "fred", "NFCI",           "index", "",    "National Financial Conditions Index"),
]

# ── Treasury yield / market context series ─────────────────────────────────────
MARKET_CONTEXT_SERIES: list[SeriesDefinition] = [
    SeriesDefinition("us2y_yield",    "fred", "DGS2",    "pct", "", "2-Year Treasury Yield"),
    SeriesDefinition("us10y_yield",   "fred", "DGS10",   "pct", "", "10-Year Treasury Yield"),
    SeriesDefinition("10y2y_spread",  "fred", "T10Y2Y",  "pct", "", "10Y-2Y Spread"),
    SeriesDefinition("fedfunds",      "fred", "FEDFUNDS", "pct", "", "Fed Funds Rate"),
    SeriesDefinition("baa_spread",    "fred", "BAA10Y",  "pct", "", "Baa-Treasury Spread"),
    SeriesDefinition("umcsent",       "fred", "UMCSENT", "index", "", "Michigan Consumer Sentiment"),
]

# ── Master registry ────────────────────────────────────────────────────────────
ALL_SERIES: list[SeriesDefinition] = (
    CPI_FEATURE_SERIES + NFP_FEATURE_SERIES + MARKET_CONTEXT_SERIES
)

_BY_NAME: dict[str, SeriesDefinition] = {s.internal_name: s for s in ALL_SERIES}
_BY_SERIES_ID: dict[str, SeriesDefinition] = {s.series_id: s for s in ALL_SERIES}


def get_series(internal_name: str) -> SeriesDefinition | None:
    return _BY_NAME.get(internal_name)


def get_series_by_id(series_id: str) -> SeriesDefinition | None:
    return _BY_SERIES_ID.get(series_id)


def get_event_series(event_code: str) -> list[SeriesDefinition]:
    """Return the series definitions relevant to a given event code."""
    if event_code in ("US_CPI", "US_CORE_CPI"):
        return CPI_FEATURE_SERIES
    if event_code in ("US_NFP", "US_UNEMPLOYMENT_RATE", "US_AVERAGE_HOURLY_EARNINGS"):
        return NFP_FEATURE_SERIES
    if event_code in ("US_PPI", "US_CORE_PPI"):
        return [s for s in CPI_FEATURE_SERIES if "ppi" in s.internal_name or "import" in s.internal_name]
    # Default: market context only
    return MARKET_CONTEXT_SERIES
