"""Repository pattern foundation.

Repositories isolate data access behind a stable interface. Today they are
backed by in-memory fixtures (``mock_data``); swapping to Supabase Postgres
means re-implementing these classes against SQLAlchemy without touching the
service or router layers above them.
"""

from __future__ import annotations

from typing import Generic, Iterable, TypeVar

T = TypeVar("T")


class InMemoryRepository(Generic[T]):
    """A read repository over a fixed list of records.

    Subclasses (or callers) provide the backing rows and the key used by
    :meth:`get`. The collection is copied defensively so callers cannot mutate
    the shared fixtures.
    """

    def __init__(self, rows: Iterable[T], id_key: str = "id") -> None:
        self._rows: list[T] = list(rows)
        self._id_key = id_key

    def list(self) -> list[T]:
        """Return all records."""
        return list(self._rows)

    def get(self, record_id: str) -> T | None:
        """Return a single record by its id, or ``None``."""
        for row in self._rows:
            if isinstance(row, dict) and row.get(self._id_key) == record_id:
                return row
        return None
