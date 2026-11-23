"""Ejercicio comparativo: institucionales en zona residencial con la tabla
residencial que les tocaria.

Toma las construcciones URBANAS que se liquidan con una tabla institucional
(T5 educativo, T6 salud, T7 servicios, T8 culto) y cuya ZHF es de tipologia
residencial (011 a 016), y les calcula el VM2 con la columna residencial que
les tocaria con la misma regla de las residenciales urbanas:
    7 comunas  -> T1_RESIDENCIAL_7C_<tipologia>
    10 comunas -> T1_RESIDENCIAL_10C_COND_9_<tipologia> si la condicion es 9,
                  T1_RESIDENCIAL_10C_COND_0_<tipologia> si no
en la fila de su puntaje. Lo compara con el VM2 que les da hoy su tabla
institucional y con el vigente 2026 (comercial).

No cambia la liquidacion: es un ejercicio aparte. Deja
    results/EJERCICIOS/EJERCICIO_INSTITUCIONAL_RESIDENCIAL_<fecha>.xlsx
        (con identificadores, uso interno)
    output/versiones/<VERSION>/EJERCICIO_INSTITUCIONAL_RESIDENCIAL.parquet
        (sin identificadores, lo lee la app)

    python src/ejercicio_institucional.py
"""
import os
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from comparacion_vigencia import CONFIG, factor_comercial  # noqa: E402
from consolidar_tablas import tabla_valor_vigente  # noqa: E402

RAIZ = Path(__file__).resolve().parent.parent
TABLAS_INSTITUCIONALES = {"T5_INSTITUCIONAL_ED": "T5 Educativo", "T6_INSTITUCIONAL_SA": "T6 Salud",
                          "T7_INSTITUCIONAL_SER": "T7 Servicios", "T8_INSTITUCIONAL_IG": "T8 Culto"}
TIPOLOGIAS = ["011", "012", "013", "014", "015", "016"]


def columna_residencial(comuna: pd.Series, condicion: pd.Series, tipologia: pd.Series) -> pd.Series:
    """La columna residencial que le toca, con la regla de las residenciales
    urbanas: 7C en las 7 comunas; en las 10, COND_9 si la condicion es 9 y
    COND_0 si no."""
    c = comuna.astype(str).str.strip().str.zfill(2)
    t = tipologia.astype(str).str.strip()
    cond9 = pd.to_numeric(condicion, errors="coerce").fillna(0).astype(int) == 9
    grupo = np.where(c.isin(CONFIG["comunas_7"]), "7C",
                     np.where(cond9, "10C_COND_9", "10C_COND_0"))
    return pd.Series("T1_RESIDENCIAL_" + pd.Series(grupo, index=c.index) + "_" + t, index=c.index)

PARQUET_APP = Path(CONFIG["parquet_publico"]).parent / "EJERCICIO_INSTITUCIONAL_RESIDENCIAL.parquet"

# La informacion de la construccion que va al Excel, en este orden.
COLUMNAS_EXCEL = [
    "ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "COMUNA", "DIREPRED",
    "ESTRPRED", "CONDICION", "USO_LADM", "DESTINOCONS", "ZHF", "TIPOLOGIA_ZHF",
    "PUNTCONS", "ACONCONS", "AREA_CONST", "TPISCONS", "ANOCONST",
    "TABLA_INSTITUCIONAL", "GRUPO_RESIDENCIAL", "COLUMNA_RESIDENCIAL",
    "VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL",
    "DIF_RESIDENCIAL_VS_INSTITUCIONAL", "VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT",
    "VAR_INSTITUCIONAL_VS_VIGENCIA_PCT", "VAR_RESIDENCIAL_VS_VIGENCIA_PCT",
    "VALORCONS_COM_VIGENCIA", "VALORCONS_COM_INSTITUCIONAL", "VALORCONS_COM_RESIDENCIAL",
]
DICCIONARIO = {
    "TABLA_INSTITUCIONAL": "Tabla institucional con que se liquida hoy (T5 a T8, bloque 17C)",
    "GRUPO_RESIDENCIAL": "7C (las 7 comunas), 10C COND 9 o 10C COND 0 (las 10 comunas, segun la condicion)",
    "COLUMNA_RESIDENCIAL": "Columna residencial que le tocaria, con la regla de las residenciales urbanas: "
                           "T1_RESIDENCIAL_7C_<tipologia> en las 7 comunas; en las 10, "
                           "T1_RESIDENCIAL_10C_COND_9_<tipologia> si la condicion es 9 y COND_0 si no",
    "VM2_COM_VIGENCIA": "VM2 vigente 2026, comercial: VALORCONS / area / factor de la comuna (0,7 actualizadas, 0,6 las demas)",
    "VM2_COM_INSTITUCIONAL": "VM2 2027 con su tabla institucional (comercial), el de la liquidacion",
    "VM2_COM_RESIDENCIAL": "VM2 2027 si se liquidara con COLUMNA_RESIDENCIAL, por su puntaje (comercial)",
    "DIF_RESIDENCIAL_VS_INSTITUCIONAL": "VM2 residencial menos VM2 institucional",
    "VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT": "Variacion del VM2 residencial frente al institucional (%)",
    "VAR_INSTITUCIONAL_VS_VIGENCIA_PCT": "Variacion del VM2 institucional frente al vigente 2026 (%)",
    "VAR_RESIDENCIAL_VS_VIGENCIA_PCT": "Variacion del VM2 residencial frente al vigente 2026 (%)",
    "VALORCONS_COM_VIGENCIA": "Valor total de la construccion vigente 2026, comercial",
    "VALORCONS_COM_INSTITUCIONAL": "Valor total 2027 con la tabla institucional (VM2 x area)",
    "VALORCONS_COM_RESIDENCIAL": "Valor total 2027 con la residencial (VM2 x area)",
}


def vm2_residencial(puntcons: pd.Series, columnas: pd.Series) -> pd.Series:
    """El VM2 comercial de cada columna residencial, en la fila de su puntaje."""
    conv = pd.read_excel(tabla_valor_vigente(), sheet_name="CONVENCIONALES")
    conv = conv.set_index(conv.columns[0])
    conv.columns = [str(c).strip() for c in conv.columns]
    faltan = sorted(set(columnas) - set(conv.columns))
    if faltan:
        raise ValueError(f"Columnas residenciales que no estan en el consolidado: {faltan}")
    largo = conv[sorted(set(columnas))].stack()
    claves = pd.MultiIndex.from_arrays(
        [pd.to_numeric(puntcons, errors="coerce").fillna(0).astype(int), columnas.astype(str)])
    return pd.Series(largo.reindex(claves).to_numpy(), index=puntcons.index)


def en_ejercicio(d: pd.DataFrame) -> pd.Series:
    """Las filas del ejercicio: urbanas, con tabla T5 a T8 y ZHF 011 a 016."""
    return ((pd.to_numeric(d["COMUNA"], errors="coerce") <= 22)
            & d["TABLA_ORIGEN"].astype(str).isin(TABLAS_INSTITUCIONALES)
            & d["TIPOLOGIA_ZHF"].astype(str).isin(TIPOLOGIAS))


# Las columnas que el ejercicio agrega al Excel de detalle (vacias fuera de el).
COLUMNAS_INST_RES = ["COLUMNA_INST_RES", "VM2_COM_INST_RES", "VM2_CAT_INST_RES",
                     "VALORCONS_COM_INST_RES", "VALORCONS_CAT_INST_RES",
                     "DIF_VM2_COM_INST_RES", "VARIACION_COM_INST_RES_PCT"]


def columnas_inst_res(det: pd.DataFrame) -> pd.DataFrame:
    """Para el detalle (comparacion): las columnas *_INST_RES de las filas del
    ejercicio. VM2_COM_LIQ es el institucional y VM2_COM_VIGENCIA el vigente."""
    out = pd.DataFrame(index=det.index, columns=COLUMNAS_INST_RES, dtype=object)
    m = en_ejercicio(det)
    if not m.any():
        return out
    d = det.loc[m]
    col = columna_residencial(d["COMUNA"], d["CONDICION"], d["TIPOLOGIA_ZHF"])
    vm2 = vm2_residencial(d["PUNTCONS"], col)
    area = pd.to_numeric(d["AREA_CONST"], errors="coerce")
    factor = CONFIG["factor_catastral"]
    vig = pd.to_numeric(d["VM2_COM_VIGENCIA"], errors="coerce")
    out.loc[m, "COLUMNA_INST_RES"] = col
    out.loc[m, "VM2_COM_INST_RES"] = vm2
    out.loc[m, "VM2_CAT_INST_RES"] = vm2 * factor
    out.loc[m, "VALORCONS_COM_INST_RES"] = vm2 * area
    out.loc[m, "VALORCONS_CAT_INST_RES"] = vm2 * area * factor
    out.loc[m, "DIF_VM2_COM_INST_RES"] = vm2 - pd.to_numeric(d["VM2_COM_LIQ"], errors="coerce")
    out.loc[m, "VARIACION_COM_INST_RES_PCT"] = ((vm2 / vig.where(vig > 0) - 1) * 100).round(6)
    for c in COLUMNAS_INST_RES[1:]:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    return out


def filas_no_comparadas(det: pd.DataFrame) -> pd.DataFrame:
    """Las construcciones del ejercicio que NO estan en la comparacion (su predio
    tiene anexo o quedo incompleto), con la forma del detalle: sus datos, el
    valor 2026, el institucional 2027 y las columnas *_INST_RES. El avaluo del
    predio no aplica (va vacio). Marcadas COMPARADA_INST_RES = 0."""
    from comparacion_vigencia import grupo_comunas
    e = armar()
    e = e[~e["CONSTRUCCION_ID"].astype(str).isin(det["CONSTRUCCION_ID"].astype(str))].copy()
    if e.empty:
        return pd.DataFrame(columns=det.columns)
    factor = CONFIG["factor_catastral"]
    area = pd.to_numeric(e["AREA_CONST"], errors="coerce")
    f_com = factor_comercial(e).to_numpy()
    out = pd.DataFrame(index=e.index)
    for c in det.columns:                          # lo que no aplica, vacio
        out[c] = np.nan if pd.api.types.is_numeric_dtype(det[c]) else ""
    for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "COMUNA",
              "USO_LADM", "ZHF", "TIPOLOGIA_ZHF"):
        if c in out.columns:
            out[c] = e[c].astype(str)
    for c in ("ESTRPRED", "CONDICION", "PUNTCONS", "ACONCONS", "AREA_CONST"):
        if c in out.columns:
            out[c] = pd.to_numeric(e[c], errors="coerce")
    out["ZONA"] = "URBANO"
    out["GRUPO_COMUNAS"] = grupo_comunas(e)
    out["TABLA_ORIGEN"] = e["TABLA_INSTITUCIONAL"]
    out["TABLA_VALOR"] = e["TABLA_INSTITUCIONAL"] + "_17C"
    out["F_COMERCIAL"] = f_com
    vig_com, liq_com = e["VM2_COM_VIGENCIA"], e["VM2_COM_INSTITUCIONAL"]
    out["VM2_COM_VIGENCIA"], out["VM2_COM_LIQ"] = vig_com, liq_com
    out["VM2_CAT_VIGENCIA"], out["VM2_CAT_LIQ"] = vig_com * f_com, liq_com * factor
    out["VALORCONS_COM_VIGENCIA"] = e["VALORCONS_COM_VIGENCIA"]
    out["VALORCONS_COM_LIQ"] = e["VALORCONS_COM_INSTITUCIONAL"]
    out["VALORCONS_CAT_VIGENCIA"] = e["VALORCONS_COM_VIGENCIA"] * f_com
    out["VALORCONS_CAT_LIQ"] = e["VALORCONS_COM_INSTITUCIONAL"] * factor
    for b in ("CAT", "COM"):
        out[f"DIF_VALORCONS_{b}"] = out[f"VALORCONS_{b}_LIQ"] - out[f"VALORCONS_{b}_VIGENCIA"]
        out[f"VARIACION_VALORCONS_{b}_PCT"] = (out[f"VALORCONS_{b}_LIQ"]
                                               / out[f"VALORCONS_{b}_VIGENCIA"] - 1) * 100
        out[f"DIF_{b}_ABS"] = out[f"VM2_{b}_LIQ"] - out[f"VM2_{b}_VIGENCIA"]
        out[f"VARIACION_{b}_PCT"] = (out[f"VM2_{b}_LIQ"] / out[f"VM2_{b}_VIGENCIA"] - 1) * 100
    # Las del ejercicio, con la residencial que le toca
    out = out.drop(columns=[c for c in COLUMNAS_INST_RES if c in out.columns])
    out = out.join(columnas_inst_res(out))
    out["COMPARADA_INST_RES"] = 0
    out["EN_CERO"], out["MOTIVO_CERO"] = 0, ""
    return out.reset_index(drop=True)


def armar(liq: pd.DataFrame | None = None) -> pd.DataFrame:
    """Las construcciones del ejercicio con los tres VM2."""
    if liq is None:
        import pyarrow.parquet as pq
        ruta = CONFIG["parquet_liquidacion"]
        hay = set(pq.ParquetFile(ruta).schema_arrow.names)
        usar = [c for c in COLUMNAS_EXCEL + ["TABLA_ORIGEN", "VM2", "VALORCONS"] if c in hay]
        liq = pd.read_parquet(ruta, columns=usar)
    d = liq[(pd.to_numeric(liq["COMUNA"], errors="coerce") <= 22)
            & liq["TABLA_ORIGEN"].astype(str).isin(TABLAS_INSTITUCIONALES)
            & liq["TIPOLOGIA_ZHF"].astype(str).isin(TIPOLOGIAS)].copy()
    d["COMUNA"] = d["COMUNA"].astype(str).str.zfill(2)
    d["TABLA_INSTITUCIONAL"] = d["TABLA_ORIGEN"].astype(str)
    d["COLUMNA_RESIDENCIAL"] = columna_residencial(d["COMUNA"], d["CONDICION"], d["TIPOLOGIA_ZHF"])
    d["GRUPO_RESIDENCIAL"] = d["COLUMNA_RESIDENCIAL"].str.extract(r"T1_RESIDENCIAL_(.+)_\d{3}$")[0] \
        .str.replace("_", " ")

    # VM2 residencial: la columna que le toca, en la fila de su puntaje
    d["VM2_COM_RESIDENCIAL"] = vm2_residencial(d["PUNTCONS"], d["COLUMNA_RESIDENCIAL"])
    d["VM2_COM_INSTITUCIONAL"] = pd.to_numeric(d["VM2"], errors="coerce")

    area = pd.to_numeric(d["AREA_CONST"], errors="coerce")
    d["VALORCONS_COM_VIGENCIA"] = pd.to_numeric(d["VALORCONS"], errors="coerce") / factor_comercial(d).to_numpy()
    d["VM2_COM_VIGENCIA"] = d["VALORCONS_COM_VIGENCIA"] / area.where(area > 0)
    d["VALORCONS_COM_INSTITUCIONAL"] = d["VM2_COM_INSTITUCIONAL"] * area
    d["VALORCONS_COM_RESIDENCIAL"] = d["VM2_COM_RESIDENCIAL"] * area
    d["DIF_RESIDENCIAL_VS_INSTITUCIONAL"] = d["VM2_COM_RESIDENCIAL"] - d["VM2_COM_INSTITUCIONAL"]

    def var(a, b):
        return ((a / b.where(b > 0) - 1) * 100).round(2)
    d["VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT"] = var(d["VM2_COM_RESIDENCIAL"], d["VM2_COM_INSTITUCIONAL"])
    d["VAR_INSTITUCIONAL_VS_VIGENCIA_PCT"] = var(d["VM2_COM_INSTITUCIONAL"], d["VM2_COM_VIGENCIA"])
    d["VAR_RESIDENCIAL_VS_VIGENCIA_PCT"] = var(d["VM2_COM_RESIDENCIAL"], d["VM2_COM_VIGENCIA"])
    # Solo lo que tiene valor en los dos lados (la app no muestra ceros)
    return d[(d["VM2_COM_INSTITUCIONAL"] > 0) & (d["VM2_COM_RESIDENCIAL"] > 0)].reset_index(drop=True)


def resumen(d: pd.DataFrame) -> pd.DataFrame:
    """Por tabla institucional y tipologia, con total por tabla y total general."""
    def fila(s):
        return {"CONSTRUCCIONES": len(s), "PREDIOS": s["ID_PREDIO"].nunique() if "ID_PREDIO" in s else np.nan,
                "ÁREA (mediana, m²)": pd.to_numeric(s["AREA_CONST"], errors="coerce").median(),
                "VM2 VIGENCIA 2026 (mediana)": s["VM2_COM_VIGENCIA"].median(),
                "VM2 INSTITUCIONAL 2027 (mediana)": s["VM2_COM_INSTITUCIONAL"].median(),
                "VM2 RESIDENCIAL 2027 (mediana)": s["VM2_COM_RESIDENCIAL"].median(),
                "VAR. RESIDENCIAL VS INSTITUCIONAL % (mediana)": s["VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT"].median(),
                "VAR. INSTITUCIONAL VS 2026 % (mediana)": s["VAR_INSTITUCIONAL_VS_VIGENCIA_PCT"].median(),
                "VAR. RESIDENCIAL VS 2026 % (mediana)": s["VAR_RESIDENCIAL_VS_VIGENCIA_PCT"].median(),
                "% RESIDENCIAL MAYOR": (s["DIF_RESIDENCIAL_VS_INSTITUCIONAL"] > 0).mean() * 100}
    filas = []
    for tabla, nombre in TABLAS_INSTITUCIONALES.items():
        s_t = d[d["TABLA_INSTITUCIONAL"] == tabla]
        for tip in TIPOLOGIAS:
            s = s_t[s_t["TIPOLOGIA_ZHF"].astype(str) == tip]
            if len(s):
                filas.append({"TABLA": nombre, "TIPOLOGIA": tip, **fila(s)})
        if len(s_t):
            filas.append({"TABLA": f"TOTAL {nombre}", "TIPOLOGIA": "", **fila(s_t)})
    filas.append({"TABLA": "TOTAL", "TIPOLOGIA": "", **fila(d)})
    return pd.DataFrame(filas)


def generar() -> tuple[str, str]:
    d = armar()
    fecha = datetime.now().strftime("%Y%m%d")
    carpeta = RAIZ / "results" / "EJERCICIOS"
    carpeta.mkdir(parents=True, exist_ok=True)
    xlsx = carpeta / f"EJERCICIO_INSTITUCIONAL_RESIDENCIAL_{fecha}.xlsx"
    res = resumen(d)
    leeme = pd.DataFrame({"LEEME": [
        "EJERCICIO COMPARATIVO: INSTITUCIONALES EN ZONA RESIDENCIAL CON LA TABLA RESIDENCIAL QUE LES TOCARIA",
        f"Liquidacion: {Path(CONFIG['parquet_liquidacion']).name} · Tablas: {Path(tabla_valor_vigente()).name}",
        "",
        "Que entra: construcciones urbanas (17 comunas) que se liquidan con T5, T6, T7 o T8 (institucionales)",
        "y cuya ZHF es de tipologia residencial (011 a 016).",
        "Ejercicio: el VM2 que les daria la columna residencial que les toca, con la regla de las residenciales",
        "urbanas: T1_RESIDENCIAL_7C_<tipologia> en las 7 comunas (02, 03, 04, 08, 17, 19, 22); en las 10 comunas,",
        "T1_RESIDENCIAL_10C_COND_9_<tipologia> si la condicion es 9 (PH) y T1_RESIDENCIAL_10C_COND_0_<tipologia> si no.",
        "Se busca en la fila de su puntaje y se compara con el VM2 de su tabla institucional y con el vigente 2026.",
        "Todo en valores comerciales.",
        "No cambia la liquidacion. ARCHIVO CON IDENTIFICADORES: uso interno.",
    ]})
    with pd.ExcelWriter(xlsx, engine="xlsxwriter") as w:
        leeme.to_excel(w, sheet_name="LEEME", index=False)
        res.to_excel(w, sheet_name="RESUMEN", index=False)
        d[[c for c in COLUMNAS_EXCEL if c in d.columns]].to_excel(w, sheet_name="CONSTRUCCIONES", index=False)
        pd.DataFrame({"COLUMNA": list(DICCIONARIO), "DESCRIPCION": list(DICCIONARIO.values())}
                     ).to_excel(w, sheet_name="DICCIONARIO", index=False)
        libro = w.book
        miles = libro.add_format({"num_format": "#,##0"})
        pct = libro.add_format({"num_format": '+0.00"%";-0.00"%"'})
        w.sheets["LEEME"].set_column(0, 0, 110)
        r = w.sheets["RESUMEN"]
        r.set_column(0, 0, 22); r.set_column(1, 1, 10); r.set_column(2, 3, 16, miles)
        r.set_column(4, 4, 16, libro.add_format({"num_format": "#,##0.0"}))
        r.set_column(5, 7, 18, miles)
        r.set_column(8, 10, 18, pct); r.set_column(11, 11, 14, libro.add_format({"num_format": "0.0"}))
        c = w.sheets["CONSTRUCCIONES"]
        cols = [x for x in COLUMNAS_EXCEL if x in d.columns]
        for j, col in enumerate(cols):
            if col.startswith(("VM2", "VALORCONS", "DIF")):
                c.set_column(j, j, 18, miles)
            elif col.endswith("_PCT"):
                c.set_column(j, j, 16, pct)
            else:
                c.set_column(j, j, 16)
        c.autofilter(0, 0, len(d), len(cols) - 1)
        c.freeze_panes(1, 3)
        w.sheets["DICCIONARIO"].set_column(0, 0, 38)
        w.sheets["DICCIONARIO"].set_column(1, 1, 110)

    # Para la app: sin identificadores y redondeado, como los demas recortes
    app = d[["COMUNA", "TABLA_INSTITUCIONAL", "TIPOLOGIA_ZHF", "GRUPO_RESIDENCIAL", "USO_LADM",
             "PUNTCONS", "AREA_CONST",
             "VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL"]].copy()
    for col in ("VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL"):
        app[col] = (app[col] / 100).round() * 100
    app = app.sort_values(["TABLA_INSTITUCIONAL", "TIPOLOGIA_ZHF", "VM2_COM_INSTITUCIONAL"],
                          ignore_index=True)
    app.to_parquet(PARQUET_APP, index=False)
    print(res.round(2).to_string(index=False))
    print(f"Excel: {xlsx}\nApp:   {PARQUET_APP} ({len(app):,} filas)")
    return str(xlsx), str(PARQUET_APP)


if __name__ == "__main__":
    generar()
