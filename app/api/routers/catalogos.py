from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Variedad, Calibre, VariedadCalibre, EstadoSesion, EstadoProcesamiento, Rol
from app.schemas.catalogo import (
    VariedadResponse, CalibreResponse,
    EstadoSesionResponse, EstadoProcesamientoResponse, RolResponse
)
from app.api.deps import obtener_usuario_actual
from app.models.models import Usuario

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


@router.get("/variedades", response_model=List[VariedadResponse])
def listar_variedades(
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    return db.query(Variedad).filter(Variedad.activo == True).all()


@router.get("/variedades/{variedad_id}/calibres", response_model=List[CalibreResponse])
def listar_calibres_por_variedad(
    variedad_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    relaciones = db.query(VariedadCalibre).filter(
        VariedadCalibre.variedad_id == variedad_id,
        VariedadCalibre.activo == True
    ).all()
    return [r.calibre for r in relaciones]


@router.get("/estados-sesion", response_model=List[EstadoSesionResponse])
def listar_estados_sesion(
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    return db.query(EstadoSesion).filter(EstadoSesion.activo == True).all()


@router.get("/roles", response_model=List[RolResponse])
def listar_roles(
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    return db.query(Rol).filter(Rol.activo == True).all()