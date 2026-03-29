from fastapi import APIRouter, Depends, status, UploadFile, File, Form, BackgroundTasks, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.database import get_db
from app.models.models import Usuario, Cultivo, ProcesamientoVideo
from app.schemas import procesamiento as schemas
from app.services import video_service
from app.api.deps import obtener_usuario_actual
from typing import List

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos de Video"])


@router.post("/", response_model=schemas.ProcesamientoResponse, status_code=status.HTTP_202_ACCEPTED)
def subir_y_procesar_video(
        background_tasks: BackgroundTasks,
        cultivo_id: int = Form(...),
        fecha_grabacion: datetime = Form(...),
        video: UploadFile = File(...),
        db: Session = Depends(get_db),
        usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    if not video.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un video.")

    cultivo = db.query(Cultivo).filter(Cultivo.id == cultivo_id, Cultivo.usuario_id == usuario_actual.id).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado o no tienes acceso.")

    nuevo_procesamiento = ProcesamientoVideo(
        cultivo_id=cultivo.id,
        usuario_id=usuario_actual.id,
        video_original_url="pendiente_de_guardar",
        fecha_grabacion=fecha_grabacion
    )
    db.add(nuevo_procesamiento)
    db.commit()
    db.refresh(nuevo_procesamiento)

    file_path = video_service.guardar_video_local(video, nuevo_procesamiento.id)

    nuevo_procesamiento.video_original_url = file_path
    db.commit()
    db.refresh(nuevo_procesamiento)

    background_tasks.add_task(video_service.tarea_procesar_video, nuevo_procesamiento.id, file_path)

    return nuevo_procesamiento

@router.get("/{procesamiento_id}", response_model=schemas.ProcesamientoResponse)
def obtener_estado_procesamiento(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    procesamiento = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.usuario_id == usuario_actual.id
    ).first()

    if not procesamiento:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    return procesamiento


@router.get("/cultivo/{cultivo_id}", response_model=List[schemas.ProcesamientoResponse])
def listar_historial_por_cultivo(
        cultivo_id: int,
        db: Session = Depends(get_db),
        usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == cultivo_id,
        Cultivo.usuario_id == usuario_actual.id
    ).first()

    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado o acceso denegado.")

    historial = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.cultivo_id == cultivo_id
    ).order_by(ProcesamientoVideo.fecha_grabacion.desc()).all()

    return historial