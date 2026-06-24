from typing import Optional

# Umbrales de confiabilidad. Un nivel se alcanza solo si AMBAS condiciones se
# cumplen; si una falla, baja de categoría (criterio conservador).
#   Alto:     promedio >= 0.75  Y  baja <= 0.15
#   Moderado: promedio >= 0.60  Y  baja <= 0.30
#   Bajo:     cualquier otro caso
UMBRAL_ALTO_PROMEDIO = 0.75
UMBRAL_ALTO_BAJA     = 0.15
UMBRAL_MOD_PROMEDIO  = 0.60
UMBRAL_MOD_BAJA      = 0.30


def derivar_nivel(
    promedio_confianza: Optional[float],
    porcentaje_baja_confianza: Optional[float],
) -> Optional[str]:
    """Deriva el nivel de confiabilidad ('alto', 'moderado', 'bajo') a partir
    del promedio de confianza y el porcentaje de baja confianza (ambos 0-1).

    Devuelve None si falta cualquiera de las dos métricas (p. ej. video o
    conteo sin detecciones): la UI lo mostrará como "sin datos".
    """
    if promedio_confianza is None or porcentaje_baja_confianza is None:
        return None

    p = float(promedio_confianza)
    b = float(porcentaje_baja_confianza)

    if p >= UMBRAL_ALTO_PROMEDIO and b <= UMBRAL_ALTO_BAJA:
        return "alto"
    if p >= UMBRAL_MOD_PROMEDIO and b <= UMBRAL_MOD_BAJA:
        return "moderado"
    return "bajo"