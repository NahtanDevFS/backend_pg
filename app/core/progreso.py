import json
import logging
from typing import Optional

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

# TTL del progreso en Redis, si por alguna razón nunca llega el callback final que limpia la clave, igual desaparece sola pasado este tiempo. Holgado para cubrir videos largos, 30 minutos
_TTL_SEGUNDOS = 30 * 60

# Cliente Redis único por proceso, decode_responses=True para trabajar con str en vez de bytes, si la URL no está configurada, queda None y todo el módulo se comporta como un no-op silencioso
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
        logger.warning("No se pudo inicializar el cliente Redis: %s", e)
        _cliente = None


def _clave(procesamiento_id: int) -> str:
    return f"progreso:procesamiento:{procesamiento_id}"


def set_progreso(procesamiento_id: int, progreso_pct: int, conteo_parcial: int) -> None:
    #Guarda el progreso actual. Best-effort: nunca lanza
    if _cliente is None:
        return
    try:
        valor = json.dumps(
            {"progreso_pct": progreso_pct, "conteo_parcial": conteo_parcial}
        )
        _cliente.set(_clave(procesamiento_id), valor, ex=_TTL_SEGUNDOS)
    except Exception as e:
        logger.warning(
            "No se pudo guardar progreso de %s en Redis: %s", procesamiento_id, e
        )


def get_progreso(procesamiento_id: int) -> Optional[dict]:
    #Lee el progreso actual. Devuelve None si no hay dato o Redis falla
    if _cliente is None:
        return None
    try:
        crudo = _cliente.get(_clave(procesamiento_id))
        if not crudo:
            return None
        return json.loads(crudo)
    except Exception as e:
        logger.warning(
            "No se pudo leer progreso de %s en Redis: %s", procesamiento_id, e
        )
        return None


def limpiar_progreso(procesamiento_id: int) -> None:
    #Borra el progreso. Se llama cuando llega el resultado final o un error. Best-effort: nunca lanza
    if _cliente is None:
        return
    try:
        _cliente.delete(_clave(procesamiento_id))
    except Exception as e:
        logger.warning(
            "No se pudo limpiar progreso de %s en Redis: %s", procesamiento_id, e
        )