from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import models
from app.schemas import usuario as schemas
from app.core.security import get_password_hash

def crear_usuario(db: Session, usuario_in: schemas.UsuarioCreate):
    usuario_existente = db.query(models.Usuario).filter(models.Usuario.email == usuario_in.email).first()
    if usuario_existente:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El email ya está registrado."
        )

    hashed_password = get_password_hash(usuario_in.password)

    nuevo_usuario = models.Usuario(
        nombre=usuario_in.nombre,
        email=usuario_in.email,
        password_hash=hashed_password
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    return nuevo_usuario