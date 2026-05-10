from sqlalchemy.orm import Session
from app.models.models import Cultivo, CultivoOperador
from app.schemas import cultivo as schemas

CAMPOS_CULTIVO = {"nombre", "ubicacion", "hectareas", "total_surcos", "activo"}


def crear_cultivo(
    db: Session,
    cultivo_in: schemas.CultivoBase,
    creado_por: int,
) -> Cultivo:
    campos = {k: v for k, v in cultivo_in.model_dump().items() if k in CAMPOS_CULTIVO}
    nuevo = Cultivo(
        **campos,
        usuario_id=creado_por,
        created_by=creado_por,
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


def obtener_cultivos_del_operador(db: Session, usuario_id: int):
    return (
        db.query(Cultivo)
        .join(CultivoOperador, CultivoOperador.cultivo_id == Cultivo.id)
        .filter(
            CultivoOperador.usuario_id == usuario_id,
            CultivoOperador.activo == True,
            Cultivo.activo == True,
        )
        .all()
    )


def asignar_operador(db: Session, cultivo_id: int, usuario_id: int, creado_por: int) -> CultivoOperador:
    existente = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo_id,
        CultivoOperador.usuario_id == usuario_id,
    ).first()

    if existente:
        existente.activo = True
        existente.updated_by = creado_por
        db.commit()
        db.refresh(existente)
        return existente

    nueva = CultivoOperador(
        cultivo_id=cultivo_id,
        usuario_id=usuario_id,
        created_by=creado_por,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


def quitar_operador(db: Session, cultivo_id: int, usuario_id: int, actualizado_por: int) -> bool:
    asignacion = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo_id,
        CultivoOperador.usuario_id == usuario_id,
        CultivoOperador.activo == True,
    ).first()

    if not asignacion:
        return False

    asignacion.activo = False
    asignacion.updated_by = actualizado_por
    db.commit()
    return True


def listar_operadores_del_cultivo(db: Session, cultivo_id: int):
    return db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo_id,
        CultivoOperador.activo == True,
    ).all()