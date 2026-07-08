from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from algo_platform.shared.infrastructure.database import Base, TimestampMixin


class FeatureFlagModel(Base, TimestampMixin):
    """A runtime-configurable feature flag. The key is its natural identity."""

    __tablename__ = "feature_flags"

    key: Mapped[str] = mapped_column(String(80), primary_key=True)
    description: Mapped[str] = mapped_column(String(255), default="")
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Emergency off that overrides every scope and rollout.
    kill_switch: Mapped[bool] = mapped_column(Boolean, default=False)
    # 0..100; 100 means fully on when enabled.
    rollout_percentage: Mapped[int] = mapped_column(Integer, default=100)


class FeatureFlagOverrideModel(Base, TimestampMixin):
    """A scoped on/off decision for a flag (environment, tenant, or user)."""

    __tablename__ = "feature_flag_overrides"
    __table_args__ = (
        UniqueConstraint(
            "flag_key", "scope_type", "scope_id", name="uq_feature_flag_overrides_scope"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    flag_key: Mapped[str] = mapped_column(
        ForeignKey("feature_flags.key", ondelete="CASCADE"), index=True
    )
    scope_type: Mapped[str] = mapped_column(String(20))
    scope_id: Mapped[str] = mapped_column(String(64))
    enabled: Mapped[bool] = mapped_column(Boolean)
