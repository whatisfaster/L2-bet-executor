"""Initial schema

Revision ID: 9e197908c5b9
Revises: 
Create Date: 2021-04-30 00:41:39.282129

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '9e197908c5b9'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('bets',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tx', sa.BINARY(length=32), nullable=False),
    sa.Column('sender', sa.BINARY(length=20), nullable=False),
    sa.Column('amount', sa.BINARY(length=32), nullable=False),
    sa.Column('created', sa.DateTime(), nullable=False),
    sa.Column('direction', sa.Integer(), nullable=False),
    sa.Column('outcome', sa.Integer(), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('state',
    sa.Column('name', sa.CHAR(length=10), nullable=False),
    sa.Column('value', sa.CHAR(length=10), nullable=True),
    sa.PrimaryKeyConstraint('name')
    )
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('state')
    op.drop_table('bets')
    # ### end Alembic commands ###
