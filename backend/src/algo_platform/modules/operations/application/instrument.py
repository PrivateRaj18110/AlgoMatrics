"""Parse option instrument metadata from a free-text symbol when present.

Google currently sends ``symbol`` as a string. Strike / expiry / CE-PE are
extracted only when they are literally in that string. Nothing is invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_OPTION_TYPE = re.compile(r"\b(CE|PE)\b", re.IGNORECASE)
_STRIKE = re.compile(r"\b(\d{4,6}(?:\.\d+)?)\b")
_EXPIRY = re.compile(
    r"\b(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4}|[A-Za-z]{3}[-/]\d{2,4}|\d{2}[A-Za-z]{3}\d{2,4})\b"
)
_FUT = re.compile(r"\bFUT(?:URE)?S?\b", re.IGNORECASE)


@dataclass(frozen=True)
class InstrumentParts:
    symbol: str
    underlying: str | None
    instrument: str | None
    expiry: str | None
    strike: str | None
    option_type: str | None
    metadata_available: bool


def parse_instrument(symbol: str | None) -> InstrumentParts:
    raw = (symbol or "").strip()
    if not raw:
        return InstrumentParts("", None, None, None, None, None, False)

    option = None
    match_opt = _OPTION_TYPE.search(raw)
    if match_opt:
        option = match_opt.group(1).upper()

    strike = None
    if option:
        match_strike = _STRIKE.search(raw)
        if match_strike:
            strike = match_strike.group(1)

    expiry = None
    match_exp = _EXPIRY.search(raw)
    if match_exp:
        expiry = match_exp.group(1)

    underlying = raw.split()[0] if raw.split() else raw
    if option:
        underlying = _OPTION_TYPE.sub("", raw)
        underlying = _STRIKE.sub("", underlying)
        underlying = _EXPIRY.sub("", underlying)
        underlying = re.sub(r"\s+", " ", underlying).strip(" -_/") or raw.split()[0]

    instrument = "FUT" if _FUT.search(raw) else ("OPT" if option else None)
    metadata_available = bool(option or expiry or (instrument == "FUT"))
    return InstrumentParts(
        symbol=raw,
        underlying=underlying if metadata_available else None,
        instrument=instrument,
        expiry=expiry,
        strike=strike,
        option_type=option,
        metadata_available=metadata_available,
    )
