"""
Liquida la base de HOY con las reglas de las vigencias marcadas en la ventana:
2025 (reglas del ejercicio 2024), 2026 (ejercicio 2025) y 2027 (la propuesta
actual). No usa exports historicos: todas salen de los mismos insumos.

Usa los motores de escenarios.py. Como alli, cada ejercicio valora solo las
comunas que actualizo; las demas quedan en cero con el motivo en METODO.

Deja en la carpeta de salida:
  LIQUIDACION_VIGENCIAS.parquet   una fila por construccion; por cada vigencia
                                  VM2_COM_VIG_<v>, VM2_CAT_VIG_<v>, TABLA_VIG_<v>,
                                  FAMILIA_VIG_<v>, METODO_VIG_<v>, UNIDAD_VIG_<v>
  RESUMEN_VIGENCIAS.xlsx          por metodo, familia y comuna de cada vigencia
  LIQUIDACION_VIGENCIAS.xlsx      el detalle, solo si se pide (tarda minutos)
  LIQUIDACION_VIGENCIAS.txt       en una LIQUIDACION: el mismo detalle con el
                                  formato de los export de Sistemas

Lo llama la ventana (preliquidar_app.py) despues de main.py, si 2027 esta
marcada, o despues de armar solo la base, si no.
"""
from pathlib import Path

import pandas as pd

# La vigencia que rige -> el motor (ejercicio) de escenarios.py.
MOTOR = {2025: "2024", 2026: "2025", 2027: "ACTUAL"}
CAMPOS = ("VM2", "TABLA", "FAMILIA", "METODO", "UNIDAD")


def armar_base():
    """Pasos 1 y 2 del main: la base cruzada, sin liquidar (cuando no va 2027)."""
    from tabla_construccion import procesar_construcciones, cruces_const_predio
    print("\n=== PASO 1: base de construcciones y predios ===")
    df_predio, df_conv, df_noconv = procesar_construcciones()
    if df_predio is None or df_conv is None or df_noconv is None:
        raise ValueError("No se pudieron cargar los insumos de predios y construcciones.")
    print("\n=== PASO 2: cruces, homologacion y uso principal ===")
    cruces_const_predio(df_predio, df_conv, df_noconv)


def escribir_txt(t: pd.DataFrame, ruta) -> None:
    """El formato de los export de Sistemas: separado por |, coma decimal,
    latin-1, y los codigos como texto -si no, una ZHF sale '82104421013,0'-."""
    d = t.copy()
    for c in d.columns:
        if c.startswith(("VM2_COM_", "VM2_CAT_")):
            d[c] = pd.to_numeric(d[c], errors="coerce").round(2)
        elif not pd.api.types.is_float_dtype(d[c]):
            d[c] = d[c].astype("string")
    d.to_csv(ruta, sep="|", decimal=",", index=False, encoding="latin-1", errors="replace")
    print(f"Escrito: {ruta} (formato Sistemas: |, coma decimal, latin-1)")


def correr(vigencias, carpeta_salida, detalle_excel=False, txt_sistemas=False) -> pd.DataFrame:
    import escenarios

    vigencias = sorted(int(v) for v in vigencias)
    carpeta_salida = Path(carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)
    base = pd.read_parquet(escenarios.RUTA_BASE)
    llave = escenarios.LLAVE
    cols = [c for c in escenarios.COLUMNAS_PREDIO if c in base.columns]
    t = base[cols].copy()
    t[llave] = t[llave].astype(str)
    t = t.drop_duplicates(llave)

    for v in vigencias:
        nombre = MOTOR[v]
        print("\n" + "=" * 66)
        print(f"=== VIGENCIA {v}: reglas {'actuales' if v == 2027 else 'del ejercicio ' + nombre} ===")
        print("=" * 66)
        r = escenarios.MOTORES[nombre](base).drop_duplicates(llave)
        r = r.rename(columns={f"{c}_{nombre}": f"{c}_VIG_{v}" for c in CAMPOS})
        t = t.merge(r, on=llave, how="left")
        t[f"VM2_VIG_{v}"] = t[f"VM2_VIG_{v}"].fillna(0)
        t[f"METODO_VIG_{v}"] = t[f"METODO_VIG_{v}"].fillna("fuera del motor")
        t[f"VM2_COM_VIG_{v}"] = t.pop(f"VM2_VIG_{v}")
        t[f"VM2_CAT_VIG_{v}"] = t[f"VM2_COM_VIG_{v}"] * escenarios.FACTOR_CATASTRAL[nombre]
        con = int((t[f"VM2_COM_VIG_{v}"] > 0).sum())
        print(f"--> vigencia {v}: {con:,} con valor, {len(t) - con:,} en cero")

    # Las columnas de cada vigencia juntas, en el orden en que se marcaron.
    orden = cols + [f"{c}_VIG_{v}" for v in vigencias
                    for c in ("VM2_COM", "VM2_CAT", "TABLA", "FAMILIA", "METODO", "UNIDAD")]
    t = t[orden]
    ruta = carpeta_salida / "LIQUIDACION_VIGENCIAS.parquet"
    t.to_parquet(ruta, index=False)
    print(f"\nEscrito: {ruta} ({len(t):,} construcciones, vigencias {vigencias})")

    def resumen(v, por):
        g = t.groupby(f"{por}_VIG_{v}" if por in ("METODO", "FAMILIA") else por, dropna=False)
        out = g.agg(CONSTRUCCIONES=(f"VM2_COM_VIG_{v}", "size"),
                    CON_VALOR=(f"VM2_COM_VIG_{v}", lambda s: int((s > 0).sum())))
        out["VM2_COM_MEDIANA"] = g[f"VM2_COM_VIG_{v}"].apply(lambda s: s[s > 0].median()).round(0)
        return out.reset_index().sort_values("CONSTRUCCIONES", ascending=False)

    ruta_x = carpeta_salida / "RESUMEN_VIGENCIAS.xlsx"
    with pd.ExcelWriter(ruta_x, engine="xlsxwriter") as xw:
        pd.DataFrame([{"VIGENCIA": v,
                       "REGLAS": "actuales (2027)" if v == 2027 else f"ejercicio {MOTOR[v]}",
                       "CONSTRUCCIONES": len(t),
                       "CON_VALOR": int((t[f"VM2_COM_VIG_{v}"] > 0).sum()),
                       "SIN_VALOR": int((t[f"VM2_COM_VIG_{v}"] <= 0).sum())} for v in vigencias]
                     ).to_excel(xw, sheet_name="RESUMEN", index=False)
        for v in vigencias:
            for hoja, por in (("METODO", "METODO"), ("FAMILIA", "FAMILIA"), ("COMUNA", "COMUNA")):
                resumen(v, por).to_excel(xw, sheet_name=f"{hoja}_VIG_{v}", index=False)
    print(f"Escrito: {ruta_x}")

    if txt_sistemas:
        escribir_txt(t, carpeta_salida / "LIQUIDACION_VIGENCIAS.txt")

    if detalle_excel:
        ruta_d = carpeta_salida / "LIQUIDACION_VIGENCIAS.xlsx"
        print(f"Escribiendo el detalle en Excel ({len(t):,} filas, tarda unos minutos)...")
        with pd.ExcelWriter(ruta_d, engine="xlsxwriter",
                            engine_kwargs={"options": {"constant_memory": True}}) as xw:
            t.to_excel(xw, sheet_name="DETALLE", index=False)
        print(f"Escrito: {ruta_d}")
    return t
