from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.schemas import usuario as schemas
from app.services import usuario_service
from app.api.deps import obtener_usuario_actual, requiere_admin
from app.models.models import Usuario
from app.core.security import get_password_hash

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


@router.patch(
    "/{usuario_id}",
    response_model=schemas.UsuarioResponse,
    summary="Editar usuario (solo Administrador)"
)
def editar_usuario(
        usuario_id: int,
        datos: schemas.UsuarioEdit,
        db: Session = Depends(get_db),
        admin: Usuario = Depends(requiere_admin)
):
    usuario = db.query(Usuario).filter(Usuario.id == usuario_id, Usuario.activo == True).first()
    if not usuario:
        raise HTTPException(status_code=404, detail="Usuario no encontrado.")

    if datos.nombre is not None:
        # Verificar que el nuevo nombre no esté en uso por otro usuario
        existente = db.query(Usuario).filter(
            Usuario.nombre == datos.nombre,
            Usuario.id != usuario_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese nombre.")
        usuario.nombre = datos.nombre

    if datos.rol_id is not None:
        usuario.rol_id = datos.rol_id

    if datos.password is not None:
        usuario.password_hash = get_password_hash(datos.password)

    usuario.updated_by = admin.id
    db.commit()
    db.refresh(usuario)
    return usuario


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