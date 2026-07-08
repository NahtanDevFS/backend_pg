from pydantic import BaseModel, ConfigDict, model_validator
from datetime import datetime
from typing import Optional, Any


class UsuarioBase(BaseModel):
    nombre: str
    rol_id: int


class UsuarioCreate(UsuarioBase):
    password: str


class UsuarioUpdate(BaseModel):
    nombre: Optional[str] = None
    rol_id: Optional[int] = None


class UsuarioEdit(BaseModel):
    # lo usa el admin pa editar nombre, rol y/o resetear la contraseña
    nombre: Optional[str] = None
    rol_id: Optional[int] = None
    password: Optional[str] = None


class CambiarPasswordPropiaRequest(BaseModel):
    # lo usa cualquier usuario pa cambiar su propia contraseña
    password_actual: str
    password_nueva: str


class UsuarioResponse(BaseModel):
    id: int
    nombre: str
    rol_id: int
    rol_nombre: Optional[str] = None
    activo: bool
    debe_cambiar_password: bool = False
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _derivar_rol_nombre(cls, obj: Any) -> Any:
        if isinstance(obj, dict):
            return obj

        rol = getattr(obj, "rol", None)
        rol_nombre = getattr(rol, "nombre", None) if rol is not None else None

        return {
            "id": obj.id,
            "nombre": obj.nombre,
            "rol_id": obj.rol_id,
            "rol_nombre": rol_nombre,
            "activo": obj.activo,
            "debe_cambiar_password": obj.debe_cambiar_password,
            "created_at": obj.created_at,
        }