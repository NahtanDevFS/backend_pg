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


class UsuarioEdit(BaseModel):
    #Usado por el admin para editar nombre, rol y/o restablecer contraseña
    nombre: Optional[str] = None
    rol_id: Optional[int] = None
    password: Optional[str] = None


class CambiarPasswordPropiaRequest(BaseModel):
    #Usado por cualquier usuario para cambiar su propia contraseña.
    password_actual: str
    password_nueva: str


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    rol_id: int
    activo: bool
    debe_cambiar_password: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)