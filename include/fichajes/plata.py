"""Capa plata: del bronce crudo a una tabla tipada, una fila por fichaje.

Esta capa **no toca la red**. Todo lo que necesita ya está en disco:

    bronce de Transfermarkt  ->  el fichaje: quién, de dónde, a dónde, cuánto
    bronce de FotMob         ->  el rendimiento previo del jugador
    bronce de UEFA           ->  ranking y coeficiente de los dos clubes

Esa es la propiedad que hace valiosa la separación en capas: se puede correr
cien veces mientras se depura el parseo o se agrega una columna derivada, sin
volver a pedirle nada a ninguna de las tres fuentes.

El enriquecimiento del club de origen
-------------------------------------
Antes, del club de origen sólo se guardaba el nombre, y con un nombre suelto
no se puede analizar nada: no se sabe si el jugador venía de la Premier o de
la segunda de Bélgica. Ahora cada fila lleva, del club de origen:

    país, liga y código de liga      de la misma fila de Transfermarkt
    si la liga es una de las cinco   derivado del código de liga
    si el club es europeo            país ∈ las 55 asociaciones de UEFA
    ranking y coeficiente UEFA       cruce contra el ranking de diez temporadas
    si está entre los 20 / 50        derivado del ranking
    ranking y coeficiente del país   ranking de asociaciones de UEFA

Y del par origen-destino salen tres columnas más: si el traspaso fue dentro
del mismo país, cuántas posiciones de ranking saltó el jugador, y si ese salto
fue hacia arriba.

Dónde termina la plata
----------------------
Esta capa describe el fichaje; no arma features. La diferencia importa y es
fácil de cruzar sin darse cuenta.

Un mapeo determinístico de una columna --`club_origen_liga_es_top5` sale del
código de liga y nada más-- es descripción, y va acá. Una columna que depende
de **cómo se agregan las demás filas** es una feature, y no va acá: un puntaje
de rendimiento normalizado por posición, por ejemplo, se calcula contra la
media y el desvío del grupo, así que su valor cambia según qué filas entren al
análisis. Congelarlo en la plata es decidir por adelantado una pregunta que le
toca al análisis.

Se probó poner acá un `score_posicion` (z de minutos, partidos y rating dentro
del grupo de posición) y se sacó por ese motivo. Vive en el notebook de
análisis, junto con la decisión de sobre qué población se normaliza.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from . import bronce, transfermarkt as tm, uefa
from .clubes import Indice
from .esquema import CLAVE, COLUMNAS_BASE, METRICAS_A_PROMEDIAR

log = logging.getLogger(__name__)


# --------------------------------------------------------------- lectura

def _uefa_mas_reciente() -> tuple[dict, dict, str]:
    """El snapshot de UEFA más nuevo que haya en bronce."""
    particiones = sorted((bronce.BRONCE_DIR / "uefa").glob("actualizacion=*"))
    if not particiones:
        raise FileNotFoundError(
            "no hay bronce de UEFA. Corré el DAG completo al menos una vez: "
            "el ranking es lo que define la columna objetivo.")
    ultima = particiones[-1]
    crudo_clubes = bronce.leer_json(ultima / "clubes_diez_temporadas.json.gz")
    crudo_asoc = bronce.leer_json(ultima / "asociaciones.json.gz")
    return crudo_clubes, crudo_asoc, ultima.name.split("=", 1)[1]


def _altas_del_bronce(temporadas: list[int] | None = None) -> pd.DataFrame:
    """Todas las altas guardadas en el bronce de Transfermarkt.

    Se parsea acá, no en la tarea que baja: el bronce guarda el byte tal como
    vino y esta capa lo interpreta. Si el parseo tiene un bug, se corrige y se
    vuelve a correr sin pedirle nada a Transfermarkt.
    """
    filas = []
    for ruta in bronce.listar("transfermarkt/altas/club=*/temporada=*/altas.html.gz"):
        club_id = ruta.parent.parent.name.split("=", 1)[1]
        temporada = int(ruta.parent.name.split("=", 1)[1])
        if temporadas and temporada not in temporadas:
            continue
        try:
            html = bronce.leer_texto(ruta)
        except OSError as e:
            log.warning("no se pudo leer %s: %s", ruta, e)
            continue
        filas.extend(tm.parsear_altas(html, club_id, temporada))
    log.info("bronce de Transfermarkt: %s altas leídas", len(filas))
    return pd.DataFrame(filas)


def _stats_del_bronce() -> dict[tuple[str, str], dict]:
    """Estadísticas de FotMob, indexadas por (jugador_tm_id, temporada_stats)."""
    indice = {}
    for ruta in bronce.listar("fotmob/temporada=*/jugador_*.json.gz"):
        try:
            registro = bronce.leer_json(ruta)
        except OSError as e:
            log.warning("no se pudo leer %s: %s", ruta, e)
            continue
        clave = (str(registro.get("jugador_tm_id")), registro.get("temporada_stats"))
        indice[clave] = registro
    log.info("bronce de FotMob: %s jugadores-temporada leídos", len(indice))
    return indice


# ------------------------------------------------------------ agregación

#: FotMob publica la misma métrica con dos títulos distintos: "Conceded" y
#: "Goals conceded" son idénticas en las 2.244 filas que pudimos comparar.
#: Quedarse con las dos sería arrastrar una columna duplicada para siempre.
METRICAS_DUPLICADAS = {"stat_conceded"}


def _metricas_consolidadas(registro: dict) -> dict:
    """Un jugador puede tener liga, copa y Champions en la misma temporada.

    Las métricas acumulativas (goles, minutos) se suman; los porcentajes y el
    rating se promedian, porque sumarlos no significaría nada.

    Limitación conocida, que conviene decir antes de que la pregunten: el
    promedio **no está ponderado por minutos**. Un jugador con 3000 minutos de
    liga y 90 de copa pesa igual en los dos torneos. Corregirlo es trabajo de
    la capa oro, donde se arman las features del modelo.
    """
    acumuladas: dict[str, float] = {}
    promediadas: dict[str, list[float]] = {}
    for torneo in registro.get("torneos") or []:
        for titulo, valor in (torneo.get("metricas") or {}).items():
            columna = "stat_" + titulo.replace(" ", "_").lower()
            if columna in METRICAS_DUPLICADAS:
                continue
            if columna in METRICAS_A_PROMEDIAR:
                promediadas.setdefault(columna, []).append(valor)
            else:
                acumuladas[columna] = acumuladas.get(columna, 0.0) + valor
    for columna, valores in promediadas.items():
        acumuladas[columna] = float(np.mean(valores)) if valores else np.nan
    return acumuladas


# -------------------------------------------------------------- armado

#: Operaciones que NO son un fichaje y por eso no entran al dataset.
#:
#: `fin_de_cesion` es un jugador que **vuelve a su propio club** después de un
#: préstamo -- el texto literal de Transfermarkt es "End of loan 30/06/2024".
#: No hubo decisión de fichar a nadie, y además `club_origen` ahí es *dónde
#: estuvo cedido*, así que enriquecerlo mide otra cosa. Son el 38% de las altas.
TIPOS_EXCLUIDOS = ("fin_de_cesion",)


def consolidar(temporadas: list[int] | None = None,
               excluir_tipos: tuple[str, ...] = TIPOS_EXCLUIDOS,
               exigir_estadisticas: bool = False) -> str | None:
    """Arma el dataset plata y devuelve la ruta del CSV, o None si no hay nada.

    Entran **todos los fichajes**, tengan o no importe publicado. Y el importe
    nulo no es un faltante: `coste_fichaje_eur` está presente exactamente en
    las compras y las cesiones con cargo, y ausente exactamente en las
    cesiones, los libres y los desconocidos -- 7.644 de 7.645 filas. Un pase
    libre no tiene monto porque no hay monto. Es un **nulo estructural**.

    Por eso filtrar por "tiene precio" no es limpiar datos, es filtrar por
    tipo de operación con otro nombre, y sale caro: se lleva el 61,6% de las
    filas y el 33,1% de los positivos, sube la clase positiva del 8,0% al
    13,9% por pura selección, y deja la muestra en 90% compras con los
    filiales derrumbados del 19,7% al 2,7%. Los efectos no mejoran: el
    coeficiente UEFA del país de origen baja de d = 1,076 a 0,786, o sea de
    verde a amarillo.

    `exigir_estadisticas` sí es una restricción defendible --pierde el 31,6%
    de las filas pero sólo el 13,4% de los positivos-- pero viene apagada a
    propósito. La plata es la capa completa; el análisis parte la población
    y lo declara, que es lo que permite mostrar el contraste. Qué filas usar
    es una decisión del análisis, no del pipeline: el trabajo del pipeline es
    no perder datos.
    """
    crudo_clubes, crudo_asoc, actualizado = _uefa_mas_reciente()
    filas_uefa = uefa.a_filas_clubes(crudo_clubes)
    filas_asoc = uefa.a_filas_asociaciones(crudo_asoc)
    indice = Indice(filas_uefa, filas_asoc)

    altas = _altas_del_bronce(temporadas)
    if altas.empty:
        log.warning("el bronce de Transfermarkt está vacío: nada que consolidar")
        return None

    antes = len(altas)
    if excluir_tipos:
        altas = altas[~altas["tipo_operacion"].isin(excluir_tipos)].copy()
        log.info("%s altas, %s fichajes (%s descartadas por tipo de operación: %s)",
                 antes, len(altas), antes - len(altas), ", ".join(excluir_tipos))
    if altas.empty:
        return None
    con_importe = altas["coste_fichaje_eur"].notna().sum()
    log.info("  de esos, %s con importe publicado (%.0f%%)",
             con_importe, 100 * con_importe / len(altas))

    stats = _stats_del_bronce()

    # --- catálogo de destino: id de Transfermarkt -> datos del club
    destinos = {}
    for ruta in bronce.listar("transfermarkt/ranking/actualizacion=*/pagina_*.html.gz"):
        for club in tm.parsear_ranking(bronce.leer_texto(ruta)):
            destinos.setdefault(club["tm_club_id"], club)

    cache_cruce: dict[tuple[str, str], tuple[dict | None, str]] = {}

    def cruzar(nombre, pais):
        # Ojo con los nulos de pandas: `float('nan') or ""` devuelve el NaN, no
        # la cadena vacía, y dos NaN distintos no comparten clave de caché.
        clave = ("" if pd.isna(nombre) else nombre, "" if pd.isna(pais) else pais)
        if clave not in cache_cruce:
            cache_cruce[clave] = indice.buscar(nombre, pais)
        return cache_cruce[clave]

    ahora = datetime.now(timezone.utc).isoformat(timespec="seconds")
    registros, sin_stats = [], 0

    for alta in altas.to_dict("records"):
        temporada_fichaje = tm.etiqueta_temporada(alta["temporada_tm"])
        temporada_stats = tm.etiqueta_temporada(alta["temporada_tm"] - 1)

        club_destino = destinos.get(str(alta["club_destino_id"]), {})
        nombre_destino = club_destino.get("tm_nombre_oficial")
        pais_destino = club_destino.get("tm_pais")

        fila_destino, metodo_destino = cruzar(nombre_destino, pais_destino)
        asociacion = indice.asociacion(alta["club_origen_pais"])

        # Un filial no cruza contra el ranking: "Chelsea FC U21" no es Chelsea.
        # El cruce por subconjunto de tokens los confundía, y el jugador salía
        # como "viene del 8º club de Europa" cuando en realidad es un canterano.
        # Son dos fenómenos distintos y el dataset tiene que poder separarlos.
        if bool(alta.get("club_origen_es_filial")):
            fila_origen, metodo_origen = None, "filial"
        else:
            fila_origen, metodo_origen = cruzar(alta["club_origen"],
                                                alta["club_origen_pais"])

        ranking_destino = fila_destino["uefa_ranking"] if fila_destino else None
        ranking_origen = fila_origen["uefa_ranking"] if fila_origen else None

        registro = {
            "jugador_tm_id": alta["jugador_tm_id"],
            "nombre": alta["jugador_nombre"],
            "temporada_fichaje": temporada_fichaje,
            "temporada_stats": temporada_stats,
            "operacion_id": alta["operacion_id"],

            # El importe viene nulo en los fichajes libres y en los que no
            # publicaron la cifra. Ese nulo es el dato, no un defecto.
            "coste_fichaje_eur": alta["coste_fichaje_eur"],
            "tipo_operacion": alta["tipo_operacion"],

            "club_destino": nombre_destino or alta["club_destino_id"],
            "club_destino_id": alta["club_destino_id"],
            "club_destino_pais": pais_destino,
            "club_destino_ranking_uefa": ranking_destino,
            "club_destino_coeficiente_uefa": (fila_destino["uefa_coeficiente"]
                                              if fila_destino else None),
            # La columna objetivo. Antes salía del orden del ranking propio de
            # Transfermarkt; ahora sale del coeficiente de clubes de UEFA de
            # las últimas diez temporadas, que es una medida publicada y
            # estable en vez de un recorte de una tabla que se reordena sola.
            "es_destino_top_20": bool(ranking_destino and ranking_destino <= 20),

            "club_origen": alta["club_origen"],
            "club_origen_id": alta["club_origen_id"],
            "club_origen_es_filial": alta["club_origen_es_filial"],
            "club_origen_pais": alta["club_origen_pais"],
            "club_origen_liga": alta["club_origen_liga"],
            "club_origen_liga_id": alta["club_origen_liga_id"],
            "club_origen_liga_es_top5": alta["club_origen_liga_es_top5"],
            "club_origen_es_europeo": indice.es_europeo(alta["club_origen_pais"]),
            "club_origen_ranking_uefa": ranking_origen,
            "club_origen_coeficiente_uefa": (fila_origen["uefa_coeficiente"]
                                             if fila_origen else None),
            "club_origen_es_top_20": bool(ranking_origen and ranking_origen <= 20),
            "club_origen_es_top_50": bool(ranking_origen and ranking_origen <= 50),
            "club_origen_pais_ranking_uefa": asociacion.get("pais_ranking_uefa"),
            "club_origen_pais_coeficiente_uefa": asociacion.get("pais_coeficiente_uefa"),

            "edad_al_fichaje": alta["edad_al_fichaje"],
            "nacionalidad": alta["nacionalidad"],
            "nacionalidad_2": alta["nacionalidad_2"],
            "posicion_tm": alta["posicion_tm"],

            "uefa_actualizado_el": crudo_clubes.get("actualizado") or actualizado,
            "extraido_el": ahora,
        }

        # --- derivadas del par
        registro["traspaso_domestico"] = bool(
            alta["club_origen_pais"] and pais_destino
            and alta["club_origen_pais"] == pais_destino)
        if ranking_origen and ranking_destino:
            salto = ranking_origen - ranking_destino
            registro["salto_ranking_uefa"] = salto
            registro["sube_de_categoria"] = bool(salto > 0)
        else:
            registro["salto_ranking_uefa"] = None
            registro["sube_de_categoria"] = None

        # --- rendimiento de la temporada anterior
        rendimiento = stats.get((str(alta["jugador_tm_id"]), temporada_stats))
        # `tiene_historial` no es un defecto del dato: los fichajes sin
        # estadísticas previas son, en su mayoría, jugadores muy jóvenes que
        # todavía no acumularon minutos profesionales. Medido sobre una muestra
        # estratificada: edad mediana 20 contra 23, y club de origen en el
        # puesto 212 contra 45. Es una vía de entrada a un club top, no ruido.
        registro["tiene_historial"] = rendimiento is not None
        metodo_jugador = "sin_estadisticas"
        if rendimiento is None:
            sin_stats += 1
            registro["jugador_fotmob_id"] = None
            bio = {}
        else:
            registro["jugador_fotmob_id"] = rendimiento.get("jugador_fotmob_id")
            metodo_jugador = rendimiento.get("match_metodo")
            bio = rendimiento.get("biografia") or {}
            registro.update(_metricas_consolidadas(rendimiento))

        registro["posicion_fotmob"] = bio.get("posicion_fotmob")
        registro["altura_cm"] = bio.get("altura_cm")
        registro["pie"] = bio.get("pie")

        # Una sola columna de linaje en lugar de tres. El detalle de *cómo*
        # cruzó cada cosa queda en el bronce, que es donde corresponde: la
        # plata se queda con la conclusión, no con el procedimiento.
        #
        # Dudosa quiere decir: o el jugador se eligió entre homónimos sin poder
        # verificar cuál era, o alguno de los dos clubes cruzó sólo por
        # parecido de texto. Los otros valores no hacen falta acá porque ya
        # están en otra columna: `filial` está en `club_origen_es_filial`,
        # `sin_match` se ve en el ranking nulo, y `sin_estadisticas` en
        # `tiene_historial`.
        registro["cruce_dudoso"] = bool(
            metodo_jugador == "primera_sugerencia"
            or str(metodo_destino).startswith("aproximado")
            or str(metodo_origen).startswith("aproximado"))

        registros.append(registro)

    df = pd.DataFrame(registros)
    log.info("%s fichajes; %s sin estadísticas de FotMob (%.1f%%)",
             len(df), sin_stats, 100 * sin_stats / max(len(df), 1))

    # Se deduplica por `operacion_id`, el id que Transfermarkt le da a cada
    # traspaso. Es la clave natural del fichaje, y es importante que sea ésa y
    # no (jugador, temporada): un jugador puede ser transferido dos veces en la
    # misma temporada -- Álvaro Morata en 2024/25 es el caso de manual-- y con
    # la clave vieja el segundo traspaso se perdía en silencio.
    antes = len(df)
    df = df.drop_duplicates(subset=CLAVE, keep="last").reset_index(drop=True)
    if antes != len(df):
        log.info("%s filas con la misma operación, deduplicadas", antes - len(df))

    # Las filas sin estadísticas no aportan la mitad del análisis, pero por
    # defecto se conservan: cuántas son y de dónde vienen es un dato de
    # calidad, y borrarlas escondería un sesgo (FotMob cubre peor las ligas
    # chicas, y los juveniles no tienen temporada senior que medir).
    if exigir_estadisticas:
        antes = len(df)
        df = df[df["tiene_historial"].astype("boolean").fillna(False)]
        df = df.reset_index(drop=True)
        log.info("exigir_estadisticas: %s -> %s filas (-%.1f%%)",
                 antes, len(df), 100 * (1 - len(df) / max(antes, 1)))

    df = _ordenar_columnas(df)
    df = _tipar(df)

    bronce.PLATA_DIR.mkdir(parents=True, exist_ok=True)
    destino = bronce.PLATA_DIR / "dataset_fichajes_silver.csv"
    df.to_csv(destino, index=False, encoding="utf-8")
    log.info("capa plata: %s filas x %s columnas -> %s", len(df), df.shape[1], destino)
    return str(destino)


def _ordenar_columnas(df: pd.DataFrame) -> pd.DataFrame:
    base = [c for c in COLUMNAS_BASE if c in df.columns]
    stats = sorted(c for c in df.columns if c.startswith("stat_"))
    resto = [c for c in df.columns if c not in base and c not in stats]
    return df[base + resto + stats]


def _tipar(df: pd.DataFrame) -> pd.DataFrame:
    enteros = ["edad_al_fichaje", "coste_fichaje_eur", "altura_cm",
               "club_destino_ranking_uefa", "club_origen_ranking_uefa",
               "club_origen_pais_ranking_uefa", "salto_ranking_uefa"]
    for c in enteros:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64")
    booleanos = ["es_destino_top_20", "club_origen_es_europeo",
                 "club_origen_es_top_20", "club_origen_es_top_50",
                 "club_origen_liga_es_top5", "club_origen_es_filial",
                 "traspaso_domestico", "tiene_historial", "cruce_dudoso"]
    for c in booleanos:
        if c in df.columns:
            df[c] = df[c].astype("boolean")
    return df


def escribir_dimension_clubes(catalogo: list[dict], sin_cruce: list[dict]) -> str:
    """Guarda el catálogo cruzado y, aparte, los clubes que no cruzaron.

    El archivo de los que no cruzaron es tan importante como el otro: es lo
    que permite decir en la defensa cuántos clubes quedaron afuera y por qué,
    en vez de responder "no sé".
    """
    bronce.PLATA_DIR.mkdir(parents=True, exist_ok=True)
    destino = bronce.PLATA_DIR / "dim_clubes.csv"
    pd.DataFrame(catalogo).to_csv(destino, index=False, encoding="utf-8")
    if sin_cruce:
        pd.DataFrame(sin_cruce).to_csv(
            bronce.PLATA_DIR / "dim_clubes_sin_cruce.csv", index=False, encoding="utf-8")
    log.info("dimensión de clubes: %s cruzados, %s sin cruce -> %s",
             len(catalogo), len(sin_cruce), destino)
    return str(destino)
