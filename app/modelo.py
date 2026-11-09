"""El modelo de la Entrega 3, tal cual el notebook: población, columnas, pipeline y partición.

Lo usan build_app.py (para entrenar) y app.py (para cargar el modelo guardado: pickle necesita
encontrar ZPorRol y a_numero en el mismo módulo con el que se guardaron).
"""
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.model_selection import StratifiedGroupKFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, OneHotEncoder, StandardScaler

SEMILLA = 42

# --------------------------------------------------------------------------- población
GRUPOS_POSICION = {
    "Goalkeeper": "Arquero",
    "Centre-Back": "Defensor central", "Defender": "Defensor central",
    "Right-Back": "Lateral", "Left-Back": "Lateral",
    "Defensive Midfield": "Mediocampo defensivo",
    "Central Midfield": "Mediocampo ofensivo", "Attacking Midfield": "Mediocampo ofensivo",
    "Right Midfield": "Mediocampo ofensivo", "Left Midfield": "Mediocampo ofensivo",
    "Midfielder": "Mediocampo ofensivo",
    "Centre-Forward": "Delantero centro", "Second Striker": "Delantero centro",
    "Striker": "Delantero centro",
    "Left Winger": "Delantero extremo", "Right Winger": "Delantero extremo",
}
ROLES = ["Arquero", "Defensor central", "Lateral", "Mediocampo defensivo", "Mediocampo ofensivo",
         "Delantero centro", "Delantero extremo"]


def poblacion(df):
    """Recodifica y filtra como la Sección 1 del notebook. Devuelve (ana, conteos de cada paso)."""
    df = df.copy()
    df["grupo_posicion"] = df["posicion_tm"].map(GRUPOS_POSICION)
    df["stat_goals_conceded_inv"] = -pd.to_numeric(df["stat_goals_conceded"], errors="coerce")
    con_historial = df["tiene_historial"].astype("boolean").fillna(False)
    sin_promocion = df["tipo_operacion"].ne("desconocido")
    arquero_tm = df["posicion_tm"].eq("Goalkeeper")
    arquero_fotmob = df["posicion_fotmob"].str.lower().eq("keeper")
    cruce_roto = arquero_tm != arquero_fotmob
    pasos = [
        ("todos los fichajes del pipeline", len(df)),
        ("con estadísticas de la temporada anterior", int(con_historial.sum())),
        ("sin promociones internas", int((con_historial & sin_promocion).sum())),
        ("sin el cruce roto con FotMob", int((con_historial & sin_promocion & ~cruce_roto).sum())),
    ]
    ana = df[con_historial & sin_promocion & ~cruce_roto].reset_index(drop=True)
    ana["club_origen_liga"] = ana["club_origen_liga"].fillna("sin dato")
    ana["tiene_segunda_nacionalidad"] = ana["nacionalidad_2"].notna()
    return ana, pasos


# --------------------------------------------------------------------------- columnas
BASE = ["stat_minutes", "stat_matches"]
ESPECIFICAS = {
    "Arquero": ["stat_saves", "stat_save_percentage", "stat_goals_conceded_inv",
                "stat_goals_prevented", "stat_high_claims"],
    "Defensor central": ["stat_tackles", "stat_interceptions", "stat_duels_won_%",
                          "stat_aerials_won_%", "stat_recoveries"],
    "Lateral": ["stat_tackles", "stat_interceptions", "stat_duels_won_%",
                "stat_successful_crosses", "stat_recoveries"],
    "Mediocampo defensivo": ["stat_tackles", "stat_interceptions", "stat_duels_won_%",
                              "stat_recoveries", "stat_pass_accuracy"],
    "Mediocampo ofensivo": ["stat_pass_accuracy", "stat_chances_created", "stat_assists",
                             "stat_dribbles_success_rate", "stat_possession_won_final_3rd"],
    "Delantero centro": ["stat_goals", "stat_xg", "stat_shots_on_target",
                          "stat_touches_in_opposition_box", "stat_aerials_won_%"],
    "Delantero extremo": ["stat_goals", "stat_assists", "stat_dribbles_success_rate",
                           "stat_successful_crosses", "stat_big_chances_created"],
}
STATS = BASE + sorted({c for cols in ESPECIFICAS.values() for c in cols})
ORIGEN_LOG = ["club_origen_coeficiente_uefa", "club_origen_pais_coeficiente_uefa"]
SI_NO = ["club_origen_liga_es_top5", "club_origen_es_filial", "club_origen_es_europeo"]
CATEGORICAS = ["grupo_posicion", "temporada_fichaje"]
EDAD = ["edad_al_fichaje"]
COLUMNAS_MODELO = STATS + ORIGEN_LOG + SI_NO + CATEGORICAS + EDAD


# --------------------------------------------------------------------------- pipeline
class ZPorRol(BaseEstimator, TransformerMixin):
    '''Cada stat pasa a z dentro del rol del jugador: (valor - media del rol) / desvío del rol.'''

    def __init__(self, columnas=(), rol="grupo_posicion"):
        self.columnas = columnas
        self.rol = rol

    def fit(self, X, y=None):
        valores = X[list(self.columnas)].apply(pd.to_numeric, errors="coerce")
        self.medias_ = valores.groupby(X[self.rol]).mean()
        self.desvios_ = valores.groupby(X[self.rol]).std().replace(0, np.nan)
        return self

    def transform(self, X):
        valores = X[list(self.columnas)].apply(pd.to_numeric, errors="coerce")
        media = self.medias_.reindex(X[self.rol]).set_index(X.index)
        desvio = self.desvios_.reindex(X[self.rol]).set_index(X.index)
        return ((valores - media) / desvio).rename(columns=lambda c: "z_" + c.removeprefix("stat_"))

    def get_feature_names_out(self, input_features=None):
        return np.array(["z_" + c.removeprefix("stat_") for c in self.columnas])


def a_numero(x):
    return x.astype(float)


def preparar():
    return ColumnTransformer([
        ("stats", Pipeline([("z", ZPorRol(columnas=tuple(STATS))),
                            ("imputar", SimpleImputer(strategy="constant", fill_value=0))]),
         STATS + ["grupo_posicion"]),
        ("edad", Pipeline([("imputar", SimpleImputer(strategy="median")),
                           ("escalar", StandardScaler())]), EDAD),
        ("categoricas", OneHotEncoder(handle_unknown="ignore"), CATEGORICAS),
        ("si_no", FunctionTransformer(a_numero, feature_names_out="one-to-one"), SI_NO),
        ("origen", Pipeline([
            ("log", FunctionTransformer(np.log1p, feature_names_out="one-to-one")),
            ("imputar", SimpleImputer(strategy="constant", fill_value=0, add_indicator=True)),
            ("escalar", StandardScaler())]), ORIGEN_LOG),
    ])


# el elegido en la Sección 5 del notebook: el mejor random forest del barrido, con su umbral
PARAMS_ELEGIDOS = {"max_depth": 10, "max_features": 0.3, "min_samples_leaf": 1}
UMBRAL = 0.25


def modelo_elegido():
    return Pipeline([("preparar", preparar()),
                     ("clasificador", RandomForestClassifier(n_estimators=300, n_jobs=-1,
                                                             random_state=SEMILLA, **PARAMS_ELEGIDOS))])


def particion(ana):
    """La misma partición por jugador del notebook: el primer pedazo de 5 es el test."""
    y = ana["es_destino_top_20"].astype(int)
    jugador = ana["jugador_tm_id"]
    corte = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMILLA)
    idx_train, idx_test = next(corte.split(ana, y, groups=jugador))
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=SEMILLA)
    return idx_train, idx_test, y, jugador, cv
