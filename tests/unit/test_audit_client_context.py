"""Audit client context: IP, browser and location on every entry.

The load-bearing property is backward compatibility of the hash chain: entries
written before the client fact existed must hash exactly as they did then.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from algo_platform.modules.audit.application import service as audit_service
from algo_platform.modules.audit.application.hashing import (
    GENESIS_HASH,
    AuditFacts,
    ChainedEntry,
    compute_entry_hash,
    verify_chain,
)
from algo_platform.shared.infrastructure.client_context import (
    ClientInfo,
    current_client,
    set_client,
)
from algo_platform.shared.infrastructure.geoip import GeoIpResolver, GeoLocation

ACTOR = UUID("11111111-1111-1111-1111-111111111111")


def _facts(**over: object) -> AuditFacts:
    base = AuditFacts(
        sequence=1,
        occurred_at=datetime(2026, 9, 1, 9, 15, tzinfo=UTC),
        action="auth.login",
        resource_type="user",
        resource_id=str(ACTOR),
        actor_type="user",
        actor_user_id=ACTOR,
        organization_id=None,
        request_id="req",
        correlation_id="corr",
        session_id=None,
        ip_hash="abc",
        before_state=None,
        after_state={"mfa": True},
    )
    return replace(base, **over)  # type: ignore[arg-type]


def _legacy_hash(prev: str, facts: AuditFacts) -> str:
    """The canonical form exactly as it was before the client fact existed."""
    payload = {
        "sequence": facts.sequence,
        "occurred_at": facts.occurred_at.isoformat(),
        "action": facts.action,
        "resource_type": facts.resource_type,
        "resource_id": facts.resource_id,
        "actor_type": facts.actor_type,
        "actor_user_id": str(facts.actor_user_id) if facts.actor_user_id else None,
        "organization_id": None,
        "request_id": facts.request_id,
        "correlation_id": facts.correlation_id,
        "session_id": facts.session_id,
        "ip_hash": facts.ip_hash,
        "before_state": facts.before_state,
        "after_state": facts.after_state,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(f"{prev}\n{canonical}".encode()).hexdigest()


def test_entries_without_client_hash_exactly_as_before() -> None:
    facts = _facts()
    assert compute_entry_hash(GENESIS_HASH, facts) == _legacy_hash(GENESIS_HASH, facts)


def test_client_fact_is_covered_by_the_hash() -> None:
    client = {"ip_address": "49.36.10.5", "user_agent": "Firefox", "geo": {"city": "Pune"}}
    signed = compute_entry_hash(GENESIS_HASH, _facts(client=client))
    assert signed != compute_entry_hash(GENESIS_HASH, _facts())

    tampered = _facts(client={**client, "ip_address": "1.2.3.4"})
    chain = [ChainedEntry(facts=tampered, prev_hash=GENESIS_HASH, entry_hash=signed)]
    assert verify_chain(chain) == 1


def test_mixed_old_and_new_entries_verify() -> None:
    old = _facts()
    old_hash = compute_entry_hash(GENESIS_HASH, old)
    new = _facts(sequence=2, client={"ip_address": "49.36.10.5", "user_agent": None, "geo": None})
    new_hash = compute_entry_hash(old_hash, new)
    chain = [
        ChainedEntry(facts=old, prev_hash=GENESIS_HASH, entry_hash=old_hash),
        ChainedEntry(facts=new, prev_hash=old_hash, entry_hash=new_hash),
    ]
    assert verify_chain(chain) is None


# -- client context ---------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_client() -> None:
    set_client(None)


def test_request_client_fills_entries_automatically() -> None:
    set_client(ClientInfo(ip_address="127.0.0.1", user_agent="curl/8"))
    ip, agent, geo, client = audit_service._client_facts(None, None)
    assert (ip, agent) == ("127.0.0.1", "curl/8")
    assert geo == {"country": "Private network", "country_code": None, "region": None, "city": None}
    assert client == {"ip_address": ip, "user_agent": agent, "geo": geo}


def test_explicit_values_win_over_the_request() -> None:
    set_client(ClientInfo(ip_address="127.0.0.1", user_agent="curl/8"))
    ip, agent, _, _ = audit_service._client_facts("10.0.0.9", "Agent/1")
    assert (ip, agent) == ("10.0.0.9", "Agent/1")


def test_outside_a_request_nothing_is_recorded() -> None:
    assert current_client() is None
    assert audit_service._client_facts(None, None) == (None, None, None, None)


# -- geoip --------------------------------------------------------------------------


def test_resolver_without_database_is_inert() -> None:
    resolver = GeoIpResolver(None)
    assert not resolver.available
    assert resolver.lookup("49.36.10.5") is None
    assert resolver.lookup("not-an-ip") is None
    assert resolver.lookup(None) is None


def test_missing_database_file_does_not_raise() -> None:
    assert not GeoIpResolver("Z:/definitely/missing.mmdb").available


@pytest.mark.parametrize("ip", ["10.1.2.3", "192.168.1.20", "127.0.0.1", "::1", "172.18.0.4"])
def test_private_addresses_are_labelled_without_a_lookup(ip: str) -> None:
    location = GeoIpResolver(None).lookup(ip)
    assert location == GeoLocation(
        country="Private network", country_code=None, region=None, city=None
    )


def test_database_record_is_mapped_to_english_names() -> None:
    class FakeReader:
        def get(self, ip: str) -> dict[str, object]:
            return {
                "city": {"names": {"en": "Mumbai"}},
                "country": {"iso_code": "IN", "names": {"en": "India"}},
                "subdivisions": [{"names": {"en": "Maharashtra"}}],
            }

    resolver = GeoIpResolver(None)
    resolver._reader = FakeReader()
    assert resolver.lookup("49.36.10.5") == GeoLocation(
        country="India", country_code="IN", region="Maharashtra", city="Mumbai"
    )
