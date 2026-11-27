"""
Escribe LIQUIDACION_COMPLETA_<version>_<fecha>.xlsx: TODA la liquidacion de la
ultima corrida, una fila por construccion, sin el filtro de la comparacion.

El DETALLE_LIQUIDADOS deja por fuera lo que no es comparable con 2026 (sobre
todo las construcciones de predios con anexo). Este libro no compara nada:
trae lo que se liquido, con su tabla, su VM2 y su valor 2027, y el valor que
tiene hoy en la base como referencia. Lo que quedo en $ 0 va con su motivo,
el mismo de post-inconsistencias.

Lleva identificadores (ID de predio, numero predial): NO sale del equipo ni
va al repositorio (results/ esta en .gitignore).

Uso:  python src/exportar_liquidacion.py
"""
import os
import time
from datetime import datetime

import numpy as np
import pandas as pd

import reglas_rurales
from comparacion_vigencia import CONFIG, factor_comercial, grupo_comunas
from post_inconsistencias import motivo, motivo_cero

COLUMNAS = {
    "ID_PREDIO": "Identificador del predio",
    "NUMERO_PREDIAL_NACIONAL": "Numero predial nacional",
    "COMUNA": "Comuna o corregimiento",
    "CORREGIMIENTO": "Solo rural: nombre del corregimiento",
    "ZONA": "URBANO (comunas 1 a 22) o RURAL (51 a 65)",
    "GRUPO_COMUNAS": "Grupo de comunas de las tablas (7C, 10C...)",
    "CLASIFICACION_SUELO": "Rural: primer digito de la ZHF",
    "AREA_MANEJO": "Rural: digitos 2 y 3 de la ZHF",
    "ZHF": "Zona homogenea fisica del corte de predios",
    "TIPOLOGIA_ZHF": "Ultimos 3 digitos de la ZHF (urbano)",
    "ESTRPRED": "Estrato del predio",
    "CONDICION": "Condicion del predio (posicion 22 del numero predial)",
    "TIPO_CONSTRUCCION": "CONVENCIONAL o NO CONVENCIONAL (anexo)",
    "DESTINOCONS": "Destino de la construccion (codigo homologado)",
    "DESTANEX": "Destino del anexo (codigo homologado)",
    "USO_LADM": "Uso LADM",
    "TIPOANEXO": "Tipo del anexo",
    "TIPO_PARQ": "Parqueadero Sencillo (<= 50 m2) o Doble",
    "PUNTCONS": "Puntaje de la construccion",
    "ANOCONST": "Año de construcción",
    "EDAD": "Edad de la construcción en años, a 2027 (2027 - ANOCONST); vacía si no hay año válido",
    "AREA_CONST": "Area construida (m2)",
    "TABLA_ORIGEN": "Tabla o metodo asignado",
    "TABLA_VALOR": "Columna exacta del Excel de tablas (rural)",
    "METODO_LIQUIDACION": "TABLA + TERRENO, INTEGRAL o MIXTO",
    "VM2_COM_LIQ": "Valor de la tabla 2027, comercial ($/m2, o $/cupo en garajes)",
    "FACTOR_AREA": "Factor de area de garajes y parqueaderos",
    "VALORCONS_COM_LIQ": "Valor comercial 2027 de la construccion",
    "VALORCONS_CAT_LIQ": "Valor catastral 2027 (comercial x factor catastral)",
    "VALORCONS_CAT_VIGENCIA": "Valor catastral en la base hoy (VALORCONS, o VALOANEX en anexos)",
    "EN_CERO": "1 si quedo en $ 0",
    "MOTIVO_POST": "Grupo del post: MODELO, ESPECIAL, SIN ZHF o SIN REGLA",
    "MOTIVO_CERO": "Por que quedo en $ 0",
}

LEER = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "ZHF", "TIPOLOGIA_ZHF",
        "ESTRPRED", "CONDICION", "DESTINOCONS", "DESTANEX", "USO_LADM", "TIPOANEXO",
        "TIPO_PARQ", "PUNTCONS", "ANOCONST", "AREA_CONST", "TABLA_ORIGEN", "TABLA_RURAL",
        "MOTIVO_RURAL", "METODO_LIQUIDACION", "VM2", "FACTOR_AREA",
        "LIQ_PARQUEADERO", "VALORCONS", "VALOANEX"]


def armar() -> pd.DataFrame:
    import pyarrow.parquet as pq
    ruta = CONFIG["parquet_liquidacion"]
    hay = set(pq.ParquetFile(ruta).schema_arrow.names)
    d = pd.read_parquet(ruta, columns=[c for c in LEER if c in hay])
    num = lambda c: pd.to_numeric(d[c], errors="coerce") if c in d.columns \
        else pd.Series(np.nan, index=d.index)

    d["COMUNA"] = d["COMUNA"].astype(str).str.strip().str.zfill(2)
    rural = pd.to_numeric(d["COMUNA"], errors="coerce") > 22
    d["ZONA"] = np.where(rural, "RURAL", "URBANO")
    d["CORREGIMIENTO"] = reglas_rurales.corregimiento(d["COMUNA"])
    anio = num("ANOCONST")
    d["EDAD"] = (2027 - anio).where(anio.between(1800, 2027))
    d["GRUPO_COMUNAS"] = grupo_comunas(d)
    zhf = d["ZHF"].astype(str)
    d["CLASIFICACION_SUELO"] = reglas_rurales.clasificacion_suelo(zhf).where(rural, "")
    d["AREA_MANEJO"] = reglas_rurales.area_manejo(zhf).where(rural, "")

    destanex = num("DESTANEX").fillna(0)
    anexo = destanex > 0
    d["TIPO_CONSTRUCCION"] = np.where(anexo, "NO CONVENCIONAL", "CONVENCIONAL")
    d["TABLA_VALOR"] = d.get("TABLA_RURAL", "")

    # El valor 2027, como en comparacion_vigencia.anexos_y_parqueaderos:
    # garajes y parqueaderos (007, 008, 036, 037) por cupo con su factor de
    # area (LIQ_PARQUEADERO); todo lo demas VM2 x area.
    vm2 = num("VM2").fillna(0)
    area = num("AREA_CONST").fillna(0)
    destino = d["DESTINOCONS"].astype(str).str.strip().str.zfill(3)
    por_cupo = d["TABLA_ORIGEN"].astype(str).eq("T12_PARQUEADEROS") & \
        destino.isin(["007", "008", "036", "037"])
    com = np.where(por_cupo, num("LIQ_PARQUEADERO").fillna(0), vm2 * area)
    d["VM2_COM_LIQ"] = vm2
    d["VALORCONS_COM_LIQ"] = com
    d["VALORCONS_CAT_LIQ"] = com * CONFIG["factor_catastral"]
    vig = np.where(anexo, num("VALOANEX"), num("VALORCONS"))
    d["VALORCONS_CAT_VIGENCIA"] = vig

    cero = vm2 <= 0
    d["EN_CERO"] = cero.astype(int)
    d["MOTIVO_POST"] = np.where(cero, motivo(d), "")
    d["MOTIVO_CERO"] = np.where(cero, motivo_cero(d), "")
    for c in COLUMNAS:
        if c not in d.columns:
            d[c] = ""
    return d[list(COLUMNAS)]


def resumen(d: pd.DataFrame) -> pd.DataFrame:
    g = d.assign(N=1, PREDIO=d["ID_PREDIO"]).groupby(
        ["ZONA", "TIPO_CONSTRUCCION", "TABLA_ORIGEN"], dropna=False)
    t = g.agg(CONSTRUCCIONES=("N", "sum"), PREDIOS=("PREDIO", "nunique"),
              EN_CERO=("EN_CERO", "sum"),
              VALOR_COM_2027=("VALORCONS_COM_LIQ", "sum"),
              VALOR_CAT_2027=("VALORCONS_CAT_LIQ", "sum")).reset_index()
    return t.sort_values(["ZONA", "TIPO_CONSTRUCCION", "CONSTRUCCIONES"],
                         ascending=[False, True, False], ignore_index=True)


def main():
    t0 = time.time()
    d = armar()
    salida = os.path.join(RAIZ_RESULTS, f"LIQUIDACION_COMPLETA_{CONFIG['version_tablas']}_"
                                        f"{datetime.now():%Y%m%d}.xlsx")
    os.makedirs(os.path.dirname(salida), exist_ok=True)
    print(f"Escribiendo {len(d):,} construcciones "
          f"({int((d['ZONA'] == 'URBANO').sum()):,} urbanas y "
          f"{int((d['ZONA'] == 'RURAL').sum()):,} rurales; "
          f"{int(d['EN_CERO'].sum()):,} en $ 0)...")
    # Sin constant_memory: pandas escribe por columnas y ese modo solo acepta
    # filas en orden, asi que dejaba todo vacio menos la primera columna.
    with pd.ExcelWriter(salida, engine="xlsxwriter") as w:
        res = resumen(d)
        res.to_excel(w, sheet_name="RESUMEN", index=False)
        d.to_excel(w, sheet_name="LIQUIDACION", index=False)
        pd.DataFrame({"COLUMNA": list(COLUMNAS), "DESCRIPCION": list(COLUMNAS.values())}) \
            .to_excel(w, sheet_name="DICCIONARIO", index=False)
        for hoja, cols in (("RESUMEN", res.columns), ("LIQUIDACION", d.columns),
                           ("DICCIONARIO", ["COLUMNA", "DESCRIPCION"])):
            h = w.sheets[hoja]
            h.set_column(0, len(cols) - 1, 18)
            h.freeze_panes(1, 0)
    print(f"Listo: {salida}\n   {time.time() - t0:.0f} s")


RAIZ_RESULTS = os.path.join(os.path.dirname(CONFIG["carpeta_results"]), "LIQUIDACION_TABLAS")

if __name__ == "__main__":
    main()
