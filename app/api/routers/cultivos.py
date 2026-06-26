from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, CampoCultivo, CampoCultivoOperador, Municipio
from app.schemas import cultivo as schemas
from app.services import cultivo_service
from app.api.deps import requiere_admin, requiere_operador

router = APIRouter(prefix="/cultivos", tags=["Cultivos"])


#Helpers

def _to_response(cultivo: CampoCultivo) -> schemas.CampoCultivoResponse:
    #Construye el response aplanando municipio -> departamento (decisión 1A)
    muni = cultivo.municipio
    depto = muni.departamento
    return schemas.CampoCultivoResponse(
        id=cultivo.id,
        nombre=cultivo.nombre,
        municipio_id=cultivo.municipio_id,
        municipio_nombre=muni.nombre,
        departamento_id=depto.id,
        departamento_nombre=depto.nombre,
        ubicacion=cultivo.ubicacion,
        hectareas=float(cultivo.hectareas) if cultivo.hectareas is not None else None,
        total_surcos=cultivo.total_surcos,
        activo=cultivo.activo,
        usuario_id=cultivo.usuario_id,
        created_at=cultivo.created_at,
    )


def _verificar_municipio(municipio_id: int, db: Session):
    #Lanza 404 si el municipio no existe o está inactivo
    existe = db.query(Municipio).filter(
        Municipio.id == municipio_id,
        Municipio.activo == True
    ).first()
    if not existe:
        raise HTTPException(status_code=404, detail="El municipio indicado no existe.")

def _get_cultivo_activo(campo_cultivo_id: int, db: Session) -> CampoCultivo:
    cultivo = db.query(CampoCultivo).filter(
        CampoCultivo.id == campo_cultivo_id,
        CampoCultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Campo de cultivo no encontrado.")
    return cultivo


def _verificar_acceso_operador(campo_cultivo_id: int, usuario_id: int, db: Session):
    """Lanza 403 si el operador no tiene acceso asignado al campo de cultivo."""
    acceso = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.usuario_id == usuario_id,
        CampoCultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este campo de cultivo."
        )


#Operador: sus campos de cultivo asignados

@router.get("/", response_model=List[schemas.CampoCultivoResponse])
def listar_cultivos_del_operador(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    #Devuelve los campos de cultivo a los que el operador fue asignado por el admin
    cultivos = cultivo_service.obtener_cultivos_del_operador(db=db, usuario_id=usuario.id)
    return [_to_response(c) for c in cultivos]


@router.get("/{campo_cultivo_id}", response_model=schemas.CampoCultivoResponse)
def obtener_cultivo_operador(
    campo_cultivo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    #Obtiene un campo de cultivo verificando que el operador tenga acceso
    _verificar_acceso_operador(campo_cultivo_id, usuario.id, db)
    return _to_response(_get_cultivo_activo(campo_cultivo_id, db))


#Administrador: gestión completa

@router.post("/", response_model=schemas.CampoCultivoResponse, status_code=status.HTTP_201_CREATED)
def crear_cultivo(
    cultivo_in: schemas.CampoCultivoCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    #Crea un campo de cultivo. Los operadores se asignan después con POST /{id}/operadores
    _verificar_municipio(cultivo_in.municipio_id, db)
    cultivo = cultivo_service.crear_cultivo(db=db, cultivo_in=cultivo_in, creado_por=admin.id)
    return _to_response(cultivo)


@router.get("/admin/todos", response_model=List[schemas.CampoCultivoResponse])
def listar_todos_los_cultivos(
    usuario_id: Optional[int] = None,
    incluir_inactivos: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    #Lista campos de cultivo. Por defecto solo activos; con ?incluir_inactivos=true devuelve también los desactivados.
    #Filtra por ?usuario_id= para ver los asignados a un operador (solo activos).
    if usuario_id:
        cultivos = cultivo_service.obtener_cultivos_del_operador(db=db, usuario_id=usuario_id)
    else:
        query = db.query(CampoCultivo)
        if not incluir_inactivos:
            query = query.filter(CampoCultivo.activo == True)
        cultivos = query.order_by(CampoCultivo.created_at.desc()).all()
    return [_to_response(c) for c in cultivos]


@router.put("/{campo_cultivo_id}", response_model=schemas.CampoCultivoResponse)
def modificar_cultivo(
    campo_cultivo_id: int,
    cultivo_in: schemas.CampoCultivoUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    cultivo = _get_cultivo_activo(campo_cultivo_id, db)
    if cultivo_in.municipio_id is not None:
        _verificar_municipio(cultivo_in.municipio_id, db)
    for campo, valor in cultivo_in.model_dump(exclude_none=True).items():
        setattr(cultivo, campo, valor)
    cultivo.updated_by = admin.id
    db.commit()
    db.refresh(cultivo)
    return _to_response(cultivo)


@router.patch("/{campo_cultivo_id}/desactivar")
def desactivar_cultivo(
    campo_cultivo_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    #Archiva (soft-delete) un campo de cultivo y, en cascada, toda su información asociada: operadores asignados, conteos, y de cada conteo sus procesamientos y clasificaciones por calibre. Solo se tocan los registros que estaban activos, los que ya estaban inactivos (p.ej. un procesamiento cancelado) se respetan. Cada registro apagado por la cascada se marca con desactivado_por_campo_cultivo=True para poder reactivarlo de forma determinista si se reactiva el campo.
    from app.models.models import (
        CampoCultivoOperador, Conteo, ProcesamientoVideo, ClasificacionCalibreConteo
    )

    cultivo = _get_cultivo_activo(campo_cultivo_id, db)

    #Operadores asignados activos
    db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.activo == True,
    ).update(
        {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
        synchronize_session=False,
    )

    #Conteos activos del campo
    conteos = db.query(Conteo).filter(
        Conteo.campo_cultivo_id == campo_cultivo_id,
        Conteo.activo == True,
    ).all()
    conteo_ids = [c.id for c in conteos]

    if conteo_ids:
        #Procesamientos activos de esos conteos
        db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.conteo_id.in_(conteo_ids),
            ProcesamientoVideo.activo == True,
        ).update(
            {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
            synchronize_session=False,
        )

        #Clasificaciones por calibre activas de esos conteos
        db.query(ClasificacionCalibreConteo).filter(
            ClasificacionCalibreConteo.conteo_id.in_(conteo_ids),
            ClasificacionCalibreConteo.activo == True,
        ).update(
            {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
            synchronize_session=False,
        )

        #los conteos mismos
        db.query(Conteo).filter(
            Conteo.id.in_(conteo_ids),
        ).update(
            {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
            synchronize_session=False,
        )

    #finalmente el campo de cultivo
    cultivo.activo = False
    cultivo.updated_by = admin.id

    db.commit()
    return {"mensaje": "Campo de cultivo y su información asociada desactivados correctamente."}


@router.patch("/{campo_cultivo_id}/reactivar")
def reactivar_cultivo(
    campo_cultivo_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    #Reactiva un campo de cultivo previamente desactivado y, en cascada, toda la información
    #que fue desactivada junto con él (marcada con desactivado_por_campo_cultivo=True).
    #Los registros que ya estaban inactivos antes de la desactivación del campo NO se reactivan.
    from app.models.models import (
        CampoCultivoOperador, Conteo, ProcesamientoVideo, ClasificacionCalibreConteo
    )

    cultivo = db.query(CampoCultivo).filter(
        CampoCultivo.id == campo_cultivo_id,
        CampoCultivo.activo == False,
    ).first()
    if not cultivo:
        raise HTTPException(
            status_code=404,
            detail="Campo de cultivo no encontrado o ya está activo."
        )

    #Reactivar solo los registros que fueron apagados por la cascada del campo
    db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == campo_cultivo_id,
        CampoCultivoOperador.desactivado_por_campo_cultivo == True,
    ).update(
        {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
        synchronize_session=False,
    )

    conteos = db.query(Conteo).filter(
        Conteo.campo_cultivo_id == campo_cultivo_id,
        Conteo.desactivado_por_campo_cultivo == True,
    ).all()
    conteo_ids = [c.id for c in conteos]

    if conteo_ids:
        db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.conteo_id.in_(conteo_ids),
            ProcesamientoVideo.desactivado_por_campo_cultivo == True,
        ).update(
            {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
            synchronize_session=False,
        )

        db.query(ClasificacionCalibreConteo).filter(
            ClasificacionCalibreConteo.conteo_id.in_(conteo_ids),
            ClasificacionCalibreConteo.desactivado_por_campo_cultivo == True,
        ).update(
            {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
            synchronize_session=False,
        )

        db.query(Conteo).filter(
            Conteo.id.in_(conteo_ids),
        ).update(
            {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
            synchronize_session=False,
        )

    cultivo.activo = True
    cultivo.updated_by = admin.id

    db.commit()
    return {"mensaje": "Campo de cultivo y su información asociada reactivados correctamente."}


#Gestión de operadores asignados (admin)

@router.get(
    "/{campo_cultivo_id}/operadores",
    response_model=List[schemas.OperadorAsignadoResponse]
)
def listar_operadores_asignados(
    campo_cultivo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    #Lista los operadores actualmente asignados a un campo de cultivo
    _get_cultivo_activo(campo_cultivo_id, db)
    asignaciones = cultivo_service.listar_operadores_del_cultivo(db=db, campo_cultivo_id=campo_cultivo_id)
    return [
        schemas.OperadorAsignadoResponse(
            id=a.id,
            usuario_id=a.usuario_id,
            nombre=a.operador.nombre,
            activo=a.activo,
            created_at=a.created_at,
        )
        for a in asignaciones
    ]


@router.post(
    "/{campo_cultivo_id}/operadores",
    response_model=schemas.OperadorAsignadoResponse,
    status_code=status.HTTP_201_CREATED
)
def asignar_operador(
    campo_cultivo_id: int,
    datos: schemas.AsignarOperadorRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    #Asigna un operador a un campo de cultivo
    _get_cultivo_activo(campo_cultivo_id, db)

    operador = db.query(Usuario).filter(
        Usuario.id == datos.usuario_id,
        Usuario.activo == True
    ).first()
    if not operador:
        raise HTTPException(status_code=404, detail="El operador indicado no existe o está inactivo.")
    if operador.rol.nombre != "Operador":
        raise HTTPException(status_code=400, detail="Solo se pueden asignar usuarios con rol Operador.")

    asignacion = cultivo_service.asignar_operador(
        db=db,
        campo_cultivo_id=campo_cultivo_id,
        usuario_id=datos.usuario_id,
        creado_por=admin.id
    )
    return schemas.OperadorAsignadoResponse(
        id=asignacion.id,
        usuario_id=asignacion.usuario_id,
        nombre=operador.nombre,
        activo=asignacion.activo,
        created_at=asignacion.created_at,
    )


@router.delete("/{campo_cultivo_id}/operadores/{usuario_id}", status_code=status.HTTP_200_OK)
def quitar_operador(
    campo_cultivo_id: int,
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    #Quita el acceso de un operador a un campo de cultivo
    _get_cultivo_activo(campo_cultivo_id, db)
    eliminado = cultivo_service.quitar_operador(
        db=db,
        campo_cultivo_id=campo_cultivo_id,
        usuario_id=usuario_id,
        actualizado_por=admin.id
    )
    if not eliminado:
        raise HTTPException(status_code=404, detail="El operador no estaba asignado a este campo de cultivo.")
    return {"mensaje": "Operador desasignado correctamente."}