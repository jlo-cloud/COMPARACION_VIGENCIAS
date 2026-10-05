"""
Compara las versiones de las tablas de valor que se han liquidado.

Cada corrida de comparacion_vigencia.py deja su detalle en
output/versiones/<VERSION>/COMPARACION_VIGENCIA_DETALLE.parquet. Con dos o mas
versiones guardadas, este modulo arma un libro con:

  - Resumen por categoria: T1_RESIDENCIAL, T3_COMERCIAL... una fila por version.
  - Resumen por tabla: cada TABLA_ORIGEN, una fila por version.
  - Detalle: una fila por construccion, con la tabla usada, el VM2 y el avaluo
    de cada version lado a lado, y cuanto cambia el VM2 de una version a la
    siguiente.
  - Diccionario.

Todo en catastral, como el detalle de cada version.

Uso:  python src/comparacion_versiones.py
"""
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
CARPETA_VERSIONES = RAIZ / "output" / "versiones"
CARPETA_SALIDA = RAIZ / "results" / "COMPARACION_VERSIONES"
NOMBRE_DETALLE = "COMPARACION_VIGENCIA_DETALLE.parquet"

LLAVE = ["ID_PREDIO", "CONSTRUCCION_ID"]
# Lo que es igual en todas las versiones: sale de la mas reciente que lo traiga.
FIJAS = ["NUMERO_PREDIAL_NACIONAL", "COMUNA", "GRUPO_COMUNAS", "ESTRPRED",
         "USO_LADM", "CONDICION", "TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA",
         "PUNTCONS", "AREA_CONST", "VM2_CAT_VIGENCIA", "AVALUO_CAT_VIGENCIA"]
# Lo que cambia con la version.
POR_VERSION = ["TABLA_VALOR", "VM2_CAT_LIQ", "VARIACION_CAT_PCT",
               "AVALUO_CAT_LIQ", "VARIACION_AVALUO_CAT_PCT"]


def orden_version(v: str) -> tuple:
    """V2 antes que V10: por el numero, no por el texto."""
    m = re.search(r"(\d+)", v)
    return (int(m.group(1)) if m else 0, v)


def versiones_disponibles() -> list:
    """Las versiones que tienen detalle guardado, de la mas vieja a la nueva."""
    if not CARPETA_VERSIONES.is_dir():
        return []
    return sorted((p.name for p in CARPETA_VERSIONES.iterdir()
                   if (p / NOMBRE_DETALLE).exists()), key=orden_version)


def categoria(tabla: pd.Series) -> pd.Series:
    """T3_COMERCIAL_021 -> T3_COMERCIAL."""
    return tabla.astype(str).str.split("_").str[:2].str.join("_")


def _leer(version: str) -> pd.DataFrame:
    ruta = CARPETA_VERSIONES / version / NOMBRE_DETALLE
    import pyarrow.parquet as pq
    hay = set(pq.ParquetFile(ruta).schema_arrow.names)
    cols = [c for c in LLAVE + FIJAS + POR_VERSION if c in hay]
    d = pd.read_parquet(ruta, columns=cols)
    for c in LLAVE:
        d[c] = d[c].astype(str)
    d["VERSION"] = version
    return d


def resumen(largo: pd.DataFrame, por: str) -> pd.DataFrame:
    """Una fila por grupo y version: conteo, medianas y como se mueve."""
    g = largo.groupby([por, "VERSION"], observed=True, sort=False)
    t = pd.DataFrame({
        "CONSTRUCCIONES": g.size(),
        "VM2_CAT_MEDIANA_2026": g["VM2_CAT_VIGENCIA"].median(),
        "VM2_CAT_MEDIANA_2027": g["VM2_CAT_LIQ"].median(),
        "VARIACION_MEDIANA_PCT": g["VARIACION_CAT_PCT"].median(),
        "BAJAN_PCT": g["VARIACION_CAT_PCT"].apply(lambda s: (s < 0).mean() * 100),
        "SUBEN_PCT": g["VARIACION_CAT_PCT"].apply(lambda s: (s > 0).mean() * 100),
    }).reset_index()
    t["_ORDEN"] = t["VERSION"].map(lambda v: orden_version(v)[0])
    return (t.sort_values([por, "_ORDEN"]).drop(columns="_ORDEN")
             .round(2).reset_index(drop=True))


def comparar_versiones(versiones: list | None = None) -> str | None:
    """Arma el libro de versiones; devuelve su ruta, o None si hay menos de 2."""
    versiones = versiones or versiones_disponibles()
    if len(versiones) < 2:
        print(f"   Comparacion de versiones: hay {len(versiones)} version(es) "
              f"guardada(s) en {CARPETA_VERSIONES}; hacen falta dos.")
        return None
    print(f"\n   Comparando versiones: {', '.join(versiones)}")

    partes = {v: _leer(v) for v in versiones}
    largo = pd.concat(partes.values(), ignore_index=True)
    largo["CATEGORIA"] = categoria(largo["TABLA_ORIGEN"])

    # --- Detalle ancho: una fila por construccion ---------------------------
    # Las columnas fijas salen de la version mas nueva que tenga la fila.
    fijas = (pd.concat([partes[v] for v in reversed(versiones)])
               .drop_duplicates(LLAVE)[LLAVE + [c for c in FIJAS
                                                if c in largo.columns]])
    ancho = fijas.set_index(LLAVE)
    for v in versiones:
        cols = [c for c in POR_VERSION if c in partes[v].columns]
        ancho = ancho.join(partes[v].set_index(LLAVE)[cols]
                           .add_suffix(f"_{v}"), how="left")
    # De cada version a la siguiente: cuanto se mueve el VM2 de 2027.
    for a, b in zip(versiones, versiones[1:]):
        va, vb = ancho[f"VM2_CAT_LIQ_{a}"], ancho[f"VM2_CAT_LIQ_{b}"]
        ancho[f"DIF_VM2_{b}_vs_{a}"] = vb - va
        ancho[f"VARIACION_VM2_{b}_vs_{a}_PCT"] = ((vb / va - 1) * 100).round(2)
        ancho[f"CAMBIA_TABLA_{b}_vs_{a}"] = (
            ancho[f"TABLA_VALOR_{b}"].astype(str)
            != ancho[f"TABLA_VALOR_{a}"].astype(str)).astype(int)
    ancho = ancho.reset_index()
    ancho.insert(ancho.columns.get_loc("TABLA_ORIGEN"), "CATEGORIA",
                 categoria(ancho["TABLA_ORIGEN"]))

    por_cat = resumen(largo, "CATEGORIA")
    por_tabla = resumen(largo, "TABLA_ORIGEN")

    dic = [("VERSION", "Version de las tablas de valor con que se liquido"),
           ("CATEGORIA", "Familia de la tabla: T1_RESIDENCIAL, T3_COMERCIAL..."),
           ("VM2_CAT_VIGENCIA", "VM2 catastral de la vigencia 2026 (igual en todas las versiones)"),
           ("AVALUO_CAT_VIGENCIA", "Avaluo catastral 2026 del predio"),
           ("TABLA_VALOR_<V>", "Columna del Excel de tablas de donde salio el VM2 en esa version"),
           ("VM2_CAT_LIQ_<V>", "VM2 catastral 2027 con esa version"),
           ("VARIACION_CAT_PCT_<V>", "Variacion del VM2 2027 con esa version contra 2026 (%)"),
           ("AVALUO_CAT_LIQ_<V>", "Avaluo catastral 2027 del predio con esa version"),
           ("VARIACION_AVALUO_CAT_PCT_<V>", "Variacion del avaluo con esa version contra 2026 (%)"),
           ("DIF_VM2_<B>_vs_<A>", "VM2 2027 con la version B menos con la A"),
           ("VARIACION_VM2_<B>_vs_<A>_PCT", "Cuanto cambia el VM2 2027 de la version A a la B (%)"),
           ("CAMBIA_TABLA_<B>_vs_<A>", "1 si la columna de tabla usada cambio entre A y B"),
           ("(vacio en una version)", "La construccion no entro a la comparacion con esa version")]
    dic = pd.DataFrame(dic, columns=["VARIABLE", "DESCRIPCION"])

    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    fecha = datetime.now().strftime("%Y%m%d")
    ruta = CARPETA_SALIDA / f"COMPARACION_VERSIONES_{'_'.join(versiones)}_{fecha}.xlsx"
    print("   Escribiendo la comparacion de versiones a Excel (puede tardar)...")
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as xw:
        libro = xw.book
        f_tit = libro.add_format({"bold": True, "bg_color": "#1F4E78",
                                  "font_color": "white", "border": 1,
                                  "text_wrap": True, "valign": "vcenter"})
        f_pesos = libro.add_format({"num_format": "$ #,##0"})
        f_pct = libro.add_format({"num_format": "0.00"})
        for nombre, t in (("Resumen por categoria", por_cat),
                          ("Resumen por tabla", por_tabla),
                          ("Detalle", ancho), ("Diccionario", dic)):
            t.to_excel(xw, sheet_name=nombre, index=False)
            h = xw.sheets[nombre]
            h.freeze_panes(1, 0)
            h.autofilter(0, 0, len(t), len(t.columns) - 1)
            for i, col in enumerate(t.columns):
                h.write(0, i, col, f_tit)
                if col.startswith(("VM2", "AVALUO", "DIF_")):
                    fmt, ancho_col = f_pesos, 18
                elif "PCT" in col:
                    fmt, ancho_col = f_pct, 14
                elif nombre == "Diccionario":
                    fmt, ancho_col = None, (34 if i == 0 else 80)
                else:
                    fmt, ancho_col = None, max(12, min(len(col) + 2, 34))
                h.set_column(i, i, ancho_col, fmt)
    print(f"   Comparacion de versiones: {ruta}")
    print(f"     Detalle: {len(ancho):,} construcciones x {len(versiones)} versiones")
    return str(ruta)


if __name__ == "__main__":
    comparar_versiones()
