# ADR 0001: Modular control plane with specialized runtimes

Status: Accepted

## Context

The platform must begin economically but support high-volume feeds, broker-local agents,
multiple tenants, and independently scaling execution.

## Decision

Use a modular monolith for transactional control-plane bounded contexts. Run API,
trading engine, market data, scheduler, and asynchronous workers as distinct processes.
Communicate across durability boundaries through versioned events and ports.

## Consequences

Early development keeps simple transactions and one migration history. Latency-sensitive
and failure-sensitive runtimes scale independently. Context/import tests and public
facades are mandatory to prevent the monolith becoming a ball of mud. Extract a context
only when team ownership, load, deployment cadence, or fault isolation provides evidence.

