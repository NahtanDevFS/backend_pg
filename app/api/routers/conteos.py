from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, CampoCultivo, Conteo, EstadoConteo, ClasificacionCalibreConteo, CalibreMelon, CampoCultivoOperador
from app.schemas.conteo import ConteoCreate, ConteoResponse, ComparacionAnteriorResponse, HistorialPaginadoResponse
from app.schemas.muestreo import MuestreoRequest, MuestreoResponse, ClasificacionResponse
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador

router = APIRouter(prefix="/conteos", tags=["Conteos"])


#Helpers

def _get_conteo_del_usuario(conteo_id: int, usuario: Usuario, db: Session) -> Conteo:
    #Devuelve un conteo verificando que el operador tiene acceso al campo de cultivo correspondiente a través de campo_cultivo_operador
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


def _get_conteo_cualquiera(conteo_id: int, db: Session) -> Conteo:
    """Devuelve cualquier conteo activo sin restricción de dueño (uso admin)."""
    conteo = db.query(Conteo).filter(
        Conteo.id == conteo_id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")
    return conteo


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


#Operador

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
    estado:      Optional[str]  = None,
    skip:        int = 0,
    limit:       int = 20,
    db:      Session = Depends(get_db),
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

    return query.order_by(Conteo.fecha_conteo.desc()).offset(skip).limit(limit).all()


#estas rutas deben ir ANTES de /{conteo_id} para que FastAPI no interprete "admin" como un parámetro entero conteo_id

@router.get(
    "/admin/historial",
    response_model=HistorialPaginadoResponse,
    summary="Historial global de conteos paginado (solo Administrador)"
)
def historial_global(
    cultivo_id:    Optional[int]  = None,
    usuario_id:    Optional[int]  = None,
    fecha_desde:   Optional[date] = None,
    fecha_hasta:   Optional[date] = None,
    skip:          int            = 0,
    limit:         int            = 20,
    db: Session = Depends(get_db),
    _: Usuario  = Depends(requiere_admin)
):
    #Devuelve los conteos activos del sistema, paginados, con filtros opcionales.
    #?cultivo_id=X solo conteos de ese campo; ?usuario_id=X conteos de campos de
    #ese operador; ?fecha_desde / ?fecha_hasta rango de fechas. La respuesta
    #incluye 'items' (la página actual) y 'total' (conteos que cumplen el filtro,
    #para que el frontend calcule el número de páginas).

    query = db.query(Conteo).filter(Conteo.activo == True)

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
        query.order_by(Conteo.fecha_conteo.desc())
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
    return _get_conteo_cualquiera(conteo_id, db)


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
    conteo = _get_conteo_cualquiera(conteo_id, db)
    return _build_muestreo_response(conteo, db)

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
    estado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    conteo.estado_id = estado.id
    conteo.updated_by = usuario.id
    db.commit()
    return {"mensaje": "Conteo marcado como completado."}


@router.get(
    "/{conteo_id}/comparacion-anterior",
    response_model=ComparacionAnteriorResponse
)
def comparar_con_anterior(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(requiere_operador)
):
    """
    Devuelve el conteo completado inmediatamente anterior del mismo campo de cultivo
    y calcula la variación porcentual respecto al conteo actual.
    """
    conteo_actual = _get_conteo_del_usuario(conteo_id, usuario, db)

    if conteo_actual.conteo_total_acumulado == 0:
        return ComparacionAnteriorResponse(hay_historial=False)

    estado_completado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    if not estado_completado:
        return ComparacionAnteriorResponse(hay_historial=False)

    anterior = db.query(Conteo).filter(
        Conteo.campo_cultivo_id == conteo_actual.campo_cultivo_id,
        Conteo.id != conteo_id,
        Conteo.estado_id == estado_completado.id,
        Conteo.activo == True,
        Conteo.fecha_conteo < conteo_actual.fecha_conteo
    ).order_by(Conteo.fecha_conteo.desc()).first()

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

    db.query(ClasificacionCalibreConteo).filter(
        ClasificacionCalibreConteo.conteo_id == conteo_id
    ).delete()

    total_acumulado = conteo.conteo_total_acumulado

    #Reparto por metodo del residuo mayor (Largest Remainder / Hamilton)
    # Redondear cada calibre por separado hace que la suma de extrapolados no cuadre con el total (p.ej. 50/20/10/10/10 sobre 48 daba 49). En su lugar:
    # 1) a cada calibre se le asigna la parte entera (floor) de su cantidad ideal  2) las unidades faltantes para llegar al total se reparten de a una a los calibres con mayor parte decimal (los que más "merecen" la unidad extra) así la suma de cantidades extrapoladas es siempre exactamente el total.
    calculos = []
    for item in datos.items:
        calibre = db.query(CalibreMelon).filter(CalibreMelon.id == item.calibre_id).first()
        if not calibre:
            raise HTTPException(status_code=404, detail=f"Calibre {item.calibre_id} no encontrado.")
        # Porcentaje real del muestreo (dato medido, se conserva tal cual)
        porcentaje = round(item.cantidad_muestreo / datos.total_muestreo * 100, 2)
        # Cantidad ideal con decimales, anclada al total acumulado
        ideal = item.cantidad_muestreo / datos.total_muestreo * total_acumulado
        base = int(ideal)  # parte entera (floor, ideal >= 0)
        residuo = ideal - base  # parte decimal para el desempate
        calculos.append({
            "item": item,
            "porcentaje": porcentaje,
            "base": base,
            "residuo": residuo,
        })

    # Unidades que faltan para llegar al total tras truncar hacia abajo
    suma_base = sum(c["base"] for c in calculos)
    faltantes = total_acumulado - suma_base

    # Repartir las faltantes a los mayores residuos (de mayor a menor).
    # En empate de residuo, se prioriza el de mayor cantidad de muestreo.
    orden = sorted(
        calculos,
        key=lambda c: (c["residuo"], c["item"].cantidad_muestreo),
        reverse=True,
    )
    # faltantes está acotado entre 0 y len(calculos) por construcción (floor),
    # pero se acota explícitamente por seguridad ante cualquier borde.
    for i in range(max(0, min(faltantes, len(orden)))):
        orden[i]["base"] += 1

    for c in calculos:
        db.add(ClasificacionCalibreConteo(
            conteo_id=conteo_id,
            calibre_id=c["item"].calibre_id,
            cantidad_muestreo=c["item"].cantidad_muestreo,
            total_muestreo=datos.total_muestreo,
            porcentaje=c["porcentaje"],
            cantidad_extrapolada=c["base"],
            created_by=usuario.id
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