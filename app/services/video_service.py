import os
import shutil
import os
import shutil
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models import models
from app.core.database import SessionLocal
from app.services.ia_service import ProcesadorVideoYOLO

os.makedirs(settings.STORAGE_PATH, exist_ok=True)


def guardar_video_local(file: UploadFile, procesamiento_id: int) -> str:

    file_extension = file.filename.split(".")[-1]
    nombre_archivo = f"{procesamiento_id}_original.{file_extension}"

    ruta_fisica = os.path.join(settings.STORAGE_PATH, nombre_archivo)

    with open(ruta_fisica, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return nombre_archivo


def obtener_ruta_fisica_video(nombre_archivo: str) -> str:
    return os.path.join(settings.STORAGE_PATH, nombre_archivo)


def tarea_procesar_video(procesamiento_id: int, nombre_archivo: str):
    db: Session = SessionLocal()

    try:
        procesamiento = db.query(models.ProcesamientoVideo).filter(
            models.ProcesamientoVideo.id == procesamiento_id).first()
        if not procesamiento:
            return

        procesamiento.estado = "procesando"
        db.commit()

        ruta_entrada = obtener_ruta_fisica_video(nombre_archivo)
        nombre_salida = f"{procesamiento_id}_anotado.mp4"
        ruta_salida = obtener_ruta_fisica_video(nombre_salida)

        ia = ProcesadorVideoYOLO()
        resultados = ia.procesar(video_entrada_path=ruta_entrada, video_salida_path=ruta_salida)

        procesamiento.video_anotado_url = nombre_salida
        procesamiento.estado = "completado"

        resultado_ia = models.ResultadoIA(
            procesamiento_id=procesamiento.id,
            conteo_maduros=resultados["maduros"],
            conteo_inmaduros=resultados["inmaduros"],
            tiempo_procesamiento_seg=resultados["tiempo_segundos"]
        )
        db.add(resultado_ia)
        db.commit()

    except Exception as e:
        print(f"Error procesando video {procesamiento_id}: {str(e)}")
        db.rollback()
        if procesamiento:
            procesamiento.estado = "error"
            db.commit()
    finally:
        db.close()