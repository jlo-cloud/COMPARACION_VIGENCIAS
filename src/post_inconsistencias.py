# -*- coding: utf-8 -*-
"""Lo que quedo sin valor DESPUES de liquidar.

PRE atrapa lo que le falta al dato de entrada; aqui va lo que traia todo y aun
asi salio en cero. De ahi la categoria FALTA REGLA: no se arregla corrigiendo
el predio sino entregando la tabla o la regla que falta.
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd

from control_filas import control

# Fuera de estas -las rurales 51 a 65- no hay columna que leer.
try:
    from tabla_construccion import COMUNAS_7, COMUNAS_10
    COMUNAS_PROGRAMADAS = sorted(set(COMUNAS_7) | set(COMUNAS_10))
except Exception:                                            # pragma: no cover
    COMUNAS_PROGRAMADAS = [f"{c:02d}" for c in range(1, 23)]

TABLA_ANEXOS = "T10_ANEXOS"


def _tablas_del_consolidado():
    """Que tablas trae hoy el consolidado. None si no se pudo leer."""
    try:
        import re

        from consolidar_tablas import tabla_valor_vigente
        ruta = tabla_valor_vigente()
        if ruta is None:
            return None
        cols = pd.read_excel(ruta, sheet_name="CONVENCIONALES", nrows=0).columns
        return {re.split(r"_\d+C", str(c))[0] for c in cols}
    except Exception as e:                                   # pragma: no cover
        print(f"   (no se pudo leer el consolidado para clasificar: {e})")
        return None


def clasificar_causa(d, col_vm2="VM2_2026_COM"):
    """Por que quedo en cero cada construccion.

    Gana la primera causa que aplica: una puede cumplir varias y lo que
    interesa es la que hay que resolver primero.
    """
    tabla = d["TABLA_ORIGEN"].astype(str) if "TABLA_ORIGEN" in d.columns \
        else pd.Series("", index=d.index)
    comuna = (d["COMUNA"].astype(str).str.strip().str.zfill(2)
              if "COMUNA" in d.columns else pd.Series("", index=d.index))

    fuera_programadas = ~comuna.isin(COMUNAS_PROGRAMADAS)

    # La T12 no sale del consolidado sino de una regla del codigo, y funciona:
    # buscarla en CONVENCIONALES la marcaba como tabla faltante.
    POR_REGLA_EN_CODIGO = {"T12_PARQUEADEROS"}

    familias = _tablas_del_consolidado()
    if familias is None:
        sin_tabla_en_excel = tabla == TABLA_ANEXOS
    else:
        base = tabla.str.replace(r"_\d{3}(_9)?$", "", regex=True)
        sin_tabla_en_excel = (~base.isin(familias)
                              & ~tabla.isin(POR_REGLA_EN_CODIGO)
                              & ~tabla.isin(["SIN TABLA", "MODELO",
                                             "ESPECIALES", ""]))

    # El puntaje existe pero la tabla solo llega a 100. Los parqueaderos no se
    # liquidan por puntaje, asi que quedan fuera.
    punt = (pd.to_numeric(d["PUNTCONS"], errors="coerce")
            if "PUNTCONS" in d.columns else pd.Series(np.nan, index=d.index))
    fuera_de_rango = (punt > 100) & (tabla != "T12_PARQUEADEROS")

    # Si la tabla no existe, que la comuna este programada da igual.
    return pd.Series(np.select(
        [
            sin_tabla_en_excel,
            fuera_programadas,
            fuera_de_rango,
            tabla == "SIN TABLA",
            tabla == "ESPECIALES",
            tabla == "MODELO",
        ],
        [
            "FALTA REGLA - la tabla no esta en el consolidado",
            "FALTA REGLA - comuna fuera de las programadas",
            "FALTA REGLA - el PUNTCONS existe pero la tabla solo llega a 100",
            "SIN TABLA - no se le pudo asignar tabla",
            "ESPECIALES - se liquidan por otra via",
            "MODELO - sin valor del modelo",
        ],
        # Tiene tabla, comuna y datos y aun asi salio en cero: ninguna rama de
        # la regla cubre esa combinacion. Es la lista corta a revisar.
        default="FALTA REGLA - la regla no cubre esta combinacion"),
        index=d.index)


def validar_vm2_cero(df_const_salida, exportar=True, output_path='./output/'):
    """Reporta lo que salio en cero y por que."""
    # Solo reporta, no filtra: el corte deja constancia de que la base que
    # revisa es la misma que salio de la liquidacion.
    control.marca("post_inconsistencias", df_const_salida)
    print("\n" + "=" * 80)
    print("🔎 POST: construcciones que quedaron SIN VALOR")
    print("=" * 80)

    col = ("VM2_2026_COM" if "VM2_2026_COM" in df_const_salida.columns
           else "VM2")
    if col not in df_const_salida.columns:
        print(f"   (no hay columna de valor que revisar; se omite)")
        return {}

    valor = pd.to_numeric(df_const_salida[col], errors="coerce").fillna(0)
    sin_vm2 = df_const_salida[valor <= 0].copy()
    if sin_vm2.empty:
        print("   Ninguna construccion quedo en cero.")
        return {"sin_vm2_detalle": sin_vm2, "predios": pd.DataFrame(),
                "total_predios": 0}

    sin_vm2["CAUSA"] = clasificar_causa(sin_vm2, col)
    sin_vm2["CATEGORIA"] = np.where(
        sin_vm2["CAUSA"].str.startswith("FALTA REGLA"), "FALTA REGLA",
        sin_vm2["CAUSA"].str.split(" - ").str[0])

    total = len(sin_vm2)
    print(f"\n   Construcciones sin valor : {total:,}")
    print(f"   Predios involucrados     : {sin_vm2['ID_PREDIO'].nunique():,}\n")

    resumen = (sin_vm2.groupby(["CATEGORIA", "CAUSA"])
               .agg(CONSTRUCCIONES=("ID_PREDIO", "size"),
                    PREDIOS=("ID_PREDIO", "nunique"))
               .reset_index()
               .sort_values("CONSTRUCCIONES", ascending=False))
    resumen["% DE LAS SIN VALOR"] = (
        resumen["CONSTRUCCIONES"] / total * 100).round(1)
    print(resumen.to_string(index=False))

    # groupby y no un bucle por predio: asi tardaba 46 minutos y el reporte
    # nunca se escribia.
    agg = {"CAUSAS": ("CAUSA", lambda s: " | ".join(sorted(set(s)))),
           "CONSTRUCCIONES_SIN_VALOR": ("CAUSA", "size")}
    if "CRUCE_CAMBIOS" in sin_vm2.columns:
        sin_vm2["CRUCE_CAMBIOS"] = pd.to_numeric(
            sin_vm2["CRUCE_CAMBIOS"], errors="coerce").fillna(0).astype(int)
        agg["CRUCE_CAMBIOS"] = ("CRUCE_CAMBIOS", "max")
    df_predios = sin_vm2.groupby("ID_PREDIO").agg(**agg).reset_index()

    # Detalle para el reporte de predios por corregir: la causa y las variables
    # que piden los modelos, para decir cual falta cuando la causa es MODELO.
    if exportar:
        cols = [c for c in ("ID_PREDIO", "LLAVE_CONST", "ID_CONSTRUCCION", "TABLA_ORIGEN", "CAUSA",
                            "CATEGORIA", "COMUNA", "GRUPO_MODELO", "DESTINOCONS", "TIPO_SEGUN_ACT",
                            "VALOR_M2_SUELO", "ANOCONST", "ESTRPRED", "PUNTCONS", "TPISCONS", "ACONCONS",
                            "ARECPRED", "LATITUDE", "LONGITUDE", "NUM_CONST_TERR", "ZHF_MODELO")
                if c in sin_vm2.columns]
        d = sin_vm2[cols].copy()
        for c in d.columns:
            d[c] = d[c].astype(str)
        carpeta = os.path.join(output_path, "post_inconsistencias")
        os.makedirs(carpeta, exist_ok=True)
        d.to_parquet(os.path.join(carpeta, "detalle_post_inconsistencias.parquet"), index=False)

    if exportar:
        carpeta = os.path.join(output_path, "post_inconsistencias")
        os.makedirs(carpeta, exist_ok=True)
        archivo = os.path.join(
            carpeta,
            f"reporte_post_inconsistencias_{datetime.now():%Y%m%d}.xlsx")

        # openpyxl escribe celda por celda y con 200.000 filas se cuelga.
        motor = "xlsxwriter"
        try:
            import xlsxwriter  # noqa: F401
        except ImportError:                                  # pragma: no cover
            motor = "openpyxl"

        with pd.ExcelWriter(archivo, engine=motor) as xl:
            resumen.to_excel(xl, sheet_name="RESUMEN", index=False)
            df_predios.to_excel(xl, sheet_name="PREDIOS", index=False)
            sin_vm2.to_excel(xl, sheet_name="DETALLE", index=False)
        print(f"\n💾 {archivo}")

    print("=" * 80 + "\n")
    return {"sin_vm2_detalle": sin_vm2, "resumen": resumen,
            "predios": df_predios, "total_predios": len(df_predios)}
