"""empty message

Revision ID: e2813654671e
Revises: e9913fa83209
Create Date: 2023-12-28 18:06:52.422615

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e2813654671e'
down_revision = 'e9913fa83209'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('personal_anime_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('list_name', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['anime.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('personal_books_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('list_name', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['books.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('personal_games_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('list_name', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['games.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('personal_series_list',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('media_id', sa.Integer(), nullable=False),
    sa.Column('list_name', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['media_id'], ['series.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['user.id'], ),
    sa.PrimaryKeyConstraint('id')
    )


def downgrade():
    op.drop_table('personal_series_list')
    op.drop_table('personal_games_list')
    op.drop_table('personal_books_list')
    op.drop_table('personal_anime_list')
