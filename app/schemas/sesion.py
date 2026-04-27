from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, date
from typing import Optional, List


class SesionCreate(BaseModel):
    cultivo_id: int
    variedad_id: int
    fecha_sesion: Optional[date] = None
    observaciones: Optional[str] = None


class SesionUpdate(BaseModel):
    estado_id: Optional[int] = None
    observaciones: Optional[str] = None


class SesionResponse(BaseModel):
    id: int
    cultivo_id: int
    variedad_id: int
    estado_id: int
    fecha_sesion: date
    conteo_total_acumulado: int
    observaciones: Optional[str] = None
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
