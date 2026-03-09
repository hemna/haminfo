from sqlalchemy.orm import DeclarativeBase


class ModelBase(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models.

    Uses the modern DeclarativeBase class (SQLAlchemy 2.0+) instead of
    the deprecated declarative_base() function.
    """

    pass
