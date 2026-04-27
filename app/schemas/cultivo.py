from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional


class CultivoBase(BaseModel):
    nombre:       str             = Field(..., min_length=1, max_length=150)
    ubicacion:    Optional[str]   = Field(default=None, max_length=255)
    hectareas:    Optional[float] = Field(default=None, gt=0)
    total_surcos: int             = Field(..., gt=0)
    activo:       bool            = True


class CultivoCreate(CultivoBase):
    pass


class CultivoUpdate(BaseModel):
    nombre:       Optional[str]   = Field(default=None, min_length=1, max_length=150)
    ubicacion:    Optional[str]   = Field(default=None, max_length=255)
    hectareas:    Optional[float] = Field(default=None, gt=0)
    total_surcos: Optional[int]   = Field(default=None, gt=0)


class CultivoResponse(CultivoBase):
    id:         int
    usuario_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)