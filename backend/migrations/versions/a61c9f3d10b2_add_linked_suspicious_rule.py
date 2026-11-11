"""Add linked-suspicious risk rule.

Revision ID: a61c9f3d10b2
Revises: 0055723a91d0
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

from app.database.types import UTCDateTime

revision = "a61c9f3d10b2"
down_revision = "0055723a91d0"
branch_labels = None
depends_on = None


def _create_sqlite_risk_rule_triggers() -> None:
    if op.get_bind().dialect.name != "sqlite":
        return
    op.execute(
        'CREATE TRIGGER prevent_risk_rule_id_update BEFORE UPDATE OF "rule_id" ON "risk_rule" '
        'WHEN OLD."rule_id" IS NOT NEW."rule_id" '
        "BEGIN SELECT RAISE(ABORT, 'record identifiers are immutable'); END"
    )
    op.execute(
        "CREATE TRIGGER prevent_active_risk_rule_update "
        "BEFORE UPDATE OF rule_key, version, name, description, parameters_json, "
        "default_score_contribution_bps, effective_at, created_at ON risk_rule "
        "WHEN OLD.status = 'active' OR EXISTS "
        "(SELECT 1 FROM alert WHERE alert.rule_id = OLD.rule_id) "
        "BEGIN SELECT RAISE(ABORT, 'active or referenced risk-rule versions are immutable'); END"
    )


def upgrade() -> None:
    with op.batch_alter_table("risk_rule", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_risk_rule_key", type_="check")
        batch_op.create_check_constraint(
            "ck_risk_rule_key",
            "rule_key IN ('velocity_spike','high_value','new_device','dormant_reactivation',"
            "'circular_transfer','linked_suspicious')",
        )

    risk_rule = sa.table(
        "risk_rule",
        sa.column("rule_id", sa.String(64)),
        sa.column("rule_key", sa.String(48)),
        sa.column("version", sa.Integer()),
        sa.column("name", sa.String(120)),
        sa.column("description", sa.Text()),
        sa.column("status", sa.String(16)),
        sa.column("parameters_json", sa.JSON()),
        sa.column("default_score_contribution_bps", sa.Integer()),
        sa.column("effective_at", UTCDateTime()),
        sa.column("retired_at", UTCDateTime()),
        sa.column("created_at", UTCDateTime()),
    )
    effective_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    op.bulk_insert(
        risk_rule,
        [
            {
                "rule_id": "RUL-linked_suspicious-V01",
                "rule_key": "linked_suspicious",
                "version": 1,
                "name": "Linked suspicious transactions",
                "description": "Correlates a transaction with an independently alerted transaction through supported account links.",
                "status": "active",
                "parameters_json": {"minimum_related_alerts": 1, "lookback_days": 30},
                "default_score_contribution_bps": 3000,
                "effective_at": effective_at,
                "retired_at": None,
                "created_at": effective_at,
            }
        ],
    )
    _create_sqlite_risk_rule_triggers()


def downgrade() -> None:
    connection = op.get_bind()
    references = connection.execute(
        sa.text("SELECT COUNT(*) FROM alert WHERE rule_id = :rule_id"),
        {"rule_id": "RUL-linked_suspicious-V01"},
    ).scalar_one()
    if references:
        raise RuntimeError("Cannot remove linked_suspicious while alerts reference its rule.")
    op.execute(
        sa.text("DELETE FROM risk_rule WHERE rule_id = :rule_id"),
        {"rule_id": "RUL-linked_suspicious-V01"},
    )
    with op.batch_alter_table("risk_rule", recreate="always") as batch_op:
        batch_op.drop_constraint("ck_risk_rule_key", type_="check")
        batch_op.create_check_constraint(
            "ck_risk_rule_key",
            "rule_key IN ('velocity_spike','high_value','new_device','dormant_reactivation','circular_transfer')",
        )
    _create_sqlite_risk_rule_triggers()
