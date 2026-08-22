"""
News ingestion -- v0.1 of the doc's M18 News Intelligence + M20 Sentiment.

Important scope note, read before wiring this to the full 176-stock
universe: there is no such thing as "all news" for a stock -- the doc's
own numbers are 50,000-500,000 articles/day across dozens of paid wire
subscriptions (Part 9). What's realistic without a Reuters/Bloomberg
contract is recent headlines + source + link, matched per ticker, deduped,
and lightly scored. That's what this module does. It does NOT fetch or
store full article bodies -- partly because most sources don't license
that for scraping, partly because reproducing article text runs into
copyright regardless of source.

Three interchangeable sources, same output shape
[{"title", "link", "source", "published_raw"}, ...]:

  - google_news_rss   Free, no signup. Unofficial (Google could change or
                       rate-limit the endpoint at any time) -- fine for a
                       personal research tool, throttle it, don't hammer it.
  - finnhub           Real API, free tier, needs your own key from
                       finnhub.io. Confirmed to carry India-market news;
                       verify the exact NSE symbol format works for your
                       tickers with one test call before looping over 176.
  - synthetic         Fully offline, fake headlines for testing the
                       dedup/sentiment/storage plumbing. Source names are
                       deliberately NOT real outlets (see below) so demo
                       output can never be mistaken for real reporting.
"""
import hashlib
import json
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import numpy as np
import pandas as pd
from datasketch import MinHash, MinHashLSH

USER_AGENT = "Mozilla/5.0 (compatible; ai-cio-research-bot/0.1)"


# ---------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------

def parse_google_news_rss(xml_text: str) -> list[dict]:
    """Standalone parser so it's testable without a live network call."""
    root = ET.fromstring(xml_text)
    items = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        source_el = item.find("source")
        items.append({
            "title": title,
            "link": (item.findtext("link") or "").strip(),
            "source": (source_el.text or "").strip() if source_el is not None else "unknown",
            "published_raw": (item.findtext("pubDate") or "").strip(),
        })
    return items


def fetch_google_news_rss(ticker: str, company_name: str, max_results: int = 10) -> list[dict]:
    query = f'{company_name} NSE'
    url = (f"https://news.google.com/rss/search?q={urllib.parse.quote(query)}"
           f"&hl=en-IN&gl=IN&ceid=IN:en")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        xml_text = resp.read().decode("utf-8", errors="replace")
    return parse_google_news_rss(xml_text)[:max_results]


def fetch_finnhub_news(ticker: str, company_name: str, max_results: int = 10,
                        api_key: str = None, days_back: int = 5) -> list[dict]:
    if not api_key:
        raise RuntimeError("Finnhub needs an API key -- get a free one at finnhub.io and pass it in")
    import datetime
    to_date, from_date = datetime.date.today(), datetime.date.today() - datetime.timedelta(days=days_back)
    url = (f"https://finnhub.io/api/v1/company-news?symbol={ticker}"
           f"&from={from_date}&to={to_date}&token={api_key}")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return [{
        "title": a.get("headline", ""), "link": a.get("url", ""),
        "source": a.get("source", "finnhub"), "published_raw": str(a.get("datetime", "")),
    } for a in data[:max_results]]


_DEMO_EVENTS = [
    "{c} reports better-than-expected quarterly profit",
    "{c} misses revenue estimates for the quarter",
    "{c} announces new board appointment",
    "Brokerage upgrades {c} to buy on strong outlook",
    "{c} shares fall after regulatory probe reported",
    "{c} wins large order, shares in focus",
    "{c} board approves fundraise plan",
    "Analysts cut price target on {c} after weak guidance",
]
_DEMO_SOURCES = ["demo-wire-1", "demo-wire-2", "demo-wire-3"]  # deliberately not real outlet names


def fetch_synthetic_news(ticker: str, company_name: str, max_results: int = 5, rng=None) -> list[dict]:
    """Fake headlines for testing only. Source names are placeholders on
    purpose -- never attribute generated text to a real news outlet."""
    rng = rng or np.random.default_rng(abs(hash(ticker)) % (2**32))
    n = min(max_results, rng.integers(2, 6))
    items = []
    for i in range(n):
        template = rng.choice(_DEMO_EVENTS)
        title = template.format(c=company_name)
        items.append({
            "title": title, "link": f"https://example.invalid/{ticker}-{i}",
            "source": rng.choice(_DEMO_SOURCES), "published_raw": "synthetic",
        })
        if rng.random() < 0.3:  # occasionally emit a near-duplicate from a "second source"
            reworded = title.replace("reports", "posts").replace("announces", "unveils").replace("wins", "secures")
            items.append({
                "title": reworded, "link": f"https://example.invalid/{ticker}-{i}-dup",
                "source": rng.choice(_DEMO_SOURCES), "published_raw": "synthetic",
            })
    return items


# ---------------------------------------------------------------------
# Dedup -- SHA-256 exact match, then MinHash LSH for near-duplicates
# (Part 9.1 stages 1-2 of the doc, minus the semantic-embedding stage,
# which needs a model this sandbox can't download)
# ---------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def _title_hash(text: str) -> str:
    return hashlib.sha256(_norm(text).encode()).hexdigest()


def _minhash(text: str, num_perm: int = 64) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for tok in set(_norm(text).split()):
        m.update(tok.encode("utf8"))
    return m


class Deduper:
    def __init__(self, jaccard_threshold: float = 0.6, num_perm: int = 64):
        self.seen_hashes = set()
        self.lsh = MinHashLSH(threshold=jaccard_threshold, num_perm=num_perm)
        self._counter = 0

    def check_and_add(self, title: str) -> str | None:
        """Returns None if new, else 'exact_duplicate' or 'near_duplicate'."""
        h = _title_hash(title)
        if h in self.seen_hashes:
            return "exact_duplicate"
        mh = _minhash(title)
        is_near = bool(self.lsh.query(mh))
        key = f"item_{self._counter}"
        self._counter += 1
        self.seen_hashes.add(h)
        self.lsh.insert(key, mh)
        return "near_duplicate" if is_near else None


# ---------------------------------------------------------------------
# Sentiment -- lexicon scorer. A placeholder for the doc's FinBERT (Part
# 5) -- this sandbox can't download model weights (no huggingface.co
# egress). Swap in `transformers` + FinBERT wherever you run this with
# GPU/network access; nothing else in this file needs to change, since
# downstream code only cares about (label, score).
# ---------------------------------------------------------------------

_POS = {"profit", "surge", "beat", "beats", "upgrade", "upgrades", "growth", "record", "rally",
        "gain", "gains", "strong", "expansion", "approval", "wins", "win", "boost", "outperform",
        "buy", "bullish", "soar", "jump"}
_NEG = {"loss", "losses", "plunge", "miss", "misses", "downgrade", "downgrades", "decline",
        "declines", "fraud", "probe", "lawsuit", "penalty", "weak", "cut", "cuts", "fall",
        "falls", "default", "scam", "ban", "crash", "resign", "resigns", "sell", "bearish",
        "slump", "slips"}


def simple_sentiment(title: str) -> tuple:
    tokens = _norm(title).replace(",", "").split()
    pos = sum(1 for t in tokens if t in _POS)
    neg = sum(1 for t in tokens if t in _NEG)
    score = round((pos - neg) / max(len(tokens), 1), 3)
    label = "neutral" if pos == neg else ("positive" if pos > neg else "negative")
    return label, score


# ---------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------

def fetch_news_for_universe(universe_df: pd.DataFrame, fetch_fn, max_per_ticker: int = 5,
                             sleep_s: float = 0.0) -> pd.DataFrame:
    """fetch_fn must match the (ticker, company_name, max_results) -> list[dict] shape
    of the source functions above. For google_news_rss on the real thing,
    set sleep_s >= 1.0 to be a reasonable citizen of an unofficial endpoint.

    A fresh Deduper is used per ticker -- dedup should only ever compare
    multiple sources covering the SAME company's story, never flag two
    different companies' headlines as duplicates of each other just
    because they're worded similarly."""
    rows = []
    for _, row in universe_df.iterrows():
        try:
            items = fetch_fn(row["ticker"], row["name"], max_per_ticker)
        except Exception as e:
            rows.append({"ticker": row["ticker"], "title": "", "source": "", "link": "",
                         "published_raw": "", "is_duplicate": False, "dup_reason": "",
                         "sentiment_label": "", "sentiment_score": np.nan, "fetch_error": str(e)})
            continue
        deduper = Deduper()  # per-ticker scope, see docstring
        for it in items:
            dup_reason = deduper.check_and_add(it["title"])
            label, score = simple_sentiment(it["title"])
            rows.append({
                "ticker": row["ticker"], "title": it["title"], "source": it.get("source", ""),
                "link": it.get("link", ""), "published_raw": it.get("published_raw", ""),
                "is_duplicate": dup_reason is not None, "dup_reason": dup_reason or "",
                "sentiment_label": label, "sentiment_score": score, "fetch_error": "",
            })
        if sleep_s:
            time.sleep(sleep_s)
    return pd.DataFrame(rows)
