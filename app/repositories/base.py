"""Base repository with common CRUD operations."""

from typing import Generic, TypeVar, Type, Optional, List, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """Generic repository with CRUD operations.
    
    This abstraction layer isolates SQLAlchemy from business logic,
    making future migration to PostgreSQL seamless.
    """
    
    def __init__(self, model: Type[ModelType], db: Session):
        self.model = model
        self.db = db
    
    def get(self, id: str) -> Optional[ModelType]:
        """Get entity by ID."""
        return self.db.get(self.model, id)
    
    def get_by_field(self, field: str, value: Any) -> Optional[ModelType]:
        """Get entity by arbitrary field."""
        stmt = select(self.model).where(getattr(self.model, field) == value)
        return self.db.execute(stmt).scalar_one_or_none()
    
    def get_all(self, skip: int = 0, limit: int = 100) -> List[ModelType]:
        """Get all entities with pagination."""
        stmt = select(self.model).offset(skip).limit(limit)
        return list(self.db.execute(stmt).scalars().all())
    
    def create(self, obj_in: dict) -> ModelType:
        """Create new entity."""
        db_obj = self.model(**obj_in)
        self.db.add(db_obj)
        self.db.flush()
        return db_obj
    
    def update(self, db_obj: ModelType, obj_in: dict) -> ModelType:
        """Update entity."""
        for field, value in obj_in.items():
            setattr(db_obj, field, value)
        self.db.flush()
        return db_obj
    
    def delete(self, db_obj: ModelType) -> None:
        """Delete entity."""
        self.db.delete(db_obj)
        self.db.flush()
    
    def upsert_by_field(
        self,
        field: str,
        value: Any,
        obj_in: dict,
    ) -> tuple[ModelType, bool]:
        """Update if exists, create otherwise. Returns (entity, created)."""
        existing = self.get_by_field(field, value)
        if existing:
            return self.update(existing, obj_in), False
        return self.create(obj_in), True
