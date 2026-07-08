from sqlalchemy import func
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status
from app.models.models import Usuario
from app.schemas import usuario as schemas
from app.core.security import get_password_hash, validar_password


def crear_usuario(db: Session, usuario_in: schemas.UsuarioCreate, creado_por: int) -> Usuario:
    # Normaliza y verifica el nombre case-insensitive (consistente con el login).
    nombre = usuario_in.nombre.strip()
    if not nombre:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El nombre de usuario no puede estar vacío."
        )

    existente = db.query(Usuario).filter(
        func.lower(Usuario.nombre) == nombre.lower()
    ).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese nombre."
        )

    validar_password(usuario_in.password)

    nuevo = Usuario(
        rol_id=usuario_in.rol_id,
        nombre=nombre,
        password_hash=get_password_hash(usuario_in.password),
        debe_cambiar_password=True,  # contraseña puesta por el admin
        created_by=creado_por
    )
    db.add(nuevo)
    try:
        db.commit()
    except IntegrityError:
        # Carrera contra la restricción UNIQUE: responde amigable en vez de un 500.
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese nombre."
        )
    db.refresh(nuevo)
    return nuevo