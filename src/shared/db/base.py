"""SQLAlchemy declarative base shared across modules."""
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
