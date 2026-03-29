from sqlalchemy.orm import Session
from app.models import models
from app.schemas import cultivo as schemas

def crear_cultivo(db: Session, cultivo_in: schemas.CultivoCreate, usuario_id: int):
    nuevo_cultivo = models.Cultivo(
        **cultivo_in.model_dump(),
        usuario_id=usuario_id
    )
    db.add(nuevo_cultivo)
    db.commit()
    db.refresh(nuevo_cultivo)
    return nuevo_cultivo

def obtener_cultivos_por_usuario(db: Session, usuario_id: int):
    return db.query(models.Cultivo).filter(models.Cultivo.usuario_id == usuario_id).all()