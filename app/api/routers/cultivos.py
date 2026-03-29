from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario
from app.schemas import cultivo as schemas
from app.services import cultivo_service
from app.api.deps import obtener_usuario_actual

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