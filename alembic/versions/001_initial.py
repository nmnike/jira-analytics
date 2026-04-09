"""Initial migration - create all tables

Revision ID: 001_initial
Revises: 
Create Date: 2026-04-09

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_initial'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Employees table
    op.create_table(
        'employees',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_account_id', sa.String(128), unique=True, nullable=False, index=True),
        sa.Column('display_name', sa.String(255), nullable=False),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('is_active', sa.Boolean(), default=True),
        sa.Column('avatar_url', sa.String(512), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Projects table
    op.create_table(
        'projects',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_project_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('key', sa.String(32), unique=True, nullable=False, index=True),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.String(2000), nullable=True),
        sa.Column('project_type', sa.String(64), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Issues table
    op.create_table(
        'issues',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_issue_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('key', sa.String(32), unique=True, nullable=False, index=True),
        sa.Column('summary', sa.String(500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('issue_type', sa.String(64), nullable=False),
        sa.Column('status', sa.String(64), nullable=False),
        sa.Column('priority', sa.String(64), nullable=True),
        sa.Column('parent_id', sa.String(36), sa.ForeignKey('issues.id'), nullable=True, index=True),
        sa.Column('project_id', sa.String(36), sa.ForeignKey('projects.id'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Worklogs table (core fact table)
    op.create_table(
        'worklogs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('jira_worklog_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('started_at', sa.DateTime(), nullable=False, index=True),
        sa.Column('hours', sa.Float(), nullable=False),
        sa.Column('time_spent_seconds', sa.Integer(), nullable=False),
        sa.Column('comment_text', sa.Text(), nullable=True),
        sa.Column('issue_id', sa.String(36), sa.ForeignKey('issues.id'), nullable=False, index=True),
        sa.Column('employee_id', sa.String(36), sa.ForeignKey('employees.id'), nullable=False, index=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('synced_at', sa.DateTime(), nullable=True),
    )

    # Sync state table
    op.create_table(
        'sync_state',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('entity_name', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('last_success_at', sa.DateTime(), nullable=True),
        sa.Column('cursor_value', sa.String(255), nullable=True),
        sa.Column('last_error', sa.String(2000), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('sync_state')
    op.drop_table('worklogs')
    op.drop_table('issues')
    op.drop_table('projects')
    op.drop_table('employees')
