import os
import json
import pandas as pd
import numpy as np

# Rutas estándar (asumiendo ejecución dentro de Docker/Airflow)
BRONZE_DIR = "/usr/local/airflow/include/bronze"
SILVER_DIR = "/usr/local/airflow/include/silver"

def limpiar_coste(coste_str):
    """Convierte '50,00 mill. €' a 50000000. Maneja casos de miles o formato libre."""
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

def limpiar_altura(altura_str):
    """Extrae los centímetros como entero."""
    if not isinstance(altura_str, str): return np.nan
    try:
        return int(altura_str.replace('cm', '').strip())
    except ValueError:
        return np.nan

def consolidar_plata():
    """Lee todos los JSON de la capa bronce, consolida, limpia y guarda en capa plata."""
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
                
                # Cada JSON puede tener múltiples registros (torneos)
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
    # Las stats se suman, excepto los porcentajes o ratings que deberíamos promediar (pesados por minutos idealmente, pero promedio simple sirve por ahora)
    
    columnas_bio = ['nombre', 'club_destino', 'club_origen', 'es_destino_top_20', 'coste_fichaje_eur', 'posicion', 'edad', 'altura_cm', 'pais', 'pie']
    
    # Separar stats acumulativas (sumar) vs promedios (mean)
    cols_stats = [c for c in df.columns if c.startswith('stat_')]
    cols_a_promediar = ['stat_rating', 'stat_pass_accuracy', 'stat_long_ball_accuracy', 'stat_cross_accuracy', 'stat_dribbles_success_rate', 'stat_duels_won_%', 'stat_aerials_won_%']
    
    dict_agregacion = {col: 'first' for col in columnas_bio} # Tomamos el primer valor para datos estáticos
    
    for col in cols_stats:
        if col in cols_a_promediar:
            dict_agregacion[col] = 'mean'
        else:
            dict_agregacion[col] = 'sum'
            
    # Agrupamos por ID y Temporada
    df_consolidado = df.groupby(['jugador_id', 'temporada']).agg(dict_agregacion).reset_index()

    # 5. Guardar la Capa Plata
    os.makedirs(SILVER_DIR, exist_ok=True)
    ruta_salida = os.path.join(SILVER_DIR, "dataset_fichajes_silver.csv")
    
    df_consolidado.to_csv(ruta_salida, index=False, encoding='utf-8')
    print(f"Capa Plata generada con éxito: {len(df_consolidado)} registros en {ruta_salida}")
    
    return ruta_salida

if __name__ == "__main__":
    # Para probar el script localmente antes de pasarlo a Airflow
    # Cambia BRONZE_DIR a tu ruta local en Windows para probar
    consolidar_plata()