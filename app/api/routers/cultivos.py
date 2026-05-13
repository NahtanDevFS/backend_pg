from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, Cultivo, CultivoOperador
from app.schemas import cultivo as schemas
from app.services import cultivo_service
from app.api.deps import requiere_admin, requiere_operador

router = APIRouter(prefix="/cultivos", tags=["Cultivos"])


#Helpers

def _get_cultivo_activo(cultivo_id: int, db: Session) -> Cultivo:
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == cultivo_id,
        Cultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")
    return cultivo


def _verificar_acceso_operador(cultivo_id: int, usuario_id: int, db: Session):
    """Lanza 403 si el operador no tiene acceso asignado al cultivo."""
    acceso = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo_id,
        CultivoOperador.usuario_id == usuario_id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes acceso a este cultivo."
        )


#Operador: sus cultivos asignados

@router.get("/", response_model=List[schemas.CultivoResponse])
def listar_cultivos_del_operador(
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    """Devuelve los cultivos a los que el operador fue asignado por el admin."""
    return cultivo_service.obtener_cultivos_del_operador(db=db, usuario_id=usuario.id)


@router.get("/{cultivo_id}", response_model=schemas.CultivoResponse)
def obtener_cultivo_operador(
    cultivo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    """Obtiene un cultivo verificando que el operador tenga acceso."""
    _verificar_acceso_operador(cultivo_id, usuario.id, db)
    return _get_cultivo_activo(cultivo_id, db)


#Administrador: gestión completa

@router.post("/", response_model=schemas.CultivoResponse, status_code=status.HTTP_201_CREATED)
def crear_cultivo(
    cultivo_in: schemas.CultivoCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    """Crea un cultivo. Los operadores se asignan después con POST /{id}/operadores."""
    return cultivo_service.crear_cultivo(db=db, cultivo_in=cultivo_in, creado_por=admin.id)


@router.get("/admin/todos", response_model=List[schemas.CultivoResponse])
def listar_todos_los_cultivos(
    usuario_id: Optional[int] = None,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    """Lista todos los cultivos activos. Filtra por ?usuario_id= para ver los asignados a un operador."""
    if usuario_id:
        return cultivo_service.obtener_cultivos_del_operador(db=db, usuario_id=usuario_id)
    return db.query(Cultivo).filter(Cultivo.activo == True).order_by(Cultivo.created_at.desc()).all()


@router.put("/{cultivo_id}", response_model=schemas.CultivoResponse)
def modificar_cultivo(
    cultivo_id: int,
    cultivo_in: schemas.CultivoUpdate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    cultivo = _get_cultivo_activo(cultivo_id, db)
    for campo, valor in cultivo_in.model_dump(exclude_none=True).items():
        setattr(cultivo, campo, valor)
    cultivo.updated_by = admin.id
    db.commit()
    db.refresh(cultivo)
    return cultivo


@router.patch("/{cultivo_id}/desactivar")
def desactivar_cultivo(
    cultivo_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    cultivo = _get_cultivo_activo(cultivo_id, db)
    cultivo.activo = False
    cultivo.updated_by = admin.id
    db.commit()
    return {"mensaje": "Cultivo desactivado correctamente."}


#Gestión de operadores asignados (admin)

@router.get(
    "/{cultivo_id}/operadores",
    response_model=List[schemas.OperadorAsignadoResponse]
)
def listar_operadores_asignados(
    cultivo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    #Lista los operadores actualmente asignados a un cultivo
    _get_cultivo_activo(cultivo_id, db)
    asignaciones = cultivo_service.listar_operadores_del_cultivo(db=db, cultivo_id=cultivo_id)
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
    "/{cultivo_id}/operadores",
    response_model=schemas.OperadorAsignadoResponse,
    status_code=status.HTTP_201_CREATED
)
def asignar_operador(
    cultivo_id: int,
    datos: schemas.AsignarOperadorRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    """Asigna un operador a un cultivo."""
    _get_cultivo_activo(cultivo_id, db)

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
        cultivo_id=cultivo_id,
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


@router.delete("/{cultivo_id}/operadores/{usuario_id}", status_code=status.HTTP_200_OK)
def quitar_operador(
    cultivo_id: int,
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    """Quita el acceso de un operador a un cultivo."""
    _get_cultivo_activo(cultivo_id, db)
    eliminado = cultivo_service.quitar_operador(
        db=db,
        cultivo_id=cultivo_id,
        usuario_id=usuario_id,
        actualizado_por=admin.id
    )
    if not eliminado:
        raise HTTPException(status_code=404, detail="El operador no estaba asignado a este cultivo.")
    return {"mensaje": "Operador desasignado correctamente."}