from sqlalchemy.orm import Session
from app.models.models import Cultivo
from app.schemas import cultivo as schemas


def crear_cultivo(db: Session, cultivo_in: schemas.CultivoCreate, usuario_id: int) -> Cultivo:
    nuevo = Cultivo(
        **cultivo_in.model_dump(),
        usuario_id=usuario_id,
        created_by=usuario_id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


def obtener_cultivos_por_usuario(db: Session, usuario_id: int):
    return db.query(Cultivo).filter(
        Cultivo.usuario_id == usuario_id,
        Cultivo.activo == True
    ).all()