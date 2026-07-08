# ADR 0002: Transactional outbox and at-least-once delivery

Status: Accepted

## Decision

Write aggregate state and an outbox record in one PostgreSQL transaction. A relay
publishes events. Consumers record an inbox key and apply their change atomically.

## Consequences

There is no dual-write gap. Delivery can duplicate, so handlers must be idempotent.
Broker calls still require client order IDs and reconciliation because database and
external venue transactions cannot be atomic.

