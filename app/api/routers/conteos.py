from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, Cultivo, Conteo, EstadoConteo, ClasificacionCalibre, Calibre, CultivoOperador
from app.schemas.conteo import ConteoCreate, ConteoResponse, ComparacionAnteriorResponse
from app.schemas.muestreo import MuestreoRequest, MuestreoResponse, ClasificacionResponse
from app.api.deps import obtener_usuario_actual, requiere_admin, requiere_operador

router = APIRouter(prefix="/conteos", tags=["Conteos"])


#Helpers

def _get_conteo_del_usuario(conteo_id: int, usuario: Usuario, db: Session) -> Conteo:
    #Devuelve un conteo verificando que el operador tiene acceso al cultivo correspondiente a través de cultivo_operador
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
    clasificaciones = db.query(ClasificacionCalibre).join(Calibre).filter(
        ClasificacionCalibre.conteo_id == conteo.id,
        ClasificacionCalibre.activo == True
    ).order_by(Calibre.orden).all()

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
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == conteo_in.cultivo_id,
        Cultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    acceso = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo.id,
        CultivoOperador.usuario_id == usuario.id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cultivo.")

    estado_inicial = db.query(EstadoConteo).filter(EstadoConteo.nombre == "en_progreso").first()
    if not estado_inicial:
        raise HTTPException(status_code=500, detail="Estado 'en_progreso' no encontrado en catálogo.")

    nuevo = Conteo(
        cultivo_id=conteo_in.cultivo_id,
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
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == cultivo_id,
        Cultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    acceso = db.query(CultivoOperador).filter(
        CultivoOperador.cultivo_id == cultivo_id,
        CultivoOperador.usuario_id == usuario.id,
        CultivoOperador.activo == True,
    ).first()
    if not acceso:
        raise HTTPException(status_code=403, detail="No tienes acceso a este cultivo.")

    query = db.query(Conteo).filter(
        Conteo.cultivo_id == cultivo_id,
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


#estas rutas deben ir ANTES de /{conteo_id} para que FastAPI no interprete "admin" como un parámetro entero conteo_id.

@router.get(
    "/admin/historial",
    response_model=List[ConteoResponse],
    summary="Historial global de conteos (solo Administrador)"
)
def historial_global(
    cultivo_id:    Optional[int]  = None,
    usuario_id:    Optional[int]  = None,
    fecha_desde:   Optional[date] = None,
    fecha_hasta:   Optional[date] = None,
    db: Session = Depends(get_db),
    _: Usuario  = Depends(requiere_admin)
):
    #Devuelve todos los conteos activos del sistema con filtros opcionales, ?cultivo_id=X solo conteos de ese cultivo, ?usuario_id=X    → solo conteos de cultivos de ese operador, fecha_desde=YYYY-MM-DD y ?fecha_hasta=YYYY-MM-DD → rango de fechas

    query = db.query(Conteo).join(Cultivo).filter(Conteo.activo == True)

    if cultivo_id:
        query = query.filter(Conteo.cultivo_id == cultivo_id)
    if usuario_id:
        query = query.filter(Cultivo.usuario_id == usuario_id)
    if fecha_desde:
        query = query.filter(Conteo.fecha_conteo >= fecha_desde)
    if fecha_hasta:
        query = query.filter(Conteo.fecha_conteo <= fecha_hasta)

    return query.order_by(Conteo.fecha_conteo.desc()).all()


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
    Devuelve el conteo completado inmediatamente anterior del mismo cultivo
    y calcula la variación porcentual respecto al conteo actual.
    """
    conteo_actual = _get_conteo_del_usuario(conteo_id, usuario, db)

    if conteo_actual.conteo_total_acumulado == 0:
        return ComparacionAnteriorResponse(hay_historial=False)

    estado_completado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    if not estado_completado:
        return ComparacionAnteriorResponse(hay_historial=False)

    anterior = db.query(Conteo).filter(
        Conteo.cultivo_id == conteo_actual.cultivo_id,
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

    db.query(ClasificacionCalibre).filter(
        ClasificacionCalibre.conteo_id == conteo_id
    ).delete()

    for item in datos.items:
        calibre = db.query(Calibre).filter(Calibre.id == item.calibre_id).first()
        if not calibre:
            raise HTTPException(status_code=404, detail=f"Calibre {item.calibre_id} no encontrado.")

        porcentaje = round(item.cantidad_muestreo / datos.total_muestreo * 100, 2)
        cantidad_extrapolada = round(porcentaje * conteo.conteo_total_acumulado / 100)

        db.add(ClasificacionCalibre(
            conteo_id=conteo_id,
            calibre_id=item.calibre_id,
            cantidad_muestreo=item.cantidad_muestreo,
            total_muestreo=datos.total_muestreo,
            porcentaje=porcentaje,
            cantidad_extrapolada=cantidad_extrapolada,
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