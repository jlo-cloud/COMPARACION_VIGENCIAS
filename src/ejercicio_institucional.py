"""Ejercicio comparativo: institucionales en zona residencial con la tabla
residencial 7C.

Toma las construcciones URBANAS que se liquidan con una tabla institucional
(T5 educativo, T6 salud, T7 servicios, T8 culto) y cuya ZHF es de tipologia
residencial (011 a 016), y les calcula el VM2 con la columna
T1_RESIDENCIAL_7C_<su tipologia> en la fila de su puntaje. Lo compara con el
VM2 que les da hoy su tabla institucional y con el vigente 2026 (comercial).

No cambia la liquidacion: es un ejercicio aparte. Deja
    results/EJERCICIOS/EJERCICIO_INSTITUCIONAL_RESIDENCIAL_7C_<fecha>.xlsx
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
COLUMNA_RESIDENCIAL = "T1_RESIDENCIAL_7C_{}"
PARQUET_APP = Path(CONFIG["parquet_publico"]).parent / "EJERCICIO_INSTITUCIONAL_RESIDENCIAL.parquet"

# La informacion de la construccion que va al Excel, en este orden.
COLUMNAS_EXCEL = [
    "ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "COMUNA", "DIREPRED",
    "ESTRPRED", "CONDICION", "USO_LADM", "DESTINOCONS", "ZHF", "TIPOLOGIA_ZHF",
    "PUNTCONS", "ACONCONS", "AREA_CONST", "TPISCONS", "ANOCONST",
    "TABLA_INSTITUCIONAL", "COLUMNA_RESIDENCIAL",
    "VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL_7C",
    "DIF_RESIDENCIAL_VS_INSTITUCIONAL", "VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT",
    "VAR_INSTITUCIONAL_VS_VIGENCIA_PCT", "VAR_RESIDENCIAL_VS_VIGENCIA_PCT",
    "VALORCONS_COM_VIGENCIA", "VALORCONS_COM_INSTITUCIONAL", "VALORCONS_COM_RESIDENCIAL_7C",
]
DICCIONARIO = {
    "TABLA_INSTITUCIONAL": "Tabla institucional con que se liquida hoy (T5 a T8, bloque 17C)",
    "COLUMNA_RESIDENCIAL": "Columna residencial 7C que se usa en el ejercicio: T1_RESIDENCIAL_7C_<tipologia de su ZHF>",
    "VM2_COM_VIGENCIA": "VM2 vigente 2026, comercial: VALORCONS / area / factor de la comuna (0,7 actualizadas, 0,6 las demas)",
    "VM2_COM_INSTITUCIONAL": "VM2 2027 con su tabla institucional (comercial), el de la liquidacion",
    "VM2_COM_RESIDENCIAL_7C": "VM2 2027 si se liquidara con la residencial 7C de su tipologia, por su puntaje (comercial)",
    "DIF_RESIDENCIAL_VS_INSTITUCIONAL": "VM2 residencial 7C menos VM2 institucional",
    "VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT": "Variacion del VM2 residencial 7C frente al institucional (%)",
    "VAR_INSTITUCIONAL_VS_VIGENCIA_PCT": "Variacion del VM2 institucional frente al vigente 2026 (%)",
    "VAR_RESIDENCIAL_VS_VIGENCIA_PCT": "Variacion del VM2 residencial 7C frente al vigente 2026 (%)",
    "VALORCONS_COM_VIGENCIA": "Valor total de la construccion vigente 2026, comercial",
    "VALORCONS_COM_INSTITUCIONAL": "Valor total 2027 con la tabla institucional (VM2 x area)",
    "VALORCONS_COM_RESIDENCIAL_7C": "Valor total 2027 con la residencial 7C (VM2 x area)",
}


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
    d["COLUMNA_RESIDENCIAL"] = d["TIPOLOGIA_ZHF"].astype(str).map(COLUMNA_RESIDENCIAL.format)

    # VM2 residencial 7C: la columna de su tipologia, en la fila de su puntaje
    conv = pd.read_excel(tabla_valor_vigente(), sheet_name="CONVENCIONALES")
    conv = conv.set_index(conv.columns[0])
    conv.columns = [str(c).strip() for c in conv.columns]
    largo = conv[[COLUMNA_RESIDENCIAL.format(t) for t in TIPOLOGIAS]].stack()
    claves = pd.MultiIndex.from_arrays([pd.to_numeric(d["PUNTCONS"], errors="coerce").fillna(0).astype(int),
                                        d["COLUMNA_RESIDENCIAL"]])
    d["VM2_COM_RESIDENCIAL_7C"] = largo.reindex(claves).to_numpy()
    d["VM2_COM_INSTITUCIONAL"] = pd.to_numeric(d["VM2"], errors="coerce")

    area = pd.to_numeric(d["AREA_CONST"], errors="coerce")
    d["VALORCONS_COM_VIGENCIA"] = pd.to_numeric(d["VALORCONS"], errors="coerce") / factor_comercial(d).to_numpy()
    d["VM2_COM_VIGENCIA"] = d["VALORCONS_COM_VIGENCIA"] / area.where(area > 0)
    d["VALORCONS_COM_INSTITUCIONAL"] = d["VM2_COM_INSTITUCIONAL"] * area
    d["VALORCONS_COM_RESIDENCIAL_7C"] = d["VM2_COM_RESIDENCIAL_7C"] * area
    d["DIF_RESIDENCIAL_VS_INSTITUCIONAL"] = d["VM2_COM_RESIDENCIAL_7C"] - d["VM2_COM_INSTITUCIONAL"]

    def var(a, b):
        return ((a / b.where(b > 0) - 1) * 100).round(2)
    d["VAR_RESIDENCIAL_VS_INSTITUCIONAL_PCT"] = var(d["VM2_COM_RESIDENCIAL_7C"], d["VM2_COM_INSTITUCIONAL"])
    d["VAR_INSTITUCIONAL_VS_VIGENCIA_PCT"] = var(d["VM2_COM_INSTITUCIONAL"], d["VM2_COM_VIGENCIA"])
    d["VAR_RESIDENCIAL_VS_VIGENCIA_PCT"] = var(d["VM2_COM_RESIDENCIAL_7C"], d["VM2_COM_VIGENCIA"])
    # Solo lo que tiene valor en los dos lados (la app no muestra ceros)
    return d[(d["VM2_COM_INSTITUCIONAL"] > 0) & (d["VM2_COM_RESIDENCIAL_7C"] > 0)].reset_index(drop=True)


def resumen(d: pd.DataFrame) -> pd.DataFrame:
    """Por tabla institucional y tipologia, con total por tabla y total general."""
    def fila(s):
        return {"CONSTRUCCIONES": len(s), "PREDIOS": s["ID_PREDIO"].nunique() if "ID_PREDIO" in s else np.nan,
                "ÁREA (mediana, m²)": pd.to_numeric(s["AREA_CONST"], errors="coerce").median(),
                "VM2 VIGENCIA 2026 (mediana)": s["VM2_COM_VIGENCIA"].median(),
                "VM2 INSTITUCIONAL 2027 (mediana)": s["VM2_COM_INSTITUCIONAL"].median(),
                "VM2 RESIDENCIAL 7C 2027 (mediana)": s["VM2_COM_RESIDENCIAL_7C"].median(),
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
    xlsx = carpeta / f"EJERCICIO_INSTITUCIONAL_RESIDENCIAL_7C_{fecha}.xlsx"
    res = resumen(d)
    leeme = pd.DataFrame({"LEEME": [
        "EJERCICIO COMPARATIVO: INSTITUCIONALES EN ZONA RESIDENCIAL CON LA TABLA RESIDENCIAL 7C",
        f"Liquidacion: {Path(CONFIG['parquet_liquidacion']).name} · Tablas: {Path(tabla_valor_vigente()).name}",
        "",
        "Que entra: construcciones urbanas (17 comunas) que se liquidan con T5, T6, T7 o T8 (institucionales)",
        "y cuya ZHF es de tipologia residencial (011 a 016).",
        "Ejercicio: el VM2 que les daria la columna T1_RESIDENCIAL_7C_<su tipologia> en la fila de su puntaje,",
        "comparado con el VM2 de su tabla institucional y con el vigente 2026. Todo en valores comerciales.",
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
    app = d[["COMUNA", "TABLA_INSTITUCIONAL", "TIPOLOGIA_ZHF", "USO_LADM", "PUNTCONS", "AREA_CONST",
             "VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL_7C"]].copy()
    for col in ("VM2_COM_VIGENCIA", "VM2_COM_INSTITUCIONAL", "VM2_COM_RESIDENCIAL_7C"):
        app[col] = (app[col] / 100).round() * 100
    app = app.sort_values(["TABLA_INSTITUCIONAL", "TIPOLOGIA_ZHF", "VM2_COM_INSTITUCIONAL"],
                          ignore_index=True)
    app.to_parquet(PARQUET_APP, index=False)
    print(res.round(2).to_string(index=False))
    print(f"Excel: {xlsx}\nApp:   {PARQUET_APP} ({len(app):,} filas)")
    return str(xlsx), str(PARQUET_APP)


if __name__ == "__main__":
    generar()
