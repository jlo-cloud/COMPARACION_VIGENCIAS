"""Liquidacion rural: que columna de las tablas de valor se aplica en lo rural.

La entrega (input/tablas/input/rural/AAAAMMDD_Construcciones_rurales_por_uso_ZHF.xlsx,
hoja CONTEO) no trae valores nuevos: para cada uso LADM y cada "uso de la ZHF
rural" -los 2 ultimos digitos de la ZHF de 12 digitos- dice que columna de las
tablas URBANAS se aplica. P.ej. Vivienda_Hasta_3_Pisos con ZHF terminada en 12
(Residencial_tipo2) va con T1_RESIDENCIAL_10C_COND_9_012.

Lo usa Liquidacion_tablas.py cuando LIQUIDAR_RURAL = True. Corrido solo,
    python src/reglas_rurales.py
valida la entrega contra el consolidado de tablas y contra la base, sin tocar
la liquidacion, y deja el reporte en results/RURAL/.
"""
import os
import re
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

RAIZ = Path(os.environ.get("PRELIQ_RAIZ") or Path(__file__).resolve().parent.parent)
if str(RAIZ / "src") not in sys.path:
    sys.path.insert(0, str(RAIZ / "src"))

import insumos  # noqa: E402

CARPETA = RAIZ / "input" / "tablas" / "input" / "rural"
PATRON = "*_Construcciones_rurales_por_uso_ZHF.xlsx"
COMUNAS_RURALES = insumos.COMUNAS_RURALES

# Comercial -> catastral en lo rural: la vigencia rural no se actualizo en
# 2024-2025, asi que va con el factor de las comunas sin actualizar.
FACTOR_COMERCIAL_RURAL = 0.6

SIN_ZHF = "SIN ZHF"

# En lo rural, comercio y oficinas en PH van por TABLA, no por modelo: toman
# la regla de su uso sin PH (con el mismo uso de la ZHF rural). Solo los
# apartamentos en PH (001) siguen por modelo. En lo urbano no cambia nada.
#
# ESTA REGLA NO VIENE EN EL EXCEL DE LA ENTREGA RURAL: el Excel no dice que
# el 028 y el 034 dejan el modelo y toman la regla de su uso sin PH. La definio el
# equipo de tablas aparte (noviembre 2026) y vive solo aqui. asignar() cambia
# el destino ANTES de buscar en la entrega, asi que las filas propias del 028
# y del 034 en el Excel no se usan nunca. Si una entrega nueva la incluye,
# este diccionario se puede quitar.
RURAL_PH_COMO_NO_PH = {"028": "025",   # Comercio_en_PH -> Comercio
                       "034": "032"}   # Oficinas_Consultorios_en_PH -> Oficinas_Consultorios

# Dominio del uso de la ZHF rural (2 ultimos digitos de la ZHF de 12 digitos).
USO_ZHF_RURAL = {
    "01": "Agricola", "02": "Pecuario", "03": "Forestal", "04": "Tierras Improductivas",
    "05": "Cuerpos de Agua", "06": "Condiciones Especiales", "07": "Edificaciones",
    "08": "Agropecuario", "09": "Agroindustrial", "10": "Minero",
    "11": "Residencial_tipo1", "12": "Residencial_tipo2", "13": "Residencial_tipo3",
    "14": "Residencial_tipo4", "15": "Residencial_tipo5", "16": "Residencial_tipo6",
    "17": "Comercial_Local", "18": "Comercial_Zonal", "19": "Comercial_Metropolitano",
    "20": "Industrial_Pequeña", "21": "Industrial_Mediana", "22": "Industrial_Grande",
    "23": "Institucional_o_dotacional", "24": "Lote_Urbanizable_No_Urbanizado",
    "25": "Lote_Urbanizado_No_Construido", "26": "Lote_No_Urbanizable",
    "27": "Espacio_Publico_De_Zonas_Verdes", "28": "Espacio_Publico_De_Parques",
    "29": "Espacio_Publico_Vial", "30": "Espacio_Otros",
}


# ESTRUCTURA_ZHF_RURAL_2026_Ajust_V5: 1er digito = clasificacion del suelo;
# digitos 2 y 3 = area de manejo / plan parcial.
CLASIFICACION_SUELO_RURAL = {"1": "Rural", "2": "Expansion urbana"}
AREA_MANEJO_RURAL = {
    "01": "PNN Los Farallones de Cali",
    "02": "Reserva Forestal Protectora Nacional de Cali",
    "03": "Ecoparques",
    "04": "Zona rural de regulacion hidrica",
    "05": "Zona rural de produccion sostenible",
    "06": "Areas sustraidas de la Reserva Forestal Protectora Nacional de Cali",
    "07": "Centros poblados",
    "08": "Suelo rural suburbano",
    "09": "Corredor suburbano interregional Cali - Jamundi",
    "10": "Suelo de expansion sin plan parcial adoptado",
    "11": "Suelo de expansion con plan parcial",
    "12": "Otras zonas con plan parcial",
}


def _parte_zhf(zhf: pd.Series, ini: int, fin: int, dominio: dict) -> pd.Series:
    """Un tramo de la ZHF rural de 12 digitos con su descripcion; sin ZHF de
    12 digitos, 'SIN ZHF'; un codigo fuera del dominio sale solo."""
    z = zhf.astype(str).str.strip()
    c = z.str[ini:fin].where(z.str.fullmatch(r"\d{12}"), SIN_ZHF)
    return c.map(lambda x: x if x == SIN_ZHF else f"{x} {dominio.get(x, '')}".strip())


def clasificacion_suelo(zhf: pd.Series) -> pd.Series:
    """1er digito de la ZHF rural, p. ej. '1 Rural'."""
    return _parte_zhf(zhf, 0, 1, CLASIFICACION_SUELO_RURAL)


def area_manejo(zhf: pd.Series) -> pd.Series:
    """Digitos 2 y 3 de la ZHF rural, p. ej. '07 Centros poblados'."""
    return _parte_zhf(zhf, 1, 3, AREA_MANEJO_RURAL)


def actividad_rural(zhf: pd.Series) -> pd.Series:
    """La 'actividad economica' de lo rural: el uso de la ZHF rural con su
    descripcion, p. ej. '12 Residencial_tipo2'. Sin ZHF de 12 digitos: 'SIN ZHF'.
    Un codigo fuera del dominio sale con el codigo solo."""
    u = uso_zhf(zhf)
    return u.map(lambda c: c if c == SIN_ZHF else f"{c} {USO_ZHF_RURAL.get(c, '')}".strip())
# Lo que dice la entrega para cada fila, ya resuelto en un estado.
TABLA, T10, T12, MODELO, SIN_TABLA = "TABLA", "T10", "T12", "MODELO", "SIN TABLA"


# El insumo limpio que sale de la entrega: es lo que lee la liquidacion. La
# entrega queda como llego, de respaldo. Una sola hoja (REGLAS) y solo estas
# columnas: TABLA_RURAL_ENTREGA dice como se liquida -la columna exacta del
# Excel de tablas, T10_ANEXOS, T12_PARQUEADEROS, MODELO o vacio (sin tabla)-.
PATRON_LIMPIO = "REGLAS_RURALES_*.xlsx"
COLUMNAS_LIMPIO = ["TIPO_CONSTRUCCION", "DESTINOCONS", "USO_LADM", "USO_ZHF",
                   "TIPOLOGIA_RURAL", "TABLA_RURAL_ENTREGA"]
ANCHOS_LIMPIO = [26, 18, 39, 10, 31, 51]


def _fecha(ruta) -> str:
    """AAAAMMDD del nombre del archivo ('' si no trae)."""
    m = re.search(r"(\d{8})", Path(ruta).name)
    return m.group(1) if m else ""


def entrega_vigente():
    """La entrega rural mas reciente (por la fecha del nombre), o None."""
    archivos = sorted(f for f in CARPETA.glob(PATRON) if not f.name.startswith("~$"))
    return archivos[-1] if archivos else None


def reglas_vigentes():
    """El insumo limpio mas reciente, o None."""
    archivos = sorted(f for f in CARPETA.glob(PATRON_LIMPIO) if not f.name.startswith("~$"))
    return archivos[-1] if archivos else None


def _derivar(r: pd.DataFrame) -> pd.DataFrame:
    """De TABLA_RURAL_ENTREGA salen ESTADO, COLUMNA y TABLA_ORIGEN (no se
    guardan en el archivo: se calculan al leerlo)."""
    t = r["TABLA_RURAL_ENTREGA"].astype(str).str.strip()
    es_columna = t.str.fullmatch(r"T\d+_[A-Z0-9_]+") & ~t.isin(["T10_ANEXOS", "T12_PARQUEADEROS"])
    r["ESTADO"] = np.select(
        [es_columna, t.str.contains("T10"), t.str.contains("T12"), t.str.upper() == "MODELO"],
        [TABLA, T10, T12, MODELO], default=SIN_TABLA)
    r["COLUMNA"] = np.where(es_columna, t, "")
    r["TABLA_ORIGEN"] = [nombre_tabla(x) if x else "" for x in r["COLUMNA"]]
    return r


def cargar_reglas(ruta=None) -> pd.DataFrame:
    """Las reglas rurales desde el insumo limpio (REGLAS_RURALES_<fecha>.xlsx).

    Si no hay insumo limpio, o la entrega es mas nueva que el, se arma primero
    con limpiar(): asi una entrega nueva entra sola, pero siempre se lee del
    archivo limpio y no de la entrega.
    """
    if ruta is None:
        limpio, entrega = reglas_vigentes(), entrega_vigente()
        if entrega is not None and (limpio is None or _fecha(entrega) > _fecha(limpio)):
            print(f"Reglas rurales: se limpia la entrega {entrega.name}")
            limpio = limpiar(entrega)
        if limpio is None:
            raise FileNotFoundError(f"No hay reglas rurales en {CARPETA} "
                                    f"({PATRON_LIMPIO} ni {PATRON})")
        ruta = limpio
    r = pd.read_excel(ruta, sheet_name="REGLAS", dtype=str).fillna("")
    for c in r.columns:
        r[c] = r[c].astype(str).str.strip()
    r["DESTINOCONS"] = r["DESTINOCONS"].str.zfill(3)
    r = _derivar(r)
    dup = r[r["TIPO_CONSTRUCCION"].str.startswith("Conv")].duplicated(["DESTINOCONS", "USO_ZHF"], keep=False)
    if dup.any():
        raise ValueError(f"{Path(ruta).name} repite DESTINOCONS + USO_ZHF:\n"
                         + r[dup.reindex(r.index, fill_value=False)].to_string())
    r.attrs["archivo"] = Path(ruta).name
    return r


def limpiar(ruta_entrega=None) -> Path:
    """La entrega como insumo limpio: una hoja REGLAS con las 6 columnas, codigos
    con ceros, USO_ZHF en 2 digitos o 'SIN ZHF' y en TABLA_RURAL_ENTREGA el
    nombre de la tabla (columna exacta validada contra el consolidado,
    T10_ANEXOS, T12_PARQUEADEROS, MODELO o vacio)."""
    ruta_entrega = Path(ruta_entrega or entrega_vigente())
    r = leer_entrega(ruta_entrega)
    from consolidar_tablas import tabla_valor_vigente
    ruta_tablas = tabla_valor_vigente()
    if ruta_tablas:
        cols = set(pd.read_excel(ruta_tablas, sheet_name="CONVENCIONALES", nrows=0).columns.astype(str))
        faltan = sorted(set(r.loc[r["COLUMNA"] != "", "COLUMNA"]) - cols)
        if faltan:
            raise ValueError(f"La entrega rural asigna columnas que no estan en "
                             f"{Path(ruta_tablas).name}: {faltan}")
    r["TABLA_RURAL_ENTREGA"] = np.select(
        [r["ESTADO"] == TABLA, r["ESTADO"] == T10, r["ESTADO"] == T12, r["ESTADO"] == MODELO],
        [r["COLUMNA"], "T10_ANEXOS", "T12_PARQUEADEROS", "MODELO"], default="")
    orden = {"Convencional": 0, "No convencional": 1}
    r = (r.assign(_o=r["TIPO_CONSTRUCCION"].map(orden).fillna(2))
          .sort_values(["_o", "DESTINOCONS", "USO_ZHF"])[COLUMNAS_LIMPIO])
    # Lleva la fecha de la entrega, para saber de cual salio.
    salida = CARPETA / f"REGLAS_RURALES_{_fecha(ruta_entrega) or f'{date.today():%Y%m%d}'}.xlsx"
    with pd.ExcelWriter(salida, engine="xlsxwriter") as w:
        r.to_excel(w, sheet_name="REGLAS", index=False)
        h = w.sheets["REGLAS"]
        for j, a in enumerate(ANCHOS_LIMPIO):
            h.set_column(j, j, a)
        h.autofilter(0, 0, len(r), len(r.columns) - 1)
        h.freeze_panes(1, 3)
    print(f"Reglas rurales limpias: {salida} ({len(r)} reglas)")
    return salida


def leer_entrega(ruta) -> pd.DataFrame:
    """La hoja CONTEO de la entrega como reglas: una fila por DESTINOCONS + USO_ZHF.

    USO_ZHF es '01'..'24' o 'SIN ZHF'; en los no convencionales va vacia
    porque no dependen de la ZHF. ESTADO dice como se liquida.
    """
    c = pd.read_excel(ruta, sheet_name="CONTEO", dtype=str)
    c = c.iloc[:, :9]
    c.columns = ["TIPO_CONSTRUCCION", "DESTINOCONS", "USO_LADM", "TABLA_URBANO",
                 "USO_ZHF", "TIPOLOGIA_RURAL", "CONSTRUCCIONES", "OBSERVACION",
                 "TABLA_RURAL"]
    c = c[c["DESTINOCONS"].notna() & (c["DESTINOCONS"].str.strip() != "TOTAL")].copy()
    for col in c.columns:
        c[col] = c[col].fillna("").astype(str).str.strip().replace({"nan": "", "None": ""})
    c["DESTINOCONS"] = c["DESTINOCONS"].str.zfill(3)
    c["USO_ZHF"] = c["USO_ZHF"].str.upper().replace({"": ""})
    c.loc[c["USO_ZHF"].str.startswith("SIN"), "USO_ZHF"] = SIN_ZHF
    c.loc[c["USO_ZHF"].str.fullmatch(r"\d"), "USO_ZHF"] = c["USO_ZHF"].str.zfill(2)

    t = c["TABLA_RURAL"]
    es_columna = t.str.fullmatch(r"T\d+_[A-Z0-9_]+")
    c["ESTADO"] = np.select(
        [es_columna, t.str.contains("T10"), t.str.contains("T12"),
         c["TABLA_URBANO"].str.upper().str.startswith("MODELO")],
        [TABLA, T10, T12, MODELO], default=SIN_TABLA)
    c["COLUMNA"] = np.where(es_columna, t, "")
    c["TABLA_ORIGEN"] = [nombre_tabla(x) if x else "" for x in c["COLUMNA"]]

    dup = c[c["TIPO_CONSTRUCCION"].str.startswith("Conv")].duplicated(["DESTINOCONS", "USO_ZHF"], keep=False)
    if dup.any():
        raise ValueError("La entrega rural repite DESTINOCONS + USO_ZHF:\n"
                         + c[dup.reindex(c.index, fill_value=False)].to_string())
    c.attrs["archivo"] = Path(ruta).name
    return c.reset_index(drop=True)


def nombre_tabla(columna: str) -> str:
    """Columna del Excel -> nombre de TABLA_ORIGEN, con la misma regla con que
    Liquidacion_tablas.py arma valores_por_tabla: se quita el grupo de comunas
    (7C, 10C, 5C_N, 17C), COND_0 desaparece y COND_9 queda como sufijo _9.
    T1_RESIDENCIAL_10C_COND_9_013 -> T1_RESIDENCIAL_013_9."""
    partes = str(columna).strip().split("_")
    for i, p in enumerate(partes):
        if re.fullmatch(r"\d+C", p):
            fin = i + 2 if i + 1 < len(partes) and partes[i + 1] == "N" else i + 1
            partes = partes[:i] + partes[fin:]
            break
    partes = [p for p in partes if p != "COND"]
    if "9" not in partes and "0" in partes:
        partes.remove("0")
    if "9" in partes:
        partes.remove("9")
        partes.append("9")
    return "_".join(partes)


def uso_zhf(zhf: pd.Series) -> pd.Series:
    """Los 2 ultimos digitos de la ZHF rural (12 digitos); lo demas, 'SIN ZHF'."""
    z = zhf.astype(str).str.strip()
    return z.str[-2:].where(z.str.fullmatch(r"\d{12}"), SIN_ZHF)


def es_rural(df: pd.DataFrame) -> pd.Series:
    return df["COMUNA"].astype(str).str.strip().str.zfill(2).isin(COMUNAS_RURALES)


def asignar(df: pd.DataFrame, reglas: pd.DataFrame) -> pd.DataFrame:
    """TABLA_ORIGEN de las construcciones rurales segun la entrega.

    No toca lo que ya va por otra via: especiales (020/023), anexos (T10) y
    parqueaderos (T12) siguen con su regla, que es la misma de lo urbano.
    Agrega TABLA_RURAL (la columna exacta del Excel) y MOTIVO_RURAL.
    """
    df = df.copy()
    for col in ("TABLA_RURAL", "MOTIVO_RURAL"):
        if col not in df.columns:
            df[col] = ""
    rur = es_rural(df) & ~df["TABLA_ORIGEN"].astype(str).isin(
        ["ESPECIALES", "T10_ANEXOS", "T12_PARQUEADEROS"])
    if not rur.any():
        return df

    conv = reglas[reglas["TIPO_CONSTRUCCION"].str.startswith("Conv")]
    por_clave = conv.set_index(["DESTINOCONS", "USO_ZHF"])
    # Un uso que va por modelo o sin tabla lo es para cualquier ZHF
    por_uso = (conv[conv["ESTADO"].isin([MODELO, SIN_TABLA]) & (conv["USO_ZHF"] != SIN_ZHF)]
               .drop_duplicates("DESTINOCONS").set_index("DESTINOCONS"))

    d = df.loc[rur]
    destino = d["DESTINOCONS"].astype(str).str.zfill(3).replace(RURAL_PH_COMO_NO_PH)
    clave = pd.MultiIndex.from_arrays([destino, uso_zhf(d["ZHF"])])
    hit = por_clave.reindex(clave)
    estado = hit["ESTADO"].to_numpy(dtype=object)
    columna = hit["COLUMNA"].fillna("").to_numpy(dtype=object)
    origen = hit["TABLA_ORIGEN"].fillna("").to_numpy(dtype=object)

    falta = pd.isna(estado)
    uso_entero = por_uso.reindex(destino)["ESTADO"].to_numpy(dtype=object)
    estado = np.where(falta & pd.notna(uso_entero), uso_entero, estado)

    # Un uso al que la entrega le da la MISMA columna en todas sus ZHF (al menos
    # dos) no depende de la ZHF: esa columna vale tambien para una ZHF que la
    # entrega no lista. La entrega se armo con las ZHF que habia en la base, y
    # un predio que despues recibe ZHF nueva (Unidad_Deportiva en uso 13) se
    # quedaba sin regla teniendo una sola tabla posible (T13).
    con_zhf = conv[conv["USO_ZHF"] != SIN_ZHF]
    g = con_zhf.groupby("DESTINOCONS")
    unica = g.filter(lambda x: len(x) >= 2 and (x["ESTADO"] == TABLA).all()
                     and x["COLUMNA"].nunique() == 1)
    por_uso_tabla = unica.drop_duplicates("DESTINOCONS").set_index("DESTINOCONS")
    ut = por_uso_tabla.reindex(destino)
    usa_unica = pd.isna(estado) & ut["ESTADO"].notna().to_numpy() & \
        (clave.get_level_values(1) != SIN_ZHF)
    estado = np.where(usa_unica, TABLA, estado)
    columna = np.where(usa_unica, ut["COLUMNA"].fillna("").to_numpy(dtype=object), columna)
    origen = np.where(usa_unica, ut["TABLA_ORIGEN"].fillna("").to_numpy(dtype=object), origen)
    sin_zhf = clave.get_level_values(1) == SIN_ZHF

    nuevo = np.select([estado == TABLA, estado == MODELO, estado == T12],
                      [origen, "MODELO", "T12_PARQUEADEROS"], default="SIN TABLA")
    motivo = np.select(
        [estado == TABLA, estado == MODELO, sin_zhf, estado == SIN_TABLA],
        ["", "rural: va por modelo", "rural: sin ZHF, no se puede escoger la tipologia",
         "rural: la entrega no le asigna tabla"],
        default="rural: uso o ZHF sin regla en la entrega")

    df.loc[rur, "TABLA_ORIGEN"] = nuevo
    df.loc[rur, "TABLA_RURAL"] = np.where(estado == TABLA, columna, "")
    df.loc[rur, "MOTIVO_RURAL"] = motivo
    return df


def valorar(df: pd.DataFrame, tablas_conv: pd.DataFrame) -> pd.Series:
    """VM2 de las filas con TABLA_RURAL: la columna exacta del Excel en la fila
    de su puntaje. tablas_conv es la hoja CONVENCIONALES con el puntaje de indice."""
    vm2 = pd.Series(0.0, index=df.index)
    con = df["TABLA_RURAL"].astype(str).ne("") & df["TABLA_RURAL"].notna()
    if not con.any():
        return vm2
    largo = tablas_conv.stack()
    largo.index.names = ["PUNTCONS", "COLUMNA"]
    claves = pd.MultiIndex.from_arrays(
        [pd.to_numeric(df.loc[con, "PUNTCONS"], errors="coerce").fillna(0).astype(int),
         df.loc[con, "TABLA_RURAL"].astype(str)])
    vm2.loc[con] = largo.reindex(claves).fillna(0).to_numpy()
    return vm2


def leer_convencionales(ruta) -> pd.DataFrame:
    t = pd.read_excel(ruta, sheet_name="CONVENCIONALES")
    t = t.set_index(t.columns[0])
    t.columns = [str(c).strip() for c in t.columns]
    return t


COLUMNAS_COBERTURA = ["COMUNA", "TABLA_ORIGEN", "MOTIVO_RURAL", "VM2", "LIQ_PARQUEADERO"]


def cobertura(liq: pd.DataFrame) -> pd.DataFrame:
    """Como quedo liquidado lo rural, sin identificadores: por via y motivo,
    cuantas construcciones y cuantas con valor. liq son filas de
    LIQUIDACION_TABLAS (basta con COLUMNAS_COBERTURA)."""
    d = liq[es_rural(liq)].copy()
    t = d["TABLA_ORIGEN"].astype(str)
    motivo = (d["MOTIVO_RURAL"].fillna("").astype(str) if "MOTIVO_RURAL" in d.columns
              else pd.Series("", index=d.index))
    d["COMO_SE_LIQUIDA"] = np.select(
        [t == "T10_ANEXOS", t == "T12_PARQUEADEROS", t == "MODELO", t == "ESPECIALES", t == "SIN TABLA"],
        ["Anexo (T10)", "Parqueadero (T12)", "Modelo (pendiente)", "Especial (pendiente)", "Sin regla: queda en 0"],
        default="Tabla (entrega rural)")
    d["MOTIVO"] = motivo.str.replace("rural: ", "", regex=False)
    d.loc[d["COMO_SE_LIQUIDA"] == "Anexo (T10)", "MOTIVO"] = "clave de la T10"
    d.loc[d["COMO_SE_LIQUIDA"] == "Parqueadero (T12)", "MOTIVO"] = "regla de la T12"
    valor = pd.to_numeric(d["VM2"], errors="coerce").fillna(0)
    if "LIQ_PARQUEADERO" in d.columns:
        valor = valor.where(valor > 0, pd.to_numeric(d["LIQ_PARQUEADERO"], errors="coerce").fillna(0))
    d["CON_VALOR"] = (valor > 0).astype(int)
    orden = {"Tabla (entrega rural)": 0, "Anexo (T10)": 1, "Parqueadero (T12)": 2,
             "Modelo (pendiente)": 3, "Especial (pendiente)": 4, "Sin regla: queda en 0": 5}
    r = (d.groupby(["COMO_SE_LIQUIDA", "MOTIVO"])
         .agg(CONSTRUCCIONES=("CON_VALOR", "size"), CON_VALOR=("CON_VALOR", "sum"))
         .reset_index())
    r["SIN_VALOR"] = r["CONSTRUCCIONES"] - r["CON_VALOR"]
    r = r.sort_values(["COMO_SE_LIQUIDA", "CONSTRUCCIONES"], key=lambda s: s.map(orden) if s.name == "COMO_SE_LIQUIDA" else -s)
    tot = pd.DataFrame([{"COMO_SE_LIQUIDA": "TOTAL", "MOTIVO": "",
                         **{c: int(r[c].sum()) for c in ("CONSTRUCCIONES", "CON_VALOR", "SIN_VALOR")}}])
    return pd.concat([r, tot], ignore_index=True)


def cobertura_con_valor(liq: pd.DataFrame) -> pd.DataFrame:
    """La cobertura que va a la app: solo lo que tomo valor, por via. Lo que
    queda en $ 0 (modelo, sin regla, clave sin valor) no sube: esta en el
    reporte de post-inconsistencias."""
    c = cobertura(liq)
    c = c[(c["COMO_SE_LIQUIDA"] != "TOTAL") & (c["CON_VALOR"] > 0)]
    c = (c.groupby("COMO_SE_LIQUIDA", sort=False)["CON_VALOR"].sum()
          .rename("CONSTRUCCIONES").reset_index())
    tot = pd.DataFrame([{"COMO_SE_LIQUIDA": "TOTAL CON VALOR",
                         "CONSTRUCCIONES": int(c["CONSTRUCCIONES"].sum())}])
    return pd.concat([c, tot], ignore_index=True)


# ---------------------------------------------------------------------------
# Validacion: corrida sola, sin tocar la liquidacion
# ---------------------------------------------------------------------------
def validar(ruta_liq=None, salida=None) -> Path:
    from consolidar_tablas import tabla_valor_vigente

    reglas = cargar_reglas()
    ruta_tablas = tabla_valor_vigente()
    conv = leer_convencionales(ruta_tablas)
    faltan = sorted(set(reglas.loc[reglas["COLUMNA"] != "", "COLUMNA"]) - set(conv.columns))

    ruta_liq = ruta_liq or RAIZ / "output" / "versiones" / "V2" / "LIQUIDACION_TABLAS.parquet"
    cols = ["COMUNA", "ZHF", "DESTINOCONS", "DESTANEX", "USO_LADM", "TABLA_ORIGEN",
            "PUNTCONS", "AREA_CONST", "VALORCONS"]
    base = pd.read_parquet(ruta_liq, columns=cols)
    base = base[es_rural(base)].copy()
    rur = asignar(base, reglas)
    rur["VM2_CAT_LIQ"] = valorar(rur, conv) * 0.7            # la tabla es comercial
    rur["VM2_COM_LIQ"] = rur["VM2_CAT_LIQ"] / 0.7
    area = pd.to_numeric(rur["AREA_CONST"], errors="coerce")
    rur["VM2_CAT_VIGENCIA"] = pd.to_numeric(rur["VALORCONS"], errors="coerce") / area.where(area > 0)
    rur["VM2_COM_VIGENCIA"] = rur["VM2_CAT_VIGENCIA"] / FACTOR_COMERCIAL_RURAL
    rur["VARIACION_COM_PCT"] = (rur["VM2_COM_LIQ"] / rur["VM2_COM_VIGENCIA"] - 1) * 100
    rur.loc[rur["VM2_COM_LIQ"] <= 0, "VARIACION_COM_PCT"] = np.nan

    rur["COMO_SE_LIQUIDA"] = np.select(
        [rur["TABLA_RURAL"] != "", rur["TABLA_ORIGEN"] == "T10_ANEXOS",
         rur["TABLA_ORIGEN"] == "T12_PARQUEADEROS", rur["TABLA_ORIGEN"] == "MODELO",
         rur["TABLA_ORIGEN"] == "ESPECIALES"],
        ["tabla (entrega rural)", "T10 anexos (como en urbano)", "T12 parqueaderos (como en urbano)",
         "modelo (pendiente)", "especial (pendiente)"],
        default="sin tabla")
    resumen = (rur.groupby("COMO_SE_LIQUIDA")
               .agg(CONSTRUCCIONES=("COMUNA", "size"),
                    CON_VALOR_DE_TABLA_RURAL=("VM2_COM_LIQ", lambda v: int((v > 0).sum())))
               .reset_index().sort_values("CONSTRUCCIONES", ascending=False))
    por_tabla = (rur[rur["TABLA_RURAL"] != ""].groupby(["TABLA_RURAL", "TABLA_ORIGEN"])
                 .agg(CONSTRUCCIONES=("COMUNA", "size"),
                      VM2_COM_2026_MEDIANA=("VM2_COM_VIGENCIA", "median"),
                      VM2_COM_2027_MEDIANA=("VM2_COM_LIQ", "median"),
                      VARIACION_MEDIANA_PCT=("VARIACION_COM_PCT", "median"),
                      PCT_SUBEN=("VARIACION_COM_PCT", lambda v: (v > 0).mean() * 100))
                 .round(1).reset_index().sort_values("CONSTRUCCIONES", ascending=False))
    sin = rur[rur["MOTIVO_RURAL"].str.startswith("rural:") & (rur["TABLA_ORIGEN"] == "SIN TABLA")]
    sin = (sin.assign(USO_ZHF=uso_zhf(sin["ZHF"]))
           .groupby(["MOTIVO_RURAL", "DESTINOCONS", "USO_LADM", "USO_ZHF"])
           .size().rename("CONSTRUCCIONES").reset_index()
           .sort_values("CONSTRUCCIONES", ascending=False))

    salida = Path(salida or RAIZ / "results" / "RURAL" /
                  f"VALIDACION_RURAL_{date.today():%Y%m%d}.xlsx")
    salida.parent.mkdir(parents=True, exist_ok=True)
    leeme = pd.DataFrame({"LEEME": [
        "VALIDACION DE LA ENTREGA RURAL (no cambia la liquidacion)",
        f"Entrega: {reglas.attrs['archivo']}",
        f"Tablas de valor: {Path(ruta_tablas).name}",
        f"Base: {Path(ruta_liq).name}, comunas {COMUNAS_RURALES[0]} a {COMUNAS_RURALES[-1]}: {len(rur):,} construcciones",
        "",
        "- USO_ZHF = 2 ultimos digitos de la ZHF rural de 12 digitos; si no tiene 12 digitos, 'SIN ZHF'.",
        "- El VM2 sale de la columna que asigna la entrega, en la fila de su puntaje (PUNTCONS).",
        "- Anexos (T10) y parqueaderos (T12) van con la misma regla de lo urbano.",
        f"- Vigencia comercial = catastral / {FACTOR_COMERCIAL_RURAL}. Liquidado comercial = valor de la tabla.",
        f"- Columnas asignadas que NO estan en el consolidado: {', '.join(faltan) or 'ninguna'}.",
        "",
        "HOJAS: RESUMEN (como se liquida), POR_TABLA (variacion por columna), SIN_REGLA (lo que queda sin tabla y por que),",
        "REGLAS (la entrega tal como se leyo).",
    ]})
    with pd.ExcelWriter(salida, engine="xlsxwriter") as w:
        leeme.to_excel(w, sheet_name="LEEME", index=False)
        resumen.to_excel(w, sheet_name="RESUMEN", index=False)
        por_tabla.to_excel(w, sheet_name="POR_TABLA", index=False)
        sin.to_excel(w, sheet_name="SIN_REGLA", index=False)
        reglas.drop(columns=["TIPOLOGIA_RURAL"]).to_excel(w, sheet_name="REGLAS", index=False)
        w.sheets["LEEME"].set_column(0, 0, 120)
        for h in ("RESUMEN", "POR_TABLA", "SIN_REGLA", "REGLAS"):
            w.sheets[h].set_column(0, 12, 22)
    print(resumen.to_string(index=False))
    print(f"Columnas que faltan en el consolidado: {faltan or 'ninguna'}")
    print(salida)
    return salida


if __name__ == "__main__":
    # --limpiar: solo arma el insumo limpio desde la entrega mas reciente.
    # Sin argumentos: valida las reglas contra la base (results/RURAL/).
    if "--limpiar" in sys.argv:
        limpiar()
    else:
        validar()
