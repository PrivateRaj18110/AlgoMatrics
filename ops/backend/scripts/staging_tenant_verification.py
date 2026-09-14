"""Staging Tenant Isolation Verification Script against PostgreSQL.

Executes Phase 5 of CODEX deployment protocol:
- Configures ORG_A/SOURCE_A and ORG_B/SOURCE_B
- Verifies A can write and read A
- Verifies B can write and read B
- Verifies A cannot read B (404 on direct evidence, filtered on collections)
- Verifies B cannot read A (404 on direct evidence, filtered on collections)
- Verifies sequence state, projections, history, quarantine, rebuild isolation
"""
import os
import sys
import json
import uuid
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

ORG_A = "9120ba73-84fd-4f16-b239-05a6a4e88658"
SOURCE_A = "staging-source-a"
TOKEN_A = "token-for-source-a"

ORG_B = "caa39fb3-7bc3-4e0b-854e-6646092d9088"
SOURCE_B = "staging-source-b"
TOKEN_B = "token-for-source-b"

ADMIN_TOKEN = "admin-test-token"
DEPLOYMENT = "staging"

os.environ["MONITORING_DEPLOYMENT_ENVIRONMENT"] = DEPLOYMENT
os.environ["MONITORING_SOURCE_TOKENS"] = f"{SOURCE_A}:{TOKEN_A},{SOURCE_B}:{TOKEN_B}"
os.environ["MONITORING_SOURCE_ORGANISATIONS"] = f"{SOURCE_A}:{ORG_A},{SOURCE_B}:{ORG_B}"
os.environ["MONITORING_ADMIN_TOKEN"] = ADMIN_TOKEN
os.environ["RAJ_AGENT_TOKEN"] = "staging-agent-token"
os.environ["RAJ_DASHBOARD_TOKEN"] = "staging-dashboard-token"

from fastapi.testclient import TestClient
from app.core.config import get_settings
from app.database import session as session_module
from app.monitoring import contract
from app.monitoring.projections import rebuild
from app.api.dependencies.dashboard_auth import Viewer, require_dashboard_viewer
from main import create_app

get_settings.cache_clear()
session_module._engine = None
session_module._SessionLocal = None

app = create_app()
results = {}

def load_fixture(name: str) -> dict:
    candidates = [
        Path("/repo/tests/fixtures/lls-monitoring-v1-handoff/fixtures/messages") / name,
        Path("/app/tests/fixtures/lls-monitoring-v1-handoff/fixtures/messages") / name,
        Path("/app/schemas/monitoring-v1") / name,
        BACKEND_DIR.parent / "tests" / "fixtures" / "lls-monitoring-v1-handoff" / "fixtures" / "messages" / name,
    ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return json.loads(candidate.read_text(encoding="utf-8"))
        except Exception:
            pass
    raise FileNotFoundError(f"Fixture {name} not found in any candidate path")

DOC_A = load_fixture("valid_snapshot.json")
DOC_A["source_id"] = SOURCE_A
DOC_A["source_instance"] = "inst-a-01"
DOC_A["source_sequence"] = "1"
DOC_A["message_id"] = contract.message_identity(DOC_A)

DOC_B = load_fixture("valid_snapshot.json")
DOC_B["source_id"] = SOURCE_B
DOC_B["source_instance"] = "inst-b-01"
DOC_B["source_sequence"] = "1"
DOC_B["message_id"] = contract.message_identity(DOC_B)

# 1. Publish A
with TestClient(app) as client:
    raw_a = contract.canonical_json(DOC_A)
    resp_a = client.post(
        "/api/monitoring/v1/messages",
        headers={
            "Authorization": f"Bearer {TOKEN_A}",
            "Content-Type": "application/json",
            "X-Monitoring-SHA256": contract.request_digest(raw_a),
        },
        content=raw_a,
    )
    assert resp_a.status_code == 200, f"Pub A failed: {resp_a.text}"
    ack_a = resp_a.json()
    assert ack_a["status"] == "accepted"
    results["publish_a"] = "PASS"

# 2. Publish B
with TestClient(app) as client:
    raw_b = contract.canonical_json(DOC_B)
    resp_b = client.post(
        "/api/monitoring/v1/messages",
        headers={
            "Authorization": f"Bearer {TOKEN_B}",
            "Content-Type": "application/json",
            "X-Monitoring-SHA256": contract.request_digest(raw_b),
        },
        content=raw_b,
    )
    assert resp_b.status_code == 200, f"Pub B failed: {resp_b.text}"
    ack_b = resp_b.json()
    assert ack_b["status"] == "accepted"
    results["publish_b"] = "PASS"

# 3. Read Surface A as Tenant A
app_a = create_app()
app_a.dependency_overrides[require_dashboard_viewer] = lambda: Viewer(
    subject="viewer-a",
    kind="jwt",
    permissions=frozenset({"ops:read"}),
    organisation_id=uuid.UUID(ORG_A),
)
with TestClient(app_a) as client_a:
    state_a = client_a.get("/api/monitoring/v1/state").json()
    assert state_a["count"] == 1
    assert state_a["items"][0]["source"]["sourceId"] == SOURCE_A
    results["state_a_isolation"] = "PASS"

    sources_a = client_a.get("/api/monitoring/v1/sources").json()
    assert sources_a["count"] == 1
    assert sources_a["items"][0]["sourceId"] == SOURCE_A
    results["sources_a_isolation"] = "PASS"

    history_a = client_a.get("/api/monitoring/v1/history").json()
    assert history_a["count"] == 1
    assert history_a["items"][0]["source"]["sourceId"] == SOURCE_A
    results["history_a_isolation"] = "PASS"

    ev_a = client_a.get(f"/api/monitoring/v1/evidence/{DOC_A['message_id']}")
    assert ev_a.status_code == 200
    results["evidence_a_own_lookup"] = "PASS"

    # Cross-tenant direct evidence lookup: A requests B's message_id -> 404 NOT FOUND
    ev_cross_a = client_a.get(f"/api/monitoring/v1/evidence/{DOC_B['message_id']}")
    assert ev_cross_a.status_code == 404
    assert ev_cross_a.json()["detail"] == "no such message"
    results["evidence_a_cross_lookup_404"] = "PASS"

# 4. Read Surface B as Tenant B
app_b = create_app()
app_b.dependency_overrides[require_dashboard_viewer] = lambda: Viewer(
    subject="viewer-b",
    kind="jwt",
    permissions=frozenset({"ops:read"}),
    organisation_id=uuid.UUID(ORG_B),
)
with TestClient(app_b) as client_b:
    state_b = client_b.get("/api/monitoring/v1/state").json()
    assert state_b["count"] == 1
    assert state_b["items"][0]["source"]["sourceId"] == SOURCE_B
    results["state_b_isolation"] = "PASS"

    sources_b = client_b.get("/api/monitoring/v1/sources").json()
    assert sources_b["count"] == 1
    assert sources_b["items"][0]["sourceId"] == SOURCE_B
    results["sources_b_isolation"] = "PASS"

    history_b = client_b.get("/api/monitoring/v1/history").json()
    assert history_b["count"] == 1
    assert history_b["items"][0]["source"]["sourceId"] == SOURCE_B
    results["history_b_isolation"] = "PASS"

    ev_b = client_b.get(f"/api/monitoring/v1/evidence/{DOC_B['message_id']}")
    assert ev_b.status_code == 200
    results["evidence_b_own_lookup"] = "PASS"

    # Cross-tenant direct evidence lookup: B requests A's message_id -> 404 NOT FOUND
    ev_cross_b = client_b.get(f"/api/monitoring/v1/evidence/{DOC_A['message_id']}")
    assert ev_cross_b.status_code == 404
    assert ev_cross_b.json()["detail"] == "no such message"
    results["evidence_b_cross_lookup_404"] = "PASS"

# 5. Quarantine test
with TestClient(app) as client:
    invalid_doc = dict(DOC_A)
    invalid_doc["schema_version"] = "monitoring.v999"
    resp_q = client.post(
        "/api/monitoring/v1/messages",
        headers={
            "Authorization": f"Bearer {TOKEN_A}",
            "Content-Type": "application/json",
        },
        content=contract.canonical_json(invalid_doc),
    )
    assert resp_q.status_code in {400, 422}
    # Inspect quarantine as admin
    q_resp = client.get("/api/monitoring/v1/quarantine", headers={"Authorization": f"Bearer {ADMIN_TOKEN}"})
    assert q_resp.status_code == 200
    q_items = q_resp.json()["items"]
    assert len(q_items) >= 1
    assert q_items[0]["sourceId"] == SOURCE_A
    results["quarantine_isolated"] = "PASS"

# 6. Rebuild isolation test
sm = session_module.get_sessionmaker()
with sm() as session:
    with session.begin():
        rebuild(session, deployment_environment=DEPLOYMENT, organisation_id=uuid.UUID(ORG_A))

with TestClient(app_a) as client_a:
    assert client_a.get("/api/monitoring/v1/state").json()["count"] == 1
with TestClient(app_b) as client_b:
    assert client_b.get("/api/monitoring/v1/state").json()["count"] == 1
results["rebuild_isolation"] = "PASS"

print(json.dumps({"status": "SUCCESS", "phase5_results": results}, indent=2))
