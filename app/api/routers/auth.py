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
    MAX_INTENTOS_USUARIO,
    BLOQUEO_USUARIO_SEGUNDOS,
    MAX_INTENTOS_IP,
    BLOQUEO_IP_SEGUNDOS,
)

router = APIRouter(tags=["Autenticación"])


def _obtener_ip_cliente(request: Request) -> str:

    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        # X-Forwarded-For puede traer una cadena "cliente, proxy1, proxy2"
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "desconocida"


@router.post("/login")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    identificador_usuario = form_data.username.strip().lower()

    ip_cliente = _obtener_ip_cliente(request)

    bloqueo_usuario = verificar_bloqueo(identificador_usuario, namespace="usuario")
    bloqueo_ip = verificar_bloqueo(ip_cliente, namespace="ip")

    segundos_restantes = None
    if bloqueo_usuario is not None or bloqueo_ip is not None:
        segundos_restantes = max(bloqueo_usuario or 0, bloqueo_ip or 0)

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

    usuario = db.query(models.Usuario).filter(
        models.Usuario.nombre == form_data.username,
        models.Usuario.activo == True,
    ).first()

    credenciales_validas = usuario and verify_password(form_data.password, usuario.password_hash)

    if not credenciales_validas:
        intentos_restantes_usuario = registrar_intento_fallido(
            identificador_usuario,
            namespace="usuario",
            max_intentos=MAX_INTENTOS_USUARIO,
            bloqueo_segundos=BLOQUEO_USUARIO_SEGUNDOS,
        )
        registrar_intento_fallido(
            ip_cliente,
            namespace="ip",
            max_intentos=MAX_INTENTOS_IP,
            bloqueo_segundos=BLOQUEO_IP_SEGUNDOS,
        )

        if intentos_restantes_usuario == 0 or verificar_bloqueo(ip_cliente, namespace="ip") is not None:
            # Este intento activó el bloqueo (por cuenta o por IP)
            segundos = verificar_bloqueo(identificador_usuario, namespace="usuario") \
                or verificar_bloqueo(ip_cliente, namespace="ip") \
                or BLOQUEO_USUARIO_SEGUNDOS
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={
                    "tipo": "bloqueado",
                    "mensaje": (
                        "Demasiados intentos fallidos. "
                        f"Intenta de nuevo en {segundos} segundos."
                    ),
                    "segundos_restantes": segundos,
                },
                headers={"Retry-After": str(segundos)},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "tipo": "credenciales_invalidas",
                "mensaje": "Usuario o contraseña incorrectos",
                "intentos_restantes": intentos_restantes_usuario,
            },
            headers={"WWW-Authenticate": "Bearer"},
        )

    limpiar_intentos(identificador_usuario, namespace="usuario")
    limpiar_intentos(ip_cliente, namespace="ip")
    access_token = crear_token_acceso(data={"sub": str(usuario.id)})

    return {"access_token": access_token, "token_type": "bearer"}