from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, date
from typing import Optional, List


class ConteoCreate(BaseModel):
    cultivo_id: int
    variedad_id: int
    fecha_conteo: Optional[date] = None
    observaciones: Optional[str] = None


class ConteoUpdate(BaseModel):
    estado_id: Optional[int] = None
    observaciones: Optional[str] = None


class ConteoResponse(BaseModel):
    id: int
    cultivo_id: int
    variedad_id: int
    estado_id: int
    fecha_conteo: date
    total_surcos: int
    conteo_total_acumulado: int
    nivel_confiabilidad_agregado: Optional[str] = None
    promedio_confianza_sesion: Optional[float] = None
    observaciones: Optional[str] = None
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ComparacionAnteriorResponse(BaseModel):
    """Devuelve el conteo anterior completado del mismo cultivo y la variación."""
    conteo_anterior_id: Optional[int] = None
    conteo_anterior_total: Optional[int] = None
    conteo_anterior_fecha: Optional[date] = None
    variacion_porcentual: Optional[float] = None  # positivo = subió, negativo = bajó
    hay_historial: bool