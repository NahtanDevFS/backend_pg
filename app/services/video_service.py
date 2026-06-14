import os
import shutil
import asyncio
from fastapi import UploadFile, HTTPException
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import ProcesamientoVideo, ResultadoIa, EstadoProcesamiento, Conteo
from app.core.database import SessionLocal
from app.services.ia_service import ProcesadorVideoYOLO

os.makedirs(settings.STORAGE_PATH, exist_ok=True)

# Tamaño máximo permitido para el video 2 GB
MAX_VIDEO_SIZE_BYTES = 2 * 1024 * 1024 * 1024

# Tamaño del chunk de lectura/escritura: 1 MB
CHUNK_SIZE = 1024 * 1024

EXTENSIONES_PERMITIDAS = {"mp4", "mov", "avi", "mkv"}



async def guardar_video_local(file: UploadFile, procesamiento_id: int) -> str:
    #Guarda el video en disco de forma asíncrona, chunk a chunk, sin bloquear el event loop de uvicorn, valida que el archivo no supere MAX_VIDEO_SIZE_BYTES.

    extension = file.filename.split(".")[-1].lower()
    nombre = f"{procesamiento_id}_original.{extension}"
    ruta = os.path.join(settings.STORAGE_PATH, nombre)

    total_bytes = 0
    loop = asyncio.get_event_loop()

    f_destino = await loop.run_in_executor(None, lambda: open(ruta, "wb"))

    try:
        while True:
            chunk = await file.read(CHUNK_SIZE)
            if not chunk:
                break

            total_bytes += len(chunk)
            if total_bytes > MAX_VIDEO_SIZE_BYTES:
                f_destino.close()
                if os.path.exists(ruta):
                    os.remove(ruta)
                raise ValueError(
                    f"El video supera el tamaño máximo permitido de "
                    f"{MAX_VIDEO_SIZE_BYTES // (1024**3)} GB."
                )

            await loop.run_in_executor(None, f_destino.write, chunk)
    finally:
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
    db: Session = SessionLocal()
    procesamiento = None

    try:
        procesamiento = db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.id == procesamiento_id
        ).first()
        if not procesamiento:
            return

        procesamiento.estado_id = _get_estado_id(db, "procesando")
        db.commit()

        ruta_entrada = obtener_ruta_fisica(nombre_archivo)
        nombre_salida = f"{procesamiento_id}_anotado.mp4"
        ruta_salida = obtener_ruta_fisica(nombre_salida)

        ia = ProcesadorVideoYOLO()
        resultados = ia.procesar(video_entrada_path=ruta_entrada, video_salida_path=ruta_salida)

        procesamiento.video_anotado_url = nombre_salida
        procesamiento.estado_id = _get_estado_id(db, "completado")
        procesamiento.updated_by = usuario_id

        resultado = ResultadoIa(
            procesamiento_id=procesamiento.id,
            conteo_ia=resultados["total"],
            tiempo_procesamiento_seg=resultados["tiempo_segundos"],
            total_frames_procesados=resultados["frames_procesados"],
            created_by=usuario_id,
        )
        db.add(resultado)
        db.flush()

        conteo = db.query(Conteo).filter(Conteo.id == procesamiento.conteo_id).first()
        todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
            ProcesamientoVideo.conteo_id == conteo.id
        ).all()
        conteo.conteo_total_acumulado = sum(
            (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
            for r in todos
        )
        conteo.updated_by = usuario_id
        db.commit()

    except Exception as e:
        print(f"Error procesando video {procesamiento_id}: {e}")
        db.rollback()
        if procesamiento:
            try:
                procesamiento.estado_id = _get_estado_id(db, "error")
                procesamiento.updated_by = usuario_id
                db.commit()
            except Exception:
                pass
    finally:
        db.close()