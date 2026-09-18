"""Paquete de extracción y transformación del dataset de fichajes.

La lógica pesada vive acá y no en `dags/`, porque el dag-processor de Airflow
vuelve a parsear la carpeta `dags/` cada pocos segundos: ahí va sólo la
definición del flujo.

Módulos:
    bronce         rutas y escritura/lectura de la capa bronce (crudo, comprimido)
    uefa           cliente de la API de coeficientes de UEFA
    transfermarkt  cliente y parseo del HTML de Transfermarkt
    fotmob         cliente de la API interna de FotMob
    clubes         normalización de nombres y cruce UEFA <-> Transfermarkt
    plata          bronce -> capa plata (aplanado, limpieza, enriquecimiento)
    esquema        columnas, tipos y reglas de validación del dataset final
"""
