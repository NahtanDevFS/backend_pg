import os
import shutil
from fastapi import UploadFile
from sqlalchemy.orm import Session
from app.core.config import settings
from app.models.models import ProcesamientoVideo, ResultadoIa, EstadoProcesamiento, Conteo
from app.core.database import SessionLocal
from app.services.ia_service import ProcesadorVideoYOLO

os.makedirs(settings.STORAGE_PATH, exist_ok=True)


def guardar_video_local(file: UploadFile, procesamiento_id: int) -> str:
    extension = file.filename.split(".")[-1]
    nombre = f"{procesamiento_id}_original.{extension}"
    ruta = os.path.join(settings.STORAGE_PATH, nombre)
    with open(ruta, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
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
            created_by=usuario_id
        )
        db.add(resultado)
        db.flush()

        # Actualizar total acumulado del conteo
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