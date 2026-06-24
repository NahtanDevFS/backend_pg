from pydantic import BaseModel, ConfigDict, Field, computed_field
from datetime import datetime
from typing import Optional
from app.core.confiabilidad import derivar_nivel


class AjusteResultadoRequest(BaseModel):
    conteo_ajustado: int = Field(..., ge=0)
    observaciones: Optional[str] = None


class ResultadoIaResponse(BaseModel):
    id: int
    conteo_ia: int
    conteo_ajustado: Optional[int] = None
    observaciones_ajuste: Optional[str] = None
    tiempo_procesamiento_seg: Optional[float] = None
    # Campos de confiabilidad requeridos por la app móvil
    promedio_confianza: Optional[float] = None
    porcentaje_baja_confianza: Optional[float] = None
    total_frames_procesados: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def nivel_confiabilidad(self) -> Optional[str]:
        #Nivel derivado ('alto', 'moderado', 'bajo') de este video. None si no hay métricas.
        return derivar_nivel(self.promedio_confianza, self.porcentaje_baja_confianza)


class ProcesamientoResponse(BaseModel):
    id: int
    conteo_id: int
    usuario_id: int
    estado_id: int
    surco_inicio: int
    surco_fin: int
    video_original_url: Optional[str]     = None
    video_anotado_url: Optional[str]   = None
    fecha_grabacion: datetime
    created_at: datetime
    resultado: Optional[ResultadoIaResponse] = None

    model_config = ConfigDict(from_attributes=True)