from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import models
from app.models.models import Usuario
from app.schemas import cultivo as schemas
from app.services import cultivo_service
from app.api.deps import obtener_usuario_actual
from fastapi import HTTPException

router = APIRouter(prefix="/cultivos", tags=["Cultivos"])

@router.post("/", response_model=schemas.CultivoResponse, status_code=status.HTTP_201_CREATED)
def crear_cultivo(
    cultivo_in: schemas.CultivoCreate,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    return cultivo_service.crear_cultivo(
        db=db,
        cultivo_in=cultivo_in,
        usuario_id=usuario_actual.id
    )

@router.get("/", response_model=List[schemas.CultivoResponse])
def listar_cultivos(
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    return cultivo_service.obtener_cultivos_por_usuario(
        db=db,
        usuario_id=usuario_actual.id
    )


@router.put("/{cultivo_id}", response_model=schemas.CultivoResponse)
def modificar_cultivo(
        cultivo_id: int,
        cultivo_in: schemas.CultivoCreate,
        db: Session = Depends(get_db),
        usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(models.Cultivo).filter(models.Cultivo.id == cultivo_id,
                                              models.Cultivo.usuario_id == usuario_actual.id).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    cultivo.nombre = cultivo_in.nombre
    cultivo.ubicacion = cultivo_in.ubicacion
    cultivo.hectareas = cultivo_in.hectareas
    db.commit()
    db.refresh(cultivo)
    return cultivo


@router.patch("/{cultivo_id}/desactivar")
def desactivar_cultivo(
        cultivo_id: int,
        db: Session = Depends(get_db),
        usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(models.Cultivo).filter(models.Cultivo.id == cultivo_id,
                                              models.Cultivo.usuario_id == usuario_actual.id).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    cultivo.activo = False
    db.commit()
    return {"mensaje": "Cultivo desactivado correctamente"}