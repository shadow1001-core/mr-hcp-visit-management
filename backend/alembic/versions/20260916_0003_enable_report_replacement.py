"""Enable complete report replacement and optional notes.

Revision ID: 20260916_0003
Revises: 20260916_0002
Create Date: 2026-09-16
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260916_0003"
down_revision: str | None = "20260916_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visit_reports", sa.Column("notes", sa.Text(), nullable=True))
    op.drop_constraint(
        op.f("ck_material_distributions_quantity_positive"),
        "material_distributions",
        type_="check",
    )
    op.create_check_constraint(
        op.f("ck_material_distributions_quantity_nonnegative"),
        "material_distributions",
        "quantity >= 0",
    )


def downgrade() -> None:
    op.drop_constraint(
        op.f("ck_material_distributions_quantity_nonnegative"),
        "material_distributions",
        type_="check",
    )
    # The previous schema cannot represent an explicit zero quantity. Preserve
    # the material row and coerce that boundary value to its former minimum.
    op.execute(sa.text("UPDATE material_distributions SET quantity = 1 WHERE quantity = 0"))
    op.create_check_constraint(
        op.f("ck_material_distributions_quantity_positive"),
        "material_distributions",
        "quantity > 0",
    )
    op.drop_column("visit_reports", "notes")
