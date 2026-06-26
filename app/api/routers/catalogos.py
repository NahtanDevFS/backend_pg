from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models.models import VariedadMelon, CalibreMelon, VariedadMelonCalibre, EstadoConteo, Rol, Usuario, Departamento, Municipio, ClasificacionCalibreConteo, Conteo
from app.schemas.catalogo import VariedadResponse, CalibreResponse, EstadoConteoResponse, RolResponse, DepartamentoResponse, MunicipioResponse, CalibreAdminResponse, CalibreCreate, CalibreUpdate, VariedadAdminResponse, VariedadCreate, VariedadUpdate, CalibreDeVariedadResponse, AsignarCalibreRequest
from app.api.deps import obtener_usuario_actual, requiere_admin

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
    # Solo calibres que además estén activos en el catálogo: si un calibre fue
    # desactivado, deja de ofrecerse para nuevos muestreos aunque la relación
    # variedad-calibre siga activa.
    calibres = [r.calibre for r in relaciones if r.calibre.activo]
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


# Gestión de calibres (admin)

def _calibre_a_admin_response(calibre: CalibreMelon, db: Session) -> dict:
    #Arma el response de un calibre incluyendo cuántas clasificaciones lo usan
    n = db.query(func.count(ClasificacionCalibreConteo.id)).filter(
        ClasificacionCalibreConteo.calibre_id == calibre.id
    ).scalar()
    return {
        "id": calibre.id,
        "nombre": calibre.nombre,
        "descripcion": calibre.descripcion,
        "orden": calibre.orden,
        "activo": calibre.activo,
        "conteos_asociados": n or 0,
    }


@router.get("/admin/calibres", response_model=List[CalibreAdminResponse])
def listar_calibres_admin(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    #Lista todos los calibres (activos e inactivos) ordenados por 'orden'.
    calibres = db.query(CalibreMelon).order_by(CalibreMelon.orden, CalibreMelon.nombre).all()
    return [_calibre_a_admin_response(c, db) for c in calibres]


@router.post("/admin/calibres", response_model=CalibreAdminResponse, status_code=201)
def crear_calibre(
    datos: CalibreCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    nombre = datos.nombre.strip()
    existente = db.query(CalibreMelon).filter(
        func.lower(CalibreMelon.nombre) == nombre.lower()
    ).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe un calibre con ese nombre.")

    calibre = CalibreMelon(
        nombre=nombre,
        descripcion=(datos.descripcion or None),
        orden=datos.orden,
        created_by=admin.id,
    )
    db.add(calibre)
    db.commit()
    db.refresh(calibre)
    return _calibre_a_admin_response(calibre, db)


@router.patch("/admin/calibres/{calibre_id}", response_model=CalibreAdminResponse)
def editar_calibre(
    calibre_id: int,
    datos: CalibreUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Edita nombre/descripcion/orden. El cambio de nombre se refleja en los conteos históricos (la FK apunta al mismo registro), que es el comportamiento deseado
    calibre = db.query(CalibreMelon).filter(CalibreMelon.id == calibre_id).first()
    if not calibre:
        raise HTTPException(status_code=404, detail="Calibre no encontrado.")

    nombre = datos.nombre.strip()
    choque = db.query(CalibreMelon).filter(
        func.lower(CalibreMelon.nombre) == nombre.lower(),
        CalibreMelon.id != calibre_id,
    ).first()
    if choque:
        raise HTTPException(status_code=409, detail="Ya existe otro calibre con ese nombre.")

    calibre.nombre = nombre
    calibre.descripcion = (datos.descripcion or None)
    calibre.orden = datos.orden
    calibre.updated_by = admin.id
    db.commit()
    db.refresh(calibre)
    return _calibre_a_admin_response(calibre, db)


@router.patch("/admin/calibres/{calibre_id}/desactivar", response_model=CalibreAdminResponse)
def desactivar_calibre(
    calibre_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Soft-delete: el calibre deja de ofrecerse para nuevos muestreos, pero los
    #conteos históricos que lo usaron quedan intactos (la FK sigue resolviendo).
    calibre = db.query(CalibreMelon).filter(CalibreMelon.id == calibre_id).first()
    if not calibre:
        raise HTTPException(status_code=404, detail="Calibre no encontrado.")
    calibre.activo = False
    calibre.updated_by = admin.id
    db.commit()
    db.refresh(calibre)
    return _calibre_a_admin_response(calibre, db)


@router.patch("/admin/calibres/{calibre_id}/activar", response_model=CalibreAdminResponse)
def activar_calibre(
    calibre_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    calibre = db.query(CalibreMelon).filter(CalibreMelon.id == calibre_id).first()
    if not calibre:
        raise HTTPException(status_code=404, detail="Calibre no encontrado.")
    calibre.activo = True
    calibre.updated_by = admin.id
    db.commit()
    db.refresh(calibre)
    return _calibre_a_admin_response(calibre, db)


#Gestión de variedades (admin)

def _variedad_a_admin_response(variedad: VariedadMelon, db: Session) -> dict:
    #Arma el response de una variedad incluyendo cuántos conteos la usan.
    n = db.query(func.count(Conteo.id)).filter(
        Conteo.variedad_id == variedad.id
    ).scalar()
    return {
        "id": variedad.id,
        "nombre": variedad.nombre,
        "descripcion": variedad.descripcion,
        "activo": variedad.activo,
        "conteos_asociados": n or 0,
    }


@router.get("/admin/variedades", response_model=List[VariedadAdminResponse])
def listar_variedades_admin(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    #Lista TODAS las variedades (activas e inactivas) ordenadas por nombre.
    variedades = db.query(VariedadMelon).order_by(VariedadMelon.nombre).all()
    return [_variedad_a_admin_response(v, db) for v in variedades]


@router.post("/admin/variedades", response_model=VariedadAdminResponse, status_code=201)
def crear_variedad(
    datos: VariedadCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    nombre = datos.nombre.strip()
    existente = db.query(VariedadMelon).filter(
        func.lower(VariedadMelon.nombre) == nombre.lower()
    ).first()
    if existente:
        raise HTTPException(status_code=409, detail="Ya existe una variedad con ese nombre.")

    variedad = VariedadMelon(
        nombre=nombre,
        descripcion=(datos.descripcion or None),
        created_by=admin.id,
    )
    db.add(variedad)
    db.commit()
    db.refresh(variedad)
    return _variedad_a_admin_response(variedad, db)


@router.patch("/admin/variedades/{variedad_id}", response_model=VariedadAdminResponse)
def editar_variedad(
    variedad_id: int,
    datos: VariedadUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Edita nombre/descripcion. El cambio de nombre se refleja en los conteos
    #históricos (la FK apunta al mismo registro), que es el comportamiento deseado.
    variedad = db.query(VariedadMelon).filter(VariedadMelon.id == variedad_id).first()
    if not variedad:
        raise HTTPException(status_code=404, detail="Variedad no encontrada.")

    nombre = datos.nombre.strip()
    choque = db.query(VariedadMelon).filter(
        func.lower(VariedadMelon.nombre) == nombre.lower(),
        VariedadMelon.id != variedad_id,
    ).first()
    if choque:
        raise HTTPException(status_code=409, detail="Ya existe otra variedad con ese nombre.")

    variedad.nombre = nombre
    variedad.descripcion = (datos.descripcion or None)
    variedad.updated_by = admin.id
    db.commit()
    db.refresh(variedad)
    return _variedad_a_admin_response(variedad, db)


@router.patch("/admin/variedades/{variedad_id}/desactivar", response_model=VariedadAdminResponse)
def desactivar_variedad(
    variedad_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Soft-delete: la variedad deja de ofrecerse para nuevos conteos, pero los
    #conteos históricos que la usaron quedan intactos (la FK sigue resolviendo).
    variedad = db.query(VariedadMelon).filter(VariedadMelon.id == variedad_id).first()
    if not variedad:
        raise HTTPException(status_code=404, detail="Variedad no encontrada.")
    variedad.activo = False
    variedad.updated_by = admin.id
    db.commit()
    db.refresh(variedad)
    return _variedad_a_admin_response(variedad, db)


@router.patch("/admin/variedades/{variedad_id}/activar", response_model=VariedadAdminResponse)
def activar_variedad(
    variedad_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    variedad = db.query(VariedadMelon).filter(VariedadMelon.id == variedad_id).first()
    if not variedad:
        raise HTTPException(status_code=404, detail="Variedad no encontrada.")
    variedad.activo = True
    variedad.updated_by = admin.id
    db.commit()
    db.refresh(variedad)
    return _variedad_a_admin_response(variedad, db)


# ── Relación variedad ↔ calibre (admin, Fase 3) ─────────────────

def _contar_conteos_variedad_calibre(variedad_id: int, calibre_id: int, db: Session) -> int:
    #Cuántos conteos de ESTA variedad usaron ESTE calibre en su muestreo.
    #Sirve para advertir al quitar un calibre que tiene historial en la variedad.
    return db.query(func.count(ClasificacionCalibreConteo.id)).join(
        Conteo, Conteo.id == ClasificacionCalibreConteo.conteo_id
    ).filter(
        Conteo.variedad_id == variedad_id,
        ClasificacionCalibreConteo.calibre_id == calibre_id,
    ).scalar() or 0


@router.get(
    "/admin/variedades/{variedad_id}/calibres",
    response_model=List[CalibreDeVariedadResponse],
)
def listar_calibres_de_variedad_admin(
    variedad_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    #Lista TODOS los calibres activos del sistema, indicando para cada uno si
    #está asignado a esta variedad (relación activa) y cuántos conteos de la
    #variedad lo han usado. Pensado para el modal de gestión de calibres.
    variedad = db.query(VariedadMelon).filter(VariedadMelon.id == variedad_id).first()
    if not variedad:
        raise HTTPException(status_code=404, detail="Variedad no encontrada.")

    calibres = db.query(CalibreMelon).filter(
        CalibreMelon.activo == True
    ).order_by(CalibreMelon.orden, CalibreMelon.nombre).all()

    relaciones = db.query(VariedadMelonCalibre).filter(
        VariedadMelonCalibre.variedad_id == variedad_id,
        VariedadMelonCalibre.activo == True,
    ).all()
    asignados = {r.calibre_id for r in relaciones}

    resultado = []
    for c in calibres:
        resultado.append({
            "calibre_id": c.id,
            "nombre": c.nombre,
            "descripcion": c.descripcion,
            "orden": c.orden,
            "asignado": c.id in asignados,
            "conteos_en_variedad": _contar_conteos_variedad_calibre(variedad_id, c.id, db),
        })
    return resultado


@router.post("/admin/variedades/{variedad_id}/calibres", status_code=204)
def asignar_calibre_a_variedad(
    variedad_id: int,
    datos: AsignarCalibreRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Asigna un calibre a una variedad. Si la fila puente ya existe pero está
    #inactiva, la reactiva (respeta la UNIQUE constraint variedad+calibre).
    variedad = db.query(VariedadMelon).filter(VariedadMelon.id == variedad_id).first()
    if not variedad:
        raise HTTPException(status_code=404, detail="Variedad no encontrada.")
    calibre = db.query(CalibreMelon).filter(CalibreMelon.id == datos.calibre_id).first()
    if not calibre:
        raise HTTPException(status_code=404, detail="Calibre no encontrado.")
    if not calibre.activo:
        raise HTTPException(status_code=400, detail="No se puede asignar un calibre inactivo.")

    rel = db.query(VariedadMelonCalibre).filter(
        VariedadMelonCalibre.variedad_id == variedad_id,
        VariedadMelonCalibre.calibre_id == datos.calibre_id,
    ).first()

    if rel:
        if not rel.activo:
            rel.activo = True
            rel.updated_by = admin.id
    else:
        rel = VariedadMelonCalibre(
            variedad_id=variedad_id,
            calibre_id=datos.calibre_id,
            created_by=admin.id,
        )
        db.add(rel)
    db.commit()
    return


@router.delete("/admin/variedades/{variedad_id}/calibres/{calibre_id}", status_code=204)
def quitar_calibre_de_variedad(
    variedad_id: int,
    calibre_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    #Quita (soft-delete) la relación variedad-calibre. NO toca los conteos
    #históricos: las clasificaciones ya guardadas con este calibre se conservan.
    #Solo deja de ofrecerse el calibre para nuevos muestreos de esta variedad.
    rel = db.query(VariedadMelonCalibre).filter(
        VariedadMelonCalibre.variedad_id == variedad_id,
        VariedadMelonCalibre.calibre_id == calibre_id,
        VariedadMelonCalibre.activo == True,
    ).first()
    if not rel:
        raise HTTPException(status_code=404, detail="La relación no existe o ya está inactiva.")
    rel.activo = False
    rel.updated_by = admin.id
    db.commit()
    return