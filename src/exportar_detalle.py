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

from comparacion_vigencia import (CONFIG, COLUMNAS_EXCEL_DETALLE,
                                  anexos_y_parqueaderos, crear_rango_variacion,
                                  exportar_detalle_excel, grupo_comunas)


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
    n_anx = int((filas["TABLA_ORIGEN"] == "T10_ANEXOS").sum())
    n_parq = len(filas) - n_anx
    det = pd.concat([det[[c for c in COLUMNAS_EXCEL_DETALLE if c in det.columns]],
                     filas[[c for c in COLUMNAS_EXCEL_DETALLE if c in det.columns]]],
                    ignore_index=True)

    print(f"Escribiendo {len(det):,} filas a Excel: construcciones, "
          f"{n_anx:,} anexos y {n_parq:,} parqueaderos (tarda unos minutos)...")
    inicio = time.time()
    exportar_detalle_excel(det, ruta, a.muestra)
    print(f"Listo: {ruta}")
    print(f"   {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
