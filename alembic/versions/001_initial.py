"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-04-16
"""
from alembic import op
import sqlalchemy as sa

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "accounts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("broker", sa.String(50), nullable=False),
        sa.Column("credentials_enc", sa.Text, nullable=False),
        sa.Column("enabled", sa.Boolean, server_default=sa.true()),
        sa.Column("circuit_broken", sa.Boolean, server_default=sa.false()),
        sa.Column("consecutive_failures", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "bond_snapshots",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("bond_code", sa.String(10), nullable=False),
        sa.Column("bond_name", sa.String(100)),
        sa.Column("market", sa.String(5)),
        sa.Column("source", sa.String(50)),
        sa.Column("confirmed", sa.Boolean, server_default=sa.false()),
        sa.UniqueConstraint("trade_date", "bond_code", "source"),
    )
    op.create_index("ix_bond_snapshots_trade_date", "bond_snapshots", ["trade_date"])
    op.create_table(
        "subscriptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("trade_date", sa.Date, nullable=False),
        sa.Column("bond_code", sa.String(10), nullable=False),
        sa.Column("bond_name", sa.String(100)),
        sa.Column("account_id", sa.Integer, sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "NEW", "SUBMITTING", "SUBMITTED", "UNKNOWN", "RECONCILED", "FAILED", "SKIPPED",
                name="subscriptionstatus",
            ),
            nullable=False,
            server_default="NEW",
        ),
        sa.Column("error", sa.Text),
        sa.Column("retry_count", sa.Integer, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("trade_date", "account_id", "bond_code"),
    )
    op.create_index("ix_subscriptions_trade_date", "subscriptions", ["trade_date"])
    op.create_table(
        "config",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("value", sa.Text, nullable=False),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
        sa.Column("operator", sa.String(100), default="system"),
        sa.Column("action", sa.String(200), nullable=False),
        sa.Column("detail", sa.Text),
    )
    op.create_table(
        "app_logs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
        sa.Column("level", sa.String(10)),
        sa.Column("message", sa.Text),
    )
    op.create_index("ix_app_logs_timestamp", "app_logs", ["timestamp"])


def downgrade():
    for t in ["app_logs", "audit_logs", "config", "subscriptions", "bond_snapshots", "accounts"]:
        op.drop_table(t)
    op.execute("DROP TYPE IF EXISTS subscriptionstatus")
