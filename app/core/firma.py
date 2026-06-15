import hmac
import hashlib
import time
from app.core.config import settings


def generar_token_descarga(procesamiento_id: int, ttl_segundos: int = 900) -> str:
    #Genera un token firmado para descargar el video original, válido por `ttl_segundos` (por defecto 15 min). Formato: {expira}.{firma}
    expira = int(time.time()) + ttl_segundos
    mensaje = f"{procesamiento_id}:{expira}"
    firma = hmac.new(
        settings.SECRET_KEY.encode(),
        mensaje.encode(),
        hashlib.sha256,
    ).hexdigest()
    return f"{expira}.{firma}"


def validar_token_descarga(procesamiento_id: int, token: str) -> bool:
    #Valida un token de descarga, devuelve True solo si la firma es correcta y el token no ha expirado
    try:
        expira_str, firma = token.split(".", 1)
        expira = int(expira_str)
    except (ValueError, AttributeError):
        return False

    # ¿Expiró?
    if time.time() > expira:
        return False

    # Recalcular la firma esperada y comparar en tiempo constante
    mensaje = f"{procesamiento_id}:{expira}"
    firma_esperada = hmac.new(
        settings.SECRET_KEY.encode(),
        mensaje.encode(),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(firma, firma_esperada)