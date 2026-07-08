from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.core.database import get_db
from app.schemas import usuario as schemas
from app.services import usuario_service
from app.api.deps import obtener_usuario_actual, requiere_admin
from app.models.models import Usuario, Rol
from app.core.security import get_password_hash, verify_password, validar_password

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

@router.patch("/me/password", summary="Cambiar la propia contraseña")
def cambiar_password_propia(
    datos: schemas.CambiarPasswordPropiaRequest,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual),
):
    # El usuario cambia su propia contraseña acreditando la actual; limpia debe_cambiar_password.
    if not verify_password(datos.password_actual, usuario_actual.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="La contraseña actual no es correcta.",
        )

    validar_password(datos.password_nueva)

    usuario_actual.password_hash = get_password_hash(datos.password_nueva)
    usuario_actual.debe_cambiar_password = False
    usuario_actual.updated_by = usuario_actual.id
    db.commit()
    return {"mensaje": "Contraseña actualizada correctamente."}

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
        # Normaliza y verifica el nombre case-insensitive (igual que creación y login).
        nombre = datos.nombre.strip()
        if not nombre:
            raise HTTPException(status_code=400, detail="El nombre de usuario no puede estar vacío.")
        existente = db.query(Usuario).filter(
            func.lower(Usuario.nombre) == nombre.lower(),
            Usuario.id != usuario_id
        ).first()
        if existente:
            raise HTTPException(status_code=400, detail="Ya existe un usuario con ese nombre.")
        usuario.nombre = nombre

    if datos.rol_id is not None:
        rol_admin = db.query(Rol).filter(Rol.nombre == "Administrador").first()
        # Al quitar el rol Administrador, impide dejar al sistema sin ningún admin activo.
        if (
            rol_admin
            and usuario.rol_id == rol_admin.id
            and datos.rol_id != rol_admin.id
        ):
            otros_admins = db.query(Usuario).filter(
                Usuario.rol_id == rol_admin.id,
                Usuario.activo == True,
                Usuario.id != usuario.id,
            ).count()
            if otros_admins == 0:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "No se puede quitar el rol de Administrador: "
                        "este es el único administrador activo del sistema."
                    ),
                )
        usuario.rol_id = datos.rol_id

    if datos.password is not None:
        validar_password(datos.password)
        usuario.password_hash = get_password_hash(datos.password)
        # Fuerza el aviso de cambio solo si el admin le puso la contraseña a otro usuario.
        usuario.debe_cambiar_password = (admin.id != usuario.id)

    usuario.updated_by = admin.id
    try:
        db.commit()
    except IntegrityError:
        # Carrera contra la restricción UNIQUE: responde amigable en vez de un 500.
        db.rollback()
        raise HTTPException(status_code=400, detail="Ya existe un usuario con ese nombre.")
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