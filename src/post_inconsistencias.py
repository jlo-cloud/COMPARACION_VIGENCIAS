"""Post-inconsistencias: lo que despues de liquidar quedo en $ 0, y por que.

Va despues de la liquidacion (main.py, PASO 4) sobre el mismo df que se
guarda en LIQUIDACION_TABLAS.parquet. A diferencia de las pre-inconsistencias,
aqui no se descuenta nada: se cuenta lo que no tomo valor, separado en urbano y
rural, con un motivo por construccion.

Corrido solo, lee el parquet de la ultima corrida:
    python src/post_inconsistencias.py
"""
import os
from datetime import datetime

import numpy as np
import pandas as pd

# Las mismas columnas y el mismo diccionario de las hojas de pre-inconsistencias.
# La hoja SIN_REGLA_LIQUIDACION lleva ademas DETALLE, porque junta varios casos.
from pre_inconsistencias import COLUMNAS_REPORTE as COLUMNAS, DICCIONARIO as _DICC_PRE  # noqa: E402

DICCIONARIO = {**_DICC_PRE,
               "DETALLE": "Solo en SIN_REGLA_LIQUIDACION: el caso puntual (anexo o parqueadero "
                          "sin valor en su tabla, rural sin tabla en la entrega, uso sin tabla)"}

# Los motivos, en este orden, y la hoja de cada uno.
MOTIVOS = {"MODELO": "MODELO", "ESPECIAL": "ESPECIAL", "SIN ZHF": "SIN_ZHF",
           "SIN REGLA DE LIQUIDACIÓN": "SIN_REGLA_LIQUIDACION"}


def motivo_cero(d: pd.DataFrame) -> pd.Series:
    t = d["TABLA_ORIGEN"].astype(str)
    rural = (d["MOTIVO_RURAL"].fillna("").astype(str) if "MOTIVO_RURAL" in d.columns
             else pd.Series("", index=d.index))
    return pd.Series(np.select(
        [t == "ESPECIALES", t == "MODELO", (t == "SIN TABLA") & rural.ne(""),
         t == "SIN TABLA", t == "T10_ANEXOS", t == "T12_PARQUEADEROS"],
        ["Especial (destino 020/023): no se valora por tabla",
         "Va por modelo: los modelos estan apagados",
         "Rural - " + rural.str.replace("rural: ", "", regex=False),
         "Sin tabla asignada: el uso no tiene regla",
         "Anexo sin valor en la T10 para su clave (destino + tipo)",
         "Parqueadero sin valor en la T12"],
        default="Tabla asignada sin valor para su comuna o puntaje"), index=d.index)


def motivo(d: pd.DataFrame) -> pd.Series:
    """El motivo agrupado: MODELO, ESPECIAL, SIN ZHF o SIN REGLA DE LIQUIDACIÓN
    (anexo o parqueadero sin valor en su tabla, uso sin tabla, rural sin
    tabla en la entrega)."""
    t = d["TABLA_ORIGEN"].astype(str)
    rural = (d["MOTIVO_RURAL"].fillna("").astype(str) if "MOTIVO_RURAL" in d.columns
             else pd.Series("", index=d.index))
    return pd.Series(np.select(
        [t == "MODELO", t == "ESPECIALES", rural.str.contains("sin ZHF")],
        ["MODELO", "ESPECIAL", "SIN ZHF"], default="SIN REGLA DE LIQUIDACIÓN"), index=d.index)


def generar_reporte_post(df_liq: pd.DataFrame,
                         output_path: str = "./output/post_inconsistencias/") -> str:
    """Construcciones en $ 0 despues de liquidar, con motivo, urbano y rural."""
    valor = pd.to_numeric(df_liq.get("VM2"), errors="coerce").fillna(0)
    if "LIQ_PARQUEADERO" in df_liq.columns:
        valor = valor.where(valor > 0, pd.to_numeric(df_liq["LIQ_PARQUEADERO"],
                                                     errors="coerce").fillna(0))
    cero = df_liq[valor <= 0].copy()
    cero["ZONA"] = np.where(pd.to_numeric(cero["COMUNA"], errors="coerce") > 22,
                            "RURAL", "URBANO")
    cero["MOTIVO"] = motivo(cero)
    cero["DETALLE"] = motivo_cero(cero)

    # Igual que el resumen de pre-inconsistencias: un MOTIVO por
    # fila, los predios y las construcciones partidas en urbano y rural.
    # Los cuatro motivos siempre, aunque alguno este en 0.
    resumen = pd.DataFrame([{
        "MOTIVO": m, "PREDIOS": int(cero.loc[cero["MOTIVO"] == m, "ID_PREDIO"].nunique()),
        "CONSTRUCCION URBANA": int(((cero["MOTIVO"] == m) & (cero["ZONA"] == "URBANO")).sum()),
        "CONSTRUCCION RURAL": int(((cero["MOTIVO"] == m) & (cero["ZONA"] == "RURAL")).sum()),
        "TOTAL DE CONSTRUCCIONES": int((cero["MOTIVO"] == m).sum())} for m in MOTIVOS])
    resumen = pd.concat([resumen, pd.DataFrame([{
        "MOTIVO": "Total", "PREDIOS": int(cero["ID_PREDIO"].nunique()),
        "CONSTRUCCION URBANA": int((cero["ZONA"] == "URBANO").sum()),
        "CONSTRUCCION RURAL": int((cero["ZONA"] == "RURAL").sum()),
        "TOTAL DE CONSTRUCCIONES": len(cero)}])], ignore_index=True)

    detalle = cero.reindex(columns=COLUMNAS + ["MOTIVO", "DETALLE"])
    os.makedirs(output_path, exist_ok=True)
    archivo = os.path.join(output_path,
                           f"reporte_post_inconsistencias_{datetime.now():%Y%m%d}.xlsx")
    with pd.ExcelWriter(archivo, engine="xlsxwriter") as w:
        resumen.to_excel(w, sheet_name="RESUMEN", index=False)
        # Una hoja por motivo, con urbano y rural juntos (columna ZONA).
        for m, hoja in MOTIVOS.items():
            cols = COLUMNAS + (["DETALLE"] if m == "SIN REGLA DE LIQUIDACIÓN" else [])
            parte = detalle.loc[detalle["MOTIVO"] == m, cols]
            if len(parte):
                parte.to_excel(w, sheet_name=hoja, index=False)
                if "DETALLE" in cols:
                    w.sheets[hoja].set_column(len(cols) - 1, len(cols) - 1, 60)

        pd.DataFrame({"COLUMNA": list(DICCIONARIO), "DESCRIPCION": list(DICCIONARIO.values())}
                     ).to_excel(w, sheet_name="DICCIONARIO", index=False)
        # Enteros con separador de miles (en Excel en espanol: 130.983)
        miles = w.book.add_format({"num_format": "#,##0"})
        w.sheets["RESUMEN"].set_column(0, 0, 30)
        w.sheets["RESUMEN"].set_column(1, 4, 24, miles)
        w.sheets["DICCIONARIO"].set_column(0, 0, 28)
        w.sheets["DICCIONARIO"].set_column(1, 1, 110)
    print("\n   Post-inconsistencias (construcciones en $ 0):")
    print(resumen.to_string(index=False))
    print(f"   ✅ {archivo}")
    return archivo


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from comparacion_vigencia import CONFIG
    ruta = CONFIG["parquet_liquidacion"]
    import pyarrow.parquet as pq
    hay = set(pq.ParquetFile(ruta).schema_arrow.names)
    usar = [c for c in COLUMNAS + ["TABLA_ORIGEN", "VM2", "LIQ_PARQUEADERO", "MOTIVO_RURAL"]
            if c in hay]
    generar_reporte_post(pd.read_parquet(ruta, columns=usar))
