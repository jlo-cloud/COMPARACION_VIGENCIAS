# -*- coding: utf-8 -*-
"""
comparacion_ofertas.py
=======================================================================
Compara el VM2 (valor por m2 construido) asignado por las TABLAS DE
LIQUIDACION contra el VM2 observado en la BASE DE OFERTAS, usando una
llave compuesta:

    LIQUIDACION (df_const_liq) : ID_PREDIO + USO_LADM + AREA_CONST
    OFERTAS                    : Id catastral + Uso del predio + Area construida
    Valor comparado            : VM2  vs  "Valor m2 construido"

EL REPORTE SALE A NIVEL OFERTA
------------------------------
El Excel tiene UNA FILA POR OFERTA (por llave de la base de ofertas), no una
fila por cada construccion de la liquidacion. Es decir: si sube 500 ofertas,
el Excel trae ~500 filas, no las 725.000 construcciones de la base.
Si una llave de oferta cubre varias construcciones, se informa cuantas son
(N_CONSTRUCCIONES) y el detalle va en la hoja DETALLE_CONSTRUCCIONES.

Entregables:
  * Alerta de llaves DUPLICADAS en ambas bases (y si el VM2 difiere dentro
    del grupo duplicado, que es el caso realmente problematico).
  * Calculo de variaciones (absoluta, %, razon) y clasificacion por rangos.
  * Excel en ./results/COMPARACION_OFERTAS/ con 3 hojas:
        RESUMEN            indicadores del cruce (incluye el conteo de duplicados)
        COMPARACION        una fila por oferta, con su variacion
        OFERTAS_SIN_CRUCE  ofertas que no encontraron construccion, con el motivo
    Hay hojas opcionales apagadas (FUERA_TOLERANCIA, RESUMEN_X_USO,
    RESUMEN_X_RANGO, DUP_OFERTAS, DUP_LIQUIDACION, DETALLE_CONSTRUCCIONES);
    se encienden agregandolas a CONFIG['hojas_exportar'] o con --hojas.

Uso rapido
----------
    # 1) Dentro de main.py (recomendado, reutiliza el df en memoria)
    from comparacion_ofertas import comparacion_ofertas
    df_comp = comparacion_ofertas(df_liquidacion, ruta_ofertas='./input/OFERTAS.xlsx')

    # 2) Standalone (lee ./output/LIQUIDACION_TABLAS.parquet)
    python src/comparacion_ofertas.py --ofertas ./input/OFERTAS.xlsx

Notas de diseno
---------------
- LOS NOMBRES DE LOS USOS NO SE CAMBIAN NUNCA. El texto original de las dos
  bases viaja intacto al Excel en dos columnas separadas:
        USO_LADM    -> tal cual viene de la liquidacion
        USO_OFERTA  -> tal cual viene de la base de ofertas
  La normalizacion (mayusculas / tildes / espacios) se hace SOLO sobre una
  columna interna USO_KEY que se usa para cruzar y se descarta al exportar.
  Si se quiere cruce 100% literal: CONFIG['normalizar_uso'] = False.
  La columna USO_COINCIDE_EXACTO deja constancia de si los dos textos eran
  identicos o solo equivalentes.
- Lo mismo aplica al identificador: ID_PREDIO se conserva y la limpieza va
  en ID_KEY.
- Los nombres de columnas de la base de ofertas se DETECTAN automaticamente
  (insensible a acentos/mayusculas/espacios). Si no se encuentran, se lanza un
  error con la lista de columnas disponibles para que se ajuste ALIAS_OFERTAS.
- AREA_CONST es float: por eso la llave usa el area REDONDEADA
  (CONFIG['redondeo_area']). Con 0 decimales cruza por m2 entero.
- EL CRUCE VA EN DOS NIVELES:
      NIVEL 1  ID + USO + AREA (llave completa)
      NIVEL 2  ID + USO, y si el predio tiene varias construcciones de ese uso
               se elige LA DE AREA MAS CERCANA a la de la oferta
  El nivel 2 existe porque el area de la oferta casi nunca coincide con la de
  catastro: la oferta publica el area total construida (o la del predio
  completo) y la liquidacion la tiene partida por construccion. Ejemplo real,
  predio 100123: la oferta dice 448 m2 y en la liquidacion hay 420 m2 de
  vivienda + 28 m2 de comercio.
  La columna ORIGEN_MATCH dice con que nivel cruzo cada oferta, y
  DIF_AREA / DIF_AREA_PCT dicen cuanto se alejo el area de la construccion
  elegida. Para volver al cruce estricto: CONFIG['match_uso_area_cercana']=False.
- Si el 'Id catastral' de las ofertas viene con ~30 digitos (NPN), el cruce se
  hace automaticamente contra NUMERO_PREDIAL_NACIONAL y no contra ID_PREDIO.
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import unicodedata
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------
# Cronometro opcional (perf.py del proyecto). Si no existe, no falla.
# ---------------------------------------------------------------------
try:  # pragma: no cover
    from perf import crono
except Exception:  # pragma: no cover
    class _CronoDummy:
        def inicio(self, *a, **k): pass
        def marca(self, *a, **k): pass
        def resumen(self, *a, **k): pass
    crono = _CronoDummy()


# Raiz del proyecto (carpeta que contiene src/). Hace que el modulo funcione
# sin importar desde donde se lance.
RAIZ = Path(__file__).resolve().parent.parent


# =====================================================================
# CONFIGURACION
# =====================================================================
CONFIG = {
    # Rutas
    "carpeta_input": str(RAIZ / "input"),
    "carpeta_output": str(RAIZ / "output"),
    "carpeta_results": str(RAIZ / "results" / "COMPARACION_OFERTAS"),
    "parquet_liquidacion": str(RAIZ / "output" / "LIQUIDACION_TABLAS.parquet"),
    # Autodeteccion del archivo de ofertas:
    #   - en ./input/ofertas/  se toma CUALQUIER planilla (es la carpeta dedicada)
    #   - en ./input/          solo las que traigan OFERTA o COMPARABLE en el nombre,
    #                          para no confundirlas con los demas insumos
    "extensiones_ofertas": ["*.xlsx", "*.xlsm", "*.xls", "*.csv", "*.txt"],
    "patrones_ofertas": ["*OFERTA*", "*oferta*", "*COMPARABLE*", "*comparable*"],

    # Llave
    "redondeo_area": 0,            # decimales del AREA para armar la llave (0 = m2 entero)
    "id_solo_alfanumerico": True,  # limpia puntos, guiones y espacios del ID catastral
    "normalizar_uso": True,        # True = ignora tildes/mayusculas/espacios al cruzar
                                   # False = cruce literal. En ambos casos NO renombra usos.
    # Columna de la liquidacion contra la que se cruza el 'Id catastral'.
    # "AUTO" decide entre ID_PREDIO y NUMERO_PREDIAL_NACIONAL segun el largo
    # de los codigos que traiga la base de ofertas.
    "col_id_liquidacion": "AUTO",

    # Duplicados en OFERTAS: alertar | promedio | mediana | max | min | primero
    "estrategia_duplicados_ofertas": "promedio",
    # Duplicados en LIQUIDACION: siempre se conservan todas las filas (son construcciones
    # distintas del mismo predio/uso/area); solo se reportan y se marcan.

    # Cruce
    # Nivel 1: llave completa ID + USO + AREA.
    # Nivel 2 (este flag): la oferta que no cruzo exacto se reintenta por
    # ID + USO, y si el predio tiene VARIAS construcciones de ese uso se elige
    # LA DE AREA MAS CERCANA a la de la oferta. Es el caso normal: la oferta
    # trae el area publicada / del predio completo y la liquidacion la tiene
    # partida por construccion. Esas filas quedan marcadas en ORIGEN_MATCH como
    # "ID+USO (area mas cercana)" y traen DIF_AREA / DIF_AREA_PCT para poder
    # filtrar los enlaces con area muy distinta.
    "match_uso_area_cercana": True,
    # Tolerancia de variacion aceptada (%). Fuera de esto -> hoja FUERA_TOLERANCIA
    "tolerancia_pct": 10.0,

    # Columnas adicionales de la liquidacion que se arrastran al reporte si existen
    # (nombres reales de df_const_liq / LIQUIDACION_TABLAS.parquet)
    "columnas_extra_liq": [
        "CONSTRUCCION_ID", "ID_CONSTRUCCION", "NUMERO_PREDIAL_NACIONAL",
        "COMUNA", "CONDICION", "ESTRPRED", "TIPOUSO", "TIPOUSO_AJUSTADO",
        "DESTINOCONS", "DESTANEX", "PUNTCONS", "TPISCONS", "ANOCONST",
        "TABLA_ORIGEN", "METODO_LIQUIDACION", "ESPECIAL_2026", "INFORMALIDAD",
        "ZHF", "VM2_MOD", "VM2_ESP_2026", "LIQ_PARQUEADERO", "VALORCONS",
    ],

    # El reporte se arma A NIVEL OFERTA: una fila por cada llave de la base de
    # ofertas, NO una fila por cada construccion de la liquidacion. El Excel
    # pesa lo que pese la base de ofertas (cientos/miles de filas), no 725.000.

    # Hojas que se escriben en el Excel, en este orden. Agregue a la lista
    # cualquiera de las opcionales si las vuelve a necesitar:
    #   FUERA_TOLERANCIA        las que se pasan del umbral (ya vienen marcadas
    #                           en la columna FUERA_TOLERANCIA de COMPARACION)
    #   RESUMEN_X_USO           variaciones agregadas por uso
    #   RESUMEN_X_RANGO         distribucion por rango de variacion
    #   DUP_OFERTAS             detalle de llaves repetidas en ofertas
    #   DUP_LIQUIDACION         detalle de llaves repetidas en liquidacion
    #   DETALLE_CONSTRUCCIONES  una fila por construccion cruzada
    # (la ALERTA de duplicados sigue saliendo por consola, en RESUMEN y en las
    #  columnas DUPLICADO_OFERTA / DUPLICADO_LIQUIDACION de COMPARACION)
    "hojas_exportar": ["RESUMEN", "GRAFICOS", "COMPARACION", "OFERTAS_SIN_CRUCE",
                       "POSIBLE_ENLACE"],

    # Columnas que se dejan en la hoja COMPARACION (y en FUERA_TOLERANCIA), en
    # este orden. La idea es que la hoja se pueda revisar de un vistazo: sin
    # esta lista salen las ~58 columnas que arrastra la liquidacion.
    # Para volver a verlas todas: "columnas_comparacion": None (o lista vacia).
    # Para agregar una, basta con escribir su nombre aqui.
    "columnas_comparacion": [
        "ID_CATASTRAL_OFERTA",                    # id catastral
        "USO_OFERTA", "USO_LADM",                 # uso en cada base
        "AREA_OFERTA", "AREA_CONST", "DIF_AREA_PCT",   # area y que tan lejos quedo
        "PUNTCONS",                               # puntaje de la construccion
        "TABLA_ORIGEN",                           # tabla con la que se liquido
        "VM2_OFERTA", "VM2_LIQ", "VALORCONS",     # valores de construccion
        "DIF_ABS", "VAR_PCT",                     # variaciones
        "ORIGEN_MATCH",                           # con que nivel cruzo
    ],

    # Graficos PNG en results/COMPARACION_OFERTAS/GRAFICOS/. Solo entran las
    # ofertas con VM2 liquidado > 0 (las que quedan en 0 no tienen variacion).
    "generar_graficos": True,

    # Seguridad Excel (limite real de la hoja: 1.048.576 filas)
    "max_filas_hoja": 900_000,
}

# Rangos de clasificacion de la variacion absoluta en %
RANGOS_VARIACION = [
    (5.0,    "1. OK (<=5%)"),
    (10.0,   "2. LEVE (5-10%)"),
    (25.0,   "3. MEDIA (10-25%)"),
    (50.0,   "4. ALTA (25-50%)"),
    (np.inf, "5. CRITICA (>50%)"),
]

# Alias para detectar columnas en la base de OFERTAS
ALIAS_OFERTAS = {
    "ID_PREDIO": [
        "id catastral", "idcatastral", "id_catastral", "codigo catastral",
        "numero predial", "numero predial nacional", "npn", "codigo predial",
        "id predio", "id_predio",
    ],
    "USO_LADM": [
        "uso del predio", "uso predio", "uso_predio", "uso ladm", "uso_ladm",
        "destino economico", "destino", "uso",
    ],
    "AREA_CONST": [
        "area construida", "area_construida", "area de construccion",
        "area construccion", "area_const", "area const", "areaconstruida",
    ],
    "VM2_OFERTA": [
        "valor m2 construido", "valor m2 construccion", "valor m2 const",
        "valor_m2_construido", "vm2 construido", "vm2_construido",
        "valor metro cuadrado construido", "vm2 const",
    ],
}

# Alias para detectar el VM2 dentro de la liquidacion
ALIAS_VM2_LIQ = ["vm2", "vm2 construccion", "valor_m2", "valor m2", "vm2_const",
                 "vm2 const", "valor m2 construido"]

# Columnas internas de trabajo: nunca se exportan.
COLS_INTERNAS = ("ID_KEY", "USO_KEY", "AREA_KEY", "AREA_NUM", "LLAVE_2",
                 "FILA_ORIGEN_LIQ", "ID_CRUCE")


# =====================================================================
# UTILIDADES
# =====================================================================
def _norm(texto) -> str:
    """Normaliza un texto: sin acentos, minusculas, solo alfanumerico."""
    if texto is None or (isinstance(texto, float) and pd.isna(texto)):
        return ""
    s = unicodedata.normalize("NFKD", str(texto))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", "", s.lower())


def _detectar_columna(df: pd.DataFrame, alias: list[str], requerida=True,
                      etiqueta: str = "") -> str | None:
    """Busca en df la primera columna que coincida con alguno de los alias."""
    mapa = {_norm(c): c for c in df.columns}
    # 1) coincidencia exacta
    for a in alias:
        na = _norm(a)
        if na in mapa:
            return mapa[na]
    # 2) coincidencia por contencion (alias contenido en el nombre real)
    for a in alias:
        na = _norm(a)
        for nc, real in mapa.items():
            if na and na in nc:
                return real
    if requerida:
        raise KeyError(
            f"No se encontro la columna '{etiqueta}'. Alias probados: {alias}\n"
            f"Columnas disponibles: {list(df.columns)}"
        )
    return None


def _limpiar_numero_txt(txt: str) -> float:
    """'$ 1.234.567' -> 1234567.0 | '1,234,567.89' -> 1234567.89 | '120,5' -> 120.5"""
    s = re.sub(r"[^\d,.\-]", "", str(txt)).strip()
    if s in ("", "-", ".", ","):
        return np.nan
    n_pto, n_com = s.count("."), s.count(",")
    if n_pto and n_com:                     # el ultimo separador es el decimal
        dec = "." if s.rfind(".") > s.rfind(",") else ","
        mil = "," if dec == "." else "."
        s = s.replace(mil, "").replace(dec, ".")
    elif n_pto > 1 or n_com > 1:            # repetido -> separador de miles
        s = s.replace(".", "").replace(",", "")
    elif n_pto == 1 or n_com == 1:
        sep = "." if n_pto else ","
        decimales = len(s.split(sep)[-1])
        if decimales == 3 and len(s.split(sep)[0]) >= 1 and sep == ".":
            s = s.replace(".", "")          # 1.234 -> 1234 (formato COP)
        else:
            s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return np.nan


def _a_numero(serie: pd.Series) -> pd.Series:
    """Convierte a numerico tolerando '$', separadores de miles y coma decimal."""
    directo = pd.to_numeric(serie, errors="coerce")
    faltan = directo.isna() & serie.notna()
    if not faltan.any():
        return directo
    directo = directo.astype("float64")
    directo.loc[faltan] = serie.loc[faltan].map(_limpiar_numero_txt)
    return pd.to_numeric(directo, errors="coerce")


def _limpiar_id(serie: pd.Series) -> pd.Series:
    """Normaliza el ID catastral / ID_PREDIO a texto comparable (columna aparte)."""
    s = serie.astype(str).str.strip()
    s = s.str.replace(r"\.0+$", "", regex=True)    # 12345.0 -> 12345 (lectura float)
    s = s.str.replace(r"\s+", "", regex=True)
    if CONFIG["id_solo_alfanumerico"]:
        s = s.str.replace(r"[^0-9A-Za-z]", "", regex=True)
    s = s.str.upper()
    return s.replace({"NAN": np.nan, "NONE": np.nan, "": np.nan, "<NA>": np.nan})


def _limpiar_uso(serie: pd.Series) -> pd.Series:
    """
    Normaliza el uso SOLO para cruzar (columna USO_KEY).
    NUNCA se escribe sobre USO_LADM: el nombre original del uso se conserva.
    """
    s = serie.astype(str).str.strip()
    if not CONFIG["normalizar_uso"]:
        return s.replace({"nan": np.nan, "None": np.nan, "": np.nan})
    s = s.str.upper()
    s = s.apply(lambda x: "".join(
        c for c in unicodedata.normalize("NFKD", x) if not unicodedata.combining(c)))
    # '_' , '-' y espacios se vuelven equivalentes:
    # "Vivienda_Hasta_3_Pisos" == "VIVIENDA HASTA 3 PISOS"
    s = s.str.replace(r"[^A-Z0-9]+", " ", regex=True).str.strip()
    s = s.str.replace(r"\s+", " ", regex=True)
    return s.replace({"NAN": np.nan, "NONE": np.nan, "": np.nan})


def _armar_llaves(df: pd.DataFrame, redondeo: int, col_id: str = "ID_PREDIO") -> pd.DataFrame:
    """
    Agrega las columnas internas de cruce SIN tocar las originales:
        ID_KEY, USO_KEY, AREA_NUM, AREA_KEY, LLAVE_2 (id+uso), LLAVE (id+uso+area)
    """
    df = df.copy()
    df["ID_KEY"] = _limpiar_id(df[col_id])
    df["USO_KEY"] = _limpiar_uso(df["USO_LADM"])      # <- original intacto
    df["AREA_NUM"] = _a_numero(df["AREA_CONST"])
    df["AREA_KEY"] = df["AREA_NUM"].round(redondeo)
    if redondeo <= 0:
        df["AREA_KEY"] = df["AREA_KEY"].astype("Float64").astype("Int64")

    df["LLAVE_2"] = df["ID_KEY"].astype(str) + "|" + df["USO_KEY"].astype(str)
    df["LLAVE"] = df["LLAVE_2"] + "|" + df["AREA_KEY"].astype(str)
    return df


def _descartar_llaves_invalidas(df: pd.DataFrame, etiqueta: str) -> pd.DataFrame:
    """Quita filas sin id / sin uso / sin area: si no, cruzarian entre si por 'nan|nan|nan'."""
    malas = df["ID_KEY"].isna() | df["USO_KEY"].isna() | df["AREA_KEY"].isna()
    n = int(malas.sum())
    if n:
        print(f"   ! [{etiqueta}] {n:,} filas descartadas por llave incompleta "
              f"(sin id, sin uso o sin area)")
    return df[~malas].copy()


def _clasificar(pct: float) -> str:
    if pd.isna(pct):
        return "0. SIN DATO"
    a = abs(pct)
    for limite, etiqueta in RANGOS_VARIACION:
        if a <= limite:
            return etiqueta
    return RANGOS_VARIACION[-1][1]


# =====================================================================
# CARGA DE DATOS
# =====================================================================
def ubicar_archivo_ofertas(ruta: str | None = None) -> str:
    """Devuelve la ruta del archivo de ofertas (explicita o autodetectada)."""
    if ruta:
        if not os.path.exists(ruta):
            alt = RAIZ / ruta
            if alt.exists():
                return str(alt)
            raise FileNotFoundError(f"No existe el archivo de ofertas: {ruta}")
        return ruta

    carpeta_ded = os.path.join(CONFIG["carpeta_input"], "ofertas")
    candidatos: list[str] = []

    # 1) Carpeta dedicada: sirve cualquier planilla, sin importar como se llame.
    for ext in CONFIG["extensiones_ofertas"]:
        candidatos += glob.glob(os.path.join(carpeta_ded, ext))

    # 2) Raiz de input/: solo lo que se parezca a una base de ofertas.
    if not candidatos:
        for patron in CONFIG["patrones_ofertas"]:
            for ext in CONFIG["extensiones_ofertas"]:
                candidatos += glob.glob(
                    os.path.join(CONFIG["carpeta_input"], patron + ext.lstrip("*")))

    candidatos = [c for c in set(candidatos) if not os.path.basename(c).startswith("~$")]
    candidatos = sorted(candidatos, key=os.path.getmtime, reverse=True)

    if not candidatos:
        raise FileNotFoundError(
            "No se encontro archivo de ofertas.\n"
            f"Copie su base en: {carpeta_ded}\n"
            "  (en esa carpeta sirve cualquier .xlsx / .csv, con el nombre que sea)\n"
            f"o dejela en {CONFIG['carpeta_input']} con OFERTA o COMPARABLE en el nombre.\n"
            "Debe traer las columnas: 'Id catastral', 'Uso del predio',\n"
            "'Area construida' y 'Valor m2 construido'.\n"
            "Tambien puede pasar la ruta con ruta_ofertas='...' o --ofertas ..."
        )
    if len(candidatos) > 1:
        print("   ! Varios archivos de ofertas encontrados, se usa el mas reciente:")
        for c in candidatos:
            print(f"     - {os.path.basename(c)}")
    return candidatos[0]


def cargar_ofertas(ruta: str | None = None, hoja=0) -> pd.DataFrame:
    """Lee la base de ofertas y la normaliza a [ID_PREDIO, USO_LADM, AREA_CONST, VM2_OFERTA]."""
    ruta = ubicar_archivo_ofertas(ruta)
    ext = os.path.splitext(ruta)[1].lower()
    print(f"   Leyendo ofertas: {ruta}")

    if ext in (".xlsx", ".xlsm", ".xls"):
        df = pd.read_excel(ruta, sheet_name=hoja, dtype=object)
    elif ext == ".csv":
        df = pd.read_csv(ruta, sep=None, engine="python", dtype=object,
                         encoding="utf-8-sig")
    else:  # .txt delimitado por |
        df = pd.read_csv(ruta, sep="|", dtype=object, encoding="utf-8-sig")

    if isinstance(df, dict):  # sheet_name=None
        df = pd.concat(df.values(), ignore_index=True)

    df = df.loc[:, [c for c in df.columns if not str(c).startswith("Unnamed:")]]

    cols = {}
    for canon, alias in ALIAS_OFERTAS.items():
        cols[canon] = _detectar_columna(df, alias, requerida=True, etiqueta=canon)
    print("   Mapeo de columnas de ofertas:")
    for k, v in cols.items():
        print(f"     {k:<12} <- '{v}'")

    out = pd.DataFrame({
        "ID_PREDIO": df[cols["ID_PREDIO"]],
        "USO_LADM": df[cols["USO_LADM"]],       # texto ORIGINAL del uso en ofertas
        "AREA_CONST": df[cols["AREA_CONST"]],
        "VM2_OFERTA": _a_numero(df[cols["VM2_OFERTA"]]),
    })
    out["FILA_ORIGEN_OFERTA"] = np.arange(2, len(out) + 2)  # fila real en Excel (con encabezado)

    # PASO 1: quedarse SOLO con las ofertas que traen valor de construccion.
    # Se filtra ANTES de armar la llave y antes de comparar: las ofertas sin
    # 'Valor m2 construido' (p.ej. las de alquiler) no entran al proceso.
    n0 = len(out)
    vacias = int(out["VM2_OFERTA"].isna().sum())
    ceros = int((out["VM2_OFERTA"] == 0).sum())
    out = out[out["VM2_OFERTA"].notna() & (out["VM2_OFERTA"] > 0)]

    print("   Filtro por valor de construccion:")
    print(f"     Filas leidas del archivo          : {n0:,}")
    if vacias:
        print(f"     - sin 'Valor m2 construido'       : {vacias:,}  (descartadas)")
    if ceros:
        print(f"     - con 'Valor m2 construido' = 0   : {ceros:,}  (descartadas)")
    print(f"     = OFERTAS CON VALOR DE CONSTRUCCION: {len(out):,}  <- sobre estas se arma la llave")

    if out.empty:
        raise ValueError(
            "Ninguna oferta tiene 'Valor m2 construido' mayor que cero.\n"
            "   Revise que la columna traiga numeros y no texto."
        )

    out.attrs["archivo"] = os.path.basename(ruta)
    out.attrs["filas_archivo"] = n0
    out.attrs["descartadas_sin_valor"] = n0 - len(out)
    return out.reset_index(drop=True)


def cargar_liquidacion(df_const_liq: pd.DataFrame | None = None) -> pd.DataFrame:
    """Toma el df en memoria o lee el parquet de liquidacion, y normaliza el VM2."""
    if df_const_liq is None:
        ruta = CONFIG["parquet_liquidacion"]
        if not os.path.exists(ruta):
            raise FileNotFoundError(
                f"No se encontro {ruta}. Ejecute main.py (PASO 4) o pase df_const_liq."
            )
        print(f"   Leyendo liquidacion: {ruta}")
        # Se leen solo las columnas necesarias: el parquet pesa ~77 MB / 725k filas.
        try:
            import pyarrow.parquet as pq
            disponibles = set(pq.ParquetFile(ruta).schema_arrow.names)
            usar = [c for c in (["ID_PREDIO", "USO_LADM", "AREA_CONST", "VM2"]
                                + CONFIG["columnas_extra_liq"]) if c in disponibles]
            df_const_liq = pd.read_parquet(ruta, columns=list(dict.fromkeys(usar)))
        except Exception:
            df_const_liq = pd.read_parquet(ruta)

    df = df_const_liq.copy()

    for req, alias in (("ID_PREDIO", ["id_predio", "id predio"]),
                       ("USO_LADM", ["uso_ladm", "uso ladm", "uso"]),
                       ("AREA_CONST", ALIAS_OFERTAS["AREA_CONST"])):
        if req not in df.columns:
            real = _detectar_columna(df, alias, requerida=True, etiqueta=req)
            df = df.rename(columns={real: req})

    col_vm2 = "VM2" if "VM2" in df.columns else _detectar_columna(
        df, ALIAS_VM2_LIQ, requerida=True, etiqueta="VM2")
    if col_vm2 != "VM2_LIQ":
        df = df.rename(columns={col_vm2: "VM2_LIQ"})
    df["VM2_LIQ"] = _a_numero(df["VM2_LIQ"])

    extra = [c for c in CONFIG["columnas_extra_liq"]
             if c in df.columns and c not in ("AREA_CONST", "ID_PREDIO", "USO_LADM", "VM2_LIQ")]
    faltantes = [c for c in CONFIG["columnas_extra_liq"] if c not in df.columns]
    if faltantes:
        print(f"   (columnas extra no disponibles, se omiten: {faltantes})")

    base = ["ID_PREDIO", "USO_LADM", "AREA_CONST", "VM2_LIQ"] + extra
    df = df[list(dict.fromkeys(base))].copy()
    df["FILA_ORIGEN_LIQ"] = np.arange(len(df))
    return df


def _elegir_columna_id(df_liq: pd.DataFrame, df_of: pd.DataFrame) -> str:
    """
    Decide contra que columna de la liquidacion se cruza el 'Id catastral'.
    Si las ofertas traen codigos largos (NPN de ~30 digitos) usa
    NUMERO_PREDIAL_NACIONAL; si no, ID_PREDIO.
    """
    forzado = CONFIG.get("col_id_liquidacion", "AUTO")
    if forzado and forzado != "AUTO":
        if forzado not in df_liq.columns:
            raise KeyError(f"col_id_liquidacion='{forzado}' no existe en la liquidacion")
        return forzado

    ids = _limpiar_id(df_of["ID_PREDIO"]).dropna()
    largo = int(ids.str.len().mode().iloc[0]) if len(ids) else 0
    if largo >= 20 and "NUMERO_PREDIAL_NACIONAL" in df_liq.columns:
        print(f"   ! El 'Id catastral' de ofertas trae {largo} digitos -> se cruza contra "
              f"NUMERO_PREDIAL_NACIONAL (no contra ID_PREDIO)")
        return "NUMERO_PREDIAL_NACIONAL"
    print(f"   Identificador de cruce: ID_PREDIO (largo tipico en ofertas: {largo})")
    return "ID_PREDIO"


# =====================================================================
# DUPLICADOS
# =====================================================================
def detectar_duplicados(df: pd.DataFrame, col_valor: str, etiqueta: str
                        ) -> tuple[pd.DataFrame, dict]:
    """Devuelve las filas con LLAVE duplicada y un resumen de la alerta."""
    dup_mask = df.duplicated(subset="LLAVE", keep=False)
    df_dup = df[dup_mask].copy()

    resumen = {
        "base": etiqueta,
        "filas_totales": len(df),
        "llaves_unicas": df["LLAVE"].nunique(),
        "llaves_duplicadas": int(df_dup["LLAVE"].nunique()) if len(df_dup) else 0,
        "filas_en_duplicado": len(df_dup),
        "llaves_dup_con_valor_distinto": 0,
    }

    if len(df_dup):
        g = df_dup.groupby("LLAVE")[col_valor]
        est = g.agg(N_REGISTROS="size", VALOR_MIN="min", VALOR_MAX="max",
                    VALOR_PROM="mean", VALOR_MEDIANA="median", VALORES_DISTINTOS="nunique")
        est["DISPERSION_PCT"] = np.where(
            est["VALOR_MIN"] > 0,
            (est["VALOR_MAX"] - est["VALOR_MIN"]) / est["VALOR_MIN"] * 100, np.nan)
        est["ALERTA"] = np.where(est["VALORES_DISTINTOS"] > 1,
                                 "DUPLICADO CON VALORES DISTINTOS",
                                 "DUPLICADO CON MISMO VALOR")
        resumen["llaves_dup_con_valor_distinto"] = int((est["VALORES_DISTINTOS"] > 1).sum())
        df_dup = (df_dup.merge(est.reset_index(), on="LLAVE", how="left")
                        .sort_values(["DISPERSION_PCT", "LLAVE"], ascending=[False, True]))

    print(f"   [{etiqueta}] filas={resumen['filas_totales']:,} | "
          f"llaves unicas={resumen['llaves_unicas']:,} | "
          f"llaves duplicadas={resumen['llaves_duplicadas']:,} "
          f"(con VM2 distinto: {resumen['llaves_dup_con_valor_distinto']:,})")
    if resumen["llaves_duplicadas"]:
        print(f"   ** ALERTA: {etiqueta} tiene {resumen['llaves_duplicadas']:,} llaves "
              f"repetidas ({resumen['filas_en_duplicado']:,} filas) -> hoja de duplicados")
    if resumen["llaves_dup_con_valor_distinto"]:
        print(f"   ** ALERTA CRITICA: {resumen['llaves_dup_con_valor_distinto']:,} llaves de "
              f"{etiqueta} tienen mas de un valor de VM2 -> revisar antes de concluir")

    return df_dup, resumen


def resolver_duplicados_ofertas(df: pd.DataFrame, estrategia: str) -> pd.DataFrame:
    """Colapsa las ofertas duplicadas por LLAVE segun la estrategia elegida."""
    agg_map = {"promedio": "mean", "mediana": "median", "max": "max", "min": "min"}

    if estrategia == "alertar":
        # conserva todas las filas: una fila del reporte por cada oferta repetida
        out = df.copy()
        out["N_OFERTAS"] = out.groupby("LLAVE")["VM2_OFERTA"].transform("size")
        out["VM2_OFERTA_MIN"] = out.groupby("LLAVE")["VM2_OFERTA"].transform("min")
        out["VM2_OFERTA_MAX"] = out.groupby("LLAVE")["VM2_OFERTA"].transform("max")
        out["AREA_OFERTA"] = out["AREA_NUM"]
        out["USO_OFERTA"] = out["USO_LADM"]          # texto original de la oferta
        out["ID_CATASTRAL_OFERTA"] = out["ID_PREDIO"]  # texto original del id
        out["FILAS_OFERTA"] = out["FILA_ORIGEN_OFERTA"].astype(str)
        out["ESTRATEGIA_DUP"] = np.where(out["N_OFERTAS"] > 1, "alertar (1:N)", "unico")
        return out

    base = (df.groupby("LLAVE", as_index=False)
              .agg(N_OFERTAS=("VM2_OFERTA", "size"),
                   VM2_OFERTA_MIN=("VM2_OFERTA", "min"),
                   VM2_OFERTA_MAX=("VM2_OFERTA", "max"),
                   AREA_OFERTA=("AREA_NUM", "mean"),
                   USO_OFERTA=("USO_LADM", "first"),   # texto original, sin modificar
                   ID_CATASTRAL_OFERTA=("ID_PREDIO", "first"),
                   LLAVE_2=("LLAVE_2", "first"),
                   FILAS_OFERTA=("FILA_ORIGEN_OFERTA",
                                 lambda s: ", ".join(map(str, sorted(s)[:10])))))

    if estrategia in agg_map:
        val = df.groupby("LLAVE", as_index=False)["VM2_OFERTA"].agg(agg_map[estrategia])
    elif estrategia == "primero":
        val = df.drop_duplicates("LLAVE", keep="first")[["LLAVE", "VM2_OFERTA"]]
    else:
        raise ValueError(f"estrategia_duplicados_ofertas invalida: {estrategia}")

    out = base.merge(val, on="LLAVE", how="left")
    out["ESTRATEGIA_DUP"] = np.where(out["N_OFERTAS"] > 1, estrategia, "unico")
    return out


# =====================================================================
# COMPARACION
# =====================================================================
def _agregar_liquidacion(df_liq: pd.DataFrame, llaves: set, por: str = "LLAVE") -> pd.DataFrame:
    """
    Colapsa la liquidacion a UNA fila por llave, quedandose SOLO con las llaves
    que trae la base de ofertas. Asi el cruce nunca arrastra las ~725.000
    construcciones: se agrupan unicamente las que participan en la comparacion.

    Cuando una llave cubre varias construcciones se informa cuantas son
    (N_CONSTRUCCIONES) y si tenian VM2 distinto (VM2_LIQ_DISTINTOS).
    """
    sub = df_liq[df_liq[por].isin(llaves)]
    if sub.empty:
        return pd.DataFrame(columns=[por, "VM2_LIQ", "N_CONSTRUCCIONES"])

    agg = {
        "VM2_LIQ": ("VM2_LIQ", "mean"),
        "VM2_LIQ_MIN": ("VM2_LIQ", "min"),
        "VM2_LIQ_MAX": ("VM2_LIQ", "max"),
        "VM2_LIQ_DISTINTOS": ("VM2_LIQ", "nunique"),
        "N_CONSTRUCCIONES": ("VM2_LIQ", "size"),
        "AREA_CONST_TOTAL": ("AREA_NUM", "sum"),
    }
    if "CONSTRUCCION_ID" in sub.columns:
        agg["CONSTRUCCIONES_LLAVE"] = ("CONSTRUCCION_ID",
                                       lambda s: ", ".join(map(str, s.unique()[:10])))
    # El resto de columnas de la liquidacion viajan con 'first' (son iguales
    # dentro de la llave salvo cuando hay construcciones duplicadas).
    saltar = set(COLS_INTERNAS) | {por, "LLAVE", "VM2_LIQ"} | set(agg)
    for c in sub.columns:
        if c not in saltar:
            agg[c] = (c, "first")

    return sub.groupby(por, as_index=False).agg(**agg)


def _liq_area_mas_cercana(df_liq: pd.DataFrame, pend: pd.DataFrame,
                          columnas: list[str]) -> pd.DataFrame:
    """
    NIVEL 2 DEL CRUCE. Para las ofertas que no cruzaron por la llave completa:
    se busca el predio+uso (LLAVE_2) y, si tiene varias construcciones de ese
    uso, se elige LA DE AREA MAS CERCANA al area de la oferta.

    No promedia ni suma: se queda con UNA construccion, la mas parecida. Asi el
    VM2 comparado es el de una construccion real y no un valor sintetico.

    Devuelve un frame con las MISMAS columnas que _agregar_liquidacion (para
    poder rellenar df_match), mas N_CONST_USO (cuantas construcciones de ese
    uso habia para elegir).

    'pend' debe traer [LLAVE, LLAVE_2, AREA_OFERTA] de las ofertas pendientes.
    """
    cand = pend[["LLAVE", "LLAVE_2", "AREA_OFERTA"]].merge(
        df_liq, on="LLAVE_2", how="inner", suffixes=("", "_LIQ"))
    if cand.empty:
        return pd.DataFrame(columns=columnas)

    cand["_DIF"] = (pd.to_numeric(cand["AREA_OFERTA"], errors="coerce")
                    - cand["AREA_NUM"]).abs()
    # Desempates estables: menor diferencia de area; si empatan, la construccion
    # de mayor area (la principal); si aun empatan, la primera de la base.
    cand = cand.sort_values(["LLAVE", "_DIF", "AREA_NUM", "FILA_ORIGEN_LIQ"],
                            ascending=[True, True, False, True], kind="mergesort")
    n_uso = cand.groupby("LLAVE")["LLAVE_2"].size()
    eleg = cand.drop_duplicates("LLAVE", keep="first").copy()

    # Se elige UNA sola construccion: no hay promedio ni dispersion que reportar.
    eleg["VM2_LIQ_MIN"] = eleg["VM2_LIQ"]
    eleg["VM2_LIQ_MAX"] = eleg["VM2_LIQ"]
    eleg["VM2_LIQ_DISTINTOS"] = 1
    eleg["N_CONSTRUCCIONES"] = 1
    eleg["AREA_CONST_TOTAL"] = eleg["AREA_NUM"]
    if "CONSTRUCCION_ID" in eleg.columns:
        eleg["CONSTRUCCIONES_LLAVE"] = eleg["CONSTRUCCION_ID"].astype(str)
    eleg["N_CONST_USO"] = eleg["LLAVE"].map(n_uso).astype("Int64")

    faltan = [c for c in columnas if c not in eleg.columns]
    for c in faltan:
        eleg[c] = np.nan
    return eleg[list(dict.fromkeys(columnas + ["N_CONST_USO"]))]


def comparar(df_liq: pd.DataFrame, df_of: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Cruza A NIVEL OFERTA: la base del reporte es la base de ofertas, no la
    liquidacion. Sale una fila por llave de oferta (o por oferta, si la
    estrategia de duplicados es 'alertar').

    Devuelve (comparacion, ofertas_sin_cruce).
    """
    # De la oferta solo viajan sus propias columnas; los textos de la
    # liquidacion (USO_LADM, ID_PREDIO, AREA_CONST) llegan del otro lado.
    excluir = {"ID_PREDIO", "USO_LADM", "USO_KEY", "ID_KEY", "AREA_CONST",
               "AREA_KEY", "AREA_NUM", "FILA_ORIGEN_OFERTA"}
    cols_of = [c for c in df_of.columns if c not in excluir]

    liq_agg = _agregar_liquidacion(df_liq, set(df_of["LLAVE"]), "LLAVE")
    df_match = df_of[cols_of].merge(liq_agg, on="LLAVE", how="left")

    df_match["ORIGEN_MATCH"] = np.where(df_match["VM2_LIQ"].notna(),
                                        "LLAVE COMPLETA (ID+USO+AREA)", None)

    # --- NIVEL 2: ID + USO, quedandose con el area mas parecida -------------
    # La oferta suele traer el area publicada (o la del predio completo) y la
    # liquidacion la tiene partida por construccion, asi que el area exacta casi
    # nunca coincide. Se cruza entonces por predio+uso y se elige la
    # construccion de area mas cercana.
    if CONFIG["match_uso_area_cercana"]:
        pend = df_match["VM2_LIQ"].isna()
        if pend.any():
            liq2 = _liq_area_mas_cercana(df_liq, df_match.loc[pend],
                                         list(liq_agg.columns))
            if not liq2.empty:
                df_match = df_match.merge(liq2, on="LLAVE", how="left", suffixes=("", "_F"))
                rec = pend & df_match["VM2_LIQ_F"].notna()
                for dst in [c for c in df_match.columns if c + "_F" in df_match.columns]:
                    df_match.loc[rec, dst] = df_match.loc[rec, dst + "_F"]
                df_match.loc[rec, "ORIGEN_MATCH"] = "ID+USO (area mas cercana)"
                df_match = df_match.drop(
                    columns=[c for c in df_match.columns if c.endswith("_F")])
                print(f"   Cruce por ID+USO con area mas cercana: "
                      f"+{int(rec.sum()):,} ofertas recuperadas")

    # --- Separar las ofertas que no encontraron construccion ----------------
    sin_cruce = df_match[df_match["VM2_LIQ"].isna()].copy()
    df_comp = df_match[df_match["VM2_LIQ"].notna()].copy()

    if df_comp.empty:
        return df_comp, sin_cruce

    # --- Variaciones --------------------------------------------------------
    df_comp["DIF_ABS"] = df_comp["VM2_OFERTA"] - df_comp["VM2_LIQ"]
    df_comp["VAR_PCT"] = np.where(df_comp["VM2_LIQ"] > 0,
                                  df_comp["DIF_ABS"] / df_comp["VM2_LIQ"] * 100, np.nan)
    df_comp["VAR_PCT_ABS"] = df_comp["VAR_PCT"].abs()
    df_comp["RAZON_LIQ_OFERTA"] = np.where(df_comp["VM2_OFERTA"] > 0,
                                           df_comp["VM2_LIQ"] / df_comp["VM2_OFERTA"], np.nan)
    df_comp["SENTIDO"] = np.select(
        [df_comp["VM2_LIQ"] <= 0, df_comp["DIF_ABS"] > 0, df_comp["DIF_ABS"] < 0],
        ["SIN VM2 LIQUIDADO", "LIQUIDACION POR DEBAJO DE OFERTA",
         "LIQUIDACION POR ENCIMA DE OFERTA"],
        default="IGUAL")
    df_comp["RANGO_VARIACION"] = df_comp["VAR_PCT"].map(_clasificar)
    df_comp["FUERA_TOLERANCIA"] = df_comp["VAR_PCT_ABS"] > CONFIG["tolerancia_pct"]

    # Marca de duplicados vista desde la fila de comparacion
    df_comp["DUPLICADO_OFERTA"] = np.where(df_comp.get("N_OFERTAS", 1) > 1, "SI", "NO")
    df_comp["DUPLICADO_LIQUIDACION"] = np.where(df_comp["N_CONSTRUCCIONES"] > 1, "SI", "NO")
    # Caso critico: la llave cubre varias construcciones con VM2 distinto, o sea
    # que el VM2_LIQ que se esta comparando es un promedio de valores distintos.
    df_comp["ALERTA_VM2_LIQ"] = np.where(
        df_comp["VM2_LIQ_DISTINTOS"] > 1,
        "VM2 PROMEDIADO: la llave tiene construcciones con VM2 distinto", "")

    # Que tan lejos quedo el area de la construccion elegida respecto a la de la
    # oferta. En los cruces de NIVEL 1 esto da ~0; en los de NIVEL 2 es el dato
    # con el que se decide si el enlace es creible.
    if "AREA_CONST" in df_comp.columns:
        a_of = pd.to_numeric(df_comp["AREA_OFERTA"], errors="coerce")
        a_lq = pd.to_numeric(df_comp["AREA_CONST"], errors="coerce")
        df_comp["DIF_AREA"] = (a_of - a_lq).round(2)
        df_comp["DIF_AREA_PCT"] = np.where(a_lq > 0, (a_of - a_lq) / a_lq * 100,
                                           np.nan).round(2)

    # Constancia de si el nombre del uso era identico o solo equivalente.
    # (Ninguno de los dos textos se modifica: solo se comparan.)
    if "USO_OFERTA" in df_comp.columns:
        df_comp["USO_COINCIDE_EXACTO"] = np.where(
            df_comp["USO_LADM"].astype(str).str.strip()
            == df_comp["USO_OFERTA"].astype(str).str.strip(), "SI", "NO")

    # Impacto en avaluo: se usa el area SUMADA de las construcciones de la llave
    if "AREA_CONST_TOTAL" in df_comp.columns:
        df_comp["IMPACTO_AVALUO"] = df_comp["DIF_ABS"] * df_comp["AREA_CONST_TOTAL"]

    df_comp = df_comp.sort_values("VAR_PCT_ABS", ascending=False)
    return df_comp, sin_cruce


def resumen_por_uso(df_comp: pd.DataFrame) -> pd.DataFrame:
    if df_comp.empty:
        return pd.DataFrame()
    g = df_comp.groupby("USO_LADM", dropna=False)
    out = pd.DataFrame({
        "CONSTRUCCIONES": g.size(),
        "VM2_LIQ_PROM": g["VM2_LIQ"].mean(),
        "VM2_OFERTA_PROM": g["VM2_OFERTA"].mean(),
        "VAR_PCT_PROM": g["VAR_PCT"].mean(),
        "VAR_PCT_MEDIANA": g["VAR_PCT"].median(),
        "VAR_PCT_ABS_PROM": g["VAR_PCT_ABS"].mean(),
        "FUERA_TOLERANCIA": g["FUERA_TOLERANCIA"].sum(),
    })
    out["% FUERA_TOLERANCIA"] = out["FUERA_TOLERANCIA"] / out["CONSTRUCCIONES"] * 100
    return out.reset_index().sort_values("VAR_PCT_ABS_PROM", ascending=False)


def posibles_enlaces(df_liq: pd.DataFrame, of_sin_cruce: pd.DataFrame) -> pd.DataFrame:
    """
    Hoja de revision manual: toma las ofertas cuyo Id catastral SI existe en
    df_const pero que aun asi NO cruzaron por la llave compuesta
    (ID + USO + AREA), y lista TODAS las construcciones de ese predio con sus
    caracteristicas, para decidir a mano cual es el registro correcto.

    Las ofertas cuyo Id catastral no existe en la liquidacion NO entran aqui:
    no hay nada que revisar. Esas quedan en la hoja OFERTAS_SIN_CRUCE, que
    conserva las 513 completas con su MOTIVO_NO_CRUCE.

    Agrega columnas de apoyo para evaluar cada candidato:
        COINCIDE_USO        si el uso de la construccion es el de la oferta
        DIF_AREA / _PCT     cuanto se aleja el area de la construccion
        CANDIDATO           1 = el mas parecido (mismo uso y area mas cercana)
        VAR_PCT_SI_ENLAZA   que variacion daria si se acepta ese enlace
    """
    if of_sin_cruce.empty:
        return pd.DataFrame()

    of = of_sin_cruce.copy()
    of["_ID"] = _limpiar_id(of["ID_CATASTRAL_OFERTA"])
    of["_USO"] = _limpiar_uso(of["USO_OFERTA"])

    cols_const = [c for c in [
        "ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "ID_CONSTRUCCION",
        "USO_LADM", "AREA_CONST", "VM2_LIQ", "DESTINOCONS", "DESTANEX", "PUNTCONS",
        "TPISCONS", "ANOCONST", "TABLA_ORIGEN", "METODO_LIQUIDACION", "COMUNA",
        "CONDICION", "ESTRPRED", "TIPOUSO", "ESPECIAL_2026", "VM2_MOD",
        "VM2_ESP_2026", "LIQ_PARQUEADERO",
    ] if c in df_liq.columns]

    const = df_liq.loc[df_liq["ID_KEY"].isin(set(of["_ID"])), ["ID_KEY", "USO_KEY"] + cols_const]
    const = const.rename(columns={"USO_KEY": "_USO_CONST"})

    # inner: esta hoja es SOLO para los Id catastral que SI existen en
    # df_const y que aun asi no cruzaron por la llave compuesta. Las ofertas
    # cuyo id no existe no tienen nada que revisar aqui; quedan reportadas
    # en la hoja OFERTAS_SIN_CRUCE con su motivo.
    e = of.merge(const, left_on="_ID", right_on="ID_KEY", how="inner")
    if e.empty:
        return pd.DataFrame()

    e["N_CONST_PREDIO"] = e.groupby("LLAVE")["ID_KEY"].transform("size")
    e["COINCIDE_USO"] = np.where(e["_USO"] == e["_USO_CONST"], "SI", "NO")

    a_of = pd.to_numeric(e["AREA_OFERTA"], errors="coerce")
    a_lq = pd.to_numeric(e["AREA_CONST"], errors="coerce")
    e["DIF_AREA"] = (a_of - a_lq).round(2)
    e["DIF_AREA_PCT"] = np.where(a_lq > 0, (a_of - a_lq) / a_lq * 100, np.nan).round(2)

    # A veces el area de la oferta corresponde al predio COMPLETO (la suma de
    # todas sus construcciones, aunque sean de usos distintos). Si
    # AREA_TOTAL_PREDIO coincide con AREA_OFERTA, la oferta cubre todo el predio.
    e["AREA_TOTAL_PREDIO"] = e.groupby("LLAVE")["AREA_CONST"].transform("sum").round(2)
    e["OFERTA_CUBRE_PREDIO"] = np.where(
        (a_of - e["AREA_TOTAL_PREDIO"]).abs() <= 1, "SI", "NO")

    e["VAR_PCT_SI_ENLAZA"] = np.where(
        pd.to_numeric(e["VM2_LIQ"], errors="coerce") > 0,
        (e["VM2_OFERTA"] - e["VM2_LIQ"]) / e["VM2_LIQ"] * 100, np.nan).round(2)

    # Ranking: primero los del mismo uso, y dentro de esos el area mas cercana.
    orden = np.where(e["COINCIDE_USO"] == "SI", 0, 1) * 1e12 + e["DIF_AREA"].abs().fillna(1e11)
    e["_orden"] = orden
    e["CANDIDATO"] = (e.groupby("LLAVE")["_orden"].rank(method="first")
                       .astype("Int64"))

    e = e.sort_values(["ID_CATASTRAL_OFERTA", "CANDIDATO"])

    salida = [c for c in [
        "ID_CATASTRAL_OFERTA", "USO_OFERTA", "AREA_OFERTA", "VM2_OFERTA",
        "MOTIVO_NO_CRUCE", "N_CONST_PREDIO", "AREA_TOTAL_PREDIO",
        "OFERTA_CUBRE_PREDIO", "CANDIDATO",
        "USO_LADM", "COINCIDE_USO", "AREA_CONST", "DIF_AREA", "DIF_AREA_PCT",
        "VM2_LIQ", "VAR_PCT_SI_ENLAZA",
    ] + cols_const + ["FILAS_OFERTA"] if c in e.columns]
    return e[list(dict.fromkeys(salida))]


def resumen_por_rango(df_comp: pd.DataFrame) -> pd.DataFrame:
    if df_comp.empty:
        return pd.DataFrame()
    out = (df_comp["RANGO_VARIACION"].value_counts().sort_index()
           .rename_axis("RANGO_VARIACION").reset_index(name="CONSTRUCCIONES"))
    out["PARTICIPACION_PCT"] = out["CONSTRUCCIONES"] / out["CONSTRUCCIONES"].sum() * 100
    return out


# =====================================================================
# GRAFICOS
# =====================================================================
# Paleta fija (modo claro). Los dos colores de serie son los slots 1 y 2 de la
# paleta categorica de referencia, que estan validados para uso all-pairs
# (dispersion) sin que se confundan bajo daltonismo.
VIZ = {
    "surface":   "#fcfcfb",   # fondo del grafico
    "ink":       "#0b0b0b",   # titulo
    "ink_2":     "#52514e",   # subtitulo / leyenda / etiquetas de eje
    "muted":     "#898781",   # ticks
    "grid":      "#e1e0d9",   # rejilla (hairline, solida, nunca punteada)
    "axis":      "#c3c2b7",   # eje / linea base
    "serie_1":   "#2a78d6",   # azul   -> LIQUIDACION
    "serie_2":   "#eb6834",   # naranja-> OFERTA
}


def _estilo_ejes(ax, titulo="", subtitulo="", xlabel="", ylabel=""):
    """Rejilla hairline, ejes recesivos, tipografia del sistema."""
    ax.set_facecolor(VIZ["surface"])
    ax.grid(True, color=VIZ["grid"], linewidth=0.8, linestyle="-", zorder=0)
    ax.set_axisbelow(True)
    for lado in ("top", "right"):
        ax.spines[lado].set_visible(False)
    for lado in ("left", "bottom"):
        ax.spines[lado].set_color(VIZ["axis"])
        ax.spines[lado].set_linewidth(1.0)
    ax.tick_params(colors=VIZ["muted"], labelsize=9, length=0)
    for t in ax.get_xticklabels() + ax.get_yticklabels():
        t.set_color(VIZ["ink_2"])
    if titulo:
        ax.set_title(titulo, color=VIZ["ink"], fontsize=13, fontweight="600",
                     loc="left", pad=32 if subtitulo else 10)
    if subtitulo:
        # Desplazamiento en PUNTOS (no en fraccion de ejes): asi el subtitulo
        # queda a la misma distancia del titulo sin importar el alto de la figura.
        ax.annotate(subtitulo, xy=(0, 1), xycoords="axes fraction",
                    xytext=(0, 8), textcoords="offset points",
                    color=VIZ["ink_2"], fontsize=9.5, va="bottom", ha="left")
    ax.set_xlabel(xlabel, color=VIZ["ink_2"], fontsize=10)
    ax.set_ylabel(ylabel, color=VIZ["ink_2"], fontsize=10)


def graficos_comparacion(df_comp: pd.DataFrame, carpeta: str, fecha: str) -> list[str]:
    """
    Genera los graficos de la comparacion VM2 liquidacion vs oferta.

    Sale un grafico de resumen con todas las categorias residenciales y
    ADEMAS un grafico por cada categoria (011, 012, ... 016) con el detalle
    oferta a oferta.

    Solo entran las ofertas COMPARABLES: las que cruzaron y ademas tienen
    VM2 liquidado > 0. Las que quedaron en 0 (usos que no liquidan por falta
    de tabla) no producen variacion y distorsionarian todo, asi que se
    excluyen y se informa cuantas fueron.
    """
    try:
        import matplotlib
        matplotlib.use("Agg")                     # sin ventanas, solo archivos
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError:
        print("   ! matplotlib no esta instalado: se omiten los graficos "
              "(pip install matplotlib)")
        return []

    comp = df_comp[df_comp["VM2_LIQ"] > 0].copy()
    n_cero = len(df_comp) - len(comp)
    if comp.empty:
        print("   ! No hay ofertas comparables con VM2 liquidado > 0: sin graficos")
        return []

    os.makedirs(carpeta, exist_ok=True)
    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans", "sans-serif"]
    miles = FuncFormatter(lambda v, _: f"{v:,.0f}".replace(",", "."))
    tol = float(CONFIG["tolerancia_pct"])
    pie = f"{len(comp):,} ofertas comparables" + (
        f"  ·  {n_cero:,} excluidas por VM2 liquidado = 0" if n_cero else "")
    generados = []

    def _guardar(fig, nombre):
        ruta = os.path.join(carpeta, f"{nombre}_{fecha}.png")
        fig.savefig(ruta, dpi=160, facecolor=VIZ["surface"], bbox_inches="tight")
        plt.close(fig)
        generados.append(ruta)

    # -----------------------------------------------------------------
    # EL GRAFICO (uno solo, reutilizado): dos lineas -liquidacion y oferta-
    # recorriendo un eje X que tiene orden natural. Es el mismo cuadro para
    # el resumen y para cada categoria; lo unico que cambia es que recorre
    # el eje X: las categorias en el resumen, los rangos de puntaje adentro
    # de cada categoria.
    # -----------------------------------------------------------------
    def _lineas(g, titulo, subtitulo, xlabel, etiquetas, nombre,
                ylabel="VM2 mediano (COP/m2)"):
        """g: DataFrame ya ordenado con columnas LIQ y OFE."""
        fig, ax = plt.subplots(figsize=(9.5, 6), facecolor=VIZ["surface"])
        _estilo_ejes(ax, titulo, subtitulo, xlabel, ylabel)

        x = np.arange(len(g))
        series = [("LIQ", VIZ["serie_1"], "Liquidacion"),
                  ("OFE", VIZ["serie_2"], "Oferta")]
        for col, color, etiqueta in series:
            ax.plot(x, g[col], color=color, linewidth=2, solid_capstyle="round",
                    solid_joinstyle="round", zorder=3, label=etiqueta)
            ax.scatter(x, g[col], s=70, color=color, zorder=4,
                       edgecolors=VIZ["surface"], linewidths=2)

        # Etiquetas directas solo en los extremos de cada linea (nunca en todos
        # los puntos): son las que cuentan la historia del cruce entre las dos.
        # En el extremo izquierdo van arriba/abajo del punto y no a su costado,
        # porque ahi se montarian sobre los numeros del eje Y. idxmax define
        # cual va arriba, asi que en un empate no se van las dos al mismo lado.
        cols = [c for c, _, _ in series]
        tope = float(max(g["LIQ"].max(), g["OFE"].max())) * 1.22
        alto_ini = g[cols].iloc[0].idxmax()
        alto_fin = g[cols].iloc[-1].idxmax()
        # Si las dos lineas terminan casi en el mismo valor, las etiquetas de la
        # derecha tambien se separan; si no, quedan una encima de la otra.
        juntas = (len(g) > 1
                  and abs(g[cols[0]].iloc[-1] - g[cols[1]].iloc[-1]) < 0.06 * tope)
        for col, color, _ in series:
            arriba = col == alto_ini
            ax.annotate(f"{g[col].iloc[0]:,.0f}".replace(",", "."),
                        xy=(x[0], g[col].iloc[0]),
                        xytext=(0, 13 if arriba else -13), textcoords="offset points",
                        color=VIZ["ink_2"], fontsize=9.5, ha="center",
                        va="bottom" if arriba else "top")
            if len(g) > 1:
                dy = 0 if not juntas else (8 if col == alto_fin else -8)
                ax.annotate(f"{g[col].iloc[-1]:,.0f}".replace(",", "."),
                            xy=(x[-1], g[col].iloc[-1]), xytext=(10, dy),
                            textcoords="offset points", color=VIZ["ink_2"],
                            fontsize=9.5, va="center", ha="left")

        ax.set_xticks(x)
        ax.set_xticklabels(etiquetas, fontsize=10)
        ax.set_xlim(-0.45, len(g) - 0.55)
        ax.set_ylim(0, tope)
        ax.yaxis.set_major_formatter(miles)
        # La leyenda se va al arriba del extremo mas BAJO: en el extremo alto
        # esta la etiqueta del valor y se montarian una sobre otra.
        esquina = ("upper right" if g[cols].iloc[0].max() >= g[cols].iloc[-1].max()
                   else "upper left")
        leg = ax.legend(frameon=False, loc=esquina, fontsize=10)
        for t in leg.get_texts():
            t.set_color(VIZ["ink_2"])
        _guardar(fig, nombre)

    def _medianas(df, por):
        return (df.groupby(por)
                  .agg(N=("VM2_LIQ", "size"), LIQ=("VM2_LIQ", "median"),
                       OFE=("VM2_OFERTA", "median"))
                  .sort_index())

    # Familias de tablas que se grafican. Las dos tienen categorias 011..016
    # que son una escala ordenada (de la tipologia mas basica a la mejor), que
    # es lo que hace legible una linea: el eje X tiene orden natural.
    FAMILIAS = [("T1_RESIDENCIAL", "RESIDENCIAL"), ("T2_EDIFICIOS", "EDIFICIOS")]

    # --- Un cuadro de resumen por familia, mas DOS por categoria ------------
    # Los dos son la misma figura de lineas; cambia el eje X, y cada uno
    # responde una pregunta distinta:
    #
    #  (a) POR PUNTAJE: el puntaje es la variable con la que esta construida
    #      la tabla de liquidacion, asi que este es el que dice QUE FILA de la
    #      tabla corregir. Cada punto es la mediana del rango.
    #
    #  (b) POR PERCENTIL: cada serie ordenada de menor a mayor por separado.
    #      Este es el que DIAGNOSTICA, porque muestra lo que la mediana
    #      esconde: si la brecha esta pareja en toda la distribucion (nivel de
    #      la tabla mal puesto) o si se abre y se cierra entre las colas
    #      (la tabla no tiene la pendiente del mercado), y cuanto se abre cada
    #      serie. Ahi se ve que la liquidacion comprime el rango: su p90/p10
    #      da ~2x en todas las categorias mientras el mercado llega a 3x.
    ANCHO = 10                          # ancho del rango de puntaje
    MIN_OFERTAS = 5                     # por debajo de esto la mediana no dice nada
    MIN_RANGOS = 2                      # con un solo punto no hay linea que trazar
    # Una curva de percentiles necesita muestra: con pocas ofertas p05 y p95 no
    # son percentiles, son el minimo y el maximo disfrazados.
    MIN_PERCENTILES = 15
    PCTS = [5, 10, 20, 25, 30, 40, 50, 60, 70, 75, 80, 90, 95]
    hay_punt = "PUNTCONS" in comp.columns
    if not hay_punt:
        print("   ! No hay columna PUNTCONS: no se puede abrir cada categoria "
              "por rango de puntaje")

    i = 1
    for PREFIJO, FAMILIA in FAMILIAS:
        fam = comp[comp["TABLA_ORIGEN"].astype(str).str.startswith(PREFIJO)]
        if fam.empty:
            print(f"   ! Ninguna oferta cruzo contra una tabla {PREFIJO}: "
                  f"se omite {FAMILIA.lower()}")
            continue
        nombre = FAMILIA.capitalize()
        omitidas = []

        # --- resumen: una posicion por categoria ----------------------------
        g = _medianas(fam, "TABLA_ORIGEN")
        otras = len(comp) - len(fam)
        _lineas(g,
                f"Valor m2 construido por categoria {FAMILIA.lower()}",
                f"p50 de cada serie por categoria  ·  {len(fam):,} ofertas"
                + (f"  ·  {otras:,} de otras tablas quedan fuera" if otras else ""),
                f"Categoria {PREFIJO}",
                [str(t).replace(PREFIJO + "_", "") + f"\n(n={int(n)})"
                 for t, n in zip(g.index, g["N"])],
                f"{i}_RESUMEN_{FAMILIA}")
        i += 1

        if not hay_punt:
            continue

        # --- dos cuadros por categoria --------------------------------------
        for tabla, sub in fam.groupby("TABLA_ORIGEN"):
            cat = str(tabla).replace(PREFIJO + "_", "")
            sub = sub.copy()
            punt = pd.to_numeric(sub["PUNTCONS"], errors="coerce")
            sin_punt = int(punt.isna().sum())
            sub, punt = sub[punt.notna()], punt[punt.notna()]
            if len(sub) < MIN_OFERTAS:
                omitidas.append(f"{cat} (n={len(sub)})")
                continue

            var = (sub["VM2_OFERTA"] - sub["VM2_LIQ"]) / sub["VM2_LIQ"] * 100

            # (a) por rango de puntaje ---------------------------------------
            sub["_RANGO"] = (punt // ANCHO * ANCHO).astype(int)
            gc = _medianas(sub, "_RANGO")
            if len(gc) < MIN_RANGOS:
                omitidas.append(f"{cat} (un solo rango de puntaje)")
            else:
                _lineas(gc,
                        f"{nombre} {cat}: valor m2 liquidado vs ofertado",
                        # OJO: las dos lineas son la mediana de CADA columna por
                        # separado, no una comparacion pareada. La variacion del
                        # subtitulo si es pareada (oferta contra su liquidacion),
                        # asi que no tiene por que coincidir con la brecha que se
                        # ve entre las lineas: por eso se dice de donde sale cada una.
                        f"p50 de cada serie por rango de puntaje  ·  {len(sub):,} ofertas"
                        f"  ·  variacion mediana oferta a oferta {var.median():+.0f}%"
                        f"  ·  {(var.abs() > tol).mean() * 100:.0f}% fuera de ±{tol:.0f}%"
                        + (f"  ·  {sin_punt} sin puntaje quedan fuera" if sin_punt else ""),
                        "Rango de puntaje de la construccion",
                        [f"{r}-{r + ANCHO - 1}\n(n={int(n)})"
                         for r, n in zip(gc.index, gc["N"])],
                        f"{i}_{FAMILIA}_{cat}_PUNTAJE")
                i += 1

            # (b) por percentil ----------------------------------------------
            if len(sub) < MIN_PERCENTILES:
                omitidas.append(f"{cat} (n={len(sub)}, sin curva de percentiles)")
                continue
            v_liq = pd.to_numeric(sub["VM2_LIQ"], errors="coerce").dropna()
            v_ofe = pd.to_numeric(sub["VM2_OFERTA"], errors="coerce").dropna()
            gp = pd.DataFrame({"LIQ": np.percentile(v_liq, PCTS),
                               "OFE": np.percentile(v_ofe, PCTS)},
                              index=[f"p{p:02d}" for p in PCTS])
            # Amplitud p90/p10: cuanto abre cada serie de punta a punta. Es la
            # comparacion que dice si la tabla acompaña la dispersion real.
            p10, p90 = PCTS.index(10), PCTS.index(90)
            amp = ""
            if gp["LIQ"].iloc[p10] > 0 and gp["OFE"].iloc[p10] > 0:
                amp = (f"  ·  amplitud p90/p10: liquidacion "
                       f"{gp['LIQ'].iloc[p90] / gp['LIQ'].iloc[p10]:.1f}x, oferta "
                       f"{gp['OFE'].iloc[p90] / gp['OFE'].iloc[p10]:.1f}x")
            _lineas(gp,
                    f"{nombre} {cat}: distribucion de valores",
                    f"cada serie ordenada por separado  ·  {len(sub):,} ofertas"
                    f"  ·  brecha p10 {(gp['OFE'].iloc[p10] / gp['LIQ'].iloc[p10] - 1) * 100:+.0f}%"
                    f", p90 {(gp['OFE'].iloc[p90] / gp['LIQ'].iloc[p90] - 1) * 100:+.0f}%"
                    + amp,
                    "Percentil de la distribucion",
                    list(gp.index),
                    f"{i}_{FAMILIA}_{cat}_PERCENTILES",
                    ylabel="VM2 del percentil (COP/m2)")
            i += 1

        if omitidas:
            print(f"   ({FAMILIA.lower()}: sin cuadro propio -> "
                  f"{', '.join(omitidas)})")

    if not generados:
        print("   ! No hubo ninguna tabla graficable")
        return []

    print(f"   Graficos generados en {carpeta}:")
    for r in generados:
        print(f"     - {os.path.basename(r)}")
    return generados


# =====================================================================
# EXPORTACION
# =====================================================================
COLS_REPORTE = [
    # identificacion (texto original de cada base, sin modificar)
    "ID_CATASTRAL_OFERTA", "ID_PREDIO", "NUMERO_PREDIAL_NACIONAL",
    "USO_OFERTA", "USO_LADM", "USO_COINCIDE_EXACTO",
    "AREA_OFERTA", "AREA_CONST", "DIF_AREA", "DIF_AREA_PCT",
    "N_CONST_USO", "AREA_CONST_TOTAL", "LLAVE",
    # comparacion
    "VM2_OFERTA", "VM2_LIQ", "DIF_ABS", "VAR_PCT", "VAR_PCT_ABS",
    "RAZON_LIQ_OFERTA", "SENTIDO", "RANGO_VARIACION", "FUERA_TOLERANCIA",
    "IMPACTO_AVALUO", "ORIGEN_MATCH",
    # trazabilidad de duplicados
    "N_OFERTAS", "DUPLICADO_OFERTA", "VM2_OFERTA_MIN", "VM2_OFERTA_MAX",
    "N_CONSTRUCCIONES", "DUPLICADO_LIQUIDACION", "VM2_LIQ_MIN", "VM2_LIQ_MAX",
    "VM2_LIQ_DISTINTOS", "ALERTA_VM2_LIQ", "CONSTRUCCIONES_LLAVE",
    "CONSTRUCCION_ID", "ESTRATEGIA_DUP", "FILAS_OFERTA",
]

# Formatos por nombre de columna (xlsxwriter)
FORMATOS = {
    "#,##0": ["VM2_LIQ", "VM2_OFERTA", "DIF_ABS", "VM2_OFERTA_MIN", "VM2_OFERTA_MAX",
              "VM2_LIQ_MIN", "VM2_LIQ_MAX", "VALOR_M2_CONSTRUIDO_OFERTA",
              "IMPACTO_AVALUO", "VALOR_MIN", "VALOR_MAX", "VALOR_PROM", "VALOR_MEDIANA",
              "VM2_LIQ_PROM", "VM2_OFERTA_PROM", "VM2_MOD", "VM2_ESP_2026",
              "LIQ_PARQUEADERO", "VALORCONS"],
    "#,##0.00": ["VAR_PCT", "VAR_PCT_ABS", "DISPERSION_PCT", "AREA_CONST", "AREA_OFERTA",
                 "AREA_CONST_TOTAL", "VAR_PCT_PROM", "VAR_PCT_MEDIANA",
                 "VAR_PCT_ABS_PROM", "% FUERA_TOLERANCIA", "PARTICIPACION_PCT",
                 "DIF_AREA", "DIF_AREA_PCT", "VAR_PCT_SI_ENLAZA", "AREA_TOTAL_PREDIO"],
    "#,##0.000": ["RAZON_LIQ_OFERTA"],
}


def _ordenar_cols(df: pd.DataFrame) -> pd.DataFrame:
    """Ordena las columnas del reporte y elimina las internas de trabajo."""
    if df is None or df.empty:
        return df
    primero = [c for c in COLS_REPORTE if c in df.columns]
    resto = [c for c in df.columns if c not in primero and c not in COLS_INTERNAS]
    return df[primero + resto]


def _recortar_comparacion(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja la hoja COMPARACION con las columnas de CONFIG['columnas_comparacion'].
    Si la lista esta vacia o es None, no recorta nada.
    Las columnas pedidas que no existan en el df se avisan y se omiten.
    """
    pedidas = CONFIG.get("columnas_comparacion")
    if df is None or df.empty or not pedidas:
        return df
    hay = [c for c in pedidas if c in df.columns]
    faltan = [c for c in pedidas if c not in df.columns]
    if faltan:
        print(f"   (COMPARACION: columnas pedidas que no existen, se omiten: {faltan})")
    return df[hay]


def _png_tamano(ruta: str) -> tuple[int, int]:
    """Ancho y alto de un PNG leyendo su cabecera IHDR (sin depender de Pillow)."""
    with open(ruta, "rb") as f:
        cab = f.read(24)
    return int.from_bytes(cab[16:20], "big"), int.from_bytes(cab[20:24], "big")


def _hoja_graficos(libro, hoja, rutas: list[str], escala: float = 0.55) -> None:
    """Pega los PNG uno debajo del otro en la hoja GRAFICOS del Excel."""
    fmt_tit = libro.add_format({"bold": True, "font_size": 12, "font_color": "#0b0b0b"})
    hoja.hide_gridlines(2)
    hoja.set_column(0, 0, 3)

    fila = 1
    for r in rutas:
        if not os.path.exists(r):
            continue
        nombre = os.path.splitext(os.path.basename(r))[0]
        # "1_DISPERSION_LIQ_VS_OFERTA_20260805" -> "1. DISPERSION LIQ VS OFERTA"
        partes = nombre.split("_")
        titulo = partes[0] + ". " + " ".join(partes[1:-1]).replace("-", " ")
        hoja.write(fila, 1, titulo, fmt_tit)
        hoja.insert_image(fila + 1, 1, r, {"x_scale": escala, "y_scale": escala})
        _, alto = _png_tamano(r)
        fila += int(alto * escala / 20) + 4      # alto de fila por defecto ~20 px


def exportar_excel(hojas: dict[str, pd.DataFrame], ruta: str,
                   graficos: list[str] | None = None) -> str:
    """Escribe el Excel con formato (anchos, filtros, congelado, formatos numericos)."""
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)

    # Como el archivo del dia se sobrescribe, si esta abierto en Excel Windows
    # bloquea la escritura. Se avisa claro en vez de reventar con un error raro.
    if os.path.exists(ruta):
        try:
            with open(ruta, "a+b"):
                pass
        except PermissionError:
            raise PermissionError(
                f"No se pudo sobrescribir '{os.path.basename(ruta)}': el archivo "
                f"esta abierto en Excel.\n"
                f"   Cierrelo y vuelva a correr el proceso."
            ) from None

    limite = CONFIG["max_filas_hoja"]
    mapa_fmt = {col: fmt for fmt, cols in FORMATOS.items() for col in cols}

    with pd.ExcelWriter(ruta, engine="xlsxwriter") as xw:
        libro = xw.book
        f_head = libro.add_format({"bold": True, "bg_color": "#1F4E78", "font_color": "white",
                                   "border": 1, "align": "center", "valign": "vcenter",
                                   "text_wrap": True})
        f_pos = libro.add_format({"bg_color": "#C6EFCE", "font_color": "#006100"})
        f_neg = libro.add_format({"bg_color": "#FFC7CE", "font_color": "#9C0006"})
        cache_fmt = {f: libro.add_format({"num_format": f}) for f in FORMATOS}

        for nombre, df in hojas.items():
            # Hoja de imagenes: no lleva datos, lleva los PNG incrustados.
            if nombre == "GRAFICOS":
                if graficos:
                    _hoja_graficos(libro, libro.add_worksheet(nombre), graficos)
                continue
            if df is None:
                continue
            d = df.copy()

            if len(d) > limite:
                csv = os.path.splitext(ruta)[0] + f"_{nombre}.csv"
                d.to_csv(csv, sep="|", index=False, encoding="utf-8-sig")
                print(f"   ! Hoja '{nombre}' con {len(d):,} filas -> volcada completa a CSV: "
                      f"{os.path.basename(csv)} (en Excel van {limite:,})")
                d = d.head(limite)

            if d.empty:
                d = pd.DataFrame({"SIN REGISTROS": ["No se generaron registros"]})

            # Un encabezado repetido rompe el formateo (d[col] devolveria un
            # DataFrame en vez de una Serie): se desduplica antes de escribir.
            if d.columns.duplicated().any():
                repes = sorted(set(d.columns[d.columns.duplicated()]))
                print(f"   ! Hoja '{nombre}': columnas repetidas {repes}, se deja la primera")
                d = d.loc[:, ~d.columns.duplicated()]

            # xlsxwriter no escribe categoricos ni fechas raras
            for c in d.columns:
                if isinstance(d[c].dtype, pd.CategoricalDtype):
                    d[c] = d[c].astype(str)

            d.to_excel(xw, sheet_name=nombre[:31], index=False)
            ws = xw.sheets[nombre[:31]]
            ws.freeze_panes(1, 0)

            for i, col in enumerate(d.columns):
                ws.write(0, i, str(col), f_head)
                largo_datos = int(d[col].astype(str).str.len().head(1000).max() or 12)
                ancho = min(max(12, largo_datos + 3, len(str(col)) + 3), 34)
                fmt = cache_fmt.get(mapa_fmt.get(col))
                ws.set_column(i, i, ancho, fmt)

            if len(d) and nombre != "RESUMEN":
                ws.autofilter(0, 0, len(d), len(d.columns) - 1)

            if "VAR_PCT" in d.columns and len(d):
                j = list(d.columns).index("VAR_PCT")
                ws.conditional_format(1, j, len(d), j,
                                      {"type": "cell", "criteria": ">", "value": 0,
                                       "format": f_pos})
                ws.conditional_format(1, j, len(d), j,
                                      {"type": "cell", "criteria": "<", "value": 0,
                                       "format": f_neg})
    return ruta


# =====================================================================
# ORQUESTADOR
# =====================================================================
def comparacion_ofertas(df_const_liq: pd.DataFrame | None = None,
                        ruta_ofertas: str | None = None,
                        hoja_ofertas=0,
                        tolerancia_pct: float | None = None,
                        estrategia_duplicados: str | None = None,
                        exportar: bool = True,
                        ruta_salida: str | None = None) -> pd.DataFrame:
    """
    Ejecuta la comparacion VM2 liquidacion vs ofertas.

    Parametros
    ----------
    df_const_liq : DataFrame de construcciones liquidadas (con VM2). Si es None se
                   lee ./output/LIQUIDACION_TABLAS.parquet
    ruta_ofertas : ruta del archivo de ofertas. Si es None se autodetecta en ./input/
    tolerancia_pct : % de variacion aceptada (default CONFIG)
    estrategia_duplicados : alertar | promedio | mediana | max | min | primero

    Retorna
    -------
    DataFrame de comparacion (una fila por construccion cruzada).
    """
    if tolerancia_pct is not None:
        CONFIG["tolerancia_pct"] = float(tolerancia_pct)
    if estrategia_duplicados is not None:
        CONFIG["estrategia_duplicados_ofertas"] = estrategia_duplicados

    # Solo se reinicia el cronometro si se corre standalone: llamarlo desde
    # main.py borraria las marcas de los pasos anteriores.
    if df_const_liq is None:
        crono.inicio("COMPARACION OFERTAS")

    print("\n" + "=" * 60)
    print("=== COMPARACION VM2: LIQUIDACION vs OFERTAS ===")
    print("=" * 60)

    # 1) Cargar y filtrar las ofertas por valor de construccion --------------
    print("\n-- PASO 1: carga y filtro de ofertas por valor de construccion")
    df_liq = cargar_liquidacion(df_const_liq)
    df_of = cargar_ofertas(ruta_ofertas, hoja_ofertas)
    archivo_ofertas = df_of.attrs.get("archivo", "")
    filas_archivo = df_of.attrs.get("filas_archivo", len(df_of))
    descartadas = df_of.attrs.get("descartadas_sin_valor", 0)
    crono.marca("COMPARACION: carga de datos")

    # 2) Llaves (solo sobre las ofertas ya filtradas) ------------------------
    print("\n-- PASO 2: armado de la llave compuesta")
    r = CONFIG["redondeo_area"]
    col_id_liq = _elegir_columna_id(df_liq, df_of)
    df_liq = _armar_llaves(df_liq, r, col_id=col_id_liq)
    df_of = _armar_llaves(df_of, r, col_id="ID_PREDIO")
    df_liq = _descartar_llaves_invalidas(df_liq, "LIQUIDACION")
    df_of = _descartar_llaves_invalidas(df_of, "OFERTAS")
    print(f"\n-- Llave compuesta: {col_id_liq} + USO_LADM + AREA_CONST "
          f"(redondeo {r} decimales, usos {'normalizados' if CONFIG['normalizar_uso'] else 'literales'})")
    print("   (los nombres de los usos NO se modifican: la normalizacion solo")
    print("    se aplica a la columna interna USO_KEY para poder cruzar)")

    # 3) Duplicados ---------------------------------------------------------
    print("\n-- Deteccion de duplicados por llave")
    dup_of, res_of = detectar_duplicados(df_of, "VM2_OFERTA", "OFERTAS")
    dup_liq, res_liq = detectar_duplicados(df_liq, "VM2_LIQ", "LIQUIDACION")
    crono.marca("COMPARACION: duplicados")

    df_of_res = resolver_duplicados_ofertas(df_of, CONFIG["estrategia_duplicados_ofertas"])

    # 4) Comparar (a nivel oferta) -------------------------------------------
    print("\n-- PASO 3: cruce y comparacion de valores (una fila por oferta)")
    df_comp, of_sin_predio = comparar(df_liq, df_of_res)

    if len(of_sin_predio):
        ids_liq = set(df_liq["ID_KEY"].dropna())
        llaves2_liq = set(df_liq["LLAVE_2"])
        of_sin_predio["MOTIVO_NO_CRUCE"] = np.select(
            [of_sin_predio["LLAVE_2"].isin(llaves2_liq),
             of_sin_predio["ID_CATASTRAL_OFERTA"].map(
                 lambda v: _limpiar_id(pd.Series([v])).iloc[0]).isin(ids_liq)],
            ["Coincide predio y uso, pero NO el area construida",
             "El predio existe pero no coincide el USO"],
            default="El Id catastral no existe en la liquidacion")

    n_liq = len(df_liq)
    n_of_llaves = len(df_of_res)
    n_ok = len(df_comp)
    n_const = int(df_comp["N_CONSTRUCCIONES"].sum()) if n_ok else 0
    fuera = int(df_comp["FUERA_TOLERANCIA"].sum()) if n_ok else 0
    print(f"   Ofertas validas                 : {len(df_of):,}")
    print(f"   Llaves de oferta a comparar     : {n_of_llaves:,}")
    print(f"   Ofertas que cruzaron            : {n_ok:,} "
          f"({(n_ok/n_of_llaves*100 if n_of_llaves else 0):.2f}%)")
    if n_ok:
        for org, cnt in df_comp["ORIGEN_MATCH"].value_counts().items():
            print(f"      - {org:<28}: {cnt:,}")
    print(f"   Ofertas sin construccion        : {len(of_sin_predio):,}")
    print(f"   Construcciones involucradas     : {n_const:,} "
          f"(de {len(df_liq):,} liquidadas)")
    n_calc = int((df_comp["VM2_LIQ"] > 0).sum()) if n_ok else 0
    n_cero = n_ok - n_calc
    if n_ok:
        if n_cero:
            print(f"   ** OJO: {n_cero:,} de {n_ok:,} cruces tienen VM2 = 0 en la "
                  f"liquidacion ({n_cero/n_ok*100:.1f}%)")
            print(f"      -> esas NO producen variacion. Las estadisticas de abajo "
                  f"salen sobre {n_calc:,} ofertas.")
        print(f"   Variacion calculable en          : {n_calc:,} ofertas")
        print(f"   VM2 liquidacion promedio        : {df_comp.loc[df_comp['VM2_LIQ']>0,'VM2_LIQ'].mean():,.0f}")
        print(f"   VM2 oferta promedio             : {df_comp.loc[df_comp['VM2_LIQ']>0,'VM2_OFERTA'].mean():,.0f}")
        print(f"   Variacion % promedio            : {df_comp['VAR_PCT'].mean():.2f}%")
        print(f"   Variacion % mediana             : {df_comp['VAR_PCT'].median():.2f}%")
        print(f"   Fuera de tolerancia (+-{CONFIG['tolerancia_pct']:.1f}%) : "
              f"{fuera:,} ({fuera/n_calc*100:.2f}% de las calculables)"
              if n_calc else "   Fuera de tolerancia: n/a")
    else:
        print("   ** No hubo cruces. Revise que el 'Id catastral', el uso y el area")
        print("      de las ofertas correspondan a los de la liquidacion")
        print("      (pruebe CONFIG['redondeo_area']=0 o revise la hoja OFERTAS_SIN_CRUCE).")
    crono.marca("COMPARACION: cruce y variaciones")

    # Detalle: solo las construcciones que participaron en la comparacion.
    detalle = pd.DataFrame()
    if "DETALLE_CONSTRUCCIONES" in CONFIG["hojas_exportar"] and n_ok:
        detalle = (df_liq[df_liq["LLAVE"].isin(set(df_comp["LLAVE"]))]
                   .merge(df_comp[["LLAVE", "VM2_OFERTA", "USO_OFERTA", "N_OFERTAS"]]
                          .drop_duplicates("LLAVE"), on="LLAVE", how="left"))
        detalle["DIF_ABS"] = detalle["VM2_OFERTA"] - detalle["VM2_LIQ"]
        detalle["VAR_PCT"] = np.where(detalle["VM2_LIQ"] > 0,
                                      detalle["DIF_ABS"] / detalle["VM2_LIQ"] * 100, np.nan)
        detalle = detalle.sort_values(["LLAVE", "VM2_LIQ"])

    if not exportar:
        return df_comp

    # 5) Resumen ------------------------------------------------------------
    filas_resumen = [
        ("Fecha de ejecucion", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Archivo de ofertas", archivo_ofertas),
        ("Llave de cruce", f"{col_id_liq} + USO_LADM + AREA_CONST (redondeo {r})"),
        ("Normalizacion de usos en la llave",
         "SI (solo en USO_KEY, no cambia nombres)" if CONFIG["normalizar_uso"] else "NO (literal)"),
        ("Nivel 2: ID+USO con area mas cercana",
         "SI" if CONFIG["match_uso_area_cercana"] else "NO"),
        ("Estrategia duplicados ofertas", CONFIG["estrategia_duplicados_ofertas"]),
        ("Tolerancia (%)", CONFIG["tolerancia_pct"]),
        ("Nivel del reporte", "OFERTA (una fila por llave de oferta)"),
        ("--- PASO 1: FILTRO DE OFERTAS ---", ""),
        ("Filas leidas del archivo", filas_archivo),
        ("Descartadas sin valor de construccion", descartadas),
        ("Ofertas con valor de construccion", len(df_of)),
        ("--- PASO 2/3: LLAVE Y COMPARACION ---", ""),
        ("Llaves de oferta a comparar", n_of_llaves),
        ("Ofertas que cruzaron", n_ok),
        ("% cruce sobre las ofertas", round(n_ok / n_of_llaves * 100, 2) if n_of_llaves else 0),
        *[(f"  por {org}", int(cnt))
          for org, cnt in (df_comp["ORIGEN_MATCH"].value_counts().items() if n_ok else [])],
        ("Ofertas sin construccion", len(of_sin_predio)),
        ("Construcciones involucradas", n_const),
        ("Construcciones liquidadas (total base)", n_liq),
        ("--- DUPLICADOS (ALERTA) ---", ""),
        ("Llaves duplicadas en OFERTAS", res_of["llaves_duplicadas"]),
        ("  filas involucradas", res_of["filas_en_duplicado"]),
        ("  ... con valor distinto (CRITICO)", res_of["llaves_dup_con_valor_distinto"]),
        ("Llaves duplicadas en LIQUIDACION (toda la base)", res_liq["llaves_duplicadas"]),
        ("  ... con VM2 distinto (CRITICO)", res_liq["llaves_dup_con_valor_distinto"]),
        ("Llaves duplicadas que SI afectan la comparacion",
         int((df_comp["N_CONSTRUCCIONES"] > 1).sum()) if n_ok else 0),
        ("  ... y ademas con VM2 distinto (CRITICO)",
         int((df_comp["VM2_LIQ_DISTINTOS"] > 1).sum()) if n_ok else 0),
        ("--- VARIACIONES ---", ""),
        ("Cruces con VM2 liquidado = 0 (sin variacion)", n_cero),
        ("Cruces con variacion calculable", n_calc),
        ("VM2 liquidacion promedio",
         round(df_comp.loc[df_comp["VM2_LIQ"] > 0, "VM2_LIQ"].mean(), 0) if n_calc else 0),
        ("VM2 oferta promedio",
         round(df_comp.loc[df_comp["VM2_LIQ"] > 0, "VM2_OFERTA"].mean(), 0) if n_calc else 0),
        ("Variacion % promedio", round(df_comp["VAR_PCT"].mean(), 2) if n_ok else 0),
        ("Variacion % mediana", round(df_comp["VAR_PCT"].median(), 2) if n_ok else 0),
        ("Variacion % minima", round(df_comp["VAR_PCT"].min(), 2) if n_ok else 0),
        ("Variacion % maxima", round(df_comp["VAR_PCT"].max(), 2) if n_ok else 0),
        ("Fuera de tolerancia", fuera),
        ("% fuera de tolerancia", round(fuera / n_ok * 100, 2) if n_ok else 0),
    ]
    if n_ok:
        for rango, cnt in df_comp["RANGO_VARIACION"].value_counts().sort_index().items():
            filas_resumen.append((f"Rango {rango}", int(cnt)))
        if "IMPACTO_AVALUO" in df_comp.columns:
            filas_resumen.append(("Impacto estimado en avaluo (dif*area)",
                                  round(df_comp["IMPACTO_AVALUO"].sum(), 0)))
    df_resumen = pd.DataFrame(filas_resumen, columns=["INDICADOR", "VALOR"])

    # Nombre por FECHA (sin hora): si se corre varias veces el mismo dia se
    # sobrescribe el mismo archivo; al dia siguiente se crea uno nuevo.
    fecha = datetime.now().strftime("%Y%m%d")
    ruta = ruta_salida or os.path.join(CONFIG["carpeta_results"],
                                       f"COMPARACION_OFERTAS_{fecha}.xlsx")

    # DUP_OFERTAS sale de la base cruda de ofertas, donde el uso y el id vienen
    # en columnas llamadas USO_LADM / ID_PREDIO. Se renombra el ENCABEZADO para
    # que no se confunda con el de la liquidacion (el texto sigue intacto).
    ren_of = {"USO_LADM": "USO_OFERTA", "ID_PREDIO": "ID_CATASTRAL_OFERTA",
              "VM2_OFERTA": "VALOR_M2_CONSTRUIDO_OFERTA"}

    # Las ofertas sin cruce no tienen lado liquidacion: se quitan esas columnas
    # (irian todas vacias) y se dejan solo los datos de la oferta y el motivo.
    cols_sin_cruce = [c for c in ["ID_CATASTRAL_OFERTA", "USO_OFERTA", "AREA_OFERTA",
                                  "VM2_OFERTA", "N_OFERTAS", "LLAVE", "FILAS_OFERTA",
                                  "MOTIVO_NO_CRUCE"] if c in of_sin_predio.columns]
    of_sin_predio = of_sin_predio[cols_sin_cruce] if cols_sin_cruce else of_sin_predio

    # Candidatos de enlace para las ofertas que no cruzaron.
    enlaces = pd.DataFrame()
    if "POSIBLE_ENLACE" in CONFIG["hojas_exportar"] and len(of_sin_predio):
        enlaces = posibles_enlaces(df_liq, of_sin_predio)
        n_of_rev = enlaces["ID_CATASTRAL_OFERTA"].nunique() if len(enlaces) else 0
        print(f"   Para revisar (hoja POSIBLE_ENLACE): {n_of_rev:,} ofertas cuyo ID si "
              f"existe en la liquidacion")
        print(f"      pero no cruzaron por la llave compuesta -> {len(enlaces):,} "
              f"construcciones candidatas")
        print(f"      ({len(of_sin_predio) - n_of_rev:,} ofertas quedan fuera: su Id "
              f"catastral no existe en la liquidacion)")

    # DUP_LIQUIDACION se limita a las llaves que realmente entran en la
    # comparacion: los duplicados del resto de la base son ruido aqui
    # (el total global queda en RESUMEN).
    dup_liq_rel = dup_liq[dup_liq["LLAVE"].isin(set(df_of_res["LLAVE"]))] if len(dup_liq) \
        else dup_liq

    hojas = {
        "RESUMEN": df_resumen,
        "COMPARACION": _recortar_comparacion(_ordenar_cols(df_comp)),
        "FUERA_TOLERANCIA": _recortar_comparacion(
            _ordenar_cols(df_comp[df_comp["FUERA_TOLERANCIA"]])) if n_ok else None,
        "RESUMEN_X_USO": resumen_por_uso(df_comp),
        "RESUMEN_X_RANGO": resumen_por_rango(df_comp),
        "DUP_OFERTAS": _ordenar_cols(dup_of).rename(columns=ren_of),
        "DUP_LIQUIDACION": _ordenar_cols(dup_liq_rel),
        "OFERTAS_SIN_CRUCE": of_sin_predio,
        "POSIBLE_ENLACE": enlaces,
        # No lleva datos: se llena con los PNG de graficos_comparacion().
        "GRAFICOS": pd.DataFrame(),
        "DETALLE_CONSTRUCCIONES": _ordenar_cols(detalle) if len(detalle) else None,
    }

    # Se escriben solo las hojas pedidas en CONFIG['hojas_exportar'].
    hojas = {h: hojas[h] for h in CONFIG["hojas_exportar"] if h in hojas}

    # Los graficos van ANTES del Excel a proposito: si el .xlsx esta abierto en
    # Excel la escritura falla, y no tiene sentido perder tambien los PNG.
    # Ademas se necesitan generados para poder incrustarlos en la hoja GRAFICOS.
    rutas_graficos = []
    if CONFIG["generar_graficos"] and n_ok:
        rutas_graficos = graficos_comparacion(
            df_comp, os.path.join(CONFIG["carpeta_results"], "GRAFICOS"), fecha)

    exportar_excel(hojas, ruta, graficos=rutas_graficos)
    print(f"\n   Excel generado: {ruta}")
    for nombre, d in hojas.items():
        if d is not None:
            print(f"     {nombre:<20} {len(d):>10,} filas")
    crono.marca("COMPARACION: exportar excel")
    if df_const_liq is None:
        crono.resumen()
    print("=" * 60 + "\n")
    return df_comp


# =====================================================================
# CLI
# =====================================================================
def _cli():
    p = argparse.ArgumentParser(description="Compara VM2 de liquidacion vs ofertas")
    p.add_argument("--ofertas", default=None, help="Ruta del archivo de ofertas")
    p.add_argument("--hoja", default=0, help="Hoja del Excel de ofertas (nombre o indice)")
    p.add_argument("--liquidacion", default=None, help="Parquet/CSV de liquidacion")
    p.add_argument("--tolerancia", type=float, default=None, help="Tolerancia en %%")
    p.add_argument("--duplicados", default=None,
                   choices=["alertar", "promedio", "mediana", "max", "min", "primero"])
    p.add_argument("--redondeo-area", type=int, default=None,
                   help="Decimales del area para la llave (0 = m2 entero)")
    p.add_argument("--uso-literal", action="store_true",
                   help="Cruza los usos texto a texto, sin normalizar tildes/espacios")
    p.add_argument("--todas-las-columnas", action="store_true",
                   help="No recorta la hoja COMPARACION: saca todas las columnas "
                        "que arrastra la liquidacion")
    p.add_argument("--cruce-estricto", action="store_true",
                   help="Apaga el nivel 2: exige que el AREA coincida exacta "
                        "(no elige la construccion mas parecida)")
    p.add_argument("--hojas", default=None,
                   help="Hojas a exportar separadas por coma. Por defecto: "
                        "RESUMEN,COMPARACION,OFERTAS_SIN_CRUCE. Opcionales: "
                        "FUERA_TOLERANCIA, RESUMEN_X_USO, RESUMEN_X_RANGO, "
                        "DUP_OFERTAS, DUP_LIQUIDACION, DETALLE_CONSTRUCCIONES")
    p.add_argument("--salida", default=None, help="Ruta del Excel de salida")
    a = p.parse_args()

    if a.redondeo_area is not None:
        CONFIG["redondeo_area"] = a.redondeo_area
    if a.liquidacion:
        CONFIG["parquet_liquidacion"] = a.liquidacion
    if a.uso_literal:
        CONFIG["normalizar_uso"] = False
    if a.cruce_estricto:
        CONFIG["match_uso_area_cercana"] = False
    if a.todas_las_columnas:
        CONFIG["columnas_comparacion"] = None
    if a.hojas:
        CONFIG["hojas_exportar"] = [h.strip().upper() for h in a.hojas.split(",") if h.strip()]

    hoja = int(a.hoja) if str(a.hoja).isdigit() else a.hoja
    comparacion_ofertas(ruta_ofertas=a.ofertas, hoja_ofertas=hoja,
                        tolerancia_pct=a.tolerancia,
                        estrategia_duplicados=a.duplicados,
                        ruta_salida=a.salida)


if __name__ == "__main__":
    _cli()
