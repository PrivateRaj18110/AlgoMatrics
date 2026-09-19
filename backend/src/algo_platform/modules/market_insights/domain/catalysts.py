"""Catalysts: what could move a stock today, from exchange filings and headlines.

Sources, all public:
- NSE corporate announcements (every listed company's filings, as filed),
- NSE event calendar (board meetings, including results dates),
- NSE corporate actions (ex-dates), the F&O ban list, bulk/block deals and
  futures open-interest spurts,
- market headlines from Indian business-news RSS feeds (titles and links only).

Everything here is rule-based and explainable: each filing gets a category, an
impact weight in [0, 1] and, where the wording supports it, a direction. The
rules are deliberately conservative — a routine filing (trading window,
newspaper copy, ESOP allotment) is weighed near zero so the day's real news is
not buried. Pure functions: no I/O.
"""

from __future__ import annotations

import csv
import hashlib
import io
import math
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from email.utils import parsedate_to_datetime
from typing import Any
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

#: Impact at or above which a filing counts as material for the model and the feed.
MATERIAL_IMPACT = 0.4
#: Impact at or above which a new intraday filing raises an alert.
ALERT_IMPACT = 0.6

MARKET_OPEN = time(9, 15)
MARKET_CLOSE = time(15, 30)
PREOPEN_FREEZE = time(9, 8)


@dataclass(frozen=True, slots=True)
class Catalyst:
    id: str
    symbol: str
    # nse_filing | results_calendar | ex_date | ban | block_deal | bulk_deal | news
    source: str
    category: str
    label: str
    impact: float
    direction: int  # +1 positive, -1 negative, 0 unclear
    title: str
    at: datetime | None  # timezone-aware, IST
    url: str | None = None
    company: str | None = None
    #: Set when an AI reader refined the rule-based impact/direction.
    note: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "source": self.source,
            "category": self.category,
            "label": self.label,
            "impact": round(self.impact, 2),
            "direction": self.direction,
            "title": self.title,
            "at": self.at.isoformat() if self.at else None,
            "url": self.url,
            "company": self.company,
            "note": self.note,
        }

    @staticmethod
    def from_dict(raw: Mapping[str, Any]) -> Catalyst:
        at = raw.get("at")
        return Catalyst(
            id=str(raw.get("id")),
            symbol=str(raw.get("symbol")),
            source=str(raw.get("source")),
            category=str(raw.get("category")),
            label=str(raw.get("label")),
            impact=float(raw.get("impact") or 0.0),
            direction=int(raw.get("direction") or 0),
            title=str(raw.get("title") or ""),
            at=datetime.fromisoformat(at) if isinstance(at, str) else None,
            url=raw.get("url"),
            company=raw.get("company"),
            note=raw.get("note"),
        )


# --------------------------------------------------------------------------------------
# Filing classification
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Rule:
    category: str
    label: str
    impact: float
    direction: int
    patterns: tuple[str, ...]
    #: Match the NSE subject line (``desc``) only, not the filing text.
    subject_only: bool = False


# Ordered: the first rule that matches wins, so specific rules sit above broad ones
# (a GST "order" is a penalty, not an order win; a SAST "acquisition of shares"
# is an insider disclosure, not M&A).
_RULES: tuple[_Rule, ...] = (
    _Rule(
        "results",
        "Financial results",
        0.9,
        0,
        (
            r"financial result",
            r"\bresults? for the (quarter|half|year)",
            r"audited (standalone|consolidated)",
            r"un-?audited",
        ),
    ),
    _Rule("buyback", "Buyback", 0.75, 1, (r"buy ?-?back",)),
    _Rule("m_and_a", "Open offer", 0.7, 0, (r"open offer",)),
    _Rule(
        "insider",
        "Promoter / insider disclosure",
        0.15,
        0,
        (r"\bsast\b", r"takeover regulations", r"insider trading", r"reg(ulation|\.) ?(29|31)\b"),
        subject_only=True,
    ),
    _Rule(
        "regulatory",
        "Regulatory action / penalty",
        0.55,
        -1,
        (
            r"penalty",
            r"show cause",
            r"\bsebi order",
            r"action\(s\) taken or orders passed",
            r"search (and|&) seizure",
            r"\braid",
            r"\bgst\b.*demand",
            r"tax demand",
            r"demand order",
            r"enforcement directorate",
            r"investigation",
            r"suspension of",
            r"\bcbi\b",
        ),
    ),
    _Rule(
        "litigation",
        "Litigation / dispute",
        0.45,
        -1,
        (
            r"litigation",
            r"dispute",
            r"\bnclt\b",
            r"insolvency",
            r"arbitration award",
            r"winding up",
        ),
    ),
    _Rule(
        "m_and_a",
        "Merger / acquisition",
        0.7,
        0,
        (
            r"acquisition",
            r"acquire",
            r"amalgamation",
            r"\bmerger\b",
            r"demerger",
            r"scheme of arrangement",
            r"slump sale",
            r"divest",
            r"stake sale",
        ),
    ),
    _Rule(
        "order_win",
        "Order / contract win",
        0.7,
        1,
        (
            r"bagging",
            r"receiving of orders",
            r"\borders? (worth|valued|of rs|from)",
            r"letter of (award|intent)",
            r"\bloa\b",
            r"\bcontract (worth|valued|from|for)",
            r"secures? .*order",
            r"wins? .*order",
            r"work order",
            r"purchase order",
        ),
    ),
    _Rule(
        "rating_down",
        "Credit rating downgrade",
        0.5,
        -1,
        (r"downgrad", r"revised downward", r"outlook.*negative", r"watch with negative"),
    ),
    _Rule(
        "rating_up",
        "Credit rating upgrade",
        0.4,
        1,
        (r"upgrad", r"revised upward", r"outlook.*positive", r"watch with positive"),
    ),
    _Rule(
        "clarification",
        "Clarification on news / volume",
        0.55,
        0,
        (
            r"clarification",
            r"news verification",
            r"spurt in (volume|price)",
            r"news item",
            r"media (report|article)",
        ),
    ),
    _Rule(
        "material_event",
        "Disclosure of material event",
        0.5,
        0,
        (
            r"disclosure of material issue",
            r"material event",
            r"\bfire\b",
            r"accident",
            r"cyber ?(attack|security incident)",
            r"plant shutdown",
            r"force majeure",
            r"\bstrike\b",
        ),
    ),
    _Rule(
        "fund_raise",
        "Fund raising",
        0.45,
        0,
        (
            r"qualified institutional placement",
            r"\bqip\b",
            r"preferential (issue|allotment)",
            r"rights issue",
            r"fund ?raising",
            r"raising of funds",
            r"issue of (non-convertible )?debentures",
        ),
    ),
    _Rule("bonus", "Bonus issue", 0.55, 1, (r"\bbonus (issue|shares)",)),
    _Rule(
        "split",
        "Stock split",
        0.45,
        1,
        (r"sub-?division", r"stock split", r"split of (equity )?shares"),
    ),
    _Rule(
        "auditor_exit",
        "Auditor resignation",
        0.5,
        -1,
        (r"resignation of (the )?(statutory )?auditor", r"auditor.*resign"),
    ),
    _Rule(
        "top_exit",
        "CEO / MD / CFO exit",
        0.5,
        -1,
        (
            r"(resignation|cessation|steps? down).*"
            r"(managing director|\bmd\b|chief executive|\bceo\b|chief financial|\bcfo\b"
            r"|whole[- ]time director)",
            r"(managing director|\bceo\b|\bcfo\b).*(resign|cessation)",
        ),
    ),
    _Rule(
        "pledge_up",
        "Promoter pledge created / invoked",
        0.35,
        -1,
        (r"(creation|invocation) of (pledge|encumbrance)", r"pledge.*invok"),
    ),
    _Rule("pledge_down", "Promoter pledge released", 0.2, 1, (r"release of (pledge|encumbrance)",)),
    _Rule(
        "capacity",
        "New capacity / production",
        0.4,
        1,
        (
            r"commencement of commercial (production|operation)",
            r"capacity expansion",
            r"new plant",
            r"commissioning",
        ),
    ),
    _Rule(
        "business_update",
        "Business / sales update",
        0.45,
        0,
        (
            r"business update",
            r"operational update",
            r"sales (update|number|volume)",
            r"production (update|number)",
            r"monthly (sales|business)",
            r"provisional (business|figures)",
            r"deposits? (growth|update)",
            r"\bauto sales\b",
        ),
    ),
    _Rule("dividend", "Dividend", 0.15, 1, (r"dividend",)),
    _Rule(
        "partnership",
        "Agreement / JV / partnership",
        0.35,
        1,
        (
            r"joint venture",
            r"\bmou\b",
            r"memorandum of understanding",
            r"strategic (partnership|alliance)",
            r"agreement with",
        ),
    ),
    _Rule("rating", "Credit rating (unchanged)", 0.1, 0, (r"credit rating", r"reaffirm")),
    _Rule(
        "management",
        "Management change",
        0.25,
        0,
        (
            r"resignation",
            r"appointment",
            r"change in management",
            r"change in director",
            r"cessation",
        ),
    ),
    _Rule("board_outcome", "Board meeting outcome", 0.3, 0, (r"outcome of (the )?board meeting",)),
    _Rule(
        "board_meeting",
        "Board meeting scheduled",
        0.15,
        0,
        (r"board meeting intimation", r"prior intimation", r"board meeting to be held"),
    ),
    _Rule(
        "investor_meet",
        "Analyst / investor meet",
        0.08,
        0,
        (
            r"analyst",
            r"investor meet",
            r"con\. call",
            r"conference call",
            r"investor presentation",
            r"earnings call",
        ),
    ),
    _Rule("press_release", "Press release", 0.3, 0, (r"press release",)),
    _Rule(
        "routine",
        "Routine compliance",
        0.03,
        0,
        (
            r"trading window",
            r"newspaper",
            r"shareholders meeting",
            r"\bagm\b",
            r"postal ballot",
            r"record date",
            r"esop",
            r"esos",
            r"loss of share certificate",
            r"duplicate share",
            r"certificate under",
            r"compliance",
            r"corrigendum",
            r"amendment to aoa",
            r"registered office",
            r"allotment of securities",
            r"statement of deviation",
            r"monitoring agency",
            r"change in auditor",
            r"closure of trading",
            r"reg\. ?74",
            r"integrated filing- ?governance",
        ),
    ),
)

_COMPILED = tuple(
    (rule, tuple(re.compile(p, re.IGNORECASE) for p in rule.patterns)) for rule in _RULES
)
_DEFAULT = _Rule("other", "Other filing", 0.1, 0, ())


def classify_filing(subject: str, text: str) -> tuple[str, str, float, int]:
    """(category, label, impact, direction) for one NSE filing."""
    haystack = f"{subject} || {text}"
    for rule, patterns in _COMPILED:
        target = subject if rule.subject_only else haystack
        if any(p.search(target) for p in patterns):
            impact = rule.impact
            # A results filing is only big news once the numbers are out: a
            # "board meeting to consider results" is a date, not the results.
            if rule.category == "results" and re.search(
                r"intimation|to consider|will be held|to be held", haystack, re.IGNORECASE
            ):
                return "results_scheduled", "Results date announced", 0.2, 0
            if rule.category == "results" and re.search(
                r"integrated filing", haystack, re.IGNORECASE
            ):
                impact = 0.6
            return rule.category, rule.label, impact, rule.direction
    return _DEFAULT.category, _DEFAULT.label, _DEFAULT.impact, _DEFAULT.direction


def _digest(text: str, size: int = 10) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:size]


def parse_nse_time(raw: Any) -> datetime | None:
    """NSE filing timestamps: '18-Sep-2026 23:59:24' or '2026-09-18 23:59:24' (IST)."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    for fmt in ("%d-%b-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%d-%b-%Y %H:%M", "%d-%b-%Y"):
        try:
            return datetime.strptime(raw.strip(), fmt).replace(tzinfo=IST)
        except ValueError:
            continue
    return None


def parse_announcements(rows: Iterable[Mapping[str, Any]], universe: set[str]) -> list[Catalyst]:
    """NSE corporate announcements → catalysts, for symbols in ``universe`` only."""
    out: list[Catalyst] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe:
            continue
        subject = str(row.get("desc") or "").strip()
        text = " ".join(str(row.get("attchmntText") or "").split())
        category, label, impact, direction = classify_filing(subject, text)
        at = parse_nse_time(row.get("sort_date")) or parse_nse_time(row.get("an_dt"))
        key = (
            str(row.get("seq_id") or "")
            or hashlib.sha256(f"{symbol}|{subject}|{row.get('an_dt')}".encode()).hexdigest()[:16]
        )
        out.append(
            Catalyst(
                id=f"nse:{key}",
                symbol=symbol,
                source="nse_filing",
                category=category,
                label=label,
                impact=impact,
                direction=direction,
                title=(text or subject)[:400],
                at=at,
                url=str(row.get("attchmntFile") or "") or None,
                company=str(row.get("sm_name") or "") or None,
            )
        )
    return out


def _nse_date(raw: Any) -> date | None:
    if not isinstance(raw, str):
        return None
    try:
        return datetime.strptime(raw.strip(), "%d-%b-%Y").date()
    except ValueError:
        return None


def parse_event_calendar(
    rows: Iterable[Mapping[str, Any]], universe: set[str], day: date
) -> list[Catalyst]:
    """Board meetings on ``day``; a results meeting is a strong same/next-day catalyst."""
    out: list[Catalyst] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe or _nse_date(row.get("date")) != day:
            continue
        purpose = f"{row.get('purpose') or ''} {row.get('bm_desc') or ''}"
        results = bool(re.search(r"financial result", purpose, re.IGNORECASE))
        fundraise = bool(re.search(r"fund ?rais|qip|preferential|rights", purpose, re.IGNORECASE))
        buyback = bool(re.search(r"buy ?-?back", purpose, re.IGNORECASE))
        if not (results or fundraise or buyback):
            continue
        category, label, impact = (
            ("results_today", "Results due today", 0.6)
            if results
            else ("buyback", "Board meets on buyback today", 0.5)
            if buyback
            else ("fund_raise", "Board meets on fund raising today", 0.35)
        )
        out.append(
            Catalyst(
                id=f"cal:{symbol}:{day.isoformat()}:{category}",
                symbol=symbol,
                source="results_calendar",
                category=category,
                label=label,
                impact=impact,
                direction=1 if buyback else 0,
                title=" ".join(str(row.get("bm_desc") or row.get("purpose") or "").split())[:300],
                at=datetime.combine(day, time(9, 0), IST),
                company=str(row.get("company") or "") or None,
            )
        )
    return out


def parse_corporate_actions(
    rows: Iterable[Mapping[str, Any]], universe: set[str], day: date
) -> list[Catalyst]:
    """Ex-dates falling on ``day``. Bonus/split ex-dates mechanically reprice the stock."""
    out: list[Catalyst] = []
    for row in rows:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe or _nse_date(row.get("exDate")) != day:
            continue
        subject = " ".join(str(row.get("subject") or "").split())
        adjusts = bool(re.search(r"bonus|split|sub-?division|rights", subject, re.IGNORECASE))
        out.append(
            Catalyst(
                id=f"ex:{symbol}:{day.isoformat()}:{hashlib.sha256(subject.encode()).hexdigest()[:8]}",
                symbol=symbol,
                source="ex_date",
                category="ex_adjustment" if adjusts else "ex_dividend",
                label="Ex-date: price adjusts" if adjusts else "Ex-dividend today",
                impact=0.0 if adjusts else 0.05,
                direction=0,
                title=subject[:200],
                at=datetime.combine(day, time(9, 0), IST),
                company=str(row.get("comp") or "") or None,
            )
        )
    return out


def parse_secban(text: str) -> tuple[date | None, set[str]]:
    """'Securities in Ban For Trade Date 21-SEP-2026:\\n1,BANDHANBNK\\n...'"""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return None, set()
    header = re.search(r"(\d{2}-[A-Za-z]{3}-\d{4})", lines[0])
    for_date = None
    if header:
        try:
            for_date = datetime.strptime(header.group(1).title(), "%d-%b-%Y").date()
        except ValueError:
            for_date = None
    symbols = set()
    for row in csv.reader(io.StringIO("\n".join(lines[1:]))):
        if len(row) >= 2 and row[1].strip():
            symbols.add(row[1].strip().upper())
    return for_date, symbols


def ban_catalysts(symbols: set[str], universe: set[str], day: date) -> list[Catalyst]:
    return [
        Catalyst(
            id=f"ban:{symbol}:{day.isoformat()}",
            symbol=symbol,
            source="ban",
            category="fo_ban",
            label="In F&O ban period",
            impact=0.3,
            direction=0,
            title="Open interest crossed 95% of the market-wide limit; no new F&O positions today.",
            at=datetime.combine(day, time(9, 0), IST),
        )
        for symbol in sorted(symbols & universe)
    ]


def parse_large_deals(payload: Mapping[str, Any], universe: set[str]) -> list[Catalyst]:
    """Previous session's bulk and block deals for the universe."""
    out: list[Catalyst] = []
    for key, source, label in (
        ("BULK_DEALS_DATA", "bulk_deal", "Bulk deal"),
        ("BLOCK_DEALS_DATA", "block_deal", "Block deal"),
    ):
        for row in payload.get(key) or []:
            symbol = str(row.get("symbol") or "").strip().upper()
            if symbol not in universe:
                continue
            side = str(row.get("buySell") or "").upper()
            client = " ".join(str(row.get("clientName") or "").split())
            deal_day = _nse_date(row.get("date"))
            fingerprint = _digest(client + side + str(row.get("qty")))
            out.append(
                Catalyst(
                    id=f"{source}:{symbol}:{row.get('date')}:{fingerprint}",
                    symbol=symbol,
                    source=source,
                    category="large_deal",
                    label=f"{label} ({side.lower() or 'deal'})",
                    impact=0.3,
                    direction=1 if side == "BUY" else -1 if side == "SELL" else 0,
                    title=f"{client} {side.lower()} {row.get('qty')} shares @ ₹{row.get('watp')}",
                    at=datetime.combine(deal_day, time(15, 30), IST) if deal_day else None,
                )
            )
    return out


def parse_oi_spurts(payload: Mapping[str, Any], universe: set[str]) -> dict[str, float]:
    """Symbol → % change in futures+options open interest over the last session."""
    out: dict[str, float] = {}
    for row in payload.get("data") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol not in universe:
            continue
        try:
            latest = float(row.get("latestOI") or 0)
            previous = float(row.get("prevOI") or 0)
        except (TypeError, ValueError):
            continue
        if previous > 0:
            out[symbol] = round((latest - previous) / previous * 100, 2)
    return out


# --------------------------------------------------------------------------------------
# Headlines
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Headline:
    id: str
    title: str
    source: str
    url: str | None
    at: datetime | None
    symbols: list[str] = field(default_factory=list)
    sentiment: int = 0  # +1 / -1 / 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "title": self.title,
            "source": self.source,
            "url": self.url,
            "at": self.at.isoformat() if self.at else None,
            "symbols": self.symbols,
            "sentiment": self.sentiment,
        }


def parse_rss(xml_text: str, source: str) -> list[Headline]:
    """Titles, links and times from an RSS feed. Refuses DTDs (entity expansion)."""
    if re.search(r"<!DOCTYPE|<!ENTITY", xml_text[:2000], re.IGNORECASE):
        return []
    try:
        # DTDs are refused above and expat never resolves external entities.
        root = ElementTree.fromstring(xml_text.encode("utf-8", errors="replace"))  # noqa: S314
    except ElementTree.ParseError:
        return []
    out: list[Headline] = []
    for item in root.iter("item"):
        title = " ".join((item.findtext("title") or "").split())
        if not title or _QUOTE_PAGE.search(title):
            continue
        link = (item.findtext("link") or "").strip() or None
        feed_source = item.find("source")
        publisher = (
            (feed_source.text or "").strip()
            if feed_source is not None and feed_source.text
            else source
        )
        at: datetime | None = None
        raw = item.findtext("pubDate")
        if raw:
            try:
                at = parsedate_to_datetime(raw.strip()).astimezone(IST)
            except (TypeError, ValueError, IndexError):
                at = None
        key = hashlib.sha256(_normal(title).encode()).hexdigest()[:16]
        out.append(
            Headline(id=f"news:{key}", title=title[:300], source=publisher[:60], url=link, at=at)
        )
    return out


_POSITIVE = (
    "surge",
    "surges",
    "soar",
    "soars",
    "jump",
    "jumps",
    "rally",
    "rallies",
    "gain",
    "gains",
    "rise",
    "rises",
    "record high",
    "beats",
    "beat estimates",
    "upgrade",
    "upgrades",
    "wins",
    "bags",
    "secures",
    "order",
    "profit rises",
    "profit jumps",
    "strong",
    "buyback",
    "bonus",
    "approval",
    "approves",
    "expansion",
    "top gainer",
    "outperform",
    "bullish",
    "raises guidance",
    "hike target",
    "target price raised",
)
_NEGATIVE = (
    "plunge",
    "plunges",
    "crash",
    "crashes",
    "slump",
    "slumps",
    "fall",
    "falls",
    "drop",
    "drops",
    "tumble",
    "tumbles",
    "sink",
    "sinks",
    "misses",
    "miss estimates",
    "downgrade",
    "downgrades",
    "loss",
    "losses",
    "penalty",
    "probe",
    "raid",
    "fraud",
    "resigns",
    "resignation",
    "weak",
    "cut target",
    "target cut",
    "bearish",
    "underperform",
    "top loser",
    "default",
    "ban",
    "warning",
    "slashes",
)


def _normal(text: str) -> str:
    return re.sub(r"[^a-z0-9& ]+", " ", text.lower()).strip()


# Phrases whose words would otherwise read as tone ("stop-loss" is not a loss).
_NEUTRAL_PHRASES = ("stop loss", "profit booking", "loss making", "target price")

#: Quote / price pages that search feeds return as "news".
_QUOTE_PAGE = re.compile(
    r"share price (today|live|nse|bse)|stock price (today|live)|price & chart|share price, stock"
    r"|live share price|stock quote",
    re.IGNORECASE,
)


def headline_sentiment(title: str) -> int:
    text = f" {_normal(title)} "
    for phrase in _NEUTRAL_PHRASES:
        text = text.replace(f" {phrase} ", " ")
    positive = sum(1 for word in _POSITIVE if f" {word} " in text)
    negative = sum(1 for word in _NEGATIVE if f" {word} " in text)
    return 1 if positive > negative else -1 if negative > positive else 0


# Everyday names for tickers whose company name does not appear in headlines as filed.
_ALIASES: dict[str, tuple[str, ...]] = {
    "RELIANCE": ("reliance industries", "ril", "reliance jio"),
    "SBIN": ("sbi", "state bank of india"),
    "LT": ("l&t", "larsen"),
    "M&M": ("m&m", "mahindra & mahindra", "mahindra and mahindra"),
    "HINDUNILVR": ("hul", "hindustan unilever"),
    "BAJFINANCE": ("bajaj finance",),
    "BAJAJFINSV": ("bajaj finserv",),
    "BAJAJ-AUTO": ("bajaj auto",),
    "HDFCBANK": ("hdfc bank",),
    "HDFCLIFE": ("hdfc life",),
    "ICICIBANK": ("icici bank",),
    "ICICIPRULI": ("icici prudential life", "icici pru life"),
    "ICICIGI": ("icici lombard",),
    "KOTAKBANK": ("kotak mahindra bank", "kotak bank"),
    "AXISBANK": ("axis bank",),
    "INFY": ("infosys",),
    "TCS": ("tcs", "tata consultancy"),
    "HCLTECH": ("hcltech", "hcl tech", "hcl technologies"),
    "TECHM": ("tech mahindra",),
    "WIPRO": ("wipro",),
    "TATAMOTORS": ("tata motors",),
    "TMPV": ("tata motors passenger",),
    "TATASTEEL": ("tata steel",),
    "TATAPOWER": ("tata power",),
    "TATACONSUM": ("tata consumer",),
    "TITAN": ("titan",),
    "MARUTI": ("maruti", "maruti suzuki"),
    "SUNPHARMA": ("sun pharma",),
    "DRREDDY": ("dr reddy", "dr. reddy"),
    "ONGC": ("ongc",),
    "BPCL": ("bpcl", "bharat petroleum"),
    "IOC": ("indian oil", "ioc"),
    "HINDPETRO": ("hpcl", "hindustan petroleum"),
    "NTPC": ("ntpc",),
    "POWERGRID": ("power grid",),
    "COALINDIA": ("coal india",),
    "ITC": ("itc",),
    "ADANIENT": ("adani enterprises",),
    "ADANIPORTS": ("adani ports",),
    "ADANIGREEN": ("adani green",),
    "ADANIPOWER": ("adani power",),
    "BHARTIARTL": ("bharti airtel", "airtel"),
    "IDEA": ("vodafone idea", "vi "),
    "ASIANPAINT": ("asian paints",),
    "ULTRACEMCO": ("ultratech",),
    "NESTLEIND": ("nestle india",),
    "HEROMOTOCO": ("hero motocorp",),
    "EICHERMOT": ("eicher", "royal enfield"),
    "ETERNAL": ("eternal", "zomato", "blinkit"),
    "PAYTM": ("paytm", "one97"),
    "NYKAA": ("nykaa",),
    "INDIGO": ("indigo", "interglobe"),
    "IRCTC": ("irctc",),
    "HAL": ("hal", "hindustan aeronautics"),
    "BEL": ("bharat electronics",),
    "BHEL": ("bhel",),
    "SAIL": ("sail", "steel authority"),
    "JSWSTEEL": ("jsw steel",),
    "HINDALCO": ("hindalco",),
    "VEDL": ("vedanta",),
    "PNB": ("punjab national bank", "pnb"),
    "BANKBARODA": ("bank of baroda",),
    "CANBK": ("canara bank",),
    "INDUSINDBK": ("indusind",),
    "YESBANK": ("yes bank",),
    "IDFCFIRSTB": ("idfc first",),
    "LICI": ("lic",),
    "DMART": ("dmart", "avenue supermarts"),
    "TRENT": ("trent", "zudio"),
    "DIXON": ("dixon",),
    "POLYCAB": ("polycab",),
}

_GENERIC = {
    "limited",
    "ltd",
    "india",
    "industries",
    "corporation",
    "company",
    "co",
    "the",
    "and",
    "&",
    "of",
    "bank",
}


def name_index(companies: Mapping[str, str | None]) -> list[tuple[re.Pattern[str], str]]:
    """Patterns that find a ticker's company in a headline.

    ``companies`` maps symbol → company name as filed (e.g. from NSE filings or
    Yahoo). Names are cut to their distinctive words; one-word generic names are
    left to the alias table so "India" or "Power" alone never matches.
    """
    patterns: list[tuple[re.Pattern[str], str]] = []
    for symbol, company in companies.items():
        phrases = set(_ALIASES.get(symbol, ()))
        if company:
            words = [w for w in _normal(company).split() if w]
            while words and words[-1] in {"limited", "ltd", "corporation", "company", "co"}:
                words.pop()
            distinctive = [w for w in words if w not in _GENERIC]
            if len(words) >= 2 and distinctive:
                phrases.add(" ".join(words[:3]) if len(words) >= 3 else " ".join(words))
                phrases.add(" ".join(words[:2]))
            elif len(distinctive) == 1 and len(distinctive[0]) >= 5:
                phrases.add(distinctive[0])
        for phrase in phrases:
            phrase = _normal(phrase)
            if len(phrase) < 3:
                continue
            patterns.append((re.compile(rf"(?<![a-z0-9]){re.escape(phrase)}(?![a-z0-9])"), symbol))
    return patterns


def tag_headlines(
    headlines: Iterable[Headline], index: list[tuple[re.Pattern[str], str]]
) -> list[Headline]:
    tagged: list[Headline] = []
    for item in headlines:
        text = _normal(item.title)
        symbols = sorted({symbol for pattern, symbol in index if pattern.search(text)})
        tagged.append(
            Headline(
                id=item.id,
                title=item.title,
                source=item.source,
                url=item.url,
                at=item.at,
                symbols=symbols,
                sentiment=headline_sentiment(item.title),
            )
        )
    return tagged


# --------------------------------------------------------------------------------------
# Windows
# --------------------------------------------------------------------------------------


def previous_session(day: date) -> date:
    """The weekday before ``day`` (exchange holidays are not modelled)."""
    prior = day - timedelta(days=1)
    while prior.weekday() >= 5:
        prior -= timedelta(days=1)
    return prior


def overnight_window(day: date) -> tuple[datetime, datetime]:
    """Filings that land between the last close and the pre-open freeze feed today's forecast."""
    start = datetime.combine(previous_session(day), MARKET_CLOSE, IST)
    end = datetime.combine(day, PREOPEN_FREEZE, IST)
    return start, end


def in_window(at: datetime | None, window: tuple[datetime, datetime]) -> bool:
    return at is not None and window[0] < at <= window[1]


def impact_total(impacts: Iterable[float]) -> float:
    """Combine several catalysts: 1 - Π(1 - impact). Two 0.5s make 0.75, not 1.0."""
    remaining = 1.0
    for impact in impacts:
        remaining *= 1.0 - max(0.0, min(1.0, impact))
    return round(1.0 - remaining, 4)


def log_count(count: int) -> float:
    return math.log1p(max(0, count))
