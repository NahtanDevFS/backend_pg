from pydantic import BaseModel
from typing import Optional


class ResultadoIaCallback(BaseModel):
    #Datos que Modal envía en el callback tras procesar el video, el video anotado viaja aparte como UploadFile en el mismo multipart
    conteo_ia: int
    tiempo_procesamiento_seg: Optional[float] = None
    total_frames_procesados: Optional[int] = None
    # Métricas de confiabilidad
    promedio_confianza: Optional[float] = None
    porcentaje_baja_confianza: Optional[float] = None