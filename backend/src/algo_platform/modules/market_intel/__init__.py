"""Market-intelligence context: a read-only, advisory projection of the AI-CIO
pipeline (regime, rankings, news, options, institutional flow).

Hard boundary: everything in this module only *reads* AI-CIO's DuckDB and *informs*
the rest of the platform. Nothing here places an order, mutates a position, or
writes to AI-CIO's store. The strategy gate built on top of it is advisory and,
in this phase, log-only.
"""
