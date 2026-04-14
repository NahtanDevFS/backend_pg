from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import models
from app.schemas import usuario as schemas
from app.core.security import get_password_hash

def crear_usuario(db: Session, usuario_in: schemas.UsuarioCreate):
    hashed_password = get_password_hash(usuario_in.password)

    nuevo_usuario = models.Usuario(
        rol_id=usuario_in.rol_id,
        nombre=usuario_in.nombre,
        password_hash=hashed_password
    )

    db.add(nuevo_usuario)
    db.commit()
    db.refresh(nuevo_usuario)

    return nuevo_usuario