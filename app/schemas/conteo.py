from pydantic import BaseModel, ConfigDict, Field, computed_field
from datetime import datetime, date
from typing import Optional, List
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
    variedad_id: int
    estado_id: int
    fecha_conteo: date
    total_surcos: int
    conteo_total_acumulado: int
    promedio_confianza_sesion: Optional[float] = None
    porcentaje_baja_confianza_sesion: Optional[float] = None
    observaciones: Optional[str] = None
    activo: bool
    created_at: datetime
    created_by: int

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def nivel_confiabilidad(self) -> Optional[str]:
        #Nivel derivado de la sesión completa. None si ningún video tiene métricas.
        return derivar_nivel(
            self.promedio_confianza_sesion,
            self.porcentaje_baja_confianza_sesion,
        )


class ComparacionAnteriorResponse(BaseModel):
    """Devuelve el conteo anterior completado del mismo campo de cultivo y la variación"""
    conteo_anterior_id: Optional[int] = None
    conteo_anterior_total: Optional[int] = None
    conteo_anterior_fecha: Optional[date] = None
    variacion_porcentual: Optional[float] = None  # positivo = subió, negativo = bajó
    hay_historial: bool