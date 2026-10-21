"""Validacion de la preliquidacion, predio por predio.

Despues de calcular el avaluo (paso 5) se revisa cada predio contra criterios
explicitos. Un criterio BLOQUEA cuando el avaluo no esta completo; una
OBSERVACION no impide la liquidacion pero hay que mirarla.

Antes, "APROBADO" queria decir "el avaluo calculado es igual al vigente del
export" (+/- $1.000). Con tablas nuevas eso significa "no cambio", no "esta bien
liquidado". Ese dato se conserva aparte, en IGUAL_AL_VIGENTE.

Salidas:
  ESTADO_PRELIQUIDACION  CUMPLE / CUMPLE CON OBSERVACIONES / NO CUMPLE
  QUE_NO_CUMPLE          los criterios que bloquean, separados por "; "
  OBSERVACIONES_REVISAR  las observaciones
y el detalle largo (un registro por predio y criterio) para el Excel de predios
por corregir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# criterio -> (bloquea, accion)
CRITERIOS = {
    "Comuna sin grupo de tablas de valor": (
        True, "La comuna no tiene tablas en Reglas.xlsx: definir su regla o quitarla de la seleccion."),
    "Avaluo en $0": (
        True, "Revisar terreno y construcciones: el predio no tiene ningun valor liquidado."),
    "Ninguna construccion con valor": (
        True, "Todas sus construcciones quedaron en $0: falta la tabla, el modelo o el dato (ver DETALLE)."),
    "Construcciones en $0": (
        True, "Algunas construcciones quedaron en $0: el avaluo esta incompleto (ver DETALLE)."),
    "Sin valor de terreno": (
        True, "El metodo exige terreno y el export no trae VALOTERR / AMETTERR para el predio."),
    "Area construida sin construcciones liquidadas": (
        True, "El predio tiene area construida pero ninguna construccion paso a la liquidacion "
              "(descontadas por falta de datos: ver PRE)."),
    "Integral y el export trae terreno": (
        False, "Predio integral (el suelo va dentro del valor) con VTER > 0 en el export: confirmar el metodo."),
    "Informal y el export trae terreno": (
        False, "Predio informal con VTER > 0 en el export: confirmar el metodo."),
    "Mixto sin terreno en el export": (False, "Predio mixto con VTER = 0 en el export: confirmar el terreno."),
    "Terreno mas construccion y el export no trae terreno": (
        False, "El export tiene VTER = 0 para un predio que se liquida con terreno."),
    "Variacion mayor a 50% frente al avaluo vigente": (
        False, "Cambio grande frente al avaluo vigente: revisar tabla, puntaje y area."),
}

UMBRAL_VARIACION = 50.0


def _col(d: pd.DataFrame, nombre: str, defecto=0) -> pd.Series:
    if nombre in d.columns:
        return pd.to_numeric(d[nombre], errors="coerce").fillna(defecto)
    return pd.Series(defecto, index=d.index)


def evaluar(d: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Agrega ESTADO_PRELIQUIDACION, QUE_NO_CUMPLE y OBSERVACIONES_REVISAR; devuelve (d, detalle)."""
    d = d.copy()
    aval = _col(d, "AVALUO_2026_CAT")
    total = _col(d, "TOTAL_CONST")
    con_valor = _col(d, "CONST_CON_VALOR")
    vter_com = _col(d, "VTER_2026_COM")
    vter_exp = _col(d, "VTER")
    terreno_incl = _col(d, "TERRENO_INCLUIDO")
    arec = _col(d, "ARECPRED")
    areap = _col(d, "AREAPRED")
    var = pd.to_numeric(d.get("VAR_AVALUO", pd.Series(np.nan, index=d.index)), errors="coerce")
    grupo = d.get("GRUPO_COMUNAS", pd.Series("", index=d.index)).astype(str)

    reglas = {
        "Comuna sin grupo de tablas de valor": grupo.eq("SIN GRUPO"),
        "Avaluo en $0": aval <= 0,
        "Ninguna construccion con valor": (total > 0) & (con_valor == 0),
        "Construcciones en $0": (con_valor > 0) & (con_valor < total),
        "Sin valor de terreno": (terreno_incl == 1) & (vter_com <= 0) & (areap > 0),
        "Area construida sin construcciones liquidadas": (arec > 0) & (total == 0),
        "Integral y el export trae terreno": (_col(d, "INTEGRAL") == 1) & (vter_exp > 0),
        "Informal y el export trae terreno": (_col(d, "INFORMALIDAD") == 1) & (vter_exp > 0),
        "Mixto sin terreno en el export": (_col(d, "MIXTO") == 1) & (vter_exp == 0),
        "Terreno mas construccion y el export no trae terreno": (_col(d, "TERRENO_MAS_CONST") == 1) & (vter_exp == 0),
        "Variacion mayor a 50% frente al avaluo vigente": var.abs() > UMBRAL_VARIACION,
    }
    detalle_textos = {
        "Construcciones en $0": (total - con_valor).astype(int).astype(str) + " de " + total.astype(int).astype(str),
        "Ninguna construccion con valor": total.astype(int).astype(str) + " construcciones",
        "Variacion mayor a 50% frente al avaluo vigente": var.round(1).astype(str) + "%",
    }

    bloquea, observa, filas = [], [], []
    for nombre, mascara in reglas.items():
        mascara = mascara.fillna(False).astype(bool)
        es_bloqueo, accion = CRITERIOS[nombre]
        texto = pd.Series(nombre, index=d.index)
        if nombre in detalle_textos:
            texto = nombre + " (" + detalle_textos[nombre] + ")"
        (bloquea if es_bloqueo else observa).append(texto.where(mascara, ""))
        if mascara.any():
            filas.append(pd.DataFrame({"ID_PREDIO": d.loc[mascara, "ID_PREDIO"].astype(str).values,
                                       "CRITERIO": nombre, "DETALLE": texto[mascara].values,
                                       "BLOQUEA": es_bloqueo, "ACCION": accion}))

    def unir(partes):
        if not partes:
            return pd.Series("", index=d.index)
        m = pd.concat(partes, axis=1)
        return m.apply(lambda r: "; ".join(x for x in r if x), axis=1)

    d["QUE_NO_CUMPLE"] = unir(bloquea)
    d["OBSERVACIONES_REVISAR"] = unir(observa)
    d["ESTADO_PRELIQUIDACION"] = np.select(
        [d.QUE_NO_CUMPLE.ne(""), d.OBSERVACIONES_REVISAR.ne("")],
        ["NO CUMPLE", "CUMPLE CON OBSERVACIONES"], default="CUMPLE")
    detalle = (pd.concat(filas, ignore_index=True) if filas
               else pd.DataFrame(columns=["ID_PREDIO", "CRITERIO", "DETALLE", "BLOQUEA", "ACCION"]))
    return d, detalle


def resumen(d: pd.DataFrame, detalle: pd.DataFrame) -> pd.DataFrame:
    estados = d.ESTADO_PRELIQUIDACION.value_counts().rename_axis("CONCEPTO").reset_index(name="PREDIOS")
    estados.insert(0, "TIPO", "ESTADO")
    crit = (detalle.groupby(["CRITERIO", "BLOQUEA"]).ID_PREDIO.nunique().reset_index(name="PREDIOS")
            .rename(columns={"CRITERIO": "CONCEPTO"}).sort_values("PREDIOS", ascending=False))
    crit.insert(0, "TIPO", np.where(crit.BLOQUEA, "NO CUMPLE", "OBSERVACION"))
    return pd.concat([estados, crit.drop(columns="BLOQUEA")], ignore_index=True)
