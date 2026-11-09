"""Construye todo lo que usa la aplicación a partir del dataset que publica el pipeline.

    py app/build_app.py                      # usa la última salida del DAG (include/output/)
    py app/build_app.py --datos otro.csv     # o un CSV que le pases

Entrena el modelo elegido en la Entrega 3 con la misma semilla y deja en app/datos/:
    modelo.joblib       el pipeline entrenado (preparar + random forest)
    fichajes_app.csv    cada fichaje con lo que dijo el modelo (para «Explorá»)
    clubes.csv          los clubes de origen conocidos (para «Probá el modelo»)
    rangos.csv          mínimo, mediana y máximo de cada stat por rol en el entrenamiento
    resumen.json        los números y tablas de la portada y del tallo

Si el pipeline actualiza los datos, correr esto de nuevo actualiza la aplicación.
"""
import argparse
import glob
import json
import os
import sys
import time
import warnings
from datetime import date

warnings.filterwarnings("ignore")
AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)

import joblib  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from sklearn.base import clone  # noqa: E402
from sklearn.dummy import DummyClassifier  # noqa: E402
from sklearn.ensemble import HistGradientBoostingClassifier, RandomForestClassifier  # noqa: E402
from sklearn.inspection import permutation_importance  # noqa: E402
from sklearn.linear_model import LogisticRegression  # noqa: E402
from sklearn.metrics import f1_score, precision_score, recall_score  # noqa: E402
from sklearn.model_selection import ParameterGrid, cross_val_predict, cross_val_score  # noqa: E402
from sklearn.pipeline import Pipeline  # noqa: E402
from sklearn.tree import DecisionTreeClassifier  # noqa: E402

import modelo as m  # noqa: E402

UMBRALES = np.round(np.arange(0.05, 0.80, 0.05), 2)
FAMILIAS = {
    "regresión logística": (LogisticRegression(max_iter=3000), {"C": [0.01, 0.1, 1, 10]}),
    "árbol de decisión": (DecisionTreeClassifier(random_state=m.SEMILLA),
                          {"max_depth": [3, 5, 8, 12], "min_samples_leaf": [1, 20, 50]}),
    "random forest": (RandomForestClassifier(n_estimators=300, n_jobs=-1, random_state=m.SEMILLA),
                      {"max_depth": [None, 10], "min_samples_leaf": [1, 5, 20],
                       "max_features": ["sqrt", 0.3]}),
    "gradient boosting": (HistGradientBoostingClassifier(random_state=m.SEMILLA),
                          {"learning_rate": [0.03, 0.1], "max_iter": [100, 300],
                           "max_leaf_nodes": [15, 31]}),
}
FUGA = ["club_destino", "club_destino_id", "club_destino_pais", "club_destino_ranking_uefa",
        "club_destino_coeficiente_uefa", "traspaso_domestico", "salto_ranking_uefa",
        "sube_de_categoria", "coste_fichaje_eur", "tipo_operacion"]


def ultimo_dataset():
    raiz = os.path.dirname(AQUI)
    salidas = sorted(glob.glob(os.path.join(raiz, "include", "output", "fichajes_*.csv")))
    if salidas:
        return salidas[-1]
    respaldo = os.path.join(raiz, "include", "frozen", "ultimo_ok.csv")
    if os.path.exists(respaldo):
        return respaldo
    sys.exit("No encontré el dataset: corré el DAG o pasá --datos ruta.csv")


def pipeline_con(clasificador):
    return Pipeline([("preparar", m.preparar()), ("clasificador", clasificador)])


def por_umbral(modelo, X, y, grupos, cv):
    pedazos = list(cv.split(X, y, groups=grupos))
    proba = cross_val_predict(modelo, X, y, groups=grupos, cv=pedazos, method="predict_proba", n_jobs=-1)[:, 1]
    filas = []
    for u in UMBRALES:
        f1s, ps, rs = [], [], []
        for _, v in pedazos:
            real, dice = y.iloc[v], proba[v] >= u
            f1s.append(f1_score(real, dice, average="macro"))
            ps.append(precision_score(real, dice, zero_division=0))
            rs.append(recall_score(real, dice))
        filas.append({"umbral": float(u), "f1": np.mean(f1s), "desvio": np.std(f1s),
                      "precision": np.mean(ps), "recall": np.mean(rs)})
    return pd.DataFrame(filas).set_index("umbral"), proba


def score_posicion(ana):
    """El score de la Entrega 2: promedio de las z de las 7 stats propias del rol, dentro del rol."""
    score = pd.Series(np.nan, index=ana.index)
    for rol, propias in m.ESPECIFICAS.items():
        filas = ana["grupo_posicion"].eq(rol)
        v = ana.loc[filas, m.BASE + propias].apply(pd.to_numeric, errors="coerce")
        score[filas] = ((v - v.mean()) / v.std()).mean(axis=1)
    return score


def main():
    t0 = time.time()
    parser = argparse.ArgumentParser()
    parser.add_argument("--datos", default=None)
    ruta = parser.parse_args().datos or ultimo_dataset()
    print(f"datos: {ruta}")
    df = pd.read_csv(ruta, low_memory=False)
    ana, pasos = m.poblacion(df)
    idx_train, idx_test, y, jugador, cv = m.particion(ana)
    X = ana[m.COLUMNAS_MODELO]
    X_train, X_test, y_train, y_test = X.iloc[idx_train], X.iloc[idx_test], y.iloc[idx_train], y.iloc[idx_test]
    g_train = jugador.iloc[idx_train]
    print(f"población: {len(ana):,} fichajes; entrenamiento {len(X_train):,}, test {len(X_test):,}")

    # el piso
    f1_piso = cross_val_score(DummyClassifier(strategy="most_frequent", random_state=m.SEMILLA),
                              X_train, y_train, groups=g_train, cv=cv, scoring="f1_macro")

    # el barrido: cada familia con su grilla, todas con validación cruzada por jugador y su mejor umbral
    barrido = []
    for familia, (base, grilla) in FAMILIAS.items():
        for params in ParameterGrid(grilla):
            t, _ = por_umbral(pipeline_con(clone(base).set_params(**params)), X_train, y_train, g_train, cv)
            u = t["f1"].idxmax()
            barrido.append({"familia": familia, "params": params, "umbral": u, **t.loc[u].to_dict()})
        print(f"  barrido {familia}: listo ({time.time() - t0:.0f}s)")
    barrido = pd.DataFrame(barrido)
    mejores = barrido.loc[barrido.groupby("familia")["f1"].idxmax()].sort_values("f1", ascending=False)
    elegido = mejores.set_index("familia").loc["random forest"]
    assert elegido["params"] == m.PARAMS_ELEGIDOS and elegido["umbral"] == m.UMBRAL, elegido

    # el elegido: por umbral (para la sección del modelo) y sus probabilidades fuera de muestra
    tabla_umbral, proba_oof = por_umbral(m.modelo_elegido(), X_train, y_train, g_train, cv)

    # el modelo final, una sola vez sobre el test
    final = m.modelo_elegido().fit(X_train, y_train)
    proba_test = final.predict_proba(X_test)[:, 1]
    pred_test = (proba_test >= m.UMBRAL).astype(int)

    # cada fichaje con lo que dijo un modelo que no lo vio
    ana["conjunto"] = "entrenamiento"
    ana.loc[idx_test, "conjunto"] = "test"
    ana["proba"] = np.nan
    ana.loc[idx_train, "proba"] = proba_oof
    ana.loc[idx_test, "proba"] = proba_test
    ana["dice_top20"] = ana["proba"] >= m.UMBRAL
    real = ana["es_destino_top_20"].astype(bool)
    ana["resultado"] = np.select(
        [real & ana["dice_top20"], real & ~ana["dice_top20"], ~real & ana["dice_top20"]],
        ["acierto: llegó y lo señaló", "se le escapó: llegó y no lo señaló", "falso positivo: lo señaló y no llegó"],
        "negativo: no llegó y no lo señaló")

    # errores del test
    test = ana.loc[idx_test]
    rt = test["es_destino_top_20"].astype(bool)
    vp, fp, fn = test[rt & test["dice_top20"]], test[~rt & test["dice_top20"]], test[rt & ~test["dice_top20"]]
    vn = test[~rt & ~test["dice_top20"]]

    def puesto(g):
        grupos = pd.cut(g["club_destino_ranking_uefa"], [20, 50, 100, 1000],
                        labels=["puesto 21 a 50", "puesto 51 a 100", "puesto 101 o más"])
        return grupos.value_counts(normalize=True).sort_index()

    clubes_test = pd.DataFrame({"encontrados": vp["club_destino"].value_counts(),
                                "perdidos": fn["club_destino"].value_counts()}).fillna(0).astype(int)
    clubes_test = clubes_test.loc[clubes_test.sum(axis=1).sort_values(ascending=False).index]

    # en qué se apoya: importancia por permutación, con nuestro umbral
    def f1_con_umbral(modelo, Xp, yp):
        return f1_score(yp, modelo.predict_proba(Xp)[:, 1] >= m.UMBRAL, average="macro")

    pi = permutation_importance(final, X_test, y_test, n_repeats=10, scoring=f1_con_umbral,
                                random_state=m.SEMILLA, n_jobs=-1)
    importancia = pd.Series(pi.importances_mean, index=m.COLUMNAS_MODELO).sort_values(ascending=False)
    print(f"  modelo final e importancia: listo ({time.time() - t0:.0f}s)")

    # lo que encontramos: club de origen × rendimiento (Hipótesis 5)
    ana["score_posicion"] = score_posicion(ana)
    log_coef = np.log1p(ana["club_origen_coeficiente_uefa"])
    nivel_origen = pd.qcut(log_coef, 3, labels=["bajo", "medio", "alto"])
    nivel_score = pd.qcut(ana["score_posicion"], 3, labels=["bajo", "medio", "alto"])
    cruce = ana.assign(origen=nivel_origen, rendimiento=nivel_score).dropna(subset=["origen", "rendimiento"])
    h5 = (cruce.groupby(["origen", "rendimiento"], observed=True)["es_destino_top_20"]
          .agg(tasa=lambda s: s.astype(float).mean(), n="size").reset_index())

    # ------------------------------------------------------------------ archivos
    salida = os.path.join(AQUI, "datos")
    os.makedirs(salida, exist_ok=True)
    joblib.dump(final, os.path.join(salida, "modelo.joblib"), compress=3)

    columnas_app = ["nombre", "temporada_fichaje", "grupo_posicion", "edad_al_fichaje", "club_origen",
                    "club_origen_liga", "club_origen_liga_es_top5", "club_origen_coeficiente_uefa",
                    "stat_minutes", "stat_matches", "club_destino", "club_destino_ranking_uefa",
                    "es_destino_top_20", "conjunto", "proba", "resultado", "score_posicion"]
    ana[columnas_app].to_csv(os.path.join(salida, "fichajes_app.csv"), index=False)

    # columnas del modelo de cada fichaje, para «partir de un jugador real»
    ana[["nombre", "temporada_fichaje", "club_origen", "club_destino"] + m.COLUMNAS_MODELO].to_csv(
        os.path.join(salida, "fichajes_modelo.csv"), index=False)

    clubes = (ana.sort_values("temporada_fichaje")
              .groupby("club_origen")
              .agg(fichajes=("club_origen", "size"),
                   club_origen_coeficiente_uefa=("club_origen_coeficiente_uefa", "last"),
                   club_origen_pais_coeficiente_uefa=("club_origen_pais_coeficiente_uefa", "last"),
                   club_origen_liga=("club_origen_liga", "last"),
                   club_origen_liga_es_top5=("club_origen_liga_es_top5", "last"),
                   club_origen_es_filial=("club_origen_es_filial", "last"),
                   club_origen_es_europeo=("club_origen_es_europeo", "last"))
              .reset_index().sort_values("club_origen"))
    clubes.to_csv(os.path.join(salida, "clubes.csv"), index=False)

    filas_rango = []
    for rol in m.ROLES:
        sub = X_train[X_train["grupo_posicion"] == rol]
        for c in m.STATS:
            v = pd.to_numeric(sub[c], errors="coerce").dropna()
            if len(v):
                filas_rango.append({"rol": rol, "stat": c, "min": v.min(), "mediana": v.median(), "max": v.max()})
    pd.DataFrame(filas_rango).to_csv(os.path.join(salida, "rangos.csv"), index=False)

    f1_test = f1_score(y_test, pred_test, average="macro")
    resumen = {
        "construido": date.today().isoformat(),
        "datos": os.path.basename(ruta),
        "pasos": pasos,
        "fuga": FUGA,
        "n_ana": len(ana), "n_jugadores": int(jugador.nunique()), "positivos": int(y.sum()),
        "tasa_top20": float(y.mean()),
        "n_train": len(X_train), "n_test": len(X_test),
        "por_temporada": (ana.groupby("temporada_fichaje")["es_destino_top_20"]
                          .agg(fichajes="size", top20=lambda s: int(s.sum())).reset_index()
                          .to_dict(orient="records")),
        "piso": {"media": float(f1_piso.mean()), "desvio": float(f1_piso.std())},
        "comparacion": [{"familia": r.familia, "params": {k: (None if v is None else v) for k, v in r.params.items()},
                         "umbral": float(r.umbral), "f1": float(r.f1), "desvio": float(r.desvio),
                         "precision": float(r.precision), "recall": float(r.recall)}
                        for r in mejores.itertuples()],
        "n_combinaciones": len(barrido),
        "umbral": m.UMBRAL, "params": m.PARAMS_ELEGIDOS,
        "por_umbral": tabla_umbral.reset_index().to_dict(orient="records"),
        "test": {"f1": float(f1_test), "precision": float(precision_score(y_test, pred_test)),
                 "recall": float(recall_score(y_test, pred_test)),
                 "accuracy": float((pred_test == y_test).mean()),
                 "accuracy_siempre_no": float(1 - y_test.mean()),
                 "vp": len(vp), "fp": len(fp), "fn": len(fn), "vn": len(vn)},
        "fp_destino": {k: float(v) for k, v in puesto(fp).items()},
        "vn_destino": {k: float(v) for k, v in puesto(vn).items()},
        "clubes_test": clubes_test.reset_index(names="club").to_dict(orient="records"),
        "importancia": [{"columna": k, "caida": float(v)} for k, v in importancia.head(12).items()],
        "h5": h5.astype({"origen": str, "rendimiento": str}).to_dict(orient="records"),
    }
    with open(os.path.join(salida, "resumen.json"), "w", encoding="utf-8") as f:
        json.dump(resumen, f, ensure_ascii=False, indent=1, default=lambda o: o.item() if hasattr(o, "item") else str(o))

    print(f"listo en {time.time() - t0:.0f}s · f1 test {f1_test:.3f} · precision {resumen['test']['precision']:.3f} "
          f"· recall {resumen['test']['recall']:.3f}")


if __name__ == "__main__":
    main()
