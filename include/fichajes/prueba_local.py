"""Corrida chica del pipeline, sin Airflow.

Hace lo mismo que el DAG pero en un solo proceso y con un alcance mínimo, para
poder probar el parseo y el cruce sin levantar los contenedores:

    py -m include.fichajes.prueba_local --clubes 3 --temporadas 1

Es una herramienta de desarrollo. El pipeline de verdad es el DAG.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timezone

from . import bronce, fotmob, plata
from . import transfermarkt as tm
from . import uefa
from .clubes import Indice, construir_catalogo

log = logging.getLogger("prueba_local")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--clubes", type=int, default=3, help="cuántos clubes del top")
    p.add_argument("--temporadas", type=int, default=1)
    p.add_argument("--anio-uefa", type=int, default=2027)
    p.add_argument("--sin-fotmob", action="store_true",
                   help="salta el paso lento y arma la plata con lo que haya")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    # ---------------------------------------------------------- bronce UEFA
    crudo = uefa.clubes_diez_temporadas(args.anio_uefa)
    actualizacion = (crudo.get("actualizado") or "")[:10] or "desconocida"
    ruta_clubes = bronce.ruta_uefa_clubes(actualizacion)
    if not ruta_clubes.exists():
        bronce.escribir_json(ruta_clubes, crudo)
    ruta_asoc = bronce.ruta_uefa_asociaciones(actualizacion)
    if not ruta_asoc.exists():
        bronce.escribir_json(ruta_asoc, uefa.asociaciones(args.anio_uefa))
    print(f"bronce UEFA -> {ruta_clubes.parent}")

    # -------------------------------------------------------- catálogo
    clubes_tm, pagina = [], 1
    while len(clubes_tm) < 600:
        destino = bronce.ruta_tm_ranking(actualizacion, pagina)
        if destino.exists():
            html = bronce.leer_texto(destino)
        else:
            try:
                html = tm.bajar_ranking(pagina)
            except tm.PaginaInexistente:
                break
            bronce.escribir_texto(destino, html)
            time.sleep(1.5)
        lote = tm.parsear_ranking(html)
        if not lote:
            break
        clubes_tm.extend(lote)
        pagina += 1
    print(f"catálogo Transfermarkt: {len(clubes_tm)} clubes en {pagina - 1} páginas")

    indice = Indice(uefa.a_filas_clubes(bronce.leer_json(ruta_clubes)),
                    uefa.a_filas_asociaciones(bronce.leer_json(ruta_asoc)))
    catalogo, sin_cruce = construir_catalogo(clubes_tm, indice, tope=None)
    plata.escribir_dimension_clubes(catalogo, sin_cruce)
    # La cobertura se mide sobre clubes únicos, no sobre las filas del ranking:
    # Transfermarkt repite entradas entre páginas y `construir_catalogo` las
    # deduplica, así que dividir por len(clubes_tm) daría un número más feo que
    # la realidad.
    reales = [c for c in sin_cruce if not c["cruce_metodo"].startswith("duplicado")]
    unicos = len(catalogo) + len(reales)
    print(f"cruce UEFA: {len(catalogo)} cruzados, {len(reales)} sin cruce sobre "
          f"{unicos} clubes únicos ({len(catalogo) / max(unicos, 1):.1%} de cobertura)")

    catalogo = catalogo[:args.clubes]
    temporada_actual = tm.temporada_actual(datetime.now(timezone.utc))
    temporadas = list(range(temporada_actual, temporada_actual - args.temporadas, -1))
    print(f"temporada en curso deducida: {temporada_actual} "
          f"({tm.etiqueta_temporada(temporada_actual)}) | se procesan {temporadas}")

    # ------------------------------------------------ bronce Transfermarkt
    for club in catalogo:
        for temporada in temporadas:
            destino = bronce.ruta_tm_altas(club["tm_club_id"], temporada)
            if destino.exists() and bronce.es_inmutable(temporada, temporada_actual):
                continue
            try:
                html = tm.bajar_altas(club["tm_slug"], club["tm_club_id"], temporada)
            except tm.PaginaInexistente:
                print(f"  sin página: {club['tm_nombre']} {temporada}")
                continue
            bronce.escribir_texto(destino, html)
            altas = tm.parsear_altas(html, club["tm_club_id"], temporada)
            con_coste = [a for a in altas if a["coste_fichaje_eur"] is not None]
            print(f"  {club['tm_nombre']:24} {temporada}  altas={len(altas):>2} "
                  f"con importe={len(con_coste):>2}  (UEFA #{club['uefa_ranking']})")
            time.sleep(2)

    # ------------------------------------------------------- bronce FotMob
    if not args.sin_fotmob:
        for club in catalogo:
            for temporada in temporadas:
                ruta = bronce.ruta_tm_altas(club["tm_club_id"], temporada)
                if not ruta.exists():
                    continue
                altas = tm.parsear_altas(bronce.leer_texto(ruta),
                                         club["tm_club_id"], temporada)
                etiqueta = tm.etiqueta_temporada(temporada - 1)
                for alta in altas:
                    if alta["coste_fichaje_eur"] is None:
                        continue
                    destino = bronce.ruta_fotmob(alta["jugador_tm_id"], etiqueta)
                    if destino.exists():
                        continue
                    registro = fotmob.registro_de_temporada(
                        alta["jugador_nombre"], alta["jugador_tm_id"], etiqueta,
                        club["tm_nombre"], alta["club_origen"])
                    if registro:
                        bronce.escribir_json(destino, registro)
                        print(f"  FotMob OK  {alta['jugador_nombre']:26} "
                              f"{registro['match_metodo']}")
                    else:
                        print(f"  FotMob --  {alta['jugador_nombre']}")

    # --------------------------------------------------------------- plata
    ruta = plata.consolidar(temporadas=temporadas)
    print(f"\ncapa plata -> {ruta}")


if __name__ == "__main__":
    main()
