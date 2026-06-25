from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import VariedadMelon, CalibreMelon, VariedadMelonCalibre, EstadoConteo, Rol, Usuario, Departamento, Municipio
from app.schemas.catalogo import VariedadResponse, CalibreResponse, EstadoConteoResponse, RolResponse, DepartamentoResponse, MunicipioResponse
from app.api.deps import obtener_usuario_actual

router = APIRouter(prefix="/catalogos", tags=["Catálogos"])


@router.get("/variedades", response_model=List[VariedadResponse])
def listar_variedades(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    return db.query(VariedadMelon).filter(VariedadMelon.activo == True).all()


@router.get("/variedades/{variedad_id}/calibres", response_model=List[CalibreResponse])
def listar_calibres_por_variedad(
    variedad_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    relaciones = db.query(VariedadMelonCalibre).filter(
        VariedadMelonCalibre.variedad_id == variedad_id,
        VariedadMelonCalibre.activo == True
    ).all()
    calibres = [r.calibre for r in relaciones]
    return sorted(calibres, key=lambda c: c.orden)


@router.get("/estados-conteo", response_model=List[EstadoConteoResponse])
def listar_estados_conteo(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    return db.query(EstadoConteo).filter(EstadoConteo.activo == True).all()


@router.get("/roles", response_model=List[RolResponse])
def listar_roles(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    return db.query(Rol).filter(Rol.activo == True).all()

@router.get("/departamentos", response_model=List[DepartamentoResponse])
def listar_departamentos(db: Session = Depends(get_db), _: Usuario = Depends(obtener_usuario_actual)):
    #Lista todos los departamentos activos, ordenados alfabéticamente
    return db.query(Departamento).filter(
        Departamento.activo == True
    ).order_by(Departamento.nombre).all()


@router.get("/departamentos/{departamento_id}/municipios", response_model=List[MunicipioResponse])
def listar_municipios_por_departamento(
    departamento_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(obtener_usuario_actual)
):
    #Lista los municipios de un departamento, ordenados alfabéticamente (para el selector en cascada)
    return db.query(Municipio).filter(
        Municipio.departamento_id == departamento_id,
        Municipio.activo == True
    ).order_by(Municipio.nombre).all()