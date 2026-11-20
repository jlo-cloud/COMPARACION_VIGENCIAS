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

COLUMNAS = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "COMUNA",
            "ZONA", "DESTINOCONS", "DESTANEX", "TIPOANEXO", "USO_LADM", "CONDICION",
            "ZHF", "PUNTCONS", "AREA_CONST", "TABLA_ORIGEN", "TABLA_RURAL", "MOTIVO"]

DICCIONARIO = {
    "ID_PREDIO": "Identificador del predio en la base catastral",
    "NUMERO_PREDIAL_NACIONAL": "Numero predial nacional (30 digitos)",
    "CONSTRUCCION_ID": "Llave de la construccion en la liquidacion: ID_PREDIO-C/A consecutivo-destino",
    "COMUNA": "Comuna (01-22) o corregimiento (51 en adelante)",
    "ZONA": "URBANO o RURAL",
    "DESTINOCONS": "Codigo LADM del uso (000 si es anexo)",
    "DESTANEX": "Codigo LADM del anexo",
    "TIPOANEXO": "Tipo (calificacion) del anexo",
    "USO_LADM": "Nombre del uso LADM",
    "CONDICION": "Condicion de propiedad (9 = propiedad horizontal)",
    "ZHF": "Zona homogenea fisica del predio",
    "PUNTCONS": "Puntaje de la construccion",
    "AREA_CONST": "Area construida (m2)",
    "TABLA_ORIGEN": "Tabla que le asigno la liquidacion",
    "TABLA_RURAL": "Columna que asigna la entrega rural (solo rural)",
    "MOTIVO": "Por que quedo en $ 0",
}


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
    cero["MOTIVO"] = motivo_cero(cero)
    total = df_liq.assign(ZONA=np.where(pd.to_numeric(df_liq["COMUNA"], errors="coerce") > 22,
                                        "RURAL", "URBANO")).groupby("ZONA").size()

    # Igual que el resumen de pre-inconsistencias: un MOTIVO por
    # fila, los predios y las construcciones partidas en urbano y rural.
    g = cero.groupby("MOTIVO")
    resumen = pd.DataFrame({
        "PREDIOS": g["ID_PREDIO"].nunique(),
        "CONSTRUCCION URBANA": g["ZONA"].apply(lambda z: int((z == "URBANO").sum())),
        "CONSTRUCCION RURAL": g["ZONA"].apply(lambda z: int((z == "RURAL").sum())),
        "TOTAL DE CONSTRUCCIONES": g.size()}).reset_index()
    resumen = resumen.sort_values("TOTAL DE CONSTRUCCIONES", ascending=False)
    resumen = pd.concat([resumen, pd.DataFrame([{
        "MOTIVO": "Total", "PREDIOS": int(cero["ID_PREDIO"].nunique()),
        "CONSTRUCCION URBANA": int((cero["ZONA"] == "URBANO").sum()),
        "CONSTRUCCION RURAL": int((cero["ZONA"] == "RURAL").sum()),
        "TOTAL DE CONSTRUCCIONES": len(cero)}])], ignore_index=True)

    # Por tabla: de lo que cada tabla tenia asignado, cuanto quedo en $ 0 y por
    # que. MODELO, ESPECIALES y SIN TABLA salen como una "tabla" mas.
    todo = df_liq.assign(ZONA=np.where(pd.to_numeric(df_liq["COMUNA"], errors="coerce") > 22,
                                       "RURAL", "URBANO"),
                         TABLA_ORIGEN=df_liq["TABLA_ORIGEN"].astype(str))
    asignadas = todo.groupby(["ZONA", "TABLA_ORIGEN"]).size().rename("ASIGNADAS")
    por_tabla = (cero.assign(TABLA_ORIGEN=cero["TABLA_ORIGEN"].astype(str))
                 .groupby(["ZONA", "TABLA_ORIGEN"])
                 .agg(EN_CERO=("MOTIVO", "size"), PREDIOS_EN_CERO=("ID_PREDIO", "nunique"),
                      MOTIVO=("MOTIVO", lambda s: " | ".join(
                          f"{m} ({n:,})" for m, n in s.value_counts().items())))
                 .join(asignadas, how="left").reset_index())
    por_tabla["% EN CERO"] = (por_tabla["EN_CERO"] / por_tabla["ASIGNADAS"] * 100).round(2)
    por_tabla = por_tabla[["ZONA", "TABLA_ORIGEN", "ASIGNADAS", "EN_CERO", "% EN CERO",
                           "PREDIOS_EN_CERO", "MOTIVO"]].sort_values(
        ["ZONA", "EN_CERO"], ascending=[False, False])
    # Y el uso, para ver que cae en cada tabla (sobre todo en SIN TABLA y MODELO)
    por_uso = (cero.assign(TABLA_ORIGEN=cero["TABLA_ORIGEN"].astype(str),
                           USO_LADM=cero["USO_LADM"].astype(str))
               .groupby(["ZONA", "TABLA_ORIGEN", "USO_LADM", "MOTIVO"])
               .size().rename("CONSTRUCCIONES").reset_index()
               .sort_values(["ZONA", "TABLA_ORIGEN", "CONSTRUCCIONES"],
                            ascending=[False, True, False]))

    detalle = cero.reindex(columns=COLUMNAS)
    os.makedirs(output_path, exist_ok=True)
    archivo = os.path.join(output_path,
                           f"reporte_post_inconsistencias_{datetime.now():%Y%m%d}.xlsx")
    with pd.ExcelWriter(archivo, engine="xlsxwriter") as w:
        resumen.to_excel(w, sheet_name="RESUMEN", index=False)
        por_tabla.to_excel(w, sheet_name="POR_TABLA", index=False)
        por_uso.to_excel(w, sheet_name="POR_TABLA_Y_USO", index=False)
        w.sheets["POR_TABLA"].set_column(0, 0, 10)
        w.sheets["POR_TABLA"].set_column(1, 1, 26)
        w.sheets["POR_TABLA"].set_column(2, 5, 14)
        w.sheets["POR_TABLA"].set_column(6, 6, 110)
        w.sheets["POR_TABLA_Y_USO"].set_column(0, 0, 10)
        w.sheets["POR_TABLA_Y_USO"].set_column(1, 2, 34)
        w.sheets["POR_TABLA_Y_USO"].set_column(3, 3, 70)
        # Una sola hoja: la columna ZONA dice si es urbano o rural.
        detalle.to_excel(w, sheet_name="EN_CERO", index=False)
        pd.DataFrame({"COLUMNA": list(DICCIONARIO), "DESCRIPCION": list(DICCIONARIO.values())}
                     ).to_excel(w, sheet_name="DICCIONARIO", index=False)
        # Enteros con separador de miles (en Excel en espanol: 130.983)
        miles = w.book.add_format({"num_format": "#,##0"})
        w.sheets["RESUMEN"].set_column(0, 0, 62)
        w.sheets["RESUMEN"].set_column(1, 4, 24, miles)
        w.sheets["POR_TABLA"].set_column(2, 3, 14, miles)
        w.sheets["POR_TABLA"].set_column(5, 5, 14, miles)
        w.sheets["POR_TABLA_Y_USO"].set_column(4, 4, 16, miles)
        w.sheets["DICCIONARIO"].set_column(0, 1, 40)
    print("\n   Post-inconsistencias (construcciones en $ 0):")
    print(resumen.to_string(index=False))
    print(por_tabla.drop(columns="MOTIVO").to_string(index=False))
    print(f"   ✅ {archivo}")
    return archivo


if __name__ == "__main__":
    import sys
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from comparacion_vigencia import CONFIG
    ruta = CONFIG["parquet_liquidacion"]
    import pyarrow.parquet as pq
    hay = set(pq.ParquetFile(ruta).schema_arrow.names)
    usar = [c for c in COLUMNAS + ["VM2", "LIQ_PARQUEADERO", "MOTIVO_RURAL"] if c in hay]
    generar_reporte_post(pd.read_parquet(ruta, columns=usar))
