# Pipeline de Datos - Fichajes y Estadísticas

Este repositorio contiene la arquitectura de extracción y orquestación de datos para nuestro proyecto integrador. El objetivo es construir un pipeline de datos escalable que alimente nuestro futuro modelo de análisis y sistema multi-agente.

## 1. Arquitectura y Técnicas de Scraping

El motor de extracción está construido en **Python** y orquestado mediante **Apache Airflow** (desplegado en contenedores Docker vía Astro CLI). 

Para recolectar la información, utilizamos una técnica híbrida de extracción orientada a dos fuentes principales:

*   **Transfermarkt (HTML Parsing):** Utilizamos `BeautifulSoup` para navegar por el catálogo histórico. El script pagina dinámicamente hasta obtener los 384 clubes más importantes de la UEFA y luego viaja en el tiempo (3 temporadas hacia atrás) para extraer las transferencias (altas) de cada equipo, capturando el origen, destino y coste del fichaje.
*   **FotMob (API Scraping):** Una vez que tenemos al jugador transferido, el sistema ataca los endpoints ocultos de la API de FotMob utilizando la librería `requests`. Realizamos un proceso de búsqueda (match por nombre) para obtener el `id` del jugador y luego descargamos sus *Deep Stats* (Minutos jugados, xG, pases, etc.) correspondientes a la temporada exacta previa a su traspaso.

**Optimizaciones clave:** 
Implementamos un sistema de caché local y *Dynamic Task Mapping* en Airflow. El DAG clona ramas de ejecución en paralelo limitadas por *Pools* (máximo 4 a la vez) para procesar múltiples clubes simultáneamente sin sufrir bloqueos de IP o baneos por anti-bots.

---

## 2. Descarga de la Capa Bronce (¡Importante!)

Dado que el orquestador extrae miles de archivos JSON en bruto, **NO ejecutaremos la extracción completa cada uno en su máquina** (tomaría horas y el repositorio de Git colapsaría de peso).

Ya realicé la extracción de los 384 clubes y empaqueté los JSON. Para sincronizar tu entorno, sigue estos pasos:

1. Descarga el archivo `.zip` con los datos desde este enlace de Google Drive:
    [Descargar Capa Bronce - Google Drive](https://drive.google.com/drive/folders/11YaVodT0KpqIDaGyzrxGM3h4jG-Q03pY)
2. Descomprime el archivo.
3. Copia la carpeta llamada `bronze` y pégala **exactamente** dentro de la carpeta `include/` de este repositorio local.
   *La ruta final debe quedar así: `tu_repo/include/bronze/bronce_jugador_año.json`*

*(Nota: Esta carpeta ya está ignorada en el `.gitignore`, así que no te preocupes, no se subirá en tus futuros commits).*

---

##  3. Montar el Entorno Local (Airflow + Docker)

Para poder ejecutar la orquestación o hacer pruebas con el código de extracción, necesitas tener el contenedor corriendo.

### Prerrequisitos:
* Tener **Docker Desktop** instalado y abierto (con el motor corriendo).
* Tener instalado **Astro CLI**.

### Pasos para ejecutar:
1. Abre una terminal (CMD, PowerShell o bash) en la raíz de este repositorio.
2. Ejecuta el siguiente comando para construir e inicializar los contenedores:
   ```bash
   astro dev start
3. Una vez que la terminal finalice de cargar los procesos, abre tu navegador web e ingresa a:
http://localhost:8080

4. Inicia sesión con las credenciales por defecto:

Usuario: admin

Contraseña: admin

---

## 🛠️ 4. Capa Plata y Validación 

*   **Cortocircuito Inteligente:** Para evitar bloqueos y ahorrar recursos, el DAG verifica automáticamente si pasaron al menos 24 horas desde la última extracción. Si no hay novedad, salta el scraping pero fuerza la actualización de la Capa Plata con los datos locales.
*   **Transformación (Capa Plata):** El script `transformacion_plata.py` (usando Pandas) lee todos los JSON dispersos de la carpeta `bronze/` y los consolida en una sola tabla. Suma métricas acumulativas (ej. goles, minutos), promedia estadísticas de rendimiento (ej. precisión de pases) y unifica los registros a **una fila por jugador y temporada de fichaje**.
*   **Variable Objetivo:** El resultado es el archivo `dataset_fichajes_silver.csv`.
*   **Validación Automática:** La última tarea del orquestador actúa como auditor de calidad. Antes de dar el OK final, verifica programáticamente que el CSV tenga más de 1000 filas, que la clave primaria (`jugador_id` + `temporada`) sea única y que no existan columnas completamente vacías.