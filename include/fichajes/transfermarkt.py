"""Cliente y parseo de Transfermarkt.

Dos responsabilidades, separadas a propósito:

  * `bajar_*`  -- toca la red y devuelve **HTML crudo**. Es lo único que el DAG
    guarda en la capa bronce, sin interpretar.
  * `parsear_*` -- recibe ese HTML (leído del bronce) y devuelve filas. **No
    toca la red.** Se puede correr cien veces mientras se depura el parseo y
    Transfermarkt ni se entera.

Por qué el dominio internacional
--------------------------------
Se usa `transfermarkt.com` y no `transfermarkt.com.ar`. El dominio en español
traduce los nombres de club ("Bayern Múnich", "SSC Nápoles", "Estrella Roja de
Belgrado", "Club Brujas"), y esos nombres traducidos no cruzan contra el
ranking de UEFA. Medido sobre los 384 clubes del catálogo: con el dominio
español el cruce llega al 89%, con el internacional al 96%. Además el importe
viene en un formato mucho más simple de parsear: `€70.00m` contra
`70,00 mill. €`.

Qué trae la fila de un alta, que es más de lo que parece
-------------------------------------------------------
La tabla de altas ya contiene, en la misma fila, todo lo que hace falta para
enriquecer el club de origen **sin una sola request extra**:

    <a href="/fc-liverpool/startseite/verein/31" title="Liverpool FC">   id + slug
    <img class="flaggenrahmen" title="England">                          país
    <a href="/premier-league/transfers/wettbewerb/GB1">Premier League    liga + código

Y del jugador: id de Transfermarkt, edad **al momento del fichaje** (no la de
hoy menos los años, que es lo que se calculaba antes), nacionalidad, posición
y el id de la operación.
"""
from __future__ import annotations

import logging
import re
import time
import urllib.error
import urllib.request

from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

BASE = "https://www.transfermarkt.com"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
CABECERAS = {"User-Agent": UA, "Accept-Language": "en-US,en;q=0.9",
             "Accept": "text/html,application/xhtml+xml"}

# Las cinco grandes, por código de competición de Transfermarkt.
LIGAS_TOP5 = {"GB1", "ES1", "IT1", "L1", "FR1"}

# Sufijos con los que Transfermarkt nombra a los filiales y juveniles:
# "Chelsea FC U21", "SL Benfica B", "FC Bayern Munich II", "Real Sociedad B".
# Hay que detectarlos porque el cruce por nombre los confunde con el primer
# equipo -- ver `club_origen_es_filial` en el esquema.
FILIAL = re.compile(
    r"(\s(B|II|III)$)|\bU-?1[5-9]\b|\bU-?2[0-3]\b|\bReserves?\b|\bYouth\b"
    r"|\bAcademy\b|\bJuniors?\b|\bsub-?\d+\b", re.IGNORECASE)


def es_filial(nombre: str) -> bool:
    """¿El nombre del club es el de un filial o un juvenil?"""
    return bool(nombre and FILIAL.search(nombre))


class PaginaInexistente(Exception):
    """404 de Transfermarkt. No es un error del pipeline: ese club no tiene
    página para esa temporada."""


# ------------------------------------------------------------------ red

def bajar(url: str, timeout=40, reintentos=3) -> str:
    for intento in range(reintentos):
        try:
            req = urllib.request.Request(url, headers=CABECERAS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise PaginaInexistente(url)
            if intento == reintentos - 1:
                raise
            time.sleep(3 * (intento + 1))
        except Exception:
            if intento == reintentos - 1:
                raise
            time.sleep(3 * (intento + 1))
    raise RuntimeError("inalcanzable")


def url_ranking(pagina: int) -> str:
    return f"{BASE}/statistik/klubrangliste?page={pagina}"


def url_altas(slug: str, club_id: str | int, temporada: int) -> str:
    return f"{BASE}/{slug}/transfers/verein/{club_id}/saison_id/{temporada}"


URL_ULTIMOS = f"{BASE}/transfers/neuestetransfers/statistik"


def bajar_ranking(pagina: int) -> str:
    return bajar(url_ranking(pagina))


def bajar_ultimos_traspasos() -> str:
    """La página de traspasos más recientes de todo el sitio.

    Es la sonda de frescura de Transfermarkt. No sirve como dato -- son 175
    filas sueltas, sin relación con nuestro catálogo -- pero cambia **exacta y
    únicamente** cuando se registran traspasos nuevos, que es la pregunta que
    tiene que responder el cortocircuito del DAG.

    La alternativa obvia, hashear la página del ranking de clubes, no sirve:
    ahí se mueve el valor de mercado todo el tiempo, así que daría "hay
    novedad" en cada corrida y el cortocircuito no cortaría nunca.
    """
    return bajar(URL_ULTIMOS)


def huella_ultimos_traspasos(html: str) -> str:
    """Los ids de jugador de la página de últimos traspasos, en orden.

    Se hashean los ids y no el HTML entero para que la huella no se mueva por
    un banner, un precio actualizado o el orden de un anuncio.
    """
    import hashlib

    ids = re.findall(r"/spieler/(\d+)", html or "")
    vistos, orden = set(), []
    for i in ids:
        if i not in vistos:
            vistos.add(i)
            orden.append(i)
    firma = ",".join(orden[:120])
    return hashlib.sha256(firma.encode()).hexdigest()[:16]


def bajar_altas(slug: str, club_id: str | int, temporada: int) -> str:
    return bajar(url_altas(slug, club_id, temporada))


# --------------------------------------------------------------- parseo

def parsear_ranking(html: str) -> list[dict]:
    """Del HTML del ranking de clubes a filas con id, slug, nombre y país.

    De esta página sólo interesan **el id y el slug**, que son lo que arma la
    URL de fichajes. La posición la pone UEFA, no Transfermarkt (ver el
    registro de cambios: antes el `es_top_20` salía de acá).
    """
    soup = BeautifulSoup(html, "html.parser")
    tabla = soup.find("table", class_="items")
    if tabla is None or tabla.find("tbody") is None:
        return []

    clubes, vistos = [], set()
    for fila in tabla.find("tbody").find_all("tr"):
        celda = fila.find("td", class_="hauptlink")
        if celda is None:
            continue
        enlace = celda.find("a", href=True)
        if enlace is None:
            continue
        partes = enlace["href"].split("/")
        if "verein" not in partes:
            continue
        club_id = partes[partes.index("verein") + 1]
        if club_id in vistos:
            continue
        # En algunas filas el primer enlace de la celda envuelve el escudo y no
        # el texto, así que el nombre queda vacío. El atributo `title` está
        # siempre, y es el nombre oficial: se usa como respaldo.
        titulo = (enlace.get("title") or "").strip()
        texto = enlace.get_text(strip=True)
        bandera = fila.find("img", class_="flaggenrahmen")
        clubes.append({
            "tm_club_id": club_id,
            "tm_slug": partes[1],
            "tm_nombre": texto or titulo,
            "tm_nombre_oficial": titulo or texto,
            "tm_pais": bandera.get("title") if bandera else None,
        })
        vistos.add(club_id)
    return clubes


def _caja_de_altas(soup: BeautifulSoup):
    """La caja titulada 'Arrivals'. Se busca por texto porque Transfermarkt no
    le pone un id estable."""
    for caja in soup.find_all("div", class_="box"):
        h2 = caja.find("h2")
        if h2 and "arrival" in h2.get_text(" ", strip=True).lower():
            return caja
    return None


def _id_de(href: str, palabra: str):
    m = re.search(rf"/{palabra}/(\d+)", href or "")
    return m.group(1) if m else None


def _entero(txt: str):
    try:
        return int(re.sub(r"[^0-9]", "", txt or ""))
    except (TypeError, ValueError):
        return None


def limpiar_importe(texto: str):
    """'€70.00m' -> 70000000 ; '€300k' -> 300000 ; 'Free transfer' -> None.

    Devuelve `(euros, tipo_operacion)`. El tipo se conserva aunque después se
    filtren las cesiones: que una fila quede afuera tiene que poder explicarse.
    """
    if not texto:
        return None, "desconocido"
    t = texto.strip()
    bajo = t.lower()

    if "loan fee" in bajo:
        tipo = "cesion_con_cargo"
    elif "end of loan" in bajo:
        return None, "fin_de_cesion"
    elif "loan" in bajo:
        return None, "cesion"
    elif "free" in bajo:
        return None, "libre"
    elif "?" in bajo or t in ("-", ""):
        return None, "desconocido"
    else:
        tipo = "compra"

    m = re.search(r"€\s*([\d.,]+)\s*([mk]?)", bajo)
    if not m:
        return None, tipo
    numero = m.group(1).replace(",", "")
    try:
        valor = float(numero)
    except ValueError:
        return None, tipo
    if m.group(2) == "m":
        valor *= 1_000_000
    elif m.group(2) == "k":
        valor *= 1_000
    return int(valor), tipo


def parsear_altas(html: str, club_destino_id: str, temporada: int) -> list[dict]:
    """Del HTML de una página de fichajes a una fila por alta.

    Devuelve **todas** las altas, incluidas cesiones y libres, con su
    `tipo_operacion`. El filtro se aplica después, en la capa plata, para que
    quede escrito en un solo lugar y sea auditable.
    """
    soup = BeautifulSoup(html, "html.parser")
    caja = _caja_de_altas(soup)
    if caja is None:
        return []
    tabla = caja.find("table")
    if tabla is None:
        return []

    altas = []
    for fila in tabla.find_all("tr", class_=["odd", "even"]):
        columnas = fila.find_all("td", recursive=False)
        if len(columnas) < 5:
            continue

        # --- jugador
        celda_jugador = fila.find("td", class_="hauptlink")
        enlace_jugador = celda_jugador.find("a", href=True) if celda_jugador else None
        if enlace_jugador is None:
            continue
        nombre = (enlace_jugador.get("title") or enlace_jugador.get_text(strip=True)).strip()
        jugador_tm_id = _id_de(enlace_jugador["href"], "spieler")

        # la posición va en la segunda línea de la tabla anidada del jugador
        posicion = None
        interna = columnas[1].find("table", class_="inline-table")
        if interna:
            filas_internas = interna.find_all("tr")
            if len(filas_internas) > 1:
                posicion = filas_internas[1].get_text(" ", strip=True) or None

        edad = _entero(columnas[2].get_text(strip=True))
        nacionalidades = [img.get("title") for img in columnas[3].find_all(
            "img", class_="flaggenrahmen") if img.get("title")]

        # --- club de origen: todo lo que hace falta está en esta celda
        origen = columnas[-2]
        celda_nombre = origen.find("td", class_="hauptlink")
        enlace_club = celda_nombre.find("a", href=True) if celda_nombre else None
        club_origen = club_origen_id = club_origen_slug = None
        if enlace_club is not None:
            club_origen = (enlace_club.get("title")
                           or enlace_club.get_text(strip=True)).strip()
            partes = enlace_club["href"].split("/")
            if "verein" in partes:
                club_origen_id = partes[partes.index("verein") + 1]
                club_origen_slug = partes[1]

        bandera = origen.find("img", class_="flaggenrahmen")
        enlace_liga = origen.find("a", href=re.compile(r"/wettbewerb/"))
        liga_id = None
        if enlace_liga is not None:
            m = re.search(r"/wettbewerb/([A-Za-z0-9]+)", enlace_liga["href"])
            liga_id = m.group(1) if m else None

        # --- operación
        texto_coste = columnas[-1].get_text(" ", strip=True)
        euros, tipo = limpiar_importe(texto_coste)
        enlace_operacion = columnas[-1].find("a", href=True)
        operacion_id = (_id_de(enlace_operacion["href"], "transfer_id")
                        if enlace_operacion else None)

        altas.append({
            "jugador_nombre": nombre,
            "jugador_tm_id": jugador_tm_id,
            "posicion_tm": posicion,
            "edad_al_fichaje": edad,
            "nacionalidad": nacionalidades[0] if nacionalidades else None,
            "nacionalidad_2": nacionalidades[1] if len(nacionalidades) > 1 else None,
            "club_destino_id": str(club_destino_id),
            "temporada_tm": temporada,
            "club_origen": club_origen,
            "club_origen_id": club_origen_id,
            "club_origen_slug": club_origen_slug,
            "club_origen_es_filial": es_filial(club_origen),
            "club_origen_pais": bandera.get("title") if bandera else None,
            "club_origen_liga": (enlace_liga.get("title") if enlace_liga else None),
            "club_origen_liga_id": liga_id,
            "club_origen_liga_es_top5": liga_id in LIGAS_TOP5 if liga_id else False,
            "coste_fichaje_eur": euros,
            "coste_fichaje_texto": texto_coste,
            "tipo_operacion": tipo,
            "operacion_id": operacion_id,
        })
    return altas


# ----------------------------------------------------------- temporadas

def temporada_actual(hoy) -> int:
    """El `saison_id` de la temporada en curso, deducido de la fecha.

    En Transfermarkt `saison_id=2025` es la temporada 2025/26: el año es el de
    **inicio**. Las ligas europeas arrancan en julio, así que de julio a
    diciembre la temporada en curso es la del año calendario, y de enero a
    junio es la del año anterior.

    Antes esto estaba escrito a mano (`temporada_actual_tm = 2026`) y había que
    acordarse de tocarlo cada agosto. Un pipeline que corre solo no puede
    depender de eso.
    """
    return hoy.year if hoy.month >= 7 else hoy.year - 1


def etiqueta_temporada(saison_id: int) -> str:
    """2025 -> '2025/2026'."""
    return f"{saison_id}/{saison_id + 1}"
