#streamlit run src/app_vigencias.py

import io
import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
# Cada version de las tablas de valor deja sus salidas en su propia carpeta:
# output/versiones/<VERSION>/. Las dos fuentes anonimas, una por GRANO, y el
# detalle con identificadores, que solo existe en el equipo local.
CARPETA_VERSIONES = RAIZ / "output" / "versiones"
NOMBRE_DATOS = "COMPARACION_VIGENCIA_PUBLICO.parquet"
NOMBRE_PREDIO = "COMPARACION_VIGENCIA_PUBLICO_PREDIO.parquet"
NOMBRE_DETALLE = "COMPARACION_VIGENCIA_DETALLE.parquet"


def _orden_version(v: str) -> tuple:
    """V2 antes que V10: por el numero, no por el texto."""
    import re
    m = re.search(r"(\d+)", v)
    return (int(m.group(1)) if m else 0, v)


def versiones_publicadas() -> list:
    """Las versiones con datos para la app, de la mas vieja a la mas nueva."""
    if not CARPETA_VERSIONES.is_dir():
        return []
    return sorted((p.name for p in CARPETA_VERSIONES.iterdir()
                   if (p / NOMBRE_DATOS).exists()), key=_orden_version)


def ruta_version(version: str, nombre: str) -> Path:
    return CARPETA_VERSIONES / version / nombre


VERSIONES = versiones_publicadas()

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


def detalle_liquidado_mas_reciente(version: str):
    """El DETALLE_LIQUIDADOS_<version>_<fecha>.xlsx mas nuevo, o None."""
    return _mas_nuevo(f"DETALLE_LIQUIDADOS_{version}_*.xlsx")


def comparacion_versiones_mas_reciente():
    """El COMPARACION_VERSIONES_*.xlsx mas nuevo, o None si no hay."""
    carpeta = RAIZ / "results" / "COMPARACION_VERSIONES"
    if not carpeta.is_dir():
        return None
    hallados = sorted((f for f in carpeta.glob("COMPARACION_VERSIONES_*.xlsx")
                       if not f.name.startswith("~$")),
                      key=lambda f: f.stat().st_mtime, reverse=True)
    return hallados[0] if hallados else None


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


def coma(v: float, decimales: int = 2) -> str:
    """Un decimal con coma, como se escribe aca: 0,7 y no 0.7."""
    return f"{v:.{decimales}f}".rstrip("0").rstrip(".").replace(".", ",")


def entero(v) -> str:
    """206875 -> '206.875'"""
    return "" if v is None or pd.isna(v) else _miles(v, 0)


def _miles(v: float, decimales: int) -> str:
    """Miles con punto y decimales con coma, a la colombiana."""
    return (f"{v:,.{decimales}f}"
            .replace(",", " ").replace(".", ",").replace(" ", "."))

    # La misma paleta de los PNG del reporte.
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
    "17C": ["01", "02", "03", "04", "07", "08", "09", "10", "11", "12",
            "14", "15", "17", "19", "20", "21", "22"],
    # Version 2: EDIFICIOS e INDUSTRIAL parten las 10 comunas en dos, y sus 5
    # extra van con 5C_N.
    "5C": ["01", "09", "10", "11", "12"],
    "5C_N": ["05", "06", "07", "13", "14", "15", "16", "18", "20", "21"],
}

# Las agrupaciones de comunas de las tablas, como las define el equipo.
AGRUPACIONES_TABLAS = [
    ("7C", "Comunas actualizadas en 2024",
     ["02", "03", "04", "08", "17", "19", "22"]),
    ("5C", "Comunas actualizadas en 2025",
     ["01", "09", "10", "11", "12"]),
    ("5C_N", "Las 5 comunas que se actualizan por primera vez en 2026",
     ["07", "14", "15", "20", "21"]),
    ("5C_E", "Las 5 comunas propuestas para actualizar en 2027",
     ["05", "06", "13", "16", "18"]),
    ("10C", "Las de 5C y 5C_N juntas",
     ["01", "07", "09", "10", "11", "12", "14", "15", "20", "21"]),
]

# Los tres grupos en que se reparten las 22 comunas.
GRUPOS_FILTRO = {
    "10 comunas": ["01", "07", "09", "10", "11", "12", "14", "15", "20", "21"],
    "7 comunas": ["02", "03", "04", "08", "17", "19", "22"],
    "5 comunas (extra)": ["05", "06", "13", "16", "18"],
}

# comuna -> grupo, para armar la columna con la que se filtra y se abre.
COMUNA_A_GRUPO = {c: g for g, cs in GRUPOS_FILTRO.items() for c in cs}

# --- Factor de valor comercial ---------------------------------------------
# El comercial de la vigencia es el catastral dividido por este factor. Sale de
# CONFIG["comunas_act_2024_2025"], ["factor_comercial_act"] y
# ["factor_comercial_resto"] de comparacion_vigencia.py: si alla cambia, hay que
# cambiarlo aqui tambien. El parquet ya trae la columna ACTUALIZACION con lo
# mismo; esto es para poder mostrar la tabla sin depender de que haya datos.
COMUNAS_ACT_2024_2025 = ["01", "02", "03", "04", "08", "09", "10", "11", "12",
                         "17", "19", "22"]
FACTOR_COMERCIAL_ACT = 0.7      # comunas actualizadas en 2024-2025
FACTOR_COMERCIAL_RESTO = 0.6    # las demas
FACTOR_COMERCIAL_TERRENO = 0.7  # el terreno no distingue comuna


def factores_comerciales() -> pd.DataFrame:
    """Una fila por comuna: su grupo, si se actualizo y por cuanto se divide."""
    filas = [{"COMUNA": c,
              "GRUPO DE COMUNAS": COMUNA_A_GRUPO.get(c, "sin grupo"),
              "ACTUALIZACIÓN": ("ACT 2024-2025" if c in COMUNAS_ACT_2024_2025
                                else "SIN ACTUALIZAR"),
              "FACTOR COMERCIAL": (FACTOR_COMERCIAL_ACT
                                   if c in COMUNAS_ACT_2024_2025
                                   else FACTOR_COMERCIAL_RESTO)}
             for c in sorted(COMUNA_A_GRUPO)]
    return pd.DataFrame(filas)


# --- Incremento del terreno proyectado ---------------------------------------
# Sale de insumo_proyección_comuna_valor_terreno_20260930.parquet (columnas
# COMUNA, GRUPO e inc): VTERR_COM_2027 = VTER / 0,7 x (1 + inc). El insumo no
# se publica, asi que se copia aqui; si llega otro, hay que actualizarlo.
# (comuna, grupo, predios en el insumo, incremento %)
INCREMENTO_TERRENO = [
    ("01", "Act. 2025", 7633, 5.00),
    ("02", "Act. 2024", 15925, 4.69),
    ("03", "Act. 2025", 7712, 6.75),
    ("04", "Act. 2024", 9661, 12.72),
    ("07", "Sin act.", 11475, 139.35),
    ("08", "Act. 2024", 15986, 11.50),
    ("09", "Act. 2025", 10100, 3.26),
    ("10", "Act. 2025", 13131, 6.53),
    ("11", "Act. 2025", 12887, 10.70),
    ("12", "Act. 2025", 9053, 5.32),
    ("14", "Sin act.", 26560, 44.05),
    ("15", "Sin act.", 27959, 177.18),
    ("17", "Act. 2024", 18615, 10.64),
    ("19", "Act. 2024", 15068, 11.32),
    ("20", "Sin act.", 8855, 138.91),
    ("21", "Sin act.", 28580, 127.56),
    ("22", "Act. 2025", 5063, 3.18),
]


USOS_T1 = ("Apartamentos_4_y_mas_pisos_en_PH (001), Barracas (004), "
           "Vivienda_Hasta_3_Pisos (012), "
           "Vivienda_Hasta_3_Pisos_En_PH (013), Jardin_Infantil_en_Casa (063)")
USOS_T2 = "Apartamentos_4_y_mas_pisos (003)"
# Pensiones_y_Residencias (038) NO va aqui: no se reparte por tipologia
# 021/022/023 como los demas comerciales, sino que tiene tabla FIJA
# T3_COMERCIAL_023 en todas las comunas. Va en USOS_T3_FIJO, mas abajo.
USOS_T3 = ("Bodegas_Comerciales_Grandes_Almacenes (016), "
           "Estacion_de_servicio (021), Clubes_Casinos (024), Comercio (025), "
           "Comercio_en_PH (028), Plaza_Mercado (039), Restaurantes (041), "
           "Restaurantes_en_PH (042), Talleres (049)")
USOS_T4 = ("Salon_Comunal (009), Bodegas_Comerciales (017), "
           "Bodegas_Comerciales_en_PH (018), Industrias (047), "
           "Industrias_en_PH (048)")
USOS_T5 = "Educación y formación institucional (050, 051, 055, 068, 070)"
USOS_T6 = "Salud y servicios institucionales (054, 067)"
USOS_T9 = "Hoteles (030, 031)"
USOS_T11 = "Centros comerciales (019, 022, 043)"
USOS_T13 = "Unidad deportiva (071)"
USOS_T10 = "Anexos y no convencionales"
USOS_T12 = "Parqueaderos (006, 007, 008, 027, 036, 037)"

# Las tipologias de la ZHF van POR REGLA y no en una lista global: las
# residenciales son 011-016, las comerciales 021-023 y las industriales
# 031-033. Con una sola lista, comercial e industrial saldrian con las
# tipologias equivocadas.
TIPOLOGIAS_RESIDENCIAL = ["011", "012", "013", "014", "015", "016"]
TIPOLOGIAS_COMERCIAL = ["021", "022", "023"]
TIPOLOGIAS_INDUSTRIAL = ["031", "032", "033"]

# Que pasa cuando la ZHF no cae en las tipologias de su familia.
EXC_RESIDENCIAL = ("El orden es: PRIMERO LA ZONA. Si las tres últimas posiciones "
                   "de la ZHF son 011-016, esa tipología decide la tabla. Si son "
                   "diferentes -o la ZHF no sirve- se emplea el estrato "
                   "socioeconómico del predio (ESTRPRED) y se asigna la tabla "
                   "según la comuna y la condición jurídica. Si no tiene zona y "
                   "además no tiene estrato o viene en cero, se liquida con la "
                   "tabla del estrato 6.")
EXC_COMERCIAL = ("Si la ZHF termina en 011-016, la tabla es la que concuerde "
                 "con T3_COMERCIAL_021 para esas comunas. Si termina en algo "
                 "distinto de 011-016 y 021-023, la tabla es "
                 "T3_COMERCIAL_022.")
# Pensiones_y_Residencias (038): es comercial, pero con tabla fija.
USOS_T3_FIJO = "Pensiones_y_Residencias (038)"
EXC_T3_FIJO = ("No depende de la ZHF ni del estrato: siempre "
               "T3_COMERCIAL_023, en todas las comunas.")
EXC_T5 = "Se liquida con T5_INSTITUCIONAL_ED_17C en el grupo 17C; no depende de la ZHF ni del estrato."
EXC_T6 = "Se liquida con T6_INSTITUCIONAL_SA_17C en el grupo 17C; no depende de la ZHF ni del estrato."
EXC_T9 = "Se liquida con T9_HOTELES_17C en el grupo 17C; no depende de la ZHF ni del estrato."
EXC_T11 = "Se liquida con T11_CCOMERCIALES_17C en el grupo 17C; no depende de la ZHF ni del estrato."
EXC_T13 = "Se liquida con T13_UNIDAD_DEPORTIVA_17C en el grupo 17C; no depende de la ZHF ni del estrato."
EXC_T10 = "La T10 no se revaloriza en esta vigencia: el anexo entra igual en ambas vigencias porque la tabla no está aprobada."
EXC_T12 = "La T12 se liquida por regla propia de parqueaderos; no entra en la lógica de ZHF ni de estrato."

EXC_INDUSTRIAL = ("Si la ZHF termina en 011-016, la tabla es la que concuerde "
                  "con T4_INDUSTRIAL_031 para esas comunas. Si termina en algo "
                  "distinto de 011-016 y 031-033, la tabla es "
                  "T4_INDUSTRIAL_032.")

# (uso, grupo, condicion juridica, patron de la columna, tipologias, excepcion).
# {t} donde va la tipologia de la ZHF.
REGLAS_TABLA = [
    (USOS_T1, "10C", "9",
     "T1_RESIDENCIAL_10C_COND_9_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    (USOS_T1, "10C", "Diferente de 9",
     "T1_RESIDENCIAL_10C_COND_0_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    (USOS_T1, "7C", "Todas",
     "T1_RESIDENCIAL_7C_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    # Edificios: la restriccion es "diferente de 9". Decia "diferente de 8 y 9",
    # y la 8 no existe en este uso -ningun Apartamentos_4_y_mas_pisos la trae-,
    # asi que nombrarla sobraba.
    #
    # OJO: la asignacion no comprueba la condicion. Mira DESTINOCONS 003 y la
    # tipologia de la ZHF -o el estrato si la ZHF no sirve-, y por eso 3 de las
    # 7.655 construcciones que van a T2 tienen CONDICION 9. Lo dice tambien el
    # comentario de Liquidacion_tablas.py:84. Para que la regla se cumpla hay
    # que agregar la comprobacion alli.
    (USOS_T2, "5C", "Diferente de 9",
     "T2_EDIFICIOS_5C_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    (USOS_T2, "5C_N", "Diferente de 9",
     "T2_EDIFICIOS_5C_N_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    (USOS_T2, "7C", "Diferente de 9",
     "T2_EDIFICIOS_7C_{t}", TIPOLOGIAS_RESIDENCIAL, EXC_RESIDENCIAL),
    (USOS_T3, "10C", "NA",
     "T3_COMERCIAL_10C_{t}", TIPOLOGIAS_COMERCIAL, EXC_COMERCIAL),
    (USOS_T3, "7C", "NA",
     "T3_COMERCIAL_7C_{t}", TIPOLOGIAS_COMERCIAL, EXC_COMERCIAL),
    # Tabla fija: el patron no lleva {t} y la lista de tipologias es un
    # unico "NA", para que reglas_asignacion() saque UNA fila por grupo.
    (USOS_T3_FIJO, "10C", "NA",
     "T3_COMERCIAL_10C_023", ["NA"], EXC_T3_FIJO),
    (USOS_T3_FIJO, "7C", "NA",
     "T3_COMERCIAL_7C_023", ["NA"], EXC_T3_FIJO),
    (USOS_T4, "5C", "NA",
     "T4_INDUSTRIAL_5C_{t}", TIPOLOGIAS_INDUSTRIAL, EXC_INDUSTRIAL),
    (USOS_T4, "5C_N", "NA",
     "T4_INDUSTRIAL_5C_N_{t}", TIPOLOGIAS_INDUSTRIAL, EXC_INDUSTRIAL),
    (USOS_T4, "7C", "NA",
     "T4_INDUSTRIAL_7C_{t}", TIPOLOGIAS_INDUSTRIAL, EXC_INDUSTRIAL),
    (USOS_T5, "17C", "NA",
     "T5_INSTITUCIONAL_ED_17C", ["NA"], EXC_T5),
    (USOS_T6, "17C", "NA",
     "T6_INSTITUCIONAL_SA_17C", ["NA"], EXC_T6),
    (USOS_T9, "17C", "NA",
     "T9_HOTELES_17C", ["NA"], EXC_T9),
    (USOS_T10, "17C", "NA",
     "T10_ANEXOS", ["NA"], EXC_T10),
    (USOS_T11, "17C", "NA",
     "T11_CCOMERCIALES_17C", ["NA"], EXC_T11),
    (USOS_T12, "17C", "NA",
     "T12_PARQUEADEROS", ["NA"], EXC_T12),
    (USOS_T13, "17C", "NA",
     "T13_UNIDAD_DEPORTIVA_17C", ["NA"], EXC_T13),
]


def reglas_asignacion() -> pd.DataFrame:
    """La especificacion desplegada: una fila por regla y tipologia."""
    filas = [{"USO DE CONSTRUCCIÓN": uso,
              "COMUNAS": ", ".join(GRUPOS_COMUNAS[grupo]),
              "CONDICIÓN JURÍDICA": condicion,
              "TIPOLOGÍA ZHF": t,
              "REFERENCIA TABLA": patron.format(t=t),
              "EXCEPCIONES": excepcion}
             for uso, grupo, condicion, patron, tipologias, excepcion in REGLAS_TABLA
             for t in tipologias]
    return pd.DataFrame(filas)


# Por que columna se parten el resumen, los percentiles y los graficos.
APERTURAS = {
    "Tabla de valor": "TABLA_ORIGEN",
    "Comuna": "COMUNA",
    "Actividad económica de la ZHF": "ACTIVIDAD_ECONOMICA",
    "Grupo de comunas": "GRUPO_COMUNAS",
    "Tabla y actividad juntas (como en el reporte)": "CLAVE",
}

# Sobre los anexos NO hay filtro, a proposito. La hoja NO_CONVENCIONALES del
# consolidado -la tabla T10, la de los anexos- viene sin datos, asi que ningun
# anexo se revalora y su valor entra al avaluo IGUAL en las dos vigencias. La
# comparacion del predio sigue siendo valida: si el avaluo de un predio con
# anexo se mueve menos, se mueve menos de verdad, no por un defecto de
# medicion. Distinto del caso de los usos en PH, donde el valor de 2026 lo
# ponia un modelo y el de 2027 una tabla: ahi si se comparaban cosas
# distintas. La columna CON_ANEXO se sigue publicando para el explorador
# predio a predio, y CONFIG["liquidar_anexos"] sigue en su sitio para cuando
# entreguen la T10.

# Lo que se lee de cada parquet.
COMUNES = ["COMUNA", "ACTUALIZACION", "TABLA_ORIGEN", "USO_LADM",
           "ACTIVIDAD_ECONOMICA", "CLAVE", "N_CONST_PREDIO", "CON_ANEXO",
           "CONDICION", "ESPECIAL", "PREDIO_ESPECIAL", "CAMBIO_TIPOLOGIA",
           "PUNTCONS",
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
        .filtros-titulo {display:flex; align-items:center; gap:10px;
            font-weight:700; font-size:18px; color:#0F1F33; margin:4px 0 6px;}
        .filtros-icono {width:32px; height:32px; border-radius:7px;
            background:#1D3557; display:flex; align-items:center;
            justify-content:center; box-shadow:0 1px 3px rgba(16,24,40,.25);}
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
    # El incremento de su comuna, solo donde el terreno 2027 es el proyectado;
    # va justo despues de ORIGEN_TERRENO_LIQ.
    # comparacion_vigencia.py ya la escribe; esto es para un detalle viejo.
    if ("ORIGEN_TERRENO_LIQ" in d.columns
            and "INCREMENTO_TERRENO_PCT" not in d.columns):
        inc = {c: p for c, _, _, p in INCREMENTO_TERRENO}
        d["INCREMENTO_TERRENO_PCT"] = d["COMUNA"].map(inc).round(0).where(
            d["ORIGEN_TERRENO_LIQ"].astype(str) == "PROYECTADO")
        cols = list(d.columns)
        cols.remove("INCREMENTO_TERRENO_PCT")
        cols.insert(cols.index("ORIGEN_TERRENO_LIQ") + 1,
                    "INCREMENTO_TERRENO_PCT")
        d = d[cols]
    # ID_PREDIO y el numero predial son unicos por fila: _a_categoria los deja
    # como estan y solo convierte las columnas que de verdad se repiten.
    return _a_categoria(d)


@st.cache_resource(show_spinner="Leyendo el detalle predio a predio…",
                   max_entries=2)
def cargar_detalles(fuentes: tuple) -> pd.DataFrame:
    """El detalle de las versiones elegidas, con VERSION al frente."""
    det = _unir([cargar_detalle(r, m).assign(VERSION=v) for v, r, m in fuentes])
    return det[["VERSION"] + [c for c in det.columns if c != "VERSION"]]


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


if not VERSIONES:
    st.error(
        f"No se encontró ninguna versión en **output/versiones/**.\n\n"
        "Corra primero `python src/main.py`, que deja cada versión en "
        "`output/versiones/<VERSION>/`."
    )
    st.stop()


def _unir(partes: list) -> pd.DataFrame:
    """Concatena versiones sin perder las categorias (el concat las deshace)."""
    from pandas.api.types import union_categoricals
    d = pd.concat(partes, ignore_index=True)
    for c in d.columns:
        if c != "VERSION" and all(
                isinstance(x[c].dtype, pd.CategoricalDtype) for x in partes):
            d[c] = union_categoricals([x[c] for x in partes])
    d["VERSION"] = pd.Categorical(d["VERSION"], categories=VERSIONES)
    return _a_categoria(d)


# cache_resource y no cache_data: guarda UN objeto y lo entrega sin copiarlo en
# cada clic. Con cache_data cada rerun armaba una copia nueva de todas las
# versiones y el contenedor del despliegue (1 GB) se caia. Nada de la app
# modifica estos DataFrames en sitio: los filtros devuelven otros nuevos.
@st.cache_resource(show_spinner="Leyendo las versiones de la comparación…",
                   max_entries=4)
def cargar_versiones(nombre: str, grano: str, marcas: tuple):
    """El recorte de todas las versiones, una debajo de otra, con VERSION."""
    partes = [cargar(str(ruta_version(v, nombre)), m, grano).assign(VERSION=v)
              for v, m in marcas]
    return _unir(partes) if partes else None


def marcas_de(nombre: str) -> tuple:
    """(version, fecha de modificacion) de cada archivo: la llave del cache."""
    return tuple((v, os.path.getmtime(ruta_version(v, nombre)))
                 for v in VERSIONES if ruta_version(v, nombre).exists())


df_construccion = cargar_versiones(NOMBRE_DATOS, "construccion",
                                   marcas_de(NOMBRE_DATOS))


# =====================================================================
# FILTROS (uno solo para todas las hojas)
# =====================================================================
# El sidebar va antes del encabezado: la medida decide de que parquet se lee.
with st.sidebar:
    st.markdown(
        """
        <div class="filtros-titulo">
          <span class="filtros-icono" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none"
                 stroke="#FFFFFF" stroke-width="2" stroke-linecap="round"
                 stroke-linejoin="round"><path d="M3 21h18"></path>
              <path d="M5 21V9l7-5 7 5v12"></path><path d="M9 21v-6h6v6"></path>
            </svg>
          </span>
          <span>Filtros</span>
        </div>
        """,
        unsafe_allow_html=True)
    st.caption("Se aplican a todas las hojas. Vacío = todo.")

    sel_versiones = st.multiselect(
        "Versión de tablas", VERSIONES, default=[VERSIONES[-1]],
        help="Con qué versión de las tablas de valor se liquida 2027. Con una "
             "sola, la app se ve como siempre. Con dos o más, cada tabla sale "
             "una vez por versión (por ejemplo T3_COMERCIAL · V1 y "
             "T3_COMERCIAL · V2) para compararlas lado a lado. Vacío = la más "
             "reciente.")
    sel_versiones = ([v for v in VERSIONES if v in sel_versiones]
                     or [VERSIONES[-1]])
    varias_versiones = len(sel_versiones) > 1

    excluir_predios_especiales = st.checkbox(
        "Excluir construcciones especiales",
        value=False,
        help="En Valor por m² excluye construcciones con ESPECIAL=1; en "
             "Valor total construido y Avalúo excluye predios con "
             "PREDIO_ESPECIAL=1."
    )

    # La columna la escribe comparacion_vigencia.py. Si el parquet es anterior
    # al cambio no esta, y entonces la casilla se ofrece deshabilitada en vez de
    # quedarse marcando sin filtrar nada, que es lo que confunde.
    hay_cambio_tip = "CAMBIO_TIPOLOGIA" in df_construccion.columns
    excluir_cambio_tipologia = st.checkbox(
        "Excluir cambio de tipología",
        value=False,
        disabled=not hay_cambio_tip,
        help="Deja fuera lo que se movió de zona entre las dos entregas "
             "(CAMBIO_TIPOLOGIA=1): esas construcciones no comparan lo mismo a "
             "lado y lado, porque cambió la tabla que les toca. En Avalúo y "
             "Valor total construido se excluye el predio completo si CUALQUIERA "
             "de sus construcciones cambió."
        if hay_cambio_tip else
        "El parquet actual no trae CAMBIO_TIPOLOGIA. Vuelva a correr "
        "`python src/comparacion_vigencia.py` para que la columna salga.")

    etiqueta_medida = st.radio(
        "Medida", list(MEDIDAS), index=0,
        help="El valor por m² es de cada CONSTRUCCIÓN; el valor construido "
             "total y el avalúo son del PREDIO completo, sumando sus "
             "construcciones. Por eso al cambiar de medida cambia el conteo.")
    etiqueta_base = st.segmented_control(
        "Base de valor", list(BASES), default=list(BASES)[0],
        selection_mode="single", width="stretch",
        help="Catastral es lo que se cobra. Comercial es lo que se estima que "
             "vale: el catastral de la vigencia dividido por 0,7 en las comunas "
             "actualizadas en 2024-2025 y por 0,6 en las demás.")
    # Si se vuelve a hacer clic en la caja marcada, queda sin seleccion.
    etiqueta_base = etiqueta_base or list(BASES)[0]
    clave_medida, titulo_medida, grano = MEDIDAS[etiqueta_medida]
    medida = SERIES[(clave_medida, BASES[etiqueta_base])]
    unidad_eje = f"{titulo_medida} {etiqueta_base.lower()} (millones de pesos)"
    unidad, unidades = UNIDAD[grano]
    # Los conteos se llaman como lo que cuentan: PREDIOS o CONSTRUCCIONES.
    COL_N = unidades.upper()
    COL_NUM = f"NUM_{COL_N}"

    # De aqui en adelante 'df' es el parquet del grano que corresponda, y todo
    # lo demas -filtros, tablas, graficos- trabaja sobre el sin enterarse.
    df_predio = (cargar_versiones(NOMBRE_PREDIO, "predio",
                                  marcas_de(NOMBRE_PREDIO))
                 if grano == "predio" and marcas_de(NOMBRE_PREDIO) else None)
    if grano == "predio" and df_predio is None:
        st.error(f"Falta {NOMBRE_PREDIO}, que es de donde salen el valor "
                 f"construido total y el avalúo. Corra "
                 f"`python src/comparacion_vigencia.py`.")
        st.stop()
    df = df_predio if grano == "predio" else df_construccion

    familias = sorted({t.split("_")[0] + "_" + t.split("_")[1]
                       for t in df["TABLA_ORIGEN"].unique() if "_" in t})
    sel_familia = st.multiselect("Categoría de tabla", familias)

    # Cada tabla tiene su pareja terminada en _9, la de la condicion 9. Las dos
    # casillas SUMAN, no se encadenan: cada una admite un grupo. Sin marcar
    # ninguna entran todas -es el arranque- y marcando las dos, tambien, que es
    # lo que se pidio al marcarlas. Asi ninguna combinacion deja el reporte
    # vacio, que con dos filtros en cadena seria lo que pasaria.
    c9_si = st.checkbox("Condición 9", value=False,
                        help="Las tablas que terminan en _9.")
    c9_no = st.checkbox("Excepto la 9", value=False,
                        help="Las demás tablas. Con las dos marcadas, o con "
                             "ninguna, entran todas.")
    # True = solo las _9, False = solo las demas, None = no filtrar.
    filtro_9 = c9_si if c9_si != c9_no else None

    # Las tablas que se ofrecen dependen de la familia elegida, para no dar a
    # escoger entre 40 codigos cuando ya se acoto a residencial.
    de_la_familia = (df["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))
                     if sel_familia else slice(None))
    tablas = sorted(df.loc[de_la_familia, "TABLA_ORIGEN"].unique())
    if filtro_9 is not None:
        tablas = [x for x in tablas if str(x).endswith("_9") == filtro_9]
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

    st.divider()
    max_n_const = (
        int(df["N_CONST_PREDIO"].dropna().max())
        if "N_CONST_PREDIO" in df.columns and not df["N_CONST_PREDIO"].dropna().empty
        else 5000
    )
    max_n_const = int(max_n_const)
    max_construcciones = st.number_input(
        "Máximo de construcciones",
        min_value=1,
        max_value=max_n_const,
        value=max_n_const,
        help="Deja solo los predios con esa cantidad máxima de construcciones "
             "o menos. El valor inicial es el máximo real observado."
    )

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
    if "VERSION" in d.columns:
        d = d[d["VERSION"].isin(sel_versiones)]
    if sel_familia:
        d = d[d["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))]
    if sel_tabla:
        d = d[d["TABLA_ORIGEN"].isin(sel_tabla)]
    if filtro_9 is not None:
        es_9 = d["TABLA_ORIGEN"].astype(str).str.endswith("_9")
        d = d[es_9] if filtro_9 else d[~es_9]
    if sel_comuna:
        d = d[d["COMUNA"].isin(sel_comuna)]
    if sel_actividad:
        d = d[d["ACTIVIDAD_ECONOMICA"].isin(sel_actividad)]
    if sel_grupo:
        d = d[d["GRUPO_COMUNAS"].isin(sel_grupo)]
    if sel_n_const and "N_CONST_PREDIO" in d.columns:
        d = d[d["N_CONST_PREDIO"].isin(sel_n_const)]
    if "N_CONST_PREDIO" in d.columns:
        d = d[d["N_CONST_PREDIO"].le(max_construcciones)]
    if excluir_cambio_tipologia and "CAMBIO_TIPOLOGIA" in d.columns:
        # Solo el 1. El "SIN COMPARACIÓN" -a alguno de los dos lados le falta la
        # tipologia- no es un cambio comprobado y se queda.
        d = d[d["CAMBIO_TIPOLOGIA"].astype(str) != "1"]
    if excluir_predios_especiales:
        columnas_especiales = (
            ("PREDIO_ESPECIAL", "PREDIO_DESTINO_ESPECIAL")
            if grano == "predio" else ("ESPECIAL", "ESPECIAL_2026")
        )
        col_especial = next(
            (c for c in columnas_especiales if c in d.columns),
            None,
        )
        if col_especial is not None:
            d = d[pd.to_numeric(d[col_especial], errors="coerce").ne(1)]
    # La medida de avaluo puede venir vacia si se corrio la comparacion sin las
    # columnas de terreno; mejor decirlo que mostrar una hoja en blanco.
    return d[d[medida["vig"]].notna() & d[medida["liq"]].notna()]


st.markdown(
    f"""
    <div class="app-hero">
        <h1>🏙️ Comparación de vigencias · {V_BASE} → {V_LIQ}</h1>
        <p>La liquidación ({V_LIQ}) contra lo que cobra hoy la base
        ({V_BASE}) · tablas <b>{" y ".join(sel_versiones)}</b> ·
        {titulo_medida.lower()}, base {etiqueta_base.lower()}. Solo predios con
        todas sus construcciones valoradas por tabla en las dos vigencias.
        El anexo no se revalora: la T10 no está entregada, así que su valor
        entra igual en las dos.</p>
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

# Con varias versiones, una fila de tarjetas por version: sumarlas mezclaria
# la misma construccion contada dos veces.
for v in sel_versiones:
    dv = dff[dff["VERSION"] == v]
    base_v = df[df["VERSION"] == v]
    if varias_versiones:
        st.markdown(f"**Versión {v}**")
    if dv.empty:
        st.caption("Ningún registro de esta versión cumple los filtros.")
        continue
    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric(unidades.capitalize(), entero(len(dv)),
              f"{pct(len(dv) / len(base_v) * 100, 1)} del total")
    k2.metric(f"Mediana vigencia {V_BASE}", pesos(dv[medida["vig"]].median()))
    k3.metric(f"Mediana vigencia {V_LIQ} · {v}" if varias_versiones
              else f"Mediana vigencia {V_LIQ}", pesos(dv[medida["liq"]].median()))
    k4.metric("Variación mediana", pct(dv[medida["var"]].median(), 2, signo=True))
    k5.metric("Bajan", pct((dv[medida["var"]] < 0).mean() * 100, 1))


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
        if "PUNTCONS" in s.columns:
            puntaje = pd.to_numeric(s["PUNTCONS"], errors="coerce").dropna()
            if not puntaje.empty:
                valor_puntaje = float(puntaje.quantile(p / 100))
            else:
                valor_puntaje = float(p)
        else:
            valor_puntaje = float(p)
        filas.append({"PERCENTIL": f"{p}%",
                      "__COUNT__": int(round(p / 100 * len(s))),
                      "PUNTAJE": int(round(valor_puntaje)),
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


AZUL_SUBE = "#1F5FA8"
NARANJA_BAJA = "#B4430E"


def con_formato(t: pd.DataFrame):
    """La tabla lista para mostrar. Devuelve un Styler: la columna sigue siendo numerica y se puede ordenar."""
    reglas = {}
    for col in t.columns:
        if col == "__COUNT__":
            continue
        if col == "PUNTAJE":
            reglas[col] = entero
        elif col == c_dif:                         # pesos, con signo
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
    sty = t.style.format(reglas)

    # Lo que sube en azul y lo que baja en naranja: se distinguen tambien en
    # luminosidad, no solo por el tono.
    def _signo(v):
        if pd.isna(v) or v == 0:
            return ""
        return f"color: {AZUL_SUBE}" if v > 0 else f"color: {NARANJA_BAJA}"
    con_signo = [c for c in (c_dif, c_var, "VAR_MEDIANA_%") if c in t.columns]
    if con_signo:
        sty = sty.map(_signo, subset=con_signo)

    # Las filas TOTAL, sombreadas y en negrilla.
    primera = t.columns[0] if len(t.columns) else None
    if primera is not None and t[primera].astype(str).str.startswith("TOTAL").any():
        def _total(fila):
            es_total = str(fila.iloc[0]).startswith("TOTAL")
            estilo = ("background-color: #E9EEF5; font-weight: 700"
                      if es_total else "")
            return [estilo] * len(fila)
        sty = sty.apply(_total, axis=1)
    return sty


def resumen(d: pd.DataFrame, col: str,
            d_total: pd.DataFrame | None = None) -> pd.DataFrame:
    """Una fila por grupo: cuantos predios, las dos medianas y como se mueve.

    d_total es de donde salen las filas TOTAL, si no es el mismo d: con varias
    versiones, a d le faltan las filas repetidas de las tablas sin cambio, y el
    total de cada version las necesita todas."""
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
    # Con varias versiones sale un TOTAL por version, nunca mezcladas.
    d_total = d if d_total is None else d_total
    sub_todo = d_total[d_total[col].isin(grupos_ok)]
    filas = []
    for v in sel_versiones:
        sub = sub_todo[sub_todo["VERSION"] == v]
        if sub.empty:
            continue
        fila = {etiqueta_apertura: f"TOTAL · {v}" if varias_versiones else "TOTAL",
                COL_N: len(sub),
                c_base: sub[medida["vig"]].median(),
                c_liq: sub[medida["liq"]].median(),
                "VAR_MEDIANA_%": sub[medida["var"]].median(),
                "BAJAN_%": (sub[medida["var"]] < 0).mean() * 100,
                "SUBEN_%": (sub[medida["var"]] > 0).mean() * 100}
        fila[c_dif] = fila[c_liq] - fila[c_base]
        filas.append(fila)
    return pd.concat([t, pd.DataFrame(filas)[t.columns]], ignore_index=True)


hoja_tablas, hoja_graf, hoja_detalle, hoja_reglas = st.tabs(
    ["📊 Tablas", "📈 Gráficos", "🔎 Detalle",
     "📋 Reglas"])

# Todo se arma una sola vez aca arriba: las tres hojas y el Excel leen de estos
# mismos objetos, asi no hay dos sitios calculando lo mismo y desviandose.
# Con varias versiones cada grupo se parte por version: "T3_COMERCIAL_021 · V1"
# y "T3_COMERCIAL_021 · V2" quedan seguidos, como si fueran dos tablas.
# Si un grupo trae exactamente los mismos valores en todas las versiones
# elegidas -la tabla no cambio-, sale UNA sola fila: "T11_CCOMERCIALES · V1 = V2
# (sin cambio)". Los TOTAL siguen siendo uno por version.
if varias_versiones:
    import hashlib
    import numpy as np

    etiqueta = dff[col_apertura].astype(str)

    def _huella(s: pd.DataFrame) -> str:
        """Los valores de las dos vigencias, ordenados: si coinciden, es igual."""
        h = hashlib.md5()
        for c in (medida["vig"], medida["liq"]):
            h.update(np.sort(pd.to_numeric(s[c], errors="coerce")
                             .to_numpy(dtype="float64")).tobytes())
        return h.hexdigest()

    huellas = (dff[[medida["vig"], medida["liq"]]]
               .assign(_K=etiqueta, VERSION=dff["VERSION"].astype(str))
               .groupby(["_K", "VERSION"])[[medida["vig"], medida["liq"]]]
               .apply(_huella)
               .unstack("VERSION")
               .reindex(columns=sel_versiones))
    sin_cambio = set(huellas.index[huellas.notna().all(axis=1)
                                   & (huellas.nunique(axis=1) == 1)])
    nota = f" · {' = '.join(sel_versiones)} (sin cambio)"
    es_igual = etiqueta.isin(sin_cambio)
    dff = dff.assign(_APERTURA=etiqueta.where(
        ~es_igual, etiqueta + nota).where(
        es_igual, etiqueta + " · " + dff["VERSION"].astype(str)))
    # Para las filas de grupo basta una version de lo que no cambio.
    dff_grupos = dff[~(es_igual & (dff["VERSION"] != sel_versiones[0]))]
    col_grupo = "_APERTURA"
else:
    dff_grupos = dff
    col_grupo = col_apertura
res = resumen(dff_grupos, col_grupo, dff)
# Los percentiles del total, uno por version.
totales = {v: percentiles(dff[dff["VERSION"] == v]) for v in sel_versiones}
totales = {v: t for v, t in totales.items() if not t.empty}
abierto = por_grupo(dff_grupos, col_grupo)
reglas = reglas_asignacion()
factores = factores_comerciales()

# El reparto de la variacion.
# en el rango de su propia variacion, no se comparan distribuciones.
RANGOS = ["Baja más de 50%", "Baja 25-50%", "Baja 10-25%", "Estable (±10%)",
          "Sube 10-25%", "Sube 25-50%", "Sube más de 50%"]
_partes_reparto = []
for v in sel_versiones:
    _r = (dff.loc[dff["VERSION"] == v, medida["var"]]
          .pipe(pd.cut,
                bins=[-float("inf"), -50, -25, -10, 10, 25, 50, float("inf")],
                labels=RANGOS)
          .value_counts(sort=False)
          .rename_axis("RANGO").reset_index(name=COL_N))
    _r["%"] = _r[COL_N] / max(_r[COL_N].sum(), 1) * 100
    _r["VERSION"] = v
    _partes_reparto.append(_r)
reparto = pd.concat(_partes_reparto, ignore_index=True)


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
    st.caption(f"En cada corte: cuánto vale en la vigencia {V_BASE}, cuánto "
               f"valdría en la {V_LIQ}, cuántos pesos de diferencia hay entre "
               f"los dos y qué proporción representa esa diferencia.")
    for v, total in totales.items():
        n_v = int((dff["VERSION"] == v).sum())
        st.markdown("**Percentiles, diferencia y variación** · "
                    + (f"versión {v} · " if varias_versiones else "")
                    + f"{entero(n_v)} {unidades}")
        total_visible = total.drop(columns=["__COUNT__"], errors="ignore")
        st.dataframe(con_formato(total_visible), width="stretch",
                     hide_index=True)



# ---------------------------------------------------------------------
# HOJA 3 - GRAFICOS
# ---------------------------------------------------------------------
with hoja_graf:
    st.subheader(f"Gráficos · {etiqueta_medida} · base {etiqueta_base.lower()}")

    def pie(t: pd.DataFrame) -> list:
        """Bajo el titulo va SOLO el conteo: es corto y nunca se corta."""
        if t.empty:
            return []
        count = t["__COUNT__"].iloc[-1] if "__COUNT__" in t.columns else t[COL_NUM].iloc[-1]
        return [f"{entero(int(count))} {unidades} comparadas"
                if grano == "construccion" else
                f"{entero(int(count))} {unidades} comparados"]

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

    cols_total = st.columns(min(len(totales), 3)) if totales else []
    for i, (v, total) in enumerate(totales.items()):
        col = cols_total[i % len(cols_total)]
        col.altair_chart(curvas(total, f"Total de la selección · {v}"
                                if varias_versiones else "Total de la selección"),
                         width="stretch")
        col.caption(frase(total))

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
            x=alt.X("RANGO:N", title=None, sort=RANGOS,
                    axis=alt.Axis(labelAngle=0)),   # rotulos en horizontal
            y=alt.Y(f"{COL_N}:Q", title=unidades.capitalize()),
            # Con varias versiones, una barra por version dentro de cada rango.
            **({"color": alt.Color("VERSION:N", title="Versión",
                                   legend=alt.Legend(orient="top")),
                "xOffset": alt.XOffset("VERSION:N")}
               if varias_versiones else {}),
            tooltip=[alt.Tooltip("RANGO:N", title="Rango"),
                     alt.Tooltip("VERSION:N", title="Versión"),
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
    for v in sel_versiones:
      detalle = detalle_liquidado_mas_reciente(v)
      if detalle is not None:
        st.download_button(
            f"📗 Detalle liquidación · {v}",
            data=leer_archivo(str(detalle), detalle.stat().st_mtime),
            file_name=detalle.name,
            mime=("application/vnd.openxmlformats-officedocument"
                  ".spreadsheetml.sheet"),
            type="primary", key=f"dl_detalle_liq_{v}",
            help="Una fila por construcción, con el VM2 de las dos vigencias, "
                 "la tabla y la columna exacta de donde salió el valor, y el "
                 "avalúo del predio. Trae además una hoja Diccionario.")
        st.caption(
            f"`{detalle.name}` · "
            f"{_miles(detalle.stat().st_size / 1e6, 1)} MB · generado el "
            f"{pd.Timestamp(detalle.stat().st_mtime, unit='s'):%Y-%m-%d %H:%M}"
            f". Es el detalle completo de la corrida: no responde a los "
            f"filtros de la izquierda.")

    comp_versiones = comparacion_versiones_mas_reciente()
    if comp_versiones is not None:
        st.download_button(
            "📘 Comparación entre versiones",
            data=leer_archivo(str(comp_versiones),
                              comp_versiones.stat().st_mtime),
            file_name=comp_versiones.name,
            mime=("application/vnd.openxmlformats-officedocument"
                  ".spreadsheetml.sheet"),
            key="dl_comp_versiones",
            help="Todas las versiones liquidadas: resumen por categoría y por "
                 "tabla con una fila por versión, y el detalle por "
                 "construcción con el VM2 y el avalúo de cada versión lado a "
                 "lado.")
        st.caption(f"`{comp_versiones.name}` · "
                   f"{_miles(comp_versiones.stat().st_size / 1e6, 1)} MB")

    st.divider()
    rutas_detalle = {v: ruta_version(v, NOMBRE_DETALLE) for v in sel_versiones
                     if ruta_version(v, NOMBRE_DETALLE).exists()}
    if rutas_detalle:
        st.markdown("**Explorador predio a predio**")
        det = cargar_detalles(tuple((v, str(r), os.path.getmtime(r))
                                    for v, r in rutas_detalle.items()))
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
                 column_config={
                     "COMUNAS": st.column_config.TextColumn(width="medium"),
                     "EXCEPCIONES": st.column_config.TextColumn(width="large")})
    st.caption( "Se identifica el uso de la construcción, la condición jurídica, la tipología y la ZHF. " "Con esta información se determina la tabla de valor correspondiente a la comuna y se " "selecciona la columna asociada en el archivo de tablas de valor. Posteriormente, el VM² " "se obtiene de la intersección entre dicha columna y la fila correspondiente al puntaje " "de construcción (PUNTCONS), cuyo rango va de 1 a 100." )

    st.divider()
    st.markdown("**Grupos de comunas**")
    st.dataframe(
        pd.DataFrame([(g, desc, ", ".join(c))
                      for g, desc, c in AGRUPACIONES_TABLAS],
                     columns=["GRUPO", "DESCRIPCIÓN", "COMUNAS"]),
        width="stretch", hide_index=True,
        column_config={
            "GRUPO": st.column_config.TextColumn(width="small"),
            "DESCRIPCIÓN": st.column_config.TextColumn(width="large"),
            "COMUNAS": st.column_config.TextColumn(width="medium")})
    st.caption("EDIFICIOS (T2) e INDUSTRIAL (T4) tienen tablas 7C, 5C y 5C_N, "
               "y sus comunas extra (5C_E) se liquidan con la 5C_N. Las demás "
               "tablas siguen con 7C y 10C, y sus comunas extra se liquidan con "
               "la 10C.")

    st.divider()
    st.markdown("**Factor de valor comercial por comuna**")
    st.dataframe(factores, width="stretch", hide_index=True,
                 column_config={
                     "COMUNA": st.column_config.TextColumn(width="small"),
                     "ACTUALIZACIÓN": st.column_config.TextColumn(width="small"),
                     "FACTOR COMERCIAL": st.column_config.NumberColumn(
                         format="%.2f", width="small")})
    n_act = len(COMUNAS_ACT_2024_2025)
    n_resto = len(COMUNA_A_GRUPO) - n_act
    st.caption(
        f"El valor comercial de la vigencia es el catastral dividido por el "
        f"factor de la comuna: las {n_act} actualizadas en 2024-2025 van por "
        f"{coma(FACTOR_COMERCIAL_ACT)} y las {n_resto} restantes por "
        f"{coma(FACTOR_COMERCIAL_RESTO)}. El terreno no distingue comuna: "
        f"siempre va por {coma(FACTOR_COMERCIAL_TERRENO)}. En el avalúo 2027 "
        f"el terreno es el proyectado (VTERR_COM_2027 × 0,7, todavía no definitivo) "
        f"donde el insumo lo trae; el predio que no está ahí conserva el "
        f"VTER de la base. El valor de la "
        f"liquidación 2027 no usa este factor: la tabla de valor da el "
        f"comercial y el catastral sale de multiplicarlo por 0,7.")

    st.markdown("**Incremento del terreno proyectado por comuna**")
    st.dataframe(
        pd.DataFrame(INCREMENTO_TERRENO,
                     columns=["COMUNA", "GRUPO", "PREDIOS", "INCREMENTO"]),
        width="stretch", hide_index=True,
        column_config={
            "COMUNA": st.column_config.TextColumn(width="small"),
            "GRUPO": st.column_config.TextColumn(width="small"),
            "PREDIOS": st.column_config.NumberColumn(format="localized",
                                                     width="small"),
            "INCREMENTO": st.column_config.NumberColumn(format="%.0f %%",
                                                        width="small")})
    st.caption("VTERR_COM_2027 = VTER_COM_2026 × (1 + incremento de la "
               "comuna). Predios: los que trae el insumo de proyección.")

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
    f"Fuente: output/versiones/<versión>/{NOMBRE_DATOS} · versión "
    f"{sel_versiones[-1]} generada por comparacion_vigencia.py el "
    f"{pd.Timestamp(os.path.getmtime(ruta_version(sel_versiones[-1], NOMBRE_DATOS)), unit='s'):%Y-%m-%d %H:%M}. "
    f"predial: el VM2 viene redondeado a $100 y el avalúo a $100.000, así que "
    f"puede haber diferencias de centésimas contra el reporte en Excel, que "
    f"trabaja con el valor exacto y es el documento de referencia."
)


# =====================================================================
# PUBLICAR (gratis, con enlace)
# =====================================================================
# Streamlit Community Cloud lo publica gratis con una URL fija.

# Lo que cada clic arma -filtros, tablas, graficos- se suelta aqui mismo: sin
# esto la memoria del despliegue (1 GB) sube de clic en clic hasta tumbar la app.
import gc
gc.collect()
