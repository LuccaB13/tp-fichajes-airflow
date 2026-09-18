"""Cruce entre el ranking de UEFA y el catálogo de Transfermarkt.

El problema
-----------
UEFA publica la posición y el coeficiente, pero no el id de Transfermarkt.
Transfermarkt publica el id -- que es lo único que arma la URL de fichajes --
pero su ranking es propio. No hay una clave compartida: hay que cruzar por
nombre, y los nombres no coinciden literalmente.

    Transfermarkt            UEFA
    Inter Milan              FC Internazionale Milano
    Ajax Amsterdam           AFC Ajax
    Red Bull Salzburg        FC Salzburg
    Athletic Bilbao          Athletic Club

La estrategia, en cuatro pasos y en este orden
----------------------------------------------
1. **Normalizar**: sin tildes, en minúsculas, y sin las siglas que no
   distinguen nada (fc, cf, sc, ac, sk, pfc...). "FC Bayern München" y
   "Bayern Munich" quedan en "bayern munchen" y "bayern munich".
2. **Bloquear por país**: sólo se compara contra clubes del mismo país. Es lo
   que evita que "Zira FC" (Azerbaiyán) matchee con "Gżira United" (Malta) o
   "ETO FC" (Hungría) con "Everton FC".
3. **Subconjunto de tokens**: si un nombre está contenido en el otro, es el
   mismo club. Resuelve el caso más común, que es que una fuente agregue la
   ciudad y la otra no ("Ajax Amsterdam" ⊇ "Ajax").
4. **Aproximado**: recién acá se mide parecido de texto, y sólo dentro del
   país. Absorbe transliteraciones ("Zorya Lugansk" / "FC Zorya Luhansk").

Medido sobre los 500 clubes únicos del catálogo, el 17/09/2026: 394 exactos,
81 por subconjunto, 11 aproximados y 14 sin cruce = **97,2% de cobertura**, con
los 20 primeros de UEFA cruzando todos. De los 14 que quedan afuera, 3 son
clubes rusos —que están excluidos de las competiciones de UEFA desde 2022 y por
lo tanto no figuran en el ranking, así que no cruzarlos es correcto— y el resto
son clubes chicos. Todos quedan registrados en el reporte de cruce
(`dim_clubes_sin_cruce.csv`): no se esconden, se cuentan.
"""
from __future__ import annotations

import logging
import re
import unicodedata
from difflib import SequenceMatcher

log = logging.getLogger(__name__)

# Siglas y sufijos que aparecen en un nombre de club y no lo identifican.
# Sacarlas es lo que hace que "SK Rapid" y "Rapid Vienna" se toquen.
RUIDO = {
    "fc", "cf", "afc", "ac", "sc", "cd", "ss", "ssc", "as", "us", "ud", "sv",
    "vfb", "vfl", "tsg", "fsv", "bsc", "sk", "fk", "nk", "hnk", "gnk", "bk",
    "if", "ik", "cfr", "rc", "rcd", "sd", "club", "clube", "cp", "sl", "scp",
    "kv", "kaa", "rsc", "krc", "kvc", "ogc", "osc", "sco", "pfc", "pfk", "cs",
    "csm", "mks", "ks", "fcs", "ca", "kf", "tsv", "acf", "asd", "ssd", "the",
    "de", "ii", "r", "psv", "pfk",
}

# Transfermarkt y UEFA escriben distinto el nombre de cuatro países. Monaco no
# es una asociación de UEFA: AS Monaco compite dentro de la federación
# francesa, y por eso se lo mapea ahí.
PAIS_ALIAS = {
    "czech republic": "czechia",
    "bosnia herzegovina": "bosnia and herzegovina",
    "ireland": "republic of ireland",
    "monaco": "france",
    "turkey": "türkiye",
}


def _texto(valor) -> str:
    """Todo lo que no sea una cadena con contenido es cadena vacía.

    Hace falta porque pandas representa los faltantes como `float('nan')`, y
    un NaN que llega hasta acá revienta con AttributeError en vez de comportarse
    como el dato ausente que es.
    """
    if valor is None or not isinstance(valor, str):
        return ""
    return valor


def normalizar(texto) -> list[str]:
    """Nombre de club -> lista de tokens significativos."""
    t = unicodedata.normalize("NFKD", _texto(texto))
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    for a, b in (("ø", "o"), ("đ", "d"), ("ł", "l"), ("ß", "ss"),
                 ("æ", "ae"), ("ı", "i"), ("þ", "th"), ("ð", "d")):
        t = t.replace(a, b)
    t = re.sub(r"\(.*?\)", " ", t)          # "(- 2025)", "( - 2024)"
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    return [x for x in t.split() if x and x not in RUIDO]


def normalizar_pais(pais) -> str:
    p = unicodedata.normalize("NFKD", _texto(pais).lower())
    p = "".join(c for c in p if not unicodedata.combining(c))
    p = re.sub(r"[^a-zü ]", " ", p)
    p = re.sub(r"\s+", " ", p).strip()
    return PAIS_ALIAS.get(p, p)


class Indice:
    """Índice de clubes de UEFA, listo para consultar por nombre y país."""

    def __init__(self, filas_uefa: list[dict], filas_asociaciones: list[dict]):
        self.clubes = filas_uefa
        self.por_pais: dict[str, list[dict]] = {}
        self.todos: list[dict] = []
        for fila in filas_uefa:
            alias = {fila.get("uefa_nombre"), fila.get("uefa_nombre_oficial"),
                     fila.get("uefa_nombre_internacional"), fila.get("uefa_nombre_corto")}
            entrada = {
                "fila": fila,
                "pais": normalizar_pais(fila.get("uefa_pais")),
                "tokens": [normalizar(a) for a in alias if a],
            }
            entrada["tokens"] = [t for t in entrada["tokens"] if t]
            self.todos.append(entrada)
            self.por_pais.setdefault(entrada["pais"], []).append(entrada)

        self.asociaciones = {normalizar_pais(a["pais"]): a for a in filas_asociaciones}

    # ------------------------------------------------------------------
    def es_europeo(self, pais: str) -> bool:
        """Europeo = el país es una de las 55 asociaciones miembro de UEFA.

        Sale del propio ranking de asociaciones, no de una lista escrita a
        mano: si mañana UEFA incorpora a alguien, el dato se actualiza solo.
        """
        return normalizar_pais(pais) in self.asociaciones

    def asociacion(self, pais: str) -> dict:
        return self.asociaciones.get(normalizar_pais(pais), {})

    # ------------------------------------------------------------------
    def buscar(self, nombre: str, pais: str | None = None) -> tuple[dict | None, str]:
        """Devuelve `(fila_uefa, metodo)`. `metodo` queda en el dataset para
        que un cruce dudoso se pueda auditar después."""
        mios = [t for t in (normalizar(nombre),) if t]
        if not mios:
            return None, "sin_nombre"
        mis_tokens = mios[0]
        mi_conjunto = set(mis_tokens)

        clave_pais = normalizar_pais(pais) if pais else None
        candidatos = self.por_pais.get(clave_pais) if clave_pais else None
        con_pais = bool(candidatos)
        if not candidatos:
            # País desconocido, o país sin clubes en el ranking: se busca en
            # todo el índice pero exigiendo más parecido.
            candidatos = self.todos

        # 1. exacto
        for c in candidatos:
            if any(t == mis_tokens for t in c["tokens"]):
                return c["fila"], "exacto"

        # 2. subconjunto de tokens, sólo si estamos bloqueados por país:
        #    sin esa restricción "Inter" matchearía con medio continente.
        if con_pais:
            for c in candidatos:
                for t in c["tokens"]:
                    ts = set(t)
                    if ts and (ts <= mi_conjunto or mi_conjunto <= ts):
                        return c["fila"], "subconjunto"

        # 3. aproximado
        umbral = 0.82 if con_pais else 0.93
        mejor, puntaje = None, 0.0
        for c in candidatos:
            for t in c["tokens"]:
                p = SequenceMatcher(None, " ".join(mis_tokens), " ".join(t)).ratio()
                if p > puntaje:
                    mejor, puntaje = c, p
        if mejor is not None and puntaje >= umbral:
            return mejor["fila"], f"aproximado:{puntaje:.2f}"

        return None, "sin_match"


def construir_catalogo(clubes_tm: list[dict], indice: Indice,
                       tope: int | None = None) -> tuple[list[dict], list[dict]]:
    """Catálogo de clubes a procesar, ordenado por el ranking de UEFA.

    Devuelve `(catalogo, sin_cruce)`. El orden importa: el DAG recorre la
    lista de arriba hacia abajo, así que si una corrida se interrumpe, lo que
    alcanzó a bajar son los clubes que más pesan.

    `tope` recorta por posición de UEFA, no por posición de Transfermarkt.
    """
    catalogo, sin_cruce = [], []
    # Transfermarkt repite clubes entre páginas del ranking, y dos entradas
    # suyas pueden cruzar contra el mismo club de UEFA (por ejemplo varias
    # fichas históricas del mismo equipo). Nos quedamos con la primera de cada
    # una: la lista viene ordenada por el ranking de Transfermarkt, así que la
    # primera es la ficha vigente.
    ids_vistos, uefa_vistos = set(), set()

    for club in clubes_tm:
        if club["tm_club_id"] in ids_vistos:
            continue
        ids_vistos.add(club["tm_club_id"])

        fila, metodo = indice.buscar(club["tm_nombre_oficial"], club.get("tm_pais"))
        if fila is None:
            fila, metodo = indice.buscar(club["tm_nombre"], club.get("tm_pais"))
        if fila is None:
            sin_cruce.append({**club, "cruce_metodo": metodo})
            continue
        if fila["uefa_club_id"] in uefa_vistos:
            sin_cruce.append({**club, "cruce_metodo": "duplicado:" + metodo})
            continue
        uefa_vistos.add(fila["uefa_club_id"])

        catalogo.append({
            **club,
            "uefa_ranking": fila["uefa_ranking"],
            "uefa_coeficiente": fila["uefa_coeficiente"],
            "uefa_pais": fila["uefa_pais"],
            "uefa_nombre_oficial": fila["uefa_nombre_oficial"],
            "cruce_metodo": metodo,
            "es_top_20": bool(fila["uefa_ranking"] and fila["uefa_ranking"] <= 20),
        })

    catalogo.sort(key=lambda c: c["uefa_ranking"] or 10_000)
    if tope:
        catalogo = [c for c in catalogo if (c["uefa_ranking"] or 10_000) <= tope]

    log.info("catálogo: %s clubes cruzados, %s sin cruce, tope de ranking UEFA=%s",
             len(catalogo), len(sin_cruce), tope)
    if sin_cruce:
        log.warning("sin cruce contra UEFA (quedan afuera del catálogo): %s",
                    ", ".join(c["tm_nombre_oficial"] for c in sin_cruce[:20]))
    return catalogo, sin_cruce
