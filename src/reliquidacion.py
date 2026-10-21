"""Reliquidacion de un listado de predios con otras condiciones.

Sirve para revisiones puntuales: reclamaciones, radicados o verificaciones de
una vigencia anterior. Toma un listado de predios y los vuelve a liquidar con
la base de construcciones de hoy, pero cambiando las condiciones que se piden
en la configuracion:

  - las reglas y tablas de un ejercicio anterior (2024 o 2025),
  - la comuna cuyos valores se aplican, cuando la comuna del predio no tiene
    tabla en ese ejercicio,
  - la ZHF, tomada de otro export de predios,
  - el terreno, tomado de otra foto de predios (se conserva, no se recalcula).

Todo se liquida por tabla. Lo que en ese ejercicio iba por modelo se fuerza a
tabla y se marca, y con "excluir_modelo" se deja fuera del archivo final.

El resultado es un Excel con la variacion por predio y por construccion frente
al avaluo de referencia, rangos de variacion y las novedades marcadas
(mutaciones, cambio de tipologia de la ZHF, especiales, terreno que no cuadra).

Uso:
    python src/reliquidacion.py configuracion.json
    LiquidadorCatastral.exe --reliquidar configuracion.json

La configuracion se documenta en docs/RELIQUIDACION.md y hay un ejemplo en
ejemplos/reliquidacion_radicados_comuna02.json.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

LLAVE = "LLAVE_CONST"

# Parqueaderos que la tabla T12 liquida por cupo (el valor ya trae el factor
# de area). Los depositos de la misma tabla (006, 027) van por m2.
PARQUEADEROS_POR_UNIDAD = {"007", "008", "036", "037"}

# Que construcciones iban por modelo en cada ejercicio.
MODELO_2025 = {"001", "028", "034"}          # con condicion 9 (PH)
USOS_MODELO_2024 = ["Apartamentos_4_y_mas_pisos_en_PH", "Comercio_en_PH", "Oficinas_Consultorios_en_PH"]

RANGOS = [-np.inf, -50, -30, -20, -10, -5, -1, 1, 5, 10, 20, 30, np.inf]
ETIQUETAS_RANGO = ["Baja mas de 50%", "Baja 30% a 50%", "Baja 20% a 30%", "Baja 10% a 20%", "Baja 5% a 10%",
                   "Baja 1% a 5%", "Sin variacion (-1% a 1%)", "Sube 1% a 5%", "Sube 5% a 10%", "Sube 10% a 20%",
                   "Sube 20% a 30%", "Sube mas de 30%"]


# ---------------------------------------------------------------------------
# Configuracion
# ---------------------------------------------------------------------------

@dataclass
class Fuente:
    """Un archivo y las columnas que se leen de el."""
    archivo: str
    columnas: dict = field(default_factory=dict)


@dataclass
class Configuracion:
    nombre: str
    predios: str
    base_construcciones: str
    reglas: str = "2025"
    comuna_reglas: str | None = None
    comuna_referencia: str | None = None
    factor_catastral: float = 0.7
    excluir_modelo: bool = False
    etiqueta_referencia: str = "REFERENCIA"
    etiqueta_nueva: str = "NUEVA"
    zhf: Fuente | None = None
    terreno: Fuente | None = None
    actual: Fuente | None = None
    export_construcciones: str | None = None
    export_anexos: str | None = None
    export_predios: str | None = None
    zona_control: Fuente | None = None
    salida: str = "output/reliquidacion"
    tolerancia_terreno: float = 1000.0

    @classmethod
    def desde_json(cls, ruta: str | Path) -> "Configuracion":
        ruta = Path(ruta)
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        base = ruta.resolve().parent
        fuentes = {}
        for k in ("zhf", "terreno", "actual", "zona_control"):
            v = datos.pop(k, None)
            if v:
                fuentes[k] = Fuente(archivo=_ruta(v["archivo"], base), columnas=v.get("columnas", {}))
        for k in ("predios", "base_construcciones", "export_construcciones", "export_anexos", "export_predios", "salida"):
            if datos.get(k):
                datos[k] = _ruta(datos[k], base)
        datos.pop("_comentario", None)
        return cls(**datos, **fuentes)

    def validar(self) -> list[str]:
        errores = []
        if self.reglas not in MOTORES:
            errores.append(f"reglas debe ser una de {sorted(MOTORES)}, no {self.reglas!r}")
        for nombre in ("predios", "base_construcciones", "export_construcciones", "export_anexos", "export_predios"):
            v = getattr(self, nombre)
            if v and not Path(v).is_file():
                errores.append(f"{nombre}: no existe {v}")
        for nombre in ("zhf", "terreno", "actual", "zona_control"):
            f = getattr(self, nombre)
            if f and not Path(f.archivo).is_file():
                errores.append(f"{nombre}: no existe {f.archivo}")
        if not self.terreno:
            errores.append("terreno es obligatorio: es el avaluo de referencia y el terreno que se conserva")
        return errores


def _ruta(valor: str, base: Path) -> str:
    p = Path(valor)
    return str(p if p.is_absolute() else (base / p).resolve())


# ---------------------------------------------------------------------------
# Lectura
# ---------------------------------------------------------------------------

def num(s: pd.Series) -> pd.Series:
    """Numero desde texto con coma o punto decimal."""
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def ids(s: pd.Series) -> pd.Series:
    """Identificador como texto, sin el .0 que deja un float."""
    return s.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()


def leer(ruta: str, columnas: list[str] | None = None) -> pd.DataFrame:
    """Parquet, Excel o texto separado por | (los export de Sistemas)."""
    ext = Path(ruta).suffix.lower()
    if ext == ".parquet":
        return pd.read_parquet(ruta, columns=columnas)
    if ext in (".xlsx", ".xls"):
        d = pd.read_excel(ruta, dtype=str)
        return d[columnas] if columnas else d
    return pd.read_csv(ruta, sep="|", dtype=str, encoding="latin-1", usecols=columnas)


def leer_predios(ruta: str) -> pd.DataFrame:
    """El listado a reliquidar. Debe traer una columna ID_PREDIO (o parecida)."""
    d = leer(ruta)
    col = next((c for c in d.columns if str(c).strip().upper().replace(" ", "_") in ("ID_PREDIO", "IDPREDIO", "PREDIO")),
               None)
    if col is None:
        raise ValueError(f"El listado {ruta} no tiene una columna ID_PREDIO. Columnas: {list(d.columns)}")
    d = d.rename(columns={col: "ID_PREDIO"})
    d.columns = [str(c).strip().upper().replace(" ", "_") for c in d.columns]
    d["ID_PREDIO"] = ids(d.ID_PREDIO)
    return d.drop_duplicates("ID_PREDIO")


def _columna_por_predio(fuente: Fuente, clave: str, defecto: str, lista: set) -> pd.Series:
    col = fuente.columnas.get(clave, defecto)
    d = leer(fuente.archivo, ["ID_PREDIO", col])
    d["ID_PREDIO"] = ids(d.ID_PREDIO)
    return d[d.ID_PREDIO.isin(lista)].drop_duplicates("ID_PREDIO").set_index("ID_PREDIO")[col]


# ---------------------------------------------------------------------------
# Motores de tablas
# ---------------------------------------------------------------------------

def _motor_2025(d: pd.DataFrame) -> pd.DataFrame:
    from Liquidacion_tablas_2025 import tablas_liquidacion
    return tablas_liquidacion(d)


def _motor_2024(d: pd.DataFrame) -> pd.DataFrame:
    from Liquidacion_tablas_2024 import tablas_liquidacion_2024
    return tablas_liquidacion_2024(d)


MOTORES = {"2024": _motor_2024, "2025": _motor_2025}


def iba_por_modelo(b: pd.DataFrame, reglas: str) -> pd.Series:
    """Construcciones que en ese ejercicio no se liquidaban por tabla sino por modelo."""
    cond = num(b.CONDICION).fillna(0).astype(int)
    if reglas == "2025":
        dest = b.DESTINOCONS.astype(str).str.strip().str.zfill(3)
        return dest.isin(MODELO_2025) & (cond == 9)
    return b.USO_LADM.isin(USOS_MODELO_2024) & (cond != 8)


def liquidar_por_tablas(b: pd.DataFrame, reglas: str, comuna: str | None, factor: float) -> pd.DataFrame:
    """Valor catastral de cada construccion con las tablas del ejercicio.

    Lo que iba por modelo se manda a tabla como la condicion 8 y las especiales
    pierden su valor especial: todo sale de la tabla.
    """
    from escenarios import _normalizar, _resultado

    d = b.copy()
    if comuna:
        d["COMUNA"] = comuna
    d.loc[d.IBA_POR_MODELO, "CONDICION"] = 8
    if "ESPECIAL" in d.columns:
        d.loc[d.ERA_ESPECIAL, "ESPECIAL"] = "0"
    with contextlib.redirect_stdout(io.StringIO()):
        r = _resultado(_normalizar(MOTORES[reglas](d)), reglas)
    r = r.drop_duplicates(LLAVE).set_index(LLAVE)

    u = b.drop_duplicates(LLAVE).set_index(LLAVE)
    out = pd.DataFrame(index=u.index)
    out["TABLA"] = r[f"TABLA_{reglas}"].reindex(out.index)
    out["METODO"] = r[f"METODO_{reglas}"].reindex(out.index)
    out["VM2_COMERCIAL"] = r[f"VM2_{reglas}"].reindex(out.index).fillna(0)
    por_unidad = (r[f"UNIDAD_{reglas}"].reindex(out.index).eq("por unidad")
                  & u.DESTINOCONS.astype(str).str.strip().str.zfill(3).isin(PARQUEADEROS_POR_UNIDAD))
    area = num(u.AREA_CONST).fillna(0)
    out["UNIDAD"] = np.where(por_unidad, "por unidad", "por m2")
    out["VALOR_CATASTRAL"] = np.where(por_unidad, out.VM2_COMERCIAL, out.VM2_COMERCIAL * area) * factor
    return out


# ---------------------------------------------------------------------------
# Mutaciones: que habia en la referencia y ya no esta igual hoy
# ---------------------------------------------------------------------------

def _k2(s):
    return num(s).round(2).map(lambda v: "" if pd.isna(v) else f"{v:.2f}")


def _k0(s):
    return num(s).fillna(0).round(0).astype("Int64").astype(str)


def llave_construccion(id_predio, area, puntaje):
    """Construcciones de dos vigencias se cruzan por predio + area + puntaje (el ID no se conserva)."""
    return "C|" + id_predio + "|" + _k2(area) + "|" + _k0(puntaje)


def llave_anexo(id_predio, destino, tipo, area):
    return "A|" + id_predio + "|" + _k0(destino) + "|" + _k0(tipo) + "|" + _k2(area)


def valores_referencia(cfg: Configuracion, lista: set) -> pd.Series:
    """Valor de cada construccion y anexo en la vigencia de referencia, por llave."""
    partes = []
    if cfg.export_construcciones:
        x = leer(cfg.export_construcciones, ["ID_PREDIO", "ACONCONS", "PUNTCONS", "VALORCONS"])
        x = x[ids(x.ID_PREDIO).isin(lista)]
        partes.append(pd.DataFrame({"K": llave_construccion(ids(x.ID_PREDIO), x.ACONCONS, x.PUNTCONS),
                                    "V": num(x.VALORCONS)}))
    if cfg.export_anexos:
        x = leer(cfg.export_anexos, ["ID_PREDIO", "DESTANEX", "TIPOANEXO", "ACONANEX", "VALOANEX"])
        x = x[ids(x.ID_PREDIO).isin(lista)]
        partes.append(pd.DataFrame({"K": llave_anexo(ids(x.ID_PREDIO), x.DESTANEX, x.TIPOANEXO, x.ACONANEX),
                                    "V": num(x.VALOANEX)}))
    if not partes:
        return pd.Series(dtype=float)
    return pd.concat(partes).groupby("K").V.first()


# ---------------------------------------------------------------------------
# Proceso
# ---------------------------------------------------------------------------

def reliquidar(cfg: Configuracion) -> Path:
    errores = cfg.validar()
    if errores:
        raise ValueError("Configuracion invalida:\n - " + "\n - ".join(errores))
    ref, nueva = cfg.etiqueta_referencia, cfg.etiqueta_nueva
    print(f"=== RELIQUIDACION: {cfg.nombre} ===")
    print(f"   reglas {cfg.reglas} | comuna de las tablas: {cfg.comuna_reglas or 'la del predio'} | "
          f"factor {cfg.factor_catastral}")

    R = leer_predios(cfg.predios)
    lista = set(R.ID_PREDIO)
    print(f"   predios en el listado: {len(lista):,}")

    b = pd.read_parquet(cfg.base_construcciones)
    b["ID_PREDIO"] = ids(b.ID_PREDIO)
    b = b[b.ID_PREDIO.isin(lista)].copy()
    b[LLAVE] = b[LLAVE].astype(str)
    print(f"   construcciones de hoy de esos predios: {len(b):,} en {b.ID_PREDIO.nunique():,} predios")

    # ZHF: la de la base, o la de otro export si se pide.
    b["ZHF"] = ids(b.ZHF)
    b["ZHF_BASE"] = b.ZHF
    if cfg.zhf:
        z = ids(_columna_por_predio(cfg.zhf, "zhf", "ZHF", lista))
        b["ZHF"] = b.ID_PREDIO.map(z).fillna(b.ZHF_BASE)
        print(f"   ZHF tomada de {Path(cfg.zhf.archivo).name}")
    b["CAMBIO_TIPOLOGIA_ZHF"] = b.ZHF.str[-3:] != b.ZHF_BASE.str[-3:]

    b["IBA_POR_MODELO"] = iba_por_modelo(b, cfg.reglas)
    b["ERA_ESPECIAL"] = b.ESPECIAL.astype(str).str.strip().eq("1") if "ESPECIAL" in b.columns else False
    b["ES_ANEXO"] = num(b.DESTANEX).fillna(0) > 0
    b["AREA"] = num(b.AREA_CONST).fillna(0)

    oficial = valores_referencia(cfg, lista)
    b["K"] = np.where(b.ES_ANEXO, llave_anexo(b.ID_PREDIO, b.DESTANEX, b.TIPOANEXO, b.ACONANEX),
                      llave_construccion(b.ID_PREDIO, b.ACONCONS, b.PUNTCONS))
    hay_ref = len(oficial) > 0
    b["IGUAL_EN_REFERENCIA"] = b.K.isin(oficial.index) if hay_ref else pd.NA
    b[f"VALOR_{ref}"] = b.K.map(oficial) if hay_ref else np.nan

    print("   liquidando por tablas...")
    liq = liquidar_por_tablas(b, cfg.reglas, cfg.comuna_reglas, cfg.factor_catastral)
    c = b.copy()
    for col in liq.columns:
        c[col] = c[LLAVE].map(liq[col])
    if cfg.comuna_referencia:
        alt = liquidar_por_tablas(b, cfg.reglas, cfg.comuna_referencia, cfg.factor_catastral)
        c[f"VALOR_COMUNA_{cfg.comuna_referencia}"] = c[LLAVE].map(alt.VALOR_CATASTRAL)

    c["NOVEDAD"] = _novedades_construccion(c, ref, hay_ref)

    p = _por_predio(c, R, cfg, oficial, lista)
    excluidos = p[p.N_IBA_POR_MODELO > 0][["ID_PREDIO", "N_IBA_POR_MODELO"]] if cfg.excluir_modelo else p.iloc[0:0]
    if cfg.excluir_modelo:
        p = p[p.N_IBA_POR_MODELO == 0].copy()
        c = c[c.ID_PREDIO.isin(p.ID_PREDIO)].copy()
        print(f"   excluidos por ir por modelo: {len(excluidos):,} predios")

    salida = _escribir(cfg, R, p, c, oficial, b, excluidos)
    print(f"   escrito: {salida}")
    return salida


def _novedades_construccion(c: pd.DataFrame, ref: str, hay_ref: bool) -> pd.Series:
    def una(x):
        m = []
        if hay_ref and not x.IGUAL_EN_REFERENCIA:
            m.append(f"MUTACION: no estaba igual en {ref} (nueva, o cambio uso/area/puntaje)")
        if x.CAMBIO_TIPOLOGIA_ZHF:
            m.append(f"ZHF: tipologia {str(x.ZHF)[-3:]} usada, {str(x.ZHF_BASE)[-3:]} en la base de hoy")
        if x.IBA_POR_MODELO:
            m.append("IBA POR MODELO en ese ejercicio: aqui por tabla")
        if x.ERA_ESPECIAL:
            m.append("ESPECIAL en la base: aqui por tabla")
        if x.VALOR_CATASTRAL <= 0:
            m.append(f"SIN VALOR por tabla ({x.METODO}, {x.TABLA})")
        return " | ".join(m)
    return c.apply(una, axis=1)


def _por_predio(c, R, cfg, oficial, lista):
    ref, nueva = cfg.etiqueta_referencia, cfg.etiqueta_nueva
    g = c.groupby("ID_PREDIO")
    p = pd.DataFrame({
        "CONSTRUCCIONES_HOY": g.size(),
        "AREA_CONST_HOY": g.apply(lambda x: x.loc[~x.ES_ANEXO, "AREA"].sum()),
        f"CONST_{nueva}": g.apply(lambda x: x.loc[~x.ES_ANEXO, "VALOR_CATASTRAL"].sum()),
        f"ANEXOS_{nueva}": g.apply(lambda x: x.loc[x.ES_ANEXO, "VALOR_CATASTRAL"].sum()),
        "N_IBA_POR_MODELO": g.IBA_POR_MODELO.sum(),
        "N_ESPECIAL": g.ERA_ESPECIAL.sum(),
        "N_SIN_VALOR": g.VALOR_CATASTRAL.apply(lambda s: int((s <= 0).sum())),
        "N_CAMBIO_ZHF": g.CAMBIO_TIPOLOGIA_ZHF.sum(),
        "N_HOY_NO_ESTABA": g.IGUAL_EN_REFERENCIA.apply(lambda s: int((s == False).sum())),  # noqa: E712
    }).reset_index()
    alt = [k for k in c.columns if k.startswith("VALOR_COMUNA_")]
    for k in alt:
        p = p.merge(g[k].sum().rename(k.replace("VALOR_", "CONST_ANEXOS_")).reset_index(), on="ID_PREDIO")

    # Lo de la referencia que ya no esta igual hoy.
    if len(oficial):
        k = pd.DataFrame({"K": list(oficial.index)})
        k["ID_PREDIO"] = k.K.str.split("|").str[1]
        hoy = set(c.K)
        p = p.merge(k.groupby("ID_PREDIO").agg(
            CONSTRUCCIONES_REFERENCIA=("K", "size"),
            N_REFERENCIA_NO_ESTA_HOY=("K", lambda s: int((~s.isin(hoy)).sum()))).reset_index(),
            on="ID_PREDIO", how="outer")

    # Terreno y avaluo de referencia.
    t = cfg.terreno
    cols = {"avaluo": "AVALPRED", "terreno": "VTER", "construccion": "VCONST", "anexos": "VANEXO",
            "area_terreno": "AREAPRED"} | t.columnas
    o = leer(t.archivo, ["ID_PREDIO"] + list(dict.fromkeys(cols.values())))
    o["ID_PREDIO"] = ids(o.ID_PREDIO)
    o = o[o.ID_PREDIO.isin(lista)].drop_duplicates("ID_PREDIO")
    o = pd.DataFrame({"ID_PREDIO": o.ID_PREDIO,
                      f"AVALUO_{ref}": num(o[cols["avaluo"]]), f"TERRENO_{ref}": num(o[cols["terreno"]]),
                      f"CONST_{ref}": num(o[cols["construccion"]]), f"ANEXOS_{ref}": num(o[cols["anexos"]]),
                      "AREA_TERRENO": num(o[cols["area_terreno"]])})
    d = R.merge(o, on="ID_PREDIO", how="left").merge(p, on="ID_PREDIO", how="left")

    if cfg.actual:
        a = _columna_por_predio(cfg.actual, "avaluo", "AVALPRED", lista)
        d["AVALUO_ACTUAL"] = d.ID_PREDIO.map(num(a))

    for col in [x for x in d.columns if x.startswith("N_")] + ["CONSTRUCCIONES_HOY", "AREA_CONST_HOY",
                                                               f"CONST_{nueva}", f"ANEXOS_{nueva}"]:
        d[col] = d[col].fillna(0)
    d["ES_LOTE"] = d.CONSTRUCCIONES_HOY.eq(0)

    ter = d[f"TERRENO_{ref}"].fillna(0)
    d[f"AVALUO_{nueva}"] = (ter + d[f"CONST_{nueva}"] + d[f"ANEXOS_{nueva}"]).round(-3)
    for k in alt:
        d[k.replace("VALOR_", "AVALUO_")] = (ter + d[k.replace("VALOR_", "CONST_ANEXOS_")].fillna(0)).round(-3)
    d["DIFERENCIA"] = d[f"AVALUO_{nueva}"] - d[f"AVALUO_{ref}"]
    d["VARIACION_PCT"] = (d.DIFERENCIA / d[f"AVALUO_{ref}"].replace(0, np.nan) * 100).round(2)
    d["RANGO_VARIACION"] = pd.cut(d.VARIACION_PCT, RANGOS, labels=ETIQUETAS_RANGO, right=False).astype(str)
    d["SENTIDO"] = np.select([d.VARIACION_PCT < -1, d.VARIACION_PCT >= 1], ["BAJA", "SUBE"], default="SIN VARIACION")

    # Control del terreno: zona x area x factor.
    d["VALIDACION_TERRENO"] = ""
    if cfg.zona_control:
        z = num(_columna_por_predio(cfg.zona_control, "zona", "ZHG_2024", lista))
        d["VALOR_ZONA"] = d.ID_PREDIO.map(z)
        calc = (d.VALOR_ZONA * d.AREA_TERRENO * cfg.factor_catastral).round(0)
        d["TERRENO_CALCULADO_ZONA"] = calc
        d["VALIDACION_TERRENO"] = np.select(
            [ter <= 0, (ter - calc).abs() <= cfg.tolerancia_terreno + 0.001 * ter],
            ["TERRENO EN 0 (en PH el suelo va dentro del avaluo integral)", "OK: zona x area x factor"],
            default="REVISAR: no cuadra con zona x area x factor")

    d["OBSERVACION_MUTACION"] = d.apply(lambda r: _mutacion(r, ref), axis=1)
    d["NOVEDAD"] = d.apply(_novedades_predio, axis=1)
    d["TIENE_NOVEDAD"] = np.where(d.NOVEDAD.ne(""), "SI", "NO")
    d["GRUPO"] = np.select([d.ES_LOTE, d.N_IBA_POR_MODELO > 0],
                           ["LOTE (solo terreno)", "IBA POR MODELO"], default="CONSTRUCCIONES POR TABLA")
    return d


def _mutacion(r, ref):
    hoy = r.get("N_HOY_NO_ESTABA", 0) or 0
    antes = r.get("N_REFERENCIA_NO_ESTA_HOY", 0) or 0
    if not hoy and not antes:
        return "SIN MUTACION"
    return (f"MUTACION: {int(hoy)} construccion(es)/anexo(s) de hoy no estaban igual en {ref} y "
            f"{int(antes)} de {ref} ya no estan igual hoy")


def _novedades_predio(r):
    n = []
    if str(r.OBSERVACION_MUTACION).startswith("MUTACION"):
        n.append("mutacion")
    if r.N_CAMBIO_ZHF:
        n.append("tipologia de la ZHF distinta a la de hoy")
    if r.N_IBA_POR_MODELO:
        n.append("construcciones que iban por modelo")
    if r.N_ESPECIAL:
        n.append("construccion especial liquidada por tabla")
    if r.N_SIN_VALOR:
        n.append("construccion sin valor por tabla")
    if str(r.VALIDACION_TERRENO).startswith("REVISAR"):
        n.append("terreno no cuadra con zona x area x factor")
    return "; ".join(n)


def resumen(d: pd.DataFrame, por: str, ref: str, nueva: str) -> pd.DataFrame:
    """Predios y avaluos por rango (o por sentido), separando con y sin novedad."""
    g = d.groupby(por, observed=False)
    r = pd.DataFrame({
        "PREDIOS": g.size(),
        "SIN_NOVEDAD": g.TIENE_NOVEDAD.apply(lambda s: int(s.eq("NO").sum())),
        "CON_NOVEDAD": g.TIENE_NOVEDAD.apply(lambda s: int(s.eq("SI").sum())),
        f"AVALUO_{ref}": g[f"AVALUO_{ref}"].sum(),
        f"AVALUO_{nueva}": g[f"AVALUO_{nueva}"].sum(),
    })
    if por == "RANGO_VARIACION":
        r = r.reindex(ETIQUETAS_RANGO).fillna(0)
    r.loc["TOTAL"] = r.sum()
    r["DIFERENCIA"] = r[f"AVALUO_{nueva}"] - r[f"AVALUO_{ref}"]
    r["VARIACION_PCT"] = (r.DIFERENCIA / r[f"AVALUO_{ref}"].replace(0, np.nan) * 100).round(2)
    r["PCT_PREDIOS"] = (r.PREDIOS / max(len(d), 1) * 100).round(1)
    return r.rename_axis(por).reset_index()


def _escribir(cfg, R, p, c, oficial, b, excluidos) -> Path:
    ref, nueva = cfg.etiqueta_referencia, cfg.etiqueta_nueva
    carpeta = Path(cfg.salida)
    carpeta.mkdir(parents=True, exist_ok=True)
    salida = carpeta / f"RELIQUIDACION_{cfg.nombre}_{datetime.now():%Y%m%d_%H%M}.xlsx"

    extra = [x for x in R.columns if x != "ID_PREDIO"]
    alt = [x for x in p.columns if x.startswith("AVALUO_COMUNA_")]
    cols_p = (extra + ["ID_PREDIO", "GRUPO", "TIENE_NOVEDAD", "NOVEDAD", f"AVALUO_{ref}", f"AVALUO_{nueva}",
                       "DIFERENCIA", "VARIACION_PCT", "RANGO_VARIACION", "SENTIDO", f"TERRENO_{ref}", f"CONST_{ref}",
                       f"ANEXOS_{ref}", f"CONST_{nueva}", f"ANEXOS_{nueva}"]
              + (["AVALUO_ACTUAL"] if "AVALUO_ACTUAL" in p.columns else []) + alt
              + ["OBSERVACION_MUTACION", "CONSTRUCCIONES_HOY", "AREA_CONST_HOY", "N_IBA_POR_MODELO", "N_ESPECIAL",
                 "N_SIN_VALOR", "N_CAMBIO_ZHF", "AREA_TERRENO"]
              + [x for x in ("VALOR_ZONA", "TERRENO_CALCULADO_ZONA") if x in p.columns] + ["VALIDACION_TERRENO"])
    pred = p[[x for x in dict.fromkeys(cols_p) if x in p.columns]].sort_values(["TIENE_NOVEDAD", "VARIACION_PCT"],
                                                                              ascending=[False, True])

    c = c.copy()
    c["TIPO"] = np.where(c.ES_ANEXO, "ANEXO", "CONSTRUCCION")
    c["VM2_CATASTRAL"] = (c.VM2_COMERCIAL * cfg.factor_catastral).round(2)
    c["DIFERENCIA"] = c.VALOR_CATASTRAL - c[f"VALOR_{ref}"]
    c["VARIACION_PCT"] = (c.DIFERENCIA / c[f"VALOR_{ref}"].replace(0, np.nan) * 100).round(2)
    cols_c = ["ID_PREDIO", LLAVE, "TIPO", "USO_LADM", "DESTINOCONS", "DESTANEX", "TIPOANEXO", "CONDICION", "ESTRPRED",
              "ZHF", "ZHF_BASE", "PUNTCONS", "AREA", "IGUAL_EN_REFERENCIA", f"VALOR_{ref}", "TABLA", "UNIDAD",
              "VM2_COMERCIAL", "VM2_CATASTRAL", "VALOR_CATASTRAL", "DIFERENCIA", "VARIACION_PCT", "NOVEDAD"] + \
             [x for x in c.columns if x.startswith("VALOR_COMUNA_")]
    cons = (c[[x for x in cols_c if x in c.columns]].rename(columns={"AREA": "AREA_LIQUIDADA", "VALOR_CATASTRAL": f"VALOR_{nueva}",
                                      "VM2_COMERCIAL": "VM2_COMERCIAL_O_VALOR_UNIDAD"})
            .sort_values(["ID_PREDIO", "TIPO", LLAVE]))

    ya_no = pd.DataFrame()
    if len(oficial):
        k = pd.DataFrame({"K": list(oficial.index), f"VALOR_{ref}": oficial.values})
        k = k[~k.K.isin(set(b.K)) & k.K.str.split("|").str[1].isin(set(p.ID_PREDIO))]
        parte = k.K.str.split("|")
        ya_no = pd.DataFrame({
            "ID_PREDIO": parte.str[1], "TIPO": np.where(parte.str[0].eq("C"), "CONSTRUCCION", "ANEXO"),
            "DETALLE": np.where(parte.str[0].eq("C"), "area " + parte.str[2] + " m2, puntaje " + parte.str[3],
                                "destino " + parte.str[2] + ", tipo " + parte.str[3] + ", area "
                                + parte.str[4].fillna("") + " m2"),
            f"VALOR_{ref}": k[f"VALOR_{ref}"].values})

    novedades = (p[p.TIENE_NOVEDAD.eq("SI")].assign(NOVEDAD=lambda x: x.NOVEDAD.str.split("; ")).explode("NOVEDAD")
                 .groupby("NOVEDAD").agg(PREDIOS=("ID_PREDIO", "size"), **{
                     f"AVALUO_{ref}": (f"AVALUO_{ref}", "sum"), f"AVALUO_{nueva}": (f"AVALUO_{nueva}", "sum")})
                 .reset_index())
    parametros = pd.DataFrame({"PARAMETRO": list(_parametros(cfg)), "VALOR": list(_parametros(cfg).values())})
    notas = pd.DataFrame({"NOTA": [
        f"AVALUO_{nueva} = TERRENO_{ref} + CONST_{nueva} + ANEXOS_{nueva}, redondeado a miles. Todo catastral.",
        f"El terreno se conserva: es el de {ref} (archivo de terreno), no se recalcula.",
        f"Construcciones con los datos fisicos de hoy y las tablas del ejercicio {cfg.reglas}; factor "
        f"{cfg.factor_catastral}. VM2_CATASTRAL = VM2_COMERCIAL x factor; VALOR = VM2_CATASTRAL x area.",
        "Parqueaderos T12 (usos 007, 008, 036, 037): la columna VM2_COMERCIAL_O_VALOR_UNIDAD es el valor total del "
        "parqueadero (cupo x factor de area), no por m2. Los depositos (006, 027) si van por m2.",
        f"DIFERENCIA = valor {nueva} - valor {ref}. VARIACION_PCT sobre el valor {ref}.",
        "MUTACION: la construccion de hoy no esta igual en la referencia (se cruza por predio + area + puntaje; "
        "anexos por predio + destino + tipo + area). La hoja REFERENCIA_YA_NO_ESTA trae el otro lado.",
        "Lo que iba por modelo en ese ejercicio se liquida por tabla (como la condicion 8) y queda marcado"
        + ("; con excluir_modelo esos predios salen del archivo y se listan en EXCLUIDOS_MODELO." if cfg.excluir_modelo
           else ".")]})

    hojas = [("RESUMEN_RANGOS", resumen(p, "RANGO_VARIACION", ref, nueva)),
             ("SUBEN_BAJAN", resumen(p, "SENTIDO", ref, nueva)),
             ("RANGOS_SIN_NOVEDAD", resumen(p[p.TIENE_NOVEDAD.eq("NO")], "RANGO_VARIACION", ref, nueva)),
             ("NOVEDADES", novedades), ("PREDIOS", pred), ("CONSTRUCCIONES", cons),
             ("REFERENCIA_YA_NO_ESTA", ya_no)]
    if cfg.excluir_modelo:
        hojas.append(("EXCLUIDOS_MODELO", R.merge(excluidos, on="ID_PREDIO")))
    hojas += [("PARAMETROS", parametros), ("NOTAS", notas)]

    with pd.ExcelWriter(salida, engine="xlsxwriter") as w:
        wb = w.book
        enc = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True,
                             "valign": "vcenter", "border": 1})
        pesos = wb.add_format({"num_format": "$ #,##0;[Red]-$ #,##0"})
        pct = wb.add_format({"num_format": "0.00;[Red]-0.00"})
        amarillo = wb.add_format({"bg_color": "#FFF2CC"})
        for nombre, df in hojas:
            df.to_excel(w, sheet_name=nombre, index=False, startrow=1, header=False)
            ws = w.sheets[nombre]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, enc)
                es_pesos = col.startswith(("AVALUO", "DIFERENCIA", "TERRENO", "CONST_", "ANEXOS_", "VALOR_", "VM2_"))
                fmt = pct if col.endswith("PCT") else (pesos if es_pesos else None)
                ancho = 70 if col in ("NOVEDAD", "OBSERVACION_MUTACION", "NOTA", "VALOR", "DETALLE") else 18
                ws.set_column(j, j, ancho, fmt)
            ws.set_row(0, 32)
            ws.freeze_panes(1, 1)
            if nombre in ("PREDIOS", "CONSTRUCCIONES") and len(df):
                ws.autofilter(0, 0, len(df), len(df.columns) - 1)
                marca = "TIENE_NOVEDAD" if nombre == "PREDIOS" else "NOVEDAD"
                j = list(df.columns).index(marca)
                letra = _letra(j)
                crit = f'=${letra}2="SI"' if nombre == "PREDIOS" else f'=LEN(${letra}2)>0'
                ws.conditional_format(1, 0, len(df), len(df.columns) - 1,
                                      {"type": "formula", "criteria": crit, "format": amarillo})
    return salida


def _letra(j: int) -> str:
    s = ""
    j += 1
    while j:
        j, r = divmod(j - 1, 26)
        s = chr(65 + r) + s
    return s


def _parametros(cfg: Configuracion) -> dict:
    f = lambda x: f"{x.archivo}  columnas={x.columnas}" if x else ""
    return {"nombre": cfg.nombre, "listado de predios": cfg.predios, "base de construcciones": cfg.base_construcciones,
            "reglas (ejercicio)": cfg.reglas, "comuna cuyos valores se aplican": cfg.comuna_reglas or "la del predio",
            "comuna de referencia (comparacion)": cfg.comuna_referencia or "",
            "factor catastral": cfg.factor_catastral, "excluir lo que va por modelo": cfg.excluir_modelo,
            "ZHF": f(cfg.zhf) or "la de la base de construcciones",
            "terreno y avaluo de referencia": f(cfg.terreno), "avaluo actual": f(cfg.actual),
            "export de construcciones de referencia": cfg.export_construcciones or "",
            "export de anexos de referencia": cfg.export_anexos or "",
            "control de zona": f(cfg.zona_control), "ejecutado": f"{datetime.now():%Y-%m-%d %H:%M}"}


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 1:
        print("Uso: python src/reliquidacion.py configuracion.json")
        return 2
    src = str(Path(__file__).resolve().parent)
    if src not in sys.path:
        sys.path.insert(0, src)
    try:
        reliquidar(Configuracion.desde_json(args[0]))
        return 0
    except ValueError as e:
        print(f"[ERROR] {e}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
