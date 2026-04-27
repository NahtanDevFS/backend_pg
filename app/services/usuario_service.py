from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models.models import Usuario
from app.schemas import usuario as schemas
from app.core.security import get_password_hash


def crear_usuario(db: Session, usuario_in: schemas.UsuarioCreate, creado_por: int) -> Usuario:
    existente = db.query(Usuario).filter(Usuario.nombre == usuario_in.nombre).first()
    if existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ya existe un usuario con ese nombre."
        )

    nuevo = Usuario(
        rol_id=usuario_in.rol_id,
        nombre=usuario_in.nombre,
        password_hash=get_password_hash(usuario_in.password),
        created_by=creado_por
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo