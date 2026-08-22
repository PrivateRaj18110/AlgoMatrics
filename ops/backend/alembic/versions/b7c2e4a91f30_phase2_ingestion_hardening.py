"""phase 2 ingestion hardening: sync_state, sessions, dead letters

Adds the three tables the hardened ingestion path needs:

* ``sync_state``          per (machine, agent) delivery bookkeeping + gap counters
* ``sessions``            durable trading-session records
* ``ingest_dead_letters`` permanently unprocessable envelopes

Purely additive — no existing table, column or index is altered, so the
migration is safe to apply while the previous build is still serving and can be
rolled back without touching telemetry that is already stored.

Revision ID: b7c2e4a91f30
Revises: e1fd66220c23
Create Date: 2026-08-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7c2e4a91f30'
down_revision: Union[str, None] = 'e1fd66220c23'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'sync_state',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('machine_id', sa.String(), nullable=False),
        sa.Column('machine', sa.String(), nullable=False),
        sa.Column('agent_id', sa.String(), nullable=False),
        sa.Column('last_sequence_id', sa.BigInteger(), nullable=True),
        sa.Column('last_event_time', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_batch_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_ack_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('queue_depth', sa.Integer(), nullable=True),
        sa.Column('gap_count', sa.Integer(), nullable=False),
        sa.Column('last_gap_from', sa.BigInteger(), nullable=True),
        sa.Column('last_gap_to', sa.BigInteger(), nullable=True),
        sa.Column('last_gap_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('missing_count', sa.Integer(), nullable=False),
        sa.Column('accepted_count', sa.Integer(), nullable=False),
        sa.Column('duplicate_count', sa.Integer(), nullable=False),
        sa.Column('failed_count', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('machine_id', 'agent_id', name='uq_sync_state_machine_agent'),
    )
    with op.batch_alter_table('sync_state', schema=None) as batch_op:
        batch_op.create_index('ix_sync_state_machine_id', ['machine_id'], unique=False)
        batch_op.create_index('ix_sync_state_last_batch_at', ['last_batch_at'], unique=False)

    op.create_table(
        'sessions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('session_id', sa.String(), nullable=False),
        sa.Column('machine_id', sa.String(), nullable=False),
        sa.Column('machine', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ended_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_event_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('event_count', sa.Integer(), nullable=False),
        sa.Column('trade_count', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('session_id', 'machine_id', name='uq_sessions_session_machine'),
    )
    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.create_index('ix_sessions_machine_id', ['machine_id'], unique=False)
        batch_op.create_index('ix_sessions_last_event_at', ['last_event_at'], unique=False)

    op.create_table(
        'ingest_dead_letters',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('envelope_id', sa.String(), nullable=True),
        sa.Column('kind', sa.String(), nullable=True),
        sa.Column('machine', sa.String(), nullable=True),
        sa.Column('machine_id', sa.String(), nullable=True),
        sa.Column('agent_id', sa.String(), nullable=True),
        sa.Column('strategy', sa.String(), nullable=True),
        sa.Column('sequence_id', sa.Integer(), nullable=True),
        sa.Column('reason', sa.String(), nullable=False),
        sa.Column('error_type', sa.String(), nullable=True),
        sa.Column('payload_preview', sa.Text(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('ingest_dead_letters', schema=None) as batch_op:
        batch_op.create_index('ix_dead_letters_received_at', ['received_at'], unique=False)
        batch_op.create_index('ix_dead_letters_machine_id', ['machine_id'], unique=False)
        batch_op.create_index('ix_dead_letters_envelope_id', ['envelope_id'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('ingest_dead_letters', schema=None) as batch_op:
        batch_op.drop_index('ix_dead_letters_envelope_id')
        batch_op.drop_index('ix_dead_letters_machine_id')
        batch_op.drop_index('ix_dead_letters_received_at')
    op.drop_table('ingest_dead_letters')

    with op.batch_alter_table('sessions', schema=None) as batch_op:
        batch_op.drop_index('ix_sessions_last_event_at')
        batch_op.drop_index('ix_sessions_machine_id')
    op.drop_table('sessions')

    with op.batch_alter_table('sync_state', schema=None) as batch_op:
        batch_op.drop_index('ix_sync_state_last_batch_at')
        batch_op.drop_index('ix_sync_state_machine_id')
    op.drop_table('sync_state')
