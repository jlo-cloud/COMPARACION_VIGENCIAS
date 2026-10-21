"""
Predios por corregir: UN Excel con una fila por predio que no cumple una
condicion o al que le falta un dato para liquidar.

Junta lo que encuentran los controles del proceso:
  - prevalidacion (paso 0B): lo que la comuna o el predio no tiene para
    liquidarse (regla, tabla con valores, modelo, ZHF, puntaje, terreno...).
  - pre_inconsistencias (paso 2): lo que le falta al dato de entrada. Algunos
    motivos sacan el predio de la liquidacion.
  - post_inconsistencias (paso 5): construcciones que quedaron en $0 aunque
    traian sus datos (tabla que falta, comuna sin regla, modelo sin valor).
    Para las de MODELO revisa que variable del modelo esta vacia.
  - validacion de la preliquidacion (paso 5): el predio, ya liquidado, no
    cumple un criterio (avaluo en $0, construcciones en $0, sin terreno...).

La columna QUE_NO_CUMPLE dice lo que hay que revisar en cada predio y
PASA_PRELIQUIDACION si el predio puede salir en la preliquidacion.

Hojas: PREDIOS (una fila por predio), DETALLE (una fila por predio,
construccion y motivo), RESUMEN, CATALOGO (que significa cada inconsistencia y
que hacer).
"""

from __future__ import annotations

import os
from datetime import datetime

import numpy as np
import pandas as pd

# motivo del control -> (inconsistencia, dato que falta, accion)
CATALOGO_PRE = {
    "Sin ZHF en comercial o industrial: no hay con que suplirla": (
        "Sin ZHF en construccion comercial / industrial", "ZHF",
        "Pedir a Sistemas la ZHF del predio; sin ella no hay tabla comercial/industrial."),
    "Sin ZHF o ZHF inválido": (
        "Sin ZHF valida", "ZHF", "Corregir la ZHF. Se liquida por estrato mientras tanto."),
    "Sin LONGITUDE": ("Sin longitud", "LONGITUDE", "Pedir coordenadas (las usan los modelos de PH)."),
    "Sin LATITUDE": ("Sin latitud", "LATITUDE", "Pedir coordenadas (las usan los modelos de PH)."),
    "Sin USO_LADM": ("Destino sin homologar a uso LADM", "DESTINOCONS",
                     "Revisar el codigo de destino: no tiene equivalencia LADM."),
    "USO _PH sin CONDICION 8 o 9": ("Uso de PH en predio que no es PH", "CONDICION",
                                    "Corregir el destino o la condicion juridica del predio."),
    "USO sin _PH con CONDICION 9": ("Predio PH con uso que no es de PH", "CONDICION / DESTINOCONS",
                                    "Corregir el destino o la condicion: cambia la tabla de valor."),
    "USO sin _PH con CONDICION 9 (7 comunas, no afecta el valor)": (
        "Predio PH con uso que no es de PH (sin efecto en el valor)", "CONDICION / DESTINOCONS",
        "Corregir cuando se pueda; en las 7 comunas no cambia el valor."),
    "Sin puntaje condicionado": ("Sin puntaje / calificacion", "PUNTCONS",
                                 "Pedir la calificacion de la construccion (o TIPOANEXO del anexo)."),
    "Sin área construida": ("Sin area construida", "ACONCONS", "Pedir el area construida."),
}
CATALOGO_POST = {
    "FALTA REGLA - la tabla no esta en el consolidado": (
        "Tabla de valor faltante en el consolidado", "Tabla de valor",
        "Entregar la tabla en Tablas_Valor_Consolidado (hoy faltan T7, T8 y anexos T10)."),
    "FALTA REGLA - comuna fuera de las programadas": (
        "Comuna / zona sin regla programada", "Regla de liquidacion",
        "Programar la regla para la comuna o zona (rural, corregimientos)."),
    "FALTA REGLA - el PUNTCONS existe pero la tabla solo llega a 100": (
        "Puntaje fuera del rango de la tabla", "PUNTCONS", "Revisar el puntaje (mayor a 100)."),
    "FALTA REGLA - la regla no cubre esta combinacion": (
        "Combinacion sin regla", "Regla de liquidacion", "Revisar la regla de asignacion de tabla para este caso."),
    "SIN TABLA - no se le pudo asignar tabla": ("Sin tabla asignada", "Regla de asignacion de tabla",
                                                "Revisar uso, tipologia y comuna de la construccion."),
    "ESPECIALES - se liquidan por otra via": ("Especial sin valor asignado", "Valor especial",
                                              "Cargar el valor especial (el Excel de especiales esta apagado)."),
}
MOTIVOS_DESCUENTAN_PRE = {
    "Sin ZHF en comercial o industrial: no hay con que suplirla", "Sin USO_LADM", "USO _PH sin CONDICION 8 o 9",
    "USO sin _PH con CONDICION 9", "Sin puntaje condicionado", "Sin área construida",
}

# variables que pide cada modelo: (familia, destino) -> columnas
VARIABLES_MODELO = {
    ("2025", 1): ["VALOR_M2_SUELO", "ANOCONST", "ESTRPRED", "PUNTCONS", "TPISCONS", "LATITUDE", "LONGITUDE", "ZHF_MODELO"],
    ("2025", 28): ["VALOR_M2_SUELO", "LATITUDE", "LONGITUDE", "ZHF_MODELO", "NUM_CONST_TERR", "ACONCONS"],
    ("2025", 34): ["VALOR_M2_SUELO", "LATITUDE", "LONGITUDE", "ACONCONS", "ZHF_MODELO"],
    ("2024", 1): ["LATITUDE", "LONGITUDE", "ESTRPRED", "ARECPRED", "TPISCONS", "PUNTCONS", "ANOCONST", "ZHF_MODELO"],
    ("2024", 28): ["VALOR_M2_SUELO", "LATITUDE", "LONGITUDE", "NUM_CONST_TERR", "ARECPRED", "TPISCONS", "PUNTCONS", "ANOCONST"],
    ("2024", 34): ["VALOR_M2_SUELO", "LATITUDE", "LONGITUDE", "NUM_CONST_TERR", "ARECPRED", "PUNTCONS", "TPISCONS", "ZHF_MODELO"],
}
NOMBRE_DATO = {"ZHF_MODELO": "ZHF", "VALOR_M2_SUELO": "VALOR_M2_SUELO (ZHG)"}


def _vacio(s: pd.Series) -> pd.Series:
    t = s.astype(str).str.strip().str.lower()
    num = pd.to_numeric(t, errors="coerce")
    return t.isin(["", "nan", "none", "<na>"]) | (num.notna() & (num == 0))


def _causas_modelo(d: pd.DataFrame) -> pd.DataFrame:
    """Para las construcciones de MODELO en $0: que variable falta, o si no hay familia."""
    d = d.copy()
    destino = pd.to_numeric(d.get("DESTINOCONS", pd.Series(np.nan, index=d.index)), errors="coerce")
    fam = d.get("GRUPO_MODELO", pd.Series("", index=d.index)).astype(str).str.strip()
    fam = fam.where(~fam.str.lower().isin(["", "nan", "none", "<na>"]), "")
    faltan = pd.Series("", index=d.index)
    for (f, dest), cols in VARIABLES_MODELO.items():
        m = fam.eq(f) & destino.eq(dest)
        if not m.any():
            continue
        partes = []
        for c in cols:
            if c in d.columns:
                partes.append(np.where(_vacio(d.loc[m, c]), NOMBRE_DATO.get(c, c), ""))
        if partes:
            unidos = pd.DataFrame(partes).T.apply(lambda r: "; ".join(x for x in r if x), axis=1)
            faltan.loc[m] = unidos.values
    inc = np.where(fam.eq(""), "Sin familia de modelo (comuna no actualizada en 2024/2025)",
                   np.where(faltan.ne(""), "Modelo sin valor: faltan variables", "Modelo sin valor: revisar prediccion"))
    dato = np.where(fam.eq(""), "Familia de modelo", faltan.where(faltan.ne(""), "Ninguno identificado"))
    accion = np.where(fam.eq(""), "Definir modelo o tabla para esta comuna / zona.",
                      np.where(faltan.ne(""), "Completar las variables que pide el modelo.",
                               "Revisar la prediccion del modelo para esta construccion."))
    d["INCONSISTENCIA"], d["DATO_FALTANTE"], d["ACCION"] = inc, dato, accion
    return d


def _detalle_pre(path: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        return pd.DataFrame()
    p = pd.read_parquet(path)
    cat = p.MOTIVO.map(lambda m: CATALOGO_PRE.get(m, (m, "", "")))
    p["INCONSISTENCIA"] = [c[0] for c in cat]
    p["DATO_FALTANTE"] = [c[1] for c in cat]
    p.loc[p.CAMPO.eq("TIPOANEXO") & p.MOTIVO.eq("Sin puntaje condicionado"), "DATO_FALTANTE"] = "TIPOANEXO"
    p["ACCION"] = [c[2] for c in cat]
    p["IMPIDE_LIQUIDAR"] = p.MOTIVO.isin(MOTIVOS_DESCUENTAN_PRE)
    p["ETAPA"] = "PRE (paso 2: dato de entrada)"
    return p


def _detalle_post(path: str) -> pd.DataFrame:
    if not os.path.isfile(path):
        return pd.DataFrame()
    q = pd.read_parquet(path)
    es_modelo = q.CAUSA.eq("MODELO - sin valor del modelo")
    partes = []
    if (~es_modelo).any():
        o = q[~es_modelo].copy()
        cat = o.CAUSA.map(lambda c: CATALOGO_POST.get(c, (c, "", "")))
        o["INCONSISTENCIA"] = [c[0] for c in cat]
        o["DATO_FALTANTE"] = [c[1] for c in cat]
        o["ACCION"] = [c[2] for c in cat]
        tabla = o.get("TABLA_ORIGEN", pd.Series("", index=o.index)).astype(str)
        falta_tabla = o.CAUSA.eq("FALTA REGLA - la tabla no esta en el consolidado")
        o.loc[falta_tabla, "DATO_FALTANTE"] = "Tabla " + tabla[falta_tabla]
        partes.append(o)
    if es_modelo.any():
        partes.append(_causas_modelo(q[es_modelo]))
    p = pd.concat(partes, ignore_index=True)
    p["CAMPO"] = p["DATO_FALTANTE"]
    p["VALOR_ACTUAL"] = "$0 liquidado"
    p["IMPIDE_LIQUIDAR"] = False      # el predio se liquida, pero esa construccion queda en $0
    p["ETAPA"] = "POST (paso 5: quedo en $0)"
    return p


def _detalle_validacion(path: str, etapa: str) -> pd.DataFrame:
    """Prevalidacion (paso 0B) o validacion final (paso 5): un registro por predio y criterio."""
    if not os.path.isfile(path):
        return pd.DataFrame()
    v = pd.read_parquet(path)
    if v.empty:
        return pd.DataFrame()
    detalle = v.DETALLE.astype(str)
    # "Tabla sin valores en el consolidado: T7_INSTITUCIONAL_SER 10C"; si el
    # detalle ya trae el criterio ("Construcciones en $0 (2 de 3)") va tal cual.
    v["INCONSISTENCIA"] = [d if d.startswith(c) else f"{c}: {d}" for c, d in zip(v.CRITERIO.astype(str), detalle)]
    v["DATO_FALTANTE"] = detalle
    v["CAMPO"] = v.DETALLE.astype(str)
    v["VALOR_ACTUAL"] = ""
    v["IMPIDE_LIQUIDAR"] = False
    v["NO_PASA"] = v.BLOQUEA.astype(bool)
    v["ETAPA"] = etapa
    return v


def generar(output_path: str = "./output", base: str | None = None) -> str | None:
    """Escribe output/predios_por_corregir/PREDIOS_POR_CORREGIR_<fecha>.xlsx y devuelve la ruta."""
    pre = _detalle_pre(os.path.join(output_path, "Pre_inconsistencias", "detalle_pre_inconsistencias.parquet"))
    post = _detalle_post(os.path.join(output_path, "post_inconsistencias", "detalle_post_inconsistencias.parquet"))
    prev = _detalle_validacion(os.path.join(output_path, "Prevalidacion", "detalle_prevalidacion.parquet"),
                               "PREVALIDACION (paso 0B: antes de liquidar)")
    final = _detalle_validacion(os.path.join(output_path, "preliquidacion", "validacion_predios.parquet"),
                                "VALIDACION (paso 5: predio liquidado)")
    partes = [x for x in (prev, pre, post, final) if not x.empty]
    if not partes:
        print("   (no hay detalle de inconsistencias para consolidar)")
        return None
    det = pd.concat(partes, ignore_index=True)
    det["ID_PREDIO"] = det.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
    det["IMPIDE_LIQUIDAR"] = det.IMPIDE_LIQUIDAR.fillna(False).astype(bool)
    # No pasa la preliquidacion: lo que impide liquidar, lo que queda en $0 y
    # lo que la prevalidacion o la validacion final marcan como bloqueante.
    no_pasa = det.get("NO_PASA", pd.Series(False, index=det.index)).fillna(False).astype(bool)
    det["NO_PASA"] = det.IMPIDE_LIQUIDAR | det.ETAPA.str.startswith("POST") | no_pasa

    # informacion del predio
    base = base or os.path.join(output_path, "todas_las_construcciones.parquet")
    info = None
    if os.path.isfile(base):
        import pyarrow.parquet as pq
        cols = [c for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "DIREPRED", "CONDICION", "ESTRPRED")
                if c in pq.read_schema(base).names]
        info = pd.read_parquet(base, columns=cols)
        info["ID_PREDIO"] = info.ID_PREDIO.astype(str).str.replace(r"\.0$", "", regex=True)
        info = info.drop_duplicates("ID_PREDIO").set_index("ID_PREDIO")

    def unir(s):
        vals = [x for x in dict.fromkeys(s.astype(str)) if x and x != "nan"]
        return "; ".join(vals)

    g = det.groupby("ID_PREDIO")
    bloquea, avisa = det[det.NO_PASA].groupby("ID_PREDIO"), det[~det.NO_PASA].groupby("ID_PREDIO")
    predios = pd.DataFrame({
        "N_INCONSISTENCIAS": bloquea.INCONSISTENCIA.nunique(),
        "INCONSISTENCIAS": bloquea.INCONSISTENCIA.agg(unir),
        "OBSERVACIONES": avisa.INCONSISTENCIA.agg(unir),
        "DATOS_FALTANTES_PARA_LIQUIDAR": g.DATO_FALTANTE.agg(
            lambda s: "; ".join(dict.fromkeys(x.strip() for v in s.astype(str) for x in v.split(";") if x.strip() and x.strip() != "nan"))),
        "ACCIONES": g.ACCION.agg(unir),
        "CONSTRUCCIONES_AFECTADAS": g.apply(lambda x: x[[c for c in ("LLAVE_CONST", "ID_CONSTRUCCION") if c in x.columns][0]].nunique()
                                            if any(c in x.columns for c in ("LLAVE_CONST", "ID_CONSTRUCCION")) else len(x)),
        "ETAPAS": g.ETAPA.agg(unir),
        "_IMPIDE": g.IMPIDE_LIQUIDAR.any(),
        "_POST": g.ETAPA.agg(lambda s: s.str.startswith("POST").any()),
        "_NO_PASA": g.NO_PASA.any(),
    })
    predios[["N_INCONSISTENCIAS", "INCONSISTENCIAS", "OBSERVACIONES"]] = predios[
        ["N_INCONSISTENCIAS", "INCONSISTENCIAS", "OBSERVACIONES"]].fillna({"N_INCONSISTENCIAS": 0,
                                                                         "INCONSISTENCIAS": "", "OBSERVACIONES": ""})
    predios["ESTADO_LIQUIDACION"] = np.select(
        [predios._IMPIDE, predios._POST, predios._NO_PASA],
        ["NO SE LIQUIDA (descontado por falta de datos)", "LIQUIDADO PARCIAL (construcciones en $0)",
         "NO PASA LA PRELIQUIDACION"], default="SE LIQUIDA (solo aviso)")
    predios["PASA_PRELIQUIDACION"] = np.where(predios._NO_PASA, "NO", "SI")
    predios = predios.drop(columns=["_IMPIDE", "_POST", "_NO_PASA"]).reset_index()
    predios = predios.rename(columns={"INCONSISTENCIAS": "QUE_NO_CUMPLE", "N_INCONSISTENCIAS": "N_QUE_NO_CUMPLE"})
    if info is not None:
        predios = predios.merge(info, left_on="ID_PREDIO", right_index=True, how="left")
    predios["ZONA"] = np.where(predios.get("NUMERO_PREDIAL_NACIONAL", pd.Series("", index=predios.index))
                               .astype(str).str[5:7].eq("01"), "URBANO", "RURAL / CORREGIMIENTO")
    orden = [c for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "ZONA", "COMUNA", "DIREPRED", "CONDICION",
                         "PASA_PRELIQUIDACION", "ESTADO_LIQUIDACION", "N_QUE_NO_CUMPLE", "QUE_NO_CUMPLE",
                         "OBSERVACIONES",
                         "DATOS_FALTANTES_PARA_LIQUIDAR",
                         "ACCIONES", "CONSTRUCCIONES_AFECTADAS", "ETAPAS") if c in predios.columns]
    predios = predios[orden].sort_values(["PASA_PRELIQUIDACION", "N_QUE_NO_CUMPLE"], ascending=[True, False])

    resumen = (det.groupby(["ETAPA", "INCONSISTENCIA", "DATO_FALTANTE"])
                  .agg(PREDIOS=("ID_PREDIO", "nunique"), REGISTROS=("ID_PREDIO", "size"),
                       IMPIDE_LIQUIDAR=("IMPIDE_LIQUIDAR", "any"), NO_PASA_PRELIQUIDACION=("NO_PASA", "any"))
                  .reset_index().sort_values("PREDIOS", ascending=False))
    estados = predios.ESTADO_LIQUIDACION.value_counts().rename_axis("ESTADO_LIQUIDACION").reset_index(name="PREDIOS")
    catalogo = pd.DataFrame(
        [("PRE", k, *v, "SI" if k in MOTIVOS_DESCUENTAN_PRE else "NO") for k, v in CATALOGO_PRE.items()]
        + [("POST", k, *v, "NO (queda en $0)") for k, v in CATALOGO_POST.items()]
        + [("POST", "MODELO - sin valor del modelo", "Modelo sin valor: faltan variables",
            "Las variables vacias del modelo de su familia y destino", "Completar las variables.", "NO (queda en $0)"),
           ("POST", "MODELO - sin valor del modelo", "Sin familia de modelo (comuna no actualizada en 2024/2025)",
            "Familia de modelo", "Definir modelo o tabla para la comuna / zona.", "NO (queda en $0)")],
        columns=["ETAPA", "MOTIVO_DEL_CONTROL", "INCONSISTENCIA", "DATO_QUE_FALTA", "ACCION", "IMPIDE_LIQUIDAR"])

    cols_det = [c for c in ("ID_PREDIO", "LLAVE_CONST", "ID_CONSTRUCCION", "ETAPA", "INCONSISTENCIA", "DATO_FALTANTE",
                            "CAMPO", "VALOR_ACTUAL", "TABLA_ORIGEN", "IMPIDE_LIQUIDAR", "NO_PASA", "ACCION")
                if c in det.columns]
    detalle = det[cols_det].sort_values(["ID_PREDIO", "ETAPA"])

    carpeta = os.path.join(output_path, "predios_por_corregir")
    os.makedirs(carpeta, exist_ok=True)
    archivo = os.path.join(carpeta, f"PREDIOS_POR_CORREGIR_{datetime.now():%Y%m%d}.xlsx")
    with pd.ExcelWriter(archivo, engine="xlsxwriter") as w:
        wb = w.book
        enc = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "text_wrap": True,
                             "valign": "vcenter", "border": 1})
        txt = wb.add_format({"text_wrap": False, "valign": "top"})
        hojas = [("PREDIOS", predios, {"QUE_NO_CUMPLE": 80, "OBSERVACIONES": 50, "DATOS_FALTANTES_PARA_LIQUIDAR": 45, "ACCIONES": 70,
                                       "ESTADO_LIQUIDACION": 40, "DIREPRED": 34, "NUMERO_PREDIAL_NACIONAL": 32}),
                 ("RESUMEN", resumen, {"INCONSISTENCIA": 55, "DATO_FALTANTE": 40, "ETAPA": 30}),
                 ("ESTADOS", estados, {"ESTADO_LIQUIDACION": 50}),
                 ("DETALLE", detalle, {"INCONSISTENCIA": 55, "DATO_FALTANTE": 40, "ACCION": 60, "ETAPA": 30}),
                 ("CATALOGO", catalogo, {"MOTIVO_DEL_CONTROL": 55, "INCONSISTENCIA": 55, "DATO_QUE_FALTA": 40, "ACCION": 70})]
        for nombre, df, anchos in hojas:
            df.to_excel(w, sheet_name=nombre, index=False, startrow=1, header=False)
            ws = w.sheets[nombre]
            for j, col in enumerate(df.columns):
                ws.write(0, j, col, enc)
                ws.set_column(j, j, anchos.get(col, 16), txt)
            ws.set_row(0, 32)
            ws.freeze_panes(1, 1)
            ws.autofilter(0, 0, max(len(df), 1), len(df.columns) - 1)
    print(f"\n[OK] Predios por corregir: {len(predios):,} -> {archivo}")
    print(estados.to_string(index=False))
    return archivo
