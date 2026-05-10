from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List


class CultivoBase(BaseModel):
    nombre:       str             = Field(..., min_length=1, max_length=150)
    ubicacion:    Optional[str]   = Field(default=None, max_length=255)
    hectareas:    Optional[float] = Field(default=None, gt=0)
    total_surcos: int             = Field(..., gt=0)
    activo:       bool            = True


class CultivoCreate(CultivoBase):
    """Usado por el administrador para crear un cultivo."""
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


# Asignación de operadores

class AsignarOperadorRequest(BaseModel):
    usuario_id: int


class OperadorAsignadoResponse(BaseModel):
    """Operador asignado a un cultivo, con datos básicos para mostrar en la UI."""
    id:         int          # id del registro cultivo_operador
    usuario_id: int
    nombre:     str          # nombre del usuario — se resuelve en el router
    activo:     bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)