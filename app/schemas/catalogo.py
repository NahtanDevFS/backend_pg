from pydantic import BaseModel, ConfigDict


class RolResponse(BaseModel):
    id:     int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class VariedadResponse(BaseModel):
    id:          int
    nombre:      str
    descripcion: str | None = None
    model_config = ConfigDict(from_attributes=True)


class CalibreResponse(BaseModel):
    id:          int
    nombre:      str
    descripcion: str | None = None
    orden:       int
    model_config = ConfigDict(from_attributes=True)


class EstadoConteoResponse(BaseModel):
    id:     int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class EstadoProcesamientoResponse(BaseModel):
    id:     int
    nombre: str
    model_config = ConfigDict(from_attributes=True)