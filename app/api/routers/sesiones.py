from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, Cultivo, SesionConteo, EstadoSesion
from app.schemas import sesion as schemas
from app.api.deps import obtener_usuario_actual

router = APIRouter(prefix="/sesiones", tags=["Sesiones de Conteo"])


@router.post("/", response_model=schemas.SesionResponse, status_code=status.HTTP_201_CREATED)
def crear_sesion(
    sesion_in: schemas.SesionCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == sesion_in.cultivo_id,
        Cultivo.usuario_id == usuario_actual.id,
        Cultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado o sin acceso.")

    estado_inicial = db.query(EstadoSesion).filter(EstadoSesion.nombre == "en_progreso").first()
    if not estado_inicial:
        raise HTTPException(status_code=500, detail="Estado 'en_progreso' no encontrado en catálogo.")

    nueva_sesion = SesionConteo(
        cultivo_id=sesion_in.cultivo_id,
        variedad_id=sesion_in.variedad_id,
        estado_id=estado_inicial.id,
        fecha_sesion=sesion_in.fecha_sesion,
        observaciones=sesion_in.observaciones,
        created_by=usuario_actual.id
    )
    db.add(nueva_sesion)
    db.commit()
    db.refresh(nueva_sesion)
    return nueva_sesion


@router.get("/cultivo/{cultivo_id}", response_model=List[schemas.SesionResponse])
def listar_sesiones_por_cultivo(
    cultivo_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == cultivo_id,
        Cultivo.usuario_id == usuario_actual.id
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado o sin acceso.")

    return db.query(SesionConteo).filter(
        SesionConteo.cultivo_id == cultivo_id,
        SesionConteo.activo == True
    ).order_by(SesionConteo.fecha_sesion.desc()).all()


@router.get("/{sesion_id}", response_model=schemas.SesionResponse)
def obtener_sesion(
    sesion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    sesion = db.query(SesionConteo).join(Cultivo).filter(
        SesionConteo.id == sesion_id,
        Cultivo.usuario_id == usuario_actual.id,
        SesionConteo.activo == True
    ).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")
    return sesion


@router.patch("/{sesion_id}/completar")
def completar_sesion(
    sesion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    sesion = db.query(SesionConteo).join(Cultivo).filter(
        SesionConteo.id == sesion_id,
        Cultivo.usuario_id == usuario_actual.id,
        SesionConteo.activo == True
    ).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada.")

    estado_completada = db.query(EstadoSesion).filter(EstadoSesion.nombre == "completada").first()
    sesion.estado_id = estado_completada.id
    sesion.updated_by = usuario_actual.id
    db.commit()
    return {"mensaje": "Sesión marcada como completada."}