from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.database import get_db
from app.models.models import (
    Usuario, Cultivo, Conteo,
    ProcesamientoVideo, ResultadoIa, EstadoProcesamiento
)
from app.schemas.procesamiento import ProcesamientoResponse, AjusteResultadoRequest
from app.api.deps import obtener_usuario_actual
from app.services import video_service

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos"])


def _get_procesamiento_del_usuario(procesamiento_id: int, usuario: Usuario, db: Session) -> ProcesamientoVideo:
    proc = db.query(ProcesamientoVideo).join(Conteo).join(Cultivo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        Cultivo.usuario_id == usuario.id,
        ProcesamientoVideo.activo == True
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")
    return proc


@router.post("/", response_model=ProcesamientoResponse, status_code=201)
def subir_video(
    background_tasks: BackgroundTasks,
    conteo_id:       int      = Form(...),
    surco_inicio:    int      = Form(...),
    surco_fin:       int      = Form(...),
    fecha_grabacion: datetime = Form(...),
    video: UploadFile         = File(...),
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(obtener_usuario_actual)
):
    conteo = db.query(Conteo).join(Cultivo).filter(
        Conteo.id == conteo_id,
        Cultivo.usuario_id == usuario.id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    estado_procesando = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "procesando"
    ).first()
    if not estado_procesando:
        raise HTTPException(status_code=500, detail="Estado 'procesando' no encontrado en catálogo.")

    nuevo = ProcesamientoVideo(
        conteo_id=conteo_id,
        usuario_id=usuario.id,
        surco_inicio=surco_inicio,
        surco_fin=surco_fin,
        fecha_grabacion=fecha_grabacion,
        estado_id=estado_procesando.id,
        video_original_url="procesando",  # se actualiza tras guardar el archivo
        created_by=usuario.id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)

    nombre_archivo = video_service.guardar_video_local(video, nuevo.id)

    # Actualizar la URL real del video original
    nuevo.video_original_url = nombre_archivo
    db.commit()
    db.refresh(nuevo)

    background_tasks.add_task(
        video_service.tarea_procesar_video,
        nuevo.id,
        nombre_archivo,
        usuario.id
    )

    return nuevo


@router.get("/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_procesamientos_por_conteo(
    conteo_id: int,
    db:        Session  = Depends(get_db),
    usuario:   Usuario  = Depends(obtener_usuario_actual)
):
    conteo = db.query(Conteo).join(Cultivo).filter(
        Conteo.id == conteo_id,
        Cultivo.usuario_id == usuario.id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    return db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True
    ).order_by(ProcesamientoVideo.created_at.desc()).all()


@router.get("/{procesamiento_id}", response_model=ProcesamientoResponse)
def obtener_procesamiento(
    procesamiento_id: int,
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(obtener_usuario_actual)
):
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db)


@router.get("/{procesamiento_id}/estado", response_model=ProcesamientoResponse)
def consultar_estado(
    procesamiento_id: int,
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(obtener_usuario_actual)
):
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db)


@router.post("/{procesamiento_id}/ajustar")
def ajustar_conteo(
    procesamiento_id: int,
    datos:   AjusteResultadoRequest,
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(obtener_usuario_actual)
):
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    if not proc.resultado:
        raise HTTPException(status_code=400, detail="Este procesamiento aún no tiene resultado de IA.")

    proc.resultado.conteo_ajustado      = datos.conteo_ajustado
    proc.resultado.observaciones_ajuste = datos.observaciones
    proc.resultado.updated_by           = usuario.id

    # Recalcular total acumulado del conteo
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == proc.conteo_id
    ).all()
    proc.conteo.conteo_total_acumulado = sum(
        r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia
        for r in todos
    )
    proc.conteo.updated_by = usuario.id
    db.commit()

    return {"mensaje": "Ajuste guardado correctamente."}