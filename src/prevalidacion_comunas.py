"""Prevalidacion por comuna: ¿se puede liquidar lo que se selecciono?

Corre ANTES de liquidar (paso 0B, despues de la calidad de insumos) y tambien
sola, desde la interfaz o con `LiquidadorCatastral.exe --prevalidar manifest`.
Para cada comuna seleccionada revisa que tenga todo lo necesario para salir con
un avaluo completo:

  REGLA      la comuna esta en Reglas.xlsx y tiene grupo de tablas (7C / 10C).
  TABLAS     cada tabla que necesitan sus construcciones (segun su uso) existe
             en el consolidado con valores para su grupo; anexos en
             NO_CONVENCIONALES; parqueaderos avalados (liquidar_parqueaderos).
  MODELO     la propiedad horizontal que va por modelo tiene familia de modelo.
  ESPECIALES las construcciones especiales (020, 023) tienen como liquidarse.
  DATOS      predio por predio: ZHF, estrato, puntaje, area construida,
             terreno y coordenadas (las usan los modelos).

Resultado por comuna: APTA, APTA CON ADVERTENCIAS o NO APTA, con la lista de
lo que no cumple, y la lista de predios que no pasarian con el motivo de cada
uno. Escribe output/Prevalidacion/PREVALIDACION_COMUNAS_<run_id>.xlsx y el
detalle en parquet para el Excel de predios por corregir.
"""

from __future__ import annotations

import contextlib
import io
import os
import re
from dataclasses import dataclass, field
from datetime import datetime

import numpy as np
import pandas as pd

import comunas as C

# Usos de construccion -> familia de tabla (input/Reglas.xlsx).
RESIDENCIAL = {1, 4, 12, 13, 63}           # el 001 fuera de PH va por la tabla residencial
FAMILIA_POR_USO = {
    **{d: "T1_RESIDENCIAL" for d in RESIDENCIAL},
    3: "T2_EDIFICIOS",
    **{d: "T3_COMERCIAL" for d in (16, 21, 24, 25, 28, 39, 41, 42, 49, 38)},
    **{d: "T4_INDUSTRIAL" for d in (9, 17, 18, 47, 48)},
    **{d: "T5_INSTITUCIONAL_ED" for d in (50, 51, 55, 68, 70)},
    **{d: "T6_INSTITUCIONAL_SA" for d in (54, 67)},
    **{d: "T7_INSTITUCIONAL_SER" for d in (32, 33, 34, 52, 73, 74, 75, 76)},
    **{d: "T8_INSTITUCIONAL_IG" for d in (53, 60, 61)},
    **{d: "T9_HOTELES" for d in (30, 31)},
    **{d: "T11_CCOMERCIALES" for d in (19, 22, 43)},
    71: "T13_UNIDAD_DEPORTIVA",
    **{d: "T12_PARQUEADEROS" for d in (6, 7, 8, 27, 36, 37)},
    **{d: "ESPECIALES" for d in (20, 23)},
}
USOS_MODELO = {1, 28, 34}                 # con condicion 9 van por modelo
TABLAS_17C = {"T5_INSTITUCIONAL_ED", "T6_INSTITUCIONAL_SA", "T7_INSTITUCIONAL_SER", "T8_INSTITUCIONAL_IG",
              "T9_HOTELES", "T11_CCOMERCIALES", "T13_UNIDAD_DEPORTIVA"}
NECESITA_ZHF = {"T3_COMERCIAL", "T4_INDUSTRIAL"}

ACCIONES = {
    "REGLA": "Definir la regla y el grupo de tablas de la comuna (Reglas.xlsx) o quitarla de la seleccion.",
    "TABLA": "Entregar la tabla en el consolidado de tablas de valor (input/tablas).",
    "PARQUEADEROS": "Aprobar los valores de parqueaderos (T12) y activar 'liquidar_parqueaderos' en el manifiesto.",
    "MODELO": "Definir modelo o tabla para la propiedad horizontal de la comuna.",
    "ESPECIALES": "Cargar el valor de las construcciones especiales (hoy no se liquidan).",
    "USO": "Revisar el destino: no tiene regla de tabla en Reglas.xlsx.",
    "ZHF": "Pedir a Sistemas la ZHF del predio.",
    "PUNTAJE": "Pedir la calificacion (PUNTCONS) de la construccion.",
    "AREA": "Pedir el area construida.",
    "TERRENO": "Pedir el valor y el area de terreno (export de terrenos).",
    "COORDENADAS": "Pedir las coordenadas del predio: las usa el modelo de propiedad horizontal.",
    "ESTRATO": "Sin ZHF ni estrato: el residencial se liquida con la tabla del estrato 6.",
}


@dataclass
class Resultado:
    comunas: pd.DataFrame
    criterios: pd.DataFrame
    predios: pd.DataFrame
    detalle: pd.DataFrame
    tablas: pd.DataFrame
    ruta: str | None = None
    no_aptas: list = field(default_factory=list)


# ---------------------------------------------------------------------------
# Consolidado de tablas
# ---------------------------------------------------------------------------

def tablas_disponibles(ruta_tablas: str | None) -> tuple[set, set]:
    """(tablas convencionales con valores como 'T1_RESIDENCIAL_10C_COND_9', grupos de anexos con valores)."""
    if not ruta_tablas or not os.path.isfile(ruta_tablas):
        return set(), set()
    conv = pd.read_excel(ruta_tablas, sheet_name="CONVENCIONALES")
    con_valores = set()
    for col in conv.columns[1:]:
        if pd.to_numeric(conv[col], errors="coerce").fillna(0).gt(0).any():
            con_valores.add(re.sub(r"_\d{3}$", "", str(col).strip()))
    anexos = set()
    try:
        nc = pd.read_excel(ruta_tablas, sheet_name="NO_CONVENCIONALES")
        for col in nc.columns[1:]:
            m = re.search(r"_(\d+C)$", str(col))
            if m and pd.to_numeric(nc[col], errors="coerce").fillna(0).gt(0).any():
                anexos.add(m.group(1))
    except ValueError:
        pass
    return con_valores, anexos


def tiene_tabla(familia: str, grupo: str, cond9: bool, disponibles: set) -> bool:
    if familia in TABLAS_17C:
        return f"{familia}_17C" in disponibles
    if familia == "T1_RESIDENCIAL" and grupo == "10C":
        return f"T1_RESIDENCIAL_10C_COND_{9 if cond9 else 0}" in disponibles
    return f"{familia}_{grupo}" in disponibles


# ---------------------------------------------------------------------------
# Lectura y clasificacion de construcciones
# ---------------------------------------------------------------------------

def _leer(ruta, columnas):
    """Las columnas pedidas, como texto; las que el archivo no trae quedan vacias."""
    from calidad_insumos import _leer as leer_cols
    d = leer_cols(ruta, columnas)
    for col in columnas:
        if col not in d.columns:
            d[col] = pd.NA
    return d


def _num(s):
    return pd.to_numeric(s.astype(str).str.replace(",", ".", regex=False), errors="coerce")


def _homologar(conv: pd.DataFrame, anexos: pd.DataFrame, comuna: pd.Series, condicion: pd.Series) -> pd.Series:
    """Destino en la codificacion actual. Las comunas no actualizadas traen la vieja: se traduce como en el paso 2."""
    destino = _num(conv.DESTINOCONS).fillna(0).astype(int)
    actualizadas = set(C.COMUNAS_7) | set(C.COMUNAS_MODELO_2025)
    viejas = ~comuna.isin(actualizadas) & comuna.isin(C.COMUNAS_URBANAS)
    if viejas.any():
        try:
            from Homologacion import aplicar_homologacion
            # aplicar_homologacion reordena y reindexa: la fila original viaja en _FILA.
            d = pd.DataFrame({"DESTINOCONS_2025": destino[viejas].values, "DESTANEX_2025": 0,
                              "CONDICION": condicion[viejas].values, "_FILA": conv.index[viejas]})
            with contextlib.redirect_stdout(io.StringIO()):
                h = aplicar_homologacion(d)
            h = h[h._FILA.notna()]
            nuevo = _num(h.DESTINOCONS)
            ok = nuevo.notna() & (nuevo > 0)
            destino.loc[h.loc[ok, "_FILA"].astype(destino.index.dtype)] = nuevo[ok].astype(int).values
        except Exception as e:                                     # pragma: no cover
            print(f"   [WARN] prevalidacion: no se pudo homologar el destino de las comunas no actualizadas ({e})")
    return destino


MODELOS_PKL = {
    "2025": ("models", ["modelo_gbr_M1.pkl", "pipeline_M02_DIF_023.pkl", "pipeline_M02_IGUAL_023.pkl",
                        "M3_RF_20251221.pkl"]),
    "2024": ("models_2024", ["21_12_2024_model_GBR_M1.pkl", "21_12_2024_model_XGB_M3.pkl", "M4_OFICINAS_20241227.pkl"]),
}


def modelos_faltantes(familia: str) -> list[str]:
    """Los .pkl de la familia que no estan donde el motor los va a buscar."""
    try:
        import model_liq
        carpeta = model_liq.RUTA_MODELOS_2025 if familia == "2025" else model_liq.RUTA_MODELOS_2024
    except Exception:                                               # pragma: no cover
        return []
    _, archivos = MODELOS_PKL[familia]
    return [a for a in archivos if not os.path.isfile(os.path.join(carpeta, a))]


def clasificar(destino: pd.Series, condicion: pd.Series) -> pd.Series:
    fam = destino.map(FAMILIA_POR_USO).fillna("SIN REGLA")
    modelo = destino.isin(USOS_MODELO) & condicion.eq(9)
    return fam.where(~modelo, "MODELO")


# ---------------------------------------------------------------------------
# Prevalidacion
# ---------------------------------------------------------------------------

def prevalidar(insumos: dict, comunas_sel: list[str], ruta_tablas: str | None,
               liquidar_parqueaderos: bool = False, carpeta: str = "./output/Prevalidacion",
               run_id: str | None = None) -> Resultado:
    print(f"   comunas seleccionadas: {', '.join(comunas_sel)}")
    p = _leer(insumos["export_predio_actual"],
              ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "ZHF", "ESTRPRED", "AREAPRED", "ARECPRED", "LATITUDE", "LONGITUDE"])
    p["ID_PREDIO"] = p.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
    p["COMUNA"] = C.de_npn(p.NUMERO_PREDIAL_NACIONAL)
    p["CONDICION"] = _num(p.NUMERO_PREDIAL_NACIONAL.astype(str).str[21]).fillna(0).astype(int)
    p = p[p.COMUNA.isin(comunas_sel)].drop_duplicates("ID_PREDIO").copy()
    zhf = p.ZHF.astype(str).str.replace(r"\.0$", "", regex=True).str.strip()
    p["ZHF_VALIDA"] = (zhf.str.len() >= 11) & ~zhf.str.fullmatch(r"0+")
    p["ESTRATO"] = _num(p.ESTRPRED).fillna(0).astype(int)
    lat, lon = _num(p.LATITUDE), _num(p.LONGITUDE)
    p["COORDENADAS"] = lat.between(3.2, 3.65) & lon.between(-76.75, -76.40)
    ids = set(p.ID_PREDIO)
    info = p.set_index("ID_PREDIO")

    c = _leer(insumos["export_construccion_actual_conv"], ["ID_PREDIO", "DESTINOCONS", "ACONCONS", "PUNTCONS"])
    c["ID_PREDIO"] = c.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
    c = c[c.ID_PREDIO.isin(ids)].copy()
    c["COMUNA"] = c.ID_PREDIO.map(info.COMUNA)
    c["CONDICION"] = c.ID_PREDIO.map(info.CONDICION)
    c["DEST"] = _homologar(c, None, c.COMUNA, c.CONDICION)
    c["FAMILIA"] = clasificar(c.DEST, c.CONDICION)
    c["PUNTAJE_OK"] = (_num(c.PUNTCONS).fillna(0) > 0) | c.DEST.isin([6, 7, 8, 27, 36, 37])
    c["AREA_OK"] = _num(c.ACONCONS).fillna(0) > 0

    a = _leer(insumos["export_construccion_actual_noconv"], ["ID_PREDIO", "DESTANEX", "TIPOANEXO", "ACONANEX"])
    a["ID_PREDIO"] = a.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
    a = a[a.ID_PREDIO.isin(ids) & (_num(a.DESTANEX).fillna(0) > 0)].copy()
    a["COMUNA"] = a.ID_PREDIO.map(info.COMUNA)

    t = _leer(insumos["export_terreno_actual"], ["ID_PREDIO", "AMETTERR", "VALOTERR"])
    t["ID_PREDIO"] = t.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
    t = t[t.ID_PREDIO.isin(ids)]
    con_terreno = set(t.loc[_num(t.VALOTERR).fillna(0) > 0, "ID_PREDIO"])

    disponibles, anexos_ok = tablas_disponibles(ruta_tablas)
    sin_consolidado = not ruta_tablas or not os.path.isfile(ruta_tablas)
    if sin_consolidado:
        print(f"   [ERROR] no se encontro el consolidado de tablas de valor ({os.environ.get('VERSION_TABLAS', '?')})")
    else:
        print(f"   tablas de valor: {os.path.basename(ruta_tablas)}")
    filas = []          # (COMUNA, ID_PREDIO, CRITERIO, DETALLE, BLOQUEA, TIPO)

    def agregar(mask_df, comuna_col, criterio, detalle, bloquea, tipo):
        if len(mask_df):
            filas.append(pd.DataFrame({"COMUNA": mask_df[comuna_col].values, "ID_PREDIO": mask_df.ID_PREDIO.values,
                                       "CRITERIO": criterio, "DETALLE": detalle, "BLOQUEA": bloquea, "TIPO": tipo}))

    resumen_comunas, criterios = [], []
    for com in comunas_sel:
        grupo = C.grupo_tablas(com)
        pc, cc, ac = p[p.COMUNA.eq(com)], c[c.COMUNA.eq(com)], a[a.COMUNA.eq(com)]
        errores, avisos = [], []

        def criterio(nombre, n, bloquea, tipo, detalle=""):
            criterios.append({"COMUNA": com, "CRITERIO": nombre, "CONSTRUCCIONES_O_PREDIOS": n,
                              "NIVEL": "NO CUMPLE" if bloquea else "ADVERTENCIA", "DETALLE": detalle,
                              "ACCION": ACCIONES[tipo]})
            (errores if bloquea else avisos).append(f"{nombre} ({n:,})" if n else nombre)

        if pc.empty:
            criterio("Sin predios en el export para la comuna", 0, True, "REGLA")
        if sin_consolidado:
            criterio(f"No se encontro el consolidado de tablas de valor (version "
                     f"{os.environ.get('VERSION_TABLAS', '?')})", len(cc), True, "TABLA")
        if grupo is None:
            criterio("Comuna sin regla de tablas (no esta en Reglas.xlsx)", len(pc), True, "REGLA")
            agregar(pc, "COMUNA", "Comuna sin regla de tablas", f"Comuna {com}: no esta en Reglas.xlsx", True, "REGLA")
        elif com in C.COMUNAS_FALTANTES:
            criterio("Comuna liquidada con los valores del grupo 10C por decision (no esta en Reglas.xlsx)",
                     len(pc), False, "REGLA")

        if grupo is not None and len(cc):
            faltas = {}
            for (fam, cond9), g in cc.groupby([cc.FAMILIA, cc.CONDICION.eq(9)]):
                if fam in ("MODELO", "ESPECIALES", "SIN REGLA"):
                    continue
                if fam == "T12_PARQUEADEROS":
                    if not liquidar_parqueaderos:
                        faltas.setdefault(("Parqueaderos T12 sin valores avalados", "PARQUEADEROS"), 0)
                        faltas[("Parqueaderos T12 sin valores avalados", "PARQUEADEROS")] += len(g)
                        agregar(g, "COMUNA", "Parqueaderos T12 sin valores avalados",
                                "liquidar_parqueaderos desactivado", True, "PARQUEADEROS")
                    continue
                if not tiene_tabla(fam, grupo, bool(cond9), disponibles):
                    nombre = f"{fam}{'_COND_9' if (fam == 'T1_RESIDENCIAL' and cond9 and grupo == '10C') else ''}"
                    clave = (f"Tabla {nombre} ({grupo}) sin valores en el consolidado", "TABLA")
                    faltas[clave] = faltas.get(clave, 0) + len(g)
                    agregar(g, "COMUNA", "Tabla sin valores en el consolidado", f"{nombre} {grupo}", True, "TABLA")
            for (nombre, tipo), n in faltas.items():
                criterio(nombre, n, True, tipo)

        if grupo is not None and len(ac) and grupo not in anexos_ok:
            criterio(f"Anexos T10 ({grupo}) sin valores en el consolidado", len(ac), True, "TABLA")
            agregar(ac, "COMUNA", "Tabla sin valores en el consolidado", f"T10_ANEXOS {grupo}", True, "TABLA")

        mod = cc[cc.FAMILIA.eq("MODELO")]
        if len(mod):
            fam_modelo = C.familia_modelo(com)
            faltan_pkl = modelos_faltantes(fam_modelo) if fam_modelo else []
            if faltan_pkl:
                criterio(f"No se encuentran los modelos {fam_modelo}: {', '.join(faltan_pkl)}", len(mod), True, "MODELO")
                agregar(mod, "COMUNA", "Modelo no disponible", ", ".join(faltan_pkl), True, "MODELO")
            elif fam_modelo is None:
                criterio("Propiedad horizontal sin modelo para la comuna", len(mod), True, "MODELO")
                agregar(mod, "COMUNA", "Propiedad horizontal sin modelo", "usos 001/028/034 con condicion 9", True,
                        "MODELO")
            else:
                criterio(f"Propiedad horizontal liquidada con el modelo {fam_modelo} (no hay modelo 2027)",
                         len(mod), False, "MODELO")
                sin_coord = mod[~mod.ID_PREDIO.map(info.COORDENADAS).fillna(False)]
                if len(sin_coord):
                    criterio("Propiedad horizontal por modelo sin coordenadas validas", len(sin_coord), True,
                             "COORDENADAS")
                    agregar(sin_coord, "COMUNA", "Sin coordenadas para el modelo", "LATITUDE / LONGITUDE", True,
                            "COORDENADAS")

        esp = cc[cc.FAMILIA.eq("ESPECIALES")]
        if len(esp):
            criterio("Construcciones especiales sin valor (020, 023)", len(esp), True, "ESPECIALES")
            agregar(esp, "COMUNA", "Construccion especial sin valor", "usos 020 / 023", True, "ESPECIALES")

        sin_regla = cc[cc.FAMILIA.eq("SIN REGLA")]
        if len(sin_regla):
            usos = ", ".join(f"{u:03d}" for u in sorted(sin_regla.DEST.unique())[:10])
            criterio("Construcciones con uso sin regla de tabla", len(sin_regla), True, "USO", f"usos {usos}")
            agregar(sin_regla, "COMUNA", "Uso sin regla de tabla", "destino " + sin_regla.DEST.astype(str), True, "USO")

        # datos, predio por predio
        zhf_ok = cc.ID_PREDIO.map(info.ZHF_VALIDA).fillna(False)
        sin_zhf = cc[cc.FAMILIA.isin(NECESITA_ZHF) & ~zhf_ok]
        if len(sin_zhf):
            criterio("Comercial / industrial sin ZHF valida", len(sin_zhf), True, "ZHF")
            agregar(sin_zhf, "COMUNA", "Sin ZHF en comercial o industrial", "ZHF", True, "ZHF")
        res = cc[cc.FAMILIA.eq("T1_RESIDENCIAL") & ~zhf_ok & cc.ID_PREDIO.map(info.ESTRATO).fillna(0).eq(0)]
        if len(res):
            criterio("Residencial sin ZHF ni estrato (se usa estrato 6)", len(res), False, "ESTRATO")
            agregar(res, "COMUNA", "Residencial sin ZHF ni estrato", "ZHF / ESTRPRED", False, "ESTRATO")
        sin_punt = cc[~cc.PUNTAJE_OK & ~cc.FAMILIA.isin(["MODELO"])]
        if len(sin_punt):
            criterio("Construcciones sin puntaje", len(sin_punt), True, "PUNTAJE")
            agregar(sin_punt, "COMUNA", "Sin puntaje", "PUNTCONS", True, "PUNTAJE")
        sin_area = cc[~cc.AREA_OK]
        if len(sin_area):
            criterio("Construcciones sin area construida", len(sin_area), True, "AREA")
            agregar(sin_area, "COMUNA", "Sin area construida", "ACONCONS", True, "AREA")
        # terreno: los PH (8, 9) e informales (2, 5) no lo llevan propio
        necesita_ter = pc[~pc.CONDICION.isin([2, 5, 8, 9]) & (_num(pc.AREAPRED).fillna(0) > 0)]
        sin_ter = necesita_ter[~necesita_ter.ID_PREDIO.isin(con_terreno)]
        if len(sin_ter):
            criterio("Predios sin valor de terreno en el export", len(sin_ter), True, "TERRENO")
            agregar(sin_ter, "COMUNA", "Sin valor de terreno", "VALOTERR / AMETTERR", True, "TERRENO")

        estado = "NO APTA" if errores else ("APTA CON ADVERTENCIAS" if avisos else "APTA")
        resumen_comunas.append({
            "COMUNA": com, "GRUPO_TABLAS": grupo or "SIN GRUPO", "FAMILIA_MODELO": C.familia_modelo(com) or "-",
            "ESTADO": estado, "PREDIOS": len(pc), "CONSTRUCCIONES": len(cc), "ANEXOS": len(ac),
            "N_NO_CUMPLE": len(errores), "N_ADVERTENCIAS": len(avisos),
            "QUE_NO_CUMPLE": "; ".join(errores), "ADVERTENCIAS": "; ".join(avisos)})

    comunas_df = pd.DataFrame(resumen_comunas)
    criterios_df = pd.DataFrame(criterios, columns=["COMUNA", "CRITERIO", "CONSTRUCCIONES_O_PREDIOS", "NIVEL",
                                                    "DETALLE", "ACCION"])
    detalle = (pd.concat(filas, ignore_index=True) if filas
               else pd.DataFrame(columns=["COMUNA", "ID_PREDIO", "CRITERIO", "DETALLE", "BLOQUEA", "TIPO"]))
    detalle["ACCION"] = detalle.TIPO.map(ACCIONES)
    predios = _predios(detalle, info)
    tablas = _matriz_tablas(disponibles, anexos_ok, liquidar_parqueaderos)
    r = Resultado(comunas_df, criterios_df, predios, detalle, tablas,
                  no_aptas=comunas_df.loc[comunas_df.ESTADO.eq("NO APTA"), "COMUNA"].tolist())
    r.ruta = _escribir(r, carpeta, run_id)
    return r


def _predios(detalle: pd.DataFrame, info: pd.DataFrame) -> pd.DataFrame:
    if detalle.empty:
        return pd.DataFrame(columns=["ID_PREDIO", "COMUNA", "ESTADO", "QUE_NO_CUMPLE", "ADVERTENCIAS"])
    d = detalle.assign(TXT=detalle.CRITERIO + " [" + detalle.DETALLE.astype(str) + "]")

    def unir(s):
        cuenta = s.value_counts()
        return "; ".join(f"{k} x{v}" if v > 1 else k for k, v in cuenta.items())

    g = d.groupby("ID_PREDIO")
    out = pd.DataFrame({
        "COMUNA": g.COMUNA.first(),
        "QUE_NO_CUMPLE": d[d.BLOQUEA].groupby("ID_PREDIO").TXT.agg(unir),
        "ADVERTENCIAS": d[~d.BLOQUEA].groupby("ID_PREDIO").TXT.agg(unir),
        "ACCIONES": g.ACCION.agg(lambda s: "; ".join(dict.fromkeys(s.dropna()))),
    }).fillna("")
    out["ESTADO"] = np.where(out.QUE_NO_CUMPLE.ne(""), "NO CUMPLE", "CUMPLE CON ADVERTENCIAS")
    out = out.reset_index()
    out = out.merge(info[["NUMERO_PREDIAL_NACIONAL", "CONDICION"]], left_on="ID_PREDIO", right_index=True, how="left")
    return out[["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "CONDICION", "ESTADO", "QUE_NO_CUMPLE",
                "ADVERTENCIAS", "ACCIONES"]].sort_values(["COMUNA", "ESTADO", "ID_PREDIO"])


def _matriz_tablas(disponibles: set, anexos_ok: set, liquidar_parqueaderos: bool) -> pd.DataFrame:
    filas = []
    for fam in ["T1_RESIDENCIAL", "T2_EDIFICIOS", "T3_COMERCIAL", "T4_INDUSTRIAL"]:
        for grupo in ("7C", "10C"):
            if fam == "T1_RESIDENCIAL" and grupo == "10C":
                for cond in (0, 9):
                    filas.append((fam, f"10C condicion {cond}", tiene_tabla(fam, grupo, cond == 9, disponibles)))
            else:
                filas.append((fam, grupo, tiene_tabla(fam, grupo, False, disponibles)))
    for fam in sorted(TABLAS_17C):
        filas.append((fam, "17C", tiene_tabla(fam, "17C", False, disponibles)))
    for grupo in ("7C", "10C"):
        filas.append(("T10_ANEXOS", grupo, grupo in anexos_ok))
    filas.append(("T12_PARQUEADEROS", "todas", liquidar_parqueaderos))
    return pd.DataFrame(filas, columns=["TABLA", "GRUPO", "DISPONIBLE"]).assign(
        DISPONIBLE=lambda d: np.where(d.DISPONIBLE, "SI", "NO"))


def _escribir(r: Resultado, carpeta: str, run_id: str | None) -> str:
    os.makedirs(carpeta, exist_ok=True)
    r.detalle.to_parquet(os.path.join(carpeta, "detalle_prevalidacion.parquet"), index=False)
    ruta = os.path.join(carpeta, f"PREVALIDACION_COMUNAS_{run_id or datetime.now().strftime('%Y%m%d_%H%M')}.xlsx")
    hojas = [("COMUNAS", r.comunas), ("CRITERIOS", r.criterios), ("PREDIOS_NO_CUMPLEN", r.predios),
             ("TABLAS_CONSOLIDADO", r.tablas)]
    with pd.ExcelWriter(ruta, engine="xlsxwriter") as w:
        wb = w.book
        enc = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True,
                             "valign": "vcenter", "border": 1})
        rojo = wb.add_format({"bg_color": "#F8CBAD"})
        amarillo = wb.add_format({"bg_color": "#FFF2CC"})
        verde = wb.add_format({"bg_color": "#E2EFDA"})
        for nombre, df in hojas:
            df.to_excel(w, sheet_name=nombre, index=False, startrow=1, header=False)
            ws = w.sheets[nombre]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, enc)
                ancho = 80 if col in ("QUE_NO_CUMPLE", "ADVERTENCIAS", "ACCIONES", "ACCION") else (
                    55 if col in ("CRITERIO", "DETALLE") else 16)
                ws.set_column(j, j, ancho)
            ws.set_row(0, 30)
            ws.freeze_panes(1, 1)
            if len(df):
                ws.autofilter(0, 0, len(df), len(df.columns) - 1)
            for marca, fmt in (("NO APTA", rojo), ("NO CUMPLE", rojo), ("NO", rojo), ("APTA CON ADVERTENCIAS", amarillo),
                               ("ADVERTENCIA", amarillo), ("APTA", verde), ("SI", verde)):
                for j, col in enumerate(df.columns):
                    if col in ("ESTADO", "NIVEL", "DISPONIBLE") and len(df):
                        ws.conditional_format(1, j, len(df), j, {"type": "cell", "criteria": "==",
                                                                 "value": f'"{marca}"', "format": fmt})
    return ruta


def ejecutar_desde_config() -> Resultado:
    """Con el manifiesto ya cargado en config."""
    import config
    if config.get_param("version_tablas"):
        os.environ["VERSION_TABLAS"] = str(config.get_param("version_tablas")).upper()
    if config.get_insumo("tablas_valor"):
        os.environ["LIQUIDACION_TABLAS_VALOR"] = config.get_insumo("tablas_valor")
    from consolidar_tablas import tabla_valor_vigente

    insumos = {k: config.get_insumo(k) for k in ("export_predio_actual", "export_construccion_actual_conv",
                                                 "export_construccion_actual_noconv", "export_terreno_actual")}
    ruta_tablas = config.get_insumo("tablas_valor") or (str(tabla_valor_vigente()) if tabla_valor_vigente() else None)
    r = prevalidar(insumos, C.seleccionadas(), ruta_tablas,
                   liquidar_parqueaderos=bool(config.get_param("liquidar_parqueaderos", False)),
                   run_id=config.MANIFEST_DATA.get("run_id"))
    imprimir(r)
    return r


def imprimir(r: Resultado) -> None:
    for _, x in r.comunas.iterrows():
        print(f"   [{x.ESTADO}] comuna {x.COMUNA} ({x.GRUPO_TABLAS}): {x.PREDIOS:,} predios"
              + (f" | no cumple: {x.QUE_NO_CUMPLE}" if x.QUE_NO_CUMPLE else ""))
    print(f"   predios que no pasarian: {(r.predios.ESTADO == 'NO CUMPLE').sum():,}")
    print(f"[OK] Prevalidacion: {r.ruta}")
