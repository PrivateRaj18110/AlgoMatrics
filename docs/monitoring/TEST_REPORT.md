# Test report

All figures below are from actual runs on 2026-09-11. Nothing is projected.

---

## 1. Results

| Suite | Command | Result |
|---|---|---|
| ops backend (full) | `ops/backend/.venv/Scripts/python.exe -m pytest -q` | **330 passed, 0 failed** (9m11s) — all 330 collected tests |
| platform backend | `PYTHONPATH=. uv run pytest tests/unit tests/architecture -q` | **440 passed, 2 failed** — both pre-existing, see §4 |
| platform read path | `PYTHONPATH=. uv run pytest tests/unit/test_monitoring_read_path.py -q` | **11 passed** |
| frontend | `npm run test` (frontend/) | **118 passed, 0 failed** (26 files) |
| frontend typecheck | `npx tsc -b` | clean |
| frontend lint | `npm run lint` | clean |
| ops lint (new files) | `ruff check --select F,E501,S608,W` | clean |

### New tests added

| File | Count |
|---|---|
| `ops/backend/tests/test_monitoring_receiver.py` | 61 |
| `ops/backend/tests/test_monitoring_export_contract.py` | 46 |
| `tests/unit/test_monitoring_read_path.py` | 11 |
| `frontend/src/lib/monitoring.test.ts` | 12 |
| `frontend/src/components/monitoring/QualifiedValue.test.tsx` | 20 |
| **Total** | **150** |

## 2. Required matrix — coverage

| Required case | Covered | Test |
|---|---|---|
| valid v1 message | yes | `test_valid_message_is_accepted_and_projected` |
| invalid schema | yes | `test_invalid_envelope_fields_are_quarantined` (4 cases) |
| unknown field | yes | `test_unknown_field_at_current_version_is_quarantined` |
| unsupported major | yes | `test_unsupported_major_is_quarantined_not_rejected` |
| newer minor | yes | `test_newer_minor_is_accepted_with_unknown_fields_ignored` |
| malformed JSON | yes | `test_malformed_json_is_a_400_and_is_preserved` |
| oversized batch | yes | `test_oversized_batch_is_rejected` |
| oversized envelope | yes | `test_oversized_envelope_is_rejected` |
| invalid auth | yes | `test_unauthenticated_upload_is_rejected`, `test_invalid_credential_is_rejected` |
| wrong source scope | yes | `test_credential_cannot_publish_for_another_source` (batch), `test_a_valid_wrapper_cannot_smuggle_a_foreign_envelope` (per envelope) |
| duplicate | yes | `test_duplicate_delivery_creates_one_record` |
| same-ID conflict | yes | `test_same_entity_same_revision_different_content_is_a_conflict` |
| revision | yes | `test_higher_revision_supersedes_without_destroying_evidence` |
| sequence gap | yes | `test_sequence_gap_is_recorded_and_the_message_is_still_stored` |
| out-of-order | yes | `test_late_lower_revision_does_not_move_the_projection`, `test_late_arrival_closes_a_known_gap` |
| UNKNOWN | yes | `test_unknown_survives_ingestion_storage_and_api` |
| STALE | yes | `test_dead_feed_becomes_stale_and_keeps_its_last_value` |
| UNTRUSTED | yes | `test_untrusted_is_not_upgraded_by_successful_delivery` |
| INCOMPLETE | yes | `test_every_knowledge_state_round_trips_through_the_api` |
| SIMULATED | yes | same, plus `test_runtime_is_preserved_for_every_mode` |
| SYNTHETIC_CLOCK | yes | same |
| historical | yes | `test_freshness_is_not_derived_from_receipt_time` |
| quarantine | yes | `test_administrator_can_inspect_quarantine` and the version tests |
| projection rebuild | yes | `test_projections_rebuild_identically_from_evidence` |
| environment isolation | yes | `test_staging_observations_never_appear_in_production_queries` |
| API serialization | yes | `test_api_serialisation_preserves_every_qualified_state` |
| UI state | yes | `QualifiedValue.test.tsx` (all nine states) |
| retry | yes | `test_ack_loss_retry_returns_duplicate` |
| ACK loss | yes | same |
| database unavailable | partial | `test_receiver_refuses_rather_than_accepting_into_nothing` covers *unconfigured*, not *configured-then-failing* |
| replay | partial | covered as duplicate delivery; no bulk historical replay test |
| interrupted / partial upload | **no** | not tested |
| receiver restart | **no** | not tested for monitoring.v1 (the agent path has `test_ingest_durability.py`) |
| database slow / disk full | **no** | not tested |
| network interruption | **no** | not tested |
| privilege escalation | partial | credential separation asserted; no systematic escalation testing |
| injection attempts | **no** | not tested — all SQL is parameterised, but nothing asserts it under hostile input |
| credential exposure | partial | audit rows carry no credential by construction; no test asserts logs are clean |
| load / burst / slow clients / many viewers | **no** | not tested — see `PERFORMANCE_REPORT.md` |
| mobile / responsive | **no** | not tested |

## 3. The dead-feed test, specifically

`test_dead_feed_becomes_stale_and_keeps_its_last_value` publishes two feeds: one with a live horizon, one whose `stale_after` has already elapsed. It asserts:

```
nse-live  ->  FRESH
nse-dead  ->  STALE, messages_per_second == {"state":"KNOWN","value":100}, dataAsOf = the source's time
```

Not `100 LIVE`. Not `0`. Time passing is expressed as a horizon that has already elapsed at read time — the same comparison and the same code path the real clock produces ten minutes after a feed goes quiet.

`test_feed_recovery_shows_no_false_continuity` covers A, outage, then B — asserting the stale reading during the outage, the new value after recovery, and both readings still present in `/history` with their own timestamps.

## 4. Pre-existing failures — classified

### `tests/unit/test_operations_integration.py::test_classification_contract_matches_f9bee1a`

**PRE-EXISTING.** Fails because `NON_TRADE_KINDS` now contains `system_start` and `system_health`, added by the in-flight system-health work in the working tree (`operations/application/service.py` is uncommitted-modified). Nothing in this delivery touches classification.

### `tests/architecture/test_import_rules.py::test_cross_context_imports_use_public_facades`

**PRE-EXISTING.** The violation is `modules/notifications/application/service.py -> modules/operations/infrastructure/telemetry_store`. That file is committed and was not modified here. The new `monitoring_store.py` does not violate the rule.

### `tests/unit/test_operations_api.py` and `test_operations_integration.py` collection error

**ENVIRONMENTAL.** `ModuleNotFoundError: No module named 'tests'` — `tests/` has no `__init__.py` and there is no root `conftest.py`, so the repo root is not on `sys.path`. Running with `PYTHONPATH=.` collects and runs them. Unrelated to this work; the fix is `pythonpath = ["."]` under `[tool.pytest.ini_options]`.

## 5. Fixed during this work — the four never-executed tests

Reported previously as "4 failed, pre-existing" in `tests/test_system_health.py`. Verified independently and fixed rather than ignored.

**Cause:** the tests use `@pytest.mark.asyncio`. The monorepo root declares `pytest-asyncio>=0.25` and `asyncio_mode = "auto"`, but `ops/backend/pytest.ini` deliberately anchors rootdir to the ops backend so that config never applied. The plugin was never declared for this suite, so the four async tests could not run **at all** — they failed on infrastructure, not on assertions.

**Determination:** `pytest-asyncio` is genuinely an intended test dependency of this monorepo, and these tests were written expecting it. This is an ordinary test-environment correction, not a change to production behaviour.

**Fix:** `pytest-asyncio>=0.25,<2.0` added to `ops/backend/requirements-dev.txt`; `asyncio_mode = auto` declared explicitly in `ops/backend/pytest.ini`, preserving the deliberate rootdir anchoring.

**Before:**

```
tests/test_system_health.py: 4 failed, 5 passed
  async def functions are not natively supported.
```

**After:**

```
tests/test_system_health.py: 9 passed
```

All four pass their real assertions. No production code was changed to achieve this, and no assertion was weakened.

## 6. One regression found and fixed

`tests/test_release_hotfix.py::test_websocket_notifications_and_api_contract_are_unchanged` pins the exact OpenAPI path set and failed when the nine `/api/v1/monitoring/*` routes appeared — the test doing exactly its job.

Fixed by **adding** the new paths to `expected_paths` with a comment explaining why. The assertion is still exact equality: it still fails if an existing route disappears or an unreviewed route appears. No assertion was weakened and no test was deleted.

## 7. Status

| | |
|---|---|
| **TESTED** | the §2 matrix rows marked yes — 150 new tests |
| **PARTIAL** | database-failure, replay, privilege-escalation, credential-exposure |
| **NOT TESTED** | restart, interrupted upload, disk full, slow database, network interruption, injection, load, responsive layout |
| **PRE-EXISTING** | 2 platform failures plus 1 collection error, classified in §4 |
| **FIXED** | 4 never-executed ops tests (§5), 1 regression introduced and corrected (§6) |
