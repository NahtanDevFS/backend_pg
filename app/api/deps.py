from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
import jwt
from sqlalchemy.orm import Session
from app.core.config import settings
from app.core.database import get_db
from app.models import models

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

ROL_ADMINISTRADOR = "Administrador"
ROL_OPERADOR = "Operador"


def obtener_usuario_actual(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db)
) -> models.Usuario:
    credenciales_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        usuario_id: str = payload.get("sub")
        if usuario_id is None:
            raise credenciales_exception
    except jwt.PyJWTError:
        raise credenciales_exception

    usuario = db.query(models.Usuario).filter(
        models.Usuario.id == int(usuario_id),
        models.Usuario.activo == True
    ).first()

    if usuario is None:
        raise credenciales_exception

    return usuario


def requiere_admin(usuario_actual: models.Usuario = Depends(obtener_usuario_actual)) -> models.Usuario:
    if usuario_actual.rol.nombre != ROL_ADMINISTRADOR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso restringido a administradores."
        )
    return usuario_actual


def requiere_operador(usuario_actual: models.Usuario = Depends(obtener_usuario_actual)) -> models.Usuario:
    if usuario_actual.rol.nombre not in (ROL_ADMINISTRADOR, ROL_OPERADOR):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acceso denegado."
        )
    return usuario_actual