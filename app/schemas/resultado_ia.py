from pydantic import BaseModel
from typing import Optional


class ResultadoIaCallback(BaseModel):
    # lo que Modal manda en el callback, el video anotado viaja aparte en el mismo multipart
    conteo_ia: int
    tiempo_procesamiento_seg: Optional[float] = None
    total_frames_procesados: Optional[int] = None
    # metricas de confiabilidad
    promedio_confianza: Optional[float] = None
    porcentaje_baja_confianza: Optional[float] = None