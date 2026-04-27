from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Variedad, Calibre, VariedadCalibre, EstadoConteo, Rol, Usuario
from app.schemas.catalogo import VariedadResponse, CalibreResponse, EstadoConteoResponse, RolResponse
from app.api.deps import obtener_usuario_actual

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


@router.get("/variedades", response_model=List[VariedadResponse])
def listar_variedades(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
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
    calibres = [r.calibre for r in relaciones]
    return sorted(calibres, key=lambda c: c.orden)


@router.get("/estados-conteo", response_model=List[EstadoConteoResponse])
def listar_estados_conteo(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    return db.query(EstadoConteo).filter(EstadoConteo.activo == True).all()


@router.get("/roles", response_model=List[RolResponse])
def listar_roles(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    return db.query(Rol).filter(Rol.activo == True).all()