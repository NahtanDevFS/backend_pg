from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import Optional, List


#Clasificación por calibre
class CalibrePorcentaje(BaseModel):
    calibre_id: int
    porcentaje: float = Field(..., gt=0, le=100)


class ClasificacionCalibreResponse(BaseModel):
    id: int
    calibre_id: int
    porcentaje: float
    cantidad_melones: int

    model_config = ConfigDict(from_attributes=True)


#Resultado IA
class AjusteResultadoRequest(BaseModel):
    conteo_ajustado: int = Field(..., ge=0)
    observaciones: Optional[str] = None
    calibres: List[CalibrePorcentaje] = []


class ResultadoIaResponse(BaseModel):
    id: int
    conteo_ia: int
    conteo_ajustado: Optional[int] = None
    observaciones_ajuste: Optional[str] = None
    tiempo_procesamiento_seg: Optional[float] = None
    clasificaciones: List[ClasificacionCalibreResponse] = []

    model_config = ConfigDict(from_attributes=True)


#Procesamiento de video
class ProcesamientoResponse(BaseModel):
    id: int
    sesion_id: int
    usuario_id: int
    estado_id: int
    surco_inicio: int
    surco_fin: int
    video_original_url: str
    video_anotado_url: Optional[str] = None
    fecha_grabacion: datetime
    created_at: datetime
    resultado: Optional[ResultadoIaResponse] = None

    model_config = ConfigDict(from_attributes=True)