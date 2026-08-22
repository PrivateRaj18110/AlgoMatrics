"""Exception hierarchy for the Raj Monitor platform.

All errors derive from :class:`RajMonitorError` so callers can catch the whole
family with one ``except``. The golden rule of this package — *monitoring must
never crash trading* — means these are almost always caught and logged
internally; they are public so the agent and tests can reason about failures.
"""

from __future__ import annotations


class RajMonitorError(Exception):
    """Base class for every error raised inside raj_monitor."""


class ConfigError(RajMonitorError):
    """Raised when configuration is missing or invalid."""


class TransportError(RajMonitorError):
    """Raised when a network round-trip to a peer fails."""


class CircuitOpenError(TransportError):
    """Raised when the circuit breaker is open and refusing requests."""


class QueueError(RajMonitorError):
    """Raised when the persistent queue cannot store or retrieve items."""


class QueueFullError(QueueError):
    """Raised (or signalled) when the queue is at capacity."""


class SecurityError(RajMonitorError):
    """Raised on an authentication / token failure."""


class AgentUnavailableError(RajMonitorError):
    """Raised by the SDK when the Local Agent cannot be reached."""
