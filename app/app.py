"""¿Qué factores hacen que un jugador llegue a un club top 20? · Entrega 4 · Grupo 7

    streamlit run app/app.py

Lee lo que deja app/build_app.py en app/datos/. No entrena nada: carga el modelo guardado.
"""
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

DATOS = os.path.join(AQUI, "datos")
alt.data_transformers.disable_max_rows()

# Los colores significan lo mismo en toda la aplicación:
#   azul      = fue a un top 20 (y el modelo lo encontró)
#   celeste   = fue a un top 20 y el modelo no lo vio
#   naranja   = el modelo dijo top 20 y no fue
#   gris      = no fue a un top 20
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

st.set_page_config(page_title="¿Qué lleva a un jugador a un top 20?", layout="wide")


def grafico(chart, **kw):
    """st.altair_chart con un margen interno, para que los títulos de los ejes no queden cortados en el borde."""
    return st.altair_chart(chart.properties(padding={"left": 18, "top": 14, "right": 14, "bottom": 10}), **kw)



@st.cache_resource
def cargar_modelo():
    return joblib.load(os.path.join(DATOS, "modelo.joblib"))


@st.cache_data
def cargar_datos():
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


resumen, fichajes, columnas_modelo, clubes, rangos = cargar_datos()
final = cargar_modelo()
t = resumen["test"]
fp_cerca = resumen["fp_destino"]["puesto 21 a 50"] + resumen["fp_destino"]["puesto 51 a 100"]

st.markdown("""
<style>
.etiqueta {font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; color: #6b6b6b; margin-top: 2.2rem;}
.cifra {font-size: 2.6rem; font-weight: 700; color: #2a78d6; line-height: 1.1;}
.idea {font-size: 1.35rem; font-weight: 600; border-left: 4px solid #2a78d6; padding-left: 0.8rem; margin: 1rem 0;}
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

st.markdown('<div class="etiqueta">El proyecto</div>', unsafe_allow_html=True)
st.title("¿Qué factores hacen que un jugador llegue a un club top 20 de Europa?")
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
            'fichajes termina en un club top 20 de UEFA.', unsafe_allow_html=True)
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
grafico((barras + textos).properties(height=230), width="stretch")
st.write(
    f"Cada barra es una temporada de fichajes; la parte azul, los que fueron a un top 20. El número a la derecha es "
    f"la proporción: entre 9 % y 11 % todos los años ({pct(resumen['tasa_top20'], 1)} en total). Por eso la "
    "precisión se mide con cuidado: un modelo que dijera siempre «no llega» acertaría 9 de cada 10 veces sin "
    "encontrar a nadie.")

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
st.write(
    f"Cada panel es un factor, con **la misma escala**; la línea punteada es la tasa general "
    f"({pct(resumen['tasa_top20'], 1)}). En los tres primeros la barra de la derecha está muy por encima de la de la "
    "izquierda: rendir más que los de su puesto, venir de un club fuerte en UEFA y llegar muy joven multiplican las "
    "chances. En el último, todas las barras quedan pegadas a la línea: el puesto no cambia casi nada.")

h5 = pd.DataFrame(resumen["h5"])
alto_alto = h5.query("origen == 'alto' and rendimiento == 'alto'")["tasa"].iloc[0]
bajo_alto = h5.query("origen == 'bajo' and rendimiento == 'alto'")["tasa"].iloc[0]
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

**Los dos primeros factores suman por separado.** Cruzando club de origen y rendimiento (tercios de cada uno), con el
mismo rendimiento alto, venir de un club de nivel bajo da""" + f""" {pct(bajo_alto, 1)} y de uno alto {pct(alto_alto, 1)}:""")
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
    st.markdown("""
**Cómo se construyó el gráfico principal.** Cada barra es el % de los fichajes de ese nivel que fue a un top 20.
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
orden_b = list(bloques.sort_values("pierde", ascending=False)["factor_corto"])
base_b = alt.Chart(bloques).encode(y=alt.Y("factor_corto:N", sort=orden_b, title=None, axis=alt.Axis(labelLimit=220)))
barras_b = base_b.mark_bar(color=AZUL).encode(
    x=alt.X("pierde:Q", axis=alt.Axis(format="%"), scale=alt.Scale(domain=[0, 0.7]),
            title="parte de lo que aprendió el modelo que se pierde sin ese factor"),
    tooltip=[alt.Tooltip("factor:N"), alt.Tooltip("pierde:Q", format=".0%", title="se pierde")])
textos_b = base_b.mark_text(align="left", dx=5, fontSize=13, color="#1d2329").encode(
    x=alt.X("pierde:Q", scale=alt.Scale(domain=[0, 0.7])), text="rotulo:N")
grafico((barras_b + textos_b).properties(height=210), width="stretch")
st.write(
    "Entrenamos un random forest que predice si el fichaje va a un top 20, con todos los factores juntos. Después le "
    "sacamos un factor por vez —mezclando esa información entre los jugadores, para que no la pueda usar— y medimos "
    f"cuánto empeora. Sin el rendimiento pierde el {pct(b['rendimiento'])} de lo que había aprendido, y sin el club de "
    f"origen el {pct(b['club de origen'])}; el puesto y la edad suman poco, y la temporada nada. Es el mismo orden que "
    "mostraban los datos solos: el modelo no encontró un factor escondido, confirmó los que ya se veían y midió cuánto "
    "pesa cada uno. Los porcentajes no suman 100 % porque los factores se superponen en parte (los jugadores de clubes "
    "fuertes también suelen rendir más).")

with st.expander("Cómo lo sabemos"):
    comp = pd.DataFrame(resumen["comparacion"])
    piso = resumen["piso"]["media"]
    st.markdown(f"""
**Para qué un modelo.** Los gráficos de arriba miran un factor por vez. El modelo los mira todos juntos, así que dice
cuánto aporta cada uno **con los demás presentes** (el club de origen no repite lo que ya dice el rendimiento).

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
({resumen['n_combinaciones']} combinaciones). La mejor versión de cada una, con media y desvío entre los 5 pedazos:
""")
    tabla = comp.assign(**{"hiperparámetros": comp["params"].astype(str)})[
        ["familia", "hiperparámetros", "umbral", "f1", "desvio", "precision", "recall"]]
    tabla = tabla.assign(**{c: tabla[c].map(lambda v: num(v, 3)) for c in ["f1", "desvio", "precision", "recall"]},
                         umbral=tabla["umbral"].map(lambda v: num(v, 2)))
    st.table(tabla.set_index("familia"))
    puntos = alt.Chart(comp).mark_point(filled=True, size=90, color=AZUL).encode(
        x=alt.X("f1:Q", scale=alt.Scale(domain=[0.46, 0.72]), title="f1 macro (media ± desvío)"),
        y=alt.Y("familia:N", sort=list(comp.sort_values("f1", ascending=False)["familia"]), title=None))
    errores = alt.Chart(comp).mark_errorbar(color=AZUL).encode(
        x=alt.X("min:Q", scale=alt.Scale(domain=[0.46, 0.72]), title="f1 macro (media ± desvío)"), x2="max:Q",
        y=alt.Y("familia:N", sort=list(comp.sort_values("f1", ascending=False)["familia"]))
    ).transform_calculate(min="datum.f1 - datum.desvio", max="datum.f1 + datum.desvio")
    linea_piso = alt.Chart(pd.DataFrame({"piso": [piso]})).mark_rule(strokeDash=[4, 3], color="#777").encode(x="piso:Q")
    grafico((errores + puntos + linea_piso).properties(height=170, title="Eje recortado de 0,46 a 0,72; "
                    "la línea punteada es el piso"), width="stretch")
    rf = comp.set_index("familia").loc["random forest"]
    rl = comp.set_index("familia").loc["regresión logística"]
    gb = comp.set_index("familia").loc["gradient boosting"]
    st.markdown(f"""
**El elegido: random forest** (`max_depth=10`, `max_features=0.3`, 300 árboles, umbral {num(resumen['umbral'], 2)}).
Le gana a la logística por {num(rf.f1 - rl.f1)}, más que el desvío de los dos ({num(rf.desvio)} y {num(rl.desvio)}). El
boosting empata con el bosque, pero no le gana a la logística por más que su propio desvío ({num(gb.desvio)}).

**En el test, una sola vez:** f1 macro **{num(t['f1'])}** (validación cruzada {num(rf.f1)} ± {num(rf.desvio)}),
precision {num(t['precision'], 2)}, recall {num(t['recall'], 2)}, accuracy {num(t['accuracy'])}. De {t['vp'] + t['fn']}
que llegaron, encontró {t['vp']}; de {t['vp'] + t['fp']} que señaló, {t['fp']} no llegaron: 2 de cada 5 señalados llegan,
cuando la tasa general es 1 de cada 10.

**Dónde se equivoca.** Los que se le escapan van sobre todo a los clubes del top 20 que fichan como medianos (Porto,
Roma, Benfica): compran jugadores sin perfil de top 20.
""")
    clubes_test = pd.DataFrame(resumen["clubes_test"]).head(12)
    largo_c = clubes_test.melt(id_vars="club", value_vars=["encontrados", "perdidos"], var_name="qué pasó",
                               value_name="fichajes")
    largo_c["qué pasó"] = largo_c["qué pasó"].replace({"encontrados": "el modelo lo encontró",
                                                       "perdidos": "se le escapó"})
    grafico(alt.Chart(largo_c).mark_bar().encode(
        y=alt.Y("club:N", sort=list(clubes_test["club"]), title=None, axis=alt.Axis(labelLimit=220, labelOverlap=False)),
        x=alt.X("fichajes:Q", title="fichajes del test que llegaron a ese club top 20", stack="zero"),
        color=alt.Color("qué pasó:N", scale=alt.Scale(domain=["el modelo lo encontró", "se le escapó"],
                                                     range=[AZUL, CELESTE]), legend=alt.Legend(title=None, orient="top")),
        order=alt.Order("qué pasó:N"), tooltip=["club", "qué pasó", "fichajes"]).properties(height=330), width="stretch")
    st.markdown("Los que señala de más tienen perfil de top 20 y terminan **justo debajo**. "
                "**De los que no llegaron a un top 20, ¿a qué puesto UEFA fue su club?** (cada grupo suma 100 %)")
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
    st.markdown(f"""
El {pct(fp_cerca)} de los falsos positivos fue a un club del puesto 21 al 100 (McTominay al Napoli, De Ketelaere al
Milan): el corte en el puesto 20 no se ve en el perfil del jugador.

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
    evento = grafico((barras_e + marcas_modelo + tasa_vista).properties(height=320), width="stretch",
                             on_select="rerun", key="explora_barras")

    if (panorama["fichajes"] < MIN_CASOS).any():
        st.caption(f"Las barras claras tienen menos de {MIN_CASOS} fichajes: con tan pocos casos el porcentaje se mueve "
                   "mucho (2 de 8 ya es 25 %), así que no conviene sacar conclusiones de ellas.")
    elegidos = [p["nivel"] for p in evento.selection.get("nivel_elegido", []) if "nivel" in p]
    if not elegidos:
        st.caption("Tocá una barra para ver los jugadores de ese grupo.")
    else:
        grupo = vista[vista[factor].isin(elegidos)].sort_values("proba", ascending=False)
        st.markdown(f"**{miles(len(grupo))} fichajes en «{', '.join(elegidos)}»**, ordenados por la probabilidad que les "
                    f"dio el modelo. {int(grupo['es_destino_top_20'].sum())} fueron a un top 20.")
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
