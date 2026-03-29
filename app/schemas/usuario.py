from pydantic import BaseModel, EmailStr, ConfigDict
from datetime import datetime

class UsuarioBase(BaseModel):
    nombre: str
    email: EmailStr

class UsuarioCreate(UsuarioBase):
    password: str

class UsuarioResponse(UsuarioBase):
    id: int
    rol: str
    creado_en: datetime


    model_config = ConfigDict(from_attributes=True)