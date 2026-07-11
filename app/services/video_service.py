import os
import asyncio
import base64
import httpx
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import ProcesamientoVideo, EstadoProcesamiento
from app.core.database import SessionLocal
from app.core.firma import generar_token_descarga

os.makedirs(settings.STORAGE_PATH, exist_ok=True)

# tamaño maximo del video: 10 GB
MAX_VIDEO_SIZE_BYTES = 10 * 1024 * 1024 * 1024

# de a cuanto leemos/escribimos al guardar: 1 MB
CHUNK_SIZE = 1024 * 1024

# extensiones que dejamos pasar
EXTENSIONES_PERMITIDAS = {"mp4", "mov", "avi", "mkv"}


def _validar_firma_video(primer_chunk: bytes, extension: str) -> bool:
    # revisa los magic bytes pa confirmar que de verdad es un video y no otra cosa con la extension cambiada
    if len(primer_chunk) < 12:
        return False
    if extension in ("mp4", "mov"):
        return primer_chunk[4:8] == b"ftyp"
    if extension == "avi":
        return primer_chunk[:4] == b"RIFF" and primer_chunk[8:12] == b"AVI "
    if extension == "mkv":
        return primer_chunk[:4] == b"\x1aE\xdf\xa3"
    return False


# subida de un solo golpe (legacy)
async def guardar_video_local(file: UploadFile, procesamiento_id: int) -> str:
    # guarda el video en disco validando extension, magic bytes y tamaño
    # el nombre lo arma el server con puros datos de aca pa que no metan path traversal
    nombre_original = file.filename or ""
    extension = (
        nombre_original.rsplit(".", 1)[-1].lower() if "." in nombre_original else ""
    )

    if extension not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no permitido. Extensiones válidas: {', '.join(sorted(EXTENSIONES_PERMITIDAS))}.",
        )

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


# subida por pedazos, se puede reanudar si se corta la conexion

def _dir_chunks(procesamiento_id: int) -> str:
    # carpeta temporal donde van cayendo los chunks del video
    d = os.path.join(settings.STORAGE_PATH, "chunks", str(procesamiento_id))
    os.makedirs(d, exist_ok=True)
    return d


def _ruta_chunk(procesamiento_id: int, numero: int) -> str:
    return os.path.join(_dir_chunks(procesamiento_id), f"{numero:06d}.bin")


def _ruta_meta(procesamiento_id: int) -> str:
    # archivito con la meta: extension y cuantos chunks esperamos
    return os.path.join(_dir_chunks(procesamiento_id), "meta.txt")


def guardar_meta_chunks(procesamiento_id: int, extension: str, total_chunks: int) -> None:
    with open(_ruta_meta(procesamiento_id), "w") as f:
        f.write(f"{extension}\n{total_chunks}\n")


def leer_meta_chunks(procesamiento_id: int) -> tuple[str, int] | None:
    ruta = _ruta_meta(procesamiento_id)
    if not os.path.exists(ruta):
        return None
    with open(ruta) as f:
        lines = f.read().splitlines()
    if len(lines) < 2:
        return None
    return lines[0], int(lines[1])


def bytes_recibidos(procesamiento_id: int) -> int:
    # suma el peso de todos los chunks que ya llegaron
    d = _dir_chunks(procesamiento_id)
    if not os.path.exists(d):
        return 0
    total = 0
    for fname in os.listdir(d):
        if fname.endswith(".bin"):
            total += os.path.getsize(os.path.join(d, fname))
    return total


def ultimo_chunk_recibido(procesamiento_id: int) -> int:
    # indice del ultimo chunk guardado (base 0), -1 si todavia no hay ninguno
    d = _dir_chunks(procesamiento_id)
    if not os.path.exists(d):
        return -1
    indices = []
    for fname in os.listdir(d):
        if fname.endswith(".bin"):
            try:
                indices.append(int(fname.replace(".bin", "")))
            except ValueError:
                pass
    return max(indices) if indices else -1


def guardar_chunk(procesamiento_id: int, numero: int, data: bytes) -> None:
    # guarda un chunk en disco, si ya existia lo pisa (idempotente pal retry)
    ruta = _ruta_chunk(procesamiento_id, numero)
    with open(ruta, "wb") as f:
        f.write(data)


def ensamblar_y_limpiar(procesamiento_id: int) -> str:
    # pega todos los chunks en el archivo final, lo valida, borra el temporal y devuelve el nombre
    meta = leer_meta_chunks(procesamiento_id)
    if meta is None:
        raise ValueError("No hay metadatos de chunks para este procesamiento.")
    extension, total_chunks = meta

    if extension not in EXTENSIONES_PERMITIDAS:
        raise ValueError(f"Extensión inválida: {extension}")

    nombre = f"{procesamiento_id}_original.{extension}"
    ruta_final = os.path.join(settings.STORAGE_PATH, nombre)

    with open(ruta_final, "wb") as f_out:
        for i in range(total_chunks):
            ruta_chunk = _ruta_chunk(procesamiento_id, i)
            if not os.path.exists(ruta_chunk):
                raise ValueError(f"Falta el chunk {i} de {total_chunks}.")
            with open(ruta_chunk, "rb") as f_in:
                f_out.write(f_in.read())

    # revisamos los magic bytes del archivo ya armado por si algun chunk vino chueco
    with open(ruta_final, "rb") as f:
        primer_bloque = f.read(12)
    if not _validar_firma_video(primer_bloque, extension):
        os.remove(ruta_final)
        raise ValueError("El archivo ensamblado no es un video válido.")

    # borra la carpeta de chunks, ya no se necesita
    import shutil
    shutil.rmtree(_dir_chunks(procesamiento_id), ignore_errors=True)

    return nombre


#Helpers compartidos

def obtener_ruta_fisica(nombre: str) -> str:
    return os.path.join(settings.STORAGE_PATH, nombre)


def _get_estado_id(db: Session, nombre: str) -> int:
    estado = db.query(EstadoProcesamiento).filter(EstadoProcesamiento.nombre == nombre).first()
    if not estado:
        raise Exception(f"Estado '{nombre}' no encontrado.")
    return estado.id


def tarea_procesar_video(procesamiento_id: int, nombre_archivo: str, usuario_id: int):
    # dispara el procesamiento en Modal (GPU remota) le pasamos una url firmada pa que Modal baje el video, el resultado cae despues por el callback, si el disparo falla dejamos el procesamiento en estado error
    db: Session = SessionLocal()
    procesamiento = None
    try:
        procesamiento = db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.id == procesamiento_id
        ).first()
        if not procesamiento:
            return

        token = generar_token_descarga(procesamiento_id)
        url_video = (
            f"{settings.PUBLIC_BASE_URL}/procesamientos/"
            f"{procesamiento_id}/video-original?token={token}"
        )

        payload = {
            "procesamiento_id": procesamiento_id,
            "url_video": url_video,
            "callback_base_url": settings.PUBLIC_BASE_URL,
            "trigger_secret": settings.MODAL_TRIGGER_SECRET,
        }

        resp = httpx.post(
            settings.MODAL_ENDPOINT_URL,
            json=payload,
            timeout=30.0,
        )
        resp.raise_for_status()

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