from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List


class ItemMuestreo(BaseModel):
    calibre_id:        int
    cantidad_muestreo: int = Field(..., ge=0)


class MuestreoRequest(BaseModel):
    total_muestreo: int              = Field(..., gt=0, description="Total de melones contados en el muestreo (ej: 100)")
    items:          List[ItemMuestreo]


class ClasificacionResponse(BaseModel):
    id:                   int
    calibre_id:           int
    nombre_calibre:       str
    orden_calibre:        int
    cantidad_muestreo:    int
    total_muestreo:       int
    porcentaje:           float
    cantidad_extrapolada: int

    model_config = ConfigDict(from_attributes=True)


class MuestreoResponse(BaseModel):
    total_muestreo:         int
    conteo_total_acumulado: int
    clasificaciones:        List[ClasificacionResponse]