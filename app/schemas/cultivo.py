from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional

class CultivoBase(BaseModel):
    #fuerza a que el nombre tenga al menos 1 caracter y máximo 150
    nombre: str = Field(..., min_length=1, max_length=150)
    ubicacion: Optional[str] = Field(default=None, max_length=255)
    #valida que las hectáreas sean estrictamente mayores a 0 (gt=0)
    hectareas: Optional[float] = Field(default=None, gt=0)

class CultivoCreate(CultivoBase):
    pass

class CultivoResponse(CultivoBase):
    id: int
    usuario_id: int
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)