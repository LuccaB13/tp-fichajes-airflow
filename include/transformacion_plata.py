import os
import json
import pandas as pd
import numpy as np

# Rutas estándar
BRONZE_DIR = "/usr/local/airflow/include/bronze"
SILVER_DIR = "/usr/local/airflow/include/silver"

#Aca pasamos el precio de texto con el simboo de auros al lado a un número entero en euros
def limpiar_coste(coste_str):
    
    if not isinstance(coste_str, str): return np.nan
    coste = coste_str.lower().replace('€', '').strip()
    try:
        if 'mill' in coste:
            num = float(coste.replace('mill.', '').replace(',', '.').strip())
            return int(num * 1000000)
        elif 'mil' in coste:
            num = float(coste.replace('mil', '').replace(',', '.').strip())
            return int(num * 1000)
        else:
            return float(coste.replace(',', '.'))
    except ValueError:
        return np.nan # Retorna nulo si no se puede parsear (ej. "Libre", "?")

#Parecido a lo anterior, pero acá estamos sacando el "cm" de la altura y devolviendo el número entero en centímetros, si no es válido retorna Nan
def limpiar_altura(altura_str):
    
    if not isinstance(altura_str, str): return np.nan
    try:
        return int(altura_str.replace('cm', '').strip())
    except ValueError:
        return np.nan

def consolidar_plata():
    #Acá extraemos todos los JSON de la capa bronce, los aplanamos y los consolidamos en un CSV de la capa plata
    #Al final va a quedar soo un csv con una fila por jugador/temporada, con todas las métricas sumadas y los datos biográficos limpios
    print("Iniciando consolidación de Capa Plata...")
    
    if not os.path.exists(BRONZE_DIR):
        print(f"Directorio bronce no encontrado: {BRONZE_DIR}")
        return None

    archivos_json = [f for f in os.listdir(BRONZE_DIR) if f.endswith('.json')]
    if not archivos_json:
        print("No hay archivos JSON en la capa bronce para procesar.")
        return None

    registros_planos = []

    # 1. Leer y aplanar todos los JSONs
    for archivo in archivos_json:
        ruta_archivo = os.path.join(BRONZE_DIR, archivo)
        try:
            with open(ruta_archivo, 'r', encoding='utf-8') as f:
                datos_jugador = json.load(f)
                
                # Cada JSON puede tener múltiples registros (torneos), por ejemplo si un jugador jugó la liga, una copa y la champions en la misma temporada
                for torneo in datos_jugador:
                    registro = {
                        "jugador_id": torneo.get("jugador_id"),
                        "nombre": torneo.get("nombre"),
                        "temporada": torneo.get("temporada"),
                        "torneo_nombre": torneo.get("torneo_nombre")
                    }
                    
                    # Extraer biografía
                    bio = torneo.get("biografia", {})
                    registro["club_destino"] = bio.get("club_destino")
                    registro["club_origen"] = bio.get("club_origen")
                    registro["es_destino_top_20"] = bio.get("es_destino_top_20")
                    registro["coste_fichaje_bruto"] = bio.get("coste_fichaje")
                    registro["posicion"] = bio.get("posicion_primaria")
                    registro["edad"] = bio.get("edad_al_fichaje")
                    registro["altura_bruta"] = bio.get("altura")
                    registro["pais"] = bio.get("pais")
                    registro["pie"] = bio.get("pie_preferido")
                    
                    # Extraer métricas y sumarlas al registro
                    metricas = torneo.get("metricas", {})
                    for key, value in metricas.items():
                        registro[f"stat_{key.replace(' ', '_').lower()}"] = value
                        
                    registros_planos.append(registro)
        except Exception as e:
            print(f"Error procesando {archivo}: {e}")

    if not registros_planos:
        print("No se extrajeron registros válidos.")
        return None

    # 2. Convertir a DataFrame
    df = pd.DataFrame(registros_planos)

    # 3. Limpieza de columnas base
    df['coste_fichaje_eur'] = df['coste_fichaje_bruto'].apply(limpiar_coste)
    df['altura_cm'] = df['altura_bruta'].apply(limpiar_altura)
    
    # Convertir tipos
    # Utilizamos pd.to_numeric para forzar la conversión, manejando errores (ej. edades como "Desconocida")
    df['edad'] = pd.to_numeric(df['edad'], errors='coerce').astype('Int64')

    # Eliminar columnas brutas que ya no sirven
    df = df.drop(columns=['coste_fichaje_bruto', 'altura_bruta'])

    # 4. Agregación (Una fila por jugador/temporada)
    # Definimos qué hacer con cada tipo de columna al agrupar
    # Las stats se suman, excepto los porcentajes o ratings que deberíamos promediar
    # Lo de los promedios es medio compliocado, por eso primero identificamos qué columnas son stats y cuáles son promedios
    
    
    columnas_bio = ['nombre', 'club_destino', 'club_origen', 'es_destino_top_20', 'coste_fichaje_eur', 'posicion', 'edad', 'altura_cm', 'pais', 'pie']
    
    # Separar stats acumulativas (sumar) vs promedios (mean)
    cols_stats = [c for c in df.columns if c.startswith('stat_')]
    cols_a_promediar = ['stat_rating', 'stat_pass_accuracy', 'stat_long_ball_accuracy', 'stat_cross_accuracy', 'stat_dribbles_success_rate', 'stat_duels_won_%', 'stat_aerials_won_%']

    # Separamos en mean y sum, mean es para las métricas que son porcentajes o ratings, sum es para las métricas acumulativas como goles, asistencias, etc.
    # Y para el resto de datos, solo toammos el primer valor (ya que son datos biográficos que no cambian por torneo), esto es para evitar dator duplicados al agrupar por jugador_id y temporada
    # Para qeu quede claro, este seria un ejemplo: supongamos que tomo tres promedios de gol, uno por el torneo, otro por la copa y otro por la champions, 
    # al final quiero que me quede un promedio de gol por temporada, no por torneo, entonces hago un mean de esos tres valores. En cambio, si tomo los goles totales, quiero sumarlos para que me quede el total de goles en la temporada.
    # Esto esta para repensarlo a futuro, porque si un jugador jugó mas en la liga que en una copa, y el promedio de gol de la liga es 0.5 y el de la copa es 1, el promedio final sería 0.75
    # Esto es un problema porque no estoy ponderando por minutos jugados, entonces el promedio final no es representativo. Pero por ahora lo dejamos así, y en el futuro podemos mejorar esto.
    dict_agregacion = {col: 'first' for col in columnas_bio} 
    
    for col in cols_stats:
        if col in cols_a_promediar:
            dict_agregacion[col] = 'mean'
        else:
            dict_agregacion[col] = 'sum'
            
    # Agrupamos por ID y Temporada
    df_consolidado = df.groupby(['jugador_id', 'temporada']).agg(dict_agregacion).reset_index()

    # Guardar la Capa Plata, acá lo guardamos en una carpeta como la del bronze (es el csv)
    os.makedirs(SILVER_DIR, exist_ok=True)
    ruta_salida = os.path.join(SILVER_DIR, "dataset_fichajes_silver.csv")
    
    df_consolidado.to_csv(ruta_salida, index=False, encoding='utf-8')
    print(f"Capa Plata generada con éxito: {len(df_consolidado)} registros en {ruta_salida}")
    
    return ruta_salida

if __name__ == "__main__":

    consolidar_plata()