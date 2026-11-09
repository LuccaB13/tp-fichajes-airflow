"""¿Qué hace falta para llegar a un club top 20? · Entrega 4 · Grupo 7

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
RESULTADOS = ["acierto: llegó y lo señaló", "se le escapó: llegó y no lo señaló",
              "falso positivo: lo señaló y no llegó", "negativo: no llegó y no lo señaló"]
COLOR_RESULTADO = alt.Scale(domain=RESULTADOS, range=[AZUL, CELESTE, NARANJA, GRIS])

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

st.set_page_config(page_title="¿Quién llega a un club top 20?", page_icon="⚽", layout="wide")


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
st.markdown('<div class="etiqueta">El proyecto</div>', unsafe_allow_html=True)
st.title("¿Qué hace falta para que un jugador llegue a un club top 20 de Europa?")
st.write(
    "Cada temporada, miles de jugadores cambian de club. Unos pocos terminan en uno de los 20 clubes con "
    "mejor coeficiente UEFA. Con lo que se sabe **antes** del fichaje —cómo jugó la temporada anterior, su "
    "edad, su puesto y de qué club viene—, ¿se puede anticipar quién?")
st.markdown(
    f'<div class="idea">Con lo que se sabe antes del fichaje, el modelo arma una lista donde 2 de cada 5 jugadores '
    f'llegan a un top 20, y {pct(fp_cerca)} de los que no llegan terminan en un club que está justo debajo.</div>',
    unsafe_allow_html=True)
c1, c2, c3 = st.columns(3)
c1.markdown(f'<div class="cifra">{num(t["f1"])}</div>f1 macro en el test, contra {num(resumen["piso"]["media"])} '
            'del piso que dice siempre «no llega»', unsafe_allow_html=True)
c2.markdown(f'<div class="cifra">2 de cada 5</div>de los jugadores que señala llegan a un top 20 '
            f'(precision {num(t["precision"], 2)}; la tasa general es 1 de cada 10)', unsafe_allow_html=True)
c3.markdown(f'<div class="cifra">{pct(fp_cerca)}</div>de los que señala y no llegan fueron a un club del puesto '
            '21 al 100 de UEFA: casi aciertos', unsafe_allow_html=True)
st.caption(f"Medido sobre {miles(resumen['n_ana'])} fichajes de {miles(resumen['n_jugadores'])} jugadores, cinco "
           f"temporadas (2022/23 a 2026/27). Datos del pipeline: {resumen['datos']}.")

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
    y=alt.Y("temporada_fichaje:N", title="temporada del fichaje"),
    x=alt.X("cantidad:Q", title="fichajes", stack="zero"),
    color=alt.Color("destino:N", scale=alt.Scale(domain=["fue a un top 20", "no fue a un top 20"],
                                                range=[AZUL, GRIS]), legend=alt.Legend(title=None, orient="top")),
    order=alt.Order("destino:N"),
    tooltip=["temporada_fichaje", "destino", "cantidad"])
textos = alt.Chart(temporadas).mark_text(align="left", dx=4, color="#333").encode(
    y="temporada_fichaje:N", x=alt.X("fichajes:Q"), text=alt.Text("tasa:Q", format=".0%"))
st.altair_chart((barras + textos).properties(height=230), width="stretch")
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
    st.dataframe(pasos, hide_index=True, width="stretch")
    st.markdown(f"""
**Columnas que se descartaron por fuga** (existen recién **en** el fichaje, o se calculan con el destino):
{", ".join(f"`{c}`" for c in resumen["fuga"])}. Todo lo del destino es la respuesta escrita de otra forma.

**Lo que entra al modelo:** las 23 estadísticas que armaban el puntaje de rendimiento de la Entrega 2, cada una
comparada con los de su mismo puesto; el puesto; la edad; la temporada; y del club de origen, su coeficiente UEFA y el
de su país, y si viene de una liga top 5, de un filial o de Europa.
""")

# =============================================================================== TALLO 2 · LO QUE ENCONTRAMOS
h5 = pd.DataFrame(resumen["h5"])
alto_alto = h5.query("origen == 'alto' and rendimiento == 'alto'")["tasa"].iloc[0]
bajo_alto = h5.query("origen == 'bajo' and rendimiento == 'alto'")["tasa"].iloc[0]
st.markdown('<div class="etiqueta">Lo que encontramos</div>', unsafe_allow_html=True)
st.header("Con el mismo rendimiento, venir de un club fuerte multiplica por cuatro las chances de llegar a un top 20")
orden = ["bajo", "medio", "alto"]
base_h5 = alt.Chart(h5).encode(
    x=alt.X("rendimiento:O", sort=orden, title="rendimiento la temporada anterior, comparado con su puesto (tercios)"),
    y=alt.Y("origen:O", sort=orden[::-1], title="nivel del club de origen en UEFA (tercios)"))
celdas = base_h5.mark_rect().encode(
    color=alt.Color("tasa:Q", scale=alt.Scale(scheme="blues", domain=[0, 0.4]),
                    legend=alt.Legend(title="% que va a un top 20", format=".0%")),
    tooltip=[alt.Tooltip("origen:O", title="club de origen"), alt.Tooltip("rendimiento:O"),
             alt.Tooltip("tasa:Q", format=".1%", title="% top 20"), alt.Tooltip("n:Q", title="fichajes")])
numeros = base_h5.mark_text(fontSize=16).encode(
    text=alt.Text("tasa:Q", format=".1%"),
    color=alt.condition(alt.datum.tasa > 0.2, alt.value("white"), alt.value("#222")))
st.altair_chart((celdas + numeros).properties(height=300), width="stretch")
st.write(
    f"Mirá la columna de la derecha: jugadores que rindieron igual de bien. Si venían de un club de nivel UEFA bajo, "
    f"llegó a un top 20 el {pct(bajo_alto, 1)}; si venían de uno alto, el {pct(alto_alto, 1)}. Y bajando por cualquier "
    "fila pasa lo mismo con el rendimiento: **los dos ejes suman por su lado**. El club de origen no repite lo que ya "
    "dicen las estadísticas: mide el contexto en el que se generaron.")

with st.expander("Cómo lo sabemos"):
    st.markdown("""
**Una hipótesis que se sostuvo (Hipótesis 5, club de origen).** El coeficiente UEFA del club de origen separa a los que
llegan a un top 20 del resto: separación estandarizada **0,749** (amarillo) entre jugadores con estadísticas. Partido
por liga, fuera de las ligas top 5 sube a **0,895** (verde), y dentro cae a 0,318: ahí la liga ya hace de filtro. Y casi
no se correlaciona con el rendimiento (Spearman **0,18**, rojo): mide otra cosa. Por eso el bloque del club de origen
entró al modelo, y sacarlo baja el f1 0,039.

**Una que no se sostuvo (Hipótesis 2, altura).** Pensábamos que los top 20 fichan jugadores más altos. Separación
**0,044**, rojo: 0,3 cm de diferencia. La altura no entró al modelo.

**Y la que agregamos (Hipótesis 6, edad).** Sola separa poco (0,143, rojo), pero no es una recta: los de 19 años o
menos llegan el 19 % de las veces y el resto alrededor del 10 %. Cruzada con los minutos aparece con fuerza. Entró al
modelo numérica, para que aprenda su forma solo.

**Cómo se construyó el gráfico.** El rendimiento es el puntaje de la Entrega 2: para cada jugador, el promedio de sus 7
estadísticas propias del puesto (minutos, partidos y 5 del rol), cada una pasada a z **dentro de su puesto**, así un
central se compara con centrales. El nivel del club es su coeficiente UEFA en escala logarítmica. Los dos se cortan en
tercios con la misma cantidad de fichajes, y cada celda es el % que fue a un top 20. Quedan afuera los clubes que no están
en el ranking UEFA (no tienen coeficiente). Se calcula sobre la población actual (7.410 fichajes); la Entrega 2 usaba
7.437, antes de sacar el cruce roto, y por eso las cifras cambian en décimas.
""")

# =============================================================================== TALLO 3 · EL MODELO
clubes_test = pd.DataFrame(resumen["clubes_test"]).head(12)
porto = clubes_test.set_index("club").loc["FC Porto"]
st.markdown('<div class="etiqueta">El modelo</div>', unsafe_allow_html=True)
st.header("El modelo encuentra a 4 de cada 10 que llegan a un top 20; los que se le escapan van sobre todo a "
          "Porto, Roma y Benfica, que fichan como clubes medianos")
largo_c = clubes_test.melt(id_vars="club", value_vars=["encontrados", "perdidos"], var_name="qué pasó",
                           value_name="fichajes")
largo_c["qué pasó"] = largo_c["qué pasó"].replace({"encontrados": "el modelo lo encontró",
                                                   "perdidos": "se le escapó"})
barras_c = alt.Chart(largo_c).mark_bar().encode(
    y=alt.Y("club:N", sort=list(clubes_test["club"]), title="club top 20 de destino",
            axis=alt.Axis(labelLimit=220, labelOverlap=False)),
    x=alt.X("fichajes:Q", title="fichajes del test que llegaron a ese club", stack="zero"),
    color=alt.Color("qué pasó:N", scale=alt.Scale(domain=["el modelo lo encontró", "se le escapó"],
                                                 range=[AZUL, CELESTE]),
                    legend=alt.Legend(title=None, orient="top")),
    order=alt.Order("qué pasó:N"),
    tooltip=["club", "qué pasó", "fichajes"])
st.altair_chart(barras_c.properties(height=420), width="stretch")
st.write(
    f"Cada barra son los jugadores del test que fueron a ese club top 20: en azul los que el modelo señaló, en celeste "
    f"los que no. Encuentra {pct(t['recall'])} en total, pero no por igual: al Real Madrid o al Atlético los ve, y del "
    f"Porto se le escapan {int(porto['perdidos'])} de {int(porto['perdidos'] + porto['encontrados'])}. Esos clubes están "
    "en el top 20 por sus resultados en copas europeas, pero compran en Portugal, Brasil o la liga de al lado, jugadores "
    "que se parecen a cualquier otro fichaje de esas ligas. Las columnas dicen quién es el jugador, no quién lo compra.")

with st.expander("Cómo lo sabemos"):
    comp = pd.DataFrame(resumen["comparacion"])
    piso = resumen["piso"]["media"]
    st.markdown(f"""
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
    st.dataframe(tabla.round(3), hide_index=True, width="stretch")
    puntos = alt.Chart(comp).mark_point(filled=True, size=90, color=AZUL).encode(
        x=alt.X("f1:Q", scale=alt.Scale(domain=[0.46, 0.72]), title="f1 macro (media ± desvío)"),
        y=alt.Y("familia:N", sort="-x", title=None))
    errores = alt.Chart(comp).mark_errorbar(color=AZUL).encode(
        x=alt.X("min:Q", scale=alt.Scale(domain=[0.46, 0.72])), x2="max:Q", y=alt.Y("familia:N", sort="-x")
    ).transform_calculate(min="datum.f1 - datum.desvio", max="datum.f1 + datum.desvio")
    linea_piso = alt.Chart(pd.DataFrame({"piso": [piso]})).mark_rule(strokeDash=[4, 3], color="#777").encode(x="piso:Q")
    st.altair_chart((errores + puntos + linea_piso).properties(height=170, title="Eje recortado de 0,46 a 0,72; "
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
que llegaron, encontró {t['vp']}; de {t['vp'] + t['fp']} que señaló, {t['fp']} no llegaron.

**Dónde se equivoca.** Los que se le escapan son los del gráfico de arriba. Los que señala de más tienen perfil de top
20 y terminan **justo debajo**:
""")
    destino = pd.DataFrame({"destino real": list(resumen["fp_destino"]),
                            "falsos positivos": list(resumen["fp_destino"].values()),
                            "negativos": [resumen["vn_destino"][k] for k in resumen["fp_destino"]]})
    largo_d = destino.melt(id_vars="destino real", var_name="grupo", value_name="proporción")
    st.altair_chart(alt.Chart(largo_d).mark_bar().encode(
        x=alt.X("destino real:N", sort=list(resumen["fp_destino"]), title="a dónde fueron en realidad"),
        xOffset="grupo:N",
        y=alt.Y("proporción:Q", axis=alt.Axis(format="%"), title="% del grupo"),
        color=alt.Color("grupo:N", scale=alt.Scale(domain=["falsos positivos", "negativos"], range=[NARANJA, GRIS]),
                        legend=alt.Legend(title=None, orient="top")),
        tooltip=["destino real", "grupo", alt.Tooltip("proporción:Q", format=".0%")]
    ).properties(height=220), width="stretch")
    st.markdown(f"""
El {pct(fp_cerca)} de los falsos positivos fue a un club del puesto 21 al 100 (McTominay al Napoli, De Ketelaere al
Milan): el corte en el puesto 20 no se ve en el perfil del jugador.

**En qué se apoya** (importancia por permutación: cuánto cae el f1 del test al desordenar cada columna):
""")
    imp = pd.DataFrame(resumen["importancia"]).head(8)
    st.altair_chart(alt.Chart(imp).mark_bar(color=AZUL).encode(
        x=alt.X("caida:Q", title="caída del f1 macro"), y=alt.Y("columna:N", sort="-x", title=None),
        tooltip=["columna", alt.Tooltip("caida:Q", format=".3f")]).properties(height=220), width="stretch")
    st.markdown("""
El puesto (que además define contra quién se compara cada estadística), el coeficiente y la liga del club de origen y la
edad. Ninguna es fuga: todas existen antes del fichaje y no usan el destino. Las columnas parecidas se reparten la
importancia, así que una baja no significa que no sirva: sin las 23 estadísticas el f1 cae 0,093.
""")

# =============================================================================== COPA · EXPLORÁ
st.markdown('<div class="etiqueta">Tu turno · Explorá</div>', unsafe_allow_html=True)
st.header(f"Los {miles(resumen['n_ana'])} fichajes, con lo que dijo el modelo de cada uno")
st.write(
    "Empezá por el panorama: cada punto es un fichaje, a la altura de la probabilidad que le dio el modelo. Arriba de la "
    f"línea ({num(resumen['umbral'], 2)}) el modelo dice «llega». Después achicá el universo con los filtros y pasá el mouse "
    "por un punto para ver quién es. Cada fichaje lo predice un modelo que no lo vio: los del entrenamiento salen de la "
    "validación cruzada, los del test del modelo final.")

EJES = {"Edad al fichar": "edad_al_fichaje", "Minutos la temporada anterior": "stat_minutes",
        "Partidos la temporada anterior": "stat_matches", "Coeficiente UEFA del club de origen": "club_origen_coeficiente_uefa",
        "Rendimiento comparado con su puesto": "score_posicion"}
f1c, f2c, f3c, f4c = st.columns([1.2, 1.2, 1, 1.2])
eje = f1c.selectbox("Eje horizontal", list(EJES), index=1)
puesto = f2c.selectbox("Puesto", ["Todos"] + m.ROLES)
origen = f3c.radio("Club de origen", ["Todos", "Liga top 5", "Fuera de las top 5"])
temporadas_sel = f4c.multiselect("Temporadas", sorted(fichajes["temporada_fichaje"].unique()),
                                 default=sorted(fichajes["temporada_fichaje"].unique()))
resultados_sel = st.multiselect("Qué pasó", RESULTADOS, default=RESULTADOS)

vista = fichajes[fichajes["temporada_fichaje"].isin(temporadas_sel) & fichajes["resultado"].isin(resultados_sel)]
if puesto != "Todos":
    vista = vista[vista["grupo_posicion"] == puesto]
if origen != "Todos":
    vista = vista[vista["club_origen_liga_es_top5"] == (origen == "Liga top 5")]
vista = vista.copy()
col_x = EJES[eje]
if col_x == "edad_al_fichaje":  # la edad es entera: un poco de ruido fijo para que no se tapen
    vista["x"] = vista[col_x] + np.random.default_rng(m.SEMILLA).uniform(-0.35, 0.35, len(vista))
else:
    vista["x"] = vista[col_x].fillna(0)
vista["destino"] = vista["club_destino"] + " (puesto " + vista["club_destino_ranking_uefa"].astype(str) + ")"
escala_x = alt.Scale(type="symlog") if col_x in ("club_origen_coeficiente_uefa", "stat_minutes") else alt.Scale(zero=False)

st.caption(f"{miles(len(vista))} fichajes con estos filtros.")
puntos_e = alt.Chart(vista).mark_circle(size=28, opacity=0.65).encode(
    x=alt.X("x:Q", title=eje, scale=escala_x),
    y=alt.Y("proba:Q", title="probabilidad de llegar a un top 20 (según el modelo)", scale=alt.Scale(domain=[0, 1])),
    color=alt.Color("resultado:N", scale=COLOR_RESULTADO,
                    legend=alt.Legend(title=None, orient="top", columns=2, labelLimit=360)),
    tooltip=[alt.Tooltip("nombre:N", title="jugador"), alt.Tooltip("temporada_fichaje:N", title="temporada"),
             alt.Tooltip("grupo_posicion:N", title="puesto"), alt.Tooltip("edad_al_fichaje:Q", title="edad"),
             alt.Tooltip("club_origen:N", title="de"), alt.Tooltip("destino:N", title="a"),
             alt.Tooltip("proba:Q", format=".2f", title="probabilidad"), alt.Tooltip("resultado:N", title="qué pasó"),
             alt.Tooltip("conjunto:N", title="predicho en")])
umbral = alt.Chart(pd.DataFrame({"u": [resumen["umbral"]]})).mark_rule(strokeDash=[5, 4], color="#555").encode(y="u:Q")
st.altair_chart((puntos_e + umbral).properties(height=460).interactive(), width="stretch")
if col_x == "club_origen_coeficiente_uefa":
    st.caption("Los clubes fuera del ranking UEFA aparecen en 0. Escala logarítmica, como en la Entrega 2.")

with st.expander("Ver un fichaje en detalle"):
    elegible = vista.sort_values("proba", ascending=False)
    etiqueta = (elegible["nombre"] + " · " + elegible["temporada_fichaje"] + " · " + elegible["club_origen"] + " → "
                + elegible["club_destino"])
    if len(elegible):
        i = st.selectbox("Fichaje (ordenados por probabilidad)", elegible.index, format_func=lambda k: etiqueta[k])
        f = elegible.loc[i]
        a, b, c = st.columns(3)
        a.metric("Probabilidad según el modelo", num(f["proba"], 2))
        b.metric("El modelo dijo", "llega" if f["proba"] >= resumen["umbral"] else "no llega")
        c.metric("En realidad", "fue a un top 20" if f["es_destino_top_20"] else "no fue a un top 20")
        st.write(f"**{f['nombre']}**, {f['grupo_posicion'].lower()}, {int(f['edad_al_fichaje'])} años. Venía de "
                 f"{f['club_origen']} ({f['club_origen_liga']}) con {miles(f['stat_minutes'])} minutos y "
                 f"fue a {f['club_destino']}, puesto {f['club_destino_ranking_uefa']} de UEFA. Predicho en el "
                 f"{f['conjunto']}.")

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
    valores[s] = cols[j % 4].slider(NOMBRES_STATS.get(s, s), lo, hi, step=paso, key=f"p_{s}")

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
    x=alt.X("p:Q", scale=escala_p, axis=alt.Axis(format=".0%"),
            title=f"probabilidad de llegar a un top 20 · la línea naranja es el umbral ({num(resumen['umbral'], 2)})"))
barra = alt.Chart(pd.DataFrame({"p": [max(proba, 0.004)]})).mark_bar(color=AZUL if llega else GRIS, size=34).encode(
    x=alt.X("p:Q", scale=escala_p))
linea_umbral = alt.Chart(pd.DataFrame({"p": [resumen["umbral"]]})).mark_tick(
    color=NARANJA, thickness=3, size=60).encode(x=alt.X("p:Q", scale=escala_p))
r2.altair_chart((pista + barra + linea_umbral).properties(height=90), width="stretch")
st.caption(f"Para comparar: el {pct(resumen['tasa_top20'], 1)} de todos los fichajes llega a un top 20. Una probabilidad "
           "de 0,25 ya es dos veces y media la tasa general.")

# =============================================================================== CIERRE
with st.expander("Qué cambió desde la Entrega 3"):
    st.markdown("""
Ajustamos las cuatro familias de modelos **antes** de elegir (antes se comparaban con sus valores por defecto), y con eso
el elegido pasó de la regresión logística al random forest. La edad entra **numérica** (antes, en tramos), y agregamos
la hipótesis de la edad a la Entrega 2. La precision subió de 0,34 a 0,39 en el test, y los errores se analizan con
nombres: a dónde fueron los que el modelo señaló de más y a qué clubes van los que se le escapan.
""")
st.caption(f"Ciencia de Datos · UTN FRM · 2026 · Grupo 7 · Fuentes: Transfermarkt, FotMob y UEFA · aplicación construida "
           f"el {resumen['construido']} con app/build_app.py.")
