"""¿Qué factores hacen que un jugador llegue a un club top 20? · Entrega 4 · Grupo 7

    streamlit run app/app.py

Lee lo que deja app/build_app.py en app/datos/. No entrena nada: carga el modelo guardado.
"""
import base64
import functools
import json
import os
import sys

import altair as alt
import joblib
import numpy as np
import pandas as pd
import streamlit as st

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)
import modelo as m  # noqa: E402  (pickle necesita ZPorRol y a_numero de este módulo)
import portada  # noqa: E402

DATOS = os.path.join(AQUI, "datos")
alt.data_transformers.disable_max_rows()

# Los colores significan lo mismo en toda la aplicación:
#   azul      = fue a un top 20 (y el modelo lo encontró)
#   celeste   = fue a un top 20 y el modelo no lo vio
#   naranja   = el modelo dijo top 20 y no fue
#   gris      = no fue a un top 20
# El verde (#2e8540) es sólo de la interfaz: la portada, las cifras grandes y los controles. No se usa en los
# gráficos, porque el verde se lee como «correcto» y los datos no son ni buenos ni malos.
AZUL, CELESTE, NARANJA, GRIS = "#2a78d6", "#9cc3ef", "#d95926", "#b5b4ae"

NOMBRES_STATS = {
    "stat_minutes": "Minutos", "stat_matches": "Partidos", "stat_goals": "Goles", "stat_xg": "xG",
    "stat_assists": "Asistencias", "stat_shots_on_target": "Tiros al arco",
    "stat_touches_in_opposition_box": "Toques en el área rival", "stat_aerials_won_%": "Duelos aéreos ganados (%)",
    "stat_dribbles_success_rate": "Gambetas exitosas (%)", "stat_successful_crosses": "Centros exitosos",
    "stat_big_chances_created": "Ocasiones claras creadas", "stat_chances_created": "Ocasiones creadas",
    "stat_pass_accuracy": "Precisión de pase (%)", "stat_possession_won_final_3rd": "Recuperaciones en campo rival",
    "stat_tackles": "Quites", "stat_interceptions": "Intercepciones", "stat_duels_won_%": "Duelos ganados (%)",
    "stat_recoveries": "Recuperaciones", "stat_saves": "Atajadas", "stat_save_percentage": "Atajadas (%)",
    "stat_goals_conceded_inv": "Goles recibidos (con signo menos)", "stat_goals_prevented": "Goles evitados",
    "stat_high_claims": "Salidas por arriba",
}

st.set_page_config(page_title="¿Qué lleva a un jugador a un top 20?", page_icon=":material/sports_soccer:",
                   layout="wide")


def grafico(chart, **kw):
    """st.altair_chart con un margen interno, para que los títulos de los ejes no queden cortados en el borde."""
    return st.altair_chart(chart.properties(padding={"left": 18, "top": 14, "right": 14, "bottom": 10}), **kw)



def version_datos():
    """Cambia cuando cambia un archivo de app/datos: así la caché no sigue sirviendo datos viejos después de un push."""
    return tuple(sorted((f, os.path.getmtime(os.path.join(DATOS, f))) for f in os.listdir(DATOS)))


@st.cache_resource
def cargar_modelo(version):
    return joblib.load(os.path.join(DATOS, "modelo.joblib"))


@st.cache_data
def cargar_datos(version):
    with open(os.path.join(DATOS, "resumen.json"), encoding="utf-8") as f:
        resumen = json.load(f)
    fichajes = pd.read_csv(os.path.join(DATOS, "fichajes_app.csv"))
    columnas = pd.read_csv(os.path.join(DATOS, "fichajes_modelo.csv"))
    clubes = pd.read_csv(os.path.join(DATOS, "clubes.csv"))
    rangos = pd.read_csv(os.path.join(DATOS, "rangos.csv"))
    return resumen, fichajes, columnas, clubes, rangos


def pct(x, dec=0):
    return f"{x * 100:.{dec}f} %".replace(".", ",")


def num(x, dec=3):
    return f"{x:.{dec}f}".replace(".", ",")


def miles(x):
    return f"{int(x):,}".replace(",", ".")


resumen, fichajes, columnas_modelo, clubes, rangos = cargar_datos(version_datos())
final = cargar_modelo(version_datos())
t = resumen["test"]
fp_cerca = resumen["fp_destino"]["puesto 21 a 50"] + resumen["fp_destino"]["puesto 51 a 100"]

st.markdown("""
<style>
.etiqueta {font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; color: #6b6b6b; margin-top: 2.2rem;}
.cifra {font-size: 2.6rem; font-weight: 700; color: #2e8540; line-height: 1.1;}
.tipo-error {font-size: 1.12rem; font-weight: 700; border-left: 4px solid #d95926; padding-left: 0.6rem;
             margin: 1.8rem 0 0.4rem 0;}
.tipo-error-fn {font-size: 1.12rem; font-weight: 700; border-left: 4px solid #9cc3ef; padding-left: 0.6rem;
                margin: 1.8rem 0 0.4rem 0;}
.carrusel {display: flex; gap: 16px; overflow-x: auto; scroll-snap-type: x mandatory; padding: 4px 2px 14px 2px;}
.tarjeta {flex: 0 0 270px; scroll-snap-align: start; border: 1px solid #e1e4e1; border-radius: 10px; background: #fff;
          overflow: hidden;}
.tarjeta img {width: 100%; height: 300px; object-fit: cover; object-position: 50% 0%; display: block;}
.tarjeta .cuerpo {padding: 10px 12px 12px 12px; font-size: 0.86rem; line-height: 1.4; color: #222;}
.tarjeta .nombre {font-size: 1.02rem; font-weight: 700; margin-bottom: 2px;}
.tarjeta .dato {color: #555; margin-bottom: 6px;}
.tarjeta .modelo {background: #eef4fb; border-radius: 6px; padding: 4px 8px; margin: 6px 0; font-size: 0.82rem;}
.tarjeta .credito {font-size: 0.7rem; color: #888; margin-top: 8px;}
.idea {font-size: 1.35rem; font-weight: 600; border-left: 4px solid #2e8540; padding-left: 0.8rem; margin: 1rem 0;}
</style>""", unsafe_allow_html=True)

# =============================================================================== PORTADA
FACTORES_TALLO = ["rendimiento comparado con su puesto", "nivel UEFA del club de origen", "edad al fichar", "puesto"]


ETIQUETA_CORTA = {"fuera del ranking": "sin ranking", "Mediocampo defensivo": "Medio. defensivo",
                  "Mediocampo ofensivo": "Medio. ofensivo", "Delantero centro": "Del. centro",
                  "Delantero extremo": "Del. extremo", "Defensor central": "Def. central"}


def tasa_por_nivel(datos, factor):
    """% real que fue a un top 20 y probabilidad media del modelo, por nivel del factor."""
    g = datos.groupby(factor)
    tabla = pd.DataFrame({"fichajes": g.size(), "tasa": g["es_destino_top_20"].mean(), "modelo": g["proba"].mean()})
    orden = [n for n in m.ORDEN_NIVELES[factor] if n in tabla.index]
    tabla = tabla.loc[orden].reset_index(names="nivel")
    tabla["etiqueta"] = tabla["nivel"].map(lambda n: ETIQUETA_CORTA.get(n, n))
    return tabla


rend = tasa_por_nivel(fichajes, "rendimiento comparado con su puesto").set_index("nivel")["tasa"]
liga = tasa_por_nivel(fichajes, "liga de origen").set_index("nivel")["tasa"]
joven = fichajes["edad al fichar"].eq("≤19")
tasa_joven, tasa_resto = fichajes.loc[joven, "es_destino_top_20"].mean(), fichajes.loc[~joven, "es_destino_top_20"].mean()

st.markdown(portada.html(
    "¿Qué factores hacen que un jugador llegue a un club top 20 de Europa?",
    f"<b>{miles(resumen['n_ana'])}</b> fichajes de <b>{miles(resumen['n_jugadores'])}</b> jugadores, cinco temporadas "
    "(2022/23 a 2026/27): cómo rindieron, de dónde venían y qué edad tenían."), unsafe_allow_html=True)
st.write(
    "Cada temporada, miles de jugadores cambian de club. Unos pocos terminan en uno de los 20 clubes con mejor "
    "coeficiente UEFA. ¿Qué tienen en común? Miramos lo que se sabe **antes** del fichaje —cómo jugó la temporada "
    "anterior, de qué club viene, su edad y su puesto— y cuánto pesa cada cosa.")
def uno_de_cada(tasa):
    """0,194 → «1 de cada 5»; si la tasa queda bastante arriba de 1/N, «más de 1 de cada N»."""
    n = max(1, round(1 / tasa))
    if n > 10:                                   # de 10 para arriba, a la decena o media decena: 1 de cada 20
        n = 5 * round(n / 5)
    return ("más de " if tasa > 1 / n * 1.05 else "") + f"1 de cada {n}"


h5_portada = pd.DataFrame(resumen["h5"])
tasa_mejores = h5_portada.query("origen == 'alto' and rendimiento == 'alto'")["tasa"].iloc[0]
st.markdown(
    '<div class="idea">Llegan a un top 20, sobre todo, los que rindieron bien para su puesto y vienen de un club '
    'fuerte de Europa.</div>', unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
c1.markdown(f'<div class="cifra">{uno_de_cada(resumen["tasa_top20"])}</div>'
            'de todos los fichajes termina en un club top 20 de UEFA.', unsafe_allow_html=True)
c2.markdown(f'<div class="cifra">{uno_de_cada(liga["liga top 5"])}</div>'
            'si el jugador viene de una liga top 5 (Premier, LaLiga, Serie A, Bundesliga o Ligue 1). '
            f'Desde las demás ligas, {uno_de_cada(liga["otra liga"])}.', unsafe_allow_html=True)
c3.markdown(f'<div class="cifra">{uno_de_cada(tasa_mejores).capitalize()}</div>'
            'si viene de un club fuerte de Europa y tuvo una temporada de alto rendimiento: entre el tercio de mejores de su puesto, comparado con todos los fichajes del mismo puesto.',
            unsafe_allow_html=True)
st.caption(f"Medido sobre {miles(resumen['n_ana'])} fichajes de {miles(resumen['n_jugadores'])} jugadores, cinco "
           f"temporadas (2022/23 a 2026/27). Un random forest que predice el destino con estos datos (f1 macro "
           f"{num(t['f1'])} en el test, contra {num(resumen['piso']['media'])} del piso) usa los factores en el mismo "
           f"orden. Datos del pipeline: {resumen['datos']}.")

# =============================================================================== TALLO 1 · LOS DATOS
st.markdown('<div class="etiqueta">Los datos</div>', unsafe_allow_html=True)
st.header("Sólo 1 de cada 10 fichajes termina en un club top 20, temporada tras temporada")
temporadas = pd.DataFrame(resumen["por_temporada"])
temporadas["no top 20"] = temporadas["fichajes"] - temporadas["top20"]
temporadas["tasa"] = temporadas["top20"] / temporadas["fichajes"]
largo = temporadas.melt(id_vars=["temporada_fichaje", "tasa"], value_vars=["top20", "no top 20"],
                        var_name="destino", value_name="cantidad")
largo["destino"] = largo["destino"].replace({"top20": "fue a un top 20", "no top 20": "no fue a un top 20"})
barras = alt.Chart(largo).mark_bar().encode(
    y=alt.Y("temporada_fichaje:N", title=None),
    x=alt.X("cantidad:Q", title="fichajes", stack="zero"),
    color=alt.Color("destino:N", scale=alt.Scale(domain=["fue a un top 20", "no fue a un top 20"],
                                                range=[AZUL, GRIS]), legend=alt.Legend(title=None, orient="top")),
    order=alt.Order("destino:N"),
    tooltip=["temporada_fichaje", "destino", "cantidad"])
textos = alt.Chart(temporadas).mark_text(align="left", dx=4, color="#333").encode(
    y="temporada_fichaje:N", x=alt.X("fichajes:Q"), text=alt.Text("tasa:Q", format=".0%"))
st.write(
    "Cada barra es una temporada de fichajes: la parte azul son los que fueron a un club top 20 y la gris, el resto. "
    f"El número a la derecha es la proporción que llegó, y casi no cambia: entre 9 % y 11 % todos los años "
    f"({pct(resumen['tasa_top20'], 1)} en total). Por eso el modelo se mide con cuidado: uno que dijera siempre «no "
    "llega» acertaría 9 de cada 10 veces sin encontrar a nadie.")
grafico((barras + textos).properties(height=230), width="stretch")

with st.expander("Cómo lo sabemos"):
    st.markdown(f"""
**De dónde salen.** Un pipeline en Airflow (este repositorio, `dags/dag_fichajes.py`) cruza tres fuentes:
**Transfermarkt** (el fichaje: jugador, club de origen y de destino, edad, liga), **FotMob** (el rendimiento de la
temporada anterior al fichaje: 56 métricas) y **UEFA** (el coeficiente de clubes y de países de las últimas diez
temporadas). Guarda el crudo (bronce), arma el dataset consolidado (plata), lo valida y lo publica fechado. Este
análisis usa la publicación `{resumen['datos']}`.

**Qué es una fila.** Un fichaje: un jugador que llega a un club europeo en una temporada, con sus estadísticas de la
temporada **anterior**. Un mismo jugador puede aparecer más de una vez (fichajes de temporadas distintas).

**El objetivo.** `es_destino_top_20`: el club de destino está entre los 20 primeros del coeficiente UEFA de clubes.

**Qué se filtró, paso por paso:**
""")
    pasos = pd.DataFrame(resumen["pasos"], columns=["paso", "fichajes que quedan"])
    pasos["por qué"] = [
        "la salida del pipeline: cinco temporadas, clubes de destino hasta el puesto 200 de UEFA",
        "sin la temporada anterior no hay rendimiento que medir (son sobre todo juveniles)",
        "las promociones del filial al primer equipo no son una compra: el destino ya era ese club",
        "el cruce con FotMob es por nombre; si una fuente dice arquero y la otra no, las stats son de otra persona",
    ]
    pasos["fichajes que quedan"] = pasos["fichajes que quedan"].map(miles)
    st.table(pasos.set_index("paso"))
    st.markdown(f"""
**Columnas que se descartaron por fuga** (existen recién **en** el fichaje, o se calculan con el destino):
{", ".join(f"`{c}`" for c in resumen["fuga"])}. Todo lo del destino es la respuesta escrita de otra forma.

**Lo que entra al modelo:** las 23 estadísticas que armaban el puntaje de rendimiento de la Entrega 2, cada una
comparada con los de su mismo puesto; el puesto; la edad; la temporada; y del club de origen, su coeficiente UEFA y el
de su país, y si viene de una liga top 5, de un filial o de Europa.
""")

# =============================================================================== TALLO 2 · LO QUE ENCONTRAMOS
st.markdown('<div class="etiqueta">Lo que encontramos</div>', unsafe_allow_html=True)
st.header("Tres factores separan a los que llegan: el rendimiento, el club de origen y la juventud; el puesto no")
TITULOS_PANEL = {"rendimiento comparado con su puesto": "Rendimiento para su puesto (tercios)",
                 "nivel UEFA del club de origen": "Nivel UEFA del club de origen",
                 "edad al fichar": "Edad al fichar", "puesto": "Puesto"}
ESCALA_TASA = alt.Scale(domain=[0, 0.25])
referencia = alt.Chart(pd.DataFrame({"tasa": [resumen["tasa_top20"]]})).mark_rule(
    strokeDash=[4, 3], color="#777").encode(y=alt.Y("tasa:Q", scale=ESCALA_TASA))
st.write(
    "Cada panel es un factor y cada barra, un nivel de ese factor: su altura es el % de esos fichajes que terminó en "
    "un club top 20. Los cuatro paneles tienen **la misma escala**, y la línea punteada es la tasa de todos los "
    f"fichajes ({pct(resumen['tasa_top20'], 1)}): una barra arriba de la línea llega más que el promedio. En los tres "
    "primeros, la barra de la derecha está muy por encima de la de la izquierda: rendir más que los de su puesto, "
    "venir de un club fuerte en UEFA y llegar muy joven multiplican las chances. En el último, todas las barras quedan "
    "pegadas a la línea: el puesto no cambia casi nada.")
paneles = []
for k, factor in enumerate(FACTORES_TALLO):
    tabla = tasa_por_nivel(fichajes, factor)
    base_p = alt.Chart(tabla).encode(x=alt.X("etiqueta:N", sort=list(tabla["etiqueta"]), title=None,
                                             axis=alt.Axis(labelAngle=-40 if factor == "puesto" else 0,
                                                           labelOverlap=False, labelLimit=120)))
    barras_p = base_p.mark_bar(color=AZUL).encode(
        y=alt.Y("tasa:Q", scale=ESCALA_TASA, axis=alt.Axis(format="%", title="% que va a un top 20" if k == 0 else None,
                                                           labels=k == 0, ticks=k == 0)),
        tooltip=[alt.Tooltip("nivel:N"), alt.Tooltip("tasa:Q", format=".1%", title="% top 20"),
                 alt.Tooltip("fichajes:Q")])
    textos_p = base_p.mark_text(dy=-7, fontSize=11, color="#333").encode(
        y=alt.Y("tasa:Q", scale=ESCALA_TASA), text=alt.Text("tasa:Q", format=".0%"))
    paneles.append((barras_p + textos_p + referencia).properties(width={"puesto": 300, "nivel UEFA del club de origen": 210}.get(factor, 170), height=240,
                                                                title=TITULOS_PANEL[factor]))
grafico(alt.hconcat(*paneles).resolve_scale(y="shared"), width="content")

h5 = pd.DataFrame(resumen["h5"])
alto_alto = h5.query("origen == 'alto' and rendimiento == 'alto'")["tasa"].iloc[0]
bajo_alto = h5.query("origen == 'bajo' and rendimiento == 'alto'")["tasa"].iloc[0]
st.write(
    "**El rendimiento y el club de origen suman por separado.** Este mapa cruza los dos: las columnas son el "
    "rendimiento para su puesto y las filas, el nivel UEFA del club de origen, en tercios cada uno. Cada casilla es el "
    "% de esos fichajes que llegó a un top 20: cuanto más oscura, más alto. Con el mismo rendimiento alto, venir de un "
    f"club de nivel bajo da {pct(bajo_alto, 1)} y de uno alto, {pct(alto_alto, 1)}: el club de origen agrega algo que "
    "el rendimiento no dice. La esquina de arriba a la derecha —club fuerte y temporada de alto rendimiento— es el "
    "«más de 1 de cada 3» de la portada.")
orden = ["bajo", "medio", "alto"]
base_h5 = alt.Chart(h5).encode(
    x=alt.X("rendimiento:O", sort=orden, title="rendimiento para su puesto", axis=alt.Axis(labelAngle=0)),
    y=alt.Y("origen:O", sort=orden[::-1], title="club de origen", axis=alt.Axis(titlePadding=10)))
grafico((base_h5.mark_rect().encode(
    color=alt.Color("tasa:Q", scale=alt.Scale(scheme="blues", domain=[0, 0.4]),
                    legend=alt.Legend(title="% top 20", format=".0%")),
    tooltip=[alt.Tooltip("tasa:Q", format=".1%", title="% top 20"), alt.Tooltip("n:Q", title="fichajes")])
    + base_h5.mark_text(fontSize=14).encode(text=alt.Text("tasa:Q", format=".1%"),
                                            color=alt.condition(alt.datum.tasa > 0.2, alt.value("white"),
                                                                alt.value("#222"))))
    .properties(height=240, width=460), width="content")

with st.expander("Cómo lo sabemos"):
    st.markdown("""
**Hipótesis que se sostuvieron** (Entrega 2, separación estandarizada entre los que van a un top 20 y el resto):
- **Rendimiento (Hipótesis 4):** el puntaje de rendimiento separa **0,815**, verde.
- **Club de origen (Hipótesis 5):** su coeficiente UEFA separa **0,749** (amarillo); fuera de las ligas top 5, **0,895**
  (verde). Y casi no se correlaciona con el rendimiento (Spearman **0,18**): mide otra cosa, el contexto.
- **Edad (Hipótesis 6):** sola separa poco (**0,143**, rojo) porque no es una recta: el salto está en los 19 años o
  menos. Cruzada con los minutos aparece con fuerza.

**Una que no se sostuvo (Hipótesis 2, altura):** separación **0,044**, rojo: 0,3 cm de diferencia. La altura no entró al
modelo.

**Cómo se construyeron los gráficos.** Cada barra (y cada casilla del mapa) es el % de los fichajes de ese nivel que fue
a un top 20: son datos reales, no predicciones del modelo.
- **Rendimiento:** el puntaje de la Entrega 2, el promedio de las 7 estadísticas propias del puesto (minutos, partidos y
  5 del rol), cada una pasada a z **dentro de su puesto**, así un central se compara con centrales. Cortado en tercios
  con la misma cantidad de fichajes.
- **Club de origen:** su coeficiente UEFA en escala logarítmica, en tercios, más los clubes que no están en el ranking.
- **Edad** en cuatro grupos, y el **puesto** en los 7 roles.

La escala vertical es la misma en los cuatro paneles (Unidad 4, 5.4: cuando los paneles se comparan, la escala se
comparte) y llega hasta 25 %, para que la línea del 10 % quede a la vista. Se calcula sobre los 7.410 fichajes de la
población actual; la Entrega 2 usaba 7.437 (antes de sacar el cruce roto), y por eso las cifras cambian en décimas.
""")

# =============================================================================== TALLO 3 · EL MODELO
bloques = pd.DataFrame(resumen["bloques"])
bloques["factor_corto"] = bloques["factor"].str.replace(r" \(.*\)", "", regex=True)
# lo que el modelo aprendió es lo que saca por encima del piso; cada factor, qué parte de eso se pierde sin él
aprendido = t["f1"] - resumen["piso"]["media"]
bloques["pierde"] = (bloques["caida"] / aprendido).clip(lower=0)
bloques["rotulo"] = bloques["pierde"].map(lambda v: pct(v))
b = bloques.set_index("factor_corto")["pierde"]
st.markdown('<div class="etiqueta">El modelo</div>', unsafe_allow_html=True)
st.header(f"El modelo confirma el orden: sin el rendimiento pierde más de la mitad de lo que aprendió, y sin el club "
          f"de origen más de un tercio")
st.write(
    "**Hicimos un modelo de predicción.** Con lo que se sabe de un fichaje **antes** de que ocurra —cómo jugó el "
    "jugador la temporada anterior comparado con los de su puesto, de qué club y de qué liga viene, su edad, su puesto "
    "y la temporada— un **random forest** (300 árboles de decisión que votan) calcula la probabilidad de que el fichaje "
    "termine en un club top 20. Lo entrenamos con el 80 % de los fichajes y lo medimos una sola vez con el 20 % "
    f"restante, que nunca vio: saca un f1 macro de **{num(t['f1'])}**, contra {num(resumen['piso']['media'])} de un "
    "modelo que dijera siempre «no llega». De cada 5 jugadores que señala, 2 llegan, cuando la tasa general es 1 de "
    "cada 10.")
st.write(
    "**En qué se apoya.** Para saber qué factores usa, le sacamos uno por vez —mezclando esa información entre los "
    "jugadores, para que no la pueda usar— y medimos cuánto empeora. Cada barra es la parte de lo que había aprendido "
    "(lo que saca por encima del modelo que dice siempre «no») que se pierde sin ese factor: cuanto más larga, más "
    f"depende de él. Sin el rendimiento pierde el {pct(b['rendimiento'])}, y sin el club de origen el "
    f"{pct(b['club de origen'])}; el puesto y la edad suman poco, y la temporada nada. Es el mismo orden que mostraban "
    "los datos solos: el modelo no encontró un factor escondido, confirmó los que ya se veían y midió cuánto pesa cada "
    "uno. Los porcentajes no suman 100 % porque los factores se superponen en parte (los jugadores de clubes fuertes "
    "también suelen rendir más).")
orden_b = list(bloques.sort_values("pierde", ascending=False)["factor_corto"])
base_b = alt.Chart(bloques).encode(y=alt.Y("factor_corto:N", sort=orden_b, title=None, axis=alt.Axis(labelLimit=220)))
barras_b = base_b.mark_bar(color=AZUL).encode(
    x=alt.X("pierde:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 0.7]),
            title="parte de lo que aprendió el modelo que se pierde sin ese factor"),
    tooltip=[alt.Tooltip("factor:N"), alt.Tooltip("pierde:Q", format=".0%", title="se pierde")])
textos_b = base_b.mark_text(align="left", dx=5, fontSize=13, color="#1d2329").encode(
    x=alt.X("pierde:Q", scale=alt.Scale(domain=[0, 0.7])), text="rotulo:N")
grafico((barras_b + textos_b).properties(height=210), width="stretch")

comp = pd.DataFrame(resumen["comparacion"])
piso = resumen["piso"]["media"]
rf = comp.set_index("familia").loc["random forest"]
rl = comp.set_index("familia").loc["regresión logística"]
gb = comp.set_index("familia").loc["gradient boosting"]
st.write(
    "**Por qué un random forest.** Probamos cuatro familias de modelos, cada una con su mejor combinación de "
    "hiperparámetros. El punto es el f1 macro medio en validación cruzada (5 pedazos del entrenamiento) y la raya va de "
    "un desvío abajo a un desvío arriba: muestra cuánto se mueve el número de un pedazo a otro. La línea punteada es el "
    f"piso ({num(piso)}). El random forest le gana a la regresión logística por {num(rf.f1 - rl.f1)}, más que el desvío "
    "de los dos; el gradient boosting empata con el bosque, pero su raya es más larga: es menos estable. El eje empieza "
    "en 0,46 para que se vean las diferencias.")
puntos = alt.Chart(comp).mark_point(filled=True, size=90, color=AZUL).encode(
    x=alt.X("f1:Q", scale=alt.Scale(domain=[0.46, 0.72]), title="f1 macro (media ± desvío)"),
    y=alt.Y("familia:N", sort=list(comp.sort_values("f1", ascending=False)["familia"]), title=None,
            axis=alt.Axis(labelOverlap=False, labelLimit=200)))
errores = alt.Chart(comp).mark_errorbar(color=AZUL).encode(
    x=alt.X("min:Q", scale=alt.Scale(domain=[0.46, 0.72]), title="f1 macro (media ± desvío)"), x2="max:Q",
    y=alt.Y("familia:N", sort=list(comp.sort_values("f1", ascending=False)["familia"]))
).transform_calculate(min="datum.f1 - datum.desvio", max="datum.f1 + datum.desvio")
linea_piso = alt.Chart(pd.DataFrame({"piso": [piso]})).mark_rule(strokeDash=[4, 3], color="#777").encode(x="piso:Q")
grafico((errores + puntos + linea_piso).properties(height=260, title="Eje recortado de 0,46 a 0,72; "
                "la línea punteada es el piso"), width="stretch")

st.write(
    "**Dónde se equivoca: los que se le escapan.** Cada barra es un club top 20 de destino y cuenta los fichajes del "
    "test que llegaron a él: en azul, los que el modelo encontró (verdaderos positivos); en celeste, los que se le "
    "escaparon (falsos negativos). Encuentra a los que van a los clubes que compran jugadores consagrados, y pierde "
    "casi todos los del Porto, la Roma o el Benfica: están en el top 20 por sus resultados en copas europeas, pero "
    "fichan como clubes medianos, jugadores que se parecen a cualquier otro fichaje de su liga.")
clubes_test = pd.DataFrame(resumen["clubes_test"]).head(12)
largo_c = clubes_test.melt(id_vars="club", value_vars=["encontrados", "perdidos"], var_name="qué pasó",
                           value_name="fichajes")
largo_c["qué pasó"] = largo_c["qué pasó"].replace({"encontrados": "lo encontró (verdadero positivo)",
                                                   "perdidos": "se le escapó (falso negativo)"})
grafico(alt.Chart(largo_c).mark_bar().encode(
    y=alt.Y("club:N", sort=list(clubes_test["club"]), title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)),
    x=alt.X("fichajes:Q", title="fichajes del test que llegaron a ese club top 20", stack="zero"),
    color=alt.Color("qué pasó:N", scale=alt.Scale(domain=["lo encontró (verdadero positivo)", "se le escapó (falso negativo)"],
                                                 range=[AZUL, CELESTE]), legend=alt.Legend(title=None, orient="top", labelLimit=320)),
    order=alt.Order("qué pasó:N"), tooltip=["club", "qué pasó", "fichajes"]).properties(height=330), width="stretch")

st.write(
    "**Dónde se equivoca: los que señala de más.** Son los jugadores que el modelo marcó como «top 20» y no llegaron "
    "(falsos positivos). Las barras naranjas dicen a qué puesto del ranking UEFA fue en realidad su club; las marcas "
    "negras, a dónde fue el resto de los que no llegaron, como referencia. Cada grupo suma 100 %. Los señalados se "
    f"amontonan justo debajo del corte: el {pct(fp_cerca)} fue a un club del puesto 21 al 100 (McTominay al Napoli, De "
    f"Ketelaere al Milan), mientras que del resto, el {pct(resumen['vn_destino']['puesto 101 o más'])} terminó del "
    "puesto 101 para abajo. Tienen perfil de top 20: los compró un club grande, pero no uno de los 20 primeros.")
destino = pd.DataFrame({"destino real": list(resumen["fp_destino"]),
                        "falsos positivos": list(resumen["fp_destino"].values()),
                        "negativos": [resumen["vn_destino"][k] for k in resumen["fp_destino"]]})
base_d = alt.Chart(destino).encode(
    x=alt.X("destino real:N", sort=list(resumen["fp_destino"]), title="a dónde fueron en realidad",
            axis=alt.Axis(labelAngle=0)))
barras_d = base_d.mark_bar(color=NARANJA, size=60).encode(
    y=alt.Y("falsos positivos:Q", axis=alt.Axis(format="%"), title="% del grupo", scale=alt.Scale(domain=[0, 0.6])),
    tooltip=["destino real", alt.Tooltip("falsos positivos:Q", format=".0%", title="los que el modelo señaló"),
             alt.Tooltip("negativos:Q", format=".0%", title="el resto de los que no llegaron")])
textos_d = base_d.mark_text(dy=-8, color=NARANJA, fontWeight="bold").encode(
    y=alt.Y("falsos positivos:Q", scale=alt.Scale(domain=[0, 0.6])), text=alt.Text("falsos positivos:Q", format=".0%"))
marcas_d = base_d.mark_tick(color="#1d2329", thickness=3, size=70).encode(
    y=alt.Y("negativos:Q", scale=alt.Scale(domain=[0, 0.6])))
grafico((barras_d + textos_d + marcas_d).properties(height=240), width="stretch")
st.caption("Barras naranjas: los que el modelo señaló y no llegaron a un top 20. Marca negra: el resto de los que no "
           "llegaron, como referencia de a dónde va un fichaje cualquiera.")


# ------------------------------------------------------------------ los falsos positivos, uno por uno
FOTOS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "imagenes", "jugadores")
COMMONS = "https://commons.wikimedia.org/wiki/File:"
CREDITOS = {  # archivo: (autor, licencia, archivo en Wikimedia Commons)
    "isak": ("Mikael Hervestad", "CC BY-SA 4.0", "Alexander_Isak_-_Sweden_-_Greece21_(cropped).jpg"),
    "mctominay": ("Bryan Berlin", "CC BY-SA 4.0", "Scott_McTominay_Scotland_v_Bolivia_6_June_2026-41.jpg"),
    "modric": ("Bryan Berlin", "CC BY-SA 4.0", "Luka_Modric_Croatia_v_Portugal_2_July_2026-055.jpg"),
    "de_ketelaere": ("Bryan Berlin", "CC BY-SA 4.0", "Charles_De_Ketelaere_USMNT_v_Belgium_Mar_28_2026-76_(cropped).jpg"),
    "osimhen": ("Fédération Guinéenne de Football", "dominio público", "Victor-osimhen-nigeria-2024-3-4.jpg"),
    "greenwood": ("Zafer", "CC BY-SA 4.0", "Mason_Greenwood_11_Fenerbahçe_20260805_(4)_(cropped)_(cropped).JPG"),
    "paqueta": ("Bryan Berlin", "CC BY-SA 4.0", "Lucas_Paqueta_Brazil_V_Morocco_13_June_2026-134_(cropped).jpg"),
}


def foto(columna, archivo):
    autor, licencia, original = CREDITOS[archivo]
    columna.image(os.path.join(FOTOS, archivo + ".jpg"), width=170)
    enlace = f", [Wikimedia Commons]({COMMONS}{original.replace(' ', '_')})" if original else ""
    columna.caption(f"Foto: {autor}, {licencia}{enlace}")


PLURAL = {"Arquero": "arqueros", "Defensor central": "defensores centrales", "Lateral": "laterales",
          "Mediocampo defensivo": "mediocampistas defensivos", "Mediocampo ofensivo": "mediocampistas ofensivos",
          "Delantero centro": "delanteros centro", "Delantero extremo": "extremos"}


@functools.lru_cache(maxsize=32)
def foto_base64(archivo):
    with open(os.path.join(FOTOS, archivo + ".jpg"), "rb") as f:
        return base64.b64encode(f.read()).decode()


def millones(x):
    return f"{x / 1e6:,.0f} M€".replace(",", ".")


def fichaje(nombre, destino):
    """Un fichaje por nombre y club de destino (si está repetido, el de más probabilidad)."""
    f = fichajes[fichajes["nombre"].eq(nombre) & fichajes["club_destino"].eq(destino)]
    return None if f.empty else f.sort_values("proba", ascending=False).iloc[0]


resultado = fichajes["resultado"].str.split(":").str[0]
fps = fichajes[resultado.eq("falso positivo")].copy()
# los cuatro tipos, en este orden: un fichaje va al primero que le corresponde
fps["tipo"] = np.select([fps["club_destino_pais"].eq("England"), fps["edad_al_fichaje"] >= 28,
                         fps["edad_al_fichaje"] <= 21], ["premier", "veteranos", "jovenes"], "casi")
grupos_fp = {"verdaderos positivos": fichajes[resultado.eq("verdadero positivo")],
             "falsos positivos": fps, "verdaderos negativos": fichajes[resultado.eq("verdadero negativo")]}
costos = pd.DataFrame({"grupo": ["llegaron y el modelo los señaló (verdaderos positivos)",
                                 "el modelo los señaló y no llegaron (falsos positivos)",
                                 "no llegaron y el modelo no los señaló (verdaderos negativos)"],
                       "costo": [g["coste_fichaje_eur"].median() for g in grupos_fp.values()],
                       "color": [AZUL, NARANJA, GRIS]})
rend_fp = {k: g["score_posicion"].median() for k, g in grupos_fp.items()}
min_fp = {k: pd.to_numeric(g["stat_minutes"], errors="coerce").median() for k, g in grupos_fp.items()}

llegaron_todos = fichajes[fichajes["es_destino_top_20"].astype(bool)]
st.markdown("#### Los falsos positivos: el modelo dijo «llega» y no llegaron")
st.write(
    f"Sobre los {miles(len(fichajes))} fichajes, cada uno con la predicción de un modelo que no lo vio, hay "
    f"**{miles(len(fps))} falsos positivos**: el modelo dijo «llega» y no llegaron. No son jugadores malos que el "
    f"modelo sobrevaloró. Tuvieron temporadas de nivel top —{num(rend_fp['falsos positivos'], 2)} desvíos sobre el "
    f"promedio de su puesto y {miles(min_fp['falsos positivos'])} minutos de mediana, más que la mitad de todos los que "
    f"sí llegaron a un top 20 ({num(llegaron_todos['score_posicion'].median(), 2)} y "
    f"{miles(pd.to_numeric(llegaron_todos['stat_minutes'], errors='coerce').median())})— y los clubes que los "
    "compraron también los vieron así: el gráfico muestra cuánto se pagó, en mediana, por cada grupo. Por un falso "
    "positivo se pagó varias veces más que por un fichaje común. El precio no entra al modelo (se conoce recién en el "
    "fichaje), pero sirve para leer el error después. Como jugaron casi toda la temporada, tampoco son lesionados.")
base_cost = alt.Chart(costos).encode(y=alt.Y("grupo:N", sort=list(costos["grupo"]), title=None,
                                             axis=alt.Axis(labelLimit=420)))
grafico((base_cost.mark_bar().encode(
    x=alt.X("costo:Q", title="costo del fichaje, mediana (millones de euros)",
            axis=alt.Axis(labelExpr="datum.value / 1e6")),
    color=alt.Color("color:N", scale=None), tooltip=[alt.Tooltip("costo:Q", format=",.0f", title="euros")])
    + base_cost.mark_text(align="left", dx=5, color="#1d2329").encode(
        x="costo:Q", text=alt.Text("etiqueta:N"))).transform_calculate(
            etiqueta="format(datum.costo / 1e6, '.0f') + ' M€'").properties(height=150), width="stretch")
st.markdown("##### ¿Por qué no llegaron? Cuatro tipos")
st.write(
    "Mirando a dónde fueron y quiénes eran, los falsos positivos se separan en **cuatro tipos**; cada fichaje va al "
    "primero que le corresponde, en este orden. Para cada tipo: qué lo explica, sus números, un ejemplo y una tabla "
    "con otros casos, con lo mismo que mira el modelo para decidir —rendimiento para su puesto, club y liga de "
    "origen, edad— y, abajo, dos filas para comparar: la mediana de todos los que llegaron a un top 20 y la de todos "
    "los fichajes.")

OPERACION = {"compra": "compra", "libre": "libre", "cesion": "préstamo", "cesion_con_cargo": "préstamo con cargo"}


def fila_referencia(nombre, grupo):
    """La mediana de un grupo, para comparar contra los casos de la tabla."""
    return {"jugador": nombre, "edad": miles(grupo["edad_al_fichaje"].median()),
            "rendimiento vs. su puesto": num(grupo["score_posicion"].median(), 2),
            "minutos": miles(pd.to_numeric(grupo["stat_minutes"], errors="coerce").median()),
            "liga top 5": f"{pct(grupo['club_origen_liga_es_top5'].astype(float).mean())} sí",
            "coef. UEFA del origen": num(grupo["club_origen_coeficiente_uefa"].median(), 1),
            "probabilidad": num(grupo["proba"].median(), 2)}


def tabla_casos(casos, g, referencia=None):
    """Los casos de un tipo, con lo que mira el modelo, y dos filas de referencia abajo: un grupo para comparar
    (por defecto, todos los que llegaron a un top 20) y todos los fichajes."""
    referencia = referencia or ("→ mediana de todos los que llegaron", llegaron_todos)
    filas = []
    for n_, d_ in casos:
        f_ = fichaje(n_, d_)
        if f_ is None or f_.name not in g.index:
            continue
        coef = f_.club_origen_coeficiente_uefa
        filas.append({"jugador": n_, "temporada": f_.temporada_fichaje, "puesto": f_.grupo_posicion,
                      "edad": miles(f_.edad_al_fichaje), "rendimiento vs. su puesto": num(f_.score_posicion, 2),
                      "minutos": miles(f_.stat_minutes) if pd.notna(f_.stat_minutes) else "—",
                      "club de origen": f_.club_origen, "liga top 5": "sí" if f_.club_origen_liga_es_top5 else "no",
                      "coef. UEFA del origen": num(coef, 1) if pd.notna(coef) else "sin ranking",
                      "a (club real)": f"{f_.club_destino} (puesto {f_.club_destino_ranking_uefa})",
                      "operación": OPERACION.get(f_.tipo_operacion, f_.tipo_operacion),
                      "probabilidad": num(f_.proba, 2)})
    if not filas:
        return None
    filas += [fila_referencia(*referencia),
              fila_referencia("→ mediana de todos los fichajes", fichajes)]
    orden = ["jugador", "a (club real)", "probabilidad", "rendimiento vs. su puesto", "minutos", "edad",
             "club de origen", "liga top 5", "coef. UEFA del origen", "operación", "puesto", "temporada"]
    return pd.DataFrame(filas).reindex(columns=orden).fillna("")


TIPOS_FP = [
    ("premier", "1 · La plata de la Premier",
     "Fueron a clubes ingleses que no están en el top 20 de UEFA porque no juegan (o juegan poco) copas europeas, "
     "pero que por los derechos de televisión de la Premier League pagan como un grande. Para el modelo, el destino "
     "tenía la billetera de un top 20; para el ranking UEFA, no.",
     ("Alexander Isak", "Newcastle United", "isak",
      "Rindió {rend} desvíos por encima del promedio de los {plural} y jugó {minutos} minutos en la Real Sociedad: el "
      "modelo le dio **{proba}**. Lo compró el Newcastle (puesto {puesto} de UEFA), que paga como un grande pero casi "
      "no juega en Europa. Tres temporadas después, en 2025, el **Liverpool** (puesto 4) pagó por él un récord del "
      "fútbol inglés, y ahí el modelo sí dijo «llega» ({proba_despues}): leyó bien al jugador, sólo que antes de "
      "tiempo.", ("Alexander Isak", "Liverpool FC")),
     [("Sandro Tonali", "Newcastle United"), ("Moussa Diaby", "Aston Villa"), ("Pau Torres", "Aston Villa"),
      ("Nikola Milenković", "Nottingham Forest"), ("Amadou Onana", "Aston Villa"),
      ("Matheus Nunes", "Wolverhampton Wanderers"), ("Yoane Wissa", "Newcastle United")]),
    ("casi", "2 · Casi top 20",
     "Fueron a clubes grandes de Europa que quedaron justo debajo del corte: el Milan, el Napoli, el Marsella o la "
     "Lazio. El puesto 20 es una línea que el perfil del jugador no ve: para el modelo, un jugador de un club del "
     "puesto 23 se parece mucho a uno del puesto 18.",
     ("Scott McTominay", "SSC Napoli", "mctominay",
      "Pasó del Manchester United al Napoli, puesto {puesto} de UEFA: a tres lugares del corte. Rindió {rend} desvíos "
      "sobre su puesto, jugó {minutos} minutos, y el modelo le dio **{proba}**. En su primera temporada en Italia fue "
      "elegido el mejor jugador de la Serie A y el Napoli salió campeón: el modelo no se equivocó sobre el jugador, "
      "sino sobre la línea.", None),
     [("Mattéo Guendouzi", "Olympique Marseille"), ("Romelu Lukaku", "SSC Napoli"),
      ("Christopher Nkunku", "AC Milan"), ("Ardon Jashari", "AC Milan"), ("Malik Tillman", "PSV Eindhoven"),
      ("Sergiño Dest", "PSV Eindhoven")]),
    ("veteranos", "3 · Veteranos: el último gran contrato",
     "Tienen 28 años o más y rinden como un top —son el grupo con mejor rendimiento—, pero ningún top 20 apuesta "
     "por un jugador de 30 años. Muchos se van libres al terminar su contrato, a un club que les da un último "
     "contrato grande.",
     ("Luka Modrić", "AC Milan", "modric",
      "Con {edad} años rindió {rend} desvíos por encima del promedio de los {plural} y jugó {minutos} minutos: el "
      "modelo le dio **{proba}**. Terminó su contrato con el Real Madrid después de trece temporadas y se fue libre "
      "al Milan (puesto {puesto}). El modelo lee la temporada, no la edad de retiro.", None),
     [("Leroy Sané", "Galatasaray"), ("Sergio Ramos", "Sevilla FC"), ("Kyle Walker", "AC Milan"),
      ("Karl Toko Ekambi", "Stade Rennais FC"), ("Dusan Tadic", "Fenerbahce"), ("Marco Asensio", "Fenerbahce")]),
    ("jovenes", "4 · Jóvenes promesas",
     "Tienen 21 años o menos. Acá el modelo no los señala por cómo jugaron —en mediana rindieron justo el promedio de "
     "su puesto: 0 desvíos quiere decir que la mitad estuvo por encima y la mitad por debajo— sino por quiénes son: "
     "muy jóvenes y, muchos, formados o comprados por clubes gigantes como el PSG, el Bayern, el Real Madrid o el "
     "Manchester City. El coeficiente UEFA mediano de su club de origen es "
     f"{num(fps.loc[fps['tipo'].eq('jovenes'), 'club_origen_coeficiente_uefa'].median(), 0)}, contra "
     f"{num(fichajes['club_origen_coeficiente_uefa'].median(), 0)} de todos los fichajes. De los más jóvenes llegan "
     "3 de cada 10, pero el modelo no puede saber cuáles. Muchos van a préstamo o a un club intermedio para crecer.",
     ("Charles De Ketelaere", "AC Milan", "de_ketelaere",
      "Con {edad} años, después de una gran temporada en el Brujas ({rend} desvíos, {minutos} minutos), lo compró el "
      "Milan (puesto {puesto}): el modelo le dio **{proba}**. No se adaptó, y al año siguiente pasó al **Atalanta** "
      "(puesto 18). Ahí sí rindió, el Atalanta lo compró, y con esos números el modelo dijo «llega» ({proba_despues}): "
      "llegó a un top 20, un año más tarde.", ("Charles De Ketelaere", "Atalanta BC")),
     [("George Ilenikhena", "AS Monaco"), ("Arnaud Kalimuendo", "Stade Rennais FC"),
      ("Joshua Zirkzee", "Bologna FC 1909"), ("Nico Paz", "Como 1907"), ("Claudio Echeverri", "Girona FC")]),
]

for clave, titulo, explicacion, (nombre_ej, destino_ej, archivo_ej, texto_ej, despues), otros in TIPOS_FP:
    g = fps[fps["tipo"].eq(clave)]
    st.markdown(f'<div class="tipo-error">{titulo}</div>', unsafe_allow_html=True)
    st.write(explicacion)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Falsos positivos (y % del total)", f"{miles(len(g))} ({pct(len(g) / len(fps))})")
    rend_g = g["score_posicion"].median()
    # muy cerca de 0 se muestra como «≈ 0»: con dos decimales daría un 0,00 que parece exacto y no lo es
    k2.metric("Rendimiento (mediana)", f"≈ 0 desvíos" if abs(rend_g) < 0.05 else f"{num(rend_g, 2)} desvíos",
              help=f"Mediana exacta: {num(rend_g, 3)} desvíos respecto del promedio de su puesto. 0 es justo el "
                   "promedio: la mitad rindió por encima y la mitad por debajo.")
    if clave == "premier":
        k3.metric("Costo (mediana)", millones(g["coste_fichaje_eur"].median()))
        k4.metric("Puesto UEFA del destino (mediana)", miles(g["club_destino_ranking_uefa"].median()))
    elif clave == "casi":
        k3.metric("Destino entre los puestos 21 y 50", pct(g["club_destino_ranking_uefa"].le(50).mean()))
        k4.metric("Costo (mediana)", millones(g["coste_fichaje_eur"].median()))
    elif clave == "veteranos":
        k3.metric("Edad (mediana)", f"{miles(g['edad_al_fichaje'].median())} años")
        k4.metric("Llegaron libres o a préstamo", pct(g["tipo_operacion"].isin(["libre", "cesion"]).mean()))
    else:
        k3.metric("Edad (mediana)", f"{miles(g['edad_al_fichaje'].median())} años")
        k4.metric("Coef. UEFA del club de origen (mediana)", num(g["club_origen_coeficiente_uefa"].median(), 0))
    ej = fichaje(nombre_ej, destino_ej)
    if ej is not None:
        foto_c, texto_c = st.columns([1, 4])
        foto(foto_c, archivo_ej)
        segundo = fichaje(*despues) if despues else None
        texto_c.markdown(f"**El ejemplo: {nombre_ej}** ({ej.club_origen} → {ej.club_destino}, {ej.temporada_fichaje})\n\n"
                         + texto_ej.format(rend=num(ej.score_posicion, 2), minutos=miles(ej.stat_minutes),
                                           proba=num(ej.proba, 2), puesto=ej.club_destino_ranking_uefa,
                                           edad=miles(ej.edad_al_fichaje), plural=PLURAL[ej.grupo_posicion],
                                           proba_despues=num(segundo.proba, 2) if segundo is not None else "—"))
    casos_tabla = tabla_casos(otros, g)
    if casos_tabla is not None:
        st.markdown("**Otros casos de este tipo**")
        st.dataframe(casos_tabla, hide_index=True, width="stretch")

st.markdown("##### Casos especiales: lo que no está en los datos")
st.write(
    "Algunos errores tienen una causa que ninguna estadística muestra: un conflicto con el club, una investigación, "
    "una causa judicial. No son la regla, pero muestran el límite de un modelo que sólo mira la cancha.")
ESPECIALES = [
    ("Victor Osimhen", "Galatasaray", "osimhen",
     "Rindió {rend} desvíos por encima del promedio de los {plural} y el modelo le dio **{proba}**. "
     "Pero su relación con el Napoli se había roto: en 2023 la cuenta del club publicó videos burlándose de él, y en "
     "2024 lo dejaron fuera de la lista de la Serie A y le sacaron la 9. Se fue a préstamo al Galatasaray (puesto "
     "{puesto}) y en 2025 el Galatasaray lo compró por unos 75 M€."),
    ("Lucas Paquetá", "West Ham United", "paqueta",
     "Rindió {rend} desvíos por encima del promedio de los {plural} en el Lyon y el modelo le dio **{proba}**. Fue al "
     "West Ham (puesto {puesto}), un caso de la plata de la Premier; lo especial vino un año después. En agosto de 2023 "
     "el **Manchester City** (puesto 3) estaba por comprarlo y el pase se cayó cuando la federación inglesa abrió una "
     "investigación por apuestas sobre él. En julio de 2025 lo absolvieron de esas acusaciones. Un top 20 lo quiso: "
     "lo frenó algo que no está en los datos."),
    ("Mason Greenwood", "Olympique Marseille", "greenwood",
     "Con 22 años rindió {rend} desvíos sobre su puesto a préstamo en el Getafe, y el modelo le dio **{proba}**. Por la "
     "causa judicial en su contra —archivada a principios de 2023— el Manchester United decidió no volver a contar con "
     "él y en 2024 lo vendió al Marsella (puesto {puesto})."),
]
columnas_esp = st.columns(3, gap="large")
for col, (nombre_e, destino_e, archivo_e, texto_e) in zip(columnas_esp, ESPECIALES):
    e = fichaje(nombre_e, destino_e)
    if e is None:
        continue
    foto(col, archivo_e)
    col.markdown(f"**{nombre_e}** ({e.club_origen} → {e.club_destino}, {e.temporada_fichaje})\n\n"
                 + texto_e.format(rend=num(e.score_posicion, 2), proba=num(e.proba, 2), plural=PLURAL[e.grupo_posicion],
                                  puesto=e.club_destino_ranking_uefa))


# ------------------------------------------------------------------ los falsos negativos, uno por uno
CREDITOS.update({
    "lucas_hernandez": ("Bryan Berlin", "CC BY-SA 4.0", "Lucas_Hernandez_France_v_Senegal_16_June_2026-281.jpg"),
    "enzo_fernandez": ("Bryan Berlin", "CC BY-SA 4.0", "Enzo_Fernandez_Argentina_v_Spain_19_July_2026-050_(cropped).jpg"),
    "tel": ("Zack Nani", "CC BY 3.0", "Mathys_Tel_en_2026.png"),
    "barcola": ("Bryan Berlin", "CC BY-SA 4.0", "Bradley_Barcola_France_v_Spain_7.24.26-112_(cropped).jpg"),
    "olise": ("Bryan Berlin", "CC BY-SA 4.0", "Michael_Olise_France_v_Senegal_16_June_2026-307_(cropped).jpg"),
    "mudryk": ("Darren Walsh / Getty Images", "la misma foto de la portada", None),
    "wesley_fofana": ("Ardfern", "CC BY-SA 4.0", "Wesley_Fofana_2022.jpg"),
    "lavia": ("Timmy96", "CC0", "Roméo_Lavia_20042025_(1)_cropped.jpg"),
    "aubameyang": ("Chensiyuan", "CC BY-SA 4.0", "1_Pierre-Emerick_Aubameyang_(cropped).jpg"),
    "sancho": ("Ardfern", "CC BY-SA 4.0", "Manchester_United_v_Liverpool,_22_August_2022_(33)_(cropped).jpg"),
    "nicolas_jackson": ("Bryan Berlin", "CC BY-SA 4.0", "Nicolas_Jackson_France_v_Senegal_16_June_2026-369_(cropped).jpg"),
})

fns = fichajes[resultado.eq("falso negativo")].copy()
fns["minutos"] = pd.to_numeric(fns["stat_minutes"], errors="coerce")
TOP20 = set(fichajes.loc[fichajes["es_destino_top_20"].astype(bool), "club_destino"])
# los tipos, en este orden; el Chelsea va primero porque tiene su propio bloque al final
fns["tipo"] = np.select(
    [fns["club_destino"].eq("Chelsea FC"), fns["club_origen"].isin(TOP20),
     fns["club_destino"].isin(["FC Porto", "SL Benfica"]), fns["minutos"].lt(900), fns["edad_al_fichaje"] <= 21,
     fns["nivel UEFA del club de origen"].ne("alto")],
    ["chelsea", "nombre", "poder", "sin_minutos", "jovenes", "sin_peso"], "otros")
minutos_g = {"llegaron y el modelo los señaló (verdaderos positivos)": grupos_fp["verdaderos positivos"],
             "llegaron y el modelo no los vio (falsos negativos)": fns,
             "no llegaron y el modelo no los señaló (verdaderos negativos)": grupos_fp["verdaderos negativos"]}
tabla_min = pd.DataFrame({"grupo": list(minutos_g),
                          "minutos": [pd.to_numeric(g["stat_minutes"], errors="coerce").median() for g in minutos_g.values()],
                          "color": [AZUL, CELESTE, GRIS]})
rend_fn, vp_ = fns["score_posicion"].median(), grupos_fp["verdaderos positivos"]

st.markdown("#### Los falsos negativos: llegaron y el modelo no los vio")
st.write(
    f"Hay **{miles(len(fns))} falsos negativos**: jugadores que llegaron a un top 20 y el modelo dijo «no llega». Al revés "
    "que los falsos positivos, estos **no tenían perfil de top 20** en lo que mira el modelo: rindieron "
    f"{num(rend_fn, 2)} desvíos sobre el promedio de su puesto (los que el modelo encontró, "
    f"{num(vp_['score_posicion'].median(), 2)}), el {pct(fns['club_origen_liga_es_top5'].astype(float).mean())} venía "
    f"de una liga top 5 (contra {pct(vp_['club_origen_liga_es_top5'].astype(float).mean())}) y jugaron bastante menos, "
    "como muestra el gráfico: los minutos de la temporada anterior, en mediana, de cada grupo. El modelo leyó bien la "
    "temporada; lo que no puede ver es por qué un club grande los compró igual.")
base_min = alt.Chart(tabla_min).encode(y=alt.Y("grupo:N", sort=list(tabla_min["grupo"]), title=None,
                                               axis=alt.Axis(labelLimit=420)))
grafico((base_min.mark_bar().encode(
    x=alt.X("minutos:Q", title="minutos jugados la temporada anterior, mediana"), color=alt.Color("color:N", scale=None),
    tooltip=[alt.Tooltip("minutos:Q", format=",.0f")])
    + base_min.mark_text(align="left", dx=5, color="#1d2329").encode(x="minutos:Q", text=alt.Text("minutos:Q", format=",.0f")))
    .properties(height=150), width="stretch")

st.markdown("##### ¿Por qué se le escaparon? Cinco tipos")
st.write(
    "Mirando de dónde venían y quién los compró, los falsos negativos se separan en **cinco tipos**; cada fichaje va al "
    "primero que le corresponde, en este orden. Los fichajes del Chelsea quedan aparte, en su propio bloque al final. "
    "Como antes: qué lo explica, sus números, un ejemplo y una tabla con otros casos; acá las dos filas para comparar "
    "son la mediana de los que el modelo sí encontró y la de todos los fichajes.")


def bloque_fn(clave, titulo, explicacion, metricas, ejemplo, otros):
    g = fns[fns["tipo"].eq(clave)]
    st.markdown(f'<div class="tipo-error-fn">{titulo}</div>', unsafe_allow_html=True)
    st.write(explicacion)
    cols = st.columns(4)
    cols[0].metric("Falsos negativos (y % del total)", f"{miles(len(g))} ({pct(len(g) / len(fns))})")
    for col, (etiqueta, valor) in zip(cols[1:], metricas(g)):
        col.metric(etiqueta, valor)
    nombre_ej, destino_ej, archivo_ej, texto_ej = ejemplo
    ej = fichaje(nombre_ej, destino_ej)
    if ej is not None:
        foto_c, texto_c = st.columns([1, 4])
        foto(foto_c, archivo_ej)
        coef = ej.club_origen_coeficiente_uefa
        texto_c.markdown(f"**El ejemplo: {nombre_ej}** ({ej.club_origen} → {ej.club_destino}, {ej.temporada_fichaje})\n\n"
                         + texto_ej.format(rend=num(ej.score_posicion, 2), minutos=miles(ej.stat_minutes),
                                           proba=num(ej.proba, 2), puesto=ej.club_destino_ranking_uefa,
                                           edad=miles(ej.edad_al_fichaje), plural=PLURAL[ej.grupo_posicion],
                                           coef=num(coef, 0) if pd.notna(coef) else "sin ranking"))
    casos_tabla = tabla_casos(otros, g, ("→ mediana de los que el modelo encontró", vp_))
    if casos_tabla is not None:
        st.markdown("**Otros casos de este tipo**")
        st.dataframe(casos_tabla, hide_index=True, width="stretch")


def mediana(g, col):
    return pd.to_numeric(g[col], errors="coerce").median()


bloque_fn(
    "nombre", "1 · Un nombre, no una temporada",
    "Venían de **otro club top 20**: ya eran de la élite. Llegaron después de una temporada floja o con pocos minutos, y "
    "el club que los compró apostó por lo que habían demostrado antes, muchas veces barato o a préstamo. El modelo sólo "
    "ve la última temporada, así que no ve el nombre.",
    lambda g: [("Rendimiento (mediana)", f"{num(mediana(g, 'score_posicion'), 2)} desvíos"),
               ("Costo (mediana)", millones(mediana(g, "coste_fichaje_eur"))),
               ("Llegaron a préstamo", pct(g["tipo_operacion"].str.startswith("cesion").mean()))],
    ("Lucas Hernández", "Paris Saint-Germain", "lucas_hernandez",
     "Campeón del mundo con Francia en 2018. En el primer partido del Mundial 2022 se rompió los ligamentos cruzados, y "
     "en la temporada anterior al fichaje jugó {minutos} minutos ({rend} desvíos): el modelo le dio **{proba}**. El PSG "
     "(puesto {puesto}) pagó igual unos 45 M€ por él. Lo compró por su nombre, no por su temporada."),
    [("Gabriel Jesus", "FC Barcelona"), ("Robin Gosens", "Inter Milan"), ("Leandro Paredes", "Juventus FC"),
     ("Renato Sanches", "AS Roma"), ("Julian Draxler", "SL Benfica"), ("Kepa Arrizabalaga", "Arsenal FC"),
     ("Clément Lenglet", "Atlético de Madrid"), ("Cristian Romero", "Tottenham Hotspur")])

bloque_fn(
    "poder", "2 · Clubes grandes con menor poder adquisitivo",
    "El Porto y el Benfica están en el top 20 de UEFA por sus resultados en copas europeas, pero no pueden pagar lo que "
    "pagan los ingleses o los españoles. Compran barato, muchas veces en Sudamérica o en ligas más chicas, jugadores que "
    "todavía no tienen perfil de top 20, y los venden caros cuando explotan. Para el modelo, son fichajes comunes.",
    lambda g: [("Costo (mediana)", millones(mediana(g, "coste_fichaje_eur"))),
               ("Vienen de liga top 5", pct(g["club_origen_liga_es_top5"].astype(float).mean())),
               ("Rendimiento (mediana)", f"{num(mediana(g, 'score_posicion'), 2)} desvíos")],
    ("Enzo Fernández", "SL Benfica", "enzo_fernandez",
     "El Benfica lo compró a River Plate en 2022. Rindió {rend} desvíos sobre el promedio de los {plural} y jugó "
     "{minutos} minutos, en una liga fuera del top 5: el modelo le dio **{proba}**. Seis meses después fue elegido el "
     "mejor jugador joven del Mundial 2022, y en enero de 2023 el Chelsea pagó 121 M€ por él, récord del fútbol inglés "
     "en ese momento."),
    [("Samu Aghehowa", "FC Porto"), ("Richard Ríos", "SL Benfica"), ("Marcos Leonardo", "SL Benfica"),
     ("Arthur Cabral", "SL Benfica"), ("David Carmo", "FC Porto"), ("Victor Froholdt", "FC Porto"),
     ("Gabri Veiga", "FC Porto")])

bloque_fn(
    "sin_minutos", "3 · Una temporada casi sin jugar",
    "Jugaron menos de 900 minutos la temporada anterior —diez partidos completos—, por una lesión o porque eran "
    "suplentes o muy chicos. Con tan pocos minutos, sus estadísticas casi no dicen nada y el modelo no tiene en qué "
    "apoyarse. El club que los compró se fijó en otra cosa: el potencial, o lo que habían hecho antes.",
    lambda g: [("Minutos (mediana)", miles(mediana(g, "stat_minutes"))),
               ("Edad (mediana)", f"{miles(mediana(g, 'edad_al_fichaje'))} años"),
               ("Costo (mediana)", millones(mediana(g, "coste_fichaje_eur")))],
    ("Mathys Tel", "Bayern Munich", "tel",
     "Con {edad} años había jugado {minutos} minutos en el Rennes: el modelo le dio **{proba}**. El Bayern (puesto "
     "{puesto}) pagó igual unos 20 M€ por él. Compró lo que podía llegar a ser, no lo que había jugado."),
    [("Lucas Beraldo", "Paris Saint-Germain"), ("Robinio Vaz", "AS Roma"), ("Yan Diomande", "RB Leipzig"),
     ("Honest Ahanor", "Atalanta BC"), ("Souza", "Tottenham Hotspur"), ("Abdoul Koné", "RB Leipzig")])

bloque_fn(
    "jovenes", "4 · Las apuestas jóvenes",
    "Tienen 21 años o menos y sí jugaron, pero con números todavía comunes. Los grandes los compran caros por lo que "
    "creen que van a ser. Varios terminaron siendo figuras: el modelo, que sólo mira el pasado, no los podía ver.",
    lambda g: [("Edad (mediana)", f"{miles(mediana(g, 'edad_al_fichaje'))} años"),
               ("Costo (mediana)", millones(mediana(g, "coste_fichaje_eur"))),
               ("Rendimiento (mediana)", f"{num(mediana(g, 'score_posicion'), 2)} desvíos")],
    ("Bradley Barcola", "Paris Saint-Germain", "barcola",
     "Con {edad} años rindió {rend} desvíos sobre el promedio de los {plural} y jugó {minutos} minutos en el Lyon: el "
     "modelo le dio **{proba}**. El PSG (puesto {puesto}) lo compró en 2023, se ganó el puesto, y en 2025 ganó la "
     "Champions League con el PSG."),
    [("Jérémy Doku", "Manchester City"), ("Benjamin Sesko", "RB Leipzig"), ("Hugo Ekitiké", "Paris Saint-Germain"),
     ("Abdukodir Khusanov", "Manchester City"), ("Patrick Dorgu", "Manchester United"),
     ("Wilson Odobert", "Tottenham Hotspur"), ("Maximilian Beier", "Borussia Dortmund")])

bloque_fn(
    "sin_peso", "5 · El salto desde un club que no es de los grandes de Europa",
    "Rindieron bien, pero en un club que juega poco o nada las copas europeas: coeficiente UEFA bajo, medio o fuera "
    "del ranking, como el Crystal Palace, el Leicester o el Bologna. El club de origen es el segundo factor del "
    "modelo —sin él pierde el 38 % de lo que aprendió—, así que los castiga: el salto directo de un club así a un top "
    "20 es raro, y el modelo lo da por improbable.",
    lambda g: [("Rendimiento (mediana)", f"{num(mediana(g, 'score_posicion'), 2)} desvíos"),
               (f"Coef. UEFA del origen (mediana; los que llegaron: {num(mediana(vp_, 'club_origen_coeficiente_uefa'), 0)})",
                num(mediana(g, "club_origen_coeficiente_uefa"), 0)),
               ("Club de origen fuera del ranking", pct(g["club_origen_coeficiente_uefa"].isna().mean()))],
    ("Michael Olise", "Bayern Munich", "olise",
     "En el Crystal Palace (coeficiente UEFA {coef}) rindió {rend} desvíos sobre el promedio de los {plural}: el modelo "
     "le dio **{proba}**, apenas debajo del umbral de 0,25. El Bayern (puesto {puesto}) lo compró en 2024 y se "
     "convirtió en una de sus figuras."),
    [("James Maddison", "Tottenham Hotspur"), ("Riccardo Calafiori", "Arsenal FC"), ("Federico Chiesa", "Juventus FC"),
     ("Kalvin Phillips", "Manchester City"), ("Micky van de Ven", "Tottenham Hotspur"), ("Davide Frattesi", "Inter Milan"),
     ("Nikola Krstović", "Atalanta BC")])

otros_fn = fns["tipo"].eq("otros").sum()
st.caption(f"Quedan {miles(otros_fn)} falsos negativos ({pct(otros_fn / len(fns))}) que no entran en ningún tipo: la "
           "mayoría vienen de clubes de nivel UEFA alto que no son top 20 —el Sporting, el Napoli, la Lazio, el PSV— y "
           "llegaron con temporadas comunes, como Pedro Porro (Sporting → Tottenham).")

# ------------------------------------------------------------------ el desastre de fichajes del Chelsea
chelsea = fichajes[fichajes["club_destino"].eq("Chelsea FC")]
llegadas_top = fichajes[fichajes["es_destino_top_20"].astype(bool)].groupby("club_destino").agg(
    llegaron=("nombre", "size"), edad=("edad_al_fichaje", "median"))
salidas = pd.DataFrame(resumen["salidas_top20"])
fn_chelsea = fns[fns["tipo"].eq("chelsea")]

st.markdown("##### El desastre de fichajes del Chelsea")
st.write(
    f"El Chelsea es el top 20 que **más jugadores trajo** en estas cinco temporadas ({miles(len(chelsea))}; el segundo, "
    f"{miles(llegadas_top['llegaron'].drop('Chelsea FC').max())}) y el que los trajo **más jóvenes** "
    f"({miles(chelsea['edad_al_fichaje'].median())} años de mediana). El modelo no vio a {miles(len(fn_chelsea))} de "
    f"ellos: llegaron con temporadas comunes —{num(fn_chelsea['score_posicion'].median(), 2)} desvíos sobre su puesto y "
    f"{miles(mediana(fn_chelsea, 'stat_minutes'))} minutos de mediana— y aun así costaron "
    f"{millones(mediana(fn_chelsea, 'coste_fichaje_eur'))} de mediana. Compra mucho, caro, joven y por poco: a veces, "
    "por media temporada buena. Y la mayoría no se queda: el gráfico muestra, para cada top 20, qué parte de los que "
    f"llegaron se fue del club en una temporada posterior (fichajes hasta {resumen['ultima_temporada'][:4]}, para que "
    "todos tengan un «después»).")
salidas = salidas.sort_values("se_fueron", ascending=False)
salidas["color"] = np.where(salidas["club_destino"].eq("Chelsea FC"), CELESTE, GRIS)
base_s = alt.Chart(salidas).encode(y=alt.Y("club_destino:N", sort=list(salidas["club_destino"]), title=None,
                                           axis=alt.Axis(labelLimit=220, labelOverlap=False)))
grafico((base_s.mark_bar().encode(
    x=alt.X("se_fueron:Q", axis=alt.Axis(format="%"), title="de los que llegaron, % que se fue del club después"),
    color=alt.Color("color:N", scale=None),
    tooltip=["club_destino", alt.Tooltip("llegaron:Q", title="llegaron"),
             alt.Tooltip("se_fueron:Q", format=".0%", title="se fueron después")])
    + base_s.mark_text(align="left", dx=4, fontSize=11, color="#1d2329").encode(
        x="se_fueron:Q", text=alt.Text("se_fueron:Q", format=".0%")))
    .properties(height=440), width="stretch")
st.write(
    f"Además, desde 2023 los dueños del Chelsea también son dueños del Strasbourg francés: en nuestros datos hay "
    f"{resumen['chelsea_a_strasbourg']} pases del Chelsea al Strasbourg, casi siempre jugadores jóvenes que llegaron y "
    "no tuvieron lugar. Abajo, seis casos que muestran el problema —deslizá para ver todos—, cada uno con lo que dijo el "
    "modelo y lo que pasó después.")

CARRUSEL = [
    ("Mykhaylo Mudryk", "mudryk",
     "Lo compró por media temporada brillante: tres goles en la fase de grupos de la Champions con el Shakhtar. En la "
     "temporada anterior, la que mira el modelo, había jugado {minutos} minutos. En diciembre de 2024 lo suspendieron "
     "provisoriamente por un control positivo de meldonium, y el caso recién se cerró en 2026."),
    ("Wesley Fofana", "wesley_fofana",
     "Llegó del Leicester después de fracturarse la pierna en 2021 ({minutos} minutos en la temporada anterior). En "
     "julio de 2023 se rompió los ligamentos cruzados y se perdió toda la temporada 2023/24."),
    ("Roméo Lavia", "lavia",
     "En su primera temporada jugó 32 minutos: un solo partido, contra el Crystal Palace, antes de lesionarse para el "
     "resto del año."),
    ("Pierre-Emerick Aubameyang", "aubameyang",
     "Lo pidió el entrenador, Thomas Tuchel, que fue despedido días después. Su reemplazante lo dejó fuera de la lista de "
     "la Champions; hizo tres goles y en 2023 se fue libre al Marsella."),
    ("Jadon Sancho", "sancho",
     "Llegó a préstamo desde el Manchester United, y el contrato obligaba al Chelsea a comprarlo por unos 25 millones de "
     "libras al terminar la temporada, salvo que pagara una multa de 5 millones para cancelar la compra. En 2025 el "
     "Chelsea no llegó a un acuerdo de sueldo con él, pagó la multa y Sancho volvió al United."),
    ("Nicolas Jackson", "nicolas_jackson",
     "Llegó del Villarreal por unos 37 M€ y el modelo no lo vio. En su primera temporada fue el tercer jugador de la "
     "Premier que más ocasiones claras falló (21, sólo detrás de Haaland y Darwin Núñez). En la segunda hizo un solo gol "
     "en 14 partidos de liga desde enero, y lo expulsaron contra el Newcastle en un partido clave para entrar a la "
     "Champions. En 2025 se fue a préstamo al Bayern, que sólo estaba obligado a comprarlo (por unos 65 M€) si Jackson "
     "era titular en 40 partidos. Como suplente de Harry Kane no llegó, y Uli Hoeneß, presidente honorario del Bayern, "
     "lo dijo en público: no iba a llegar a esos 40 partidos, así que el Bayern no iba a tener que comprarlo."),
]
tarjetas = []
for nombre_c, archivo_c, texto_c in CARRUSEL:
    c = fichaje(nombre_c, "Chelsea FC")
    if c is None:
        continue
    autor, licencia, original = CREDITOS[archivo_c]
    costo = ("préstamo" if str(c.tipo_operacion).startswith("cesion")
             else millones(c.coste_fichaje_eur) if pd.notna(c.coste_fichaje_eur) else "libre")
    vio = "lo señaló (dijo «llega»)" if c.proba >= resumen["umbral"] else "no lo vio (dijo «no llega»)"
    tarjetas.append(
        f'<div class="tarjeta"><img src="data:image/jpeg;base64,{foto_base64(archivo_c)}" alt="{nombre_c}">'
        f'<div class="cuerpo"><div class="nombre">{nombre_c}</div>'
        f'<div class="dato">{c.club_origen} → Chelsea · {c.temporada_fichaje} · {miles(c.edad_al_fichaje)} años · {costo}</div>'
        f'<div class="modelo">Probabilidad del modelo: <b>{num(c.proba, 2)}</b> — {vio}</div>'
        f'<div>{texto_c.format(minutos=miles(c.stat_minutes) if pd.notna(c.stat_minutes) else "—")}</div>'
        f'<div class="credito">Foto: {autor}, {licencia}'
        + (f', <a href="{COMMONS}{original.replace(" ", "_")}" target="_blank">Wikimedia Commons</a>' if original else "")
        + '</div></div></div>')
st.markdown('<div class="carrusel">' + "".join(tarjetas) + "</div>", unsafe_allow_html=True)

# los demás fichajes del Chelsea que no se quedaron: se fueron a préstamo, o vendidos a un club fuera del top 20
no_quedaron = (chelsea[chelsea["salio_mal"].astype(bool) & ~chelsea["nombre"].isin([n for n, _, _ in CARRUSEL])]
               .sort_values("coste_fichaje_eur", ascending=False).drop_duplicates("nombre"))
st.markdown("**Otros fichajes del Chelsea que no se quedaron**")
st.write(
    f"Además de los seis de arriba, otros {miles(len(no_quedaron))} fichajes del Chelsea se fueron en una temporada "
    "posterior a préstamo, o vendidos a un club que no es top 20. La última columna dice qué pasó después, según los "
    "traspasos que registra nuestro pipeline (Transfermarkt).")
tabla_ch = pd.DataFrame({
    "jugador": no_quedaron["nombre"], "temporada": no_quedaron["temporada_fichaje"],
    "edad": no_quedaron["edad_al_fichaje"].map(miles),
    "de": no_quedaron["club_origen"],
    "costo": [("préstamo" if str(t).startswith("cesion") else millones(c) if pd.notna(c) else "libre")
              for t, c in zip(no_quedaron["tipo_operacion"], no_quedaron["coste_fichaje_eur"])],
    "rendimiento vs. su puesto": no_quedaron["score_posicion"].map(lambda v: num(v, 2)),
    "minutos": [miles(v) if pd.notna(v) else "—" for v in pd.to_numeric(no_quedaron["stat_minutes"], errors="coerce")],
    "probabilidad": no_quedaron["proba"].map(lambda v: num(v, 2)),
    "el modelo": np.where(no_quedaron["proba"] >= resumen["umbral"], "dijo «llega»", "dijo «no llega»"),
    "qué pasó después": no_quedaron["salidas_despues"]})
st.dataframe(tabla_ch, hide_index=True, width="stretch")


def caso(nombre, destino):
    """Un fichaje del test, para contar los errores con nombre (si está repetido, el de más probabilidad)."""
    f = fichajes[fichajes["nombre"].eq(nombre) & fichajes["club_destino"].eq(destino) & fichajes["conjunto"].eq("test")]
    return None if f.empty else f.sort_values("proba", ascending=False).iloc[0]


with st.expander("Cómo lo sabemos"):
    st.markdown(f"""
**Para qué un modelo.** Los gráficos de *Lo que encontramos* miran un factor por vez. El modelo los mira todos juntos,
así que dice cuánto aporta cada uno **con los demás presentes** (el club de origen no repite lo que ya dice el
rendimiento).

**La métrica: f1 macro.** Sólo el {pct(resumen['tasa_top20'])} de los fichajes llega a un top 20, así que la accuracy
premia decir siempre «no» ({num(t['accuracy_siempre_no'])} sin encontrar a nadie). El f1 macro promedia el f1 de las dos
clases con el mismo peso, y el f1 exige a la vez **precision** (de los que señala, cuántos llegan) y **recall** (de los
que llegan, cuántos encuentra).

**El piso:** un modelo que dice siempre «no llega» da f1 macro **{num(piso)}**.

**La validación:** el test es el 20 % de los fichajes, separado al principio y mirado una sola vez. Todo se eligió con
validación cruzada de 5 pedazos sobre el resto, **por jugador** (`StratifiedGroupKFold`): hay jugadores con más de un
fichaje, y todos sus fichajes van al mismo pedazo. Armados al azar, el número no cambió más que el desvío.

**El desbalance:** sobre la logística de referencia, mover el umbral (0,671) le ganó a `class_weight` (0,613); cada
modelo usa su mejor umbral.

**La comparación.** Cada familia pasó por su grilla de hiperparámetros **antes** de comparar
({resumen['n_combinaciones']} combinaciones). La mejor versión de cada una, con media y desvío entre los 5 pedazos (los
mismos números del gráfico de las cuatro familias):
""")
    tabla = comp.assign(**{"hiperparámetros": comp["params"].astype(str)})[
        ["familia", "hiperparámetros", "umbral", "f1", "desvio", "precision", "recall"]]
    tabla = tabla.assign(**{c: tabla[c].map(lambda v: num(v, 3)) for c in ["f1", "desvio", "precision", "recall"]},
                         umbral=tabla["umbral"].map(lambda v: num(v, 2)))
    st.table(tabla.set_index("familia"))
    st.markdown(f"""
**El elegido: random forest** (`max_depth=10`, `max_features=0.3`, 300 árboles, umbral {num(resumen['umbral'], 2)}).
Le gana a la logística por {num(rf.f1 - rl.f1)}, más que el desvío de los dos ({num(rf.desvio)} y {num(rl.desvio)}). El
boosting empata con el bosque, pero no le gana a la logística por más que su propio desvío ({num(gb.desvio)}).

**En el test, una sola vez:** f1 macro **{num(t['f1'])}** (validación cruzada {num(rf.f1)} ± {num(rf.desvio)}),
precision {num(t['precision'], 2)}, recall {num(t['recall'], 2)}, accuracy {num(t['accuracy'])}. De {t['vp'] + t['fn']}
que llegaron, encontró {t['vp']}; de {t['vp'] + t['fp']} que señaló, {t['fp']} no llegaron: 2 de cada 5 señalados llegan,
cuando la tasa general es 1 de cada 10.

**Cómo se midió lo que aporta cada factor** (importancia por permutación, Práctica 1, 5.4):
1. El modelo final predice los fichajes del test y saca un f1 macro de {num(t['f1'])}. El piso, que dice siempre «no
   llega», saca {num(resumen['piso']['media'])}: lo que el modelo **aprendió** es la diferencia, {num(aprendido)}.
2. Se **mezcla** un factor entero entre los jugadores del test (por ejemplo, las 23 estadísticas de rendimiento, todas
   con la misma mezcla): cada jugador queda con el rendimiento de otro, pero conserva su club, su edad y su puesto.
3. El modelo vuelve a predecir. Como ese factor ya no corresponde a cada jugador, acierta menos.
4. Lo que baja el f1 es lo que aportaba ese factor; dividido por lo aprendido, es la parte que se pierde. Con el
   rendimiento, el f1 baja {num(bloques.set_index('factor_corto').loc['rendimiento', 'caida'])}, el {pct(b['rendimiento'])} de lo aprendido.
5. Como la mezcla es al azar, se repite 10 veces y se promedia (de una mezcla a otra el número varía alrededor de
   0,01). La temporada da un poquito negativo por azar: el modelo no la usa, y se muestra como 0 %.

Se hace por factor y no por columna porque las columnas parecidas se reparten la importancia: cada una de las 23
estadísticas pesa poco sola, porque las otras la cubren. Sacando cada factor y reentrenando (Entrega 3, sección 7.1)
el orden es el mismo: sin las estadísticas el f1 cae 0,093, sin el club de origen 0,039. Ninguno es fuga: todos existen
antes del fichaje y no usan el destino.

**Por qué se equivoca.** En promedio el modelo ordena bien —los que llegan reciben probabilidades mucho más altas—,
pero las dos clases se superponen: hay jugadores que llegan con el perfil de los que no, y al revés (Entrega 3,
secciones 8.1 a 8.3). Casos del test:
""")
    osimhen, mudryk = caso("Victor Osimhen", "Galatasaray"), caso("Mykhaylo Mudryk", "Chelsea FC")
    casos = []
    if osimhen is not None:
        casos.append(
            f"- **Falso positivo, Victor Osimhen** ({osimhen.club_origen} → {osimhen.club_destino}, puesto "
            f"{osimhen.club_destino_ranking_uefa} de UEFA). En la temporada anterior rindió {num(osimhen.score_posicion, 2)} "
            f"desvíos por encima del promedio de los delanteros centro, jugó {miles(osimhen.stat_minutes)} minutos y venía "
            f"de una liga top 5: el modelo le dio **{num(osimhen.proba, 2)}**. Tenía todo el perfil; lo compró un club "
            "grande, pero no uno del top 20. Lo mismo pasa con De Ketelaere (Brugge → Milan, puesto 34) o McTominay "
            "(Manchester United → Napoli, puesto 23).")
    if mudryk is not None:
        casos.append(
            f"- **Falso negativo, Mykhaylo Mudryk** ({mudryk.club_origen} → {mudryk.club_destino}). En la temporada "
            f"anterior al fichaje jugó {miles(mudryk.stat_minutes)} minutos, con un rendimiento de "
            f"{num(mudryk.score_posicion, 2)} desvíos respecto de los extremos y en una liga fuera del top 5: el modelo le "
            f"dio **{num(mudryk.proba, 3)}**. El Chelsea lo compró por la primera mitad de esa misma temporada, y el "
            "modelo sólo ve la temporada **anterior** al fichaje. Que después no rindiera en el Chelsea no cambia la "
            "cuenta: el modelo predice a dónde llega un jugador, no si valía la pena.")
    casos.append(
        "- **Los clubes que fichan como medianos.** El Porto, el Benfica o la Roma compran en su liga o en la de al "
        "lado, jugadores con perfil de fichaje común (David Carmo, del Braga al Porto; Petar Musa, del Boavista al "
        "Benfica): el modelo no los ve porque no sabe quién compra.")
    st.markdown("\n".join(casos) + """

Los dos errores vienen del mismo lugar: el destino depende del club que compra, y eso es justamente lo que el modelo no
puede usar, porque sería la respuesta escrita de otra forma (fuga).
""")

# =============================================================================== COPA · EXPLORÁ
st.markdown('<div class="etiqueta">Tu turno · Explorá</div>', unsafe_allow_html=True)
st.header("Elegí un factor, achicá el universo y mirá quiénes son")
st.write(
    "Empezá por el panorama: para cada nivel del factor que elijas, la barra es el % de fichajes que fue a un top 20 y "
    "la marca negra es la probabilidad media que les dio el modelo. Después achicá el universo con los filtros y **tocá "
    "una barra** para ver los jugadores de ese grupo con lo que dijo el modelo de cada uno. Cada fichaje lo predice un "
    "modelo que no lo vio: los del entrenamiento salen de la validación cruzada, los del test del modelo final.")

NOMBRE_FACTOR = {"rendimiento comparado con su puesto": "Rendimiento para su puesto",
                 "nivel UEFA del club de origen": "Nivel UEFA del club de origen",
                 "liga de origen": "Liga de origen", "edad al fichar": "Edad al fichar", "puesto": "Puesto"}
f1c, f2c, f3c, f4c = st.columns([1.3, 1.2, 1, 1.3])
factor = f1c.selectbox("Factor", list(NOMBRE_FACTOR), format_func=NOMBRE_FACTOR.get)
puesto = f2c.selectbox("Puesto", ["Todos"] + m.ROLES, disabled=factor == "puesto")
origen = f3c.radio("Liga de origen", ["Todas", "Liga top 5", "Otra liga"], disabled=factor == "liga de origen")
temporadas_sel = f4c.multiselect("Temporadas", sorted(fichajes["temporada_fichaje"].unique()),
                                 default=sorted(fichajes["temporada_fichaje"].unique()))

vista = fichajes[fichajes["temporada_fichaje"].isin(temporadas_sel)]
if puesto != "Todos" and factor != "puesto":
    vista = vista[vista["grupo_posicion"] == puesto]
if origen != "Todas" and factor != "liga de origen":
    vista = vista[vista["club_origen_liga_es_top5"] == (origen == "Liga top 5")]

if vista.empty:
    st.info("No quedan fichajes con estos filtros.")
else:
    panorama = tasa_por_nivel(vista, factor)
    # con pocos casos el porcentaje salta mucho (2 de 8 ya es 25 %): como en la práctica de Altair (7.3),
    # los grupos de menos de 20 fichajes se muestran claros y con su cantidad a la vista
    MIN_CASOS = 20
    panorama["alfa"] = np.where(panorama["fichajes"] < MIN_CASOS, 0.3, 1.0)
    panorama["etiqueta"] = [f"{e} ({miles(n_)})" for e, n_ in zip(panorama["etiqueta"], panorama["fichajes"])]
    st.caption(f"{miles(len(vista))} fichajes con estos filtros · entre paréntesis, cuántos hay en cada grupo · "
               "la línea punteada es la tasa de este universo "
               f"({pct(vista['es_destino_top_20'].mean(), 1)})")
    seleccion = alt.selection_point(name="nivel_elegido", fields=["nivel"])
    base_e = alt.Chart(panorama).encode(x=alt.X("etiqueta:N", sort=list(panorama["etiqueta"]), title=NOMBRE_FACTOR[factor],
                                                axis=alt.Axis(labelAngle=0, labelOverlap=False, labelLimit=160)))
    barras_e = base_e.mark_bar(color=AZUL, cursor="pointer").encode(
        y=alt.Y("tasa:Q", title="% que va a un top 20", axis=alt.Axis(format="%")),
        opacity=alt.condition(seleccion, alt.Opacity("alfa:Q", scale=None, legend=None), alt.value(0.15)),
        tooltip=[alt.Tooltip("nivel:N"), alt.Tooltip("fichajes:Q"),
                 alt.Tooltip("tasa:Q", format=".1%", title="% que fue a un top 20"),
                 alt.Tooltip("modelo:Q", format=".1%", title="probabilidad media del modelo")]
    ).add_params(seleccion)
    marcas_modelo = base_e.mark_tick(color="#1d2329", thickness=3, size=40).encode(y="modelo:Q")
    tasa_vista = alt.Chart(pd.DataFrame({"t": [vista["es_destino_top_20"].mean()]})).mark_rule(
        strokeDash=[4, 3], color="#777").encode(y="t:Q")
    # la clave cambia con el factor (la barra elegida de otro factor no existe en éste) y con «Cerrar la lista»:
    # una clave nueva es un gráfico nuevo, sin ninguna barra elegida
    st.session_state.setdefault("explora_cierres", 0)
    evento = grafico((barras_e + marcas_modelo + tasa_vista).properties(height=320), width="stretch",
                     on_select="rerun", key=f"explora_barras_{factor}_{st.session_state['explora_cierres']}")

    if (panorama["fichajes"] < MIN_CASOS).any():
        st.caption(f"Las barras claras tienen menos de {MIN_CASOS} fichajes: con tan pocos casos el porcentaje se mueve "
                   "mucho (2 de 8 ya es 25 %), así que no conviene sacar conclusiones de ellas.")
    niveles_vistos = set(panorama["nivel"])
    elegidos = [p["nivel"] for p in evento.selection.get("nivel_elegido", [])
                if "nivel" in p and p["nivel"] in niveles_vistos]
    if not elegidos:
        st.caption("Tocá una barra para ver los jugadores de ese grupo.")
    else:
        grupo = vista[vista[factor].isin(elegidos)].sort_values("proba", ascending=False)
        texto_c, boton_c = st.columns([5, 1], vertical_alignment="center")
        texto_c.markdown(f"**{miles(len(grupo))} fichajes en «{', '.join(elegidos)}»**, ordenados por la probabilidad que "
                         f"les dio el modelo. {int(grupo['es_destino_top_20'].sum())} fueron a un top 20.")
        boton_c.button("Cerrar la lista", icon=":material/close:",
                       on_click=lambda: st.session_state.update(explora_cierres=st.session_state["explora_cierres"] + 1))
        detalle = grupo.assign(destino=grupo["club_destino"] + " (puesto " + grupo["club_destino_ranking_uefa"].astype(str)
                                       + ")")[["nombre", "temporada_fichaje", "grupo_posicion", "edad_al_fichaje",
                                               "club_origen", "destino", "proba", "resultado"]]
        st.dataframe(
            detalle, hide_index=True, width="stretch", height=320,
            column_config={"nombre": "jugador", "temporada_fichaje": "temporada", "grupo_posicion": "puesto",
                           "edad_al_fichaje": st.column_config.NumberColumn("edad", format="%d"),
                           "club_origen": "de", "destino": "a (club real)",
                           "proba": st.column_config.ProgressColumn("probabilidad del modelo", min_value=0,
                                                                    max_value=1, format="%.2f"),
                           "resultado": "qué pasó"})

# =============================================================================== COPA · PROBÁ EL MODELO
st.markdown('<div class="etiqueta">Tu turno · Probá el modelo</div>', unsafe_allow_html=True)
st.header("Armá un fichaje y mirá qué probabilidad le da el modelo")
st.write(
    "Elegí el puesto, la edad y el club de origen, y mové las estadísticas de la temporada anterior. El modelo es el "
    "mismo random forest del notebook, ya entrenado: nada se reentrena. Los deslizadores van del mínimo al máximo que vio "
    "el entrenamiento **para ese puesto**, y el club sale de la lista de clubes que conoce, así que no se pueden cargar "
    "valores que el modelo nunca vio.")

rangos_rol = {rol: g.set_index("stat") for rol, g in rangos.groupby("rol")}
EDAD_MIN, EDAD_MAX = int(fichajes["edad_al_fichaje"].min()), int(fichajes["edad_al_fichaje"].max())


def cargar_jugador():
    """Copia los valores de un fichaje real a los controles."""
    k = st.session_state["partir_de"]
    if k is None:
        return
    fila = columnas_modelo.loc[k]
    st.session_state["p_puesto"] = fila["grupo_posicion"]
    st.session_state["p_edad"] = int(np.clip(fila["edad_al_fichaje"], EDAD_MIN, EDAD_MAX))
    st.session_state["p_club"] = fila["club_origen"]
    st.session_state["p_temporada"] = fila["temporada_fichaje"]
    # las stats que no son del puesto no tienen deslizador: se guardan tal cual las tenía el jugador
    st.session_state["p_resto"] = {"puesto": fila["grupo_posicion"],
                                   "valores": {s: fila[s] for s in m.STATS}}
    r = rangos_rol[fila["grupo_posicion"]]
    for s in [s for s in m.STATS if s in r.index]:
        v = pd.to_numeric(fila[s], errors="coerce")
        st.session_state[f"p_{s}"] = float(np.clip(v if pd.notna(v) else r.loc[s, "mediana"], r.loc[s, "min"], r.loc[s, "max"]))


conocidos = columnas_modelo.assign(etiqueta=columnas_modelo["nombre"] + " · " + columnas_modelo["temporada_fichaje"]
                                   + " · " + columnas_modelo["club_origen"] + " → " + columnas_modelo["club_destino"])
st.selectbox("Partir de un fichaje real (opcional)", [None] + list(conocidos.index), key="partir_de",
             format_func=lambda k: "— elegí uno o arrancá de cero —" if k is None else conocidos.loc[k, "etiqueta"],
             on_change=cargar_jugador)

lista_clubes = list(clubes["club_origen"])
lista_temporadas = sorted(fichajes["temporada_fichaje"].unique())
# valores de partida: un extremo de 22 años que viene del Benfica, en la última temporada
st.session_state.setdefault("p_puesto", "Delantero extremo")
st.session_state.setdefault("p_edad", 22)
st.session_state.setdefault("p_club", "SL Benfica" if "SL Benfica" in lista_clubes else lista_clubes[0])
st.session_state.setdefault("p_temporada", lista_temporadas[-1])

p1, p2, p3, p4 = st.columns(4)
puesto_p = p1.selectbox("Puesto", m.ROLES, key="p_puesto")
edad_p = p2.slider("Edad al fichar", EDAD_MIN, EDAD_MAX, key="p_edad")
club_p = p3.selectbox("Club de origen", lista_clubes, key="p_club")
temporada_p = p4.selectbox("Temporada del fichaje", lista_temporadas, key="p_temporada")
club = clubes.set_index("club_origen").loc[club_p]
st.caption(f"{club_p}: {club['club_origen_liga']} · "
           + ("liga top 5" if club["club_origen_liga_es_top5"] else "fuera de las ligas top 5") + " · "
           + (f"coeficiente UEFA {num(club['club_origen_coeficiente_uefa'], 1)}"
              if pd.notna(club["club_origen_coeficiente_uefa"]) else "fuera del ranking UEFA de clubes"))

r = rangos_rol[puesto_p]
propias = [s for s in m.BASE + m.ESPECIFICAS[puesto_p] if s in r.index]
NIVELES_Q = [f"q{k}" for k in range(101)]
PLURAL = {"Arquero": "arqueros", "Defensor central": "defensores centrales", "Lateral": "laterales",
          "Mediocampo defensivo": "mediocampistas defensivos", "Mediocampo ofensivo": "mediocampistas ofensivos",
          "Delantero centro": "delanteros centro", "Delantero extremo": "delanteros extremos"}


def aplicar_nivel(percentil):
    """Pone las 7 stats del puesto en un percentil del entrenamiento; las demás vuelven al promedio del puesto."""
    rr = rangos_rol[st.session_state["p_puesto"]]
    for s_ in m.BASE + m.ESPECIFICAS[st.session_state["p_puesto"]]:
        if s_ in rr.index:
            lo_, hi_ = float(rr.loc[s_, "min"]), float(rr.loc[s_, "max"])
            paso_ = 1.0 if hi_ - lo_ > 50 else 0.1 if hi_ - lo_ > 5 else 0.01
            st.session_state[f"p_{s_}"] = round(float(rr.loc[s_, f"q{percentil}"]) / paso_) * paso_
    st.session_state["p_resto"] = None
    st.session_state["partir_de"] = None


st.markdown("**Atajos:** cargá las 7 estadísticas del puesto de una vez, y después ajustá lo que quieras.")
a1, a2, a3, _ = st.columns([1, 1, 1, 1.5])
a1.button("Promedio del puesto", on_click=aplicar_nivel, args=(50,), help="La mitad de los jugadores del puesto "
          "tiene más y la mitad menos", width="stretch")
a2.button("Bueno", on_click=aplicar_nivel, args=(75,), help="Mejor que 3 de cada 4 jugadores del puesto",
          width="stretch")
a3.button("Muy bueno", on_click=aplicar_nivel, args=(90,), help="Mejor que 9 de cada 10 jugadores del puesto",
          width="stretch")
resto = st.session_state.get("p_resto")
st.markdown(f"**Estadísticas de la temporada anterior** (las 7 propias de un {puesto_p.lower()}; las demás "
            + ("quedan como las tenía el jugador elegido)" if resto and resto["puesto"] == puesto_p
               else "quedan en el promedio de su puesto)"))
valores = {}
cols = st.columns(4)
for j, s in enumerate(propias):
    lo, med, hi = float(r.loc[s, "min"]), float(r.loc[s, "mediana"]), float(r.loc[s, "max"])
    if f"p_{s}" not in st.session_state or not (lo <= st.session_state[f"p_{s}"] <= hi):
        st.session_state[f"p_{s}"] = med
    paso = 1.0 if hi - lo > 50 else 0.1 if hi - lo > 5 else 0.01
    formato = "%.0f" if paso == 1.0 else "%.1f" if paso == 0.1 else "%.2f"
    valores[s] = cols[j % 4].slider(NOMBRES_STATS.get(s, s), lo, hi, step=paso, key=f"p_{s}", format=formato)
    cuantiles = r.loc[s, NIVELES_Q].to_numpy(dtype=float)
    supera = float(np.interp(valores[s], cuantiles, np.arange(101)))
    cols[j % 4].caption(f"más que el {supera:.0f} % de los {PLURAL[puesto_p]} · típico: "
                        f"{num(r.loc[s, 'mediana'], 0 if paso == 1.0 else 1)}")

caso = {c: np.nan for c in m.COLUMNAS_MODELO}
resto = st.session_state.get("p_resto")
if resto and resto["puesto"] == puesto_p:  # partiendo de un jugador real, el resto de sus stats
    caso.update(resto["valores"])
caso.update(valores)
caso.update({"grupo_posicion": puesto_p, "temporada_fichaje": temporada_p, "edad_al_fichaje": edad_p,
             "club_origen_coeficiente_uefa": club["club_origen_coeficiente_uefa"],
             "club_origen_pais_coeficiente_uefa": club["club_origen_pais_coeficiente_uefa"],
             "club_origen_liga_es_top5": bool(club["club_origen_liga_es_top5"]),
             "club_origen_es_filial": bool(club["club_origen_es_filial"]),
             "club_origen_es_europeo": bool(club["club_origen_es_europeo"])})
proba = float(final.predict_proba(pd.DataFrame([caso])[m.COLUMNAS_MODELO])[:, 1][0])
llega = proba >= resumen["umbral"]

r1, r2 = st.columns([1, 2])
r1.markdown(f'<div class="cifra" style="color:{AZUL if llega else GRIS}">{num(proba, 2)}</div>'
            f'probabilidad de llegar a un top 20<br><b>El modelo dice: {"llega" if llega else "no llega"}</b> '
            f'(umbral {num(resumen["umbral"], 2)})', unsafe_allow_html=True)
escala_p = alt.Scale(domain=[0, 1])
pista = alt.Chart(pd.DataFrame({"p": [1.0]})).mark_bar(color="#e6e6e6", size=34, opacity=0.35).encode(
    x=alt.X("p:Q", scale=escala_p, axis=alt.Axis(format=".0%"), title=None))
barra = alt.Chart(pd.DataFrame({"p": [max(proba, 0.004)]})).mark_bar(color=AZUL if llega else GRIS, size=34).encode(
    x=alt.X("p:Q", scale=escala_p))
linea_umbral = alt.Chart(pd.DataFrame({"p": [resumen["umbral"]]})).mark_tick(
    color=NARANJA, thickness=3, size=60).encode(x=alt.X("p:Q", scale=escala_p))
with r2:
    grafico((pista + barra + linea_umbral).properties(height=110), width="stretch")
st.caption(f"La barra es la probabilidad; la línea naranja, el umbral ({num(resumen['umbral'], 2)}): desde ahí el modelo "
           f"dice «llega». Para comparar: el {pct(resumen['tasa_top20'], 1)} de todos los fichajes llega a un top 20. Una probabilidad "
           "de 0,25 ya es dos veces y media la tasa general.")

# =============================================================================== CIERRE
mudryk_c, hernandez_c = fichaje("Mykhaylo Mudryk", "Chelsea FC"), fichaje("Lucas Hernández", "Paris Saint-Germain")
se_fueron_chelsea = pd.DataFrame(resumen["salidas_top20"]).set_index("club_destino").loc["Chelsea FC", "se_fueron"]
st.markdown('<div class="etiqueta">Cierre</div>', unsafe_allow_html=True)
st.header("Sabemos qué factores pesan; lo que el modelo no puede ver es quién compra y qué pasa después")
st.write(
    "**La respuesta a la pregunta del proyecto:** llegan a un club top 20, sobre todo, los que rindieron bien para su "
    "puesto y vienen de un club fuerte de Europa; ser muy joven ayuda, y el puesto no cambia nada. El modelo lo confirma "
    "y mide cuánto pesa cada factor. Pero con lo que se sabe antes del fichaje tiene un techo: cuando dice «llega», "
    f"acierta el {pct(t['precision'])} de las veces, y encuentra al {pct(t['recall'])} de los que llegan. Esto es lo que "
    "quedó sin responder:")
st.markdown(f"""
1. **Quién compra.** El destino depende del club que compra, y ése es justamente el dato que el modelo no puede usar:
   sería la respuesta escrita de otra forma. De ahí salen los dos errores. El {pct(fp_cerca)} de los falsos positivos
   terminó en un club del puesto 21 al 100, y clubes del top 20 como el Porto o el Benfica compran jugadores que, por sus
   números, parecen fichajes comunes.
2. **Lo que pasa en la misma temporada.** El modelo mira la temporada **anterior** al fichaje. Un club que compra en enero
   lo hace por la primera mitad de la temporada en curso, que el modelo no ve: Mudryk llegó al Chelsea con
   {miles(mudryk_c.stat_minutes) if mudryk_c is not None else "pocos"} minutos en la temporada anterior. Faltaría separar
   los fichajes de verano de los de invierno, y sumar esa media temporada.
3. **Lo que no está en las estadísticas.** Lesiones, conflictos con el club, investigaciones, sueldos, cláusulas, años de
   contrato. Lucas Hernández llegó al PSG con {miles(hernandez_c.stat_minutes) if hernandez_c is not None else "pocos"}
   minutos, después de romperse los ligamentos; Osimhen se fue del Napoli por un conflicto con el club; a Paquetá lo
   frenó una investigación. Ninguna de nuestras tres fuentes tiene esos datos.
4. **Una línea en el puesto 20.** Preguntamos «top 20, sí o no», pero el ranking de UEFA es una escala continua: para el
   modelo, un club del puesto 18 y uno del 23 se parecen mucho. Predecir el puesto del club de destino, en vez de sí o
   no, respondería la pregunta con más matices.
5. **Si el fichaje salió bien.** El modelo predice a dónde llega un jugador, no si va a rendir: del Chelsea se fue el
   {pct(se_fueron_chelsea)} de los que llegaron. La pregunta que sigue es otra: qué hace que un jugador, una vez en un
   top 20, se quede y juegue.
""")

with st.expander("Qué cambió desde la Entrega 3"):
    st.markdown("""
La aplicación y la sección 9 del notebook responden directamente la pregunta del proyecto: qué factores pesan y cuánto
(importancia por factor y cómo usa el modelo cada uno). Ajustamos las cuatro familias de modelos **antes** de elegir
(antes se comparaban con sus valores por defecto), y con eso el elegido pasó de la regresión logística al random forest. La edad entra **numérica** (antes, en tramos), y agregamos
la hipótesis de la edad a la Entrega 2. La precision subió de 0,34 a 0,39 en el test, y los errores se analizan con
nombres: a dónde fueron los que el modelo señaló de más y a qué clubes van los que se le escapan.
""")
st.caption(f"Ciencia de Datos · UTN FRM · 2026 · Grupo 7 · Fuentes: Transfermarkt, FotMob y UEFA · aplicación construida "
           f"el {resumen['construido']} con app/build_app.py.")
