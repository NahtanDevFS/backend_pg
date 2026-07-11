from typing import Optional

# umbrales de confiabilidad, se tienen que cumplir las dos condiciones o baja de categoria: alto: prom>=0.75 y baja<=0.15 · moderado: prom>=0.60 y baja<=0.30 · bajo: lo demas
UMBRAL_ALTO_PROMEDIO = 0.75
UMBRAL_ALTO_BAJA = 0.15
UMBRAL_MOD_PROMEDIO = 0.60
UMBRAL_MOD_BAJA = 0.30


def derivar_nivel(
    promedio_confianza: Optional[float],
    porcentaje_baja_confianza: Optional[float],
) -> Optional[str]:
    # saca el nivel (alto/moderado/bajo) segun las metricas, None si falta alguna (video sin detecciones)
    if promedio_confianza is None or porcentaje_baja_confianza is None:
        return None

    p = float(promedio_confianza)
    b = float(porcentaje_baja_confianza)

    if p >= UMBRAL_ALTO_PROMEDIO and b <= UMBRAL_ALTO_BAJA:
        return "alto"
    if p >= UMBRAL_MOD_PROMEDIO and b <= UMBRAL_MOD_BAJA:
        return "moderado"
    return "bajo"