from airflow.decorators import dag, task
from datetime import datetime

from include.extraccion_fotmob import obtener_catalogo_clubes, obtener_perfil_fotmob, HEADERS_HTML

@dag(
    dag_id="extraccion_fichajes_fotmob",
    schedule=None, 
    start_date=datetime(2024, 1, 1),
    catchup=False,
    tags=["ingesta", "capa_bronce"],
)
def pipeline_fichajes():

    @task
    def extraer_catalogo_clubes():
        return obtener_catalogo_clubes(cantidad_maxima=384)

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
            print(f"\n[AÑO {anio_tm}] Buscando fichajes en Transfermarkt para {club_destino_actual}")
            
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
                                        print(f" [CACHÉ] {nombre} ya fue extraído. Saltando...")
                                        continue 

                                    print(f" -> {nombre} | Origen: {club_origen}")
                                    obtener_perfil_fotmob(nombre, coste, temporada_fotmob, club_destino_actual, club_origen, es_top_20)
                                    time.sleep(2) 
                        break 
            else:
                print(f"Error HTTP leyendo los fichajes de {club_destino_actual} en {anio_tm}.")
            
            time.sleep(3) 
            
        return f"Carga finalizada para {club_destino_actual}"

    lista_clubes = extraer_catalogo_clubes()
    procesar_club.expand(club=lista_clubes)

dag_fichajes = pipeline_fichajes()