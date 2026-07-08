import hmac
import hashlib
import time
from app.core.config import settings


def generar_token_descarga(procesamiento_id: int, ttl_segundos: int = 900) -> str:
    # genera el token firmado para que Modal baje el video, formato {expira}.{firma} y dura ttl_segundos
    expira = int(time.time()) + ttl_segundos
    mensaje = f"{procesamiento_id}:{expira}"
    firma = hmac.new(
        settings.SECRET_KEY.encode(),
        mensaje.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{expira}.{firma}"


def validar_token_descarga(procesamiento_id: int, token: str) -> bool:
    # valida el token, solo pasa si la firma cuadra y todavia no expira
    try:
        expira_str, firma = token.split(".", 1)
        expira = int(expira_str)
    except (ValueError, AttributeError):
        return False

    # ya expiro?
    if time.time() > expira:
        return False

    # recalcula la firma esperada y compara en tiempo constante para no filtrar info por timing
    mensaje = f"{procesamiento_id}:{expira}"
    firma_esperada = hmac.new(
        settings.SECRET_KEY.encode(),
        mensaje.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(firma, firma_esperada)