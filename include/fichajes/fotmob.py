"""Cliente de la API interna de FotMob: estadísticas de rendimiento.

FotMob no publica una API documentada, pero la que consume su propio sitio es
accesible y devuelve JSON, así que acá no hay HTML que parsear:

    /api/data/search/suggest?term=...     buscar un jugador por nombre
    /api/data/playerData?id=...           perfil: edad, altura, país, pie
    /api/data/playerStats?playerId=...    métricas detalladas de un torneo

El problema real de esta fuente: el cruce por nombre
----------------------------------------------------
Transfermarkt da el nombre; FotMob hay que buscarlo. Y "Luis Díaz" devuelve
tres jugadores distintos: el del Bayern, uno del Alajuelense y uno de Peñarol.
La versión anterior de este código se quedaba siempre con la primera
sugerencia, sin ninguna verificación, y un acierto silencioso no se distingue
de un error silencioso.

Acá se desambigua con lo que ya sabemos del fichaje: la sugerencia trae el
club actual del jugador (`teamName`), así que se prefiere la que coincide con
el club de destino o con el de origen del traspaso. Cuando no hay forma de
decidir se usa igual la mejor sugerencia, **pero queda anotado el método** en
`match_metodo`, que viaja hasta el dataset final. Un cruce dudoso tiene que
poder filtrarse después; lo que no se puede es no saber cuáles son.

Qué se guarda en bronce
-----------------------
Un archivo por **jugador y temporada de estadísticas**, y nada del fichaje:
los datos del traspaso viven en el bronce de Transfermarkt. Esa separación es
la que permite que las estadísticas de un jugador en 2024/25 se reusen si
aparece en más de un fichaje, sin volver a pedirlas.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.parse
import urllib.request

from .clubes import normalizar

log = logging.getLogger(__name__)

BASE = "https://www.fotmob.com/api/data"
CABECERAS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                   "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"),
    "Accept": "application/json",
}


def _pedir(recurso: str, params: dict, timeout=20, reintentos=2):
    url = f"{BASE}/{recurso}?" + urllib.parse.urlencode(params)
    for intento in range(reintentos + 1):
        try:
            req = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if intento == reintentos:
                log.debug("FotMob falló en %s (%s)", recurso, e)
                return None
            time.sleep(1.5 * (intento + 1))
    return None


# ------------------------------------------------------------- búsqueda

def _variantes(nombre: str) -> list[str]:
    """El nombre completo, después nombre+apellido, después sólo el apellido.
    FotMob a veces registra al jugador con una forma y Transfermarkt con otra."""
    partes = nombre.split()
    variantes = [nombre]
    if len(partes) > 2:
        variantes.append(f"{partes[0]} {partes[-1]}")
    if len(partes) >= 2:
        variantes.append(partes[-1])
    vistas, salida = set(), []
    for v in variantes:
        if v.lower() not in vistas:
            vistas.add(v.lower())
            salida.append(v)
    return salida


def buscar_jugador(nombre: str, club_destino: str | None = None,
                   club_origen: str | None = None) -> tuple[str | None, dict]:
    """Devuelve `(id_fotmob, detalle)` con el método de cruce usado."""
    candidatos: dict[str, dict] = {}
    for termino in _variantes(nombre):
        datos = _pedir("search/suggest", {"term": termino})
        if not datos:
            continue
        try:
            sugerencias = datos[0].get("suggestions") or []
        except (IndexError, AttributeError, TypeError):
            sugerencias = []
        for s in sugerencias:
            if s.get("type") == "player" and not s.get("isCoach") and s.get("id"):
                candidatos.setdefault(str(s["id"]), s)
        if candidatos:
            break                       # con la primera variante que dé algo, alcanza
        time.sleep(0.4)

    if not candidatos:
        return None, {"match_metodo": "sin_sugerencias", "nombre_fotmob": None}

    destino = set(normalizar(club_destino or ""))
    origen = set(normalizar(club_origen or ""))

    def puntaje(s):
        equipo = set(normalizar(s.get("teamName") or ""))
        if equipo and destino and (equipo & destino):
            return 3
        if equipo and origen and (equipo & origen):
            return 2
        return 0

    ordenados = sorted(candidatos.values(),
                       key=lambda s: (puntaje(s), s.get("score") or 0), reverse=True)
    elegido = ordenados[0]
    p = puntaje(elegido)
    if p == 3:
        metodo = "club_destino"
    elif p == 2:
        metodo = "club_origen"
    elif len(ordenados) == 1:
        metodo = "unica_sugerencia"
    else:
        metodo = "primera_sugerencia"       # ambiguo: queda marcado a propósito

    return str(elegido["id"]), {
        "match_metodo": metodo,
        "nombre_fotmob": elegido.get("name"),
        "club_actual_fotmob": elegido.get("teamName"),
        "candidatos": len(ordenados),
    }


# --------------------------------------------------------------- perfil

def _texto(valor):
    if isinstance(valor, dict):
        return valor.get("fallback")
    return None if valor is None else str(valor)


def perfil(jugador_id: str) -> dict | None:
    return _pedir("playerData", {"id": jugador_id})


def biografia(datos_perfil: dict) -> dict:
    """Edad, altura, país y pie hábil, de la lista `playerInformation`.

    La edad que sale de acá es la **de hoy**, no la del fichaje. La edad al
    fichaje la da Transfermarkt en la misma fila del traspaso, que es el dato
    correcto; ésta se conserva sólo para verificar que el jugador cruzado sea
    el que buscábamos.
    """
    bio = {"altura_cm": None, "pais_fotmob": None, "pie": None,
           "edad_hoy": None, "posicion_fotmob": None}

    posicion = datos_perfil.get("positionDescription")
    if isinstance(posicion, dict):
        principal = posicion.get("primaryPosition") or {}
        bio["posicion_fotmob"] = principal.get("label")

    for item in (datos_perfil.get("playerInformation") or []):
        titulo = item.get("title")
        valor = _texto(item.get("value"))
        if valor in (None, ""):
            continue
        if titulo == "Age":
            try:
                bio["edad_hoy"] = int(valor)
            except ValueError:
                pass
        elif titulo == "Height":
            try:
                bio["altura_cm"] = int(str(valor).replace("cm", "").strip())
            except ValueError:
                pass
        elif titulo == "Country":
            bio["pais_fotmob"] = valor
        elif titulo == "Preferred foot":
            bio["pie"] = valor
    return bio


def torneos_de(datos_perfil: dict, temporada: str) -> list[dict]:
    """Torneos con estadísticas detalladas para esa temporada.

    Un jugador puede tener liga, copa y Champions en la misma temporada, y
    FotMob los expone por separado. Se aceptan las dos formas en que nombra la
    temporada: '2024/2025' y, en ligas de año calendario, '2024'.
    """
    validas = {temporada, temporada.split("/")[0]}
    salida = []
    for t in (datos_perfil.get("statSeasons") or []):
        if t.get("seasonName") not in validas:
            continue
        for torneo in (t.get("tournaments") or []):
            if torneo.get("hasDeepStats"):
                salida.append({"nombre": torneo.get("name"),
                               "entry_id": torneo.get("entryId"),
                               "torneo_id": torneo.get("tournamentId")})
    return salida


def metricas_de_torneo(jugador_id: str, entry_id) -> dict:
    """Las métricas de un torneo, aplanadas a {título: valor numérico}.

    FotMob devuelve las métricas en dos lugares y **no siempre manda los dos**:

      topStatCards  el resumen -- goles, asistencias, minutos, rating
      statsSection  el detalle -- pases, duelos, xG, y unas cincuenta más

    Hay jugadores, sobre todo en ligas chicas, para los que viene el resumen y
    no el detalle. Antes esta función cortaba apenas faltaba `statsSection` y
    tiraba también el resumen que sí había llegado, así que esos jugadores
    quedaban como "sin estadísticas" teniendo goles y minutos publicados.
    """
    datos = _pedir("playerStats", {"playerId": jugador_id, "seasonId": entry_id,
                                   "isFirstSeason": "false"})
    if not datos:
        return {}
    seccion = datos.get("statsSection") or {}

    metricas = {}

    def anotar(items):
        for item in (items or []):
            titulo = item.get("title")
            if not titulo:
                continue
            try:
                metricas[titulo] = float(item.get("statValue"))
            except (TypeError, ValueError):
                continue

    tarjetas = datos.get("topStatCards") or datos.get("topStatCard") or {}
    anotar(tarjetas.get("items"))
    for bloque in (seccion.get("items") or []):
        anotar(bloque.get("items"))
    return metricas


# ------------------------------------------------- registro para el bronce

def registro_de_temporada(nombre_tm: str, jugador_tm_id: str, temporada: str,
                          club_destino: str | None, club_origen: str | None,
                          pausa=1.0) -> dict | None:
    """Todo lo que FotMob sabe de un jugador en una temporada.

    Devuelve `None` sólo si no se pudo identificar al jugador o si no hay
    ningún torneo con estadísticas detalladas: en los dos casos no hay nada
    que guardar, y el motivo queda en el log.
    """
    jugador_id, detalle = buscar_jugador(nombre_tm, club_destino, club_origen)
    if not jugador_id:
        log.info("sin cruce en FotMob: %s", nombre_tm)
        return None

    datos = perfil(jugador_id)
    if not datos:
        log.info("FotMob no devolvió perfil de %s (id %s)", nombre_tm, jugador_id)
        return None

    torneos = torneos_de(datos, temporada)
    if not torneos:
        log.info("%s no tiene estadísticas detalladas en %s", nombre_tm, temporada)
        return None

    registro = {
        "jugador_fotmob_id": jugador_id,
        "jugador_tm_id": jugador_tm_id,
        "nombre_tm": nombre_tm,
        "temporada_stats": temporada,
        "biografia": biografia(datos),
        "torneos": [],
        **detalle,
    }
    for torneo in torneos:
        metricas = metricas_de_torneo(jugador_id, torneo["entry_id"])
        if metricas:
            registro["torneos"].append({**torneo, "metricas": metricas})
        time.sleep(pausa)

    if not registro["torneos"]:
        return None
    return registro
