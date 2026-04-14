from pydantic import BaseModel, ConfigDict
from datetime import datetime

class UsuarioBase(BaseModel):
    nombre: str
    rol_id: int

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    id: int
    creado_en: datetime
    model_config = ConfigDict(from_attributes=True)