"""Contrato de las variables de los modelos: tipo, unidad y rango.

Un modelo entrenado con una variable numerica no avisa si la recibe como texto:
segun el camino, el texto se convierte con errors='coerce' y queda en 0, o
pasa por get_dummies, se parte en columnas que despues se descartan y la
variable esperada se rellena con 0. En los dos casos la prediccion sale, pero
mal, y nada se detiene. Lo mismo con una indicadora que se arma comparando
contra '04' cuando la columna llego como el numero 4: queda siempre en 0.

Antes de cada prediccion `verificar` revisa la matriz que entra al modelo:

  - que esten todas las variables que el modelo espera (feature_names_in_);
  - que las numericas sean numeros. Si llegan como texto y TODAS se pueden
    convertir, se convierten (el valor no cambia) y se anota; si alguna no se
    puede, es ERROR;
  - que esten dentro de su rango (latitud en Cali, año entre 1800 y la
    vigencia, puntaje 1-100...). Una variable que salio entera en 0 o fuera
    de rango es la huella de una columna que se perdio por el tipo;
  - que las indicadoras valgan solo 0 o 1.

Los hallazgos quedan en output/modelos/CONTRATO_VARIABLES_MODELOS.xlsx, con
la hoja CONTRATO (que espera cada variable) y HALLAZGOS (que llego).
"""

from __future__ import annotations

import os
import re

import numpy as np
import pandas as pd

# variable -> (tipo, unidad, minimo, maximo, descripcion)
#   numerica   cantidad continua o discreta
#   codigo     categoria codificada con numero (el modelo la usa como numero)
#   indicadora 0 / 1
CONTRATO = {
    "VALOR_M2_SUELO": ("numerica", "pesos / m2", 1_000, 50_000_000, "Valor del suelo (ZHG) por metro cuadrado"),
    "LATITUDE": ("numerica", "grados decimales", 3.20, 3.65, "Latitud del predio"),
    "LONGITUDE": ("numerica", "grados decimales", -76.75, -76.40, "Longitud del predio"),
    "LATITUD": ("numerica", "grados decimales", 3.20, 3.65, "Latitud del predio (nombre en los modelos 2024)"),
    "LONGITUD": ("numerica", "grados decimales", -76.75, -76.40, "Longitud del predio (nombre en los modelos 2024)"),
    "ACONCONS": ("numerica", "m2", 0.01, 200_000, "Area construida de la construccion"),
    "ARECPRED": ("numerica", "m2", 0, 500_000, "Area construida del predio"),
    "ANOCONST": ("numerica", "año", 1800, 2027, "Año de construccion"),
    "EDAD": ("numerica", "años", 0, 230, "Edad de la construccion"),
    "PUNTCONS": ("numerica", "puntos", 1, 100, "Puntaje de calificacion"),
    "TPISCONS": ("numerica", "pisos", 1, 80, "Total de pisos de la construccion"),
    "NO_PISO": ("numerica", "piso", 0, 80, "Piso de la unidad (NPN posiciones 24-26)"),
    "NO_CONST": ("numerica", "construcciones", 1, 10_000, "Construcciones en el terreno"),
    "NUM_CONST_TERR": ("numerica", "construcciones", 1, 10_000, "Construcciones en el terreno"),
    "ESTRPRED": ("codigo", "estrato 0-6", 0, 6, "Estrato socioeconomico"),
    "INFLUENCIA_VIA": ("codigo", "codigo ZHF posicion 7", 0, 9, "Influencia de via"),
    "TOPOGRAFIA": ("codigo", "codigo ZHF posicion 8", 0, 9, "Topografia"),
    "TIPO_SEGUN_ACT": ("codigo", "codigo ZHF", 0, 999, "Tipo segun actividad"),
}
PATRON_INDICADORA = re.compile(r"^(COMUNA_[\d_]+|.+_\d+)$")

REGISTRO: list[dict] = []


def tipo_esperado(variable: str) -> tuple:
    if variable in CONTRATO:
        return CONTRATO[variable]
    if PATRON_INDICADORA.match(variable):
        return ("indicadora", "0 / 1", 0, 1, "Indicadora")
    return ("sin contrato", "", None, None, "")


def _esperadas(modelo) -> list[str] | None:
    nombres = getattr(modelo, "feature_names_in_", None)
    if nombres is None and hasattr(modelo, "steps"):
        for _, paso in modelo.steps:
            nombres = getattr(paso, "feature_names_in_", None)
            if nombres is not None:
                break
    return [str(n) for n in nombres] if nombres is not None else None


def verificar(nombre_modelo: str, X: pd.DataFrame, modelo=None, imprimir: bool = True) -> pd.DataFrame:
    """Revisa la matriz que entra al modelo; devuelve la misma matriz (numericas en texto, convertidas)."""
    if not isinstance(X, pd.DataFrame) or X.empty:
        return X
    X = X.copy()
    hallazgos = []

    esperadas = _esperadas(modelo) if modelo is not None else None
    if esperadas:
        faltan = [v for v in esperadas if v not in X.columns]
        for v in faltan:
            hallazgos.append(_fila(nombre_modelo, v, "falta", len(X), "ERROR",
                                   "El modelo espera la variable y no llega en la matriz"))

    for var in X.columns:
        tipo, unidad, minimo, maximo, _ = tipo_esperado(str(var))
        s = X[var]
        n = len(s)
        recibido = str(s.dtype)
        if tipo == "sin contrato":
            continue
        if not pd.api.types.is_numeric_dtype(s):
            num = pd.to_numeric(s.astype(str).str.strip().str.replace(",", ".", regex=False)
                                .replace({"": None, "nan": None, "None": None, "<NA>": None}), errors="coerce")
            malos = int((num.isna() & s.notna() & s.astype(str).str.strip().ne("")).sum())
            if malos:
                hallazgos.append(_fila(nombre_modelo, var, recibido, n, "ERROR",
                                       f"Se esperaba {tipo} ({unidad}) y llega como texto; {malos:,} valores no son "
                                       f"numeros", no_convertibles=malos))
                continue
            X[var] = num
            s = num
            hallazgos.append(_fila(nombre_modelo, var, recibido, n, "AJUSTE",
                                   f"Llegaba como texto; se convirtio a numero sin cambiar valores ({tipo}, {unidad})"))
        nulos = int(s.isna().sum())
        if nulos:
            hallazgos.append(_fila(nombre_modelo, var, recibido, n, "ADVERTENCIA",
                                   f"{nulos:,} valores vacios", nulos=nulos))
        v = s.dropna()
        if v.empty:
            continue
        if tipo == "indicadora":
            fuera = int((~v.isin([0, 1])).sum())
            if fuera:
                hallazgos.append(_fila(nombre_modelo, var, recibido, n, "ERROR",
                                       f"Indicadora con {fuera:,} valores distintos de 0 y 1", fuera_rango=fuera))
            continue
        fuera = int(((v < minimo) | (v > maximo)).sum())
        if fuera:
            pct = fuera / len(v)
            nivel = "ERROR" if pct >= 0.5 else "ADVERTENCIA"
            texto = (f"{fuera:,} valores ({pct:.1%}) fuera de {minimo} a {maximo} {unidad}; "
                     f"minimo {v.min():g}, maximo {v.max():g}")
            if nivel == "ERROR":
                texto += ". Huella de una variable que se perdio (por ejemplo, numero leido como texto)"
            hallazgos.append(_fila(nombre_modelo, var, recibido, n, nivel, texto, fuera_rango=fuera,
                                   minimo=v.min(), maximo=v.max()))

    REGISTRO.extend(hallazgos)
    if imprimir:
        graves = [h for h in hallazgos if h["NIVEL"] == "ERROR"]
        for h in graves:
            print(f"   ❌ CONTRATO {nombre_modelo} | {h['VARIABLE']}: {h['MENSAJE']}")
        if not graves:
            print(f"   ✅ CONTRATO {nombre_modelo}: {X.shape[1]} variables con el tipo y rango esperados")
    return X


def _fila(modelo, var, recibido, filas, nivel, mensaje, **extra):
    tipo, unidad, minimo, maximo, _ = tipo_esperado(str(var))
    return {"MODELO": modelo, "VARIABLE": str(var), "TIPO_ESPERADO": tipo, "UNIDAD": unidad,
            "RANGO": "" if minimo is None else f"{minimo} a {maximo}", "TIPO_RECIBIDO": recibido, "FILAS": filas,
            "NIVEL": nivel, "MENSAJE": mensaje, **{k.upper(): v for k, v in extra.items()}}


def errores() -> list[dict]:
    return [h for h in REGISTRO if h["NIVEL"] == "ERROR"]


def escribir(carpeta: str = "./output/modelos") -> str | None:
    """Excel con el contrato y lo que se encontro en esta corrida."""
    os.makedirs(carpeta, exist_ok=True)
    contrato = pd.DataFrame([(k, *v) for k, v in CONTRATO.items()],
                            columns=["VARIABLE", "TIPO", "UNIDAD", "MINIMO", "MAXIMO", "DESCRIPCION"])
    contrato = pd.concat([contrato, pd.DataFrame([{
        "VARIABLE": "COMUNA_xx, *_n (p. ej. TRAT_URB_04)", "TIPO": "indicadora", "UNIDAD": "0 / 1",
        "MINIMO": 0, "MAXIMO": 1,
        "DESCRIPCION": "Se arma comparando la variable de origen como TEXTO con ceros ('04', '013')"}])])
    hall = pd.DataFrame(REGISTRO) if REGISTRO else pd.DataFrame(
        [{"MODELO": "-", "NIVEL": "OK", "MENSAJE": "Todas las variables con el tipo y rango esperados"}])
    ruta = os.path.join(carpeta, "CONTRATO_VARIABLES_MODELOS.xlsx")
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as w:
        hall.to_excel(w, sheet_name="HALLAZGOS", index=False)
        contrato.to_excel(w, sheet_name="CONTRATO", index=False)
        for hoja, df in (("HALLAZGOS", hall), ("CONTRATO", contrato)):
            ws = w.sheets[hoja]
            ws.freeze_panes(1, 0)
            for j, col in enumerate(df.columns):
                ws.set_column(j, j, 90 if col in ("MENSAJE", "DESCRIPCION") else 18)
    n_err = len(errores())
    print(f"[{'ERROR' if n_err else 'OK'}] Contrato de variables de los modelos: {n_err} error(es) -> {ruta}")
    return ruta
