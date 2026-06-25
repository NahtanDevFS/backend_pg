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
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    #Lista todos los campos de cultivo activos. Filtra por ?usuario_id= para ver los asignados a un operador
    if usuario_id:
        cultivos = cultivo_service.obtener_cultivos_del_operador(db=db, usuario_id=usuario_id)
    else:
        cultivos = db.query(CampoCultivo).filter(CampoCultivo.activo == True).order_by(
            CampoCultivo.created_at.desc()).all()
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
    cultivo = _get_cultivo_activo(campo_cultivo_id, db)
    cultivo.activo = False
    cultivo.updated_by = admin.id
    db.commit()
    return {"mensaje": "Campo de cultivo desactivado correctamente."}


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