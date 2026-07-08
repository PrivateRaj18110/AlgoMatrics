"""Pagination helpers: bounded limit/offset and opaque time cursors."""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Query

from algo_platform.shared.domain.errors import ValidationFailed


@dataclass(frozen=True, slots=True)
class PageParams:
    limit: int
    offset: int


def get_page_params(
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0, le=100_000)] = 0,
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


PageDep = Annotated[PageParams, Depends(get_page_params)]


@dataclass(frozen=True, slots=True)
class TimeCursor:
    """Keyset cursor: strictly-before (occurred_at, id) ordering for descending feeds."""

    before_at: datetime
    before_id: UUID


def encode_cursor(at: datetime, item_id: UUID) -> str:
    raw = json.dumps({"at": at.isoformat(), "id": str(item_id)})
    return base64.urlsafe_b64encode(raw.encode("utf-8")).decode("ascii")


def decode_cursor(cursor: str) -> TimeCursor:
    try:
        raw = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
        return TimeCursor(
            before_at=datetime.fromisoformat(str(raw["at"])),
            before_id=UUID(str(raw["id"])),
        )
    except (KeyError, ValueError, binascii.Error, json.JSONDecodeError) as error:
        raise ValidationFailed("cursor is malformed") from error
