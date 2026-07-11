from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Header, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import os
import shutil
import base64
from app.core.database import get_db
from app.core.config import settings
from app.models.models import (
    Usuario, CampoCultivo, Conteo,
    ProcesamientoVideo, ResultadoIa, EstadoProcesamiento, CampoCultivoOperador, EstadoConteo
)
from app.schemas.procesamiento import ProcesamientoResponse, AjusteResultadoRequest
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador
from app.services import video_service
from app.core.firma import validar_token_descarga
import secrets
from app.core.config import settings
from app.core import progreso
# import lazy para no hacer ciclo: conteos -> procesamientos -> conteos
def _recalcular_clasificaciones_conteo(conteo_id: int, db) -> None:
    from app.api.routers.conteos import _recalcular_clasificaciones
    _recalcular_clasificaciones(conteo_id, db)

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos"])


#Helpers

def _get_procesamiento_del_usuario(procesamiento_id: int, usuario: Usuario, db: Session, incluir_inactivos: bool = False) -> ProcesamientoVideo:
    # trae el procesamiento chequeando que el operador tenga acceso; incluir_inactivos deja leer los cancelados
    q = db.query(ProcesamientoVideo).filter(ProcesamientoVideo.id == procesamiento_id)
    if not incluir_inactivos:
        q = q.filter(ProcesamientoVideo.activo == True)
    proc = q.first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    acceso = db.query(CampoCultivoOperador).join(Conteo, Conteo.campo_cultivo_id == CampoCultivoOperador.campo_cultivo_id).filter(
        Conteo.id == proc.conteo_id,
        CampoCultivoOperador.usuario_id == usuario.id,
        CampoCultivoOperador.activo == True,
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


def _recalcular_conteo(conteo_id: int, db: Session):
    # recalcula el acumulado y la confiabilidad del conteo a partir de sus videos activos se llama al cancelar/reactivar para que el video que sale (o entra) deje de contar (o vuelva a contar)
    conteo = db.query(Conteo).filter(Conteo.id == conteo_id).first()
    if not conteo:
        return
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True,
    ).all()
    conteo.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in todos
    )
    con_metricas = [
        r for r in todos
        if r.promedio_confianza is not None
        and r.porcentaje_baja_confianza is not None
        and r.total_frames_procesados
        and r.total_frames_procesados > 0
    ]
    total_frames = sum(r.total_frames_procesados for r in con_metricas)
    if total_frames > 0:
        conteo.promedio_confianza_sesion = round(
            sum(float(r.promedio_confianza) * r.total_frames_procesados for r in con_metricas) / total_frames, 4
        )
        conteo.porcentaje_baja_confianza_sesion = round(
            sum(float(r.porcentaje_baja_confianza) * r.total_frames_procesados for r in con_metricas) / total_frames, 4
        )
    else:
        conteo.promedio_confianza_sesion = None
        conteo.porcentaje_baja_confianza_sesion = None

    # si ya habia muestreo, recalcula la segmentacion por calibre
    _recalcular_clasificaciones_conteo(conteo_id, db)

#Operador (rutas con segmentos literales)

# aca cae el callback de Modal cuando termina de procesar, guarda el resultado y recalcula el conteo
@router.post("/{procesamiento_id}/resultado-ia")
def recibir_resultado_ia(
        procesamiento_id: int,
        x_modal_secret: str = Header(...),
        conteo_ia: int = Form(...),
        tiempo_procesamiento_seg: float = Form(None),
        total_frames_procesados: int = Form(None),
        promedio_confianza: float = Form(None),
        porcentaje_baja_confianza: float = Form(None),
        error_msg: str = Form(None),
        video_anotado: UploadFile = File(None),
        db: Session = Depends(get_db),
):
    # valida el secreto en tiempo constante, si no cuadra pa fuera
    if not secrets.compare_digest(x_modal_secret, settings.MODAL_CALLBACK_SECRET):
        raise HTTPException(status_code=403, detail="Secreto inválido.")

    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    # si ya tiene resultado lo ignoramos, es un callback repetido o un reintento
    if proc.resultado:
        progreso.limpiar_progreso(procesamiento_id)
        return {"detail": "Resultado ya registrado, callback ignorado."}

    # caso error: Modal manda conteo_ia negativo cuando algo trono alla
    if conteo_ia is not None and conteo_ia < 0:
        estado_error = db.query(EstadoProcesamiento).filter(
            EstadoProcesamiento.nombre == "error"
        ).first()
        if estado_error:
            proc.estado_id = estado_error.id
            db.commit()
        progreso.limpiar_progreso(procesamiento_id)
        return {"detail": f"Procesamiento marcado como error: {error_msg or 'desconocido'}"}

    # camino feliz, aca si o si tiene que venir el video anotado
    if video_anotado is None:
        raise HTTPException(
            status_code=400,
            detail="Falta el video anotado para un resultado exitoso.",
        )

    # guardamos el video anotado en disco, es livianito (720p)
    nombre_salida = f"{procesamiento_id}_anotado.mp4"
    ruta_salida = video_service.obtener_ruta_fisica(nombre_salida)
    try:
        # copyfileobj escribe por bloques desde el temporal de Starlette, como el endpoint es sync
        # esto corre en el threadpool y no traba el event loop
        with open(ruta_salida, "wb") as f:
            shutil.copyfileobj(video_anotado.file, f, 1024 * 1024)
    except Exception:
        estado_error = db.query(EstadoProcesamiento).filter(
            EstadoProcesamiento.nombre == "error"
        ).first()
        if estado_error:
            proc.estado_id = estado_error.id
            db.commit()
        progreso.limpiar_progreso(procesamiento_id)
        raise HTTPException(status_code=500, detail="No se pudo guardar el video anotado.")

    # guardamos el resultado de la IA
    resultado = ResultadoIa(
        procesamiento_id=proc.id,
        conteo_ia=conteo_ia,
        tiempo_procesamiento_seg=tiempo_procesamiento_seg,
        total_frames_procesados=total_frames_procesados,
        promedio_confianza=promedio_confianza,
        porcentaje_baja_confianza=porcentaje_baja_confianza,
        created_by=proc.created_by,
    )
    db.add(resultado)

    proc.video_anotado_url = nombre_salida
    estado_completado = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "completado"
    ).first()
    if not estado_completado:
        raise HTTPException(status_code=500, detail="Estado 'completado' no configurado.")
    proc.estado_id = estado_completado.id

    db.flush()

    # recalculamos el acumulado del conteo sumando todos sus videos activos (usa el ajustado si lo hay)
    conteo = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo.id,
        ProcesamientoVideo.activo == True,
    ).all()
    conteo.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in todos
    )

    # promedio de confianza de la sesion ponderado por frames, queda None si ningun video trae metricas
    con_metricas = [
        r for r in todos
        if r.promedio_confianza is not None
           and r.porcentaje_baja_confianza is not None
           and r.total_frames_procesados
           and r.total_frames_procesados > 0
    ]
    total_frames = sum(r.total_frames_procesados for r in con_metricas)
    if total_frames > 0:
        conteo.promedio_confianza_sesion = round(
            sum(float(r.promedio_confianza) * r.total_frames_procesados for r in con_metricas)
            / total_frames,
            4,
        )
        conteo.porcentaje_baja_confianza_sesion = round(
            sum(float(r.porcentaje_baja_confianza) * r.total_frames_procesados for r in con_metricas)
            / total_frames,
            4,
        )
    else:
        conteo.promedio_confianza_sesion = None
        conteo.porcentaje_baja_confianza_sesion = None

    # si ya habia muestreo, vuelve a repartir la segmentacion por calibre con el nuevo total
    _recalcular_clasificaciones_conteo(conteo.id, db)

    db.commit()

    # limpia el progreso efimero de redis
    progreso.limpiar_progreso(procesamiento_id)

    return {"detail": "Resultado registrado correctamente."}


@router.post("/{procesamiento_id}/progreso")
async def reportar_progreso(
        procesamiento_id: int,
        request: Request,
        x_modal_secret: str = Header(...),
):
    # recibe el progreso en vivo de Modal mientras procesa y lo mete a redis (efimero, best-effort)
    # body: {"progreso_pct": int, "conteo_parcial": int}

    # mismo secreto que el callback, validado en tiempo constante
    if not secrets.compare_digest(x_modal_secret, settings.MODAL_CALLBACK_SECRET):
        raise HTTPException(status_code=403, detail="Secreto inválido.")

    try:
        datos = await request.json()
        pct = int(datos.get("progreso_pct", 0))
        parcial = int(datos.get("conteo_parcial", 0))
    except Exception:
        # body chueco, lo ignoramos y ya, esto no es critico
        return {"detail": "Progreso ignorado (body inválido)."}

    # lo dejamos entre 0 y 99, el 100 lo pone el resultado final no el progreso
    pct = max(0, min(99, pct))

    progreso.set_progreso(procesamiento_id, pct, parcial)
    return {"detail": "Progreso registrado."}


@router.get("/{procesamiento_id}/progreso")
def consultar_progreso(
        procesamiento_id: int,
        db: Session = Depends(get_db),
        usuario: Usuario = Depends(requiere_operador),
):
    # devuelve el progreso en vivo para el polling de la app, ceros si todavia no hay nada en redis
    _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    datos = progreso.get_progreso(procesamiento_id)
    if not datos:
        return {"progreso_pct": 0, "conteo_parcial": 0, "disponible": False}

    return {
        "progreso_pct": datos.get("progreso_pct", 0),
        "conteo_parcial": datos.get("conteo_parcial", 0),
        "disponible": True,
    }


@router.get("/{procesamiento_id}/video-original")
def descargar_video_original(
    procesamiento_id: int,
    token: str,
    db: Session = Depends(get_db),
):
    # descarga el video original con el token firmado (lo usa Modal), no lleva auth de usuario porque el token es la credencial
    if not validar_token_descarga(procesamiento_id, token):
        raise HTTPException(status_code=403, detail="Token inválido o expirado.")

    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    # el original quedo como {id}_original.{ext}, probamos que extension existe
    ruta = None
    for ext in ("mp4", "mov", "avi", "mkv"):
        candidata = video_service.obtener_ruta_fisica(f"{procesamiento_id}_original.{ext}")
        if os.path.exists(candidata):
            ruta = candidata
            break

    if not ruta:
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado.")

    return FileResponse(ruta, media_type="application/octet-stream")

# registra el video sin el archivo todavia y devuelve el id de una vez, el video se sube despues
@router.post("/registrar", response_model=ProcesamientoResponse, status_code=201)
def registrar_procesamiento(
    conteo_id: int = Form(...),
    surco_inicio: int = Form(...),
    surco_fin: int = Form(...),
    fecha_grabacion: datetime = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario  = Depends(requiere_operador)
):
    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id, Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    acceso = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == conteo.campo_cultivo_id,
        CampoCultivoOperador.usuario_id == usuario.id,
        CampoCultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este campo de cultivo.")

    # validamos el rango aca tambien, el front ya valida pero no hay que confiarse: una llamada directa a la API podria meter rangos chuecos o solapados e inflar el conteo
    if surco_inicio < 1 or surco_fin < surco_inicio:
        raise HTTPException(
            status_code=400,
            detail="Rango de surcos inválido: el inicio debe ser >= 1 y el fin >= el inicio.",
        )
    if surco_fin > conteo.total_surcos:
        raise HTTPException(
            status_code=400,
            detail=(
                f"El surco final ({surco_fin}) supera el total de surcos del "
                f"conteo ({conteo.total_surcos})."
            ),
        )

    # ningun video activo del conteo puede pisar el mismo rango, cada surco se cuenta una sola vez
    conflicto = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True,
        ProcesamientoVideo.surco_inicio <= surco_fin,
        ProcesamientoVideo.surco_fin >= surco_inicio,
    ).first()
    if conflicto:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El rango de surcos {surco_inicio}–{surco_fin} se solapa con un "
                f"procesamiento activo existente (surcos {conflicto.surco_inicio}–{conflicto.surco_fin})."
            ),
        )

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


@router.get("/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_por_conteo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")

    acceso = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == conteo.campo_cultivo_id,
        CampoCultivoOperador.usuario_id == usuario.id,
        CampoCultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este campo de cultivo.")

    return db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True
    ).order_by(ProcesamientoVideo.created_at.desc()).all()


#esto va antes de /{procesamiento_id} pa que FastAPI no lea "admin" como si fuera un id

@router.get("/admin/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_por_conteo_admin(
    conteo_id: int,
    incluir_cancelados: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    # lista los videos del conteo, con incluir_cancelados tambien trae los anulados
    query = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id
    )
    if not incluir_cancelados:
        query = query.filter(ProcesamientoVideo.activo == True)
    return query.order_by(ProcesamientoVideo.created_at.desc()).all()


@router.patch("/admin/{procesamiento_id}/cancelar")
def cancelar_procesamiento_admin(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # el admin anula cualquier video (soft delete) sin importar en que estado este, y recalcula el conteo
    proc = _get_procesamiento_cualquiera(procesamiento_id, db)

    estado_cancelado = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "cancelado"
    ).first()
    if not estado_cancelado:
        raise HTTPException(status_code=500, detail="Estado 'cancelado' no configurado.")

    proc.estado_id = estado_cancelado.id
    proc.activo = False
    proc.updated_by = admin.id

    progreso.limpiar_progreso(procesamiento_id)

    # flush pa que el activo=False lo vea la query de _recalcular_conteo
    db.flush()

    _recalcular_conteo(proc.conteo_id, db)
    db.commit()

    return {"detail": "Procesamiento anulado correctamente."}


@router.patch("/admin/{procesamiento_id}/reactivar")
def reactivar_procesamiento_admin(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # reactiva un video anulado, tiene que tener resultado de IA y que su rango de surcos no choque con otro
    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == False,
    ).first()
    if not proc:
        raise HTTPException(
            status_code=404,
            detail="Procesamiento no encontrado o ya está activo."
        )

    if not proc.resultado:
        raise HTTPException(
            status_code=400,
            detail="Este procesamiento no tiene resultado de IA y no puede reactivarse como completado."
        )

    # revisa que ningun otro video activo del conteo pise el mismo rango de surcos
    conflicto = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == proc.conteo_id,
        ProcesamientoVideo.activo == True,
        ProcesamientoVideo.id != proc.id,
        ProcesamientoVideo.surco_inicio <= proc.surco_fin,
        ProcesamientoVideo.surco_fin >= proc.surco_inicio,
    ).first()
    if conflicto:
        raise HTTPException(
            status_code=409,
            detail=(
                f"Ya existe un procesamiento activo (surcos {conflicto.surco_inicio}–{conflicto.surco_fin}) "
                f"que solapa el rango de este procesamiento ({proc.surco_inicio}–{proc.surco_fin}). "
                "Cancela ese procesamiento primero."
            )
        )

    estado_completado = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "completado"
    ).first()
    if not estado_completado:
        raise HTTPException(status_code=500, detail="Estado 'completado' no configurado.")

    proc.estado_id = estado_completado.id
    proc.activo = True
    proc.updated_by = admin.id

    # flush pa que el activo=True lo vea la query de _recalcular_conteo
    db.flush()

    _recalcular_conteo(proc.conteo_id, db)
    db.commit()

    return {"detail": "Procesamiento reactivado correctamente."}

@router.get("/admin/{procesamiento_id}", response_model=ProcesamientoResponse)
def obtener_procesamiento_admin(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    # detalle de cualquier video, version admin sin chequear que el operador este asignado
    return _get_procesamiento_cualquiera(procesamiento_id, db)


@router.get(
    "/admin/{procesamiento_id}/video-anotado",
    summary="Descargar video etiquetado en 720p (admin)",
)
def descargar_video_anotado_admin(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    # descarga del video anotado, version admin, no pide estar asignado como operador
    proc = _get_procesamiento_cualquiera(procesamiento_id, db)

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

# rutas dinamicas /{procesamiento_id}, tienen que ir despues de todas las literales o FastAPI se confunde

@router.get("/{procesamiento_id}", response_model=ProcesamientoResponse)
def obtener_procesamiento(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    # incluir_inactivos=True pa poder ver el video aunque este cancelado
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db, incluir_inactivos=True)


@router.get("/{procesamiento_id}/estado", response_model=ProcesamientoResponse)
def consultar_estado(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    return _get_procesamiento_del_usuario(procesamiento_id, usuario, db, incluir_inactivos=True)


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


# subida clasica en un solo request (legacy), la app hoy usa la de chunks
@router.post("/{procesamiento_id}/video", response_model=ProcesamientoResponse)
async def subir_video(
    procesamiento_id: int,
    background_tasks: BackgroundTasks,
    video: UploadFile = File(...),
    db: Session  = Depends(get_db),
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
    if not estado_procesando:
        raise HTTPException(status_code=500, detail="Estado 'procesando' no configurado.")
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


class IniciarSubidaChunksRequest(BaseModel):
    extension: str
    total_chunks: int


@router.post("/{procesamiento_id}/video/iniciar-chunks", response_model=ProcesamientoResponse)
def iniciar_subida_chunks(
    procesamiento_id: int,
    datos: IniciarSubidaChunksRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    # guarda la meta de la subida por chunks (extension y total) antes de mandar el primer pedazo, es idempotente por si se reintenta
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    estado_pendiente = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "pendiente"
    ).first()
    if not estado_pendiente or proc.estado_id != estado_pendiente.id:
        raise HTTPException(
            status_code=400,
            detail="Este procesamiento no está en estado pendiente."
        )

    extension = datos.extension.lower().strip(".")
    if extension not in video_service.EXTENSIONES_PERMITIDAS:
        raise HTTPException(
            status_code=400,
            detail=f"Extensión no permitida. Válidas: {', '.join(sorted(video_service.EXTENSIONES_PERMITIDAS))}.",
        )
    if datos.total_chunks < 1 or datos.total_chunks > 5000:
        raise HTTPException(status_code=400, detail="total_chunks debe estar entre 1 y 5000.")

    video_service.guardar_meta_chunks(procesamiento_id, extension, datos.total_chunks)
    return proc


# recibe un pedazo del video en base64, y cuando llega el ultimo ensambla y dispara Modal
@router.post("/{procesamiento_id}/video/chunk")
async def subir_chunk(
    procesamiento_id: int,
    background_tasks: BackgroundTasks,
    numero: int = Form(...),
    data_b64: str = Form(...),
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    estado_pendiente = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "pendiente"
    ).first()
    estado_procesando = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "procesando"
    ).first()
    if not estado_pendiente or not estado_procesando:
        raise HTTPException(status_code=500, detail="Estados 'pendiente'/'procesando' no configurados.")

    if proc.estado_id not in (estado_pendiente.id, estado_procesando.id):
        print(f"[CHUNK {procesamiento_id}] FALLO estado: proc.estado_id={proc.estado_id} no es pendiente({estado_pendiente.id}) ni procesando({estado_procesando.id})")
        raise HTTPException(
            status_code=400,
            detail="Este procesamiento no acepta más chunks (estado no válido)."
        )

    # si ya esta en procesando con el video armado, es un chunk que llego tarde del retry, lo ignoramos
    if proc.estado_id == estado_procesando.id and proc.video_original_url and proc.video_original_url != "pendiente":
        print(f"[CHUNK {procesamiento_id}] chunk tardío numero={numero}, video ya ensamblado, respondiendo completo=True")
        return {"recibido": numero, "ultimo_recibido": -1, "total_chunks": -1, "completo": True}

    meta = video_service.leer_meta_chunks(procesamiento_id)
    if meta is None:
        # no hay meta pero el video ya esta armado, o sea el ensamblado ya paso, avisamos completo=True pa que el cliente pare
        if proc.video_original_url and proc.video_original_url != "pendiente":
            print(f"[CHUNK {procesamiento_id}] meta=None pero video ya ensamblado, respondiendo completo=True")
            return {"recibido": numero, "ultimo_recibido": -1, "total_chunks": -1, "completo": True}
        print(f"[CHUNK {procesamiento_id}] FALLO meta=None para chunk numero={numero}")
        raise HTTPException(
            status_code=400,
            detail="Primero llama a /iniciar-chunks para registrar la extensión y total de chunks."
        )
    extension, total_chunks = meta
    print(f"[CHUNK {procesamiento_id}] recibido numero={numero}, total_chunks={total_chunks}, len(data_b64)={len(data_b64)}")

    if numero < 0 or numero >= total_chunks:
        print(f"[CHUNK {procesamiento_id}] FALLO rango: numero={numero} fuera de 0-{total_chunks-1}")
        raise HTTPException(
            status_code=400,
            detail=f"Número de chunk inválido. Esperado 0–{total_chunks - 1}, recibido {numero}."
        )

    try:
        data = base64.b64decode(data_b64)
    except Exception:
        raise HTTPException(status_code=400, detail="El chunk no es base64 válido.")

    video_service.guardar_chunk(procesamiento_id, numero, data)
    print(f"[CHUNK {procesamiento_id}] guardado chunk {numero}, bytes_reales={len(data)}")

    ultimo = video_service.ultimo_chunk_recibido(procesamiento_id)
    print(f"[CHUNK {procesamiento_id}] ultimo_recibido={ultimo}, total_chunks={total_chunks}")
    if ultimo < total_chunks - 1:
        return {
            "recibido": numero,
            "ultimo_recibido": ultimo,
            "total_chunks": total_chunks,
            "completo": False,
        }

    # ya llegaron todos, a ensamblar el archivo final
    try:
        nombre_archivo = video_service.ensamblar_y_limpiar(procesamiento_id)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    proc.video_original_url = nombre_archivo
    proc.estado_id = estado_procesando.id
    db.commit()
    db.refresh(proc)

    background_tasks.add_task(
        video_service.tarea_procesar_video,
        proc.id,
        nombre_archivo,
        usuario.id,
    )

    return {
        "recibido": numero,
        "ultimo_recibido": ultimo,
        "total_chunks": total_chunks,
        "completo": True,
    }


@router.get("/{procesamiento_id}/video/estado-subida")
def estado_subida_chunks(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    # ultimo chunk recibido y bytes acumulados, el cliente lo usa pa reanudar una subida que se corto
    _get_procesamiento_del_usuario(procesamiento_id, usuario, db)
    return {
        "ultimo_chunk_recibido": video_service.ultimo_chunk_recibido(procesamiento_id),
        "bytes_recibidos": video_service.bytes_recibidos(procesamiento_id),
    }


@router.patch("/{procesamiento_id}/cancelar")
def cancelar_procesamiento(
    procesamiento_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    # el operador cancela un video suyo (soft delete), libera sus surcos y recalcula el conteo
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

    conteo = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    if conteo is not None:
        estado_conteo = db.query(EstadoConteo).filter(
            EstadoConteo.id == conteo.estado_id
        ).first()
        if estado_conteo and estado_conteo.nombre == "completado":
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se puede anular un procesamiento de un conteo ya completado. "
                    "Contacta a un administrador para reabrir el conteo si necesitas corregirlo."
                ),
            )

    estado_actual = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.id == proc.estado_id
    ).first()
    if estado_actual.nombre not in ("pendiente", "procesando", "completado"):
        raise HTTPException(
            status_code=400,
            detail="Solo se pueden cancelar procesamientos en estado pendiente, procesando o completado.",
        )

    estado_cancelado = db.query(EstadoProcesamiento).filter(
        EstadoProcesamiento.nombre == "cancelado"
    ).first()
    if not estado_cancelado:
        raise HTTPException(status_code=500, detail="Estado 'cancelado' no configurado.")

    proc.estado_id = estado_cancelado.id
    proc.activo = False
    proc.updated_by = usuario.id

    # limpia el progreso efimero si habia
    progreso.limpiar_progreso(procesamiento_id)

    # flush pa que el activo=False lo vea la query de _recalcular_conteo
    db.flush()

    # recalcula el conteo, el video cancelado ya no suma porque quedo en activo=False
    _recalcular_conteo(proc.conteo_id, db)
    db.commit()

    return {"detail": "Procesamiento cancelado correctamente."}

# el operador corrige a mano el conteo de la IA (por si hubo oclusiones) y recalcula el acumulado
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

    conteo_check = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    if conteo_check is not None:
        estado_conteo = db.query(EstadoConteo).filter(
            EstadoConteo.id == conteo_check.estado_id
        ).first()
        if estado_conteo and estado_conteo.nombre == "completado":
            raise HTTPException(
                status_code=400,
                detail=(
                    "No se puede ajustar un procesamiento de un conteo ya completado. "
                    "Contacta a un administrador para reabrir el conteo si necesitas corregirlo."
                ),
            )

    proc.resultado.conteo_ajustado = datos.conteo_ajustado
    proc.resultado.observaciones_ajuste = datos.observaciones
    proc.resultado.updated_by = usuario.id

    # recalcula el acumulado del conteo ya con el ajuste nuevo
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

    # si ya habia muestreo, recalcula la segmentacion por calibre con el total nuevo
    _recalcular_clasificaciones_conteo(conteo.id, db)

    db.commit()

    return {"detail": "Ajuste guardado correctamente."}