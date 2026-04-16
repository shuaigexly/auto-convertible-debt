"""add unique constraint on accounts.name

Revision ID: 002
Revises: 001
Create Date: 2025-04-17
"""
from alembic import op

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_accounts_name", "accounts", ["name"])


def downgrade():
    op.drop_constraint("uq_accounts_name", "accounts", type_="unique")
