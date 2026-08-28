"""add unique constraint on readings mi record_date

Revision ID: c9c9670878f9
Revises: 0ff3aa912e51
Create Date: 2026-08-27 15:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c9c9670878f9'
down_revision: Union[str, Sequence[str], None] = '0ff3aa912e51'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        'uq_readings_mi_record_date', 'readings', ['mi', 'record_date']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_readings_mi_record_date', 'readings', type_='unique')
