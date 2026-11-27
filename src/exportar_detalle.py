"""
Escribe el DETALLE_LIQUIDADOS_<version>_<fecha>.xlsx a partir del parquet que
dejo la ultima corrida del main, sin volver a liquidar.

El main ya no escribe este Excel (cuesta ~5 min); guarda los mismos datos en
output/versiones/<VERSION>/COMPARACION_VIGENCIA_DETALLE.parquet. Este script
los pasa a Excel cuando se necesitan para entregar o revisar a mano.

Uso:  python src/exportar_detalle.py
      python src/exportar_detalle.py --muestra 5000   (solo una muestra)
"""
import argparse
import os
import time
from datetime import datetime

import pandas as pd

import reglas_rurales

from comparacion_vigencia import (CONFIG, COLUMNAS_EXCEL_DETALLE,
                                  anexos_y_parqueaderos, crear_rango_variacion,
                                  exportar_detalle_excel, grupo_comunas)


def filas_en_cero(columnas) -> pd.DataFrame:
    """Lo que quedo en $ 0 en la liquidacion, con la forma del detalle: sus
    datos, el valor vigente y el motivo. Lo numerico que no aplica, en 0."""
    from post_inconsistencias import motivo
    from comparacion_vigencia import factor_comercial
    import pyarrow.parquet as pq
    ruta = CONFIG["parquet_liquidacion"]
    hay = set(pq.ParquetFile(ruta).schema_arrow.names)
    usar = [c for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "ESTRPRED",
                        "USO_LADM", "CONDICION", "TABLA_ORIGEN", "TABLA_RURAL", "MOTIVO_RURAL",
                        "ZHF", "TIPOLOGIA_ZHF", "ESPECIAL", "PUNTCONS", "ANOCONST", "ACONCONS",
                        "AREA_CONST", "VALORCONS", "VALOANEX", "VM2", "LIQ_PARQUEADERO")
            if c in hay]
    liq = pd.read_parquet(ruta, columns=usar)
    valor = pd.to_numeric(liq["VM2"], errors="coerce").fillna(0)
    if "LIQ_PARQUEADERO" in liq.columns:
        valor = valor.where(valor > 0, pd.to_numeric(liq["LIQ_PARQUEADERO"],
                                                     errors="coerce").fillna(0))
    z = liq[valor <= 0].copy()
    z["COMUNA"] = z["COMUNA"].astype(str).str.strip().str.zfill(2)
    out = pd.DataFrame(index=z.index)
    for c in columnas:
        out[c] = 0
    for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "USO_LADM",
              "TABLA_ORIGEN", "ZHF", "TIPOLOGIA_ZHF"):
        if c in z.columns:
            out[c] = z[c].astype(str).replace({"nan": "", "None": "", "<NA>": ""})
    for c in ("ESTRPRED", "CONDICION", "ESPECIAL", "PUNTCONS", "ANOCONST", "ACONCONS", "AREA_CONST"):
        if c in z.columns:
            out[c] = pd.to_numeric(z[c], errors="coerce").fillna(0)
    out["ZONA"] = (pd.to_numeric(z["COMUNA"], errors="coerce") > 22).map(
        {True: "RURAL", False: "URBANO"})
    out["GRUPO_COMUNAS"] = grupo_comunas(out)
    out["TABLA_VALOR"] = (z["TABLA_RURAL"].fillna("").astype(str)
                          if "TABLA_RURAL" in z.columns else "")
    # El valor vigente: el de la construccion, o el del anexo si es anexo.
    vig = pd.to_numeric(z.get("VALORCONS"), errors="coerce").fillna(0)
    if "VALOANEX" in z.columns:
        vig = vig.where(vig > 0, pd.to_numeric(z["VALOANEX"], errors="coerce").fillna(0))
    out["VALORCONS_CAT_VIGENCIA"] = vig
    out["VALORCONS_COM_VIGENCIA"] = vig / factor_comercial(z).to_numpy()
    for c in ("VARIACION_VALORCONS_CAT_PCT", "VARIACION_VALORCONS_COM_PCT",
              "VARIACION_CAT_PCT", "VARIACION_COM_PCT",
              "VARIACION_AVALUO_CAT_PCT", "VARIACION_AVALUO_COM_PCT"):
        out[c] = float("nan")              # sin valor 2027 no hay variacion
    sin_comp = crear_rango_variacion(None, CONFIG["vigencia_base"])
    for c in ("RANGO_VM2", "RANGO_ANEXO", "RANGO_CONS_TOTAL", "RANGO_TERR", "RANGO_AVALUO"):
        out[c] = sin_comp
    for c in ("ZHF_ANTERIOR", "TIPOLOGIA_ZHF_ANTERIOR", "CAMBIO_TIPOLOGIA",
              "USO_ZHF", "CLAVE", "ORIGEN_TERRENO_LIQ"):
        out[c] = ""
    out["EN_CERO"] = 1
    out["MOTIVO_CERO"] = motivo(z).to_numpy()
    return out.reset_index(drop=True)


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--muestra", type=int, default=None,
                   help="filas del Excel, repartidas entre las tablas "
                        "(por defecto salen todas)")
    a = p.parse_args()

    origen = CONFIG["parquet_detalle"]
    if not os.path.exists(origen):
        raise SystemExit(f"No existe {origen}. Corra primero: python src/main.py")

    hecho = datetime.fromtimestamp(os.path.getmtime(origen))
    print(f"Leyendo {origen}")
    print(f"   (lo dejo la corrida del {hecho:%Y-%m-%d %H:%M})")
    det = pd.read_parquet(origen)
    # En el Excel la actividad de la ZHF se llama USO_ZHF
    det = det.rename(columns={"ACTIVIDAD_ECONOMICA": "USO_ZHF"})

    # El mismo nombre que le ponia el main.
    sufijo = "" if CONFIG["base_valor"] == "CATASTRAL" else "_COMERCIAL"
    ruta = os.path.join(
        CONFIG["carpeta_results"],
        f"DETALLE_LIQUIDADOS_{CONFIG['version_tablas']}{sufijo}_"
        f"{datetime.now():%Y%m%d}.xlsx")

    # Los anexos (T10) y parqueaderos (T12) no pasan por la comparacion
    # principal -no tienen puntaje y se valoran por clave o por cupo-, pero van
    # en la MISMA hoja Detalle, de la misma corrida: lo que comparten (predio,
    # comuna, uso, area, valor por m2 y valor total, en las dos bases) en su
    # columna, y lo que no tienen (puntaje, ZHF, terreno, avaluo...) en 0.
    # Solo los que tienen valor en la tabla, como en la app.
    anx = anexos_y_parqueaderos(con_identificadores=True)
    anx = anx[anx["CON_VALOR"] == 1]
    filas = pd.DataFrame(index=anx.index)
    for c in COLUMNAS_EXCEL_DETALLE:
        # En 0 lo numerico; el texto (ZHF, rangos...) queda vacio.
        texto = (c in det.columns
                 and not pd.api.types.is_numeric_dtype(det[c]))
        filas[c] = "" if texto else 0
    for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "USO_LADM",
              "TABLA_ORIGEN", "CLAVE"):
        filas[c] = anx[c].astype(str)
    filas["TABLA_VALOR"] = anx["TABLA_ORIGEN"].map(
        {"T10_ANEXOS": "T10_NO_CONVENCIONAL_17C",
         "T12_PARQUEADEROS": "T12_PARQUEADEROS"})
    filas["GRUPO_COMUNAS"] = grupo_comunas(filas)
    filas["ZONA"] = anx["ZONA"].astype(str)
    filas["AREA_CONST"] = anx["AREA"]
    for b in ("CAT", "COM"):
        vig, liq = anx[f"VALOR_{b}_VIGENCIA"], anx[f"VALOR_{b}_LIQ"]
        filas[f"VALORCONS_{b}_VIGENCIA"], filas[f"VALORCONS_{b}_LIQ"] = vig, liq
        filas[f"DIF_VALORCONS_{b}"] = liq - vig
        filas[f"VARIACION_VALORCONS_{b}_PCT"] = anx[f"VARIACION_VALOR_{b}_PCT"]
        filas[f"VM2_{b}_VIGENCIA"] = anx[f"VM2_{b}_VIGENCIA"]
        filas[f"VM2_{b}_LIQ"] = anx[f"VM2_{b}_LIQ"]
        filas[f"DIF_{b}_ABS"] = anx[f"VM2_{b}_LIQ"] - anx[f"VM2_{b}_VIGENCIA"]
        filas[f"VARIACION_{b}_PCT"] = anx[f"VARIACION_VM2_{b}_PCT"]
    # Los rangos, con la misma regla del detalle (crear_rango_variacion, sobre
    # el catastral). El del anexo, solo en las filas de anexo; terreno y
    # avaluo no aplican y quedan en '19. Sin comparacion', como en las
    # construcciones que no tienen con que comparar.
    base = CONFIG["vigencia_base"]
    rango = lambda s: s.apply(lambda v: crear_rango_variacion(v, base))
    filas["RANGO_VM2"] = rango(anx["VARIACION_VM2_CAT_PCT"])
    filas["RANGO_CONS_TOTAL"] = rango(anx["VARIACION_VALOR_CAT_PCT"])
    sin_comparacion = crear_rango_variacion(None, base)
    filas["RANGO_ANEXO"] = rango(anx["VARIACION_VALOR_CAT_PCT"]).where(
        anx["TABLA_ORIGEN"] == "T10_ANEXOS", sin_comparacion)
    for c in ("RANGO_TERR", "RANGO_AVALUO"):
        filas[c] = sin_comparacion
    filas = filas.fillna(0)
    filas["EN_CERO"], filas["MOTIVO_CERO"] = 0, ""
    n_anx = int((filas["TABLA_ORIGEN"] == "T10_ANEXOS").sum())
    n_parq = len(filas) - n_anx
    det["EN_CERO"], det["MOTIVO_CERO"] = 0, ""
    cero = filas_en_cero(det.columns)
    cols_det = [c for c in COLUMNAS_EXCEL_DETALLE if c in det.columns]
    det = pd.concat([det[cols_det], filas[cols_det], cero[cols_det]], ignore_index=True)
    det["CORREGIMIENTO"] = reglas_rurales.corregimiento(det["COMUNA"]).to_numpy()
    # Edad de la construccion en 2027 (anio de construccion valido: 1800 a 2027)
    anio = pd.to_numeric(det.get("ANOCONST"), errors="coerce")
    det["EDAD"] = (2027 - anio).where(anio.between(1800, 2027))

    # Lo rural con su ZHF en TODAS las filas: los anexos y parqueaderos llegan
    # sin ZHF (se arman desde su propia comparacion) y las filas en $ 0 sin
    # uso. La ZHF es la del predio; de ella salen el uso de la ZHF rural, la
    # clasificacion del suelo y el area de manejo.
    rural = det["ZONA"].astype(str).eq("RURAL")
    zhf_txt = det["ZHF"].astype(str).str.strip()
    falta = rural & ~zhf_txt.str.fullmatch(r"\d{12}")
    if falta.any():
        zhf_predio = (pd.read_parquet(CONFIG["parquet_liquidacion"], columns=["ID_PREDIO", "ZHF"])
                      .astype(str).drop_duplicates("ID_PREDIO").set_index("ID_PREDIO")["ZHF"])
        det.loc[falta, "ZHF"] = det.loc[falta, "ID_PREDIO"].astype(str).map(zhf_predio).fillna("").to_numpy()
    zhf_r = det.loc[rural, "ZHF"].astype(str)
    # En lo rural USO_ZHF es el uso de la ZHF rural ('12 Residencial_tipo2')
    det.loc[rural, "USO_ZHF"] = reglas_rurales.actividad_rural(zhf_r).to_numpy()
    det.loc[rural, "CLASIFICACION_SUELO"] = reglas_rurales.clasificacion_suelo(zhf_r).to_numpy()
    det.loc[rural, "AREA_MANEJO"] = reglas_rurales.area_manejo(zhf_r).to_numpy()
    print(f"   + {len(cero):,} construcciones en $ 0 (EN_CERO = 1), como en "
          f"post-inconsistencias")

    # Urbano y rural en la MISMA hoja Detalle: la columna ZONA los separa
    # (el R de resumenes filtra ZONA = URBANO). Aparte solo va la cobertura
    # rural, que es un conteo y no filas de construccion.
    rural = det["ZONA"].astype(str).eq("RURAL")
    extras = {}       # sin hoja de cobertura rural: solo Detalle y Diccionario

    print(f"Escribiendo {len(det):,} filas a Excel ({int((~rural).sum()):,} urbanas y "
          f"{int(rural.sum()):,} rurales, columna ZONA; tarda unos minutos)...")
    inicio = time.time()
    exportar_detalle_excel(det, ruta, a.muestra, extras=extras)
    print(f"Listo: {ruta}")
    print(f"   {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
