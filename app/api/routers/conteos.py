from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models.models import Usuario, Cultivo, Conteo, EstadoConteo, ClasificacionCalibre, Calibre
from app.schemas.conteo import ConteoCreate, ConteoResponse
from app.schemas.muestreo import MuestreoRequest, MuestreoResponse, ClasificacionResponse
from app.api.deps import obtener_usuario_actual

router = APIRouter(prefix="/conteos", tags=["Conteos"])


def _get_conteo_del_usuario(conteo_id: int, usuario: Usuario, db: Session) -> Conteo:
    conteo = db.query(Conteo).join(Cultivo).filter(
        Conteo.id == conteo_id,
        Cultivo.usuario_id == usuario.id,
        Conteo.activo == True
    ).first()
    if not conteo:
        raise HTTPException(status_code=404, detail="Conteo no encontrado.")
    return conteo


@router.post("/", response_model=ConteoResponse, status_code=status.HTTP_201_CREATED)
def crear_conteo(
    conteo_in: ConteoCreate,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == conteo_in.cultivo_id,
        Cultivo.usuario_id == usuario.id,
        Cultivo.activo == True
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    estado_inicial = db.query(EstadoConteo).filter(EstadoConteo.nombre == "en_progreso").first()
    if not estado_inicial:
        raise HTTPException(status_code=500, detail="Estado 'en_progreso' no encontrado en catálogo.")

    nuevo = Conteo(
        cultivo_id=conteo_in.cultivo_id,
        variedad_id=conteo_in.variedad_id,
        estado_id=estado_inicial.id,
        fecha_conteo=conteo_in.fecha_conteo,
        observaciones=conteo_in.observaciones,
        created_by=usuario.id
    )
    db.add(nuevo)
    db.commit()
    db.refresh(nuevo)
    return nuevo


@router.get("/cultivo/{cultivo_id}", response_model=List[ConteoResponse])
def listar_conteos_por_cultivo(
    cultivo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    cultivo = db.query(Cultivo).filter(
        Cultivo.id == cultivo_id,
        Cultivo.usuario_id == usuario.id
    ).first()
    if not cultivo:
        raise HTTPException(status_code=404, detail="Cultivo no encontrado.")

    return db.query(Conteo).filter(
        Conteo.cultivo_id == cultivo_id,
        Conteo.activo == True
    ).order_by(Conteo.fecha_conteo.desc()).all()


@router.get("/{conteo_id}", response_model=ConteoResponse)
def obtener_conteo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    return _get_conteo_del_usuario(conteo_id, usuario, db)


@router.patch("/{conteo_id}/completar")
def completar_conteo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)
    estado = db.query(EstadoConteo).filter(EstadoConteo.nombre == "completado").first()
    conteo.estado_id = estado.id
    conteo.updated_by = usuario.id
    db.commit()
    return {"mensaje": "Conteo marcado como completado."}


# ── Muestreo por calibre ──────────────────────────────────────

@router.post("/{conteo_id}/muestreo", response_model=MuestreoResponse)
def guardar_muestreo(
    conteo_id: int,
    datos: MuestreoRequest,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)

    if conteo.conteo_total_acumulado == 0:
        raise HTTPException(status_code=400, detail="El conteo aún no tiene videos procesados.")

    # Validar que la suma de cantidades no supere el total del muestreo
    suma = sum(i.cantidad_muestreo for i in datos.items)
    if suma != datos.total_muestreo:
        raise HTTPException(
            status_code=400,
            detail=f"La suma de cantidades por calibre ({suma}) debe ser igual al total del muestreo ({datos.total_muestreo})."
        )

    # Eliminar clasificaciones anteriores y reemplazar
    db.query(ClasificacionCalibre).filter(
        ClasificacionCalibre.conteo_id == conteo_id
    ).delete()

    clasificaciones_resp = []
    for item in datos.items:
        calibre = db.query(Calibre).filter(Calibre.id == item.calibre_id).first()
        if not calibre:
            raise HTTPException(status_code=404, detail=f"Calibre {item.calibre_id} no encontrado.")

        porcentaje = round(item.cantidad_muestreo / datos.total_muestreo * 100, 2)
        cantidad_extrapolada = round(porcentaje * conteo.conteo_total_acumulado / 100)

        nueva = ClasificacionCalibre(
            conteo_id=conteo_id,
            calibre_id=item.calibre_id,
            cantidad_muestreo=item.cantidad_muestreo,
            total_muestreo=datos.total_muestreo,
            porcentaje=porcentaje,
            cantidad_extrapolada=cantidad_extrapolada,
            created_by=usuario.id
        )
        db.add(nueva)

        clasificaciones_resp.append(ClasificacionResponse(
            id=0,  # se actualiza tras el commit
            calibre_id=item.calibre_id,
            nombre_calibre=calibre.nombre,
            orden_calibre=calibre.orden,
            cantidad_muestreo=item.cantidad_muestreo,
            total_muestreo=datos.total_muestreo,
            porcentaje=porcentaje,
            cantidad_extrapolada=cantidad_extrapolada
        ))

    db.commit()

    # Recargar con IDs reales
    clasificaciones_db = db.query(ClasificacionCalibre).join(Calibre).filter(
        ClasificacionCalibre.conteo_id == conteo_id
    ).order_by(Calibre.orden).all()

    return MuestreoResponse(
        total_muestreo=datos.total_muestreo,
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
            ) for c in clasificaciones_db
        ]
    )


@router.get("/{conteo_id}/muestreo", response_model=MuestreoResponse)
def obtener_muestreo(
    conteo_id: int,
    db: Session = Depends(get_db),
    usuario: Usuario = Depends(obtener_usuario_actual)
):
    conteo = _get_conteo_del_usuario(conteo_id, usuario, db)

    clasificaciones = db.query(ClasificacionCalibre).join(Calibre).filter(
        ClasificacionCalibre.conteo_id == conteo_id,
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