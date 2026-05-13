from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from datetime import datetime
import os
from app.core.database import get_db
from app.core.config import settings
from app.models.models import (
    Usuario, Cultivo, Conteo,
    ProcesamientoVideo, ResultadoIa, EstadoProcesamiento, CultivoOperador
)
from app.schemas.procesamiento import ProcesamientoResponse, AjusteResultadoRequest
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador
from app.services import video_service

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos"])


#helpers

def _get_procesamiento_del_usuario(procesamiento_id: int, usuario: Usuario, db: Session) -> ProcesamientoVideo:
    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    acceso = db.query(CultivoOperador).join(Conteo, Conteo.cultivo_id == CultivoOperador.cultivo_id).filter(
        Conteo.id == proc.conteo_id,
        CultivoOperador.usuario_id == usuario.id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este procesamiento.")
    return proc


def _get_procesamiento_cualquiera(procesamiento_id: int, db: Session) -> ProcesamientoVideo:
    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")
    return proc


#operador

@router.post("/registrar", response_model=ProcesamientoResponse, status_code=201)
def registrar_procesamiento(
    conteo_id:       int      = Form(...),
    surco_inicio:    int      = Form(...),
    surco_fin:       int      = Form(...),
    fecha_grabacion: datetime = Form(...),
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(requiere_operador)
):
    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id, Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    acceso = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == conteo.cultivo_id,
        CultivoOperador.usuario_id == usuario.id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cultivo.")

    estado_pendiente = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "pendiente"
    ).first()
    if not estado_pendiente:
        raise HTTPException(status_code=500, detail="Estado 'pendiente' no configurado.")

    nuevo = ProcesamientoVideo(
        conteo_id=conteo_id,
        usuario_id=usuario.id,
        surco_inicio=surco_inicio,
        surco_fin=surco_fin,
        fecha_grabacion=fecha_grabacion,
        estado_id=estado_pendiente.id,
        video_original_url="pendiente",
        created_by=usuario.id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


#recibe el archivo y lanza la IA
@router.post("/{procesamiento_id}/video", response_model=ProcesamientoResponse)
async def subir_video(
    procesamiento_id: int,
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    db:      Session  = Depends(get_db),
    usuario: Usuario  = Depends(requiere_operador)
):
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    estado_pendiente = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "pendiente"
    ).first()
    if not estado_pendiente or proc.estado_id != estado_pendiente.id:
        raise HTTPException(status_code=400, detail="Este procesamiento no está en estado pendiente.")

    nombre_archivo = await video_service.guardar_video_local(video, proc.id)

    estado_procesando = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "procesando"
    ).first()
    proc.video_original_url = nombre_archivo
    proc.estado_id = estado_procesando.id
    db.commit()
    db.refresh(proc)

    background_tasks.add_task(
        video_service.tarea_procesar_video,
        proc.id,
        nombre_archivo,
        usuario.id
    )
    return proc


@router.get("/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_por_conteo(
    conteo_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    acceso = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == conteo.cultivo_id,
        CultivoOperador.usuario_id == usuario.id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cultivo.")

    return db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True
    ).order_by(ProcesamientoVideo.created_at.desc()).all()


@router.get("/{procesamiento_id}", response_model=ProcesamientoResponse)
def obtener_procesamiento(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db)


@router.get("/{procesamiento_id}/estado", response_model=ProcesamientoResponse)
def consultar_estado(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db)


@router.get(
    "/{procesamiento_id}/video-anotado",
    summary="Descargar video etiquetado en 720p (operador autenticado)",
)
def descargar_video_anotado(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    if not proc.video_anotado_url:
        raise HTTPException(
            status_code=404,
            detail="El video anotado aún no está disponible. El procesamiento puede estar en curso.",
        )

    ruta = video_service.obtener_ruta_fisica(proc.video_anotado_url)
    if not os.path.exists(ruta):
        raise HTTPException(
            status_code=404,
            detail="El archivo de video no se encontró en el servidor.",
        )

    nombre_descarga = (
        f"conteo_{proc.conteo_id}_surcos_{proc.surco_inicio}-{proc.surco_fin}_anotado.mp4"
    )
    return FileResponse(path=ruta, media_type="video/mp4", filename=nombre_descarga)


@router.post("/{procesamiento_id}/ajustar")
def ajustar_conteo(
    procesamiento_id: int,
    datos:   AjusteResultadoRequest,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    if not proc.resultado:
        raise HTTPException(status_code=400, detail="Este procesamiento aún no tiene resultado de IA.")

    proc.resultado.conteo_ajustado = datos.conteo_ajustado
    proc.resultado.observaciones_ajuste = datos.observaciones
    proc.resultado.updated_by = usuario.id

    # Recalcular total acumulado del conteo
    conteo = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo.id,
        ProcesamientoVideo.activo == True,
    ).all()
    conteo.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in todos
    )
    conteo.updated_by = usuario.id
    db.commit()

    return {"detail": "Ajuste guardado correctamente."}