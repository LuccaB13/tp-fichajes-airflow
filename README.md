# Pipeline de fichajes — Ciencia de Datos, UTN FRM 2026

> **Proyecto integrador completo:** el pipeline (este README, más abajo), el análisis y el modelo
> (`analisis/`) y la aplicación web (`app/`). La sección [La aplicación](#la-aplicación-entrega-4)
> explica cómo se regenera todo desde los datos.

Construye un dataset donde **una fila es un fichaje**: un jugador que llegó a un
club europeo en una temporada, con sus estadísticas de la temporada **anterior**
al traspaso, y con los dos clubes —origen y destino— enriquecidos con el ranking
oficial de UEFA.

La variable objetivo es `es_destino_top_20`: si el club que lo compró está entre
los 20 primeros del coeficiente de clubes de UEFA de las últimas diez
temporadas.

## Documentación

Todo está en un solo documento, en dos formatos:

| Archivo | Para qué |
|---|---|
| [docs/Explicacion_Pipeline_Fichajes.pdf](docs/Explicacion_Pipeline_Fichajes.pdf) | **el documento para leer y compartir**: qué cambió, cómo funciona cada parte, el diagrama del DAG, el diccionario de columnas y la defensa oral |
| [docs/EXPLICACION.md](docs/EXPLICACION.md) | la misma documentación en markdown. Es la **fuente**: se edita acá |
| [docs/generar_pdf.py](docs/generar_pdf.py) | regenera el PDF a partir del markdown (`py docs/generar_pdf.py`) |

## Las tres fuentes

| Fuente | Qué aporta | Acceso |
|---|---|---|
| **UEFA** | ranking y coeficiente de clubes (10 temporadas) y de asociaciones | API JSON pública, `comp.uefa.com` |
| **Transfermarkt** | el fichaje: jugador, origen, destino, importe, edad, liga | HTML, dominio internacional |
| **FotMob** | el rendimiento previo: 56 métricas por torneo | API interna, JSON |

## Las capas

```
include/bronze/     el byte tal como vino, comprimido y particionado
include/silver/     dataset_fichajes_silver.csv + dim_clubes.csv + dim_clubes_sin_cruce.csv
include/output/     el entregable fechado de cada corrida
include/frozen/     respaldo congelado, por si las fuentes no responden
```

Ninguna se versiona: se regeneran corriendo el DAG.

## Cómo levantarlo

Hace falta **Docker Desktop** corriendo y **Astro CLI** instalado.

```bash
astro dev start
```

La primera vez tarda unos minutos. Después, `localhost:8080` — usuario `admin`,
contraseña `admin`.

### La primera corrida

1. **Dejalo pausado** y disparalo a mano: *Trigger DAG w/ config* →
   `modo = prueba`. Baja sólo el top 20 de UEFA y una temporada; termina en
   minutos y sirve para ver el grafo moverse entero.
2. Mirá la vista *Graph*: van a aparecer 20 instancias de la misma tarea, cada
   una con el nombre de su club, corriendo de a cuatro. Eso es `.expand()` en
   vivo.
3. En modo prueba, `validar_dataset_plata` **va a fallar a propósito**: con 20
   clubes el dataset no llega al mínimo de 1000 filas. No es un bug, es la
   validación haciendo su trabajo — y por eso `publicar` no corre.
4. **Disparalo de nuevo sin cambiar nada.** Esta vez termina en segundos y casi
   todo queda en gris. No falló: `hay_novedad` se dio cuenta de que las fuentes
   están igual y cortó. La corrida que no hace nada también es un resultado.
5. Cuando quieras el dataset completo: `modo = normal`. Con los valores por
   defecto (200 clubes, 5 temporadas) son unas 1.000 páginas de Transfermarkt y
   varios miles de consultas a FotMob: **calculá un par de horas la primera
   vez**. Las siguientes reusan el bronce.

> ⚠️ **Despausar el DAG dispara una corrida enseguida, con los parámetros por
> defecto** — o sea los 200 clubes y las 5 temporadas, no lo que hayas elegido
> en el formulario. Despausalo cuando estés listo para esa corrida larga, no
> antes.

> ⚠️ **La capa bronce vieja del Drive ya no sirve** y no se puede convertir: no
> contiene el HTML de Transfermarkt, así que de ahí no salen ni la liga del club
> de origen, ni el id del club, ni la edad real al fichaje. Hay que regenerarla.
> Ver la sección 4 del documento de explicación.

### Parámetros de corrida

| Parámetro | Por defecto | Qué hace |
|---|---|---|
| `modo` | `normal` | `prueba` pisa todo: top 20 y una temporada |
| `tope_ranking_uefa` | `200` | hasta qué puesto del ranking UEFA se procesan clubes de destino |
| `temporadas_hacia_atras` | `5` | cuántas temporadas de fichajes, desde la actual |
| `exigir_estadisticas` | `false` | deja afuera a los fichajes sin estadísticas previas en FotMob |
| `anio_uefa` | `2027` | ventana del ranking de diez años. Fijarlo hace la corrida reproducible |
| `forzar` | `false` | ignora la huella de frescura y vuelve a pedir todo |

## Probar sin levantar Airflow

Para depurar el parseo sin esperar a los contenedores:

```bash
py -m include.fichajes.prueba_local --clubes 3 --temporadas 1
```

Agregá `--sin-fotmob` para saltear el paso lento.

## El grafo

```mermaid
graph LR
    A[esperar_fuentes] --> B{elegir_camino}
    B -->|responden| C{hay_novedad}
    B -->|30 min sin respuesta| R[usar_respaldo]
    C -->|nada cambió| S([termina en verde])
    C --> D[bronce UEFA] --> E[catálogo] --> F[bronce Transfermarkt] --> G[bronce FotMob] --> H[capa plata]
    H --> V[validar]
    R --> V
    V --> P[publicar]
```

La versión completa del diagrama, con la regla de disparo de cada tarea, está en
la sección 7 del documento de explicación.

## La aplicación (Entrega 4)

Una aplicación de Streamlit que cuenta el proyecto entero y deja usar el modelo: la pregunta, los
datos, lo que encontramos, el modelo, y después explorar los fichajes y probar el modelo con un caso
nuevo.

| Carpeta | Qué hay |
|---|---|
| `analisis/` | los notebooks de la Entrega 2 (análisis exploratorio, seis hipótesis) y de la Entrega 3 (modelado) |
| `app/modelo.py` | el modelo de la Entrega 3, tal cual el notebook: población, columnas, `ZPorRol`, pipeline y partición |
| `app/build_app.py` | entrena el modelo con la misma semilla y genera todo lo que usa la aplicación |
| `app/app.py` | la aplicación de Streamlit (gráficos con Altair) |
| `app/datos/` | lo que genera `build_app.py`: el modelo entrenado, los fichajes con su predicción y los números |

### De los datos a la aplicación

```bash
# 1. el pipeline publica el dataset en include/output/fichajes_AAAA-MM-DD.csv (ver arriba)
# 2. instalar lo que usa la aplicación
py -m pip install -r app/requirements.txt
# 3. entrenar el modelo y generar app/datos/ (toma la última salida del DAG; tarda ~1 minuto)
py app/build_app.py
# 4. abrir la aplicación en el navegador
py -m streamlit run app/app.py
```

`build_app.py` también acepta otro archivo: `py app/build_app.py --datos ruta/al/dataset.csv`.

**Si el pipeline actualiza los datos, se corre de nuevo el paso 3** y la aplicación pasa a mostrar los
datos nuevos. Después se hace commit de `app/datos/` y Streamlit Community Cloud se actualiza solo con
el push.

### Lo que hace `build_app.py`

1. Arma la población de análisis igual que el notebook (con estadísticas previas, sin promociones
   internas, sin el cruce roto con FotMob) y la misma partición por jugador.
2. Repite el barrido de la Entrega 3 (cuatro familias, 36 combinaciones, validación cruzada por
   jugador) y verifica que el elegido siga siendo el random forest del notebook.
3. Entrena el modelo final con todo el entrenamiento y lo mide una vez en el test.
4. Le da a cada fichaje la probabilidad de un modelo que no lo vio: validación cruzada para los del
   entrenamiento, el modelo final para los del test.
5. Guarda en `app/datos/` el modelo, los fichajes con su predicción y los números de la aplicación.

Lo que muestra la aplicación coincide con el notebook `analisis/entrega3_grupo_7.ipynb`: f1 macro
0,667 en el test, precision 0,394, recall 0,414.

### Los notebooks

Para correr los notebooks de `analisis/`, copiar la salida del DAG a esa carpeta con el nombre
`fichajes.csv` (no se versiona, igual que las capas de datos). `ranking_fifa.csv` viaja con el
repositorio.
