"""
Publicacion de resultados: una carpeta por ACCION y, dentro, una carpeta por
VERSION (corrida). Asi la carpeta de trabajo no se vuelve una lista larga de
archivos sueltos y quedan todas las versiones, como en el Drive del proyecto.

    <carpeta de resultados>/
        01_CALIDAD_INSUMOS/<version>/...
        01B_PREVALIDACION_COMUNAS/<version>/... (comunas aptas o no y predios que no cumplen)
        02_INCONSISTENCIAS_PREVIAS/<version>/...
        03_LIQUIDACION_CONSTRUCCIONES/<version>/...
        04_INCONSISTENCIAS_POSTERIORES/<version>/...
        05_RESULTADO_PREDIOS/<version>/...
        06_ESCENARIOS/<version>/...
        07_PREDIOS_POR_CORREGIR/<version>/...   (un Excel: predio, inconsistencia, dato que falta)
        00_MANIFIESTOS/<version>/...

<version> = <AAAA-MM-DD_HHMM>_<PRELIQUIDACION|LIQUIDACION>.

El motor sigue escribiendo en ./output y ./results como siempre (no se toca
ningun calculo); al terminar, lo que ESTA corrida genero se MUEVE a su carpeta.

Formatos del resultado por predio:
  - preliquidacion: parquet + el Excel de revision (APROBADOS / NO APROBADOS).
  - liquidacion:    ademas .txt con el formato de los export de Sistemas
                    ('|', coma decimal, latin-1).
"""

from __future__ import annotations

import os
import re
import shutil
from datetime import datetime
from pathlib import Path

import pandas as pd

FORMATOS_POR_TIPO = {
    "preliquidacion": ["parquet", "xlsx"],
    "liquidacion": ["txt", "parquet", "xlsx"],
}

# (patron sobre la ruta relativa, carpeta de accion). Gana el primero que cumpla.
DESTINOS = [
    (r"predios_por_corregir|PREDIOS_POR_CORREGIR", "07_PREDIOS_POR_CORREGIR"),
    (r"Calidad_insumos", "01_CALIDAD_INSUMOS"),
    (r"Prevalidacion", "01B_PREVALIDACION_COMUNAS"),
    (r"preliquidacion[\/]validacion", "05_RESULTADO_PREDIOS"),
    (r"Pre_inconsistencias|todas_las_construcciones", "02_INCONSISTENCIAS_PREVIAS"),
    (r"LIQUIDACION_TABLAS", "03_LIQUIDACION_CONSTRUCCIONES"),
    (r"CONTRATO_VARIABLES_MODELOS", "03_LIQUIDACION_CONSTRUCCIONES"),
    (r"post_inconsistencias", "04_INCONSISTENCIAS_POSTERIORES"),
    (r"REVISION_LIQUIDACION|PREDIOS_", "05_RESULTADO_PREDIOS"),
    (r"ESCENARIOS|DETALLE_VIGENCIAS|COMPARACION_VIGENCIA", "06_ESCENARIOS"),
    (r"manifiesto_ejecucion|manifests", "00_MANIFIESTOS"),
]
CARPETAS_ORIGEN = ["./output", "./results"]


def version(tipo: str, inicio: float | None = None) -> str:
    momento = datetime.fromtimestamp(inicio) if inicio else datetime.now()
    return f"{momento:%Y-%m-%d_%H%M}_{tipo.upper()}"


CODIGOS = ("ID_PREDIO", "NUMERO_PREDIAL", "NUMERO_PREDIAL_NACIONAL", "ID_TERR", "ID_TERRENO", "ID_MANZANA",
           "ZHF", "ZHF_ANTERIOR", "COMUNA", "BARRIO", "MATCPRED", "ID_CONSTRUCCION")


def _codigos_como_texto(df):
    """Codigos como texto: sin esto una ZHF sale '82104421013,0' en el .txt."""
    df = df.copy()
    for c in CODIGOS:
        if c in df.columns:
            df[c] = (df[c].astype("string").str.replace(r"\.0$", "", regex=True)
                     .replace({"nan": pd.NA, "<NA>": pd.NA, "None": pd.NA}))
    return df


def exportar_predios(df, carpeta: Path, tipo: str, formatos: list[str]) -> list[Path]:
    """El resultado por predio en los formatos pedidos (el Excel de revision ya lo escribe el motor)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    df = _codigos_como_texto(df)
    base = carpeta / f"PREDIOS_{tipo.upper()}"
    hechos = []
    if "parquet" in formatos:
        df.to_parquet(base.with_suffix(".parquet"), index=False)
        hechos.append(base.with_suffix(".parquet"))
    if "txt" in formatos:
        # Mismo formato que los export de Sistemas, para que lo puedan cargar.
        df.to_csv(base.with_suffix(".txt"), sep="|", decimal=",", index=False,
                  encoding="latin-1", errors="replace")
        hechos.append(base.with_suffix(".txt"))
    return hechos


def publicar(inicio: float, tipo: str, formatos: list[str], df_predios=None, raiz: str = ".",
             manifiesto: str | None = None) -> dict[str, list[str]]:
    """Mueve lo que genero ESTA corrida a <accion>/<version>/ y exporta los predios."""
    raiz_p = Path(raiz).resolve()
    ver = version(tipo, inicio)
    movidos: dict[str, list[str]] = {}

    # El manifiesto con que se corrio: se copia (el original lo reusa la interfaz).
    if manifiesto and Path(manifiesto).is_file():
        destino = raiz_p / "00_MANIFIESTOS" / ver / Path(manifiesto).name
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(manifiesto, destino)
        movidos.setdefault("00_MANIFIESTOS", []).append(str(destino))

    if df_predios is not None:
        exportar_predios(df_predios, raiz_p / "output" / "_publicar", tipo, formatos)

    for origen in CARPETAS_ORIGEN:
        o = raiz_p / origen
        if not o.is_dir():
            continue
        for actual, _, archivos in os.walk(o):
            for nombre in archivos:
                ruta = Path(actual) / nombre
                if nombre.startswith("~$"):
                    continue
                try:
                    if ruta.stat().st_mtime < inicio:
                        continue
                except OSError:
                    continue
                rel = ruta.relative_to(raiz_p).as_posix()
                accion = next((c for patron, c in DESTINOS if re.search(patron, rel, re.IGNORECASE)), "07_OTROS")
                if accion == "05_RESULTADO_PREDIOS" and nombre.lower().endswith(".xlsx") and "xlsx" not in formatos:
                    continue
                destino = raiz_p / accion / ver / nombre
                destino.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(ruta), destino)
                movidos.setdefault(accion, []).append(str(destino))

    # carpetas vacias que quedan en ./output y ./results
    for origen in ("./output", "./results"):
        o = raiz_p / origen
        if o.is_dir():
            for actual, dirs, archivos in sorted(os.walk(o), key=lambda x: -len(x[0])):
                if not dirs and not archivos and Path(actual) != o:
                    try:
                        Path(actual).rmdir()
                    except OSError:
                        pass

    print(f"\n[OK] Resultados publicados en la version {ver}:")
    for accion in sorted(movidos):
        print(f"   {accion}/{ver}/  ({len(movidos[accion])} archivo(s))")
    return movidos
