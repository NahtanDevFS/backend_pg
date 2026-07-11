from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from datetime import datetime, date
from typing import Optional, List, Any
from app.core.confiabilidad import derivar_nivel



class ConteoCreate(BaseModel):
    campo_cultivo_id: int
    variedad_id: int
    fecha_conteo: Optional[date] = None
    observaciones: Optional[str] = None


class ConteoUpdate(BaseModel):
    estado_id: Optional[int] = None
    observaciones: Optional[str] = None


class ConteoResponse(BaseModel):
    id: int
    campo_cultivo_id: int
    cultivo_nombre: Optional[str] = None
    variedad_id: int
    variedad_nombre: Optional[str] = None
    estado_id: int
    estado_nombre: Optional[str] = None
    fecha_conteo: date
    total_surcos: int
    conteo_total_acumulado: int
    promedio_confianza_sesion: Optional[float] = None
    porcentaje_baja_confianza_sesion: Optional[float] = None
    observaciones: Optional[str] = None
    activo: bool
    created_at: datetime
    created_by: int
    operador_nombre: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _extraer_nombres(cls, data: Any) -> Any:
        variedad = getattr(data, "variedad", None)
        if variedad is not None:
            try:
                object.__setattr__(data, "variedad_nombre", variedad.nombre)
            except Exception:
                pass
        cultivo = getattr(data, "cultivo", None)
        if cultivo is not None:
            try:
                object.__setattr__(data, "cultivo_nombre", cultivo.nombre)
            except Exception:
                pass
        creador = getattr(data, "creador", None)
        if creador is not None:
            try:
                object.__setattr__(data, "operador_nombre", creador.nombre)
            except Exception:
                pass
        estado = getattr(data, "estado", None)
        if estado is not None:
            try:
                object.__setattr__(data, "estado_nombre", estado.nombre)
            except Exception:
                pass
        return data

    @computed_field
    @property
    def nivel_confiabilidad(self) -> Optional[str]:
        # nivel de la sesion completa, None si ningun video tiene metricas
        return derivar_nivel(
            self.promedio_confianza_sesion,
            self.porcentaje_baja_confianza_sesion,
        )


class ComparacionAnteriorResponse(BaseModel):
    #Devuelve el conteo anterior completado del mismo campo de cultivo y la variación
    conteo_anterior_id: Optional[int] = None
    conteo_anterior_total: Optional[int] = None
    conteo_anterior_fecha: Optional[date] = None
    variacion_porcentual: Optional[float] = None  # positivo = subió, negativo = bajó
    hay_historial: bool

class HistorialPaginadoResponse(BaseModel):
    # respuesta paginada del historial: la tanda de conteos + el total global pa que el front sepa cuantas paginas hay
    items: List[ConteoResponse]
    total: int


class CambiarEstadoConteoRequest(BaseModel):
    # el admin puede mover el conteo a cualquier estado por su id
    estado_id: int