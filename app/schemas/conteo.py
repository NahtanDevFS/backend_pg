from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, date
from typing import Optional, List


class ConteoCreate(BaseModel):
    cultivo_id:    int
    variedad_id:   int
    fecha_conteo:  Optional[date] = None
    observaciones: Optional[str]  = None


class ConteoUpdate(BaseModel):
    estado_id:     Optional[int] = None
    observaciones: Optional[str] = None


class ConteoResponse(BaseModel):
    id:                     int
    cultivo_id:             int
    variedad_id:            int
    estado_id:              int
    fecha_conteo:           date
    conteo_total_acumulado: int
    observaciones:          Optional[str] = None
    activo:                 bool
    created_at:             datetime

    model_config = ConfigDict(from_attributes=True)