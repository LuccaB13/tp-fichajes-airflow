from airflow.sdk import dag, task, PokeReturnValue
from datetime import datetime
from include.transformacion_plata import consolidar_plata
from airflow.utils.trigger_rule import TriggerRule

# Importamos las herramientas de tu carpeta include
from include.extraccion_fotmob import obtener_catalogo_clubes, obtener_perfil_fotmob, HEADERS_HTML

@dag(
    dag_id="extraccion_fichajes_fotmob",
    schedule=None, 
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingesta", "capa_bronce", "sensor", "cortocircuito"],
)
def pipeline_fichajes():

    # 1. EL SENSOR: Tantea que la API de FotMob esté viva antes de lanzar 384 tareas
    @task.sensor(poke_interval=60, timeout=600, mode="reschedule", soft_fail=True)
    def esperar_api_fotmob() -> PokeReturnValue:
        import requests
        print("Tanteando la API de FotMob...")
        try:
            # Hacemos un ping rápido a la API de búsqueda
            url_prueba = "https://www.fotmob.com/api/data/search/suggest?term=messi"
            respuesta = requests.get(url_prueba, headers=HEADERS_HTML, timeout=10)
            
            if respuesta.status_code == 200:
                print("¡FotMob está online! Vía libre.")
                return PokeReturnValue(is_done=True)
            else:
                print(f"FotMob respondió con error {respuesta.status_code}. Reintentando en 60 seg...")
                return PokeReturnValue(is_done=False)
        except Exception as e:
            print(f"Falla de conexión: {e}. Reintentando en 60 seg...")
            return PokeReturnValue(is_done=False)


# 2. EL CORTOCIRCUITO: Verifica si ya se corrió recientemente
    @task.short_circuit(ignore_downstream_trigger_rules=False)
    def hay_informacion_nueva() -> bool:
        from airflow.models import Variable
        from datetime import datetime, timedelta
        
        # Obtenemos la fecha de la última corrida exitosa guardada en Airflow
        # Si es la primera vez que corre, devuelve una fecha muy antigua por defecto
        ultima_corrida_str = Variable.get("ultima_extraccion_fichajes", default_var="2000-01-01")
        ultima_corrida = datetime.strptime(ultima_corrida_str, "%Y-%m-%d")
        
        hoy = datetime.now()
        diferencia = hoy - ultima_corrida
        
        # Si pasaron menos de 24 horas desde la última extracción, cortamos el flujo
        if diferencia < timedelta(hours=24):
            print(f"Ya extrajimos datos hoy ({ultima_corrida_str}). No hay necesidad de saturar Transfermarkt.")
            print("Cortocircuito activado: Finalizando DAG con éxito sin extraer.")
            return False
            
        print(f"Última extracción fue el {ultima_corrida_str}. Pasaron más de 24 hs.")
        print("Luz verde para buscar nuevos fichajes.")
        
        # Importante: Solo deberíamos actualizar esta variable si la extracción es exitosa,
        # pero para simplificar el ejemplo en esta tarea, lo actualizamos acá. 
        # (En un entorno de producción estricto, esto se actualiza en la última tarea del DAG).
        Variable.set("ultima_extraccion_fichajes", hoy.strftime("%Y-%m-%d"))
        
        return True

    # 3. EXTRACCIÓN DEL CATÁLOGO
    @task
    def extraer_catalogo_clubes():
        return obtener_catalogo_clubes(cantidad_maxima=384)

    # 4. PROCESAMIENTO PARALELO (Dynamic Mapping)
    @task(map_index_template="{{ my_custom_map_index }}", max_active_tis_per_dag=4)
    def procesar_club(club: dict):
        from airflow.sdk import get_current_context
        import requests
        from bs4 import BeautifulSoup
        import time
        import os
        
        context = get_current_context()
        context["my_custom_map_index"] = f"Procesando: {club['nombre']}"
        
        temporada_actual_tm = 2026
        temporadas_hacia_atras = 3
        club_destino_actual = club['nombre']
        es_top_20 = club['es_top_20']
        
        for anio_tm in range(temporada_actual_tm, temporada_actual_tm - temporadas_hacia_atras, -1):
            temporada_fotmob = f"{anio_tm-1}/{anio_tm}"
            
            url_club_temporada = f"https://www.transfermarkt.com.ar/{club['slug']}/transfers/verein/{club['id']}/saison_id/{anio_tm}"
            respuesta = requests.get(url_club_temporada, headers=HEADERS_HTML)
            
            if respuesta.status_code == 200:
                soup = BeautifulSoup(respuesta.text, 'html.parser')
                cajas = soup.find_all('div', class_='box')
                
                for caja in cajas:
                    encabezado = caja.find('h2')
                    if encabezado and "altas" in encabezado.text.lower():
                        filas = caja.find('table').find_all('tr', class_=['odd', 'even']) if caja.find('table') else []

                        for fila in filas:
                            celda_nombre = fila.find('td', class_='hauptlink')
                            columnas = fila.find_all('td', recursive=False)
                            
                            if celda_nombre and len(columnas) >= 5:
                                nombre = celda_nombre.text.strip()
                                coste = columnas[-1].text.strip()
                                coste_lower = coste.lower()
                                
                                celda_origen = columnas[-2]
                                club_origen = "Desconocido"
                                celda_origen_nombre = celda_origen.find('td', class_='hauptlink')
                                if celda_origen_nombre:
                                    enlace_origen = celda_origen_nombre.find('a')
                                    if enlace_origen:
                                        club_origen = enlace_origen.get('title', enlace_origen.text).strip()
                                
                                if "cesión" not in coste_lower and "libre" not in coste_lower and "?" not in coste and coste != "-":
                                    nombre_limpio = nombre.replace(" ", "_").lower()
                                    ruta_cache = f"/usr/local/airflow/include/bronze/bronce_{nombre_limpio}_{temporada_fotmob.replace('/', '-')}.json"
                                    
                                    if os.path.exists(ruta_cache):
                                        continue 

                                    obtener_perfil_fotmob(nombre, coste, temporada_fotmob, club_destino_actual, club_origen, es_top_20)
                                    time.sleep(2) 
                        break 
            time.sleep(3) 
            
        return f"Carga finalizada para {club_destino_actual}"
    
    @task(trigger_rule=TriggerRule.ALL_DONE)
    def generar_capa_plata():
        from include.transformacion_plata import consolidar_plata
        print("Iniciando tarea de transformación a Capa Plata...")
        ruta = consolidar_plata()
        if ruta:
            print(f"Transformación exitosa. Archivo en: {ruta}")
            return ruta  # <-- ¡ESTO ERA LO QUE FALTABA!
        else:
            print("No se generó la Capa Plata.")
            return None
        
    @task(trigger_rule=TriggerRule.NONE_FAILED_MIN_ONE_SUCCESS)
    def validar_dataset_plata(ruta_csv: str):
        import pandas as pd
        
        if not ruta_csv:
            raise ValueError("Error: No se recibió ninguna ruta de la Capa Plata.")
            
        print(f"Iniciando validación sobre: {ruta_csv}")
        df = pd.read_csv(ruta_csv)
        problemas = []
        
        # 1. Clave primaria sin duplicados (Unidad de análisis: Jugador por Temporada)
        if df.duplicated(subset=["jugador_id", "temporada"]).any():
            duplicados = df.duplicated(subset=["jugador_id", "temporada"]).sum()
            problemas.append(f"Falla crítica: {duplicados} claves primarias duplicadas.")
            
        # 2. Volumen suficiente
        if len(df) <= 1000:
            problemas.append(f"Volumen insuficiente: El dataset tiene {len(df)} filas, se exigen más de 1000.")
            
        # 3. Ancho suficiente
        if df.shape[1] < 5:
            problemas.append(f"Ancho insuficiente: El dataset solo tiene {df.shape[1]} columnas.")
            
        # 4. Sin columnas 100% vacías
        columnas_vacias = df.columns[df.isna().all()].tolist()
        if columnas_vacias:
            problemas.append(f"Existen columnas totalmente vacías: {columnas_vacias}")
            
        # 5. Validación de la Columna Objetivo
        if "es_destino_top_20" not in df.columns:
            problemas.append("Falta la columna objetivo 'es_destino_top_20'.")
        elif df["es_destino_top_20"].isna().any():
            problemas.append("La columna objetivo 'es_destino_top_20' contiene nulos.")

        # Disparar alerta si hay errores
        if problemas:
            raise ValueError("Validación fallida:\n  - " + "\n  - ".join(problemas))
            
        print(f"Validación Exitosa: {len(df)} filas y {df.shape[1]} columnas limpias.")
        return ruta_csv

    # --- DEFINICIÓN DEL GRAFO (DEPENDENCIAS) ---
    
    # 1. Instanciamos las tareas
    espera = esperar_api_fotmob()
    novedad = hay_informacion_nueva()
    lista_clubes = extraer_catalogo_clubes()
    tarea_plata = generar_capa_plata()
    
    # Instanciamos la nueva tarea de validación pasándole la salida de la capa plata
    validacion_final = validar_dataset_plata(tarea_plata)
    
    # 2. Instanciamos el mapeo dinámico
    procesamiento = procesar_club.expand(club=lista_clubes)

    # 3. Ruta lógica
    espera >> novedad >> lista_clubes >> procesamiento >> tarea_plata >> validacion_final

dag_fichajes = pipeline_fichajes()