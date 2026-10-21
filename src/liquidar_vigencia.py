"""
Liquida la vigencia 2025 o la 2026 con las reglas del ejercicio que la
produjo (2024 y 2025), sobre la base de hoy.

Usa los mismos motores que los escenarios (escenarios.py): la base sale de los
insumos elegidos, igual que en la corrida 2027, y despues se aplica la regla de
esa vigencia con sus tablas -que estan dentro de su codigo- y, si la casilla
esta prendida, con sus modelos. Como en los escenarios, las comunas que ese
ejercicio no actualizo quedan en cero.

Deja en la carpeta de salida:
  LIQUIDACION_VIGENCIA_<vigencia>.parquet   una fila por construccion
  RESUMEN_VIGENCIA_<vigencia>.xlsx          por metodo, familia y comuna

Lo llama la ventana (preliquidar_app.py); no reemplaza a main.py.
"""
import os
from pathlib import Path

import pandas as pd

# La vigencia que rige -> el escenario (ejercicio) que la produjo.
ESCENARIO = {2025: "2024", 2026: "2025"}


def correr(vigencia: int, carpeta_salida) -> pd.DataFrame:
    import escenarios
    from tabla_construccion import procesar_construcciones, cruces_const_predio

    if vigencia not in ESCENARIO:
        raise ValueError(f"La vigencia {vigencia} no se liquida por aqui (2025 o 2026).")
    nombre = ESCENARIO[vigencia]
    carpeta_salida = Path(carpeta_salida)
    carpeta_salida.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print(f"=== VIGENCIA {vigencia}: reglas del ejercicio {nombre} ===")
    print("=" * 60)

    print("\n=== PASO 1: base de construcciones y predios ===")
    df_predio, df_conv, df_noconv = procesar_construcciones()
    if df_predio is None or df_conv is None or df_noconv is None:
        raise ValueError("No se pudieron cargar los insumos de predios y construcciones.")
    print("\n=== PASO 2: cruces, homologacion y uso principal ===")
    cruces_const_predio(df_predio, df_conv, df_noconv)

    # La base que deja el cruce, la misma que leen los escenarios.
    base = pd.read_parquet(escenarios.RUTA_BASE)
    print(f"\n=== PASO 3: reglas del ejercicio {nombre} sobre {len(base):,} construcciones ===")
    r = escenarios.MOTORES[nombre](base).drop_duplicates(escenarios.LLAVE)

    cols = [c for c in escenarios.COLUMNAS_PREDIO if c in base.columns]
    t = (base[cols].assign(**{escenarios.LLAVE: base[escenarios.LLAVE].astype(str)})
         .merge(r, on=escenarios.LLAVE, how="left"))
    t = t.rename(columns={f"{c}_{nombre}": c for c in
                          ("VM2", "TABLA", "FAMILIA", "METODO", "UNIDAD")})
    t["VM2"] = t["VM2"].fillna(0)
    t["METODO"] = t["METODO"].fillna("fuera del motor")
    factor = escenarios.FACTOR_CATASTRAL[nombre]
    t["VM2_COM"] = t["VM2"]
    t["VM2_CAT"] = t["VM2"] * factor
    t["VIGENCIA"] = vigencia

    ruta = carpeta_salida / f"LIQUIDACION_VIGENCIA_{vigencia}.parquet"
    t.to_parquet(ruta, index=False)
    print(f"\nEscrito: {ruta} ({len(t):,} construcciones)")

    # Resumen: cuantas salen por cada via, de que familia y en que comuna.
    def resumen(por):
        g = t.groupby(por, dropna=False)
        out = g.agg(CONSTRUCCIONES=("VM2", "size"),
                    CON_VALOR=("VM2", lambda s: int((s > 0).sum())))
        out["VM2_COM_MEDIANA"] = g["VM2_COM"].apply(lambda s: s[s > 0].median()).round(0)
        out["VM2_CAT_MEDIANA"] = g["VM2_CAT"].apply(lambda s: s[s > 0].median()).round(0)
        return out.reset_index().sort_values("CONSTRUCCIONES", ascending=False)

    ruta_x = carpeta_salida / f"RESUMEN_VIGENCIA_{vigencia}.xlsx"
    with pd.ExcelWriter(ruta_x, engine="xlsxwriter") as xw:
        pd.DataFrame({"DATO": ["Vigencia", "Reglas", "Factor catastral",
                               "Construcciones", "Con valor", "Sin valor"],
                      "VALOR": [vigencia, f"ejercicio {nombre}", factor, len(t),
                                int((t["VM2"] > 0).sum()), int((t["VM2"] <= 0).sum())]}
                     ).to_excel(xw, sheet_name="RESUMEN", index=False)
        for hoja, por in (("POR_METODO", "METODO"), ("POR_FAMILIA", "FAMILIA"),
                          ("POR_COMUNA", "COMUNA")):
            resumen(por).to_excel(xw, sheet_name=hoja, index=False)
    print(f"Escrito: {ruta_x}")
    print("\n" + t["METODO"].value_counts().to_string())
    return t
