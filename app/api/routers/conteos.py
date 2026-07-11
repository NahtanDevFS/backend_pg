from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, CampoCultivo, Conteo, EstadoConteo, ClasificacionCalibreConteo, CalibreMelon, CampoCultivoOperador
from app.schemas.conteo import ConteoCreate, ConteoResponse, ComparacionAnteriorResponse, HistorialPaginadoResponse, CambiarEstadoConteoRequest
from app.schemas.muestreo import MuestreoRequest, MuestreoResponse, ClasificacionResponse
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador


router = APIRouter(prefix="/conteos", tags=["Conteos"])


# helpers

def _get_conteo_del_usuario(conteo_id: int, usuario: Usuario, db: Session) -> Conteo:
    # trae el conteo chequeando que el operador tenga acceso a ese campo de cultivo
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
        raise HTTPException(status_code=403, detail="No tienes acceso a este conteo.")
    return conteo


def _get_conteo_cualquiera(conteo_id: int, db: Session, incluir_inactivos: bool = False) -> Conteo:
    #Devuelve cualquier conteo (uso admin), incluir_inactivos permite leer los desactivados
    q = db.query(Conteo).filter(Conteo.id == conteo_id)
    if not incluir_inactivos:
        q = q.filter(Conteo.activo == True)
    conteo = q.first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")
    return conteo


def _recalcular_clasificaciones(conteo_id: int, db: Session) -> None:
    # vuelve a repartir las cantidades extrapoladas por calibre cuando cambia el total del conteo, no hace commit, de eso se encarga quien lo llama
    clasificaciones = db.query(ClasificacionCalibreConteo).filter(
        ClasificacionCalibreConteo.conteo_id == conteo_id,
        ClasificacionCalibreConteo.activo == True,
    ).all()

    if not clasificaciones:
        return  # si no hubo muestreo, no hay nada que recalcular

    conteo = db.query(Conteo).filter(Conteo.id == conteo_id).first()
    if not conteo:
        return

    total_acumulado = conteo.conteo_total_acumulado
    total_muestreo = clasificaciones[0].total_muestreo  # invariante: igual para todas

    if total_muestreo == 0:
        return

    if total_acumulado == 0:
        for c in clasificaciones:
            c.cantidad_extrapolada = 0
        return

    # mismo metodo Hamilton de guardar_muestreo: primero la parte entera, luego reparte las faltantes por residuo mayor
    calculos = []
    for c in clasificaciones:
        ideal = c.cantidad_muestreo / total_muestreo * total_acumulado
        base = int(ideal)
        residuo = ideal - base
        calculos.append({"obj": c, "base": base, "residuo": residuo})

    suma_base = sum(x["base"] for x in calculos)
    faltantes = total_acumulado - suma_base

    orden = sorted(
        calculos,
        key=lambda x: (x["residuo"], x["obj"].cantidad_muestreo),
        reverse=True,
    )
    for i in range(max(0, min(faltantes, len(orden)))):
        orden[i]["base"] += 1

    for x in calculos:
        x["obj"].cantidad_extrapolada = x["base"]
        x["obj"].porcentaje = round(x["obj"].cantidad_muestreo / total_muestreo * 100, 2)


def _build_muestreo_response(conteo: Conteo, db: Session) -> MuestreoResponse:
    clasificaciones = db.query(ClasificacionCalibreConteo).join(CalibreMelon).filter(
        ClasificacionCalibreConteo.conteo_id == conteo.id,
        ClasificacionCalibreConteo.activo == True
    ).order_by(CalibreMelon.orden).all()

    total_muestreo = clasificaciones[0].total_muestreo if clasificaciones else 0

    return MuestreoResponse(
        total_muestreo=total_muestreo,
        conteo_total_acumulado=conteo.conteo_total_acumulado,
        clasificaciones=[
            ClasificacionResponse(
                id=c.id,
                calibre_id=c.calibre_id,
                nombre_calibre=c.calibre.nombre,
                orden_calibre=c.calibre.orden,
                cantidad_muestreo=c.cantidad_muestreo,
                total_muestreo=c.total_muestreo,
                porcentaje=float(c.porcentaje),
                cantidad_extrapolada=c.cantidad_extrapolada
            ) for c in clasificaciones
        ]
    )


# operador

@router.post("/", response_model=ConteoResponse, status_code=status.HTTP_201_CREATED)
def crear_conteo(
    conteo_in: ConteoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    cultivo = db.query(CampoCultivo).filter(
        CampoCultivo.id == conteo_in.campo_cultivo_id,
        CampoCultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Campo de cultivo no encontrado.")

    acceso = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == cultivo.id,
        CampoCultivoOperador.usuario_id == usuario.id,
        CampoCultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este campo de cultivo.")

    estado_inicial = db.query(EstadoConteo).filter(EstadoConteo.nombre == "en_progreso").first()
    if not estado_inicial:
        raise HTTPException(status_code=500, detail="Estado 'en_progreso' no encontrado en catálogo.")

    nuevo = Conteo(
        campo_cultivo_id=conteo_in.campo_cultivo_id,
        variedad_id=conteo_in.variedad_id,
        estado_id=estado_inicial.id,
        fecha_conteo=conteo_in.fecha_conteo,
        observaciones=conteo_in.observaciones,
        total_surcos=cultivo.total_surcos,
        created_by=usuario.id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("/cultivo/{cultivo_id}", response_model=List[ConteoResponse])
def listar_conteos_por_cultivo(
    cultivo_id:  int,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    estado: Optional[str]  = None,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    cultivo = db.query(CampoCultivo).filter(
        CampoCultivo.id == cultivo_id,
        CampoCultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Campo de cultivo no encontrado.")

    acceso = db.query(CampoCultivoOperador).filter(
        CampoCultivoOperador.campo_cultivo_id == cultivo_id,
        CampoCultivoOperador.usuario_id == usuario.id,
        CampoCultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este campo de cultivo.")

    query = db.query(Conteo).filter(
        Conteo.campo_cultivo_id == cultivo_id,
        Conteo.activo == True
    )
    if fecha_desde:
        query = query.filter(Conteo.fecha_conteo >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Conteo.fecha_conteo <= fecha_hasta)
    if estado:
        est = db.query(EstadoConteo).filter(EstadoConteo.nombre == estado).first()
        if est:
            query = query.filter(Conteo.estado_id == est.id)

    return query.order_by(Conteo.fecha_conteo.desc(), Conteo.id.desc()).offset(skip).limit(limit).all()


# estas rutas van antes de /{conteo_id} o FastAPI lee "admin" como si fuera un id

@router.get(
    "/admin/historial",
    response_model=HistorialPaginadoResponse,
    summary="Historial global de conteos paginado (solo Administrador)"
)
def historial_global(
    cultivo_id: Optional[int]  = None,
    usuario_id: Optional[int]  = None,
    fecha_desde: Optional[date] = None,
    fecha_hasta: Optional[date] = None,
    incluir_inactivos: bool = False,
    skip: int = 0,
    limit: int = 20,
    db: Session = Depends(get_db),
    _: Usuario  = Depends(requiere_admin)
):
    # historial global de conteos paginado, con filtros opcionales, esto lo usa la web del admin
    query = db.query(Conteo)
    if not incluir_inactivos:
        query = query.filter(Conteo.activo == True)

    if cultivo_id:
        query = query.filter(Conteo.campo_cultivo_id == cultivo_id)
    if usuario_id:
        query = query.filter(Conteo.created_by == usuario_id)
    if fecha_desde:
        query = query.filter(Conteo.fecha_conteo >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Conteo.fecha_conteo <= fecha_hasta)

    total = query.count()
    items = (
        query.order_by(Conteo.fecha_conteo.desc(), Conteo.id.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )
    return {"items": items, "total": total}


@router.get(
    "/admin/{conteo_id}",
    response_model=ConteoResponse,
    summary="Detalle de cualquier conteo (solo Administrador)"
)
def obtener_conteo_admin(
    conteo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    # incluir_inactivos=True pa que el admin pueda ver el detalle aunque el conteo este desactivado
    return _get_conteo_cualquiera(conteo_id, db, incluir_inactivos=True)


@router.get(
    "/admin/{conteo_id}/muestreo",
    response_model=MuestreoResponse,
    summary="Muestreo de cualquier conteo (solo Administrador)"
)
def obtener_muestreo_admin(
    conteo_id: int,
    db: Session = Depends(get_db),
    _: Usuario = Depends(requiere_admin)
):
    conteo = _get_conteo_cualquiera(conteo_id, db, incluir_inactivos=True)
    return _build_muestreo_response(conteo, db)


@router.patch("/admin/{conteo_id}/desactivar", response_model=ConteoResponse)
def desactivar_conteo_admin(
    conteo_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # baja logica del conteo y en cascada baja tambien sus videos y clasificaciones que esten activos
    from app.models.models import ProcesamientoVideo, ClasificacionCalibreConteo

    conteo = _get_conteo_cualquiera(conteo_id, db)  # solo activos

    # los videos activos del conteo
    procs = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.activo == True,
    ).all()
    proc_ids = [p.id for p in procs]

    if proc_ids:
        db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.id.in_(proc_ids),
        ).update(
            {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
            synchronize_session=False,
        )

    # las clasificaciones de calibre activas
    db.query(ClasificacionCalibreConteo).filter(
        ClasificacionCalibreConteo.conteo_id == conteo_id,
        ClasificacionCalibreConteo.activo == True,
    ).update(
        {"activo": False, "desactivado_por_campo_cultivo": True, "updated_by": admin.id},
        synchronize_session=False,
    )

    conteo.activo = False
    conteo.desactivado_por_campo_cultivo = False  # lo bajaron directo, no por la cascada de un campo
    conteo.updated_by = admin.id
    db.commit()
    db.refresh(conteo)
    return conteo


@router.patch("/admin/{conteo_id}/reactivar", response_model=ConteoResponse)
def reactivar_conteo_admin(
    conteo_id: int,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # reactiva un conteo que se bajo directo, y de paso revive lo que se apago junto con el
    from app.models.models import ProcesamientoVideo, ClasificacionCalibreConteo

    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id,
        Conteo.activo == False,
        Conteo.desactivado_por_campo_cultivo == False,  # solo los que se bajaron directo, no por la cascada del campo
    ).first()
    if not conteo:
        raise HTTPException(
            status_code=404,
            detail="Conteo no encontrado, ya está activo, o fue desactivado por la cascada del campo de cultivo."
        )

    # revivimos solo los videos que se apagaron por esta cascada (los que quedaron marcados con el flag)
    procs = db.query(ProcesamientoVideo).filter(
        ProcesamientoVideo.conteo_id == conteo_id,
        ProcesamientoVideo.desactivado_por_campo_cultivo == True,
    ).all()
    proc_ids = [p.id for p in procs]

    if proc_ids:
        db.query(ProcesamientoVideo).filter(
            ProcesamientoVideo.id.in_(proc_ids),
        ).update(
            {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
            synchronize_session=False,
        )

    # y las clasificaciones de calibre igual
    db.query(ClasificacionCalibreConteo).filter(
        ClasificacionCalibreConteo.conteo_id == conteo_id,
        ClasificacionCalibreConteo.desactivado_por_campo_cultivo == True,
    ).update(
        {"activo": True, "desactivado_por_campo_cultivo": False, "updated_by": admin.id},
        synchronize_session=False,
    )

    conteo.activo = True
    conteo.updated_by = admin.id
    db.commit()
    db.refresh(conteo)
    return conteo

@router.get("/{conteo_id}", response_model=ConteoResponse)
def obtener_conteo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    return _get_conteo_del_usuario(conteo_id, usuario, db)


@router.patch("/{conteo_id}/completar")
def completar_conteo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)

    # no se puede completar un conteo si todavia no tiene ni un video procesado
    if conteo.conteo_total_acumulado == 0:
        raise HTTPException(
            status_code=400,
            detail="No se puede completar: el conteo aún no tiene videos procesados.",
        )

    estado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    if not estado:
        raise HTTPException(status_code=500, detail="Estado 'completado' no configurado.")
    conteo.estado_id = estado.id
    conteo.updated_by = usuario.id
    db.commit()
    return {"mensaje": "Conteo marcado como completado."}


@router.patch("/admin/{conteo_id}/estado", response_model=ConteoResponse)
def cambiar_estado_conteo_admin(
    conteo_id: int,
    datos: CambiarEstadoConteoRequest,
    db: Session = Depends(get_db),
    admin: Usuario = Depends(requiere_admin),
):
    # el admin mueve el conteo a cualquier estado a mano, por ej pa reabrir uno ya completado si hubo un error
    conteo = _get_conteo_cualquiera(conteo_id, db)

    estado = db.query(EstadoConteo).filter(
        EstadoConteo.id == datos.estado_id,
        EstadoConteo.activo == True,
    ).first()
    if not estado:
        raise HTTPException(status_code=404, detail="El estado indicado no existe.")

    conteo.estado_id = estado.id
    conteo.updated_by = admin.id
    db.commit()
    db.refresh(conteo)
    return conteo


@router.get(
    "/{conteo_id}/comparacion-anterior",
    response_model=ComparacionAnteriorResponse
)
def comparar_con_anterior(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    #Devuelve el conteo completado anterior del mismo campo y la variación porcentual
    conteo_actual = _get_conteo_del_usuario(conteo_id, usuario, db)

    if conteo_actual.conteo_total_acumulado == 0:
        return ComparacionAnteriorResponse(hay_historial=False)

    estado_completado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    if not estado_completado:
        return ComparacionAnteriorResponse(hay_historial=False)

    anterior = db.query(Conteo).filter(
        Conteo.campo_cultivo_id == conteo_actual.campo_cultivo_id,
        Conteo.id < conteo_id,  # anterior = creado antes, mismo día o no
        Conteo.estado_id == estado_completado.id,
        Conteo.activo == True,
    ).order_by(Conteo.id.desc()).first()

    if not anterior or anterior.conteo_total_acumulado == 0:
        return ComparacionAnteriorResponse(hay_historial=False)

    variacion = round(
        (conteo_actual.conteo_total_acumulado - anterior.conteo_total_acumulado)
        / anterior.conteo_total_acumulado * 100,
        2
    )

    return ComparacionAnteriorResponse(
        conteo_anterior_id=anterior.id,
        conteo_anterior_total=anterior.conteo_total_acumulado,
        conteo_anterior_fecha=anterior.fecha_conteo,
        variacion_porcentual=variacion,
        hay_historial=True
    )


@router.post("/{conteo_id}/muestreo", response_model=MuestreoResponse)
def guardar_muestreo(
    conteo_id: int,
    datos: MuestreoRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)

    if conteo.conteo_total_acumulado == 0:
        raise HTTPException(status_code=400, detail="El conteo aún no tiene videos procesados.")

    suma = sum(i.cantidad_muestreo for i in datos.items)
    if suma != datos.total_muestreo:
        raise HTTPException(
            status_code=400,
            detail=f"La suma de cantidades por calibre ({suma}) debe ser igual al total del muestreo ({datos.total_muestreo})."
        )

    total_acumulado = conteo.conteo_total_acumulado

    # repartimos con el metodo del residuo mayor (Hamilton) pa que la suma de los extrapolados cuadre exacto con el total, si redondeamos cada calibre por separado la suma no da, por eso este metodo
    calculos = []
    for item in datos.items:
        calibre = db.query(CalibreMelon).filter(CalibreMelon.id == item.calibre_id).first()
        if not calibre:
            raise HTTPException(status_code=404, detail=f"Calibre {item.calibre_id} no encontrado.")
        # porcentaje real del muestreo, es dato medido asi que se guarda tal cual
        porcentaje = round(item.cantidad_muestreo / datos.total_muestreo * 100, 2)
        # cantidad ideal con decimales, escalada al total del conteo
        ideal = item.cantidad_muestreo / datos.total_muestreo * total_acumulado
        base = int(ideal)  # la parte entera
        residuo = ideal - base  # la parte decimal, la usamos pa desempatar
        calculos.append({
            "item": item,
            "porcentaje": porcentaje,
            "base": base,
            "residuo": residuo,
        })

    # cuantas unidades faltan pa llegar al total despues de truncar todo hacia abajo
    suma_base = sum(c["base"] for c in calculos)
    faltantes = total_acumulado - suma_base

    # esas faltantes se las damos a los de mayor residuo; si empatan gana el de mayor muestreo
    orden = sorted(
        calculos,
        key=lambda c: (c["residuo"], c["item"].cantidad_muestreo),
        reverse=True,
    )
    # faltantes ya viene entre 0 y len(calculos), pero lo acotamos por si acaso
    for i in range(max(0, min(faltantes, len(orden)))):
        orden[i]["base"] += 1

    # hacemos upsert en vez de borrar y recrear, actualizamos las que ya estan (reactivando si alguna quedo apagada por una cascada), insertamos los calibres nuevos y borramos solo los que ya no van, asi respetamos el UNIQUE(conteo_id, calibre_id) sin el hard-delete masivo de antes
    existentes = {
        fila.calibre_id: fila
        for fila in db.query(ClasificacionCalibreConteo).filter(
            ClasificacionCalibreConteo.conteo_id == conteo_id
        ).all()
    }
    calibres_nuevos = {c["item"].calibre_id for c in calculos}

    # los calibres que ya no estan en el muestreo nuevo, los sacamos
    for calibre_id, fila in existentes.items():
        if calibre_id not in calibres_nuevos:
            db.delete(fila)

    for c in calculos:
        item = c["item"]
        fila = existentes.get(item.calibre_id)
        if fila is not None:
            fila.cantidad_muestreo = item.cantidad_muestreo
            fila.total_muestreo = datos.total_muestreo
            fila.porcentaje = c["porcentaje"]
            fila.cantidad_extrapolada = c["base"]
            fila.activo = True
            fila.desactivado_por_campo_cultivo = False
            fila.updated_by = usuario.id
        else:
            db.add(ClasificacionCalibreConteo(
                conteo_id=conteo_id,
                calibre_id=item.calibre_id,
                cantidad_muestreo=item.cantidad_muestreo,
                total_muestreo=datos.total_muestreo,
                porcentaje=c["porcentaje"],
                cantidad_extrapolada=c["base"],
                created_by=usuario.id,
            ))

    db.commit()
    return _build_muestreo_response(conteo, db)


@router.get("/{conteo_id}/muestreo", response_model=MuestreoResponse)
def obtener_muestreo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)
    return _build_muestreo_response(conteo, db)