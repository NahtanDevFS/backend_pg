from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List


class CampoCultivoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=150)
    municipio_id: int = Field(..., gt=0)
    # ubicacion: dirección/referencia libre dentro del municipio (opcional)
    ubicacion: Optional[str] = Field(default=None, max_length=255)
    hectareas: Optional[float] = Field(default=None, gt=0)
    total_surcos: int = Field(..., gt=0)
    activo: bool = True


class CampoCultivoCreate(CampoCultivoBase):
    #Usado por el administrador para crear un campo de cultivo
    pass


class CampoCultivoUpdate(BaseModel):
    nombre: Optional[str] = Field(default=None, min_length=1, max_length=150)
    municipio_id: Optional[int] = Field(default=None, gt=0)
    ubicacion: Optional[str] = Field(default=None, max_length=255)
    hectareas: Optional[float] = Field(default=None, gt=0)
    total_surcos: Optional[int] = Field(default=None, gt=0)


class CampoCultivoResponse(BaseModel):
    id: int
    nombre: str
    municipio_id: int
    # Nombres desnormalizados para conveniencia del frontend (decisión 1A).
    # Se resuelven en el router a partir de la relación municipio -> departamento.
    municipio_nombre: str
    departamento_id: int
    departamento_nombre: str
    ubicacion: Optional[str] = None
    hectareas: Optional[float] = None
    total_surcos: int
    activo: bool
    usuario_id: int
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


# Asignación de operadores

class AsignarOperadorRequest(BaseModel):
    usuario_id: int


class OperadorAsignadoResponse(BaseModel):
    #Operador asignado a un campo de cultivo, con datos básicos para mostrar en la UI
    id: int # id del registro campo_cultivo_operador
    usuario_id: int
    nombre: str # nombre del usuario se resuelve en el router
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)