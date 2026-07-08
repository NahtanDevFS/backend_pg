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
    # campos de confiabilidad que necesita la app movil
    promedio_confianza: Optional[float] = None
    porcentaje_baja_confianza: Optional[float] = None
    total_frames_procesados: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)

    @computed_field
    @property
    def nivel_confiabilidad(self) -> Optional[str]:
        # nivel de este video (alto/moderado/bajo), None si no hay metricas
        return derivar_nivel(self.promedio_confianza, self.porcentaje_baja_confianza)


class ProcesamientoResponse(BaseModel):
    id: int
    conteo_id: int
    usuario_id: int
    estado_id: int
    # estado_nombre: nombre legible del estado, resuelto desde la relación ORM
    estado_nombre: Optional[str] = None
    # conteo_estado_nombre estado del conteo padre (en_progreso, completado ...) permite al cliente bloquear acciones (anular) sobre conteos ya completados
    conteo_estado_nombre: Optional[str] = None
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
        # Inyecta estado_nombre desde la relación ORM 'estado'.
        estado = getattr(data, "estado", None)
        if estado is not None:
            try:
                object.__setattr__(data, "estado_nombre", estado.nombre)
            except Exception:
                pass
        # Inyecta el estado del conteo padre desde la relación ORM 'conteo'.
        conteo = getattr(data, "conteo", None)
        estado_conteo = getattr(conteo, "estado", None) if conteo is not None else None
        if estado_conteo is not None:
            try:
                object.__setattr__(data, "conteo_estado_nombre", estado_conteo.nombre)
            except Exception:
                pass
        return data