from pydantic import BaseModel, ConfigDict, Field


class RolResponse(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class VariedadResponse(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None
    model_config = ConfigDict(from_attributes=True)


class CalibreResponse(BaseModel):
    id: int
    nombre: str
    descripcion: str | None = None
    orden: int
    model_config = ConfigDict(from_attributes=True)


class EstadoConteoResponse(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class EstadoProcesamientoResponse(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)

class DepartamentoResponse(BaseModel):
    id: int
    nombre: str
    model_config = ConfigDict(from_attributes=True)


class MunicipioResponse(BaseModel):
    id: int
    nombre: str
    departamento_id: int
    model_config = ConfigDict(from_attributes=True)

#Gestión de catálogo de melones (admin)

class CalibreAdminResponse(BaseModel):
    #Calibre con su estado activo, para la vista de gestión del admin.
    id: int
    nombre: str
    descripcion: str | None = None
    orden: int
    activo: bool
    conteos_asociados: int = 0  # cuántas clasificaciones lo referencian
    model_config = ConfigDict(from_attributes=True)


class CalibreCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=20)
    descripcion: str | None = Field(None, max_length=255)
    orden: int = 0


class CalibreUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=20)
    descripcion: str | None = Field(None, max_length=255)
    orden: int = 0

class VariedadAdminResponse(BaseModel):
    #Variedad con su estado activo, para la vista de gestión del admin.
    id: int
    nombre: str
    descripcion: str | None = None
    activo: bool
    conteos_asociados: int = 0  # cuántos conteos usan esta variedad
    model_config = ConfigDict(from_attributes=True)


class VariedadCreate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=2000)


class VariedadUpdate(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=100)
    descripcion: str | None = Field(None, max_length=2000)

class CalibreDeVariedadResponse(BaseModel):
    #Un calibre en el contexto de una variedad: incluye si está asignado
    #(relación activa) y cuántos conteos de esa variedad lo han usado
    calibre_id: int
    nombre: str
    descripcion: str | None = None
    orden: int
    asignado: bool  # la relación variedad-calibre está activa
    conteos_en_variedad: int = 0  # usos históricos en conteos de esta variedad


class AsignarCalibreRequest(BaseModel):
    calibre_id: int