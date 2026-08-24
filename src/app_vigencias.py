

import io
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
# Las dos fuentes anonimas, una por GRANO.
RUTA_DATOS = RAIZ / "output" / "COMPARACION_VIGENCIA_PUBLICO.parquet"
RUTA_PREDIO = RAIZ / "output" / "COMPARACION_VIGENCIA_PUBLICO_PREDIO.parquet"
RUTA_DETALLE = RAIZ / "output" / "COMPARACION_VIGENCIA_DETALLE.parquet"

# Carpeta de Drive donde se deja el Excel del detalle con identificadores. Es
# la via para verlo desde fuera: el archivo pesa mas de 100 MB -el tope de
# GitHub- y lleva numero predial, asi que no puede ir en el repositorio.
#
# OJO: este enlace queda a la vista de cualquiera que abra la app. Eso solo es
# seguro si la carpeta esta restringida a personas concretas; si estuviera en
# "cualquiera con el enlace", publicarlo aqui equivale a publicar el archivo.
ENLACE_DETALLE_DRIVE = ("https://drive.google.com/drive/folders/"
                        "1Kt-LnURIXhQThsZSS-vogcYtu8uBy5_C")

# Donde cada corrida deja el detalle liquidado.
CARPETA_REPORTE = RAIZ / "results" / "COMPARACION_VIGENCIA"


def _mas_nuevo(patron):
    """El archivo mas nuevo de results/ que case con el patron, o None."""
    if not CARPETA_REPORTE.is_dir():
        return None
    # Se descartan los "~$...": son los bloqueos que deja Excel al abrir un
    # archivo, y entregarlos daria 165 bytes de basura en vez del libro.
    hallados = sorted((f for f in CARPETA_REPORTE.glob(patron)
                       if not f.name.startswith("~$")),
                      key=lambda f: f.stat().st_mtime, reverse=True)
    return hallados[0] if hallados else None


def detalle_liquidado_mas_reciente():
    """El DETALLE_LIQUIDADOS_<fecha>.xlsx mas nuevo, o None si no hay."""
    return _mas_nuevo("DETALLE_LIQUIDADOS*.xlsx")


# Las vigencias salen del modulo que genero el parquet, no escritas a mano.
try:
    from comparacion_vigencia import CONFIG as CONFIG_VIGENCIA
    V_BASE = CONFIG_VIGENCIA["vigencia_base"]
    V_LIQ = CONFIG_VIGENCIA["vigencia_liq"]
except Exception:                                            # pragma: no cover
    V_BASE, V_LIQ = 2026, 2027

# Los mismos seis cortes del reporte y del ejercicio 2025.
PERCENTILES = [10, 25, 50, 75, 90, 100]

# --- Formato de numeros -----------------------------------------------------
LOCALE_VEGA = {"number": {"decimal": ",", "thousands": ".", "grouping": [3],
                          "currency": ["$ ", ""]}}


def pesos(v, decimales: int = 0) -> str:
    """1234567.8 -> '$ 1.234.568'"""
    return "" if v is None or pd.isna(v) else f"$ {_miles(v, decimales)}"


def pct(v, decimales: int = 2, signo: bool = False) -> str:
    """6.9123 -> '6,91 %'  (con signo=True, '+6,91 %')"""
    if v is None or pd.isna(v):
        return ""
    texto = _miles(v, decimales)
    return f"+{texto} %" if signo and v > 0 else f"{texto} %"


def pesos_signo(v, decimales: int = 0) -> str:
    """Una diferencia SIEMPRE con su signo: '+$ 1.234.568' o '-$ 1.234.568'."""
    if v is None or pd.isna(v):
        return ""
    return ("+" if v >= 0 else "-") + pesos(abs(v), decimales)


def entero(v) -> str:
    """206875 -> '206.875'"""
    return "" if v is None or pd.isna(v) else _miles(v, 0)


def _miles(v: float, decimales: int) -> str:
    """Miles con punto y decimales con coma, a la colombiana."""
    return (f"{v:,.{decimales}f}"
            .replace(",", " ").replace(".", ",").replace(" ", "."))

# La misma paleta de los PNG del reporte (VIZ en comparacion_ofertas.py):
# azul = liquidacion, naranja = el valor contra el que se compara.
AZUL, NARANJA = "#2a78d6", "#eb6834"

# Tres medidas por dos bases: el parquet trae las seis combinaciones.
MEDIDAS = {
    "Valor por m²": ("VM2", "Valor por m²", "construccion"),
    "Valor total construido": ("VALORCONS", "Valor total construido", "predio"),
    "Avalúo": ("AVALUO", "Avalúo", "predio"),
}
# Como se llama lo que se esta contando, en singular y plural, segun el grano.
UNIDAD = {"construccion": ("construcción", "construcciones"),
          "predio": ("predio", "predios")}
BASES = {"Catastral": "CATASTRAL", "Comercial": "COMERCIAL"}

SERIES = {
    ("VALORCONS", "CATASTRAL"): {
        "vig": "VALORCONS_CAT_VIGENCIA", "liq": "VALORCONS_CAT_LIQ",
        "var": "VARIACION_VALORCONS_CAT_PCT", "prefijo": "VALORCONS_CAT",
        "dif": "DIF_VALORCONS_CAT"},
    ("VALORCONS", "COMERCIAL"): {
        "vig": "VALORCONS_COM_VIGENCIA", "liq": "VALORCONS_COM_LIQ",
        "var": "VARIACION_VALORCONS_COM_PCT", "prefijo": "VALORCONS_COM",
        "dif": "DIF_VALORCONS_COM"},
    ("VM2", "CATASTRAL"): {
        "vig": "VM2_CAT_VIGENCIA", "liq": "VM2_CAT_LIQ",
        "var": "VARIACION_CAT_PCT", "prefijo": "VM2_CAT",
        "dif": "DIF_CAT_ABS"},
    ("VM2", "COMERCIAL"): {
        "vig": "VM2_COM_VIGENCIA", "liq": "VM2_COM_LIQ",
        "var": "VARIACION_COM_PCT", "prefijo": "VM2_COM",
        "dif": "DIF_COM_ABS"},
    ("AVALUO", "CATASTRAL"): {
        "vig": "AVALUO_CAT_VIGENCIA", "liq": "AVALUO_CAT_LIQ",
        "var": "VARIACION_AVALUO_CAT_PCT", "prefijo": "AVALÚO_CAT",
        "dif": "DIF_AVALUO_CAT"},
    ("AVALUO", "COMERCIAL"): {
        "vig": "AVALUO_COM_VIGENCIA", "liq": "AVALUO_COM_LIQ",
        "var": "VARIACION_AVALUO_COM_PCT", "prefijo": "AVALÚO_COM",
        "dif": "DIF_AVALUO_COM"},
}

# --- Reglas de asignacion de tabla (hoja informativa) -----------------------
GRUPOS_COMUNAS = {
    "7C": ["02", "03", "04", "08", "17", "19", "22"],
    "10C": ["01", "05", "06", "07", "09", "10", "11", "12", "13", "14", "15",
            "16", "18", "20", "21"],
}

# Los tres grupos en que se reparten las 22 comunas.
GRUPOS_FILTRO = {
    "10 comunas": ["01", "07", "09", "10", "11", "12", "14", "15", "20", "21"],
    "7 comunas": ["02", "03", "04", "08", "17", "19", "22"],
    "5 comunas (extra)": ["05", "06", "13", "16", "18"],
}

# comuna -> grupo, para armar la columna con la que se filtra y se abre.
COMUNA_A_GRUPO = {c: g for g, cs in GRUPOS_FILTRO.items() for c in cs}

USOS_T1 = ("Casas (001), Barracas (004), Vivienda_Hasta_3_Pisos (012), "
           "Vivienda_Hasta_3_Pisos_En_PH (013), Jardin_Infantil_en_Casa (063)")
USOS_T2 = "Apartamentos_4_y_mas_pisos (003)"

# (uso, grupo, condicion juridica, patron de la columna).
# {t} donde va la tipologia de la ZHF.
REGLAS_TABLA = [
    (USOS_T1, "10C", "9",
     "T1_RESIDENCIAL_10C_COND_9_{t}"),
    (USOS_T1, "10C", "Diferente de 9", "T1_RESIDENCIAL_10C_COND_0_{t}"),
    (USOS_T1, "7C", "Todas", "T1_RESIDENCIAL_7C_{t}"),
    (USOS_T2, "10C", "Diferente de 8 y 9", "T2_EDIFICIOS_10C_{t}"),
    (USOS_T2, "7C", "Diferente de 8 y 9", "T2_EDIFICIOS_7C_{t}"),
]

TIPOLOGIAS_ZHF = ["011", "012", "013", "014", "015", "016"]


def reglas_asignacion() -> pd.DataFrame:
    """La especificacion desplegada: una fila por regla y tipologia."""
    filas = [{"USO DE CONSTRUCCIÓN": uso,
              "COMUNAS": ", ".join(GRUPOS_COMUNAS[grupo]),
              "CONDICIÓN JURÍDICA": condicion,
              "TIPOLOGÍA ZHF": t,
              "REFERENCIA TABLA": patron.format(t=t)}
             for uso, grupo, condicion, patron in REGLAS_TABLA
             for t in TIPOLOGIAS_ZHF]
    return pd.DataFrame(filas)


# Por que columna se parten el resumen, los percentiles y los graficos.
APERTURAS = {
    "Tabla de valor": "TABLA_ORIGEN",
    "Comuna": "COMUNA",
    "Actividad económica de la ZHF": "ACTIVIDAD_ECONOMICA",
    "Grupo de comunas": "GRUPO_COMUNAS",
    "Tabla y actividad juntas (como en el reporte)": "CLAVE",
}

# El anexo no se esta liquidando: la tabla T10 no esta aprobada, y en
# comparacion_vigencia.py eso es CONFIG["liquidar_anexos"] = False. En los
# predios que tienen anexo su valor entra al avaluo igual en las dos
# vigencias, asi que la variacion del predio sale amortiguada por una parte
# que nadie ha aprobado. Por eso la app arranca dejandolos fuera: lo que
# muestra por defecto es avaluo liquidado de punta a punta.
ANEXOS = {"Sin anexos (lo aprobado)": 0,
          "Todos": None,
          "Solo con anexos": 1}

# Las tablas vienen en pareja: T1_RESIDENCIAL_011 y T1_RESIDENCIAL_011_9. La
# segunda es la que aplica a la condicion 9. Quien usa la app pide verlas por
# separado despues de elegir la categoria, y marcarlas una por una en "Tabla de
# valor" es justo lo que se queria evitar.
VARIANTES = {"Todas": None, "Solo las _9": True, "Sin las _9": False}

# Lo que se lee de cada parquet.
COMUNES = ["COMUNA", "ACTUALIZACION", "TABLA_ORIGEN", "USO_LADM",
           "ACTIVIDAD_ECONOMICA", "CLAVE", "N_CONST_PREDIO", "CON_ANEXO",
           "CONDICION",
           "VALORCONS_CAT_VIGENCIA", "VALORCONS_CAT_LIQ",
           "VARIACION_VALORCONS_CAT_PCT",
           "VALORCONS_COM_VIGENCIA", "VALORCONS_COM_LIQ",
           "VARIACION_VALORCONS_COM_PCT"]

COLUMNAS = COMUNES + [
    "TABLA_VALOR",
    "VM2_CAT_VIGENCIA", "VM2_CAT_LIQ", "VARIACION_CAT_PCT",
    "VM2_COM_VIGENCIA", "VM2_COM_LIQ", "VARIACION_COM_PCT"]

COLUMNAS_PREDIO = COMUNES + [
    "N_TABLAS_PREDIO",
    "AVALUO_CAT_VIGENCIA", "AVALUO_CAT_LIQ", "VARIACION_AVALUO_CAT_PCT",
    "AVALUO_COM_VIGENCIA", "AVALUO_COM_LIQ", "VARIACION_AVALUO_COM_PCT"]


st.set_page_config(page_title=f"Comparación de vigencias {V_BASE} → {V_LIQ}",
                   page_icon="🏙️", layout="wide")

st.markdown(
    """
    <style>
        /* Compacto a proposito: el encabezado y las tarjetas se comian media
           pantalla al abrir, y lo que se viene a ver son las tablas. Todo lo
           de arriba tiene que caber en una franja y dejar el contenido a la
           vista sin desplazarse. */
        .block-container {padding-top: .8rem; padding-bottom: 1.2rem;}
        div[data-testid="stMetric"] {
            background:#ffffff; border:1px solid #e6e9ef; border-radius:9px;
            padding:7px 11px; box-shadow:0 1px 2px rgba(16,24,40,.05);
        }
        div[data-testid="stMetricLabel"] p {
            color:#667085; font-weight:600; font-size:12px;
        }
        div[data-testid="stMetricValue"] {font-size:20px; line-height:1.2;}
        div[data-testid="stMetricDelta"] {font-size:11px;}
        .app-hero {
            background:linear-gradient(120deg,#1e3a8a 0%,#2563eb 55%,#0ea5e9 100%);
            color:#fff; padding:11px 16px; border-radius:10px; margin-bottom:10px;
        }
        .app-hero h1 {margin:0; font-size:18px; font-weight:700;}
        .app-hero p  {margin:2px 0 0; opacity:.88; font-size:12.5px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# DATOS
# =====================================================================
def _a_categoria(d: pd.DataFrame) -> pd.DataFrame:
    """
    Las columnas de texto repetido pasan a category: mismo contenido, menos RAM.

    Son columnas con 2 a 55 valores distintos sobre cientos de miles de filas
    (ACTUALIZACION tiene 2, COMUNA 22), asi que guardar el texto entero en cada
    fila cuesta 120 MB de mas. Con category la app pasa de 197 MB a 82 MB, que
    es lo que decide si cabe o no en el contenedor del despliegue.

    OJO: agrupar por una columna categorica NO se comporta igual en pandas 2 y
    en 3. Por eso los groupby de resumen() y por_grupo() llevan observed=True
    escrito: sin el, en pandas 2 saldrian filas de grupos que el filtro dejo
    fuera.
    """
    for c in d.select_dtypes(include=["object", "string"]).columns:
        if d[c].nunique(dropna=False) <= max(64, len(d) // 1000):
            d[c] = d[c].astype("category")
    return d


@st.cache_data(show_spinner="Leyendo el detalle de la comparación…")
def cargar(ruta: str, marca_tiempo: float, grano: str = "construccion"):
    """Uno de los dos recortes anonimos, con solo las columnas que usa la app."""
    columnas = COLUMNAS_PREDIO if grano == "predio" else COLUMNAS
    try:
        import pyarrow.parquet as pq
        hay = set(pq.ParquetFile(ruta).schema_arrow.names)
        d = pd.read_parquet(ruta, columns=[c for c in columnas if c in hay])
    except ImportError:                                      # pragma: no cover
        d = pd.read_parquet(ruta)
        d = d[[c for c in columnas if c in d.columns]]
    d["COMUNA"] = d["COMUNA"].astype(str).str.strip().str.zfill(2)
    for c in ("TABLA_ORIGEN", "TABLA_VALOR", "USO_LADM",
              "ACTIVIDAD_ECONOMICA", "CLAVE"):
        if c in d.columns:
            d[c] = d[c].astype(str)
    # Grupo de comunas: es con lo que se filtra y se abre, no viene en el parquet.
    d["GRUPO_COMUNAS"] = (d["COMUNA"].map(COMUNA_A_GRUPO)
                          .fillna("sin grupo"))
    return _a_categoria(d)


@st.cache_data(show_spinner="Leyendo el detalle predio a predio…")
def cargar_detalle(ruta: str, marca_tiempo: float) -> pd.DataFrame:
    """El detalle fila a fila, CON identificadores. Solo lo lee la hoja Detalle."""
    d = pd.read_parquet(ruta)
    d["COMUNA"] = d["COMUNA"].astype(str).str.strip().str.zfill(2)
    for c in ("ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID",
              "TABLA_ORIGEN", "TABLA_VALOR", "USO_LADM", "ZHF",
              "ACTIVIDAD_ECONOMICA", "CLAVE", "SENTIDO", "RANGO_VARIACION"):
        if c in d.columns:
            d[c] = d[c].astype(str)
    d["GRUPO_COMUNAS"] = d["COMUNA"].map(COMUNA_A_GRUPO).fillna("sin grupo")
    # El detalle guarda VANEXO -el valor- y no la marca; se deriva aqui para
    # que el filtro de la barra lateral valga tambien en el explorador.
    if "CON_ANEXO" not in d.columns and "VANEXO" in d.columns:
        d["CON_ANEXO"] = (pd.to_numeric(d["VANEXO"], errors="coerce")
                          .fillna(0) > 0).astype(int)
    # ID_PREDIO y el numero predial son unicos por fila: _a_categoria los deja
    # como estan y solo convierte las columnas que de verdad se repiten.
    return _a_categoria(d)


# Las columnas del detalle que se muestran en la vista corta.
COLUMNAS_DETALLE_FIJAS = [
    "ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "COMUNA",
    "GRUPO_COMUNAS", "ESTRPRED", "USO_LADM", "CONDICION", "TABLA_ORIGEN",
    "TABLA_VALOR", "ZHF", "ACTIVIDAD_ECONOMICA", "PUNTCONS", "AREA_CONST",
]

# Que es cada columna del detalle.
try:
    from comparacion_vigencia import DICCIONARIO_DETALLE
except Exception:                                        # pragma: no cover
    DICCIONARIO_DETALLE = []


if not os.path.exists(RUTA_DATOS):
    st.error(
        f"No se encontró **{RUTA_DATOS.name}**.\n\n"
        "Corra primero `python src/comparacion_vigencia.py`, que es quien lo "
        "escribe en `output/`."
    )
    st.stop()

df_construccion = cargar(str(RUTA_DATOS), os.path.getmtime(RUTA_DATOS),
                         "construccion")
df_predio = (cargar(str(RUTA_PREDIO), os.path.getmtime(RUTA_PREDIO), "predio")
             if os.path.exists(RUTA_PREDIO) else None)


# =====================================================================
# FILTROS (uno solo para todas las hojas)
# =====================================================================
# El sidebar va antes del encabezado: la medida decide de que parquet se lee.
with st.sidebar:
    st.header("⚙️ Filtros")
    st.caption("Se aplican a todas las hojas. Vacío = todo.")

    etiqueta_medida = st.radio(
        "Medida", list(MEDIDAS), index=0,
        help="El valor por m² es de cada CONSTRUCCIÓN; el valor construido "
             "total y el avalúo son del PREDIO completo, sumando sus "
             "construcciones. Por eso al cambiar de medida cambia el conteo.")
    etiqueta_base = st.radio(
        "Base de valor", list(BASES), index=0, horizontal=True,
        help="Catastral es lo que se cobra. Comercial es lo que se estima que "
             "vale: el catastral de la vigencia dividido por 0,7 en las comunas "
             "actualizadas en 2024-2025 y por 0,6 en las demás.")
    clave_medida, titulo_medida, grano = MEDIDAS[etiqueta_medida]
    medida = SERIES[(clave_medida, BASES[etiqueta_base])]
    unidad_eje = f"{titulo_medida} {etiqueta_base.lower()} (millones de pesos)"
    unidad, unidades = UNIDAD[grano]
    # Los conteos se llaman como lo que cuentan: PREDIOS o CONSTRUCCIONES.
    COL_N = unidades.upper()
    COL_NUM = f"NUM_{COL_N}"

    # De aqui en adelante 'df' es el parquet del grano que corresponda, y todo
    # lo demas -filtros, tablas, graficos- trabaja sobre el sin enterarse.
    if grano == "predio" and df_predio is None:
        st.error(f"Falta {RUTA_PREDIO.name}, que es de donde salen el valor "
                 f"construido total y el avalúo. Corra "
                 f"`python src/comparacion_vigencia.py`.")
        st.stop()
    df = df_predio if grano == "predio" else df_construccion

    familias = sorted({t.split("_")[0] + "_" + t.split("_")[1]
                       for t in df["TABLA_ORIGEN"].unique() if "_" in t})
    sel_familia = st.multiselect("Categoría de tabla", familias)

    sel_variante = st.radio(
        "Variante de la tabla", list(VARIANTES), index=0, horizontal=True,
        help="Cada tabla tiene su pareja terminada en _9, la que aplica a la "
             "condición 9. Esto las separa de una vez, sin marcarlas una por "
             "una: recorta lo que se ofrece abajo en «Tabla de valor» y "
             "también lo que entra al reporte.")

    # Las tablas que se ofrecen dependen de la familia elegida, para no dar a
    # escoger entre 40 codigos cuando ya se acoto a residencial.
    de_la_familia = (df["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))
                     if sel_familia else slice(None))
    tablas = sorted(df.loc[de_la_familia, "TABLA_ORIGEN"].unique())
    # Y la variante recorta esa misma lista, que es lo que se pidio al usarla.
    if VARIANTES[sel_variante] is not None:
        tablas = [x for x in tablas
                  if str(x).endswith("_9") == VARIANTES[sel_variante]]
    sel_tabla = st.multiselect("Tabla de valor", tablas)

    sel_comuna = st.multiselect("Comuna", sorted(df["COMUNA"].unique()))
    sel_actividad = st.multiselect("Actividad económica de la ZHF",
                                   sorted(df["ACTIVIDAD_ECONOMICA"].unique()))
    sel_grupo = st.multiselect(
        "Grupo de comunas", list(GRUPOS_FILTRO),
        help="Qué comunas trae cada grupo está en la hoja Reglas.")

    # Cuantas construcciones tiene el predio. El numero es siempre del predio
    # completo, pero se lee distinto segun la medida: con el valor por m2 un
    # predio de tres construcciones aporta tres filas, y con el avaluo aporta
    # una sola. Por eso al elegir "3 construcciones" el conteo de arriba cambia
    # al cambiar de medida aunque los predios sean los mismos.
    if "N_CONST_PREDIO" in df.columns:
        conteos = sorted(int(v) for v in df["N_CONST_PREDIO"].dropna().unique())
        sel_n_const = st.multiselect(
            "Construcciones del predio", conteos,
            format_func=lambda n: ("1 construcción" if n == 1
                                   else f"{n} construcciones"),
            help="Deja solo los predios que tengan exactamente ese número de "
                 "construcciones; se puede marcar más de uno. El número lo "
                 "trae N_CONST_PREDIO y cuenta las construcciones del predio "
                 "sin anexos, que en 231 predios es una más de las que "
                 "aparecen valoradas en el detalle.")
    else:
        sel_n_const = []
        st.caption("Para filtrar por número de construcciones hace falta "
                   "volver a correr `comparacion_vigencia.py`: el parquet de "
                   "esta medida todavía no trae N_CONST_PREDIO.")

    if "CON_ANEXO" in df.columns:
        sel_anexo = st.radio(
            "Anexos del predio", list(ANEXOS), index=0,
            help="La tabla T10, la del anexo, no está aprobada: el anexo no se "
                 "liquida y su valor entra al avalúo igual en las dos "
                 "vigencias. En un predio con anexo, entonces, parte del "
                 "avalúo no está liquidada y la variación sale amortiguada. "
                 "Por eso la app arranca en «Sin anexos». Los otros dos "
                 "valores están para mirar el efecto, no para reportar.")
    else:
        sel_anexo = "Todos"
        st.caption("Para separar los predios con anexo hace falta volver a "
                   "correr `comparacion_vigencia.py`: el parquet de esta "
                   "medida todavía no trae CON_ANEXO.")

    st.divider()
    etiqueta_apertura = st.selectbox(
        "Separar los resultados por", list(APERTURAS), index=0,
        help="Con lo que se elija aquí se parten las tablas y los gráficos: "
             "una fila del resumen y un gráfico por cada valor de esa "
             "columna. Con «Comuna», por ejemplo, sale una fila y un gráfico "
             "por cada comuna.")
    col_apertura = APERTURAS[etiqueta_apertura]
    min_predios = st.number_input(
        f"Mínimo de {unidades} por grupo", 1, 5000, 5,
        help=f"Los grupos con menos {unidades} de los que se pidan aquí no se "
             f"muestran: con tan pocos casos una mediana no dice nada.")

def filtrar(d: pd.DataFrame) -> pd.DataFrame:
    """Los filtros de la barra lateral, aplicados a lo que se le pase."""
    if sel_familia:
        d = d[d["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))]
    if sel_tabla:
        d = d[d["TABLA_ORIGEN"].isin(sel_tabla)]
    if VARIANTES[sel_variante] is not None:
        con_9 = d["TABLA_ORIGEN"].astype(str).str.endswith("_9")
        d = d[con_9] if VARIANTES[sel_variante] else d[~con_9]
    if sel_comuna:
        d = d[d["COMUNA"].isin(sel_comuna)]
    if sel_actividad:
        d = d[d["ACTIVIDAD_ECONOMICA"].isin(sel_actividad)]
    if sel_grupo:
        d = d[d["GRUPO_COMUNAS"].isin(sel_grupo)]
    if sel_n_const and "N_CONST_PREDIO" in d.columns:
        d = d[d["N_CONST_PREDIO"].isin(sel_n_const)]
    if ANEXOS[sel_anexo] is not None and "CON_ANEXO" in d.columns:
        d = d[d["CON_ANEXO"] == ANEXOS[sel_anexo]]
    # La medida de avaluo puede venir vacia si se corrio la comparacion sin las
    # columnas de terreno; mejor decirlo que mostrar una hoja en blanco.
    return d[d[medida["vig"]].notna() & d[medida["liq"]].notna()]


# Que se esta haciendo con el anexo, dicho en el encabezado. Sin esto el
# conteo de arriba se lee como si fuera todo lo que hay, y con el filtro en
# "Sin anexos" -que es como arranca- no lo es.
NOTA_ANEXO = {
    0: "Deja fuera los predios con anexo: la T10 no está aprobada, así que "
       "su avalúo llevaría una parte sin liquidar.",
    1: "Solo predios con anexo, cuyo avalúo lleva una parte sin liquidar: la "
       "T10 no está aprobada.",
    None: "Incluye los predios con anexo, cuyo avalúo lleva una parte sin "
          "liquidar: la T10 no está aprobada.",
}[ANEXOS[sel_anexo]]

st.markdown(
    f"""
    <div class="app-hero">
        <h1>🏙️ Comparación de vigencias · {V_BASE} → {V_LIQ}</h1>
        <p>La liquidación ({V_LIQ}) contra lo que cobra hoy la base
        ({V_BASE}) · <b>{entero(len(df))} {unidades}</b> ·
        {titulo_medida.lower()}, base {etiqueta_base.lower()}. Solo predios con
        todas sus construcciones valoradas por tabla en las dos vigencias.
        {NOTA_ANEXO}</p>
    </div>
    """,
    unsafe_allow_html=True,
)

dff = filtrar(df)

if dff.empty:
    st.warning(f"Ningún {unidad} cumple los filtros elegidos. Quite alguno en "
               f"la barra lateral.")
    st.stop()

c_base, c_liq, c_var = (f"{medida['prefijo']}_VIG_{V_BASE}",
                        f"{medida['prefijo']}_VIG_{V_LIQ}",
                        f"VARIACIÓN_{medida['prefijo']}_{V_LIQ}_vs_{V_BASE}")
# La diferencia absoluta -en pesos- entre las dos vigencias.
c_dif = f"DIFERENCIA_{medida['prefijo']}_{V_LIQ}_vs_{V_BASE}"

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric(unidades.capitalize(), entero(len(dff)),
          f"{pct(len(dff) / len(df) * 100, 1)} del total")
k2.metric(f"Mediana vigencia {V_BASE}", pesos(dff[medida["vig"]].median()))
k3.metric(f"Mediana vigencia {V_LIQ}", pesos(dff[medida["liq"]].median()))
k4.metric("Variación mediana", pct(dff[medida["var"]].median(), 2, signo=True))
k5.metric("Bajan", pct((dff[medida["var"]] < 0).mean() * 100, 1))


# =====================================================================
# CALCULOS (los mismos que arma comparacion_vigencia.py)
# =====================================================================
def percentiles(s: pd.DataFrame) -> pd.DataFrame:
    """Los seis cortes de un grupo, con las dos series y su variacion."""
    v = pd.to_numeric(s[medida["vig"]], errors="coerce").dropna()
    l = pd.to_numeric(s[medida["liq"]], errors="coerce").dropna()
    if v.empty or l.empty:
        return pd.DataFrame()
    filas = []
    for p in PERCENTILES:
        pv, pl = float(v.quantile(p / 100)), float(l.quantile(p / 100))
        filas.append({"PERCENTIL": f"{p}%",
                      COL_NUM: int(round(p / 100 * len(s))),
                      c_base: pv, c_liq: pl,
                      c_dif: pl - pv,
                      c_var: (pl / pv - 1) if pv else None})
    return pd.DataFrame(filas)


def por_grupo(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """Los percentiles de cada grupo, uno debajo de otro y en una sola tabla."""
    salida = []
    for clave, s in d.groupby(col, sort=True, observed=True):
        if len(s) < min_predios:
            continue
        t = percentiles(s)
        if t.empty:
            continue
        t.insert(0, etiqueta_apertura, str(clave))
        salida.append(t)
    return pd.concat(salida, ignore_index=True) if salida else pd.DataFrame()


def con_formato(t: pd.DataFrame):
    """La tabla lista para mostrar. Devuelve un Styler: la columna sigue siendo numerica y se puede ordenar."""
    reglas = {}
    for col in t.columns:
        if col == c_dif:                         # pesos, con signo
            reglas[col] = pesos_signo
        elif col in (c_base, c_liq):
            reglas[col] = pesos
        elif col == c_var:                       # fraccion, con signo
            reglas[col] = lambda v: pct(v * 100 if pd.notna(v) else v, 2,
                                        signo=True)
        elif col == "VAR_MEDIANA_%":             # puntos, con signo
            reglas[col] = lambda v: pct(v, 2, signo=True)
        elif col.endswith("_%"):                 # BAJAN_% y SUBEN_% son
            reglas[col] = lambda v: pct(v, 2)    # proporciones, no variaciones
        elif col in (COL_N, COL_NUM, "NUM_PREDIOS", "PREDIOS",
                     "N_CONST_PREDIO", "N_TABLAS_PREDIO"):
            reglas[col] = entero
    return t.style.format(reglas)


def resumen(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """Una fila por grupo: cuantos predios, las dos medianas y como se mueve."""
    g = d.groupby(col, sort=True, observed=True)
    t = pd.DataFrame({
        COL_N: g.size(),
        c_base: g[medida["vig"]].median(),
        c_liq: g[medida["liq"]].median(),
        "VAR_MEDIANA_%": g[medida["var"]].median(),
        "BAJAN_%": g[medida["var"]].apply(lambda s: (s < 0).mean() * 100),
        "SUBEN_%": g[medida["var"]].apply(lambda s: (s > 0).mean() * 100),
    })
    t = t[t[COL_N] >= min_predios]
    if t.empty:
        return pd.DataFrame()

    grupos_ok = list(t.index)                    # antes de perder el indice
    t.insert(3, c_dif, t[c_liq] - t[c_base])     # queda detras de las dos medianas
    t = t.reset_index().rename(columns={col: etiqueta_apertura})

    # La fila TOTAL va sobre los mismos grupos; las medianas se recalculan.
    sub = d[d[col].isin(grupos_ok)]
    fila = {etiqueta_apertura: "TOTAL",
            COL_N: len(sub),
            c_base: sub[medida["vig"]].median(),
            c_liq: sub[medida["liq"]].median(),
            "VAR_MEDIANA_%": sub[medida["var"]].median(),
            "BAJAN_%": (sub[medida["var"]] < 0).mean() * 100,
            "SUBEN_%": (sub[medida["var"]] > 0).mean() * 100}
    fila[c_dif] = fila[c_liq] - fila[c_base]
    return pd.concat([t, pd.DataFrame([fila])[t.columns]], ignore_index=True)


hoja_tablas, hoja_graf, hoja_detalle, hoja_reglas = st.tabs(
    ["📊 Tablas", "📈 Gráficos", "🔎 Detalle",
     "📋 Reglas"])

# Todo se arma una sola vez aca arriba: las tres hojas y el Excel leen de estos
# mismos objetos, asi no hay dos sitios calculando lo mismo y desviandose.
res = resumen(dff, col_apertura)
total = percentiles(dff)
abierto = por_grupo(dff, col_apertura)
reglas = reglas_asignacion()

# El reparto de la variacion.
# en el rango de su propia variacion, no se comparan distribuciones.
RANGOS = ["Baja más de 50%", "Baja 25-50%", "Baja 10-25%", "Estable (±10%)",
          "Sube 10-25%", "Sube 25-50%", "Sube más de 50%"]
reparto = (dff[medida["var"]]
           .pipe(pd.cut,
                 bins=[-float("inf"), -50, -25, -10, 10, 25, 50, float("inf")],
                 labels=RANGOS)
           .value_counts(sort=False)
           .rename_axis("RANGO").reset_index(name=COL_N))
reparto["%"] = reparto[COL_N] / reparto[COL_N].sum() * 100


def _motor_excel():
    """El primer motor de Excel que este instalado, o None si no hay ninguno."""
    for modulo in ("xlsxwriter", "openpyxl"):
        try:
            __import__(modulo)
            return modulo
        except ImportError:
            continue
    return None


MOTOR_EXCEL = _motor_excel()


def excel_predios(d: pd.DataFrame) -> bytes:
    """El detalle fila a fila a Excel, para revisar casos a mano."""
    d = d.copy()
    for c in d.columns:
        if isinstance(d[c].dtype, pd.CategoricalDtype):
            d[c] = d[c].astype(str)

    # Mismas dos columnas y mismo orden que la hoja Detalle, igual que en el
    # Excel que arma comparacion_vigencia.py.
    desc = {c: q for c, q, _ in DICCIONARIO_DETALLE}
    dic = pd.DataFrame([(c, desc.get(c, "")) for c in d.columns],
                       columns=["VARIABLE", "DESCRIPCIÓN"])

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine=MOTOR_EXCEL) as xw:
        libro = xw.book if MOTOR_EXCEL == "xlsxwriter" else None
        if libro is not None:
            f_tit = libro.add_format({"bold": True, "bg_color": "#1F4E78",
                                      "font_color": "white", "border": 1,
                                      "align": "center", "valign": "vcenter",
                                      "text_wrap": True})
            f_pesos = libro.add_format({"num_format": "$ #,##0"})
            f_pct = libro.add_format({"num_format": "0.00"})
            f_ent = libro.add_format({"num_format": "#,##0"})
            f_texto = libro.add_format({"text_wrap": True, "valign": "top"})

        for nombre, t in (("Detalle", d), ("Diccionario", dic)):
            if t.empty:
                continue
            t.to_excel(xw, sheet_name=nombre, index=False)
            if libro is None:
                continue
            h = xw.sheets[nombre]
            h.freeze_panes(1, 2 if nombre == "Detalle" else 0)
            h.autofilter(0, 0, len(t), len(t.columns) - 1)
            for i, col in enumerate(t.columns):
                h.write(0, i, str(col), f_tit)
                nom = str(col)
                if nombre == "Diccionario":
                    fmt, ancho = f_texto, (34 if i == 0 else 72)
                elif nom.startswith(("VM2", "VALORCONS", "AVALUO", "AVALPRED",
                                     "VTER", "VANEXO", "DIF_")):
                    fmt, ancho = f_pesos, 20
                elif nom.startswith("VARIACION") or nom.endswith("_PCT"):
                    fmt, ancho = f_pct, 16
                elif nom in ("PUNTCONS", "ACONCONS", "AREA_CONST", "ESTRPRED",
                             "CONDICION", "N_CONST_PREDIO"):
                    fmt, ancho = f_ent, 14
                else:
                    largo = int(t[col].astype(str).str.len().head(500).max() or 12)
                    fmt, ancho = None, min(max(14, largo + 3, len(nom) + 3), 40)
                h.set_column(i, i, ancho, fmt)
    return buf.getvalue()


# ---------------------------------------------------------------------
# HOJA 1 - TABLAS
# ---------------------------------------------------------------------
with hoja_tablas:
    st.subheader(f"Tablas · {etiqueta_medida} · base {etiqueta_base.lower()}")

    # Sin boton de descarga aqui: la unica esta en la hoja Detalle.

    st.markdown(f"**Resumen por {etiqueta_apertura.lower()}**")
    st.caption(
        f"Comparación de la mediana de los valores de cada grupo entre las vigencias "
        f"{V_BASE} y {V_LIQ}."
    )
    if res.empty:
        st.info(f"Ningún grupo llega a {min_predios} {unidades} con estos filtros.")
    else:
        # column_config SIN 'format': el formato lo pone el Styler y aquel le ganaria.
        st.dataframe(
            con_formato(res), width="stretch", hide_index=True,
            column_config={
                COL_N: st.column_config.Column(
                    help=f"{unidades.capitalize()} del grupo que entran a la "
                         f"comparación."),
                c_base: st.column_config.Column(
                    help=f"Valor mediano del grupo en la vigencia {V_BASE}: la "
                         f"mitad de los predios está por debajo."),
                c_liq: st.column_config.Column(
                    help=f"Valor mediano del grupo con la liquidación "
                         f"({V_LIQ}), calculado igual."),
                c_dif: st.column_config.Column(
                    help="La mediana de {} menos la de {}. Compara las dos "
                         "distribuciones, no predio contra predio: el predio "
                         "que queda en el medio en una vigencia no tiene por "
                         "qué ser el mismo de la otra.".format(V_LIQ, V_BASE)),
                "VAR_MEDIANA_%": st.column_config.Column(
                    help="La mediana de las variaciones, y esta SÍ es predio "
                         "contra sí mismo. Por eso no coincide con la "
                         "diferencia dividida entre el valor base: son dos "
                         "cuentas distintas, no un error."),
                "BAJAN_%": st.column_config.Column(
                    help="Qué proporción del grupo baja de una vigencia a otra."),
                "SUBEN_%": st.column_config.Column(
                    help="Qué proporción del grupo sube de una vigencia a otra."),
            })

    st.divider()
    st.markdown("**Percentiles, diferencia y variación** · "
                f"{entero(len(dff))} {unidades}")
    st.caption(f"En cada corte: cuánto vale en la vigencia {V_BASE}, cuánto "
               f"valdría en la {V_LIQ}, cuántos pesos de diferencia hay entre "
               f"los dos y qué proporción representa esa diferencia.")
    st.dataframe(con_formato(total), width="stretch", hide_index=True)



# ---------------------------------------------------------------------
# HOJA 3 - GRAFICOS
# ---------------------------------------------------------------------
with hoja_graf:
    st.subheader(f"Gráficos · {etiqueta_medida} · base {etiqueta_base.lower()}")

    def pie(t: pd.DataFrame) -> list:
        """Bajo el titulo va SOLO el conteo: es corto y nunca se corta."""
        if t.empty:
            return []
        return [f"{entero(int(t[COL_NUM].iloc[-1]))} {unidades} comparadas"
                if grano == "construccion" else
                f"{entero(int(t[COL_NUM].iloc[-1]))} {unidades} comparados"]

    def frase(t: pd.DataFrame) -> str:
        """La lectura del grafico en una frase, para el caption de DEBAJO."""
        fila = t[t["PERCENTIL"] == "50%"] if not t.empty else t
        if fila.empty or pd.isna(fila[c_var].iloc[0]):
            return ""
        pv, pl = float(fila[c_base].iloc[0]), float(fila[c_liq].iloc[0])
        var = float(fila[c_var].iloc[0]) * 100
        return (f"En el medio de la distribución (percentil 50) el valor "
                f"{'sube' if pl >= pv else 'baja'} de **{pesos(pv)}** en "
                f"{V_BASE} a **{pesos(pl)}** en {V_LIQ}. La diferencia es de "
                f"**{pesos_signo(pl - pv)}**, que sobre el valor de {V_BASE} "
                f"equivale a **{pct(var, 1, signo=True)}**.")

    def curvas(t: pd.DataFrame, titulo: str) -> alt.Chart:
        """Las dos curvas de percentiles, en millones y con los colores del reporte."""
        largo = t.melt(id_vars="PERCENTIL", value_vars=[c_base, c_liq],
                       var_name="Serie", value_name="Valor")
        largo["Millones"] = largo["Valor"] / 1e6
        largo["Etiqueta"] = largo["Valor"].map(pesos)
        ref = t.set_index("PERCENTIL")
        largo["Diferencia"] = largo["PERCENTIL"].map(
            ref[c_dif].map(pesos_signo))
        largo["Variacion"] = largo["PERCENTIL"].map(
            ref[c_var].map(lambda v: pct(v * 100, 1, signo=True)
                           if pd.notna(v) else ""))
        return (
            alt.Chart(largo,
                      title=alt.TitleParams(text=titulo, subtitle=pie(t),
                                            subtitleColor="#667085",
                                            anchor="start"))
            .mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=2.5)
            .encode(
                # labelAngle=0: los rotulos del eje x van en horizontal.
                x=alt.X("PERCENTIL:N", title="Percentil",
                        sort=[f"{p}%" for p in PERCENTILES],
                        axis=alt.Axis(labelAngle=0)),
                y=alt.Y("Millones:Q", title=unidad_eje),
                color=alt.Color("Serie:N", title=None,
                                scale=alt.Scale(domain=[c_base, c_liq],
                                                range=[NARANJA, AZUL]),
                                legend=alt.Legend(orient="top")),
                tooltip=[alt.Tooltip("PERCENTIL:N", title="Percentil"),
                         alt.Tooltip("Serie:N", title="Serie"),
                         alt.Tooltip("Etiqueta:N", title="Valor"),
                         alt.Tooltip("Diferencia:N",
                                     title=f"Diferencia {V_LIQ} vs {V_BASE}"),
                         alt.Tooltip("Variacion:N", title="Variación")],
            )
            .properties(height=340)
            .configure(locale=LOCALE_VEGA)      # ejes en formato colombiano
        )

    st.altair_chart(curvas(total, "Total de la selección"), width="stretch")
    st.caption(frase(total))

    st.divider()
    st.markdown(f"**Por {etiqueta_apertura.lower()}**")
    if abierto.empty:
        st.info(f"Ningún grupo llega a {min_predios} {unidades} con estos filtros.")
    else:
        grupos = list(abierto[etiqueta_apertura].unique())
        # Con muchos grupos la grilla se vuelve ilegible; se muestran de a pocos
        # y el usuario elige cuales, que es justo lo que en el Excel no se puede.
        elegidos = st.multiselect(f"{etiqueta_apertura} a dibujar", grupos,
                                  default=grupos[:6])
        columnas_grilla = st.radio("Gráficos por fila", [1, 2, 3], index=1,
                                   horizontal=True)
        for i in range(0, len(elegidos), columnas_grilla):
            for col, nombre in zip(st.columns(columnas_grilla),
                                   elegidos[i:i + columnas_grilla]):
                t = abierto[abierto[etiqueta_apertura] == nombre]
                col.altair_chart(curvas(t, nombre), width="stretch")
                col.caption(frase(t))

    st.divider()
    st.markdown(f"**Distribución de {unidades} según variación porcentual**")
    st.caption("Muestra cómo se distribuyen los predios según la variación porcentual de su valor entre las vigencias 2026 y 2027, comparando cada predio consigo mismo.")
    st.altair_chart(
        alt.Chart(reparto).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
            x=alt.X("RANGO:N", title=None, sort=list(reparto["RANGO"]),
                    axis=alt.Axis(labelAngle=0)),   # rotulos en horizontal
            y=alt.Y(f"{COL_N}:Q", title=unidades.capitalize()),
            tooltip=[alt.Tooltip("RANGO:N", title="Rango"),
                     alt.Tooltip(f"{COL_N}:Q", title=unidades.capitalize(),
                                 format=",.0f"),
                     alt.Tooltip("%:Q", title="% del total", format=",.1f")],
        ).properties(height=300).configure(locale=LOCALE_VEGA),
        width="stretch")



# ---------------------------------------------------------------------
# HOJA 3 - DETALLE DE LA LIQUIDACION
# ---------------------------------------------------------------------
# El libro del reporte y el explorador fila a fila son cosas distintas.
with hoja_detalle:
    st.subheader("Detalle de la liquidación")

    st.link_button("📂 Detalle liquidación · Excel completo (Drive)",
                   ENLACE_DETALLE_DRIVE, type="primary")
    st.caption(
        "Una fila por construcción con todo: ID_PREDIO, número predial, ZHF, "
        "puntaje, área, la columna exacta de la tabla de donde salió el valor "
        "y el avalúo del predio. Se abre desde cualquier parte, con la cuenta "
        "que tenga acceso a la carpeta.")
    st.divider()

    @st.cache_data(show_spinner="Leyendo el libro…")
    def leer_archivo(ruta: str, marca_tiempo: float) -> bytes:
        """El archivo tal cual esta en disco, sin tocarle nada."""
        with open(ruta, "rb") as f:
            return f.read()

    # Solo el archivo que dejo la corrida. En el deploy no esta, y para eso
    # queda el enlace de Drive de arriba.
    detalle = detalle_liquidado_mas_reciente()
    if detalle is not None:
        st.download_button(
            "📗 Detalle liquidación",
            data=leer_archivo(str(detalle), detalle.stat().st_mtime),
            file_name=detalle.name,
            mime=("application/vnd.openxmlformats-officedocument"
                  ".spreadsheetml.sheet"),
            type="primary", key="dl_detalle_liq",
            help="Una fila por construcción, con el VM2 de las dos vigencias, "
                 "la tabla y la columna exacta de donde salió el valor, y el "
                 "avalúo del predio. Trae además una hoja Diccionario.")
        st.caption(
            f"`{detalle.name}` · "
            f"{_miles(detalle.stat().st_size / 1e6, 1)} MB · generado el "
            f"{pd.Timestamp(detalle.stat().st_mtime, unit='s'):%Y-%m-%d %H:%M}"
            f". Es el detalle completo de la corrida: no responde a los "
            f"filtros de la izquierda.")

    st.divider()
    if os.path.exists(RUTA_DETALLE):
        st.markdown("**Explorador predio a predio**")
        det = cargar_detalle(str(RUTA_DETALLE), os.path.getmtime(RUTA_DETALLE))
        detf = filtrar(det)

        st.caption("Esto SÍ trae identificadores: ID_PREDIO y número predial. "
                   "Responde a los mismos filtros de la barra lateral que las "
                   "demás hojas, más los de aquí abajo.")

        f1, f2, f3 = st.columns([2, 1, 1])
        busca = f1.text_input(
            "Buscar por ID_PREDIO o número predial",
            placeholder="uno o varios, separados por espacio o coma",
            help="Coincidencia exacta en cualquiera de las dos columnas. Pasa "
                 "por encima de los filtros de la barra lateral para que un "
                 "predio concreto siempre aparezca.")
        rangos_disp = (sorted(detf["RANGO_VARIACION"].dropna().unique())
                       if "RANGO_VARIACION" in detf.columns else [])
        sel_rango = f2.multiselect("Rango de variación", rangos_disp)
        solo_fuera = f3.checkbox(
            "Solo fuera de tolerancia", value=False,
            help="La marca FUERA_TOLERANCIA de comparacion_vigencia.py.",
            disabled="FUERA_TOLERANCIA" not in detf.columns)

        if busca.strip():
            claves = {t.strip() for t in busca.replace(",", " ").split()
                      if t.strip()}
            detf = det[det["ID_PREDIO"].isin(claves)
                       | det["NUMERO_PREDIAL_NACIONAL"].isin(claves)]
            st.caption(f"Búsqueda directa sobre el detalle completo: "
                       f"{entero(len(detf))} filas para "
                       f"{entero(len(claves))} clave(s). Los filtros de la "
                       f"barra lateral no se aplican.")
        else:
            if sel_rango:
                detf = detf[detf["RANGO_VARIACION"].isin(sel_rango)]
            if solo_fuera and "FUERA_TOLERANCIA" in detf.columns:
                detf = detf[detf["FUERA_TOLERANCIA"].astype(str)
                            .isin(["1", "True", "true", "SI", "SÍ"])]

        if detf.empty:
            st.warning("Ninguna construcción cumple lo pedido.")
        else:
            # Columnas: las fijas mas las cuatro de la medida elegida.
            cols_medida = [c for c in (medida["vig"], medida["liq"],
                                       medida.get("dif"), medida["var"])
                           if c and c in detf.columns]
            cortas = ([c for c in COLUMNAS_DETALLE_FIJAS if c in detf.columns]
                      + cols_medida)

            c1, c2 = st.columns([1, 1])
            vista = c1.radio(
                "Columnas", ["Las de la medida elegida", "Todas"],
                horizontal=True,
                help=f"La vista corta deja los identificadores y las cuatro "
                     f"columnas de {etiqueta_medida.lower()} "
                     f"{etiqueta_base.lower()}. La completa trae las "
                     f"{len(detf.columns)} del archivo.")
            n_ver = c2.number_input(
                "Filas en pantalla", 50, 5000, 300, step=50,
                help="Solo cuántas se dibujan aquí. La descarga no depende "
                     "de esto.")

            cols = cortas if vista.startswith("Las") else list(detf.columns)
            st.caption(f"**{entero(len(detf))} construcciones** cumplen la "
                       f"selección · se muestran las primeras {entero(n_ver)}")
            st.dataframe(con_formato(detf[cols].head(int(n_ver))),
                         width="stretch", hide_index=True)

            st.divider()
            st.markdown("**Bajar esta selección**")

            # NADA se arma antes de que lo pidan.
            g1, g2 = st.columns([1, 1])
            formato = g1.radio("Formato", ["Excel", "CSV"], horizontal=True,
                               help="El Excel va a unas 1.500 filas por "
                                    "segundo y trae la hoja Diccionario. El "
                                    "CSV no tiene tope y es mucho más rápido.")
            tope = g2.number_input(
                "Filas al Excel", 500, 50000, 5000, step=500,
                disabled=formato != "Excel",
                help="5.000 filas tardan ~4 s; 50.000, cerca de medio minuto.")

            recorte = detf.head(int(tope)) if formato == "Excel" else detf
            if formato == "Excel" and len(detf) > len(recorte):
                st.warning(f"El Excel llevará {entero(len(recorte))} de las "
                           f"{entero(len(detf))} filas. Para llevarlas todas, "
                           f"use el CSV o afine los filtros.")

            firma = (medida["prefijo"], tuple(sel_familia), tuple(sel_tabla),
                     tuple(sel_comuna), tuple(sel_actividad), tuple(sel_grupo),
                     busca.strip(), tuple(sel_rango), bool(solo_fuera),
                     formato, int(tope), len(detf))

            if st.button(f"🧾 Preparar el {formato}", type="secondary",
                         disabled=formato == "Excel" and not MOTOR_EXCEL,
                         help=None if MOTOR_EXCEL else
                         "Este entorno no tiene xlsxwriter instalado."):
                with st.spinner(f"Armando el {formato} "
                                f"({entero(len(recorte))} filas)…"):
                    st.session_state["descarga"] = {
                        "firma": firma,
                        "n": len(recorte),
                        "datos": (excel_predios(recorte) if formato == "Excel"
                                  else recorte.to_csv(index=False)
                                              .encode("utf-8-sig")),
                        "nombre": (f"DETALLE_PREDIOS_{V_BASE}_{V_LIQ}"
                                   f".{'xlsx' if formato == 'Excel' else 'csv'}"),
                        "mime": ("application/vnd.openxmlformats-officedocument"
                                 ".spreadsheetml.sheet" if formato == "Excel"
                                 else "text/csv")}

            listo = st.session_state.get("descarga")
            if listo and listo["firma"] == firma:
                st.download_button(
                    f"⬇️ Descargar {listo['nombre']} "
                    f"({entero(listo['n'])} filas · "
                    f"{_miles(len(listo['datos']) / 1e6, 1)} MB)",
                    data=listo["datos"], file_name=listo["nombre"],
                    mime=listo["mime"], type="primary", key="dl_predios")
            elif listo:
                st.caption("Cambió la selección: vuelva a preparar la "
                           "descarga para no bajar lo de antes.")



# ---------------------------------------------------------------------
# HOJA 3 - REGLAS
# ---------------------------------------------------------------------
with hoja_reglas:
    st.subheader("Cómo se asigna la tabla de valor")


    st.dataframe(reglas, width="stretch", hide_index=True,
                 column_config={"COMUNAS": st.column_config.TextColumn(
                     width="medium")})
    st.caption( "Se identifica el uso de la construcción, la condición jurídica, la tipología y la ZHF. " "Con esta información se determina la tabla de valor correspondiente a la comuna y se " "selecciona la columna asociada en el archivo de tablas de valor. Posteriormente, el VM² " "se obtiene de la intersección entre dicha columna y la fila correspondiente al puntaje " "de construcción (PUNTCONS), cuyo rango va de 1 a 100." )

    st.divider()
    st.markdown("**Grupos de comunas**")
    st.markdown("\n".join(f"- **{g}** — {', '.join(c)}"
                          for g, c in GRUPOS_FILTRO.items()))
    st.caption("Las 5 comunas extra no tienen tabla propia: hoy se liquidan "
               "leyendo las mismas columnas *_10C_* del grupo de 10.")

    st.divider()
    st.markdown("**Excepciones**")
    st.info("**ZHF fuera de 011-016.** Si las tres últimas posiciones de la "
            "ZHF son diferentes a 011, 012, 013, 014, 015 y 016, se emplea el "
            "**estrato socioeconómico del predio (ESTRPRED)** y se asigna la "
            "tabla correspondiente según la comuna y la condición jurídica.")

    st.divider()
    st.markdown("**Qué predios NO se liquidan por tabla**")
    st.markdown(
        """

**1. Van por modelo, no por tabla**

| Uso de construcción |
|---|
| `Apartamentos_4_y_mas_pisos_en_PH` |
| `Comercio_en_PH` |
| `Oficinas_Consultorios_en_PH` |

**2. Son especiales por defecto**

| Uso de construcción |
|---|
| `Centros_Comerciales_grandes` |
| `Centros_Comerciales_en_PH_grandes` |

**3. El predio tiene información incompleta**

Sin área, sin valor, sin puntaje o sin VM2 de tabla: no hay con qué comparar.
        """)




st.caption(
    f"Fuente: {RUTA_DATOS.name} · generado por comparacion_vigencia.py el "
    f"{pd.Timestamp(os.path.getmtime(RUTA_DATOS), unit='s'):%Y-%m-%d %H:%M}. "
    f"predial: el VM2 viene redondeado a $100 y el avalúo a $100.000, así que "
    f"puede haber diferencias de centésimas contra el reporte en Excel, que "
    f"trabaja con el valor exacto y es el documento de referencia."
)


# =====================================================================
# PUBLICAR (gratis, con enlace)
# =====================================================================
# Streamlit Community Cloud lo publica gratis con una URL fija.
