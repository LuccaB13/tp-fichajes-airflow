import os
import requests
import json
from bs4 import BeautifulSoup
import time

HEADERS_HTML = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept-Language": "es-ES,es;q=0.9"
}

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
    "Accept": "application/json"
}

def obtener_perfil_fotmob(nombre_jugador, coste, temporada_objetivo, club_destino, club_origen, es_top_20):
    try:
        print(f"  -> Buscando a '{nombre_jugador}' en FotMob...")
        
        url_search = "https://www.fotmob.com/api/data/search/suggest"
        id_jugador = None
        
        partes_nombre = nombre_jugador.split()
        intentos_busqueda = [nombre_jugador]
        
        if len(partes_nombre) > 2:
            intentos_busqueda.append(f"{partes_nombre[0]} {partes_nombre[-1]}")
        if len(partes_nombre) >= 2:
            intentos_busqueda.append(f"{partes_nombre[-1]}")

        for intento in intentos_busqueda:
            resp_search = requests.get(url_search, headers=HEADERS_API, params={"term": intento}, timeout=10)
            if resp_search.status_code == 200 and resp_search.json():
                sugerencias = resp_search.json()[0].get('suggestions', [])
                if sugerencias:
                    id_jugador = sugerencias[0].get('id')
                    print(f"     [+] Match exitoso (ID: {id_jugador})")
                    break 
                    
        if not id_jugador:
            print(f"     [!] Imposible encontrar a {nombre_jugador} en FotMob.")
            return

        url_perfil = "https://www.fotmob.com/api/data/playerData"
        resp_perfil = requests.get(url_perfil, headers=HEADERS_API, params={"id": id_jugador}, timeout=10)
        
        if resp_perfil.status_code != 200:
            return
            
        datos_perfil = resp_perfil.json()
        
        info_bio = {
            "club_destino": club_destino,
            "club_origen": club_origen,
            "es_destino_top_20": es_top_20,
            "coste_fichaje": coste,
            "posicion_primaria": "Desconocida",
            "edad_al_fichaje": "Desconocida",
            "altura": "Desconocida",
            "pais": "Desconocido",
            "pie_preferido": "Desconocido"
        }
        
        if 'positionDescription' in datos_perfil and datos_perfil['positionDescription']:
            pos_data = datos_perfil['positionDescription']
            if isinstance(pos_data, dict):
                info_bio['posicion_primaria'] = pos_data.get('primaryPosition', {}).get('label', 'Desconocida')
        
        anio_fichaje = int(temporada_objetivo.split('/')[0])
        
        # BLINDAJE: or [] previene el error si playerInformation es null
        player_info = datos_perfil.get('playerInformation') or []
        for item in player_info:
            titulo = item.get('title', '')
            valor_obj = item.get('value', {}) or {}
            valor_limpio = valor_obj.get('fallback', '') if isinstance(valor_obj, dict) else str(valor_obj)
            
            if titulo == "Age": 
                try:
                    edad_actual = int(valor_limpio)
                    info_bio['edad_al_fichaje'] = edad_actual - (2026 - anio_fichaje)
                except:
                    info_bio['edad_al_fichaje'] = valor_limpio
            elif titulo == "Height": info_bio['altura'] = valor_limpio
            elif titulo == "Country": info_bio['pais'] = valor_limpio
            elif titulo == "Preferred foot": info_bio['pie_preferido'] = valor_limpio

        anio_calendario = temporada_objetivo.split('/')[0] 
        temporadas_validas = [temporada_objetivo, anio_calendario]
        torneos_a_procesar = []
        
        # BLINDAJE: Aseguramos que statSeasons no rompa el bucle
        stat_seasons = datos_perfil.get('statSeasons') or []
        for temporada in stat_seasons:
            if temporada.get('seasonName') in temporadas_validas:
                tournaments = temporada.get('tournaments') or []
                for torneo in tournaments:
                    if torneo.get('hasDeepStats'):
                        torneos_a_procesar.append({
                            "nombre": torneo.get('name'),
                            "entryId": torneo.get('entryId'),
                            "tournamentId": torneo.get('tournamentId')
                        })
                
        if not torneos_a_procesar:
            print(f"     [!] No hay Deep Stats para las temporadas {temporadas_validas}.")
            return

        capa_bronce = []
        url_deep_stats = "https://www.fotmob.com/api/data/playerStats"
        
        for torneo in torneos_a_procesar:
            resp_stats = requests.get(url_deep_stats, headers=HEADERS_API, params={
                "playerId": id_jugador, 
                "seasonId": torneo['entryId'],
                "isFirstSeason": "false"
            }, timeout=10)
            
            if resp_stats.status_code == 200:
                datos_stats = resp_stats.json()
                stats_section = datos_stats.get('statsSection')
                
                if stats_section:
                    registro_torneo = {
                        "jugador_id": id_jugador,
                        "nombre": nombre_jugador,
                        "temporada": temporada_objetivo,
                        "torneo_nombre": torneo['nombre'],
                        "torneo_id": torneo.get('tournamentId'),
                        "biografia": info_bio, 
                        "metricas": {} 
                    }
                    
                    tarjetas_superiores = datos_stats.get('topStatCards') or datos_stats.get('topStatCard') or {}
                    items_tarjetas = tarjetas_superiores.get('items') or []
                    for card in items_tarjetas:
                        try: registro_torneo["metricas"][card.get('title')] = float(card.get('statValue', 0))
                        except: pass
                    
                    items_seccion = stats_section.get('items') or []
                    for seccion in items_seccion:
                        items_metrica = seccion.get('items') or []
                        for metrica in items_metrica:
                            try: registro_torneo["metricas"][metrica.get('title')] = float(metrica.get('statValue', 0))
                            except: pass
                            
                    capa_bronce.append(registro_torneo)
            time.sleep(1)

        if capa_bronce:
            nombre_limpio = nombre_jugador.replace(" ", "_").lower()
            ruta_directorio = "/usr/local/airflow/include/bronze"
            os.makedirs(ruta_directorio, exist_ok=True)
            ruta_archivo = f"{ruta_directorio}/bronce_{nombre_limpio}_{temporada_objetivo.replace('/', '-')}.json"
            
            with open(ruta_archivo, 'w', encoding='utf-8') as archivo_json:
                json.dump(capa_bronce, archivo_json, indent=4, ensure_ascii=False)
            print(f"     [v] ¡Éxito! Archivo guardado en {ruta_archivo}")

    except Exception as e:
        # PARACAÍDAS: Si cualquier cosa falla, lo ataja acá y el programa sigue con el próximo jugador.
        print(f"     [X] Error inesperado al procesar a {nombre_jugador}: {e}")


def obtener_catalogo_clubes(cantidad_maxima=384):
    print(f"--- OBTENIENDO EL TOP {cantidad_maxima} DE CLUBES UEFA ---")
    clubes_base = []
    nombres_vistos = set() 
    pagina = 1
    
    while len(clubes_base) < cantidad_maxima:
        url_ranking = f"https://www.transfermarkt.com.ar/statistik/klubrangliste?page={pagina}"
        try:
            resp = requests.get(url_ranking, headers=HEADERS_HTML, timeout=15)
        except Exception as e:
            print(f"Error de conexión con Transfermarkt: {e}")
            break
            
        if resp.status_code != 200:
            print("Límite de páginas alcanzado o acceso denegado. Finalizando extracción.")
            break
            
        soup = BeautifulSoup(resp.text, 'html.parser')
        tabla = soup.find('table', class_='items')
        
        if not tabla:
            print("No se encontró la tabla en la página. Finalizando extracción.")
            break
            
        filas = tabla.find('tbody').find_all('tr')
        
        if not filas:
            print(f"No hay más equipos listados en la página {pagina}. Finalizando extracción.")
            break
            
        for fila in filas:
            celda_club = fila.find('td', class_='hauptlink')
            if celda_club:
                enlace = celda_club.find('a')
                if enlace and 'href' in enlace.attrs:
                    nombre_club = enlace.text.strip()
                    
                    if nombre_club and nombre_club not in nombres_vistos:
                        url_relativa = enlace['href']
                        partes = url_relativa.split('/')
                        if "verein" in partes:
                            club_id = partes[partes.index("verein") + 1]
                            club_slug = partes[1]
                            
                            es_top_20 = len(clubes_base) < 20
                            
                            clubes_base.append({
                                "nombre": nombre_club, 
                                "slug": club_slug, 
                                "id": club_id,
                                "es_top_20": es_top_20
                            })
                            nombres_vistos.add(nombre_club)
            
            if len(clubes_base) >= cantidad_maxima:
                break
                
        pagina += 1
        time.sleep(2)
        
    return clubes_base