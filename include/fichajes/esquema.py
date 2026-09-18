"""Esquema del dataset final y reglas de validación.

Tener las columnas escritas en un solo lugar es lo que permite que la tarea de
validación compare contra algo concreto en vez de "las que haya". Si mañana la
fuente deja de traer una columna, el DAG falla ahí y no publica un dataset
mutilado.

Unidad de análisis
------------------
Una fila es **un fichaje**: un jugador que llegó a un club en una temporada
concreta, con sus estadísticas de la temporada **anterior** al traspaso.

No es "un jugador": el mismo jugador aparece más de una vez si fue transferido
más de una vez dentro de la ventana que recorre el DAG.

La clave primaria es `operacion_id`, el identificador que Transfermarkt le da a
cada traspaso. Es la clave natural: si la unidad de análisis es el fichaje, la
clave tiene que identificar un fichaje.

Antes la clave era `(jugador_tm_id, temporada_fichaje)`, y estaba mal: un
jugador puede ser transferido **dos veces en la misma temporada**. Álvaro Morata
en 2024/25 es el caso de manual. Sobre el bronce que teníamos, esa clave
colapsaba 52 pares de traspasos distintos en una fila sola y perdía el otro, sin
avisar: un 2% de las filas.

Ojo con las dos temporadas, que antes eran una sola columna llamada
`temporada` y se prestaba a confusión:

* `temporada_fichaje` -- cuándo ocurrió el traspaso, ej. 2025/2026.
* `temporada_stats`   -- de qué temporada son las métricas: la anterior,
  2024/2025. Es la que corresponde, porque lo que se quiere explicar es el
  destino del fichaje a partir del rendimiento **previo**.
"""

CLAVE = ["operacion_id"]

# --- identificación del fichaje
IDENTIFICACION = [
    "jugador_tm_id", "jugador_fotmob_id", "nombre", "temporada_fichaje",
    "temporada_stats", "operacion_id",
]

# --- la operación
OPERACION = [
    "coste_fichaje_eur", "tipo_operacion",
]

# --- club de destino
DESTINO = [
    "club_destino", "club_destino_id", "club_destino_pais",
    "club_destino_ranking_uefa", "club_destino_coeficiente_uefa",
    "es_destino_top_20",
]

# --- club de origen: el enriquecimiento nuevo
ORIGEN = [
    "club_origen", "club_origen_id", "club_origen_es_filial",
    "club_origen_pais", "club_origen_liga",
    "club_origen_liga_id", "club_origen_liga_es_top5", "club_origen_es_europeo",
    "club_origen_ranking_uefa", "club_origen_coeficiente_uefa",
    "club_origen_es_top_20", "club_origen_es_top_50",
    "club_origen_pais_ranking_uefa", "club_origen_pais_coeficiente_uefa",
]

# --- derivadas del par origen-destino
PAR = [
    "traspaso_domestico", "salto_ranking_uefa", "sube_de_categoria",
]

# --- biografía del jugador
BIOGRAFIA = [
    "edad_al_fichaje", "nacionalidad", "nacionalidad_2", "posicion_tm",
    "posicion_fotmob", "altura_cm", "pie",
]

# --- linaje: cuánta confianza merece la fila
#
# Son cuatro y no seis. `match_metodo` y los dos `cruce_club_*_metodo` se
# fusionaron en `cruce_dudoso`: sus otros valores ya estaban en otra columna
# (`filial` en club_origen_es_filial, `sin_match` en el ranking nulo,
# `sin_estadisticas` en tiene_historial) y el detalle vive en el bronce.
LINAJE = [
    "tiene_historial", "cruce_dudoso", "uefa_actualizado_el", "extraido_el",
]

COLUMNAS_BASE = (IDENTIFICACION + OPERACION + DESTINO + ORIGEN + PAR
                 + BIOGRAFIA + LINAJE)

# Las columnas `stat_*` NO son fijas: se generan a partir de lo que FotMob
# devuelve para cada jugador. Si a un jugador le falta una métrica, esa
# columna queda nula para esa fila. Por eso la validación compara las
# columnas base, no el ancho total.

# Métricas que son porcentajes o promedios: al consolidar los torneos de una
# misma temporada se promedian en vez de sumarse. El resto se suma.
METRICAS_A_PROMEDIAR = {
    "stat_rating", "stat_pass_accuracy", "stat_long_ball_accuracy",
    "stat_cross_accuracy", "stat_dribbles_success_rate", "stat_duels_won_%",
    "stat_aerials_won_%",
}

# Sin estas columnas el dataset no sirve para nada, así que un nulo acá es un
# error de extracción y no un dato faltante legítimo.
#
# Dos que parecen obligatorias y no lo son:
#
#   coste_fichaje_eur -- un fichaje libre, o con la cifra no publicada, es una
#     fila legítima, y ese nulo es el dato. `tipo_operacion` dice cuál de los
#     dos casos es.
#   club_origen -- puede venir nulo, o como "Without Club", cuando el jugador
#     llegó sin contrato. Szczesny a Barcelona en 2024/25 es el ejemplo. Son 82
#     filas, y son una vía de entrada real a un club top, no un error.
OBLIGATORIAS = [
    "operacion_id", "jugador_tm_id", "temporada_fichaje", "nombre",
    "club_destino", "es_destino_top_20", "tipo_operacion",
]

# Umbrales de la validación. El número lo elige alguien: sale de para qué se
# va a usar el dataset, no del dato.
MINIMO_FILAS = 1000
MINIMO_COLUMNAS = 30
