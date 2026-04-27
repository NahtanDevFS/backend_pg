from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas import usuario as schemas
from app.services import usuario_service
from app.api.deps import obtener_usuario_actual, requiere_admin
from app.models.models import Usuario

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.post(
    "/",
    response_model=schemas.UsuarioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Crear usuario (solo Administrador)"
)
def crear_usuario(
    usuario_in: schemas.UsuarioCreate,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    return usuario_service.crear_usuario(db=db, usuario_in=usuario_in, creado_por=admin.id)


@router.get("/", response_model=List[schemas.UsuarioResponse], summary="Listar usuarios (solo Administrador)")
def listar_usuarios(
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    return db.query(Usuario).filter(Usuario.activo == True).all()


@router.get("/me", response_model=schemas.UsuarioResponse)
def leer_usuario_actual(usuario_actual: Usuario = Depends(obtener_usuario_actual)):
    return usuario_actual


@router.patch("/{usuario_id}/desactivar", summary="Desactivar usuario (solo Administrador)")
def desactivar_usuario(
    usuario_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin)
):
    if usuario_id == admin.id:
        raise HTTPException(status_code=400, detail="No puedes desactivar tu propia cuenta.")

    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.activo == True).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    usuario.activo = False
    usuario.updated_by = admin.id
    db.commit()
    return {"mensaje": "Usuario desactivado correctamente."}