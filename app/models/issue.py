"""Issue model."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SyncedMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.project import Project
    from app.models.worklog import Worklog


class Issue(Base, SyncedMixin):
    """Jira issue (task, epic, bug, etc.)."""
    
    __tablename__ = "issues"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    jira_issue_id: Mapped[str] = mapped_column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(
        String(32),
        unique=True,
        nullable=False,
        index=True,
    )
    summary: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    issue_type: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    priority: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    
    # Parent reference (for subtasks, stories in epics)
    parent_id: Mapped[Optional[str]] = mapped_column(
        String(36),
        ForeignKey("issues.id"),
        nullable=True,
        index=True,
    )
    
    # Project reference
    project_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )
    
    # Relationships
    project: Mapped["Project"] = relationship(back_populates="issues")
    parent: Mapped[Optional["Issue"]] = relationship(
        back_populates="children",
        remote_side=[id],
    )
    children: Mapped[List["Issue"]] = relationship(
        back_populates="parent",
        cascade="all, delete-orphan",
    )
    worklogs: Mapped[List["Worklog"]] = relationship(
        back_populates="issue",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Issue {self.key}>"
