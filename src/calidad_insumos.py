"""
PASO 0A - Calidad de los insumos (exports de Sistemas).

Corre ANTES de todo el proceso y sobre los archivos en bruto. No reemplaza a
pre_inconsistencias.py: aquella revisa construccion por construccion despues
del cruce y descuenta los predios que no se pueden liquidar; esta revisa cada
export completo y lo compara contra el de la vigencia anterior.

Nacio de un caso real: el export de predios 2026 trae la direccion vacia
("NA # - ") en el 97% de los predios rurales, cuando el de 2025 la traia en el
99%. Nada fallaba -la direccion no entra al valor- y solo se vio al armar un
listado para Economico. Aqui eso sale como ADVERTENCIA de "caida frente a la
vigencia anterior", con los predios que se pueden recuperar del export viejo.

Niveles:
  ERROR        el insumo no sirve tal como esta (columna obligatoria que falta,
               identificadores duplicados). Detiene la corrida si el parametro
               calidad_bloqueante del manifiesto esta en true (por defecto).
  ADVERTENCIA  el dato se puede usar pero perdio calidad: cae mas de
               UMBRAL_CAIDA_PP puntos frente a la vigencia anterior, o queda
               por debajo del minimo de la regla.
  OK / INFO    sin novedad / solo informativo.

NO corrige nada. Lo recuperable se lista para pedir el ajuste a Sistemas o
para decidirlo: las coordenadas, por ejemplo, alimentan las distancias de los
modelos, asi que rellenarlas desde otra fuente cambia el valor liquidado.
"""

from __future__ import annotations

import gc
import os
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

import config

UMBRAL_CAIDA_PP = 2.0          # puntos porcentuales frente a la vigencia anterior
UMBRAL_COMPLETITUD = 90.0      # % minimo de registros validos por regla
UMBRAL_HUERFANOS = 99.5        # % minimo de registros que cruzan con predios
BBOX_CALI = (3.20, 3.65, -76.75, -76.40)   # lat_min, lat_max, lon_min, lon_max
MUESTRA = 200                  # filas de ejemplo por regla
MAX_RECUPERABLES = 500_000

# Destinos que se liquidan sin puntaje (mismos que pre_inconsistencias).
DESTINOS_SIN_PUNTAJE = [6, 7, 8, 27, 36, 37]
# Condiciones sin terreno propio: 2 informal, 5 mejora en predio ajeno.
CONDICIONES_SIN_TERRENO = ["2", "5"]

COLUMNAS_OBLIGATORIAS = {
    "export_predio_actual": ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "AVALPRED", "AREAPRED", "ZHF",
                             "ESTRPRED", "TIPOPRED", "LATITUDE", "LONGITUDE"],
    "export_construccion_actual_conv": ["ID_PREDIO", "ID_CONSTRUCCION", "DESTINOCONS", "ACONCONS", "PUNTCONS"],
    "export_construccion_actual_noconv": ["ID_PREDIO", "TIPOANEXO", "ACONANEX"],
    "export_terreno_actual": ["ID_PREDIO", "AMETTERR"],
    "zhg_historico": ["ID_PREDIO", "ZHG_2024", "ZHG_2025"],
}
ETIQUETA = {
    "export_predio_actual": "Predios de la vigencia",
    "export_construccion_actual_conv": "Construcciones convencionales",
    "export_construccion_actual_noconv": "Construcciones no convencionales",
    "export_terreno_actual": "Terrenos de la vigencia",
    "zhg_historico": "ZHG 2024-2025",
    "export_predio_2024": "Predios vigencia anterior (comparacion)",
    "export_construccion_2024": "Construcciones vigencia anterior (comparacion)",
}


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------
def _columnas_disponibles(path: str) -> list[str]:
    ext = Path(path).suffix.lower()
    if ext == ".parquet":
        import pyarrow.parquet as pq
        return list(pq.read_schema(path).names)
    with open(path, "r", encoding="latin-1", errors="replace") as f:
        cab = f.readline().lstrip("﻿")
    sep = "|" if "|" in cab else (";" if ";" in cab else ",")
    return [c.strip().strip('"') for c in cab.rstrip("\r\n").split(sep)]


def _leer(path: str, columnas: list[str]) -> pd.DataFrame:
    """Solo las columnas pedidas que existan, todo como texto."""
    disponibles = _columnas_disponibles(path)
    usar = [c for c in columnas if c in disponibles]
    if Path(path).suffix.lower() == ".parquet":
        df = pd.read_parquet(path, columns=usar)
    else:
        with open(path, "r", encoding="latin-1", errors="replace") as f:
            cab = f.readline()
        sep = "|" if "|" in cab else (";" if ";" in cab else ",")
        df = pd.read_csv(path, sep=sep, encoding="latin-1", dtype=str, usecols=usar,
                         on_bad_lines="skip", low_memory=False)
    for c in df.columns:
        if df[c].dtype == object or str(df[c].dtype).startswith("string"):
            df[c] = df[c].astype("string").str.strip()
    for c in ("ID_PREDIO", "ID_CONSTRUCCION"):
        if c in df.columns:
            df[c] = df[c].astype("string").str.replace(r"\.0$", "", regex=True).str.strip()
    return df


def _num(s: pd.Series) -> pd.Series:
    """Numerico tolerante a coma decimal (los .txt de Sistemas la traen)."""
    if pd.api.types.is_numeric_dtype(s):
        return pd.to_numeric(s, errors="coerce")
    return pd.to_numeric(s.astype("string").str.replace(",", ".", regex=False), errors="coerce")


def _texto_valido(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip()
    return (s.notna() & t.ne("") & ~t.str.upper().isin(["NAN", "NONE", "NULL", "0"])
            & ~t.str.match(r"^NA\s*#\s*-?\s*$").fillna(False)).fillna(False)


def _zhf_valida(s: pd.Series) -> pd.Series:
    t = s.astype("string").str.strip().str.replace(r"\.0$", "", regex=True)
    digitos = t.str.fullmatch(r"\d+").fillna(False)
    return digitos & (t.str.len() >= 6) & (_num(t).fillna(0) > 0)


def _zona(npn: pd.Series) -> pd.Series:
    return np.where(npn.astype("string").str[5:7] == "01", "URBANO", "RURAL")


def _condicion(npn: pd.Series) -> pd.Series:
    return npn.astype("string").str[21]


# ---------------------------------------------------------------------------
# Motor de reglas
# ---------------------------------------------------------------------------
class Reporte:
    def __init__(self) -> None:
        self.reglas: list[dict] = []
        self.ejemplos: list[pd.DataFrame] = []
        self.recuperables: list[pd.DataFrame] = []
        self.archivos: dict[str, str] = {}

    # nivel ------------------------------------------------------------------
    @staticmethod
    def _nivel(pct_ok, pct_ant, minimo, bloqueante, n_falla, error_si_menor=None) -> str:
        if bloqueante:
            return "ERROR" if n_falla > 0 else "OK"
        if pct_ok is None:
            return "INFO"
        if error_si_menor is not None and pct_ok < error_si_menor:
            return "ERROR"
        if pct_ant is not None and (pct_ant - pct_ok) > UMBRAL_CAIDA_PP:
            return "ADVERTENCIA"
        if minimo is not None and pct_ok < minimo:
            return "ADVERTENCIA"
        return "OK"

    def agregar(self, insumo, ambito, regla, descripcion, universo, fallan, *,
                pct_ant=None, minimo=UMBRAL_COMPLETITUD, bloqueante=False, error_si_menor=None,
                ejemplos: pd.DataFrame | None = None, recuperables: int | None = None,
                detalle_recuperable: pd.DataFrame | None = None) -> None:
        n_u = int(universo)
        n_f = int(fallan)
        pct_ok = None if n_u == 0 else round(100 * (n_u - n_f) / n_u, 4 if n_f and n_f < n_u / 1000 else 2)
        nivel = self._nivel(pct_ok, pct_ant, minimo, bloqueante, n_f, error_si_menor)
        self.reglas.append({
            "NIVEL": nivel,
            "INSUMO": ETIQUETA.get(insumo, insumo),
            "AMBITO": ambito,
            "REGLA": regla,
            "DESCRIPCION": descripcion,
            "REGISTROS_EVALUADOS": n_u,
            "REGISTROS_CON_FALLA": n_f,
            "PCT_VALIDO": pct_ok,
            "PCT_VALIDO_VIGENCIA_ANTERIOR": pct_ant,
            "CAMBIO_PP": None if (pct_ant is None or pct_ok is None) else round(pct_ok - pct_ant, 2),
            "RECUPERABLES_DESDE_ANTERIOR": recuperables,
            "ARCHIVO": os.path.basename(self.archivos.get(insumo, "")),
        })
        if ejemplos is not None and len(ejemplos):
            e = ejemplos.head(MUESTRA).copy()
            e.insert(0, "REGLA", f"{ETIQUETA.get(insumo, insumo)} | {ambito} | {regla}")
            self.ejemplos.append(e.astype("string"))
        if detalle_recuperable is not None and len(detalle_recuperable):
            self.recuperables.append(detalle_recuperable.astype("string"))
        marca = {"ERROR": "[ERROR]", "ADVERTENCIA": "[WARN] ", "OK": "[OK]   ", "INFO": "[INFO] "}[nivel]
        extra = "" if pct_ant is None else f" (anterior {pct_ant:.1f}%)"
        pct_txt = "-" if pct_ok is None else f"{pct_ok:.1f}%"
        print(f"   {marca} {ETIQUETA.get(insumo, insumo)} | {ambito:7s} | {regla}: {pct_txt}{extra}"
              + (f" | recuperables {recuperables:,}" if recuperables else ""))

    def columnas(self, insumo: str, df: pd.DataFrame) -> bool:
        faltan = [c for c in COLUMNAS_OBLIGATORIAS.get(insumo, []) if c not in df.columns]
        self.agregar(insumo, "TODO", "Columnas obligatorias",
                     "Columnas que el motor necesita. " + (f"Faltan: {', '.join(faltan)}" if faltan else "Completas."),
                     len(COLUMNAS_OBLIGATORIAS.get(insumo, [])), len(faltan), bloqueante=True)
        return not faltan

    @property
    def errores(self) -> int:
        return sum(r["NIVEL"] == "ERROR" for r in self.reglas)

    @property
    def advertencias(self) -> int:
        return sum(r["NIVEL"] == "ADVERTENCIA" for r in self.reglas)


# ---------------------------------------------------------------------------
# Reglas por insumo
# ---------------------------------------------------------------------------
REGLAS_PREDIO = [
    # (columna, nombre, descripcion, validador, filtro de universo, minimo absoluto)
    ("DIREPRED", "Direccion", "Direccion diligenciada (no vacia ni 'NA # -').", _texto_valido, None,
     UMBRAL_COMPLETITUD),
    ("AREAPRED", "Area de terreno > 0", "AREAPRED mayor que cero. Excluye informales (2) y mejoras (5).",
     lambda s: _num(s).fillna(0) > 0, "con_terreno", UMBRAL_COMPLETITUD),
    ("AVALPRED", "Avaluo > 0", "Avaluo catastral vigente mayor que cero.", lambda s: _num(s).fillna(0) > 0, None,
     UMBRAL_COMPLETITUD),
    ("ZHF", "ZHF valida", "Zona homogenea fisica numerica de 6 o mas digitos y distinta de cero.", _zhf_valida,
     "urbano", UMBRAL_COMPLETITUD),
    # Los predios no residenciales no llevan estrato: solo cuenta si cae frente a la vigencia anterior.
    ("ESTRPRED", "Estrato 1 a 6", "Estrato socioeconomico entre 1 y 6 (los no residenciales no lo llevan).",
     lambda s: _num(s).between(1, 6).fillna(False), "urbano", None),
    ("MATCPRED", "Matricula", "Matricula inmobiliaria diligenciada.", _texto_valido, "con_terreno", UMBRAL_COMPLETITUD),
]


def _universo(df: pd.DataFrame, filtro: str | None, ambito: str) -> pd.Series:
    m = pd.Series(True, index=df.index) if ambito == "TODO" else (df["_ZONA"] == ambito)
    if filtro == "urbano":
        m &= df["_ZONA"] == "URBANO"
    elif filtro == "con_terreno":
        m &= ~df["_COND"].isin(CONDICIONES_SIN_TERRENO)
    return m


def _revisar_predios(rep: Reporte, actual_path: str, anterior_path: str | None) -> set:
    cols = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "DIREPRED", "AREAPRED", "AVALPRED", "ZHF",
            "ESTRPRED", "TIPOPRED", "MATCPRED", "LATITUDE", "LONGITUDE"]
    act = _leer(actual_path, cols)
    if not rep.columnas("export_predio_actual", act):
        return set(act.get("ID_PREDIO", pd.Series(dtype="string")).dropna())

    ant = None
    if anterior_path:
        ant = _leer(anterior_path, cols)
        if "ID_PREDIO" not in ant.columns or "NUMERO_PREDIAL_NACIONAL" not in ant.columns:
            ant = None
    for d in [x for x in (act, ant) if x is not None]:
        d["_ZONA"] = _zona(d.NUMERO_PREDIAL_NACIONAL)
        d["_COND"] = _condicion(d.NUMERO_PREDIAL_NACIONAL)

    # --- identificacion
    dup = act.ID_PREDIO.duplicated(keep=False)
    rep.agregar("export_predio_actual", "TODO", "ID_PREDIO unico", "Cada ID_PREDIO debe aparecer una sola vez.",
                len(act), int(act.ID_PREDIO[dup].nunique()), bloqueante=True,
                ejemplos=act.loc[dup, ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL"]])
    npn = act.NUMERO_PREDIAL_NACIONAL.astype("string")
    malo = ~npn.str.fullmatch(r"\d{30}").fillna(False)
    rep.agregar("export_predio_actual", "TODO", "NPN de 30 digitos", "Numero predial nacional con 30 digitos numericos.",
                len(act), int(malo.sum()), minimo=99.0, ejemplos=act.loc[malo, ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL"]])

    # --- cobertura frente a la vigencia anterior
    if ant is not None:
        ids_a, ids_b = set(act.ID_PREDIO.dropna()), set(ant.ID_PREDIO.dropna())
        rep.agregar("export_predio_actual", "TODO", "Predios de la vigencia anterior presentes",
                    f"De {len(ids_b):,} predios del export anterior, cuantos siguen. Altas nuevas: {len(ids_a - ids_b):,}.",
                    len(ids_b), len(ids_b - ids_a), minimo=95.0,
                    ejemplos=pd.DataFrame({"ID_PREDIO_AUSENTE": sorted(ids_b - ids_a)[:MUESTRA]}))
        for zona in ("URBANO", "RURAL"):
            rep.agregar("export_predio_actual", zona, "Numero de predios",
                        f"Actual {int((act._ZONA == zona).sum()):,} vs anterior {int((ant._ZONA == zona).sum()):,}.",
                        0, 0, minimo=None)

    # --- completitud por campo, zona y frente a la vigencia anterior
    ant_idx = ant.drop_duplicates("ID_PREDIO").set_index("ID_PREDIO") if ant is not None else None
    for col, nombre, desc, validar, filtro, minimo in REGLAS_PREDIO:
        if col not in act.columns:
            continue
        ok_act = validar(act[col])
        ok_ant = validar(ant[col]) if (ant is not None and col in ant.columns) else None
        for ambito in ("URBANO", "RURAL"):
            u = _universo(act, filtro, ambito)
            if u.sum() == 0:
                continue
            pct_ant = None
            if ok_ant is not None:
                ua = _universo(ant, filtro, ambito)
                pct_ant = round(100 * ok_ant[ua].mean(), 2) if ua.sum() else None
            falla = u & ~ok_act
            recup, detalle = None, None
            if ant_idx is not None and col in ant_idx.columns:
                previo = act.loc[falla, "ID_PREDIO"].map(ant_idx[col])
                bueno = validar(previo.astype("string")) if len(previo) else previo.astype(bool)
                recup = int(bueno.sum())
                if recup:
                    f = act.loc[falla].loc[bueno.values]
                    detalle = pd.DataFrame({
                        "CAMPO": col, "ZONA": ambito, "ID_PREDIO": f.ID_PREDIO.values,
                        "NUMERO_PREDIAL_NACIONAL": f.NUMERO_PREDIAL_NACIONAL.values,
                        "VALOR_ACTUAL": f[col].values, "VALOR_VIGENCIA_ANTERIOR": previo[bueno.values].values,
                    })
            rep.agregar("export_predio_actual", ambito, nombre, desc, int(u.sum()), int(falla.sum()),
                        pct_ant=pct_ant, minimo=minimo, recuperables=recup, detalle_recuperable=detalle,
                        ejemplos=act.loc[falla, ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", col]])

    # --- coordenadas (el export anterior no las trae)
    lat, lon = _num(act.LATITUDE), _num(act.LONGITUDE)
    ok = lat.between(BBOX_CALI[0], BBOX_CALI[1]) & lon.between(BBOX_CALI[2], BBOX_CALI[3])
    for ambito in ("URBANO", "RURAL"):
        u = act._ZONA == ambito
        falla = u & ~ok.fillna(False)
        rep.agregar("export_predio_actual", ambito, "Coordenadas dentro de Cali",
                    "LATITUDE/LONGITUDE diligenciadas y dentro del rectangulo de Cali. Alimentan las distancias de los modelos.",
                    int(u.sum()), int(falla.sum()),
                    ejemplos=act.loc[falla, ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "LATITUDE", "LONGITUDE"]])

    ids = set(act.ID_PREDIO.dropna())
    rep._cond = act.set_index("ID_PREDIO")._COND  # para terrenos
    rep._ph = set(act.loc[(act._COND == "9") & (act._ZONA == "URBANO"), "ID_PREDIO"])
    del act, ant, ant_idx
    gc.collect()
    return ids


def _revisar_huerfanos(rep, insumo, df, ids_predio, descripcion):
    huer = ~df.ID_PREDIO.isin(ids_predio)
    rep.agregar(insumo, "TODO", "Cruzan con predios", descripcion, len(df), int(huer.sum()),
                minimo=UMBRAL_HUERFANOS, ejemplos=df.loc[huer, ["ID_PREDIO"]].drop_duplicates())


def _revisar_construcciones(rep, path, path_ant, ids_predio):
    c = _leer(path, ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "ID_CONSTRUCCION", "DESTINOCONS", "ACONCONS", "PUNTCONS"])
    if not rep.columnas("export_construccion_actual_conv", c):
        return
    # Una construccion repetida se liquida dos veces: duplica su area y su valor.
    # Unas pocas se reportan para corregir; si pasan del 0,1% el export esta mal armado.
    dup = c.ID_CONSTRUCCION.duplicated(keep=False) & c.ID_CONSTRUCCION.notna()
    rep.agregar("export_construccion_actual_conv", "TODO", "ID_CONSTRUCCION unico",
                f"Cada construccion una sola vez; repetida se liquida dos veces. "
                f"{int(c.ID_CONSTRUCCION[dup].nunique()):,} construcciones repetidas en {int(dup.sum()):,} filas.",
                len(c), int(dup.sum()), minimo=100.0, error_si_menor=99.9,
                ejemplos=c.loc[dup, ["ID_PREDIO", "ID_CONSTRUCCION", "ACONCONS", "PUNTCONS"]])
    _revisar_huerfanos(rep, "export_construccion_actual_conv", c, ids_predio,
                       "Construcciones cuyo ID_PREDIO existe en el export de predios.")
    area_ant = None
    if path_ant:
        a = _leer(path_ant, ["ID_PREDIO", "ACONCONS"])
        if "ACONCONS" in a.columns and len(a):
            area_ant = round(100 * (_num(a.ACONCONS).fillna(0) > 0).mean(), 2)
        del a
    area = _num(c.ACONCONS).fillna(0) > 0
    rep.agregar("export_construccion_actual_conv", "TODO", "Area construida > 0", "ACONCONS mayor que cero.",
                len(c), int((~area).sum()), pct_ant=area_ant, ejemplos=c.loc[~area, ["ID_PREDIO", "ID_CONSTRUCCION", "ACONCONS"]])
    dest = _num(c.DESTINOCONS).fillna(0)
    urbano = c.NUMERO_PREDIAL_NACIONAL.astype("string").str[5:7].eq("01") if "NUMERO_PREDIAL_NACIONAL" in c else pd.Series(True, index=c.index)
    u = urbano & ~dest.isin(DESTINOS_SIN_PUNTAJE)
    falla = u & ~(_num(c.PUNTCONS).fillna(0) > 0)
    rep.agregar("export_construccion_actual_conv", "URBANO", "Puntaje > 0",
                "PUNTCONS mayor que cero. Excluye destinos que se liquidan sin puntaje (garajes, depositos, parqueaderos).",
                int(u.sum()), int(falla.sum()), ejemplos=c.loc[falla, ["ID_PREDIO", "ID_CONSTRUCCION", "DESTINOCONS", "PUNTCONS"]])
    # El destino NO se valida aqui: las comunas no actualizadas traen la
    # codificacion vieja de tres digitos y la homologacion la traduce; lo que no
    # logra homologar lo reporta pre_inconsistencias como "Sin USO_LADM".
    del c
    gc.collect()


def _revisar_anexos(rep, path, ids_predio):
    n = _leer(path, ["ID_PREDIO", "TIPOANEXO", "ACONANEX"])
    if not rep.columnas("export_construccion_actual_noconv", n):
        return
    _revisar_huerfanos(rep, "export_construccion_actual_noconv", n, ids_predio,
                       "Anexos cuyo ID_PREDIO existe en el export de predios.")
    area = _num(n.ACONANEX).fillna(0) > 0
    rep.agregar("export_construccion_actual_noconv", "TODO", "Area del anexo > 0", "ACONANEX mayor que cero.",
                len(n), int((~area).sum()), ejemplos=n.loc[~area, ["ID_PREDIO", "ACONANEX"]])
    tipo = _num(n.TIPOANEXO).fillna(0) > 0
    rep.agregar("export_construccion_actual_noconv", "TODO", "Tipo de anexo", "TIPOANEXO diligenciado (hace las veces de puntaje).",
                len(n), int((~tipo).sum()), ejemplos=n.loc[~tipo, ["ID_PREDIO", "TIPOANEXO"]])
    del n
    gc.collect()


def _revisar_terrenos(rep, path, ids_predio):
    t = _leer(path, ["ID_PREDIO", "AMETTERR"])
    if not rep.columnas("export_terreno_actual", t):
        return
    _revisar_huerfanos(rep, "export_terreno_actual", t, ids_predio, "Terrenos cuyo ID_PREDIO existe en el export de predios.")
    area = _num(t.AMETTERR).fillna(0) > 0
    rep.agregar("export_terreno_actual", "TODO", "Area de terreno > 0", "AMETTERR mayor que cero.",
                len(t), int((~area).sum()), ejemplos=t.loc[~area, ["ID_PREDIO", "AMETTERR"]])
    cond = getattr(rep, "_cond", pd.Series(dtype="string"))
    con_terreno = {i for i in ids_predio if cond.get(i) not in CONDICIONES_SIN_TERRENO}
    sin = sorted(con_terreno - set(t.ID_PREDIO.dropna()))
    rep.agregar("export_terreno_actual", "TODO", "Predios con terreno",
                "Predios (salvo informales y mejoras) que tienen al menos un registro en el export de terrenos.",
                len(con_terreno), len(sin), minimo=99.0, ejemplos=pd.DataFrame({"ID_PREDIO": sin[:MUESTRA]}))
    del t
    gc.collect()


def _revisar_zhg(rep, path):
    z = _leer(path, ["ID_PREDIO", "ZHG_2024", "ZHG_2025"])
    if not rep.columnas("zhg_historico", z):
        return
    ph = getattr(rep, "_ph", set())
    if ph:
        zi = z.drop_duplicates("ID_PREDIO").set_index("ID_PREDIO")
        tiene = (_num(zi.ZHG_2025).fillna(0) > 0) | (_num(zi.ZHG_2024).fillna(0) > 0)
        con = set(zi.index[tiene])
        sin = sorted(ph - con)
        rep.agregar("zhg_historico", "URBANO", "Cobertura en PH",
                    "Predios urbanos en PH (condicion 9) con valor de suelo ZHG; los modelos lo usan.",
                    len(ph), len(sin), ejemplos=pd.DataFrame({"ID_PREDIO": sin[:MUESTRA]}))
    del z
    gc.collect()


# ---------------------------------------------------------------------------
# Salida
# ---------------------------------------------------------------------------
def _escribir(rep: Reporte, destino: Path, run_id: str) -> Path:
    destino.parent.mkdir(parents=True, exist_ok=True)
    reglas = pd.DataFrame(rep.reglas)
    orden = {"ERROR": 0, "ADVERTENCIA": 1, "OK": 2, "INFO": 3}
    reglas = reglas.sort_values(["NIVEL", "INSUMO", "AMBITO"], key=lambda s: s.map(orden) if s.name == "NIVEL" else s)
    resumen = pd.DataFrame({
        "CONCEPTO": ["Corrida", "Fecha", "Resultado", "Errores", "Advertencias", "Reglas OK",
                     "Umbral de caida frente a la vigencia anterior (pp)", "Completitud minima por defecto (%)"]
                    + [f"Archivo: {ETIQUETA.get(k, k)}" for k in rep.archivos],
        "VALOR": [run_id, datetime.now().strftime("%Y-%m-%d %H:%M"),
                  "NO APTO: corregir los ERROR antes de liquidar" if rep.errores else
                  ("APTO CON ADVERTENCIAS" if rep.advertencias else "APTO"),
                  rep.errores, rep.advertencias, int((reglas.NIVEL == "OK").sum()),
                  UMBRAL_CAIDA_PP, UMBRAL_COMPLETITUD] + list(rep.archivos.values()),
    })
    acerca = pd.DataFrame({"NOTA": [
        "Este reporte revisa cada export de Sistemas en bruto, antes de liquidar, y lo compara con el de la vigencia anterior.",
        "ERROR: el insumo no sirve como esta (columnas obligatorias, identificadores duplicados). Detiene la corrida.",
        f"ADVERTENCIA: el dato perdio mas de {UMBRAL_CAIDA_PP} puntos frente a la vigencia anterior, o esta bajo el minimo de la regla.",
        "RECUPERABLES: registros que fallan en el export actual pero traen el dato valido en el de la vigencia anterior.",
        "Nada se corrige automaticamente: lo recuperable se reporta para solicitar el ajuste a Sistemas o decidirlo.",
        "Complementa, no reemplaza, el reporte de pre-inconsistencias (paso 2), que revisa construccion por construccion.",
    ]})
    with pd.ExcelWriter(destino, engine="xlsxwriter") as w:
        resumen.to_excel(w, sheet_name="RESUMEN", index=False)
        reglas.to_excel(w, sheet_name="REGLAS", index=False)
        wb, ws = w.book, w.sheets["REGLAS"]
        formatos = {"ERROR": "#F8CBAD", "ADVERTENCIA": "#FFE699", "OK": "#C6EFCE", "INFO": "#DDEBF7"}
        for nivel, color in formatos.items():
            ws.conditional_format(1, 0, len(reglas), 0, {"type": "cell", "criteria": "==", "value": f'"{nivel}"',
                                                          "format": wb.add_format({"bg_color": color})})
        for i, ancho in enumerate([13, 34, 9, 38, 70, 12, 12, 11, 13, 10, 13, 40]):
            ws.set_column(i, i, ancho)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(reglas), len(reglas.columns) - 1)
        if rep.recuperables:
            rec = pd.concat(rep.recuperables, ignore_index=True).head(MAX_RECUPERABLES)
            rec.to_excel(w, sheet_name="RECUPERABLES", index=False)
        if rep.ejemplos:
            pd.concat(rep.ejemplos, ignore_index=True).to_excel(w, sheet_name="EJEMPLOS", index=False)
        acerca.to_excel(w, sheet_name="ACERCA", index=False)
    return destino


def evaluar_calidad(run_id: str | None = None, carpeta: str = "./output/Calidad_insumos") -> Reporte:
    """Revisa los insumos del manifiesto cargado en config y escribe el reporte."""
    run_id = run_id or config.MANIFEST_DATA.get("run_id", "DEFAULT")
    rep = Reporte()
    rutas = {k: config.get_insumo(k) for k in (
        "export_predio_actual", "export_predio_2024", "export_construccion_actual_conv", "export_construccion_2024",
        "export_construccion_actual_noconv", "export_terreno_actual", "zhg_historico")}
    rep.archivos = {k: v for k, v in rutas.items() if v and os.path.isfile(v)}

    print("   Predios...")
    ids = _revisar_predios(rep, rutas["export_predio_actual"], rep.archivos.get("export_predio_2024"))
    if "export_construccion_actual_conv" in rep.archivos:
        print("   Construcciones convencionales...")
        _revisar_construcciones(rep, rutas["export_construccion_actual_conv"],
                                rep.archivos.get("export_construccion_2024"), ids)
    if "export_construccion_actual_noconv" in rep.archivos:
        print("   Construcciones no convencionales...")
        _revisar_anexos(rep, rutas["export_construccion_actual_noconv"], ids)
    if "export_terreno_actual" in rep.archivos:
        print("   Terrenos...")
        _revisar_terrenos(rep, rutas["export_terreno_actual"], ids)
    if "zhg_historico" in rep.archivos:
        print("   ZHG...")
        _revisar_zhg(rep, rutas["zhg_historico"])

    destino = _escribir(rep, Path(carpeta) / f"CALIDAD_INSUMOS_{run_id}.xlsx", run_id)
    rep.ruta = str(destino.resolve())
    print(f"\n   Resultado: {rep.errores} error(es), {rep.advertencias} advertencia(s)")
    print(f"[OK] Reporte de calidad: {rep.ruta}")
    gc.collect()
    return rep
