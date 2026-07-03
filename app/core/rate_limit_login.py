import logging
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# Reglas de bloqueo por intentos fallidos de login
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 30

# TTL del contador de intentos cuando aún no se alcanza el máximo, si el
# usuario deja de intentar, el contador se resetea solo pasado este tiempo
# en vez de acumularse indefinidamente. 5 minutos
TTL_CONTADOR_SEGUNDOS = 5 * 60

# Cliente Redis único por proceso, mismo patrón que app/core/progreso.py
# Si REDIS_URL no está configurada, el módulo se comporta como no-op:
# nunca bloquea (fail-open), para no dejar el login inutilizable si Redis cae
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


def _clave_intentos(identificador: str) -> str:
    return f"login_intentos:{identificador}"


def _clave_bloqueo(identificador: str) -> str:
    return f"login_bloqueo:{identificador}"


def verificar_bloqueo(identificador: str) -> Optional[int]:
    """Revisa si el identificador (usuario, o usuario+ip) está bloqueado.

    Devuelve los segundos restantes de bloqueo, o None si puede intentar.
    Fail-open: si Redis no está disponible, nunca bloquea.
    """
    if _cliente is None:
        return None
    try:
        ttl = _cliente.ttl(_clave_bloqueo(identificador))
        # ttl > 0 -> sigue bloqueado, -2 -> la clave no existe, -1 -> existe sin expiración (no debería pasar)
        if ttl and ttl > 0:
            return ttl
        return None
    except Exception as e:
        logger.warning("No se pudo verificar bloqueo de login para %s: %s", identificador, e)
        return None


def registrar_intento_fallido(identificador: str) -> Optional[int]:
    """Incrementa el contador de intentos fallidos. Al llegar a MAX_INTENTOS
    activa el bloqueo temporal y reinicia el contador. Best-effort: nunca lanza.

    Devuelve los intentos restantes antes del bloqueo (>= 0), o None si
    Redis no está disponible (en ese caso no se puede informar el conteo).
    """
    if _cliente is None:
        return None
    try:
        clave = _clave_intentos(identificador)
        intentos = _cliente.incr(clave)
        if intentos == 1:
            _cliente.expire(clave, TTL_CONTADOR_SEGUNDOS)

        if intentos >= MAX_INTENTOS:
            _cliente.set(_clave_bloqueo(identificador), "1", ex=BLOQUEO_SEGUNDOS)
            _cliente.delete(clave)
            return 0

        return MAX_INTENTOS - intentos
    except Exception as e:
        logger.warning("No se pudo registrar intento fallido de login para %s: %s", identificador, e)
        return None


def limpiar_intentos(identificador: str) -> None:
    """Se llama tras un login exitoso, borra contador y bloqueo si existieran.
    Best-effort: nunca lanza.
    """
    if _cliente is None:
        return
    try:
        _cliente.delete(_clave_intentos(identificador), _clave_bloqueo(identificador))
    except Exception as e:
        logger.warning("No se pudo limpiar intentos de login para %s: %s", identificador, e)