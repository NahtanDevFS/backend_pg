from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import models
from app.core.security import verify_password, crear_token_acceso
from app.core.rate_limit_login import (
    verificar_bloqueo,
    registrar_intento_fallido,
    limpiar_intentos,
    BLOQUEO_SEGUNDOS,
)

router = APIRouter(tags=["Autenticación"])

@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    # Identificador del rate limit: usuario normalizado. Así el bloqueo
    # protege esa cuenta sin importar desde qué IP vengan los intentos
    identificador = form_data.username.strip().lower()

    segundos_restantes = verificar_bloqueo(identificador)
    if segundos_restantes is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={
                "tipo": "bloqueado",
                "mensaje": (
                    "Demasiados intentos fallidos. "
                    f"Intenta de nuevo en {segundos_restantes} segundos."
                ),
                "segundos_restantes": segundos_restantes,
            },
            headers={"Retry-After": str(segundos_restantes)},
        )

    # Nota deliberada de seguridad: el mensaje de error es idéntico tanto si
    # el usuario no existe como si la contraseña es incorrecta, para no
    # revelar qué usuarios existen en el sistema (user enumeration). El
    # conteo de intentos se aplica igual en ambos casos.
    usuario = db.query(models.Usuario).filter(
        models.Usuario.nombre == form_data.username,
        models.Usuario.activo == True,
    ).first()

    credenciales_validas = usuario and verify_password(form_data.password, usuario.password_hash)

    if not credenciales_validas:
        intentos_restantes = registrar_intento_fallido(identificador)

        if intentos_restantes == 0:
            # Este intento fue el que activó el bloqueo
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "tipo": "bloqueado",
                    "mensaje": (
                        "Demasiados intentos fallidos. "
                        f"Intenta de nuevo en {BLOQUEO_SEGUNDOS} segundos."
                    ),
                    "segundos_restantes": BLOQUEO_SEGUNDOS,
                },
                headers={"Retry-After": str(BLOQUEO_SEGUNDOS)},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "tipo": "credenciales_invalidas",
                "mensaje": "Usuario o contraseña incorrectos",
                "intentos_restantes": intentos_restantes,  # None si Redis no disponible
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    limpiar_intentos(identificador)
    access_token = crear_token_acceso(data={"sub": str(usuario.id)})

    return {"access_token": access_token, "token_type": "bearer"}