# VPS Agent

The agent bridges cloud control services to broker SDKs or terminals that must run near
the venue or on Windows (notably MT5). It registers using a one-time token, receives a
rotatable mTLS identity, heartbeats, holds scoped account leases, deduplicates commands,
and reports acknowledgements and broker events.

It must never accept arbitrary shell commands or strategy source from the control plane.
Signed upgrades, least-privilege service accounts, bounded offline behavior, and local
encrypted command journals are required before production use.

