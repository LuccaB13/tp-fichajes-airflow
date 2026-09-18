"""Cliente de la API de coeficientes de UEFA.

Por qué la API y no la página
-----------------------------
La tabla que se ve en
https://es.uefa.com/nationalassociations/uefarankings/tenyears/?year=2027
la arma JavaScript, y además `es.uefa.com` no le contesta a un cliente HTTP
pelado: la conexión TLS se establece y después el servidor no responde nunca
(probado con `urllib` y con `requests`, 17/09/2026). Scrapearla exigiría un
navegador headless.

El mismo dato sale del backend que alimenta esa página, que sí responde a un
cliente común y devuelve JSON::

    https://comp.uefa.com/v2/coefficients
        ?coefficientType=MEN_CLUB_TEN_YEARS   <- coeficiente de clubes, 10 temporadas
        &coefficientRange=OVERALL             <- acumulado, no una temporada suelta
        &seasonYear=2027                      <- ventana que termina en 2026/27
        &language=EN&page=1&pagesize=500

Se pide en inglés a propósito: Transfermarkt también se consulta en su dominio
internacional, y que las dos fuentes usen la misma forma del nombre es lo que
hace que el cruce funcione (ver el registro de cambios).

Los valores de esos dos enum salen del propio contrato de la API, publicado en
https://comp.uefa.com/v3/api-docs — no son adivinados.

Verificado contra la captura de la página el 17/09/2026: Bayern 267.500,
Real Madrid 246.500, Man City 240.500, Liverpool 239.000, Paris 233.000.

Qué devuelve, y por qué importa
-------------------------------
* `lastUpdateDate` -- cuándo actualizó UEFA los coeficientes. Es la señal de
  frescura que usa el cortocircuito del DAG para decidir si hay algo nuevo.
* Por club: posición, coeficiente, país, id de UEFA y varias formas del nombre.
  Las cuatro formas del nombre son lo que hace posible el cruce con
  Transfermarkt (ver `clubes.py`).
* Por asociación (los 55 miembros de UEFA): posición y coeficiente del país.
  De acá sale el "es europeo" del club de origen: europeo = su país es una
  asociación miembro, no una lista escrita a mano.
"""
from __future__ import annotations

import logging
import time
import urllib.parse
import urllib.request
import json

log = logging.getLogger(__name__)

BASE = "https://comp.uefa.com/v2/coefficients"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
PAGINA = 500


def _pedir(params: dict, timeout=45, reintentos=3) -> dict:
    url = BASE + "?" + urllib.parse.urlencode(params)
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as e:
            if intento == reintentos - 1:
                raise
            log.warning("UEFA no respondió (%s). Reintento %s/%s.",
                        e, intento + 2, reintentos)
            time.sleep(2 * (intento + 1))
    raise RuntimeError("inalcanzable")


def _paginar(tipo: str, anio: int, idioma: str) -> tuple[str, list[dict]]:
    """Devuelve (lastUpdateDate, miembros). Pagina hasta agotar la colección."""
    miembros, pagina, actualizado = [], 1, None
    while True:
        d = _pedir({"coefficientType": tipo, "coefficientRange": "OVERALL",
                    "seasonYear": anio, "language": idioma,
                    "page": pagina, "pagesize": PAGINA})
        datos = d["data"]
        actualizado = actualizado or datos.get("lastUpdateDate")
        lote = datos.get("members") or []
        miembros.extend(lote)
        total = int(d.get("meta", {}).get("collection", {})
                    .get("totalElements", len(miembros)))
        if len(miembros) >= total or not lote:
            break
        pagina += 1
        time.sleep(0.3)
    return actualizado, miembros


def clubes_diez_temporadas(anio=2027, idioma="EN") -> dict:
    """Ranking de clubes por coeficiente de las últimas diez temporadas.

    `anio` es la temporada en la que termina la ventana: 2027 = ventana que
    cierra en 2026/27. Fijarlo hace la corrida reproducible.
    """
    actualizado, miembros = _paginar("MEN_CLUB_TEN_YEARS", anio, idioma)
    log.info("UEFA clubes (10 temporadas, %s): %s clubes, actualizado %s",
             anio, len(miembros), actualizado)
    return {"actualizado": actualizado, "anio": anio, "idioma": idioma,
            "miembros": miembros}


def asociaciones(anio=2027, idioma="EN") -> dict:
    """Coeficiente por asociación nacional: los 55 miembros de UEFA."""
    actualizado, miembros = _paginar("MEN_ASSOCIATION", anio, idioma)
    log.info("UEFA asociaciones (%s): %s miembros, actualizado %s",
             anio, len(miembros), actualizado)
    return {"actualizado": actualizado, "anio": anio, "idioma": idioma,
            "miembros": miembros}


def ultima_actualizacion(anio=2027) -> str | None:
    """Sólo la fecha de actualización, con una request mínima.

    Es lo que consulta el sensor: no baja los 554 clubes para preguntar si
    cambió algo.
    """
    d = _pedir({"coefficientType": "MEN_CLUB_TEN_YEARS", "coefficientRange": "OVERALL",
                "seasonYear": anio, "language": "EN", "page": 1, "pagesize": 1})
    return d["data"].get("lastUpdateDate")


# ------------------------------------------------------------- aplanado

def a_filas_clubes(crudo: dict) -> list[dict]:
    """Del JSON de UEFA a filas planas, una por club."""
    filas = []
    for m in crudo.get("miembros", []):
        miembro = m.get("member") or {}
        ranking = m.get("overallRanking") or {}
        filas.append({
            "uefa_club_id": miembro.get("id"),
            "uefa_nombre": miembro.get("displayName"),
            "uefa_nombre_oficial": miembro.get("displayOfficialName"),
            "uefa_nombre_internacional": miembro.get("internationalName"),
            "uefa_nombre_corto": miembro.get("displayNameShort"),
            "uefa_pais": miembro.get("countryName"),
            "uefa_pais_codigo": miembro.get("countryCode"),
            "uefa_asociacion_id": miembro.get("associationId"),
            "uefa_ranking": ranking.get("position"),
            "uefa_coeficiente": ranking.get("totalValue"),
            "uefa_tendencia": ranking.get("trend"),
        })
    return filas


def a_filas_asociaciones(crudo: dict) -> list[dict]:
    """Del JSON de UEFA a filas planas, una por asociación nacional."""
    filas = []
    for m in crudo.get("miembros", []):
        miembro = m.get("member") or {}
        ranking = m.get("overallRanking") or {}
        filas.append({
            "pais": miembro.get("countryName") or miembro.get("displayName"),
            "pais_codigo": miembro.get("countryCode"),
            "pais_ranking_uefa": ranking.get("position"),
            "pais_coeficiente_uefa": ranking.get("totalValue"),
        })
    return filas
