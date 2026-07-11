import logging
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# bloqueo temporal de login contra fuerza bruta, cuenta intentos fallidos por usuario y por IP en redis, si no hay redis esto no hace nada y el login funciona normal
MAX_INTENTOS_USUARIO = 5
BLOQUEO_USUARIO_SEGUNDOS = 30

MAX_INTENTOS_IP = 10
BLOQUEO_IP_SEGUNDOS = 60

TTL_CONTADOR_SEGUNDOS = 5 * 60

_cliente: Optional[redis.Redis] = None

if settings.REDIS_URL:
    try:
        _cliente = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
    except Exception as e:  # pragma: no cover
        logger.warning("No se pudo inicializar el cliente Redis (rate limit login): %s", e)
        _cliente = None


def _clave_intentos(namespace: str, identificador: str) -> str:
    return f"login_intentos:{namespace}:{identificador}"


def _clave_bloqueo(namespace: str, identificador: str) -> str:
    return f"login_bloqueo:{namespace}:{identificador}"


def verificar_bloqueo(
    identificador: str, namespace: str = "usuario"
) -> Optional[int]:
    # devuelve cuantos segundos le quedan de bloqueo, o None si no esta bloqueado
    if _cliente is None:
        return None
    try:
        ttl = _cliente.ttl(_clave_bloqueo(namespace, identificador))
        if ttl and ttl > 0:
            return ttl
        return None
    except Exception as e:
        logger.warning(
            "No se pudo verificar bloqueo de login (%s) para %s: %s",
            namespace, identificador, e,
        )
        return None


def registrar_intento_fallido(
    identificador: str,
    namespace: str = "usuario",
    max_intentos: int = MAX_INTENTOS_USUARIO,
    bloqueo_segundos: int = BLOQUEO_USUARIO_SEGUNDOS,
) -> Optional[int]:
    # suma un intento fallido y bloquea si se paso del maximo, devuelve cuantos intentos quedan (0 = ya bloqueado)
    if _cliente is None:
        return None
    try:
        clave = _clave_intentos(namespace, identificador)
        intentos = _cliente.incr(clave)
        if intentos == 1:
            _cliente.expire(clave, TTL_CONTADOR_SEGUNDOS)

        if intentos >= max_intentos:
            _cliente.set(_clave_bloqueo(namespace, identificador), "1", ex=bloqueo_segundos)
            _cliente.delete(clave)
            return 0

        return max_intentos - intentos
    except Exception as e:
        logger.warning(
            "No se pudo registrar intento fallido de login (%s) para %s: %s",
            namespace, identificador, e,
        )
        return None


def limpiar_intentos(identificador: str, namespace: str = "usuario") -> None:
    # borra el contador y el bloqueo, se llama cuando el login salio bien
    if _cliente is None:
        return
    try:
        _cliente.delete(
            _clave_intentos(namespace, identificador),
            _clave_bloqueo(namespace, identificador),
        )
    except Exception as e:
        logger.warning(
            "No se pudo limpiar intentos de login (%s) para %s: %s",
            namespace, identificador, e,
        )