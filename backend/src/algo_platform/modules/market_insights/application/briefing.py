"""AI-CIO morning briefing: one e-mail per trading day, also kept as a daily log.

Sent to the platform owner(s) at about 09:10 IST — right after the pre-open
auction, before the 09:15 open — or with the overnight forecast by 09:30 if the
auction data did not arrive (usually an exchange holiday). It covers:

* how the last forecast graded on the close;
* today's likely major movers, with direction and reasons;
* the overnight exchange filings that matter, and today's exchange events;
* market cues (pre-open breadth, institutional flows);
* the routine log: what AI-CIO collected and built, and the health of every
  background process.

The content is assembled once as sections and rendered twice — plain text and
e-mail HTML (inline styles and tables, which is what mail clients render). Every
briefing is stored (kind ``mv_briefing``) whether or not e-mail delivery is
configured, so the console keeps the daily log either way.
"""

from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

from algo_platform.modules.market_insights.application.movers import (
    KIND_CATALYSTS,
    KIND_FORECAST,
    KIND_NEWS,
    KIND_OUTCOME,
    MoversService,
    SnapshotStore,
)
from algo_platform.modules.market_insights.application.service import (
    KIND_FII_DII,
    KIND_PREOPEN,
    ist_now,
)
from algo_platform.modules.market_insights.domain.catalysts import previous_session
from algo_platform.modules.market_insights.domain.premarket import parse_preopen
from algo_platform.modules.market_insights.domain.pulse import parse_fii_dii
from algo_platform.shared.application.ports import EmailMessage, EmailSender
from algo_platform.shared.infrastructure.heartbeats import Heartbeat

KIND_BRIEFING = "mv_briefing"
EMAIL_DISCLAIMER = (
    "AI-CIO ranks situations from public filings, exchange data, headlines and prices, and "
    "is graded against the close every day. It is a research aid, not investment advice, "
    "and it never places orders."
)
SEND_FROM = time(9, 10)
WAIT_FOR_AUCTION_UNTIL = time(9, 30)
SEND_UNTIL = time(10, 30)
TOP = 10

_ARROW = {"up": "▲ up", "down": "▼ down", "either": "↕ either way"}
_HEALTH = {"ok": "running", "overdue": "OVERDUE", "missing": "NO HEARTBEAT"}
_TONE = {"up": "#059669", "down": "#dc2626", "either": "#64748b"}


@dataclass(frozen=True, slots=True)
class Briefing:
    day: date
    subject: str
    text: str
    html: str
    stage: str | None


@dataclass(slots=True)
class _Item:
    text: str
    detail: str = ""
    url: str | None = None


@dataclass(slots=True)
class _Section:
    title: str
    intro: str = ""
    items: list[_Item] = field(default_factory=list)
    movers: list[dict[str, Any]] = field(default_factory=list)
    chips: list[tuple[str, str]] = field(default_factory=list)  # (text, state)


def _ratio(value: Any, digits: int = 0) -> str:
    return "—" if not isinstance(value, int | float) else f"{value * 100:.{digits}f}%"


def _signed(value: Any) -> str:
    return "—" if not isinstance(value, int | float) else f"{value:+.1f}%"


def _chance(probability: Any) -> str:
    if not isinstance(probability, int | float):
        return "—"
    return "<1%" if probability < 0.01 else f"{probability * 100:.0f}%"


def _stamp(value: Any) -> str:
    if not isinstance(value, str) or not value:
        return "—"
    try:
        return datetime.fromisoformat(value).strftime("%d %b %H:%M")
    except ValueError:
        return value[:16]


def _crore(value: Any) -> str:
    return "—" if not isinstance(value, int | float) else f"₹{value:+,.0f} cr"


def _safe_url(value: Any) -> str | None:
    ok = isinstance(value, str) and value.startswith(("https://", "http://"))
    return value if ok else None


def briefing_recipients(owners: Iterable[str], extra: str = "") -> list[str]:
    """Platform owners plus any comma-separated extra addresses, deduplicated."""
    candidates = [*owners, *extra.replace(";", ",").split(",")]
    return sorted({address.strip().lower() for address in candidates if "@" in address})


class BriefingService:
    def __init__(self, store: SnapshotStore, movers: MoversService) -> None:
        self._store = store
        self._movers = movers

    async def due(self, now: datetime) -> bool:
        """A weekday morning, not yet sent, and the auction is in (or we stopped waiting)."""
        if now.weekday() >= 5 or not (SEND_FROM <= now.time() <= SEND_UNTIL):
            return False
        day = now.date()
        if await self._store.get(KIND_BRIEFING, day) is not None:
            return False
        opening = await self._store.get(KIND_FORECAST["opening"], day)
        return opening is not None or now.time() >= WAIT_FOR_AUCTION_UNTIL

    async def build(
        self,
        day: date,
        *,
        heartbeats: Sequence[Heartbeat] = (),
        alerts_yesterday: int | None = None,
        delivery: str = "console",
        console_url: str = "",
    ) -> Briefing:
        sections = await self._sections(day, heartbeats, alerts_yesterday, delivery)
        opening = await self._store.get(KIND_FORECAST["opening"], day)
        forecast = opening or await self._store.get(KIND_FORECAST["overnight"], day)
        stage = forecast["stage"] if forecast else None
        leaders = ", ".join(row["symbol"] for row in (forecast or {}).get("stocks", [])[:3])
        subject = f"AI-CIO briefing · {day:%a %d %b}" + (f" · watch {leaders}" if leaders else "")
        heading = f"Morning briefing — {day:%a %d %b %Y}"
        byline = (
            "Opening forecast · includes the 09:08 pre-open auction"
            if stage == "opening"
            else "Overnight forecast · no pre-open auction data today"
            if stage == "overnight"
            else "No forecast this morning"
        )
        return Briefing(
            day=day,
            subject=subject,
            text=_render_text(heading, byline, sections, console_url),
            html=_render_html(heading, byline, sections, console_url),
            stage=stage,
        )

    async def _sections(
        self,
        day: date,
        heartbeats: Sequence[Heartbeat],
        alerts_yesterday: int | None,
        delivery: str,
    ) -> list[_Section]:
        store = self._store
        opening = await store.get(KIND_FORECAST["opening"], day)
        overnight = await store.get(KIND_FORECAST["overnight"], day)
        forecast = opening or overnight
        sections: list[_Section] = []

        graded = await store.latest(KIND_OUTCOME, on_or_before=previous_session(day))
        if graded is not None:
            grades = graded[1].get("grades") or {}
            grade = grades.get("opening") or grades.get("overnight")
            if grade:
                lift = grade.get("lift")
                verdict = (
                    f"{lift:.1f}x better than picking at random"
                    if isinstance(lift, int | float) and lift >= 1.05
                    else "no better than picking at random"
                )
                sections.append(
                    _Section(
                        f"Last session · {graded[0]:%a %d %b}",
                        f"{grade['hits']} of the top {grade['top_k']} made a major move "
                        f"({_ratio(grade.get('precision'))}) against "
                        f"{_ratio(grade.get('base_rate'), 1)} of all stocks — {verdict}. "
                        f"Direction right on {grade.get('direction_right', 0)} "
                        f"of {grade.get('direction_calls', 0)}.",
                    )
                )

        if forecast and forecast.get("stocks"):
            sections.append(
                _Section(
                    "Today's likely major movers",
                    f"Major move = {forecast.get('threshold_rule')}. Expected about "
                    f"{round(forecast.get('expected_majors') or 0)} of {forecast.get('universe')}.",
                    movers=forecast["stocks"][:TOP],
                )
            )
        else:
            sections.append(
                _Section("Today", "No forecast could be built this morning; see the routine log.")
            )

        catalysts = await self._movers.catalysts(day, min_impact=0.5)
        filings: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        # NSE sometimes files the same notice twice (e.g. query + response); list it once.
        for f in sorted(
            (f for f in catalysts["filings"] if f.get("session") == "overnight"),
            key=lambda f: -float(f.get("impact") or 0),
        ):
            key = (f["symbol"], f["label"], f["title"][:120])
            if key not in seen:
                seen.add(key)
                filings.append(f)
        filings = filings[:10]
        if filings:
            sections.append(
                _Section(
                    "Overnight filings that matter",
                    items=[
                        _Item(
                            f"{f['symbol']} · {f['label']}",
                            f["title"][:220],
                            _safe_url(f.get("url")),
                        )
                        for f in filings
                    ],
                )
            )
        events = _event_lines(catalysts["events"])
        if events:
            sections.append(_Section("On the exchange today", items=[_Item(t) for t in events]))

        cues: list[_Item] = []
        preopen_payload = await store.get(KIND_PREOPEN, day)
        if preopen_payload:
            snap = parse_preopen(preopen_payload)
            cues.append(
                _Item(
                    f"Pre-open: {snap.advances} up / {snap.declines} down "
                    f"across {len(snap.stocks)} F&O stocks"
                )
            )
        flows = await store.latest(KIND_FII_DII, on_or_before=day)
        flow = parse_fii_dii(flows[1]) if flows else None
        if flow:
            cues.append(
                _Item(
                    f"Institutional flows ({flow.trade_date}): FII {_crore(flow.fii_net)}, "
                    f"DII {_crore(flow.dii_net)}"
                )
            )
        if cues:
            sections.append(_Section("Market cues", items=cues))

        log = await self._routine_log(day, overnight, opening, graded, alerts_yesterday, delivery)
        sections.append(
            _Section(
                "Routine log",
                items=[_Item(entry) for entry in log],
                chips=[(f"{hb.label} · {_HEALTH[hb.state]}", hb.state) for hb in heartbeats],
            )
        )
        return sections

    async def _routine_log(
        self,
        day: date,
        overnight: dict[str, Any] | None,
        opening: dict[str, Any] | None,
        graded: tuple[date, Any] | None,
        alerts_yesterday: int | None,
        delivery: str,
    ) -> list[str]:
        filings = await self._store.get(KIND_CATALYSTS, day) or {}
        news = await self._store.get(KIND_NEWS, day) or {}
        _, model = await self._movers.model()
        record = await self._movers.track_record()
        log = [
            f"Filings on F&O stocks since the last close: {len(filings.get('items', []))} "
            f"(last checked {_stamp(filings.get('updated_at'))})",
            f"Headlines read: {len(news.get('items', []))} from {news.get('feeds') or 0} feeds "
            f"(last read {_stamp(news.get('updated_at'))})",
            "Overnight forecast: "
            + (_stamp(overnight["generated_at"]) if overnight else "not built"),
            "Opening forecast: "
            + (_stamp(opening["generated_at"]) if opening else "not built (no pre-open data)"),
        ]
        if graded is not None:
            evaluated = _stamp(graded[1].get("evaluated_at"))
            log.append(f"Last graded session: {graded[0]:%a %d %b} (graded {evaluated})")
        fitted = model.get("source") == "fitted"
        log.append(
            f"Model: fitted on {model.get('days')} graded sessions ({model.get('version')})"
            if fitted
            else "Model: starting weights (not yet fitted)"
        )
        live = ((record.get("live") or {}).get("opening") or {}).get("summary") or {}
        if live.get("days"):
            sessions = f"{live['days']} session" + ("s" if live["days"] != 1 else "")
            log.append(
                f"Live record, last {sessions}: top-10 hit "
                f"{_ratio(live.get('precision'))} vs base {_ratio(live.get('base_rate'), 1)}"
            )
        backtest = record.get("backtest") or {}
        summary = (((backtest.get("stages") or {}).get("opening") or {}).get("fitted") or {}).get(
            "summary"
        ) or {}
        if summary.get("days"):
            log.append(
                f"Backtest ({backtest.get('ran_on')}, out of sample): top-10 hit "
                f"{_ratio(summary.get('precision'))} vs base {_ratio(summary.get('base_rate'), 1)}"
            )
        if alerts_yesterday is not None:
            log.append(f"Filing alerts sent last session: {alerts_yesterday}")
        if delivery != "smtp":
            log.append(
                "E-mail delivery is not configured on the server; "
                "this briefing is kept in the console only."
            )
        return log

    async def send(
        self,
        day: date,
        *,
        recipients: Iterable[str],
        sender: EmailSender,
        heartbeats: Sequence[Heartbeat] = (),
        alerts_yesterday: int | None = None,
        delivery: str = "console",
        console_url: str = "",
    ) -> dict[str, Any]:
        briefing = await self.build(
            day,
            heartbeats=heartbeats,
            alerts_yesterday=alerts_yesterday,
            delivery=delivery,
            console_url=console_url,
        )
        to = briefing_recipients(recipients)
        for address in to:
            await sender.send(
                EmailMessage(
                    to=address, subject=briefing.subject, text=briefing.text, html=briefing.html
                )
            )
        payload = {
            "sent_at": ist_now().isoformat(),
            "subject": briefing.subject,
            "stage": briefing.stage,
            "recipients": to,
            "delivery": delivery,
            "text": briefing.text,
            "html": briefing.html,
        }
        await self._store.put(KIND_BRIEFING, day, payload)
        return payload

    async def archive(self, day: date | None = None) -> dict[str, Any]:
        history = await self._store.history(KIND_BRIEFING, 60)
        chosen: tuple[date, Any] | None
        if day is not None:
            payload = await self._store.get(KIND_BRIEFING, day)
            chosen = (day, payload) if payload is not None else None
        else:
            chosen = history[0] if history else None
        return {
            "dates": [when.isoformat() for when, _ in history],
            "briefing": None if chosen is None else {"day": chosen[0].isoformat(), **chosen[1]},
        }


def _event_lines(events: Sequence[dict[str, Any]]) -> list[str]:
    groups: dict[str, set[str]] = {}
    for item in events:
        groups.setdefault(item.get("category", ""), set()).add(item.get("symbol", ""))
    lines = []
    for category, title in (
        ("results_today", "Results due today"),
        ("fo_ban", "In F&O ban"),
        ("ex_adjustment", "Ex-date, price adjusts (bonus/split)"),
        ("buyback", "Board meets on a buyback"),
        ("large_deal", "Bulk/block deals last session"),
    ):
        symbols = sorted(groups.get(category, set()))
        if symbols:
            more = " …" if len(symbols) > 15 else ""
            lines.append(f"{title}: {', '.join(symbols[:15])}{more}")
    return lines


# --------------------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------------------


def _why(row: dict[str, Any]) -> list[str]:
    return [reason["text"] for reason in row.get("reasons", [])[:2]] or ["Volatility"]


def _render_text(heading: str, byline: str, sections: list[_Section], console_url: str) -> str:
    lines = [f"AI-CIO {heading}", byline, ""]
    for section in sections:
        lines.append(section.title.upper())
        if section.intro:
            lines.append(section.intro)
        for row in section.movers:
            arrow = _ARROW.get(row["direction"], row["direction"])
            lines.append(
                f"{row['rank']:>2}. {row['symbol']:<12} {_chance(row['probability']):>4}  "
                f"{arrow:<14} gap {_signed(row.get('gap_pct'))} — {'; '.join(_why(row))}"
            )
        for item in section.items:
            lines.append(f"- {item.text}" + (f" — {item.detail}" if item.detail else ""))
        if section.chips:
            lines.append("- Background processes: " + ", ".join(text for text, _ in section.chips))
        lines.append("")
    lines.append(EMAIL_DISCLAIMER)
    if console_url:
        lines.append(f"Open in the console: {console_url}/app/market-intelligence")
    return "\n".join(lines)


_E = html.escape
_CELL = "padding:8px 6px;border-top:1px solid #e2e8f0;vertical-align:top;"
_SMALL = "font-size:12px;color:#64748b;"
_LABEL = (
    "font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#64748b;font-weight:600"
)


def _mover_rows(rows: list[dict[str, Any]]) -> str:
    out = []
    for row in rows:
        tone = _TONE.get(row["direction"], "#64748b")
        why = "<br>".join(_E(text) for text in _why(row))
        out.append(
            "<tr>"
            f'<td style="{_CELL}{_SMALL}">{row["rank"]}</td>'
            f'<td style="{_CELL}"><b style="font-size:14px">{_E(row["symbol"])}</b>'
            f'<div style="{_SMALL}">{_E(row.get("sector", ""))}</div></td>'
            f'<td style="{_CELL}font-size:14px;font-weight:700">'
            f"{_E(_chance(row['probability']))}</td>"
            f'<td style="{_CELL}font-size:12px;font-weight:600;color:{tone};white-space:nowrap">'
            f"{_E(_ARROW.get(row['direction'], row['direction']))}"
            f'<div style="{_SMALL}font-weight:400">gap {_E(_signed(row.get("gap_pct")))}</div></td>'
            f'<td style="{_CELL}font-size:12px;color:#334155">{why}</td>'
            "</tr>"
        )
    head = "".join(
        f'<td style="padding:4px 6px">{title}</td>'
        for title in ("#", "Stock", "Chance", "Direction", "Why")
    )
    return (
        '<table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">'
        f'<tr style="font-size:10px;color:#94a3b8;text-transform:uppercase">{head}</tr>'
        + "".join(out)
        + "</table>"
    )


def _chip(text: str, state: str) -> str:
    color = {"ok": "#059669", "overdue": "#d97706"}.get(state, "#dc2626")
    return (
        '<span style="display:inline-block;margin:3px 6px 3px 0;padding:3px 8px;'
        f"border-radius:999px;border:1px solid {color};color:{color};font-size:11px;"
        f'font-weight:600">{_E(text)}</span>'
    )


def _section_html(section: _Section) -> str:
    body = [f'<div style="{_LABEL}">{_E(section.title)}</div>']
    if section.intro:
        body.append(
            f'<p style="margin:8px 0;font-size:14px;line-height:1.5">{_E(section.intro)}</p>'
        )
    if section.movers:
        body.append(_mover_rows(section.movers))
    if section.items:
        items = []
        for item in section.items:
            link = (
                f' <a href="{_E(item.url, quote=True)}" style="color:#0e7490">filing ↗</a>'
                if item.url
                else ""
            )
            detail = f'<div style="{_SMALL}">{_E(item.detail)}</div>' if item.detail else ""
            items.append(
                f'<li style="margin:5px 0;font-size:13px">{_E(item.text)}{link}{detail}</li>'
            )
        body.append(f'<ul style="margin:8px 0 0;padding-left:18px">{"".join(items)}</ul>')
    if section.chips:
        body.append(
            f'<div style="margin-top:8px">{"".join(_chip(t, s) for t, s in section.chips)}</div>'
        )
    return f'<tr><td style="padding:18px 28px 4px">{"".join(body)}</td></tr>'


def _render_html(heading: str, byline: str, sections: list[_Section], console_url: str) -> str:
    header = (
        '<tr><td style="background:#0b1220;padding:22px 28px">'
        '<div style="font-size:12px;letter-spacing:.2em;color:#7ee4f5;font-weight:700">'
        "ALGOMATRIC · AI-CIO</div>"
        '<div style="font-size:22px;font-weight:600;color:#ffffff;margin-top:6px">'
        f"{_E(heading)}</div>"
        f'<div style="font-size:13px;color:#94a3b8;margin-top:4px">{_E(byline)}</div>'
        "</td></tr>"
    )
    button = ""
    if _safe_url(console_url):
        href = _E(f"{console_url}/app/market-intelligence", quote=True)
        button = (
            f'<a href="{href}" style="display:inline-block;margin-top:12px;background:#22b8d4;'
            "color:#0b1220;padding:10px 16px;border-radius:8px;font-weight:700;font-size:13px;"
            'text-decoration:none">Open AI-CIO in the console</a>'
        )
    footer = (
        f'<tr><td style="padding:18px 28px 26px">{button}'
        '<p style="margin:16px 0 0;font-size:11px;color:#94a3b8;line-height:1.5">'
        f"{_E(EMAIL_DISCLAIMER)} You receive this because you are the platform owner.</p></td></tr>"
    )
    return (
        '<!doctype html><html><body style="margin:0;background:#f1f5f9;'
        'font-family:Segoe UI,Helvetica,Arial,sans-serif;color:#0f172a">'
        '<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;'
        'padding:24px 0"><tr><td align="center">'
        '<table width="640" cellpadding="0" cellspacing="0" style="max-width:640px;width:100%;'
        'background:#ffffff;border-radius:14px;overflow:hidden;border:1px solid #e2e8f0">'
        + header
        + "".join(_section_html(section) for section in sections)
        + footer
        + "</table></td></tr></table></body></html>"
    )
