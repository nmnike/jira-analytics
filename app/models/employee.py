"""Employee model."""

from typing import Optional, List, TYPE_CHECKING

from sqlalchemy import String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.base import SyncedMixin, generate_uuid

if TYPE_CHECKING:
    from app.models.worklog import Worklog


class Employee(Base, SyncedMixin):
    """Employee/user from Jira."""
    
    __tablename__ = "employees"
    
    id: Mapped[str] = mapped_column(
        String(36),
        primary_key=True,
        default=generate_uuid,
    )
    jira_account_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    
    # Relationships
    worklogs: Mapped[List["Worklog"]] = relationship(
        back_populates="employee",
        cascade="all, delete-orphan",
    )
    
    def __repr__(self) -> str:
        return f"<Employee {self.display_name}>"
