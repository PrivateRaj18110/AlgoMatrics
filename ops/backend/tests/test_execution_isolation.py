"""Structural guarantee: ingestion can never reach execution.

Google is the only execution authority. AWS ingests telemetry and must have no
code path — not even an unused import — to broker login, order placement,
strategy execution, signal routing or risk control.

This is not a style check. It is the one architectural invariant with no
acceptable trade-off, and the risk is drift: nothing is wrong today, but a future
change that imports a broker client into the ingest path would be invisible in
review. This test fails loudly the moment that happens.

Two independent checks, because either alone can be fooled:

1. **Static** — walk the import graph reachable from the ingestion entry points
   and assert no module resolves to a forbidden name. Catches an import that is
   present but never executed.
2. **Runtime** — import the whole app and inspect ``sys.modules``. Catches a
   dynamic/deferred import that static analysis would miss.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1] / "app"
BACKEND_DIR = APP_DIR.parent

# Entry points of the telemetry write path.
INGEST_ENTRY_POINTS = (
    APP_DIR / "api" / "routers" / "agent.py",
    APP_DIR / "api" / "routers" / "ingest.py",
    APP_DIR / "services" / "agent_service.py",
    APP_DIR / "services" / "ingest_service.py",
)

PRELIVE_OBSERVATIONAL_ENTRY_POINTS = (
    APP_DIR / "api" / "routers" / "eod.py",
    APP_DIR / "api" / "routers" / "quant.py",
    APP_DIR / "api" / "routers" / "recovery.py",
    APP_DIR / "api" / "routers" / "sessions.py",
    APP_DIR / "services" / "eod_service.py",
    APP_DIR / "services" / "quant_service.py",
    APP_DIR / "services" / "recovery_service.py",
    APP_DIR / "services" / "session_service.py",
    BACKEND_DIR / "scripts" / "run_phase3_simulation.py",
    BACKEND_DIR / "scripts" / "measure_phase3_performance.py",
)

# Module names that would represent an execution *capability* — something able to
# authenticate to a venue or move an order. Matched against the full dotted path.
#
# Note on scope: the ops app legitimately *displays* broker status
# (`app/api/routers/brokers.py`, `app/schemas/broker.py`). Reading and rendering
# a broker's connection state is not an execution capability, so first-party
# `app.*` modules are exempt from the runtime scan — and
# `test_ops_broker_surface_is_read_only` below keeps that exemption honest by
# asserting the ops broker surface never gains a write route.
FORBIDDEN_MODULE_PATTERNS = (
    r"(^|\.)algo_platform\.modules\.trading(\.|$)",
    r"(^|\.)algo_platform\.modules\.brokerage(\.|$)",
    r"(^|\.)algo_platform\.modules\.risk(\.|$)",
    r"(^|\.)raj_monitor(\.|$)",          # the agent SDK belongs on Google, not here
    r"(^|\.)broker_client(\.|$)",
    r"(^|\.)broker_adapter(\.|$)",
    r"(^|\.)execution(\.|$)",
    r"(^|\.)execution_engine(\.|$)",
    r"(^|\.)order_execution(\.|$)",
    r"(^|\.)signal_router(\.|$)",
    r"(^|\.)safety_controller(\.|$)",
    r"(^|\.)strategy_engine(\.|$)",
    r"(^|\.)multi_strategy_engine(\.|$)",
    r"(^|\.)flattrade\w*(\.|$)",
    r"(^|\.)norenapi(\.|$)",
    r"(^|\.)ccxt(\.|$)",
    r"(^|\.)MetaTrader5(\.|$)",
    r"(^|\.)ib_insync(\.|$)",
    r"(^|\.)alpaca\w*(\.|$)",
)

# First-party modules of this service. Exempt from the *runtime* scan only; the
# static reachability check still applies to them in full.
FIRST_PARTY_PREFIXES = ("app.", "main")

# Call names that would place an order even without an obvious import.
FORBIDDEN_CALL_NAMES = frozenset({
    "place_order", "submit_order", "send_order", "cancel_order", "modify_order",
    "buy", "sell", "close_position", "square_off", "broker_login",
})

_FORBIDDEN = tuple(re.compile(p) for p in FORBIDDEN_MODULE_PATTERNS)


def _is_forbidden(module: str) -> bool:
    return any(pattern.search(module) for pattern in _FORBIDDEN)


def _module_to_path(module: str) -> Path | None:
    """Resolve a first-party ``app.*`` module to a file inside this backend."""
    if not module.startswith("app."):
        return None
    relative = Path(*module.split(".")[1:])
    for candidate in (APP_DIR / relative.with_suffix(".py"), APP_DIR / relative / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _imports_of(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _reachable_imports(entry_points: tuple[Path, ...] = INGEST_ENTRY_POINTS) -> dict[str, Path]:
    """Transitive closure of imports from the ingestion entry points."""
    seen: set[Path] = set()
    queue = [p for p in entry_points if p.is_file()]
    assert queue, "no ingestion entry points found — test would vacuously pass"
    collected: dict[str, Path] = {}

    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        for module in _imports_of(current):
            collected.setdefault(module, current)
            nested = _module_to_path(module)
            if nested is not None and nested not in seen:
                queue.append(nested)
    return collected


def _forbidden_calls(entry_points: tuple[Path, ...]) -> dict[str, str]:
    offenders: dict[str, str] = {}
    for path in set(_reachable_imports(entry_points).values()) | set(entry_points):
        if not path.is_file():
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = (
                func.attr if isinstance(func, ast.Attribute)
                else func.id if isinstance(func, ast.Name)
                else None
            )
            if name in FORBIDDEN_CALL_NAMES:
                offenders[name] = str(path.relative_to(BACKEND_DIR))
    return offenders


def test_ingestion_imports_nothing_execution_related() -> None:
    """Static: no forbidden module is reachable from the ingest path."""
    offenders = {
        module: str(source.relative_to(APP_DIR.parent))
        for module, source in _reachable_imports().items()
        if _is_forbidden(module)
    }
    assert not offenders, (
        "AWS ingestion must never import an execution capability. "
        f"Forbidden imports found: {offenders}"
    )


def test_ingestion_calls_no_order_primitives() -> None:
    """Static: no order-placing call name appears in the ingest path."""
    offenders = _forbidden_calls(INGEST_ENTRY_POINTS)
    assert not offenders, f"order-placing call found in the ingest path: {offenders}"


def test_prelive_observational_surfaces_import_nothing_execution_related() -> None:
    """EOD, quant, recovery, sessions and local replay remain read/data only."""
    offenders = {
        module: str(source.relative_to(BACKEND_DIR))
        for module, source in _reachable_imports(PRELIVE_OBSERVATIONAL_ENTRY_POINTS).items()
        if _is_forbidden(module)
    }
    assert not offenders, (
        "AWS pre-live surfaces must never import an execution capability. "
        f"Forbidden imports found: {offenders}"
    )


def test_prelive_observational_surfaces_call_no_order_primitives() -> None:
    """Replay/analytics/data surfaces must not invoke trading primitives."""
    offenders = _forbidden_calls(PRELIVE_OBSERVATIONAL_ENTRY_POINTS)
    assert not offenders, (
        f"order-placing call found in pre-live observational surfaces: {offenders}"
    )


def test_loaded_application_has_no_execution_module() -> None:
    """Runtime: importing the app loads no execution module (catches lazy imports)."""
    import main  # noqa: F401  (importing populates sys.modules)

    offenders = sorted(
        m for m in list(sys.modules)
        if _is_forbidden(m) and not m.startswith(FIRST_PARTY_PREFIXES)
    )
    assert not offenders, (
        f"execution-capable modules were loaded into the ops API process: {offenders}"
    )


def test_ops_broker_surface_is_read_only() -> None:
    """The broker display surface must never gain a write route.

    This is the honesty check behind exempting first-party modules from the
    runtime scan: displaying broker status is fine, but the moment the ops API
    grows a POST/PUT/PATCH/DELETE on a broker route it is no longer purely a
    monitoring surface and the exemption would be hiding it.
    """
    import main

    offenders = [
        (path, method)
        for path, operations in main.app.openapi()["paths"].items()
        if "/broker" in path
        for method in operations
        if method.lower() not in {"get", "head", "options"}
    ]
    assert not offenders, f"ops broker surface gained a write route: {offenders}"


def test_dashboard_trading_surfaces_are_get_only() -> None:
    """Dashboard routes may display trading state but must not control it."""
    import main

    display_prefixes = (
        "/api/accounts",
        "/api/analytics",
        "/api/brokers",
        "/api/dashboard",
        "/api/execution",
        "/api/risk",
        "/api/strategies",
        "/api/trades",
    )
    offenders = [
        (path, method)
        for path, operations in main.app.openapi()["paths"].items()
        if path.startswith(display_prefixes)
        for method in operations
        if method.lower() not in {"get", "head", "options"}
    ]
    assert not offenders, f"dashboard trading display surface gained a write route: {offenders}"


def test_no_agent_route_reaches_a_write_beyond_telemetry() -> None:
    """The ingest path may only touch telemetry repositories.

    Guards against a future handler writing through some other repository (say,
    a strategy or account store) that could feed back into trading decisions.
    """
    allowed = {
        "machines_repo", "events_repo", "logs_repo", "trades_repo", "metrics_repo",
        "sync_state_repo", "sessions_repo", "dead_letter_repo",
        "reserve_envelope", "unit_of_work", "prune_dedup",
    }
    source = (APP_DIR / "services" / "agent_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "app.repositories":
            imported.update(alias.name for alias in node.names)
    unexpected = imported - allowed
    assert not unexpected, (
        f"agent_service imported non-telemetry repositories: {unexpected}"
    )


def test_forbidden_matcher_actually_matches() -> None:
    """Guard the guard: a matcher that matches nothing would pass everything."""
    assert _is_forbidden("algo_platform.modules.trading.application")
    assert _is_forbidden("raj_monitor.agent")
    assert _is_forbidden("execution.flattrade_option_service")
    assert _is_forbidden("ccxt")
    assert not _is_forbidden("app.services.agent_service")
    assert not _is_forbidden("sqlalchemy.orm")
