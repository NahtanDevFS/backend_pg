from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator
from datetime import datetime
from typing import Optional, Any
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
    # estado_nombre: nombre legible del estado ('pendiente', 'procesando',
    # 'completado', 'error', 'cancelado'). Se resuelve desde la relación ORM.
    estado_nombre: Optional[str] = None
    activo: bool = True
    surco_inicio: int
    surco_fin: int
    video_original_url: Optional[str]     = None
    video_anotado_url: Optional[str]   = None
    fecha_grabacion: datetime
    created_at: datetime
    resultado: Optional[ResultadoIaResponse] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode="before")
    @classmethod
    def _extraer_estado_nombre(cls, data: Any) -> Any:
        #Inyecta estado_nombre leyendo la relación ORM 'estado'. Mantiene el objeto original para que Pydantic siga resolviendo el resto de campos por from_attributes.
        estado = getattr(data, "estado", None)
        if estado is not None:
            try:
                object.__setattr__(data, "estado_nombre", estado.nombre)
            except Exception:
                pass
        return data