from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class UsuarioBase(BaseModel):
    nombre: str
    rol_id: int


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    rol_id: Optional[int] = None


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    rol_id: int
    activo: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
