from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.core.config import settings


engine = create_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

class Base(DeclarativeBase):
    pass

# abre una sesion de BD por request y la cierra al terminar, se inyecta con Depends
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()