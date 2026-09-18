"""Capa bronce: el dato crudo, tal como lo devolvió la fuente.

La regla del bronce es **append-only**: lo que ya está en disco no se vuelve a
pedir. De esa regla salen las dos propiedades que la justifican:

  * La fuente se toca una vez por dato, no una vez por corrida. La segunda
    corrida sobre el mismo material no genera ni una request.
  * Un error de parseo se arregla sin volver a la fuente: se corrige la capa
    plata y se reprocesa lo que ya está en disco.

Hay una excepción deliberada y está explicada en `es_inmutable()`: la página de
altas de la **temporada en curso** cambia mientras el mercado está abierto, así
que esa sí se vuelve a pedir. Las temporadas cerradas nunca cambian.

Particionado
------------
El snapshot y la entidad van en la **ruta**, no en el nombre del archivo, igual
que cualquier data lake sobre S3 pero con carpetas en lugar de prefijos::

    include/bronze/
      uefa/actualizacion=2026-09-17/clubes_diez_temporadas.json.gz
      uefa/actualizacion=2026-09-17/asociaciones.json.gz
      transfermarkt/ranking/actualizacion=2026-09-17/pagina_00.html.gz
      transfermarkt/altas/club=27/temporada=2025/altas.html.gz
      fotmob/temporada=2024-2025/jugador_860914.json.gz

Todo se guarda comprimido. El HTML de Transfermarkt baja unas ocho veces de
tamaño; el JSON de FotMob, unas diez.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

# La raíz se deduce de dónde vive este archivo, así que el mismo código
# funciona adentro del contenedor (/usr/local/airflow/include) y afuera,
# corriendo los módulos a mano desde el repositorio clonado.
INCLUDE_DIR = Path(__file__).resolve().parents[1]
BRONCE_DIR = INCLUDE_DIR / "bronze"
PLATA_DIR = INCLUDE_DIR / "silver"
RESPALDO_DIR = INCLUDE_DIR / "frozen"
SALIDA_DIR = INCLUDE_DIR / "output"


# --------------------------------------------------------------- escritura

def escribir_texto(destino: Path, contenido: str) -> Path:
    """Guarda texto comprimido, creando la partición si hace falta."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(destino, "wt", encoding="utf-8") as f:
        f.write(contenido)
    return destino


def leer_texto(ruta: str | Path) -> str:
    with gzip.open(Path(ruta), "rt", encoding="utf-8") as f:
        return f.read()


def escribir_json(destino: Path, datos) -> Path:
    return escribir_texto(destino, json.dumps(datos, ensure_ascii=False))


def leer_json(ruta: str | Path):
    return json.loads(leer_texto(ruta))


def huella(texto: str) -> str:
    """sha256 corto de un contenido. Es lo que permite responder
    '¿esto cambió desde la última vez?' sin guardar dos copias."""
    return hashlib.sha256(texto.encode("utf-8", "replace")).hexdigest()[:16]


# ------------------------------------------------------------------ rutas

def ruta_uefa_clubes(actualizacion: str) -> Path:
    return BRONCE_DIR / "uefa" / f"actualizacion={actualizacion}" / "clubes_diez_temporadas.json.gz"


def ruta_uefa_asociaciones(actualizacion: str) -> Path:
    return BRONCE_DIR / "uefa" / f"actualizacion={actualizacion}" / "asociaciones.json.gz"


def ruta_tm_ranking(actualizacion: str, pagina: int) -> Path:
    return (BRONCE_DIR / "transfermarkt" / "ranking"
            / f"actualizacion={actualizacion}" / f"pagina_{pagina:02d}.html.gz")


def ruta_tm_altas(club_id: str | int, temporada: int) -> Path:
    return (BRONCE_DIR / "transfermarkt" / "altas"
            / f"club={club_id}" / f"temporada={temporada}" / "altas.html.gz")


def ruta_fotmob(jugador_id: str | int, temporada: str) -> Path:
    """`temporada` llega como '2024/2025' y se guarda como '2024-2025':
    la barra abriría una carpeta."""
    return (BRONCE_DIR / "fotmob" / f"temporada={temporada.replace('/', '-')}"
            / f"jugador_{jugador_id}.json.gz")


# ------------------------------------------------------- reglas de frescura

def es_inmutable(temporada: int, temporada_actual: int) -> bool:
    """¿La página de altas de esa temporada puede seguir cambiando?

    Una temporada cerrada no cambia nunca más: si el archivo está en bronce,
    es definitivo y no hay razón para volver a pedirlo. La temporada en curso
    sí cambia, porque el mercado sigue abierto y Transfermarkt agrega altas.

    Esta es la única excepción a la regla append-only del bronce, y es la que
    hace que el pipeline "sepa qué hacer cuando la fuente cambió" en lugar de
    depender de que alguien apriete un botón.
    """
    return temporada < temporada_actual


def listar(patron: str) -> list[Path]:
    """Todos los archivos del bronce que matchean un patrón glob."""
    return sorted(BRONCE_DIR.glob(patron))
