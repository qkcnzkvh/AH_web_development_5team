"""ai_analysis_results: heatmap_url NULL 허용, (record_id, ai_model) UNIQUE 추가

Revision ID: a1b2c3d4e5f6
Revises: c75d234c47b0
Create Date: 2026-10-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'c75d234c47b0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Heatmap은 선택사항이므로 NULL 허용
    op.alter_column(
        'ai_analysis_results',
        'heatmap_url',
        existing_type=sa.String(length=255),
        nullable=True,
    )
    # 같은 진료기록·같은 모델의 결과는 1건만 저장
    op.create_unique_constraint(
        'uq_ai_results_record_model',
        'ai_analysis_results',
        ['record_id', 'ai_model'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_ai_results_record_model', 'ai_analysis_results', type_='unique')
    op.alter_column(
        'ai_analysis_results',
        'heatmap_url',
        existing_type=sa.String(length=255),
        nullable=False,
    )
