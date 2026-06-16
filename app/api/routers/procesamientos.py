from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks, Header, Request
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
from app.core.firma import validar_token_descarga
import secrets
from app.core.config import settings
from app.core import progreso

router = APIRouter(prefix="/procesamientos", tags=["Procesamientos"])


#Helpers

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
        porcentaje_ocluidos: float = Form(None),
        nivel_confiabilidad: str = Form(None),
        total_detecciones_brutas: int = Form(None),
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
        porcentaje_ocluidos=porcentaje_ocluidos,
        nivel_confiabilidad=nivel_confiabilidad,
        total_detecciones_brutas=total_detecciones_brutas,
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
    conteo = db.query(Conteo).filter(Conteo.id == proc.conteo_id).first()
    todos = db.query(ResultadoIa).join(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo.id,
        ProcesamientoVideo.activo == True,
    ).all()
    conteo.conteo_total_acumulado = sum(
        (r.conteo_ajustado if r.conteo_ajustado is not None else r.conteo_ia)
        for r in todos
    )
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


#debe ir antes de /{procesamiento_id} para que FastAPI no interprete "admin" como un entero procesamiento_id.

@router.get("/admin/conteo/{conteo_id}", response_model=List[ProcesamientoResponse])
def listar_por_conteo_admin(
    conteo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin),
):
    return db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True
    ).order_by(ProcesamientoVideo.created_at.desc()).all()


#Operador (rutas dinámicas /{procesamiento_id}) Deben ir despues de todas las rutas con segmentos literales

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