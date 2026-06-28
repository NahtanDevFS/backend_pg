from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Header, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime
import os
import base64
from app.core.database import get_db
from app.core.config import settings
from app.models.models import (
    Usuario, CampoCultivo, Conteo,
    ProcesamientoVideo, ResultadoIa, EstadoProcesamiento, CampoCultivoOperador
)
from app.schemas.procesamiento import ProcesamientoResponse, AjusteResultadoRequest
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador
from app.services import video_service
from app.core.firma import validar_token_descarga
import secrets
from app.core.config import settings
from app.core import progreso

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos"])


#Helpers

def _get_procesamiento_del_usuario(procesamiento_id: int, usuario: Usuario, db: Session, incluir_inactivos: bool = False) -> ProcesamientoVideo:
    #incluir_inactivos=True permite leer procesamientos cancelados (activo=False), necesario para que la pantalla pueda mostrar el estado 'cancelado'. Las acciones (subir, ajustar) lo dejan en False para no operar sobre cancelados.
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
    #Recalcula el acumulado y los agregados de confiabilidad de un conteo a partir de sus procesamientos activos. Se usa al cancelar un procesamiento para que el video excluido deje de contar.
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

#Operador (rutas con segmentos literales)

@router.post("/{procesamiento_id}/resultado-ia")
async def recibir_resultado_ia(
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
    # Validación del secreto en tiempo constante
    if not secrets.compare_digest(x_modal_secret, settings.MODAL_CALLBACK_SECRET):
        raise HTTPException(status_code=403, detail="Secreto inválido.")

    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    # Si ya tiene resultado, ignoramos (callback duplicado / reintento)
    if proc.resultado:
        progreso.limpiar_progreso(procesamiento_id)
        return {"detail": "Resultado ya registrado, callback ignorado."}

    #caso de error: Modal manda conteo_ia negativo
    if conteo_ia is not None and conteo_ia < 0:
        estado_error = db.query(EstadoProcesamiento).filter(
            EstadoProcesamiento.nombre == "error"
        ).first()
        if estado_error:
            proc.estado_id = estado_error.id
            db.commit()
        progreso.limpiar_progreso(procesamiento_id)
        return {"detail": f"Procesamiento marcado como error: {error_msg or 'desconocido'}"}

    #camino feliz: tiene que venir el video anotado
    if video_anotado is None:
        raise HTTPException(
            status_code=400,
            detail="Falta el video anotado para un resultado exitoso.",
        )

    # Guardar el video anotado en disco (es liviano, 720p)
    nombre_salida = f"{procesamiento_id}_anotado.mp4"
    ruta_salida = video_service.obtener_ruta_fisica(nombre_salida)
    try:
        with open(ruta_salida, "wb") as f:
            while True:
                chunk = await video_anotado.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
    except Exception:
        estado_error = db.query(EstadoProcesamiento).filter(
            EstadoProcesamiento.nombre == "error"
        ).first()
        if estado_error:
            proc.estado_id = estado_error.id
            db.commit()
        progreso.limpiar_progreso(procesamiento_id)
        raise HTTPException(status_code=500, detail="No se pudo guardar el video anotado.")

    # Escribir el resultado de IA
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
    proc.estado_id = estado_completado.id

    db.flush()

    # Recalcular el acumulado del conteo
    # Recalcular el acumulado del conteo
    conteo = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo.id,
        ProcesamientoVideo.activo == True,
    ).all()
    conteo.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in todos
    )

    # Recalcular agregados de confiabilidad de la sesión, ponderados por
    # total_frames_procesados. Solo se consideran los videos que tienen
    # métricas y frames (> 0); los videos sin detecciones no arrastran el
    # promedio. Si ningún video tiene métricas, los agregados quedan en None.
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

    db.commit()

    # Limpiar el progreso efímero
    progreso.limpiar_progreso(procesamiento_id)

    return {"detail": "Resultado registrado correctamente."}


@router.post("/{procesamiento_id}/progreso")
async def reportar_progreso(
        procesamiento_id: int,
        request: Request,
        x_modal_secret: str = Header(...),
):
    #Recibe el progreso en vivo desde Modal mientras procesa el video, autenticado con el mismo secreto compartido que el callback de resultado, solo escribe en Redis (efímero), no toca la base de datos. Es best-effort: si algo falla, devuelve 200 igual para no entorpecer el procesamiento
    #Body JSON esperado: {"progreso_pct": int, "conteo_parcial": int}

    # Validación del secreto en tiempo constante
    if not secrets.compare_digest(x_modal_secret, settings.MODAL_CALLBACK_SECRET):
        raise HTTPException(status_code=403, detail="Secreto inválido.")

    try:
        datos = await request.json()
        pct = int(datos.get("progreso_pct", 0))
        parcial = int(datos.get("conteo_parcial", 0))
    except Exception:
        # Body malformado: lo ignoramos sin romper nada
        return {"detail": "Progreso ignorado (body inválido)."}

    # Acotar el porcentaje a [0, 99]. El 100 lo da el resultado final, no el progreso, para evitar mostrar "100%" antes de que exista el resultado.
    pct = max(0, min(99, pct))

    progreso.set_progreso(procesamiento_id, pct, parcial)
    return {"detail": "Progreso registrado."}


@router.get("/{procesamiento_id}/progreso")
def consultar_progreso(
        procesamiento_id: int,
        db: Session = Depends(get_db),
        usuario: Usuario = Depends(requiere_operador),
):
    #Devuelve el progreso en vivo para que la app móvil lo muestre, lo consulta el polling de la pantalla de procesamiento. Si no hay progreso en Redis (aún no empieza, ya terminó, o Redis no está disponible), devuelve valores en cero: la UI simplemente mostrará el spinner sin barra.

    # Verifica acceso del usuario a este procesamiento (reutiliza el helper)
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
    #Descarga del video original mediante token firmado de un solo uso,lo consume Modal para procesar el video con GPU. No requiere auth de usuario: el token HMAC firmado es la credencial. TTL corto (15 min)

    if not validar_token_descarga(procesamiento_id, token):
        raise HTTPException(status_code=403, detail="Token inválido o expirado.")

    proc = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.id == procesamiento_id,
        ProcesamientoVideo.activo == True,
    ).first()
    if not proc:
        raise HTTPException(status_code=404, detail="Procesamiento no encontrado.")

    # El original se guardó como {id}_original.{ext}, busca el archivo real.
    ruta = None
    for ext in ("mp4", "mov", "avi", "mkv"):
        candidata = video_service.obtener_ruta_fisica(f"{procesamiento_id}_original.{ext}")
        if os.path.exists(candidata):
            ruta = candidata
            break

    if not ruta:
        raise HTTPException(status_code=404, detail="Archivo de video no encontrado.")

    return FileResponse(ruta, media_type="application/octet-stream")

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
    db:      Session = Depends(get_db),
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


#debe ir antes de /{procesamiento_id} para que FastAPI no interprete "admin" como un entero procesamiento_id.

@router.get("/admin/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_por_conteo_admin(
    conteo_id: int,
    incluir_cancelados: bool = False,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    #Lista los procesamientos de un conteo. Por defecto solo activos (activo=True).
    #Con ?incluir_cancelados=true devuelve también los cancelados (activo=False).
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
    #Cancela/anula cualquier procesamiento (soft delete), sin restricción de estado. Pensado para corregir equivocaciones, incluso sobre procesamientos ya 'completado'. Lo marca como 'cancelado' + activo=False y recalcula el conteo.
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

    # Flush para que activo=False sea visible para la query de _recalcular_conteo
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
    #Reactiva un procesamiento previamente cancelado, marcándolo de nuevo como 'completado' + activo=True.
    #Solo funciona si el procesamiento tiene resultado de IA (estaba completado antes de cancelarse).
    #Valida que no haya otro procesamiento activo que solape el mismo rango de surcos en el mismo conteo.
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

    #Verificar conflicto de surcos: ningún otro procesamiento activo del mismo conteo puede solapar el rango
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

    # Flush para que activo=True sea visible para la query de _recalcular_conteo
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
    #Versión admin de obtener_procesamiento: sin restricción de operador asignado.
    #La web administrativa la usa para ver el detalle de cualquier procesamiento.
    #incluir_inactivos via _get_procesamiento_cualquiera (muestra cancelados).
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
    #Versión admin de la descarga del video anotado, sin requerir asignación
    #como operador. Usada por la web administrativa.
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

#Operador (rutas dinámicas /{procesamiento_id}) Deben ir despues de todas las rutas con segmentos literales

@router.get("/{procesamiento_id}", response_model=ProcesamientoResponse)
def obtener_procesamiento(
    procesamiento_id: int,
    db:      Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador),
):
    # incluir_inactivos=True: permite ver el procesamiento aunque esté cancelado
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
    #Registra los metadatos de la subida por chunks (extensión y total de chunks).
    #Debe llamarse antes de enviar el primer chunk. Idempotente: si se llama de nuevo
    #con los mismos datos, simplemente sobreescribe la meta (útil para reintentos).
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

    if proc.estado_id not in (estado_pendiente.id, estado_procesando.id):
        print(f"[CHUNK {procesamiento_id}] FALLO estado: proc.estado_id={proc.estado_id} no es pendiente({estado_pendiente.id}) ni procesando({estado_procesando.id})")
        raise HTTPException(
            status_code=400,
            detail="Este procesamiento no acepta más chunks (estado no válido)."
        )

    # Si ya está en procesando con video ensamblado, es un chunk tardío del retry — ignorar
    if proc.estado_id == estado_procesando.id and proc.video_original_url and proc.video_original_url != "pendiente":
        print(f"[CHUNK {procesamiento_id}] chunk tardío numero={numero}, video ya ensamblado, respondiendo completo=True")
        return {"recibido": numero, "ultimo_recibido": -1, "total_chunks": -1, "completo": True}

    meta = video_service.leer_meta_chunks(procesamiento_id)
    if meta is None:
        # Si no hay meta pero el video ya está ensamblado (video_original_url != "pendiente"),
        # el ensamblado ya ocurrió — responder con completo=True para que el cliente pare.
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

    #Todos los chunks llegaron, entonces ensamblar
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
    #Devuelve el índice del último chunk recibido y los bytes acumulados
    #El cliente lo usa para reanudar una subida interrumpida sin repetir chunks ya enviados
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
    #Cancela un procesamiento propio (soft delete). Permitido en estados 'pendiente', 'procesando' y 'completado'
    #Marca como 'cancelado' + activo=False, libera el rango de surcos y excluye el video del acumulado del conteo
    proc = _get_procesamiento_del_usuario(procesamiento_id, usuario, db)

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

    # Limpiar progreso efímero si lo hubiera
    progreso.limpiar_progreso(procesamiento_id)

    # Flush para que activo=False sea visible para la query de _recalcular_conteo
    db.flush()

    # Recalcular el conteo (el video cancelado ya no cuenta por activo=False)
    _recalcular_conteo(proc.conteo_id, db)
    db.commit()

    return {"detail": "Procesamiento cancelado correctamente."}

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