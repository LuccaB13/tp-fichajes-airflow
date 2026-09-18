"""
### Dataset de fichajes — Ciencia de Datos, UTN FRM 2026

Construye un dataset donde **una fila es un fichaje**: un jugador que llegó a
un club europeo en una temporada, con las estadísticas de su rendimiento en la
temporada **anterior** al traspaso, y con los dos clubes —origen y destino—
enriquecidos con el ranking oficial de UEFA.

Tres fuentes, tres roles distintos
----------------------------------

| Fuente | Qué aporta | Cómo se accede |
|---|---|---|
| **UEFA** | ranking y coeficiente de clubes (diez temporadas) y de asociaciones | API JSON pública (`comp.uefa.com`) |
| **Transfermarkt** | el fichaje: jugador, origen, destino, importe, edad, liga | HTML, hay que parsearlo |
| **FotMob** | el rendimiento previo: minutos, goles, xG, precisión de pases | API interna, JSON |

**Dos capas, y son tareas distintas en el grafo**, siguiendo el modelo
medallón:

* **Bronce** — el byte tal como vino: el HTML de Transfermarkt y el JSON de
  UEFA, comprimidos y particionados. Son las únicas tareas que tocan la red.
* **Plata** — una fila por fichaje, tipada, enriquecida y validada. **No toca
  la red**: lee del bronce.

La tercera capa, **oro** (features del modelo, agregados por liga), no se
construye acá: se arma en las unidades 3 y 4 sobre esta misma plata.

Corre solo, y sabe cuándo no hacer nada
---------------------------------------
`schedule="0 6 * * *"`. La mayoría de las corridas terminan enseguida sin bajar
nada, y eso es lo normal en un pipeline sano. La decisión no se toma con un
reloj ("¿pasaron 24 horas?") sino comparando una **huella de las fuentes**
contra la de la última corrida exitosa:

    huella = fecha de actualización del ranking UEFA
           + temporada en curso, deducida de la fecha
           + hash de los últimos traspasos registrados en Transfermarkt
           + el alcance pedido (cuántos clubes, cuántas temporadas)

Si la huella no cambió, el cortocircuito corta y la corrida termina en verde
sin haber pedido nada. Si cambió, baja **sólo lo que puede haber cambiado**:
una temporada cerrada no se vuelve a pedir nunca; la temporada en curso sí,
porque el mercado sigue abierto.

Degradación
-----------
Si las fuentes no responden, el sensor espera media hora antes de darlas por
perdidas; recién ahí el DAG se va por la rama del respaldo congelado. Un corte
de diez minutos no tiene por qué arruinar la corrida del día.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pendulum
from airflow.sdk import Param, PokeReturnValue, Variable, dag, task
from airflow.utils.trigger_rule import TriggerRule

from include.fichajes import bronce, fotmob, plata
from include.fichajes import transfermarkt as tm
from include.fichajes import uefa
from include.fichajes.clubes import Indice
from include.fichajes.clubes import construir_catalogo as cruzar_con_uefa

log = logging.getLogger(__name__)

# Acá se anota la huella de la última corrida completa exitosa. Es lo que le
# permite al DAG saber, mañana, si hay algo nuevo que hacer.
VAR_HUELLA = "fichajes_ultima_huella"

SEMILLA = bronce.RESPALDO_DIR / "fichajes_semilla.csv"
ULTIMO_OK = bronce.RESPALDO_DIR / "ultimo_ok.csv"


@dag(
    dag_id="pipeline_fichajes",
    # Mira las fuentes todos los días a las 6 de la mañana. `catchup=False`
    # evita que, si el entorno estuvo apagado una semana, Airflow intente
    # recuperar las siete corridas perdidas.
    schedule="0 6 * * *",
    start_date=pendulum.datetime(2026, 8, 1, tz="America/Argentina/Buenos_Aires"),
    catchup=False,
    # Cuántos clubes se bajan a la vez. Cuatro es lo que veníamos usando sin
    # que Transfermarkt corte la conexión; más arriba no vale la pena arriesgar
    # un bloqueo de IP por una fuente gratuita.
    max_active_tasks=4,
    # Una sola corrida por vez. No es una precaución genérica: la capa plata
    # lee la carpeta de bronce **entera**, así que si dos corridas se pisan, la
    # que consolida primero arma el dataset con el bronce a medio escribir de
    # la otra. Nos pasó apenas despausamos el DAG: la corrida manual de prueba
    # (20 clubes) consolidó 582 filas de 110 clubes, porque la corrida
    # programada estaba bajando los 200 al mismo tiempo.
    max_active_runs=1,
    # Reintentos para todas las tareas. Es seguro ponerlo acá porque **todas
    # son idempotentes**: las de bronce no vuelven a pedir lo que ya está en
    # disco, la plata reconstruye el CSV entero, y `publicar` escribe siempre
    # el mismo archivo fechado. Una tarea que no fuera idempotente convertiría
    # cada reintento en datos duplicados.
    default_args={"retries": 2, "retry_delay": pendulum.duration(seconds=30)},
    tags=["ciencia-de-datos", "unidad-1", "fichajes", "medallon"],
    doc_md=__doc__,
    params={
        "modo": Param(
            "normal", enum=["prueba", "normal"],
            title="Modo de corrida",
            description=("prueba: sólo el top 20 de UEFA y una temporada, para "
                         "ver el grafo moverse en minutos. normal: usa los dos "
                         "parámetros de abajo."),
        ),
        "tope_ranking_uefa": Param(
            200, type="integer", minimum=1, maximum=560,
            title="Hasta qué puesto del ranking UEFA",
            description=("Se procesan los clubes de destino hasta esta posición "
                         "del coeficiente de diez temporadas. 200 es el corte "
                         "recomendado: más abajo cada club aporta ~1,5 fichajes "
                         "y sólo agrega negativos."),
        ),
        "temporadas_hacia_atras": Param(
            3, type="integer", minimum=1, maximum=10,
            title="Cuántas temporadas de fichajes",
            description=("Contando desde la temporada en curso hacia atrás. "
                         "Subir esto rinde más que bajar el ranking: una "
                         "temporada más son ~750 filas con el mismo balance "
                         "de clases."),
        ),
        "anio_uefa": Param(
            2027, type="integer", minimum=2020, maximum=2035,
            title="Ventana del ranking UEFA",
            description=("Temporada en la que termina la ventana de diez años. "
                         "2027 = ventana que cierra en 2026/27. Fijarlo hace la "
                         "corrida reproducible."),
        ),
        "forzar": Param(
            False, type="boolean",
            title="Forzar la corrida",
            description=("Ignora la huella de frescura y vuelve a pedir incluso "
                         "las temporadas cerradas que ya están en bronce."),
        ),
    },
)
def pipeline_fichajes():

    # ------------------------------------------------------------------ 1
    @task.sensor(poke_interval=300, timeout=1800, mode="reschedule",
                 soft_fail=True)
    def esperar_fuentes(**context) -> PokeReturnValue:
        """Espera a que las tres fuentes estén disponibles y toma la huella.

        Un sensor sirve para esperar algo que está **fuera del control del
        DAG**. Para esperar a una tarea del mismo DAG no hace falta: para eso
        están las dependencias.

        `mode="reschedule"` libera el worker entre sondeo y sondeo en vez de
        tenerlo durmiendo cinco minutos. Con un sensor da igual; con cincuenta
        esperando es la diferencia entre un scheduler sano y uno tapado.

        `soft_fail=True` hace que al agotarse el tiempo la tarea quede en
        `skipped` y no en `failed`: que una fuente no conteste no es un error
        del pipeline, es una condición que sabemos manejar — y la maneja la
        rama del respaldo.

        El valor que devuelve viaja por XCom y es la **huella de las fuentes**,
        que es lo que después decide si hay trabajo.
        """
        params = context["params"]
        try:
            actualizado = uefa.ultima_actualizacion(params["anio_uefa"])
            if not actualizado:
                log.warning("UEFA respondió sin fecha de actualización")
                return PokeReturnValue(is_done=False)

            html = tm.bajar_ultimos_traspasos()
            huella_tm = tm.huella_ultimos_traspasos(html)
            if not huella_tm:
                log.warning("Transfermarkt respondió pero sin traspasos")
                return PokeReturnValue(is_done=False)

            # A FotMob se le pide lo mínimo: que conteste.
            if not fotmob.buscar_jugador("Messi")[0]:
                log.warning("FotMob no devolvió resultados de prueba")
                return PokeReturnValue(is_done=False)

            hoy = datetime.now(timezone.utc)
            huella = {
                "uefa_actualizado": actualizado,
                "tm_ultimos": huella_tm,
                "temporada_actual": tm.temporada_actual(hoy),
            }
            log.info("las tres fuentes responden. Huella: %s", huella)
            return PokeReturnValue(is_done=True, xcom_value=huella)
        except Exception as e:
            log.warning("alguna fuente todavía no responde (%s). Reintento en 5 min.", e)
            return PokeReturnValue(is_done=False)

    # ------------------------------------------------------------------ 2
    @task.branch(trigger_rule=TriggerRule.ALL_DONE)
    def elegir_camino(**context) -> str:
        """Decide por dónde sigue el DAG según lo que consiguió el sensor.

        Corre con `ALL_DONE` porque la tarea de arriba puede haber quedado en
        `skipped` — que es justamente el caso que tiene que manejar. Con la
        regla por defecto, `ALL_SUCCESS`, nunca se ejecutaría cuando más falta
        hace.
        """
        if context["ti"].xcom_pull(task_ids="esperar_fuentes"):
            return "hay_novedad"
        log.error("las fuentes no respondieron en 30 minutos. Se usa el respaldo.")
        return "usar_respaldo"

    # ------------------------------------------------------------------ 3
    @task.short_circuit
    def hay_novedad(**context) -> bool:
        """¿Hay algo nuevo que bajar? Si no, corta acá y no hace nada.

        Esta es la tarea que reemplaza al viejo "¿pasaron 24 horas?". La
        diferencia no es de forma: un reloj dice cuánto hace que corriste, no
        si la fuente cambió. Podías correr el DAG a las 23:59 y otra vez a las
        00:01 del día siguiente bajando exactamente lo mismo, o saltearte un
        mercado entero porque habías corrido esa mañana.

        Ahora se compara la **huella de las fuentes** contra la de la última
        corrida exitosa, guardada en una Variable de Airflow. Si devuelve
        `False`, todo lo que está aguas abajo queda en `skipped` y la corrida
        termina bien: no pasó nada porque no había nada que hacer.

        El **alcance** de la corrida (hasta qué puesto y cuántas temporadas)
        entra en la huella a propósito: si alguien sube el tope de clubes o
        pide una temporada más, hay trabajo nuevo aunque las fuentes no se
        hayan movido ni un milímetro.

        Y queda la excepción de siempre: `forzar=True`, que lo baja todo.
        """
        params = context["params"]
        huella = dict(context["ti"].xcom_pull(task_ids="esperar_fuentes") or {})

        if params["forzar"]:
            log.info("forzar=True: se baja aunque no haya cambiado nada.")
            return True

        tope, temporadas = _alcance(params)
        huella["alcance"] = f"{tope}/{temporadas}"

        anterior = Variable.get(VAR_HUELLA, default=None)
        actual = _serializar(huella)
        if anterior == actual:
            log.info("Sin novedad: las fuentes están igual que en la última "
                     "corrida (%s). No hay nada que hacer.", actual)
            return False

        log.info("Hay novedad.\n  antes: %s\n  ahora: %s", anterior, actual)
        return True

    # ------------------------------------------------------------------ 4
    @task
    def aterrizar_bronce_uefa(**context) -> dict:
        """**Capa bronce**: el ranking de UEFA, crudo.

        Se guardan las dos tablas que publica UEFA: el coeficiente de clubes
        de las últimas diez temporadas —de donde sale la columna objetivo— y
        el de asociaciones nacionales, que es lo que define qué país es
        europeo sin necesidad de una lista escrita a mano.

        La partición es la fecha de actualización que informa la propia UEFA,
        no la fecha de la corrida: dos corridas del mismo snapshot escriben en
        la misma carpeta y no se duplica nada.
        """
        params = context["params"]
        crudo = uefa.clubes_diez_temporadas(params["anio_uefa"])
        actualizado = (crudo.get("actualizado") or "")[:10] or "desconocida"

        ruta_clubes = bronce.ruta_uefa_clubes(actualizado)
        ruta_asoc = bronce.ruta_uefa_asociaciones(actualizado)

        if not ruta_clubes.exists() or params["forzar"]:
            bronce.escribir_json(ruta_clubes, crudo)
        if not ruta_asoc.exists() or params["forzar"]:
            bronce.escribir_json(ruta_asoc, uefa.asociaciones(params["anio_uefa"]))

        log.info("bronce UEFA en %s (%s clubes)", ruta_clubes.parent,
                 len(crudo.get("miembros", [])))
        return {"actualizacion": actualizado,
                "clubes": str(ruta_clubes), "asociaciones": str(ruta_asoc)}

    # ------------------------------------------------------------------ 5
    @task
    def construir_catalogo(uefa_bronce: dict, **context) -> list[dict]:
        """El catálogo de clubes a procesar, ordenado por ranking de UEFA.

        Hace dos cosas y las dos importan:

        1. Baja el ranking de clubes de Transfermarkt **y lo guarda en
           bronce**. De esta página sólo se usan el id y el slug, que son lo
           único que arma la URL de fichajes; la posición la pone UEFA.
        2. Cruza las dos fuentes por nombre (ver `clubes.py`) y escribe la
           dimensión de clubes en plata, junto con el archivo de los que no
           cruzaron. Los que no cruzan no se esconden: se cuentan.
        """
        params = context["params"]
        tope, _ = _alcance(params)
        actualizacion = uefa_bronce["actualizacion"]

        clubes_tm, pagina = [], 1
        while len(clubes_tm) < 600:
            destino = bronce.ruta_tm_ranking(actualizacion, pagina)
            if destino.exists() and not params["forzar"]:
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

        crudo_clubes = bronce.leer_json(uefa_bronce["clubes"])
        crudo_asoc = bronce.leer_json(uefa_bronce["asociaciones"])
        indice = Indice(uefa.a_filas_clubes(crudo_clubes),
                        uefa.a_filas_asociaciones(crudo_asoc))

        catalogo, sin_cruce = cruzar_con_uefa(clubes_tm, indice, tope)
        plata.escribir_dimension_clubes(catalogo, sin_cruce)

        # Por XCom viajan metadatos, no datos: de cada club sólo lo que hace
        # falta para armar la URL y nombrar la tarea en la interfaz.
        temporada_actual = tm.temporada_actual(datetime.now(timezone.utc))
        _, temporadas = _alcance(params)
        return [{
            "id": c["tm_club_id"], "slug": c["tm_slug"], "nombre": c["tm_nombre"],
            "ranking": c["uefa_ranking"],
            "temporadas": list(range(temporada_actual,
                                     temporada_actual - temporadas, -1)),
            "temporada_actual": temporada_actual,
            "forzar": params["forzar"],
        } for c in catalogo]

    # ------------------------------------------------------------------ 6
    @task(map_index_template="{{ task.op_kwargs['club']['nombre'] }}")
    def aterrizar_bronce_transfermarkt(club: dict) -> dict:
        """**Capa bronce de Transfermarkt**: el HTML crudo, sin interpretarlo.

        Esto es lo que faltaba. Antes se pedía la página, se parseaba en
        memoria y se tiraba: lo único que quedaba en disco era el JSON de
        FotMob. Con eso, cualquier arreglo en el parseo del fichaje —el
        importe, el club de origen, la liga— obligaba a scrapear
        Transfermarkt de nuevo. Y si el sitio cambiaba en el medio, los datos
        viejos no se podían recuperar nunca más.

        La regla es append-only, con **una excepción explícita**: la página de
        la temporada en curso se vuelve a pedir, porque el mercado sigue
        abierto y aparecen altas nuevas. Las temporadas cerradas, una vez en
        disco, son definitivas.
        """
        paginas, pedidas, reusadas, sin_pagina = [], 0, 0, 0
        for temporada in club["temporadas"]:
            destino = bronce.ruta_tm_altas(club["id"], temporada)
            inmutable = bronce.es_inmutable(temporada, club["temporada_actual"])
            anotar = {"ruta": str(destino), "temporada": temporada}

            if destino.exists() and inmutable and not club["forzar"]:
                paginas.append(anotar)
                reusadas += 1
                continue

            try:
                html = tm.bajar_altas(club["slug"], club["id"], temporada)
            except tm.PaginaInexistente:
                sin_pagina += 1
                continue

            # Si es la temporada en curso y el contenido no cambió, no se
            # reescribe: así la fecha del archivo sigue diciendo la verdad
            # sobre cuándo cambió el dato, no cuándo lo miramos.
            if destino.exists() and bronce.huella(html) == bronce.huella(
                    bronce.leer_texto(destino)):
                reusadas += 1
            else:
                bronce.escribir_texto(destino, html)
                pedidas += 1
            paginas.append(anotar)
            time.sleep(2)

        log.info("%s: %s temporadas en bronce (%s pedidas, %s reusadas, "
                 "%s sin página)", club["nombre"], len(paginas), pedidas,
                 reusadas, sin_pagina)
        # Devuelve rutas, no HTML. Pasar megabytes de página por XCom satura
        # la base de metadatos de Airflow, y es de los errores más comunes al
        # empezar con la herramienta.
        return {"club": club, "paginas": paginas}

    # ------------------------------------------------------------------ 7
    @task(map_index_template="{{ task.op_kwargs['lote']['club']['nombre'] }}",
          max_active_tis_per_dag=4)
    def aterrizar_bronce_fotmob(lote: dict) -> dict:
        """**Capa bronce de FotMob**: el rendimiento previo de cada fichado.

        Lee las altas del HTML que ya está en disco —no vuelve a Transfermarkt—
        y por cada fichaje pide a FotMob las estadísticas
        de la temporada **anterior** al traspaso.

        El archivo se guarda por jugador y temporada, sin nada del fichaje
        adentro. Así, si el mismo jugador aparece en dos traspasos distintos,
        sus estadísticas de 2024/25 se piden una sola vez.
        """
        club = lote["club"]
        pedidos = reusados = sin_datos = 0

        for pagina in lote["paginas"]:
            temporada_tm = pagina["temporada"]
            altas = tm.parsear_altas(bronce.leer_texto(pagina["ruta"]),
                                     club["id"], temporada_tm)
            # Las estadísticas que importan son las de la temporada ANTERIOR
            # al traspaso: lo que se quiere explicar es a qué club fue el
            # jugador dado cómo venía rindiendo, no cómo rindió después.
            temporada_stats = tm.etiqueta_temporada(temporada_tm - 1)

            for alta in altas:
                # El criterio tiene que ser el mismo que usa la capa plata para
                # armar el dataset: si acá filtráramos por "tiene importe", los
                # fichajes libres entrarían al dataset pero nunca tendrían
                # estadísticas, y el hueco parecería un problema de FotMob.
                if alta["tipo_operacion"] in plata.TIPOS_EXCLUIDOS:
                    continue
                jugador = alta["jugador_tm_id"]
                destino = bronce.ruta_fotmob(jugador, temporada_stats)
                if destino.exists():
                    reusados += 1
                    continue

                registro = fotmob.registro_de_temporada(
                    alta["jugador_nombre"], jugador, temporada_stats,
                    club_destino=club["nombre"], club_origen=alta["club_origen"])
                if registro is None:
                    sin_datos += 1
                    continue
                bronce.escribir_json(destino, registro)
                pedidos += 1

        log.info("%s: %s jugadores nuevos en bronce, %s ya estaban, "
                 "%s sin estadísticas en FotMob", club["nombre"], pedidos,
                 reusados, sin_datos)
        return {"club": club["nombre"], "nuevos": pedidos,
                "reusados": reusados, "sin_datos": sin_datos}

    # ------------------------------------------------------------------ 8
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def generar_capa_plata(_lotes, **context) -> str | None:
        """**Capa plata**: una fila por fichaje, tipada y enriquecida.

        Corre con `ALL_DONE` porque tiene que consolidar lo que haya aunque
        algún club haya fallado al bajar: un club caído no puede tirar abajo
        el dataset entero.

        No toca la red. Todo sale del bronce.
        """
        params = context["params"]
        temporada_actual = tm.temporada_actual(datetime.now(timezone.utc))
        _, cuantas = _alcance(params)
        temporadas = list(range(temporada_actual, temporada_actual - cuantas, -1))
        return plata.consolidar(temporadas=temporadas)

    # ------------------------------------------------------------------ 9
    @task
    def usar_respaldo() -> str:
        """Rama de último recurso: el respaldo más fresco que haya en disco.

        Prefiere el de la última corrida completa exitosa; si no existe
        todavía, la semilla versionada en el repositorio.

        Ojo con qué es este archivo: es **plata**, ya parseada. Salva la
        corrida de hoy, pero no permite reprocesar nada. El bronce es el que
        te salva de un bug en el parser.
        """
        for ruta, origen in ((ULTIMO_OK, "última corrida completa exitosa"),
                             (SEMILLA, "semilla versionada en el repositorio")):
            if ruta.exists():
                log.warning("Las fuentes no respondieron. Se usa el respaldo (%s). "
                            "Estos datos NO son de hoy.", origen)
                return str(ruta)
        raise FileNotFoundError(
            f"las fuentes no responden y no hay ningún respaldo en "
            f"{bronce.RESPALDO_DIR}. La primera corrida tiene que ser con las "
            f"fuentes arriba.")

    # ----------------------------------------------------------------- 10
    # `retries=0` pisa el default del DAG a propósito: un chequeo de calidad que
    # falla no es un error transitorio, es el dataset que está mal. Reintentarlo
    # dos veces sólo agrega ruido en los logs y demora el rojo.
    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS, retries=0)
    def validar_dataset_plata(desde_fuente: str | None,
                              desde_respaldo: str | None) -> str:
        """Chequeos duros. Si alguno falla, el DAG falla: no se publica basura.

        Recibe las dos ramas y una de las dos **siempre** viene salteada, así
        que con la regla por defecto (`ALL_SUCCESS`) esta tarea no se
        ejecutaría nunca. `NONE_FAILED_MIN_ONE_SUCCESS` dice "que ninguna haya
        fallado y que al menos una haya tenido éxito": salteada no es fallada.

        Un criterio de calidad que no está escrito como código no protege
        nada. Cada uno de estos chequeos es una de las cinco dimensiones de
        calidad convertida en una regla que una máquina puede evaluar.
        """
        import pandas as pd

        from include.fichajes.esquema import (CLAVE, COLUMNAS_BASE,
                                              MINIMO_COLUMNAS, MINIMO_FILAS,
                                              OBLIGATORIAS)

        ruta = desde_fuente or desde_respaldo
        if ruta is None:
            raise ValueError("ninguna rama produjo un archivo")
        df = pd.read_csv(ruta, low_memory=False)
        problemas = []

        # unicidad: es el test operativo de la unidad de análisis
        duplicados = df.duplicated(subset=CLAVE).sum()
        if duplicados:
            problemas.append(f"{duplicados} claves {tuple(CLAVE)} repetidas")

        # volumen y ancho
        if len(df) < MINIMO_FILAS:
            problemas.append(f"muy pocas filas: {len(df)} (mínimo {MINIMO_FILAS})")
        if df.shape[1] < MINIMO_COLUMNAS:
            problemas.append(f"muy pocas columnas: {df.shape[1]}")

        # completitud: ninguna columna base puede faltar ni venir 100% vacía
        faltantes = [c for c in COLUMNAS_BASE if c not in df.columns]
        if faltantes:
            problemas.append(f"faltan columnas del esquema: {faltantes}")
        vacias = df.columns[df.isna().all()].tolist()
        if vacias:
            problemas.append(f"columnas totalmente vacías: {vacias}")
        for c in OBLIGATORIAS:
            if c in df.columns and df[c].isna().any():
                problemas.append(f"{c} tiene {int(df[c].isna().sum())} nulos "
                                 f"y no debería tener ninguno")

        # precisión: rangos que, si se rompen, son error de captura
        if "edad_al_fichaje" in df.columns:
            fuera = df["edad_al_fichaje"].dropna()
            fuera = fuera[(fuera < 14) | (fuera > 45)]
            if len(fuera):
                problemas.append(f"{len(fuera)} edades fuera del rango 14-45")
        if "altura_cm" in df.columns:
            fuera = df["altura_cm"].dropna()
            fuera = fuera[(fuera < 140) | (fuera > 220)]
            if len(fuera):
                problemas.append(f"{len(fuera)} alturas fuera del rango 140-220 cm")
        if "coste_fichaje_eur" in df.columns and (df["coste_fichaje_eur"] < 0).any():
            problemas.append("hay importes de fichaje negativos")

        # consistencia: la columna objetivo tiene que derivarse del ranking
        if {"es_destino_top_20", "club_destino_ranking_uefa"} <= set(df.columns):
            esperado = df["club_destino_ranking_uefa"].le(20).fillna(False)
            incoherentes = (df["es_destino_top_20"].astype("boolean").fillna(False)
                            != esperado).sum()
            if incoherentes:
                problemas.append(f"{incoherentes} filas donde es_destino_top_20 no "
                                 f"coincide con el ranking UEFA del club de destino")
            # Un club de destino sin ranking sería un `es_destino_top_20=False`
            # puesto por omisión, no por el dato: la etiqueta quedaría mal sin
            # que nada se queje. No puede pasar --el catálogo se arma sólo con
            # clubes cruzados-- salvo que el bronce del ranking y el de las
            # altas queden desalineados, que es justo lo que hay que detectar.
            sin_ranking = int(df["club_destino_ranking_uefa"].isna().sum())
            if sin_ranking:
                problemas.append(
                    f"{sin_ranking} filas cuyo club de destino no cruzó contra el "
                    f"ranking de UEFA: la columna objetivo estaría en False por "
                    f"omisión")

        # el filtro de tipos de operación se aplicó de verdad
        excluidos = set(df.get("tipo_operacion", pd.Series(dtype=object))) & set(
            plata.TIPOS_EXCLUIDOS)
        if excluidos:
            problemas.append(f"quedaron operaciones que no son fichajes: {excluidos}")

        if problemas:
            raise ValueError("Validación fallida:\n  - " + "\n  - ".join(problemas))

        objetivo = df["es_destino_top_20"].mean() if "es_destino_top_20" in df else 0
        sin_stats = (int((~df["tiene_historial"].astype("boolean")).sum())
                     if "tiene_historial" in df.columns else 0)
        log.info("Validación OK: %s filas x %s columnas | %s clubes de destino | "
                 "%.1f%% de la clase positiva | %s fichajes sin estadísticas",
                 len(df), df.shape[1], df["club_destino"].nunique(),
                 100 * objetivo, sin_stats)
        return ruta

    # ----------------------------------------------------------------- 11
    @task
    def publicar(ruta: str, **context) -> str:
        """Escribe el entregable fechado y anota la huella de la corrida.

        Ojo con `ds`: sólo existe cuando el DAG tiene schedule y por lo tanto
        intervalo de datos. Sacar la fecha del DagRun funciona en los dos
        casos, así que es lo que conviene por costumbre.
        """
        import shutil
        from pathlib import Path

        corrida = context["dag_run"]
        momento = corrida.logical_date or corrida.run_after
        fecha = momento.date().isoformat()

        bronce.SALIDA_DIR.mkdir(parents=True, exist_ok=True)
        destino = bronce.SALIDA_DIR / f"fichajes_{fecha}.csv"
        shutil.copy(ruta, destino)
        log.info("dataset escrito en %s", destino)

        vino_del_respaldo = Path(ruta).parent == bronce.RESPALDO_DIR
        if vino_del_respaldo:
            log.info("El respaldo no se toca: estos datos salieron de él, y la "
                     "huella tampoco se actualiza — no vimos las fuentes.")
            return str(destino)

        bronce.RESPALDO_DIR.mkdir(parents=True, exist_ok=True)
        shutil.copy(destino, ULTIMO_OK)
        log.info("respaldo actualizado -> %s", ULTIMO_OK)

        # Anotar la huella recién acá, cuando ya sabemos que el dataset pasó
        # la validación. Si se anotara antes, una corrida fallida dejaría al
        # DAG creyendo que ya procesó algo que nunca terminó.
        huella = dict(context["ti"].xcom_pull(task_ids="esperar_fuentes") or {})
        if huella:
            tope, temporadas = _alcance(context["params"])
            huella["alcance"] = f"{tope}/{temporadas}"
            Variable.set(VAR_HUELLA, _serializar(huella))
            log.info("huella de la corrida anotada: %s", _serializar(huella))
        return str(destino)

    # --------------------------------------------------- grafo del DAG
    espera = esperar_fuentes()
    rama = elegir_camino()
    novedad = hay_novedad()
    uefa_bronce = aterrizar_bronce_uefa()
    catalogo = construir_catalogo(uefa_bronce)
    bronces_tm = aterrizar_bronce_transfermarkt.expand(club=catalogo)
    bronces_fotmob = aterrizar_bronce_fotmob.expand(lote=bronces_tm)
    tabla_plata = generar_capa_plata(bronces_fotmob)
    respaldo = usar_respaldo()

    # Las únicas dependencias declaradas a mano son las de las tareas de
    # decisión, que no se pasan datos entre sí: sólo ordenan el flujo.
    espera >> rama
    rama >> [novedad, respaldo]
    novedad >> uefa_bronce
    publicar(validar_dataset_plata(tabla_plata, respaldo))


# ------------------------------------------------------------- auxiliares

def _alcance(params) -> tuple[int, int]:
    """El alcance efectivo de la corrida: (tope de ranking, temporadas).

    El modo `prueba` pisa los dos parámetros para que el grafo se pueda ver
    moverse entero en minutos, sin bajar 200 clubes.
    """
    if params["modo"] == "prueba":
        return 20, 1
    return int(params["tope_ranking_uefa"]), int(params["temporadas_hacia_atras"])


def _serializar(huella: dict) -> str:
    return "|".join(f"{k}={huella[k]}" for k in sorted(huella))


pipeline_fichajes()
