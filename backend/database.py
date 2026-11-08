from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from config import settings

engine = create_engine(settings.DATABASE_URL, echo=settings.DEBUG)
SyncSession = sessionmaker(bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SyncSession()
    try:
        yield db
    finally:
        db.close()
