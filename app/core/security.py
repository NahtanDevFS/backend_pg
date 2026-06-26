import bcrypt
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException, status
from app.core.config import settings

LONGITUD_MINIMA_PASSWORD = 6

def validar_password(password: str) -> None:
    #Valida la fortaleza mínima de una contraseña. Se usa en todos los puntos
    #donde se establece una contraseña (crear, editar, cambiar la propia) para
    #que la regla sea consistente. Lanza HTTP 400 si no cumple.
    if password is None or len(password) < LONGITUD_MINIMA_PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"La contraseña debe tener al menos {LONGITUD_MINIMA_PASSWORD} caracteres.",
        )

def get_password_hash(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(pwd_bytes, salt)
    return hashed_password.decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    password_byte_enc = plain_password.encode('utf-8')
    hashed_password_byte_enc = hashed_password.encode('utf-8')

    return bcrypt.checkpw(password_byte_enc, hashed_password_byte_enc)


def crear_token_acceso(data: dict) -> str:
    to_encode = data.copy()

    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})

    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
    return encoded_jwt