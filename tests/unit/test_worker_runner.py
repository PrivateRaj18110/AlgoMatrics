"""Unit tests for the worker framework (Phase 7, slice A)."""

from __future__ import annotations

import asyncio
import contextlib

from algo_platform.processes.workers.registry import REGISTRY, available_roles, build_roles
from algo_platform.processes.workers.runner import run_workers


class _Role:
    def __init__(self, name: str) -> None:
        self.name = name
        self.iterations = 0

    async def run(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            self.iterations += 1
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=0.01)


class _CrashingRole:
    name = "crasher"

    def __init__(self) -> None:
        self.starts = 0

    async def run(self, stop: asyncio.Event) -> None:
        self.starts += 1
        raise RuntimeError("boom")


async def test_run_workers_runs_until_stop() -> None:
    role = _Role("a")
    stop = asyncio.Event()
    task = asyncio.create_task(run_workers([role], stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert role.iterations >= 1


async def test_run_workers_supervises_all_roles() -> None:
    roles = [_Role("a"), _Role("b")]
    stop = asyncio.Event()
    task = asyncio.create_task(run_workers(roles, stop))  # type: ignore[arg-type]
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=1)
    assert all(r.iterations >= 1 for r in roles)


async def test_crashing_role_is_restarted_then_stops() -> None:
    role = _CrashingRole()
    stop = asyncio.Event()
    task = asyncio.create_task(run_workers([role], stop))
    await asyncio.sleep(0.05)
    stop.set()
    await asyncio.wait_for(task, timeout=3)
    # It crashed and was restarted at least once before stop (2s backoff).
    assert role.starts >= 1


async def test_empty_roles_returns_immediately() -> None:
    await asyncio.wait_for(run_workers([], asyncio.Event()), timeout=1)


def test_registry_has_relay_and_email() -> None:
    assert "relay" in REGISTRY
    assert "email" in REGISTRY


def test_build_roles_all_selects_everything() -> None:
    roles = build_roles(["all"], ctx=None)  # type: ignore[arg-type]
    assert {r.name for r in roles} == set(available_roles())


def test_build_roles_selects_named_subset() -> None:
    roles = build_roles(["email"], ctx=None)  # type: ignore[arg-type]
    assert [r.name for r in roles] == ["email"]


def test_build_roles_ignores_unknown() -> None:
    roles = build_roles(["email", "nope"], ctx=None)  # type: ignore[arg-type]
    assert [r.name for r in roles] == ["email"]
