import os
import asyncio
import httpx
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import ProcesamientoVideo, EstadoProcesamiento
from app.core.database import SessionLocal
from app.core.firma import generar_token_descarga

os.makedirs(settings.STORAGE_PATH, exist_ok=True)

# Tamaño máximo permitido para el video 2 GB
MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024

# Tamaño del chunk de lectura/escritura: 1 MB
CHUNK_SIZE = 1024 * 1024

# Extensiones de video permitidas
EXTENSIONES_PERMITIDAS = {"mp4", "mov", "avi", "mkv"}


def _validar_firma_video(primer_chunk: bytes, extension: str) -> bool:
    """Verifica los magic bytes del archivo para confirmar que realmente
    es un video y no otro tipo de archivo renombrado."""
    if len(primer_chunk) < 12:
        return False
    if extension in ("mp4", "mov"):
        # Contenedor ISO BMFF: bytes 4-8 == 'ftyp'
        return primer_chunk[4:8] == b"ftyp"
    if extension == "avi":
        return primer_chunk[:4] == b"RIFF" and primer_chunk[8:12] == b"AVI "
    if extension == "mkv":
        return primer_chunk[:4] == b"\x1aE\xdf\xa3"
    return False


async def guardar_video_local(file: UploadFile, procesamiento_id: int) -> str:
    """Guarda el video en disco de forma asíncrona, chunk a chunk.
    Valida extensión (whitelist), firma del archivo (magic bytes) y
    tamaño máximo. El nombre final se construye SOLO con datos del
    servidor para impedir path traversal."""

    nombre_original = file.filename or ""
    extension = (
        nombre_original.rsplit(".", 1)[-1].lower() if "." in nombre_original else ""
    )

    if extension not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no permitido. Extensiones válidas: {', '.join(sorted(EXTENSIONES_PERMITIDAS))}.",
        )

    # Nombre construido únicamente con valores controlados por el servidor
    nombre = f"{procesamiento_id}_original.{extension}"
    ruta = os.path.join(settings.STORAGE_PATH, nombre)

    total_bytes = 0
    primer_chunk_validado = False
    loop = asyncio.get_event_loop()

    f_destino = await loop.run_in_executor(None, lambda: open(ruta, "wb"))

    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break

            if not primer_chunk_validado:
                if not _validar_firma_video(chunk, extension):
                    raise HTTPException(
                        status_code=400,
                        detail="El archivo no parece ser un video válido.",
                    )
                primer_chunk_validado = True

            total_bytes += len(chunk)
            if total_bytes > MAX_VIDEO_SIZE_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail=f"El video supera el tamaño máximo permitido de "
                    f"{MAX_VIDEO_SIZE_BYTES // (1024**3)} GB.",
                )

            await loop.run_in_executor(None, f_destino.write, chunk)
    except HTTPException:
        await loop.run_in_executor(None, f_destino.close)
        if os.path.exists(ruta):
            os.remove(ruta)
        raise
    finally:
        if not f_destino.closed:
            await loop.run_in_executor(None, f_destino.close)

    return nombre


def obtener_ruta_fisica(nombre: str) -> str:
    return os.path.join(settings.STORAGE_PATH, nombre)


def _get_estado_id(db: Session, nombre: str) -> int:
    estado = db.query(EstadoProcesamiento).filter(EstadoProcesamiento.nombre == nombre).first()
    if not estado:
        raise Exception(f"Estado '{nombre}' no encontrado.")
    return estado.id


def tarea_procesar_video(procesamiento_id: int, nombre_archivo: str, usuario_id: int):
    """Dispara el procesamiento en Modal (GPU remota). NO procesa localmente.
    Genera una URL firmada (TTL corto) para que Modal descargue el video
    original e invoca el endpoint de Modal. El resultado llega después por
    callback a POST /procesamientos/{id}/resultado-ia.
    El estado ya viene en 'procesando' desde el endpoint subir_video."""
    db: Session = SessionLocal()
    procesamiento = None
    try:
        procesamiento = db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.id == procesamiento_id
        ).first()
        if not procesamiento:
            return

        # URL firmada (TTL 15 min) para que Modal descargue el original
        token = generar_token_descarga(procesamiento_id)
        url_video = (
            f"{settings.PUBLIC_BASE_URL}/procesamientos/"
            f"{procesamiento_id}/video-original?token={token}"
        )
        #print(f"[DEBUG] url_video -> {url_video}")

        payload = {
            "procesamiento_id": procesamiento_id,
            "url_video": url_video,
            "callback_base_url": settings.PUBLIC_BASE_URL,
            "trigger_secret": settings.MODAL_CALLBACK_SECRET,
        }
        #headers = {"X-Modal-Trigger-Secret": settings.MODAL_CALLBACK_SECRET}

        resp = httpx.post(
            settings.MODAL_ENDPOINT_URL,
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()
        # Modal aceptó el trabajo. El resultado llegará por callback.

    except Exception as e:
        print(f"Error al disparar Modal para {procesamiento_id}: {e}")
        db.rollback()
        if procesamiento:
            try:
                estado_error = db.query(EstadoProcesamiento).filter(
                    EstadoProcesamiento.nombre == "error"
                ).first()
                if estado_error:
                    procesamiento.estado_id = estado_error.id
                    procesamiento.updated_by = usuario_id
                    db.commit()
            except Exception:
                pass
    finally:
        db.close()