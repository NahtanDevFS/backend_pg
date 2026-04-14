from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

class ResultadoCalibreResponse(BaseModel):
    id: int
    calibre_id: int
    porcentaje_muestreo: float
    cantidad_calculada: int

    model_config = ConfigDict(from_attributes=True)

class ResultadoDetalle(BaseModel):
    id: int
    conteo_ia: int
    conteo_final_ajustado: Optional[int] = None
    observaciones_ajuste: Optional[str] = None
    tiempo_procesamiento_seg: Optional[float] = None
    calibres: List[ResultadoCalibreResponse] = []

    model_config = ConfigDict(from_attributes=True)

class ProcesamientoResponse(BaseModel):
    id: int
    cultivo_id: int
    variedad_id: int
    estado: str       #'procesando', 'completado', 'error'
    video_original_url: str
    video_anotado_url: Optional[str] = None
    fecha_grabacion: datetime
    creado_en: datetime
    resultado: Optional[ResultadoDetalle] = None

    model_config = ConfigDict(from_attributes=True)