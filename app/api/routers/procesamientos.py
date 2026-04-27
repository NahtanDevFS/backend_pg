from typing import List
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, BackgroundTasks
from sqlalchemy.orm import Session
from datetime import datetime
from app.core.database import get_db
from app.models.models import Usuario, SesionConteo, Cultivo, ProcesamientoVideo, ResultadoIa, ClasificacionCalibre, EstadoProcesamiento
from app.schemas import procesamiento as schemas
from app.services import video_service
from app.api.deps import obtener_usuario_actual

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos de Video"])


def _get_estado_id(db: Session, nombre: str) -> int:
    estado = db.query(EstadoProcesamiento).filter(EstadoProcesamiento.nombre == nombre).first()
    if not estado:
        raise HTTPException(status_code=500, detail=f"Estado '{nombre}' no encontrado en catálogo.")
    return estado.id


@router.post("/", response_model=schemas.ProcesamientoResponse, status_code=status.HTTP_202_ACCEPTED)
def subir_y_procesar_video(
    background_tasks: BackgroundTasks,
    sesion_id:       int      = Form(...),
    surco_inicio:    int      = Form(...),
    surco_fin:       int      = Form(...),
    fecha_grabacion: datetime = Form(...),
    video:           UploadFile = File(...),
    db:              Session  = Depends(get_db),
    usuario_actual:  Usuario  = Depends(obtener_usuario_actual)
):
    if not video.content_type.startswith("video/"):
        raise HTTPException(status_code=400, detail="El archivo debe ser un video.")

    if surco_fin < surco_inicio:
        raise HTTPException(status_code=400, detail="surco_fin debe ser mayor o igual a surco_inicio.")

    # Verificar que la sesión pertenece al usuario
    sesion = db.query(SesionConteo).join(Cultivo).filter(
        SesionConteo.id == sesion_id,
        Cultivo.usuario_id == usuario_actual.id,
        SesionConteo.activo == True
    ).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o sin acceso.")

    estado_id = _get_estado_id(db, "procesando")

    nuevo_procesamiento = ProcesamientoVideo(
        sesion_id=sesion_id,
        usuario_id=usuario_actual.id,
        estado_id=estado_id,
        surco_inicio=surco_inicio,
        surco_fin=surco_fin,
        video_original_url="pendiente",
        fecha_grabacion=fecha_grabacion,
        created_by=usuario_actual.id
    )
    db.add(nuevo_procesamiento)
    db.commit()
    db.refresh(nuevo_procesamiento)

    file_path = video_service.guardar_video_local(video, nuevo_procesamiento.id)
    nuevo_procesamiento.video_original_url = file_path
    db.commit()
    db.refresh(nuevo_procesamiento)

    background_tasks.add_task(
        video_service.tarea_procesar_video,
        nuevo_procesamiento.id,
        file_path,
        usuario_actual.id
    )

    return nuevo_procesamiento


@router.get("/{procesamiento_id}", response_model=schemas.ProcesamientoResponse)
def obtener_procesamiento(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    procesamiento = db.query(ProcesamientoVideo).join(SesionConteo).join(Cultivo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        Cultivo.usuario_id == usuario_actual.id
    ).first()
    if not procesamiento:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")
    return procesamiento


@router.get("/sesion/{sesion_id}", response_model=List[schemas.ProcesamientoResponse])
def listar_por_sesion(
    sesion_id: int,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    sesion = db.query(SesionConteo).join(Cultivo).filter(
        SesionConteo.id == sesion_id,
        Cultivo.usuario_id == usuario_actual.id
    ).first()
    if not sesion:
        raise HTTPException(status_code=404, detail="Sesión no encontrada o sin acceso.")

    return db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.sesion_id == sesion_id,
        ProcesamientoVideo.activo == True
    ).order_by(ProcesamientoVideo.surco_inicio).all()


@router.post("/{procesamiento_id}/ajustar-resultado")
def ajustar_resultado(
    procesamiento_id: int,
    datos: schemas.AjusteResultadoRequest,
    db: Session = Depends(get_db),
    usuario_actual: Usuario = Depends(obtener_usuario_actual)
):
    resultado = db.query(ResultadoIa).filter(
        ResultadoIa.procesamiento_id == procesamiento_id
    ).first()
    if not resultado:
        raise HTTPException(status_code=404, detail="Resultado de IA no encontrado.")

    # Validar suma de porcentajes si se enviaron calibres
    if datos.calibres:
        total_pct = sum(c.porcentaje for c in datos.calibres)
        if abs(total_pct - 100) > 0.01:
            raise HTTPException(status_code=400, detail=f"La suma de porcentajes debe ser 100%. Suma actual: {total_pct}%")

    resultado.conteo_ajustado = datos.conteo_ajustado
    resultado.observaciones_ajuste = datos.observaciones
    resultado.updated_by = usuario_actual.id

    # Reemplazar clasificaciones anteriores
    db.query(ClasificacionCalibre).filter(
        ClasificacionCalibre.resultado_id == resultado.id
    ).delete()

    conteo_base = datos.conteo_ajustado
    for item in datos.calibres:
        cantidad = round(conteo_base * item.porcentaje / 100)
        db.add(ClasificacionCalibre(
            resultado_id=resultado.id,
            calibre_id=item.calibre_id,
            porcentaje=item.porcentaje,
            cantidad_melones=cantidad,
            created_by=usuario_actual.id
        ))

    # Actualizar el total acumulado de la sesión
    procesamiento = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id
    ).first()
    sesion = db.query(SesionConteo).filter(
        SesionConteo.id == procesamiento.sesion_id
    ).first()

    total = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.sesion_id == sesion.id
    ).all()

    sesion.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in total
    )
    sesion.updated_by = usuario_actual.id

    db.commit()
    return {"mensaje": "Resultado ajustado y calibres registrados correctamente."}