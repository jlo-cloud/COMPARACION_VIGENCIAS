"""
Liquidacion 2027: el avaluo de CADA predio y su aprobacion contra el export de
Sistemas.

Avaluo catastral 2027 del predio = terreno + construcciones + anexos, cada
componente redondeado a miles:
  terreno        el proyectado (VTERR_COM_2027 x 0,7) donde el insumo lo trae;
                 si no, el VTER de la base
  construcciones suma de AREA_CONST x VM2 x 0,7; en parqueaderos (T12) el VM2
                 ya es el valor del cupo, asi que es VM2 x 0,7
  anexos         la tabla T10 todavia no tiene valores: va el VANEXO de la base
                 (igual que en la comparacion de vigencias)

Aprobacion: |avaluo liquidado - AVALPRED del export de Sistemas| < $1.000.
MOTIVO dice en que componente esta la diferencia y si el predio tiene
construcciones sin valor (modelo, especial, sin tabla).

Deja en la carpeta de salida:
  AVALUO_PREDIOS_VIG_2027.parquet / .txt (formato Sistemas)
  APROBACION_LIQUIDACION_2027.xlsx   RESUMEN, POR_MOTIVO, POR_COMUNA, NO_APROBADOS

Lo llama la ventana (preliquidar_app.py) en una corrida de tipo Liquidacion,
despues de main.py.
"""
from pathlib import Path

import numpy as np
import pandas as pd

TOLERANCIA = 1_000          # pesos
FACTOR = 0.7                # comercial -> catastral


def miles(s) -> pd.Series:
    return (pd.to_numeric(pd.Series(s), errors="coerce").fillna(0) / 1000).round(0) * 1000


def num(s) -> pd.Series:
    return pd.to_numeric(s, errors="coerce").fillna(0)


def universo(ruta_predio: str, comunas=None) -> pd.DataFrame:
    """Todos los predios de la vigencia (del archivo de predios con ZHF), en las
    comunas de la corrida: tambien los lotes, que no tienen construcciones."""
    u = pd.read_parquet(ruta_predio, columns=["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "VTER", "VANEXO", "AVALPRED"])         if str(ruta_predio).lower().endswith(".parquet") else         pd.read_csv(ruta_predio, sep="|", decimal=",", encoding="latin-1", dtype=str,
                    usecols=["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "VTER", "VANEXO", "AVALPRED"])
    u["ID_PREDIO"] = u["ID_PREDIO"].astype(str).str.strip()
    u = u.drop_duplicates("ID_PREDIO")
    u["COMUNA"] = u["NUMERO_PREDIAL_NACIONAL"].astype(str).str[9:11]
    if comunas:
        u = u[u["COMUNA"].isin(comunas)]
    for c in ("VTER", "VANEXO", "AVALPRED"):
        u[c] = pd.to_numeric(u[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return u


def avaluo_predios(ruta_liquidacion: str, terreno: pd.DataFrame, u: pd.DataFrame = None,
                   ids_base=None) -> pd.DataFrame:
    """Una fila por predio con el avaluo catastral 2027 y sus componentes. Con
    `u` (universo) entran tambien los lotes y los predios que la corrida
    descarto; `ids_base` son los predios que tenian construcciones en la base."""
    cols = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "CONSTRUCCION_ID", "TABLA_ORIGEN",
            "AREA_CONST", "VM2", "VTER", "VANEXO", "AVALPRED", "DESTINOCONS"]
    import pyarrow.parquet as pq
    hay = set(pq.ParquetFile(ruta_liquidacion).schema_arrow.names)
    d = pd.read_parquet(ruta_liquidacion, columns=[c for c in cols if c in hay])
    d["ID_PREDIO"] = d["ID_PREDIO"].astype(str).str.strip()
    tabla = d["TABLA_ORIGEN"].astype(str)
    anexo = tabla.eq("T10_ANEXOS")
    parq = tabla.str.startswith("T12")
    vm2 = num(d["VM2"])
    d["VALORCONS_CAT_LIQ"] = np.where(anexo, 0.0,
                                      np.where(parq, vm2, num(d["AREA_CONST"]) * vm2) * FACTOR)
    sin_valor = ~anexo & (vm2 <= 0)
    d["SIN_VALOR_MODELO"] = sin_valor & tabla.eq("MODELO")
    d["SIN_VALOR_ESPECIAL"] = sin_valor & tabla.isin(["ESPECIALES", "ESPECIAL"])
    d["SIN_VALOR_SIN_TABLA"] = sin_valor & tabla.eq("SIN TABLA")
    d["SIN_VALOR_TABLA"] = sin_valor & ~(d["SIN_VALOR_MODELO"] | d["SIN_VALOR_ESPECIAL"] | d["SIN_VALOR_SIN_TABLA"])

    g = d.groupby("ID_PREDIO", sort=False)
    p = pd.concat([
        g[["NUMERO_PREDIAL_NACIONAL", "COMUNA", "VTER", "VANEXO", "AVALPRED"]].first(),
        g["VALORCONS_CAT_LIQ"].sum(),
        g[["SIN_VALOR_MODELO", "SIN_VALOR_ESPECIAL", "SIN_VALOR_SIN_TABLA", "SIN_VALOR_TABLA"]].sum().astype(int),
        g.size().rename("N_CONSTRUCCIONES"),
    ], axis=1).reset_index()
    p["CASO"] = "CON CONSTRUCCIONES"
    if u is not None:
        # Los que no salieron de la liquidacion por construccion: lotes (solo
        # terreno) o predios que la corrida descarto por inconsistencias.
        resto = u[~u["ID_PREDIO"].isin(p["ID_PREDIO"])].copy()
        tenia = resto["ID_PREDIO"].isin(set(ids_base or []))
        resto["CASO"] = np.where(tenia, "EXCLUIDO POR INCONSISTENCIAS", "SOLO TERRENO")
        resto["VALORCONS_CAT_LIQ"] = 0.0
        resto["N_CONSTRUCCIONES"] = 0
        for c in ("SIN_VALOR_MODELO", "SIN_VALOR_ESPECIAL", "SIN_VALOR_SIN_TABLA", "SIN_VALOR_TABLA"):
            resto[c] = 0
        p = pd.concat([p, resto[p.columns]], ignore_index=True)
        p = p[p["ID_PREDIO"].isin(u["ID_PREDIO"])]

    # Terreno: el proyectado donde el insumo lo trae; si no, el de la base.
    proy = p["ID_PREDIO"].map(terreno["VTERR_COM_2027"]) if not terreno.empty else pd.Series(np.nan, index=p.index)
    p["ORIGEN_TERRENO"] = np.where(proy.notna(), "PROYECTADO", "BASE")
    p["TERRENO_LIQ"] = miles(np.where(proy.notna(), proy * FACTOR, num(p["VTER"])))
    p["CONSTRUCCIONES_LIQ"] = miles(p["VALORCONS_CAT_LIQ"])
    p["ANEXOS_LIQ"] = miles(p["VANEXO"])
    p["AVALUO_LIQ"] = p["TERRENO_LIQ"] + p["CONSTRUCCIONES_LIQ"] + p["ANEXOS_LIQ"]
    # El excluido no se liquido: no tiene avaluo, no se puede aprobar.
    p.loc[p["CASO"].eq("EXCLUIDO POR INCONSISTENCIAS"),
          ["TERRENO_LIQ", "CONSTRUCCIONES_LIQ", "ANEXOS_LIQ", "AVALUO_LIQ"]] = np.nan
    return p.drop(columns=["VALORCONS_CAT_LIQ", "VTER", "VANEXO"]).rename(
        columns={"AVALPRED": "AVALPRED_BASE"})


def leer_export(ruta: str) -> pd.DataFrame:
    """El export de predios de la liquidacion 2027 de Sistemas."""
    ruta = str(ruta)
    pedidas = ["ID_PREDIO", "AVALPRED", "VTER", "VCONST", "VANEXO"]
    if ruta.lower().endswith(".parquet"):
        e = pd.read_parquet(ruta)
    else:
        e = pd.read_csv(ruta, sep="|", decimal=",", encoding="latin-1", low_memory=False, dtype=str)
    e.columns = [c.strip().strip('"').upper() for c in e.columns]
    faltan = [c for c in pedidas if c not in e.columns]
    if "ID_PREDIO" in faltan or "AVALPRED" in faltan:
        raise ValueError(f"El export de liquidacion no trae {faltan}")
    e = e[[c for c in pedidas if c in e.columns]].copy()
    e["ID_PREDIO"] = e["ID_PREDIO"].astype(str).str.strip()
    for c in e.columns[1:]:
        # Los export de Sistemas vienen con coma decimal.
        e[c] = pd.to_numeric(e[c].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    return e.drop_duplicates("ID_PREDIO").rename(columns={c: f"{c}_SISTEMAS" for c in e.columns[1:]})


def aprobar(p: pd.DataFrame, e: pd.DataFrame) -> pd.DataFrame:
    # Solo los predios de la corrida (sus comunas): el resto del export no se juzga.
    e = e[e["ID_PREDIO"].isin(p["ID_PREDIO"])]
    t = p.merge(e, on="ID_PREDIO", how="left", indicator=True)
    t.loc[t["AVALUO_LIQ"].isna(), "_merge"] = "right_only"
    t["DIFERENCIA"] = (num(t["AVALUO_LIQ"]) - num(t["AVALPRED_SISTEMAS"])).where(t["_merge"].eq("both"))
    t["ESTADO"] = np.select(
        [t["_merge"].eq("left_only"), t["_merge"].eq("right_only"), t["DIFERENCIA"].abs() < TOLERANCIA],
        ["NO APROBADO", "NO APROBADO", "APROBADO"], default="NO APROBADO")

    motivos = []
    for comp, sis in (("TERRENO", "VTER"), ("CONSTRUCCIONES", "VCONST"), ("ANEXOS", "VANEXO")):
        if f"{sis}_SISTEMAS" in t.columns:
            t[f"DIF_{comp}"] = (num(t[f"{comp}_LIQ"]) - num(t[f"{sis}_SISTEMAS"])).where(t["_merge"].eq("both"))
            motivos.append((t[f"DIF_{comp}"].abs() >= TOLERANCIA, f"difiere {comp.lower()}"))
    motivos += [(t["SIN_VALOR_MODELO"].fillna(0) > 0, "construcciones por modelo en $0"),
                (t["SIN_VALOR_ESPECIAL"].fillna(0) > 0, "especiales en $0"),
                (t["SIN_VALOR_SIN_TABLA"].fillna(0) > 0, "construcciones sin tabla"),
                (t["SIN_VALOR_TABLA"].fillna(0) > 0, "construcciones con tabla sin valor")]

    # Los motivos se pegan en bloque (no fila por fila: son cientos de miles).
    m = pd.Series("", index=t.index)
    for mask, texto in motivos:
        m = m.where(~mask, m + np.where(m.eq(""), "", "; ") + texto)
    m = m.where(m.ne(""), "diferencia sin componente identificado")
    t["MOTIVO"] = np.select(
        [t["_merge"].eq("left_only"), t["_merge"].eq("right_only"), t["ESTADO"].eq("APROBADO")],
        ["no esta en el export de Sistemas", "no se liquido: excluido por inconsistencias (pre-inconsistencias)", ""],
        default=m)
    t["COMUNA"] = t["COMUNA"].fillna("")
    return t.drop(columns="_merge")


def correr(ruta_liquidacion, ruta_export, terreno: pd.DataFrame, carpeta_salida,
           ruta_predio=None, comunas=None, ruta_base=None) -> pd.DataFrame:
    carpeta_salida = Path(carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    print("\n" + "=" * 66)
    print("=== LIQUIDACION 2027: avaluo por predio y aprobacion contra Sistemas ===")
    print("=" * 66)
    u = universo(ruta_predio, comunas) if ruta_predio else None
    ids_base = (set(pd.read_parquet(ruta_base, columns=["ID_PREDIO"])["ID_PREDIO"].astype(str).str.strip())
                if ruta_base and Path(ruta_base).exists() else set())
    p = avaluo_predios(ruta_liquidacion, terreno, u, ids_base)
    print(f"Avaluo liquidado: {len(p):,} predios")
    e = leer_export(ruta_export)
    print(f"Export de Sistemas: {len(e):,} predios ({Path(ruta_export).name})")
    t = aprobar(p, e)

    orden = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "CASO", "ESTADO", "MOTIVO",
             "AVALUO_LIQ", "AVALPRED_SISTEMAS", "DIFERENCIA",
             "TERRENO_LIQ", "VTER_SISTEMAS", "DIF_TERRENO",
             "CONSTRUCCIONES_LIQ", "VCONST_SISTEMAS", "DIF_CONSTRUCCIONES",
             "ANEXOS_LIQ", "VANEXO_SISTEMAS", "DIF_ANEXOS",
             "ORIGEN_TERRENO", "N_CONSTRUCCIONES", "SIN_VALOR_MODELO", "SIN_VALOR_ESPECIAL",
             "SIN_VALOR_SIN_TABLA", "SIN_VALOR_TABLA", "AVALPRED_BASE"]
    t = t[[c for c in orden if c in t.columns]]
    t.to_parquet(carpeta_salida / "AVALUO_PREDIOS_VIG_2027.parquet", index=False)

    # El avaluo por predio en el formato de los export de Sistemas.
    txt = t[t["AVALUO_LIQ"].notna()][["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "TERRENO_LIQ",
                                      "CONSTRUCCIONES_LIQ", "ANEXOS_LIQ", "AVALUO_LIQ"]].copy()
    txt.columns = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA", "VTER", "VCONST", "VANEXO", "AVALPRED"]
    for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "COMUNA"):
        txt[c] = txt[c].astype("string")
    txt.to_csv(carpeta_salida / "AVALUO_PREDIOS_VIG_2027.txt", sep="|", decimal=",", index=False,
               encoding="latin-1", errors="replace")

    est = t["ESTADO"].value_counts()
    resumen = pd.DataFrame({
        "DATO": ["Predios liquidados", "Predios en el export de Sistemas", "APROBADOS", "NO APROBADOS",
                 "Tolerancia (pesos)", "Export de Sistemas"],
        "VALOR": [int(t["AVALUO_LIQ"].notna().sum()), int(t["AVALPRED_SISTEMAS"].notna().sum()),
                  int(est.get("APROBADO", 0)), int(est.get("NO APROBADO", 0)), TOLERANCIA, Path(ruta_export).name]})
    no = t[t["ESTADO"] == "NO APROBADO"]
    por_motivo = no["MOTIVO"].value_counts().rename_axis("MOTIVO").reset_index(name="PREDIOS")
    por_comuna = (t.groupby(["COMUNA", "ESTADO"]).size().unstack(fill_value=0).reset_index())
    por_caso = (t.groupby(["CASO", "ESTADO"]).size().unstack(fill_value=0).reset_index())
    ruta_x = carpeta_salida / "APROBACION_LIQUIDACION_2027.xlsx"
    with pd.ExcelWriter(ruta_x, engine="xlsxwriter") as xw:
        resumen.to_excel(xw, sheet_name="RESUMEN", index=False)
        por_motivo.to_excel(xw, sheet_name="POR_MOTIVO", index=False)
        por_comuna.to_excel(xw, sheet_name="POR_COMUNA", index=False)
        por_caso.to_excel(xw, sheet_name="POR_CASO", index=False)
        no.to_excel(xw, sheet_name="NO_APROBADOS", index=False)
    print(f"APROBADOS: {int(est.get('APROBADO', 0)):,} | NO APROBADOS: {int(est.get('NO APROBADO', 0)):,}")
    print(f"Escrito: {ruta_x}")
    print(f"Escrito: {carpeta_salida / 'AVALUO_PREDIOS_VIG_2027.txt'} (formato Sistemas)")
    return t
