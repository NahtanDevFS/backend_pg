from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class ResultadoIADetalle(BaseModel):
    conteo_maduros: int
    conteo_inmaduros: int
    tiempo_procesamiento_seg: Optional[float]

    model_config = ConfigDict(from_attributes=True)


class ProcesamientoResponse(BaseModel):
    id: int
    cultivo_id: int
    estado: str  #pendiente, procesando, completado, error
    video_original_url: str
    video_anotado_url: Optional[str]
    fecha_grabacion: datetime
    creado_en: datetime
    resultado_ia: Optional[ResultadoIADetalle] = None

    model_config = ConfigDict(from_attributes=True)