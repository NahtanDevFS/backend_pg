from sqlalchemy.orm import Session
from app.models.models import CampoCultivo, CampoCultivoOperador
from app.schemas import cultivo as schemas

CAMPOS_CULTIVO = {"nombre", "municipio_id", "ubicacion", "hectareas", "total_surcos", "activo"}


def crear_cultivo(
    db: Session,
    cultivo_in: schemas.CampoCultivoBase,
    creado_por: int,
) -> CampoCultivo:
    campos = {k: v for k, v in cultivo_in.model_dump().items() if k in CAMPOS_CULTIVO}
    nuevo = CampoCultivo(
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
        db.query(CampoCultivo)
        .join(CampoCultivoOperador, CampoCultivoOperador.campo_cultivo_id == CampoCultivo.id)
        .filter(
            CampoCultivoOperador.usuario_id == usuario_id,
            CampoCultivoOperador.activo == True,
            CampoCultivo.activo == True,
        )
        .all()
    )


def asignar_operador(db: Session, campo_cultivo_id: int, usuario_id: int, creado_por: int) -> CampoCultivoOperador:
    existente = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.usuario_id == usuario_id,
    ).first()

    if existente:
        existente.activo = True
        existente.updated_by = creado_por
        db.commit()
        db.refresh(existente)
        return existente

    nueva = CampoCultivoOperador(
        campo_cultivo_id=campo_cultivo_id,
        usuario_id=usuario_id,
        created_by=creado_por,
    )
    db.add(nueva)
    db.commit()
    db.refresh(nueva)
    return nueva


def quitar_operador(db: Session, campo_cultivo_id: int, usuario_id: int, actualizado_por: int) -> bool:
    asignacion = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.usuario_id == usuario_id,
        CampoCultivoOperador.activo == True,
    ).first()

    if not asignacion:
        return False

    asignacion.activo = False
    asignacion.updated_by = actualizado_por
    db.commit()
    return True


def listar_operadores_del_cultivo(db: Session, campo_cultivo_id: int):
    return db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.activo == True,
    ).all()