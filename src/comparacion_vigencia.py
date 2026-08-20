"""
=====================================================================
COMPARACION VM2: VIGENCIA 2027 (liquidacion)  vs  VIGENCIA 2026 (la base)
=====================================================================

Que compara
-----------
Para CADA construccion liquidada, el valor por m2 que quedaria con la
liquidacion nueva contra el que hoy tiene la base catastral:

    VM2_VIGENCIA  = VALORCONS / ACONCONS          <- lo que hay hoy (catastral)
    VM2_LIQ       = VM2 * FACTOR_CATASTRAL        <- lo que daria la liquidacion

En el reporte esas dos series salen NOMBRADAS POR VIGENCIA: VM2_VIG_2026 es lo
que esta cobrando hoy la base y VM2_VIG_2027 lo que quedaria con la
liquidacion; lo mismo con AVALÚO_VIG_2026 / AVALÚO_VIG_2027 y con la leyenda
de los graficos. El ejercicio del ano pasado los llamaba VM2_2025 / VM2_2026
-el ano de la corrida-, y asi no se sabia cual de los dos era la base. Los dos
anos salen de CONFIG["vigencia_base"] y CONFIG["vigencia_liq"] via
nombres_series(): el ano entrante se corren esos dos numeros y el libro entero
queda renombrado.

Que entra
---------
Solo los predios de UNA SOLA construccion. Son los unicos que se pueden
comparar enteros: en un predio con varias, el VTER y el VALOANEX vienen
repetidos en cada fila y no hay forma de repartirlos por tabla, y el VALORCONS
de la base tampoco se lee contra un solo VM2. El VM2 y el avaluo salen ahora
del mismo universo, asi que las dos hojas hablan de los mismos predios.

Ademas, ese predio tiene que TENER una construccion valorada (area, valor y
puntaje) y su construccion tiene que salir de la TABLA DE VALOR EN LAS DOS
VIGENCIAS. Que el VM2 2026 salga de la tabla no alcanza: si el VALORCONS de la
base venia de un valor especial o integral, se estarian restando dos cosas
distintas. Por eso tambien quedan fuera las construcciones con ESPECIAL = 1 en
la base, con ESPECIAL_2026 = 1, y las de predios con METODO_LIQUIDACION
INTEGRAL o MIXTO: traian un VM2 de vigencia mediano de ~3.5 millones contra
~0.7 de las normales (VALORCONS incluye el terreno), y entraban al reporte
como caidas del 45% que no eran de la tabla.

El detalle de los tres filtros esta en filtrar_comparables(), que ademas
informa cuanto se llevo cada uno. Con CONFIG["solo_una_construccion"] = False
(o --con-varias-construcciones) vuelven los predios de varias, y con
CONFIG["solo_valor_de_tabla"] = False (o --sin-filtro-tablas) se deja de mirar
como quedo valorada la vigencia.

Una tabla que todavia no se entrego (hoy T3_COMERCIAL y T4_INDUSTRIAL: el
consolidado V1 solo trae columnas T1_RESIDENCIAL y T2_EDIFICIOS) simplemente
no aparece en el reporte, y cuando llegue entra sola sin tocar nada.

VM2 en el parquet es COMERCIAL: el pipeline calcula
    VALORCONS_2026_COM = AREA_CONST * VM2      (Liquidacion_final.py)
    VCONST_2026_CAT    = VALORCONS_2026_COM * 0.7
asi que para comparar contra la base (que esta en catastral) hay que bajar
el comercial con el mismo 0.7. Sin ese factor la comparacion no significa
nada: se estarian restando dos cosas distintas.

A diferencia de comparacion_ofertas.py aqui NO hay cruce que hacer: los dos
valores viven en la misma fila del parquet, uno al lado del otro.

Avaluo
------
Sale de los mismos predios que el VM2, que es como estaba el analisis original
(20250717_preliquidacion3.ipynb, filtro NO_CONST == 1). Las construcciones se
cuentan sobre el PREDIO COMPLETO (N_CONST_PREDIO), no sobre las filas que
pasaron el filtro: un predio con una casa y un parqueadero tiene dos, aunque
al reporte solo llegue la casa. Contandolas mal entraban 27.658 predios cuyo
avaluo reconstruido coincidia con el AVALPRED de la base en el 0.1% de los
casos, contra el 89.1% de los que de verdad tienen una sola construccion.

    AVALUO_VIGENCIA = VTER + VALORCONS + VALOANEX
    AVALUO_LIQ      = VTER + (AREA_CONST * VM2 * 0.7) + VALOANEX

Salidas
-------
El libro repite la estructura del ejercicio del ano pasado
(20250710_Ejercicio_liquidacion_tablas.xlsx): un bloque de percentiles por
TABLA_ORIGEN y ACTIVIDAD_ECONOMICA, con las dos series una al lado de la otra.

    results/COMPARACION_VIGENCIA/COMPARACION_VIGENCIA_<fecha>.xlsx
        General              una fila por tabla y actividad: cuantas bajan
        Resumen VM2          bloques de percentiles 10-100 del VM2
        Resumen Avaluos      lo mismo sobre el avaluo del predio
        Graficos             un cuadro por bloque, seccion VM2 y seccion avaluo
        Reglas               parametros de la corrida y reglas de asignacion
        Conclusiones         lectura de los resultados, armada con los datos
        Comparacion tablas   anexo: una fila por tabla (variacion pareada)
        Rangos variacion     anexo: como se reparte la variacion por tabla
    results/COMPARACION_VIGENCIA/GRAFICOS/VM2/*.png
    results/COMPARACION_VIGENCIA/GRAFICOS/AVALUO/*.png
    output/COMPARACION_VIGENCIA_DETALLE.parquet   (el detalle fila a fila,
        que no cabe comodo en Excel: son cientos de miles de construcciones.
        Lleva ID_PREDIO y numero predial, asi que se queda adentro)
    output/COMPARACION_VIGENCIA_PUBLICO.parquet   (el mismo detalle sin
        identificadores, area ni puntaje: comuna, tabla, actividad y valores.
        Es lo que lee app_vigencias.py y lo unico que sube al repositorio)

Uso
---
    python src/comparacion_vigencia.py
    python src/comparacion_vigencia.py --tolerancia 15
    python src/comparacion_vigencia.py --familias T1_RESIDENCIAL,T2_EDIFICIOS
    python src/comparacion_vigencia.py --sin-filtro-tablas

o desde main.py:
    from comparacion_vigencia import comparacion_vigencia
    comparacion_vigencia(df_liquidacion)
"""

import os
import re
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# El estilo de los graficos y el escritor de Excel se reutilizan del modulo de
# ofertas para que los dos reportes se vean identicos y la paleta viva en un
# solo sitio. De ahi solo se toma presentacion, nada de la logica de ofertas.
from comparacion_ofertas import VIZ, _estilo_ejes, _png_tamano

try:  # pragma: no cover
    from perf import crono
except Exception:  # pragma: no cover
    class _CronoDummy:
        def inicio(self, *a, **k): pass
        def marca(self, *a, **k): pass
        def resumen(self, *a, **k): pass
    crono = _CronoDummy()


RAIZ = Path(__file__).resolve().parent.parent


# =====================================================================
# CONFIGURACION
# =====================================================================
CONFIG = {
    "parquet_liquidacion": str(RAIZ / "output" / "LIQUIDACION_TABLAS.parquet"),
    "carpeta_results": str(RAIZ / "results" / "COMPARACION_VIGENCIA"),
    "parquet_detalle": str(RAIZ / "output" / "COMPARACION_VIGENCIA_DETALLE.parquet"),
    # El mismo detalle sin identificadores, que es lo que lee app_vigencias.py
    # y lo unico de output/ que se versiona (ver .gitignore).
    "parquet_publico": str(RAIZ / "output" / "COMPARACION_VIGENCIA_PUBLICO.parquet"),

    # Comercial -> catastral. Es el mismo 0.7 que aplica Liquidacion_final.py
    # (variable 'confis'). Si alla cambia, cambiar aqui tambien.
    "factor_catastral": 0.7,

    # --- Catastral <-> comercial de la VIGENCIA -------------------------------
    # El avaluo catastral que trae la base es una fraccion del comercial, y esa
    # fraccion depende de si la comuna se actualizo en 2024-2025: en las que si,
    # el catastral quedo al 70% del comercial; en las demas, al 60%. Para leer
    # la vigencia en comercial hay que dividir por ese factor.
    #
    # El TERRENO va siempre por 0.7, en toda la ciudad.
    #
    # En el universo comparable solo aparecen 17 comunas urbanas: las 12 de esta
    # lista mas la 07, 14, 15, 20 y 21, que van por 0.6. Las rurales (51-65) no
    # entran porque ninguna tiene VM2 de tabla todavia.
    "comunas_act_2024_2025": [1, 2, 3, 4, 8, 9, 10, 11, 12, 17, 19, 22],
    "factor_comercial_act": 0.7,      # comunas actualizadas 2024-2025
    "factor_comercial_resto": 0.6,    # las demas
    "factor_comercial_terreno": 0.7,  # el terreno no distingue comuna

    # En que base sale el reporte de Excel: "CATASTRAL" o "COMERCIAL". Las dos
    # se calculan siempre y las dos van al parquet, asi que la app deja cambiar
    # entre ellas sin volver a correr nada; esto solo decide cual se imprime.
    "base_valor": "CATASTRAL",

    # Las dos vigencias que se comparan. La base trae hoy la vigencia 2026 y la
    # liquidacion daria la 2027. De aqui salen TODOS los nombres del reporte
    # (columnas del Excel, series de los graficos y textos), via
    # nombres_series(): el ano que viene se corren estos dos numeros y el libro
    # entero queda renombrado, sin tocar nada mas.
    "vigencia_base": 2026,
    "vigencia_liq": 2027,

    # Familias de tablas que entran al reporte, en orden. Son las dos que trae
    # el consolidado V1: residenciales y edificios. T3_COMERCIAL y
    # T4_INDUSTRIAL existen en TABLA_ORIGEN pero ninguna de sus construcciones
    # tiene VM2 (la tabla no se ha entregado), asi que aunque se listaran aqui
    # se caerian enteras; cuando lleguen, se agregan a esta lista.
    "familias": [("T1_RESIDENCIAL", "RESIDENCIAL"),
                 ("T2_EDIFICIOS", "EDIFICIOS")],

    # Solo entran los predios de UNA SOLA construccion: son los unicos que se
    # pueden comparar de punta a punta (VM2 y avaluo) sin repartir el terreno
    # ni el anexo entre construcciones. Ver filtrar_comparables().
    "solo_una_construccion": True,

    # Solo entran las construcciones cuyo valor sale de la tabla EN LAS DOS
    # vigencias. Ver preparar(): sin esto se cuelan los especiales/integrales,
    # que traen en VALORCONS un valor que no es de tabla (incluye el terreno) y
    # que por eso arrastran la comparacion hacia abajo.
    "solo_valor_de_tabla": True,
    # Metodos de liquidacion 2026 que si son "por tabla". INTEGRAL y MIXTO
    # significan que el predio tiene construcciones que se resuelven completas
    # (terreno incluido), asi que su VALORCONS de base no es un valor de tabla.
    "metodos_de_tabla": ("TABLA + TERRENO", "TABLA SIN TERRENO"),

    "tolerancia_pct": 10.0,        # variacion aceptada antes de marcar fuera
    # Los mismos seis cortes del ejercicio 2025. El 100% es el maximo, no un
    # percentil "alto": sirve para ver hasta donde llega la cola de cada tabla.
    "percentiles": [10, 25, 50, 75, 90, 100],
    "min_predios_bloque": 5,       # con menos predios el bloque no se abre
    "generar_graficos": True,
    "guardar_detalle": True,
}


# Las cuatro series que se pueden comparar: dos medidas (el VM2 de la
# construccion y el avaluo del predio) en dos bases (catastral y comercial).
# Cada entrada es (columna de la vigencia, columna de la liquidacion, prefijo
# con que se nombran las columnas del reporte).
SERIES = {
    ("VM2", "CATASTRAL"): {
        "vig": "VM2_VIGENCIA", "liq": "VM2_LIQ",
        "dif": "DIF_ABS", "var": "VARIACION_PCT", "prefijo": "VM2"},
    ("VM2", "COMERCIAL"): {
        "vig": "VM2_COM_VIGENCIA", "liq": "VM2_COM_LIQ",
        "dif": "DIF_COM_ABS", "var": "VARIACION_COM_PCT", "prefijo": "VM2_COM"},
    ("AVALUO", "CATASTRAL"): {
        "vig": "AVALUO_VIGENCIA", "liq": "AVALUO_LIQ",
        "dif": "DIF_AVALUO", "var": "VARIACION_AVALUO_PCT", "prefijo": "AVALÚO"},
    ("AVALUO", "COMERCIAL"): {
        "vig": "AVALUO_COM_VIGENCIA", "liq": "AVALUO_COM_LIQ",
        "dif": "DIF_AVALUO_COM", "var": "VARIACION_AVALUO_COM_PCT",
        "prefijo": "AVALÚO_COM"},
}


def serie(medida: str) -> dict:
    """
    Que columnas usar para una medida en la base configurada.

    medida es "VM2" o "AVALUO"; la base sale de CONFIG["base_valor"]. Devuelve
    las llaves vig / liq / dif / var / prefijo. Todo el reporte pide las
    columnas por aqui, asi que cambiar de base no toca ninguna otra funcion.
    """
    return SERIES[(medida, CONFIG["base_valor"])]


def factor_comercial(d: pd.DataFrame) -> pd.Series:
    """
    Por cuanto hay que dividir el valor CATASTRAL de cada fila para leerlo en
    comercial: 0.7 en las comunas actualizadas en 2024-2025 y 0.6 en el resto.

    La comuna viene como texto con cero a la izquierda ('07'), asi que se pasa a
    numero antes de comparar contra la lista. Una comuna que no se pueda leer
    como numero cae en el factor del resto, que es el mas conservador: deja el
    valor comercial mas alto y por lo tanto la comparacion menos favorable.
    """
    act = CONFIG["comunas_act_2024_2025"]
    if "COMUNA" not in d.columns:
        return pd.Series(CONFIG["factor_comercial_act"], index=d.index)
    numero = pd.to_numeric(d["COMUNA"], errors="coerce")
    return pd.Series(np.where(numero.isin(act),
                              CONFIG["factor_comercial_act"],
                              CONFIG["factor_comercial_resto"]), index=d.index)


def nombres_series(prefijo: str) -> tuple[str, str, str]:
    """
    Los tres encabezados de un bloque, nombrados POR VIGENCIA.

        nombres_series("VM2") -> ("VM2_VIG_2026", "VM2_VIG_2027",
                                  "VARIACIÓN_VM2_2027_vs_2026")

    El ejercicio del ano pasado los llamaba VM2_2025 / VM2_2026 -el ano de la
    corrida, no el de la vigencia-, y con eso el lector no sabia si "2026" era
    lo que trae la base o lo que daria la liquidacion. Aqui el numero es
    siempre LA VIGENCIA: _VIG_2026 es lo que esta cobrando hoy la base y
    _VIG_2027 lo que quedaria con la liquidacion.

    Lo usan por igual la hoja de Excel y los graficos, para que la etiqueta de
    la curva y el encabezado de la columna no puedan separarse.
    """
    base, liq = CONFIG["vigencia_base"], CONFIG["vigencia_liq"]
    return (f"{prefijo}_VIG_{base}", f"{prefijo}_VIG_{liq}",
            f"VARIACIÓN_{prefijo}_{liq}_vs_{base}")

# Columnas del parquet que se necesitan. Se leen solo estas: el archivo pesa
# ~77 MB y tiene 83 columnas.
COLUMNAS = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID", "USO_LADM",
            "TABLA_ORIGEN", "TIPOLOGIA_ZHF", "ZHF", "COMUNA", "PUNTCONS",
            "ACONCONS", "AREA_CONST", "VALORCONS", "VM2", "VM2_MOD",
            "VM2_ESP_2026", "ESPECIAL_2026", "VTER", "VALOANEX", "VANEXO",
            "AVALPRED",
            # Marcas de como se valoro la construccion a cada lado. Son las que
            # dejan fuera lo que no sale de la tabla (ver preparar()).
            "ESPECIAL", "INTEGRAL", "METODO_LIQUIDACION"]

# Actividad economica de la ZHF donde esta la construccion, leida del mismo
# codigo de tipologia con que se arman las tablas (Liquidacion_tablas.py).
# Es la segunda mitad de la llave de cada bloque: una construccion residencial
# parada en una zona comercial no se comporta como una en zona residencial.
ACTIVIDAD_ZHF = {
    "RESIDENCIAL": ["011", "012", "013", "014", "015", "016"],
    "COMERCIAL":   ["021", "022", "023"],
    "INDUSTRIAL":  ["031", "032", "033"],
}

# Reglas con que la liquidacion 2026 asigna tabla (Liquidacion_tablas.py).
# Van al Excel tal cual, como la hoja "Reglas" del ejercicio anterior.
REGLAS = [
    ("T1_RESIDENCIAL",
     "Casas (001), Barracas (004), Vivienda_Hasta_3_Pisos (012), "
     "Vivienda_Hasta_3_Pisos_En_PH (013), Jardin_Infantil_en_Casa (063)",
     "Construcciones residenciales ubicadas en zonas con actividad economica "
     "residencial", "Tipologias 011 a 016"),
    ("", "", "Construcciones residenciales ubicadas en zonas con actividad "
     "economica diferente a residencial", "Estratos 1 a 6"),
    ("T2_EDIFICIOS", "Apartamentos_4_y_mas_pisos (003)",
     "Construcciones con uso edificios ubicadas en zonas con actividad "
     "economica residencial", "Tipologias 011 a 016"),
    ("", "", "Construcciones con uso edificios ubicadas en zonas con actividad "
     "economica diferente a residencial", "Estratos 1 a 6"),
    ("T3_COMERCIAL",
     "Bodegas_Comerciales_Grandes_Almacenes (016), Estacion_de_servicio (021), "
     "Clubes_Casinos (024), Comercio (025), Oficinas (028), Plaza_Mercado (039), "
     "Restaurantes (041), Talleres (049)",
     "Construcciones comerciales ubicadas en zonas con actividad economica "
     "comercial", "Tipologias 021 a 023"),
    ("", "", "Construcciones comerciales ubicadas en zonas con actividad "
     "economica residencial", "Tipologia 021"),
    ("", "", "Construcciones comerciales ubicadas en zonas diferentes a la "
     "actividad economica residencial y comercial", "Tipologia 022"),
    ("T4_INDUSTRIAL",
     "Salon_Comunal (009), Bodegas_Comerciales_en_PH (018), Industrias (047), "
     "Industrias_en_PH (048)",
     "Construcciones industriales ubicadas en zonas con actividad economica "
     "industrial", "Tipologias 031 a 033"),
    ("", "", "Construcciones industriales ubicadas en zonas con actividad "
     "economica residencial", "Tipologia 031"),
    ("", "", "Construcciones industriales ubicadas en zonas diferentes a la "
     "actividad economica residencial e industrial", "Tipologia 032"),
]



# =====================================================================
# CARGA Y PREPARACION
# =====================================================================
def cargar(df_liq: pd.DataFrame | None = None) -> pd.DataFrame:
    """Toma el df en memoria o lee el parquet, dejando solo las columnas utiles."""
    if df_liq is not None:
        hay = [c for c in COLUMNAS if c in df_liq.columns]
        return df_liq[hay].copy()

    ruta = CONFIG["parquet_liquidacion"]
    if not os.path.exists(ruta):
        raise FileNotFoundError(
            f"No se encontro {ruta}. Ejecute main.py (PASO 4) o pase df_liq."
        )
    print(f"   Leyendo liquidacion: {ruta}")
    try:
        import pyarrow.parquet as pq
        disponibles = set(pq.ParquetFile(ruta).schema_arrow.names)
        usar = [c for c in COLUMNAS if c in disponibles]
        faltan = [c for c in COLUMNAS if c not in disponibles]
        if faltan:
            print(f"   (columnas que no trae el parquet, se omiten: {faltan})")
        return pd.read_parquet(ruta, columns=usar)
    except ImportError:
        return pd.read_parquet(ruta)


def preparar(df: pd.DataFrame) -> pd.DataFrame:
    """
    Deja una fila por construccion con los dos VM2 comparables y su variacion.

    Solo entran las construcciones de las familias configuradas que pasan
    filtrar_comparables(): predio con construccion valorada y valor de tabla en
    las dos vigencias.
    """
    d = df.copy()
    d["TABLA_ORIGEN"] = d["TABLA_ORIGEN"].astype(str)

    # Cuantas construcciones tiene el PREDIO COMPLETO. Se cuenta aqui, antes de
    # cualquier filtro, porque despues ya no se ve: si se cuenta sobre las filas
    # que quedaron, un predio con una casa y un parqueadero pasa por predio de
    # una sola construccion. Los anexos no son construccion, no cuentan.
    if "CONSTRUCCION_ID" in d.columns:
        es_const = d["TABLA_ORIGEN"] != "T10_ANEXOS"
        n_const = d.loc[es_const].groupby("ID_PREDIO")["CONSTRUCCION_ID"].nunique()
        d["N_CONST_PREDIO"] = d["ID_PREDIO"].map(n_const).fillna(0).astype(int)

    prefijos = tuple(p for p, _ in CONFIG["familias"])
    total = len(d)
    d = d[d["TABLA_ORIGEN"].str.startswith(prefijos)].copy()
    print(f"   Construcciones en {', '.join(prefijos)}: {len(d):,} "
          f"(de {total:,} liquidadas)")
    if d.empty:
        return d

    for c in ["ACONCONS", "AREA_CONST", "VALORCONS", "VM2", "VM2_MOD",
              "VM2_ESP_2026", "VTER", "VALOANEX", "VANEXO", "AVALPRED",
              "PUNTCONS"]:
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")

    # Solo el VM2 que salio de la TABLA DE VALOR. Ni el especial ni el del
    # modelo entran: se resuelven por fuera y no dicen nada de la tabla que se
    # esta revisando. Sin esto, una tabla que todavia no existe (el consolidado
    # V1 solo trae T1_RESIDENCIAL y T2_EDIFICIOS) aparecia igual en el reporte,
    # armada con el puñado de especiales que si tenian valor.
    solo_esp = (int(((d["VM2"] <= 0) & (d["VM2_ESP_2026"] > 0)).sum())
                if "VM2_ESP_2026" in d.columns else 0)

    # --- Las dos bases, calculadas siempre ----------------------------------
    # El VM2 del parquet ya es COMERCIAL (asi lo deja Liquidacion_tablas.py),
    # asi que la liquidacion en comercial es el VM2 tal cual, y en catastral es
    # ese mismo VM2 por 0.7. La vigencia va al reves: VALORCONS es catastral, y
    # para leerlo en comercial hay que dividir por el factor de la comuna.
    factor = CONFIG["factor_catastral"]
    d["F_COMERCIAL"] = factor_comercial(d)
    d["ACTUALIZACION"] = np.where(
        d["F_COMERCIAL"] == CONFIG["factor_comercial_act"],
        "ACT 2024-2025", "SIN ACTUALIZAR")

    d["VM2_COM_LIQ"] = d["VM2"]                             # comercial, 2027
    d["VM2_LIQ"] = d["VM2_COM_LIQ"] * factor                # catastral, 2027
    d["VM2_VIGENCIA"] = d["VALORCONS"] / d["ACONCONS"]      # catastral, hoy
    d["VM2_COM_VIGENCIA"] = d["VM2_VIGENCIA"] / d["F_COMERCIAL"]   # comercial, hoy

    # Cuantas se caen por familia por no tener VM2 de tabla. Es la forma de ver
    # que tablas no llegaron todavia: T3_COMERCIAL y T4_INDUSTRIAL se caen
    # completas mientras el consolidado siga trayendo solo T1 y T2. Va al Excel,
    # no solo a la consola.
    sin_vm2 = d.loc[d["VM2_LIQ"] <= 0, "TABLA_ORIGEN"]
    por_familia = {}
    for prefijo, _ in CONFIG["familias"]:
        n = int(sin_vm2.str.startswith(prefijo).sum())
        if n:
            por_familia[prefijo] = n

    antes = len(d)
    d, descartes = filtrar_comparables(d)
    d.attrs["excluidas_sin_vm2"] = por_familia
    d.attrs["descartes"] = descartes
    print(f"   Comparables (predio de una construccion, con valor de tabla en "
          f"las dos vigencias): {len(d):,} de {antes:,}")
    for motivo, n in descartes.items():
        if n:
            print(f"      - {motivo}: {n:,}")
    if solo_esp:
        print(f"      (de las que no traen VM2 de tabla, {solo_esp:,} si tienen "
              f"valor especial 2026; tampoco entran)")
    if d.empty:
        return d

    # La variacion se calcula en las DOS bases y con nombres distintos, para que
    # el parquet las lleve las dos y la app pueda cambiar de una a otra sin
    # volver a correr esto. Ojo: en comercial la variacion NO es la misma que en
    # catastral, porque el factor de la vigencia (0.7 o 0.6) no es el mismo 0.7
    # con que se baja la liquidacion.
    for base in ("", "_COM"):
        vig, liq = f"VM2{base}_VIGENCIA", f"VM2{base}_LIQ"
        d[f"DIF{base}_ABS"] = d[liq] - d[vig]
        d[f"VARIACION{base}_PCT"] = d[f"DIF{base}_ABS"] / d[vig] * 100

    # Sentido, tolerancia y rangos van sobre la base que se este reportando.
    activa = serie("VM2")
    d["VARIACION_PCT_ABS"] = d[activa["var"]].abs()
    d["SENTIDO"] = np.select(
        [d[activa["dif"]] > 0, d[activa["dif"]] < 0],
        ["SUBE con la liquidacion", "BAJA con la liquidacion"], default="IGUAL")
    d["FUERA_TOLERANCIA"] = d["VARIACION_PCT_ABS"] > CONFIG["tolerancia_pct"]
    d["RANGO_VARIACION"] = pd.cut(
        d[activa["var"]],
        bins=[-np.inf, -50, -25, -10, 10, 25, 50, np.inf],
        labels=["baja mas de 50%", "baja 25-50%", "baja 10-25%",
                "estable (±10%)", "sube 10-25%", "sube 25-50%", "sube mas de 50%"])

    # Valor de construccion (para dimensionar el impacto, no solo el VM2).
    # El comercial es el area por el VM2 tal cual, sin bajarlo con el 0.7.
    d["VALORCONS_COM_LIQ"] = d["AREA_CONST"] * d["VM2_COM_LIQ"]
    d["VALORCONS_LIQ"] = d["VALORCONS_COM_LIQ"] * factor
    d["DIF_VALORCONS"] = d["VALORCONS_LIQ"] - d["VALORCONS"]

    # Llave de los bloques del reporte: tabla + actividad economica de la ZHF.
    d["ACTIVIDAD_ECONOMICA"] = actividad_economica(d)
    d["CLAVE"] = d["TABLA_ORIGEN"] + "_" + d["ACTIVIDAD_ECONOMICA"]
    print(f"   Bloques (tabla x actividad): {d['CLAVE'].nunique()}")
    return d


def filtrar_comparables(d: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """
    Deja solo las construcciones que se pueden comparar contra la tabla, y
    devuelve (df, motivos) con cuantas se llevo cada motivo.

    Tres condiciones, y las tres hacen falta:

    1) El predio tiene UNA SOLA construccion (N_CONST_PREDIO == 1, contada
       sobre el predio completo en preparar()). Es el unico caso que se puede
       comparar entero: en un predio con varias, el VTER y el VALOANEX vienen
       repetidos en cada fila y no hay forma de repartirlos por tabla sin
       inventar un criterio, y el VALORCONS de la base tampoco se puede leer
       contra un solo VM2 de tabla. Antes esto solo se aplicaba al avaluo y el
       VM2 se comparaba sobre todas; ahora el reporte completo sale del mismo
       universo, asi que la hoja de VM2 y la de avaluo hablan de los mismos
       predios.

    2) Ese predio TIENE una construccion valorada: area, valor de construccion
       y puntaje. Sin cualquiera de los tres no hay VM2 de vigencia que sacar
       (VALORCONS / ACONCONS), asi que el predio no entra.

    3) Esa construccion TIENE RELACION CON LA TABLA DE VALOR en las dos
       vigencias, no en una sola:

         - 2026: el VM2 salio del cruce con la tabla (VM2 > 0) y no de un
           valor especial (ESPECIAL_2026 = 1). Esta mitad ya estaba.
         - vigencia: el VALORCONS de la base tambien salio de una tabla. Es la
           mitad que faltaba. En la base, ESPECIAL = 1 marca las
           construcciones valoradas por fuera de las tablas -y las integrales,
           INTEGRAL = 1, que son un subconjunto-, donde VALORCONS trae terreno
           y construccion en un solo numero. Su VM2 de vigencia mediano da
           ~3.5 millones contra ~0.7 de las normales, asi que entraban al
           reporte como caidas del 45% que no dicen nada de la tabla.
         - predio: METODO_LIQUIDACION INTEGRAL o MIXTO significa que el predio
           tiene construcciones que se resuelven completas, y su valor de base
           arrastra lo mismo aunque la construccion quede clasificada en una
           tabla.

    Los motivos se aplican EN CASCADA: cada uno cuenta solo lo que no se habia
    caido antes, para que la suma de por resultado el total descartado y no un
    numero inflado por los solapes (un especial suele fallar tres condiciones
    a la vez).

    Con CONFIG["solo_una_construccion"] = False vuelven los predios de varias
    construcciones (el avaluo los sigue dejando fuera por su cuenta), y con
    CONFIG["solo_valor_de_tabla"] = False se salta la condicion 3 sobre la
    vigencia.
    """
    def _marca(col: str) -> pd.Series:
        """La columna leida como bandera 0/1; todo en False si no viene."""
        if col not in d.columns:
            return pd.Series(False, index=d.index)
        return pd.to_numeric(d[col], errors="coerce").fillna(0) == 1

    def _falta(col: str) -> pd.Series:
        """True donde la columna no es un numero positivo."""
        if col not in d.columns:
            return pd.Series(False, index=d.index)
        return ~(pd.to_numeric(d[col], errors="coerce") > 0)

    reglas = []
    if CONFIG["solo_una_construccion"] and "N_CONST_PREDIO" in d.columns:
        reglas.append(("el predio tiene mas de una construccion (no se puede "
                       "repartir terreno ni anexo)", d["N_CONST_PREDIO"] != 1))
    reglas += [
        ("sin area de construccion (ACONCONS <= 0)", _falta("ACONCONS")),
        ("sin valor de construccion en la base (VALORCONS <= 0)",
         _falta("VALORCONS")),
        ("sin puntaje de construccion (PUNTCONS <= 0)", _falta("PUNTCONS")),
        ("sin VM2 de tabla en 2026 (VM2 <= 0)", _falta("VM2_LIQ")),
    ]

    if CONFIG["solo_valor_de_tabla"]:
        if "METODO_LIQUIDACION" in d.columns:
            metodo = d["METODO_LIQUIDACION"].astype(str).str.strip().str.upper()
            validos = [m.upper() for m in CONFIG["metodos_de_tabla"]]
            fuera_metodo = ~metodo.isin(validos)
        else:
            fuera_metodo = pd.Series(False, index=d.index)
        reglas += [
            ("valorada por fuera de tabla en la vigencia (ESPECIAL = 1)",
             _marca("ESPECIAL")),
            ("con valor especial en 2026 (ESPECIAL_2026 = 1)",
             _marca("ESPECIAL_2026")),
            ("predio no liquidado por tabla (METODO_LIQUIDACION INTEGRAL/MIXTO)",
             fuera_metodo),
        ]

    vivos = pd.Series(True, index=d.index)
    motivos: dict[str, int] = {}
    for motivo, fuera in reglas:
        cae = vivos & fuera.fillna(True)
        motivos[motivo] = int(cae.sum())
        vivos &= ~cae
    return d[vivos].copy(), motivos


def actividad_economica(d: pd.DataFrame) -> pd.Series:
    """
    RESIDENCIAL / COMERCIAL / INDUSTRIAL / OTRAS segun la tipologia de la ZHF.

    La tipologia son los ULTIMOS TRES digitos del codigo de ZHF, no los de una
    posicion fija. El campo TIPOLOGIA_ZHF que trae el parquet sale de
    ZHF.str[8:11] (Liquidacion_tablas.py), que solo cae bien cuando el codigo
    tiene 11 caracteres: los de 13 quedan corridos dos posiciones y producen
    codigos inexistentes (110, 210, 310...) que aqui se leerian como OTRAS.
    Por eso se lee el ZHF directo y TIPOLOGIA_ZHF queda de respaldo para las
    filas sin codigo utilizable.
    """
    indice = d.index
    codigo = pd.Series("", index=indice, dtype=object)
    if "ZHF" in d.columns:
        z = d["ZHF"].astype(str).str.strip()
        # Menos de 11 caracteres no es un codigo de ZHF (hay filas en '0')
        usable = z.str.len() >= 11
        codigo = codigo.mask(usable, z.str[-3:])
    if "TIPOLOGIA_ZHF" in d.columns:
        respaldo = d["TIPOLOGIA_ZHF"].astype(str).str.strip().str.zfill(3)
        codigo = codigo.where(codigo != "", respaldo)

    condiciones = [codigo.isin(v) for v in ACTIVIDAD_ZHF.values()]
    return pd.Series(np.select(condiciones, list(ACTIVIDAD_ZHF), default="OTRAS"),
                     index=indice)


def preparar_avaluo(d: pd.DataFrame) -> pd.DataFrame:
    """
    Avaluo por predio, SOLO en predios de una sola construccion.

    Con CONFIG["solo_una_construccion"] activo esto ya no quita nada: el filtro
    corre antes, en filtrar_comparables(), y todo el reporte sale de predios de
    una sola construccion. Se deja porque es la garantia de que el avaluo nunca
    se lea sobre predios de varias, aunque se apague aquel filtro.

    En los de varias, VTER y el anexo vienen repetidos por fila y el avaluo no
    se puede atribuir a una tabla sin inventar un reparto. Se devuelve vacio si
    faltan las columnas de terreno o anexo.

    El anexo se toma de VANEXO, no de VALOANEX. VALOANEX es el valor de UNA
    fila de anexo y en la fila de la construccion viene en cero: con el, 41.824
    predios entraban al reporte sin su anexo -uno de ~3.8 millones en la
    mediana- y el avaluo reconstruido solo cuadraba con el AVALPRED de la base
    en el 89.1% de los casos. Con VANEXO, que es el total del predio, cuadra en
    el 99.99%. Si algun dia hay que volver a VALOANEX, es esta linea.

    "Una sola construccion" se cuenta sobre el PREDIO COMPLETO
    (N_CONST_PREDIO, armada en preparar()), no sobre las filas que sobrevivieron
    al filtro. Contandolo sobre las filas filtradas entraban 27.658 predios que
    si tienen otras construcciones -parqueaderos, sobre todo-: su avaluo
    reconstruido coincidia con el AVALPRED de la base en el 0.1% de los casos,
    contra el 89.1% de los que de verdad tienen una sola.
    """
    col_anexo = "VANEXO" if "VANEXO" in d.columns else "VALOANEX"
    faltan = [c for c in ("VTER", col_anexo) if c not in d.columns]
    if faltan or d.empty:
        if faltan:
            print(f"   (sin columnas {faltan}: no se compara avaluo)")
        return pd.DataFrame()

    if "N_CONST_PREDIO" in d.columns:
        una_sola = d["N_CONST_PREDIO"] == 1
    else:   # sin CONSTRUCCION_ID no se puede contar el predio completo
        una_sola = d.groupby("ID_PREDIO")["ID_PREDIO"].transform("size") == 1
    uni = d[una_sola].copy()
    fuera = d["ID_PREDIO"].nunique() - uni["ID_PREDIO"].nunique()
    print(f"   Avaluo: {len(uni):,} predios de una sola construccion"
          + (f" ({fuera:,} con varias quedan fuera)" if fuera else
             " (los mismos de la comparacion de VM2)"))
    if uni.empty:
        return uni

    uni["VTER"] = uni["VTER"].fillna(0)
    anexo = uni[col_anexo].fillna(0)

    # --- Catastral: los tres componentes tal como los trae la base ----------
    uni["AVALUO_VIGENCIA"] = uni["VTER"] + uni["VALORCONS"] + anexo
    uni["AVALUO_LIQ"] = uni["VTER"] + uni["VALORCONS_LIQ"] + anexo

    # --- Comercial: cada componente dividido por su factor -------------------
    # El terreno va siempre por 0.7; la construccion y el anexo, por el factor
    # de la comuna (0.7 si se actualizo en 2024-2025, 0.6 si no). La liquidacion
    # solo cambia la construccion: terreno y anexo son los mismos a los dos
    # lados, igual que en la version catastral.
    f_ter = CONFIG["factor_comercial_terreno"]
    f_com = uni["F_COMERCIAL"]
    terreno_anexo_com = uni["VTER"] / f_ter + anexo / f_com
    uni["AVALUO_COM_VIGENCIA"] = terreno_anexo_com + uni["VALORCONS"] / f_com
    uni["AVALUO_COM_LIQ"] = terreno_anexo_com + uni["VALORCONS_COM_LIQ"]

    for base in ("", "_COM"):
        vig, liq = f"AVALUO{base}_VIGENCIA", f"AVALUO{base}_LIQ"
        uni[f"DIF_AVALUO{base}"] = uni[liq] - uni[vig]
        uni[f"VARIACION_AVALUO{base}_PCT"] = np.where(
            uni[vig] > 0, uni[f"DIF_AVALUO{base}"] / uni[vig] * 100, np.nan)

    # Control: el avaluo reconstruido deberia parecerse al AVALPRED de la base.
    # Si no se parece, la base trae componentes que aqui no se estan sumando.
    if "AVALPRED" in uni.columns:
        ap = pd.to_numeric(uni["AVALPRED"], errors="coerce")
        ok = ap > 0
        if ok.any():
            desvio = ((uni.loc[ok, "AVALUO_VIGENCIA"] - ap[ok]).abs() / ap[ok])
            print(f"   (control: el avaluo reconstruido queda a menos de 1% del "
                  f"AVALPRED de la base en {(desvio <= 0.01).mean() * 100:.1f}% "
                  f"de los predios)")
    return uni


# =====================================================================
# TABLAS DEL REPORTE
# =====================================================================
def resumen_por_tabla(d: pd.DataFrame) -> pd.DataFrame:
    """Una fila por tabla de liquidacion: cuanto se mueve y cuanto se sale."""
    if d.empty:
        return pd.DataFrame()
    s = serie("VM2")
    g = d.groupby("TABLA_ORIGEN")
    out = pd.DataFrame({
        "CONSTRUCCIONES": g.size(),
        "PREDIOS": g["ID_PREDIO"].nunique(),
        "VM2_VIGENCIA_P50": g[s["vig"]].median(),
        "VM2_LIQ_P50": g[s["liq"]].median(),
        "VAR_PCT_P50": g[s["var"]].median(),
        "VAR_PCT_PROM": g[s["var"]].mean(),
        "PCT_SUBEN": g[s["dif"]].apply(lambda x: (x > 0).mean() * 100),
        "PCT_BAJAN": g[s["dif"]].apply(lambda x: (x < 0).mean() * 100),
        "FUERA_TOLERANCIA": g["FUERA_TOLERANCIA"].sum(),
        "IMPACTO_TOTAL": g["DIF_VALORCONS"].sum(),
    })
    out["PCT_FUERA_TOLERANCIA"] = out["FUERA_TOLERANCIA"] / out["CONSTRUCCIONES"] * 100
    return out.reset_index()


def bloques_percentiles(d: pd.DataFrame, col_vig: str, col_liq: str,
                        nombres: tuple[str, str, str]) -> dict:
    """
    Un DataFrame de percentiles por bloque (tabla x actividad economica), con
    las mismas cinco columnas del ejercicio 2025 y los encabezados que arma
    nombres_series():

        PERCENTIL | <serie>_VIG_<base> | <serie>_VIG_<liq> | VARIACIÓN_... |
        NUM_PREDIOS

    NUM_PREDIOS es el conteo ACUMULADO de predios del bloque (percentil x total
    de predios), igual que el ano pasado: dice cuantos predios quedan por
    debajo de ese corte, no cuantos hay en el corte.

    OJO: cada serie se ordena POR SEPARADO. El p90 de una vigencia y el p90 de
    la otra no son la misma construccion, asi que esto compara distribuciones,
    no casos. La variacion pareada (construccion contra si misma) esta en la
    hoja "Comparacion tablas".
    """
    bloques = {}
    if d.empty:
        return bloques
    c_base, c_liq, c_var = nombres
    minimo = CONFIG["min_predios_bloque"]
    chicos = []
    for clave, s in d.groupby("CLAVE"):
        v = pd.to_numeric(s[col_vig], errors="coerce").dropna()
        l = pd.to_numeric(s[col_liq], errors="coerce").dropna()
        predios = int(s["ID_PREDIO"].nunique())
        if v.empty or l.empty:
            continue
        if predios < minimo:
            chicos.append(f"{clave} (n={predios})")
            continue
        filas = []
        for p in CONFIG["percentiles"]:
            pv, pl = float(np.percentile(v, p)), float(np.percentile(l, p))
            filas.append({
                "PERCENTIL": f"{p}%",
                c_base: pv,
                c_liq: pl,
                # Fraccion, no porcentaje: Excel la formatea con 0.0%
                c_var: (pl / pv - 1) if pv else np.nan,
                "NUM_PREDIOS": int(round(p / 100 * predios)),
            })
        bloques[str(clave)] = pd.DataFrame(filas)
    if chicos:
        print(f"      (bloques con menos de {minimo} predios, no se abren: "
              f"{', '.join(chicos)})")
    return bloques


def resumen_general(d: pd.DataFrame, aval: pd.DataFrame) -> pd.DataFrame:
    """
    La hoja General del ejercicio 2025: una fila por tabla y actividad con
    cuantas construcciones bajan y cuantas suben, mas la misma lectura sobre
    el avaluo de los predios de una sola construccion.
    """
    if d.empty:
        return pd.DataFrame()

    s_vm2, s_aval = serie("VM2"), serie("AVALUO")
    g = d.groupby(["TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA"])
    out = pd.DataFrame({
        "TOTAL": g.size(),
        "PREDIOS": g["ID_PREDIO"].nunique(),
        "BAJARON": g[s_vm2["dif"]].apply(lambda x: int((x < 0).sum())),
        "SUBIERON": g[s_vm2["dif"]].apply(lambda x: int((x > 0).sum())),
        "VARIACION_VM2_P50": g[s_vm2["var"]].median().round(1),
    })
    out["%_BAJARON"] = (out["BAJARON"] / out["TOTAL"] * 100).round(1)
    out["%_SUBIERON"] = (out["SUBIERON"] / out["TOTAL"] * 100).round(1)

    if aval is not None and not aval.empty:
        ga = aval.groupby(["TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA"])
        out["PREDIOS_AVALUO"] = ga.size()
        out["BAJARON_AVALUO"] = ga[s_aval["dif"]].apply(
            lambda x: int((x < 0).sum()))
        out["VARIACION_AVALUO_P50"] = ga[s_aval["var"]].median().round(1)
        out["%_BAJARON_AVALUO"] = (out["BAJARON_AVALUO"]
                                   / out["PREDIOS_AVALUO"] * 100).round(1)

    out = out.reset_index().rename(columns={"TABLA_ORIGEN": "CATEGORIA"})
    orden = ["CATEGORIA", "ACTIVIDAD_ECONOMICA", "TOTAL", "PREDIOS",
             "BAJARON", "%_BAJARON", "SUBIERON", "%_SUBIERON",
             "VARIACION_VM2_P50", "PREDIOS_AVALUO", "BAJARON_AVALUO",
             "%_BAJARON_AVALUO", "VARIACION_AVALUO_P50"]
    return out[[c for c in orden if c in out.columns]]


def conclusiones(d: pd.DataFrame, aval: pd.DataFrame) -> list[tuple[str, str]]:
    """
    La hoja Conclusiones, redactada con los numeros de la corrida.

    El ano pasado ese texto se escribio a mano; aqui se arma solo para que no
    quede desfasado del dato cada vez que se vuelve a correr la liquidacion.
    Devuelve una lista de (SECCION, TEXTO); las secciones en mayuscula son los
    titulos de banda.
    """
    filas: list[tuple[str, str]] = []
    v_base, v_liq = CONFIG["vigencia_base"], CONFIG["vigencia_liq"]

    def _lectura(sub: pd.DataFrame, col_var: str, unidad: str) -> str:
        var = pd.to_numeric(sub[col_var], errors="coerce").dropna()
        if var.empty:
            return "sin datos suficientes."
        p50 = var.median()
        baja = (var < 0).mean() * 100
        # Medio punto de decima no es "sube": con volumenes de este tamano la
        # mediana casi nunca da cero exacto y decirlo asi seria sobreleer.
        sentido = (f"practicamente no se mueve frente a la vigencia {v_base}"
                   if abs(p50) < 0.05
                   else f"queda por debajo de la vigencia {v_base}" if p50 < 0
                   else f"queda por encima de la vigencia {v_base}")
        # Que categoria se mueve mas, para no dejar la conclusion en el promedio
        por_cat = sub.groupby("CLAVE")[col_var].median().sort_values()
        extremos = ""
        if len(por_cat) > 1:
            extremos = (f" El extremo bajo es {por_cat.index[0]} "
                        f"({por_cat.iloc[0]:+.2f}%) y el alto "
                        f"{por_cat.index[-1]} ({por_cat.iloc[-1]:+.2f}%).")
        return (f"*El valor de la vigencia {v_liq} {sentido}: variacion mediana "
                f"caso a caso {p50:+.2f}% sobre {len(var):,} {unidad}, y baja "
                f"en el {baja:.1f}% de los casos.{extremos}")

    filas.append(("VM2 CATASTRAL", ""))
    for prefijo, familia in CONFIG["familias"]:
        sub = d[d["TABLA_ORIGEN"].str.startswith(prefijo)]
        if sub.empty:
            continue
        filas.append((familia,
                      _lectura(sub, serie("VM2")["var"], "construcciones")))
    filas.append(("TOTAL",
                  _lectura(d, serie("VM2")["var"], "construcciones")))

    if aval is not None and not aval.empty:
        filas.append(("AVALUO CATASTRAL", ""))
        for prefijo, familia in CONFIG["familias"]:
            sub = aval[aval["TABLA_ORIGEN"].str.startswith(prefijo)]
            if sub.empty:
                continue
            filas.append((familia,
                          _lectura(sub, serie("AVALUO")["var"], "predios")))
        filas.append(("TOTAL",
                      _lectura(aval, serie("AVALUO")["var"], "predios")))
        filas.append(("NOTA", "*El avaluo solo se lee en predios de una sola "
                              "construccion: en los de varias, el terreno y el "
                              "anexo no se pueden repartir por tabla."))
    return filas


def seleccion_por_comuna(d: pd.DataFrame) -> pd.DataFrame:
    """
    Que quedo seleccionado y donde esta: una fila por comuna.

    Responde "sobre que predios se armo este reporte", que es lo primero que
    pregunta quien lo recibe. Trae el factor con que se paso a comercial, para
    que se vea de una que las comunas actualizadas y las que no se convierten
    distinto.
    """
    if d.empty or "COMUNA" not in d.columns:
        return pd.DataFrame()
    s = serie("VM2")
    g = d.groupby("COMUNA")
    out = pd.DataFrame({
        "CONSTRUCCIONES": g.size(),
        "PREDIOS": g["ID_PREDIO"].nunique(),
        "ACTUALIZACION": g["ACTUALIZACION"].first(),
        "FACTOR_COMERCIAL": g["F_COMERCIAL"].first(),
        "T1_RESIDENCIAL": g["TABLA_ORIGEN"].apply(
            lambda x: int(x.str.startswith("T1_RESIDENCIAL").sum())),
        "T2_EDIFICIOS": g["TABLA_ORIGEN"].apply(
            lambda x: int(x.str.startswith("T2_EDIFICIOS").sum())),
        "VM2_VIGENCIA_P50": g[s["vig"]].median().round(0),
        "VM2_LIQ_P50": g[s["liq"]].median().round(0),
        "VAR_PCT_P50": g[s["var"]].median().round(2),
        "PCT_BAJAN": g[s["dif"]].apply(lambda x: round((x < 0).mean() * 100, 1)),
    })
    out["%_DEL_TOTAL"] = (out["CONSTRUCCIONES"] / len(d) * 100).round(2)
    return out.reset_index().sort_values("CONSTRUCCIONES", ascending=False)


def rangos_variacion(d: pd.DataFrame) -> pd.DataFrame:
    """Como se reparten las construcciones entre los rangos de variacion."""
    if d.empty:
        return pd.DataFrame()
    t = (pd.crosstab(d["TABLA_ORIGEN"], d["RANGO_VARIACION"])
           .reset_index().rename_axis(None, axis=1))
    cols = [c for c in t.columns if c != "TABLA_ORIGEN"]
    t["TOTAL"] = t[cols].sum(axis=1)
    return t


# =====================================================================
# EXCEL
# =====================================================================
def _sin_tildes(texto: str) -> str:
    """Para comparar encabezados sin depender de si traen tilde."""
    return (str(texto).upper()
            .replace("Á", "A").replace("É", "E").replace("Í", "I")
            .replace("Ó", "O").replace("Ú", "U"))


def _hoja_bloques(libro, hoja, bloques: dict) -> None:
    """
    Escribe un bloque por tabla y actividad: titulo, encabezados y percentiles.

    Todos los bloques de una misma tabla (T1, T2, T3...) van uno al lado del
    otro y cada tabla abre una banda nueva, que es como quedaba el resumen del
    ejercicio 2025 (una tablita por bloque, no una fila larga por percentil).
    """
    f_tit = libro.add_format({"bold": True, "font_size": 12})
    f_head = libro.add_format({"bold": True, "align": "center", "valign": "vcenter",
                               "text_wrap": True, "border": 1, "bg_color": "#DDEBF7"})
    base = {"align": "center", "valign": "vcenter", "border": 1}
    f_txt = libro.add_format(base)
    f_money = libro.add_format({**base, "num_format": '"$"#,##0'})
    f_pct = libro.add_format({**base, "num_format": "0.0%"})
    f_int = libro.add_format({**base, "num_format": "#,##0"})

    def _formato(col: str):
        c = _sin_tildes(col)
        if "VARIACION" in c:
            return f_pct
        if "PREDIOS" in c:
            return f_int
        if "VM2" in c or "AVALUO" in c:
            return f_money
        return f_txt

    hoja.hide_gridlines(2)
    fila = 0
    for _, claves in _por_tabla(bloques):
        col, alto = 0, 0
        for clave in claves:
            df = bloques[clave]
            hoja.write(fila, col, clave, f_tit)
            for j, h in enumerate(df.columns):
                hoja.write(fila + 1, col + j, str(h), f_head)
                hoja.set_column(col + j, col + j, 17)
            for r, (_, row) in enumerate(df.iterrows(), start=2):
                for j, h in enumerate(df.columns):
                    v = row[h]
                    if pd.isna(v):
                        hoja.write_blank(fila + r, col + j, None, _formato(h))
                    else:
                        hoja.write(fila + r, col + j, v, _formato(h))
            alto = max(alto, 2 + len(df))
            col += len(df.columns) + 1        # una columna de aire entre bloques
        fila += alto + 3                      # y tres filas entre tablas


def _por_tabla(claves) -> list:
    """
    Agrupa las claves por numero de tabla (T1, T2, ...) y las devuelve en ese
    orden, con las de cada tabla ordenadas alfabeticamente. Lo que no empieza
    por T<numero> va al final para no perderlo en silencio.
    """
    grupos: dict = {}
    for clave in claves:
        m = re.match(r"T(\d+)", str(clave))
        grupos.setdefault(int(m.group(1)) if m else 999, []).append(str(clave))
    return [(n, sorted(v)) for n, v in sorted(grupos.items())]


def _hoja_graficos(libro, hoja, secciones: dict, ancho_px: int = 430,
                   por_fila: int = 3) -> None:
    """
    Pega los PNG en grilla, con el nombre del bloque encima de cada imagen y
    una seccion por tanda (VM2 y avaluo), como en el reporte del ano pasado.

    secciones: {"VM2 CATASTRAL": [(clave, ruta), ...], ...}
    """
    f_sec = libro.add_format({"bold": True, "font_size": 14, "font_color": "#2F5496"})
    f_tit = libro.add_format({"bold": True, "font_size": 9})
    ANCHO_COL = 12                       # caracteres; ~89 px
    PX_COL = ANCHO_COL * 7.5
    hoja.hide_gridlines(2)

    fila = 0
    for titulo, imagenes in secciones.items():
        imagenes = [(n, r) for n, r in imagenes if os.path.exists(r)]
        if not imagenes:
            continue
        hoja.write(fila, 0, f"GRÁFICOS {titulo}", f_sec)
        fila += 2
        col = 0
        alto_fila_bloque = 0
        for k, (nombre, ruta) in enumerate(imagenes):
            ancho_px_img, alto_px_img = _png_tamano(ruta)
            escala = ancho_px / ancho_px_img
            hoja.write(fila, col, nombre, f_tit)
            hoja.insert_image(fila + 1, col, ruta,
                              {"x_scale": escala, "y_scale": escala})
            paso_col = int(np.ceil(ancho_px / PX_COL)) + 1
            for c in range(col, col + paso_col):
                hoja.set_column(c, c, ANCHO_COL)
            alto_fila_bloque = max(alto_fila_bloque,
                                   int(np.ceil(alto_px_img * escala / 20)) + 3)
            col += paso_col
            if (k + 1) % por_fila == 0:      # salto de renglon de la grilla
                col = 0
                fila += alto_fila_bloque
                alto_fila_bloque = 0
        if alto_fila_bloque:
            fila += alto_fila_bloque
        fila += 2


def _hoja_reglas(libro, hoja, parametros: pd.DataFrame) -> None:
    """
    Dos bloques: los parametros con que corrio la comparacion (para que el
    lector sepa que se comparo y con que factor) y la tabla de reglas con que
    la liquidacion asigna tabla a cada construccion.
    """
    f_sec = libro.add_format({"bold": True, "font_size": 14, "font_color": "#2F5496"})
    f_head = libro.add_format({"bold": True, "align": "center", "valign": "vcenter",
                               "text_wrap": True, "border": 1, "bg_color": "#DDEBF7"})
    f_txt = libro.add_format({"valign": "top", "text_wrap": True, "border": 1})
    f_cat = libro.add_format({"bold": True, "valign": "top", "border": 1})
    f_lbl = libro.add_format({"bold": True, "valign": "top", "text_wrap": True,
                              "border": 1})

    hoja.hide_gridlines(2)
    hoja.set_column(0, 0, 34)
    hoja.set_column(1, 1, 46)
    hoja.set_column(2, 2, 52)
    hoja.set_column(3, 3, 26)

    hoja.write(0, 0, "PARÁMETROS DE LA COMPARACIÓN", f_sec)
    fila = 2
    for _, row in parametros.iterrows():
        hoja.write(fila, 0, str(row["CONCEPTO"]), f_lbl)
        valor = row["VALOR"]
        if pd.isna(valor):
            valor = ""
        elif isinstance(valor, np.integer):      # xlsxwriter no traga np.int64
            valor = int(valor)
        elif isinstance(valor, np.floating):
            valor = float(valor)
        hoja.write(fila, 1, valor, f_txt)
        fila += 1

    fila += 2
    hoja.write(fila, 0, "REGLAS DE ASIGNACIÓN DE TABLA (liquidación vigencia "
                        f"{CONFIG['vigencia_liq']})", f_sec)
    fila += 2
    for j, h in enumerate(["CATEGORÍA", "USOS", "CONDICIÓN", "CRITERIO"]):
        hoja.write(fila, j, h, f_head)
    fila += 1
    for categoria, usos, condicion, criterio in REGLAS:
        hoja.write(fila, 0, categoria, f_cat)
        hoja.write(fila, 1, usos, f_txt)
        hoja.write(fila, 2, condicion, f_txt)
        hoja.write(fila, 3, criterio, f_txt)
        fila += 1


def _hoja_conclusiones(libro, hoja, filas: list) -> None:
    """Las conclusiones, con las bandas VM2 / AVALUO como titulo de seccion."""
    f_sec = libro.add_format({"bold": True, "font_size": 14, "font_color": "#2F5496"})
    f_lbl = libro.add_format({"bold": True, "valign": "top", "border": 1,
                              "bg_color": "#DDEBF7"})
    f_txt = libro.add_format({"valign": "top", "text_wrap": True, "border": 1})

    hoja.hide_gridlines(2)
    hoja.set_column(0, 0, 22)
    hoja.set_column(1, 1, 130)
    hoja.write(0, 0, "CONCLUSIONES", f_sec)

    fila = 2
    for etiqueta, texto in filas:
        if not texto:                     # titulo de banda (VM2 / AVALUO)
            fila += 1 if fila > 2 else 0
            hoja.write(fila, 0, etiqueta, f_sec)
            fila += 1
            continue
        hoja.write(fila, 0, etiqueta, f_lbl)
        hoja.write(fila, 1, texto, f_txt)
        hoja.set_row(fila, 30)
        fila += 1


def escribir_excel(general: pd.DataFrame, bloques_vm2: dict, bloques_aval: dict,
                   graficos: dict, parametros: pd.DataFrame, concl: list,
                   anexos: dict, ruta: str) -> str:
    """
    Arma el libro en el orden del ejercicio 2025: General, Resumen VM2,
    Resumen Avaluos, Graficos, Reglas, Conclusiones, y al final los anexos.

    (No se llama 'exportar' porque el orquestador tiene un parametro con ese
    nombre y lo taparia.)
    """
    os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
    if os.path.exists(ruta):
        try:
            with open(ruta, "a+b"):
                pass
        except PermissionError:
            raise PermissionError(
                f"No se pudo sobrescribir '{os.path.basename(ruta)}': el archivo "
                f"esta abierto en Excel.\n   Cierrelo y vuelva a correr el proceso."
            ) from None

    with pd.ExcelWriter(ruta, engine="xlsxwriter") as xw:
        libro = xw.book
        f_head = libro.add_format({"bold": True, "bg_color": "#1F4E78",
                                   "font_color": "white", "border": 1,
                                   "align": "center", "valign": "vcenter",
                                   "text_wrap": True})

        def _tabla(nombre: str, df: pd.DataFrame, filtro: bool = True) -> None:
            if df is None or df.empty:
                return
            d = df.copy()
            for c in d.columns:
                if isinstance(d[c].dtype, pd.CategoricalDtype):
                    d[c] = d[c].astype(str)
            d.to_excel(xw, sheet_name=nombre[:31], index=False)
            ws = xw.sheets[nombre[:31]]
            ws.freeze_panes(1, 0)
            for i, col in enumerate(d.columns):
                ws.write(0, i, str(col), f_head)
                largo = int(d[col].astype(str).str.len().head(500).max() or 12)
                ws.set_column(i, i, min(max(14, largo + 3, len(str(col)) + 3), 40))
            if filtro:
                ws.autofilter(0, 0, len(d), len(d.columns) - 1)

        _tabla("General", general, filtro=False)
        if bloques_vm2:
            _hoja_bloques(libro, libro.add_worksheet("Resumen VM2"), bloques_vm2)
        if bloques_aval:
            _hoja_bloques(libro, libro.add_worksheet("Resumen Avalúos"), bloques_aval)
        if graficos:
            _hoja_graficos(libro, libro.add_worksheet("Gráficos"), graficos)
        _hoja_reglas(libro, libro.add_worksheet("Reglas"), parametros)
        if concl:
            _hoja_conclusiones(libro, libro.add_worksheet("Conclusiones"), concl)
        for nombre, df in anexos.items():
            _tabla(nombre, df)
    return ruta


# =====================================================================
# GRAFICOS
# =====================================================================
def graficos_vigencia(bloques_vm2: dict, bloques_aval: dict,
                      carpeta_base: str, fecha: str) -> dict:
    """
    Un cuadro por bloque, en dos tandas (VM2 y avaluo) y en carpetas separadas.

    Se dibujan los MISMOS numeros que quedaron en las hojas de resumen: se
    reciben los bloques ya calculados en vez de volver a sacar percentiles, asi
    la linea del grafico y la fila de la tabla nunca se contradicen.

    Devuelve {"VM2 CATASTRAL": [(clave, ruta), ...], "AVALÚO CATASTRAL": [...]}
    para que la hoja de Excel pueda armar las dos secciones.
    """
    v_base, v_liq = CONFIG["vigencia_base"], CONFIG["vigencia_liq"]
    base = CONFIG["base_valor"]              # CATASTRAL o COMERCIAL
    etiqueta = base.lower()
    salida = {}
    # Los nombres de las columnas y los de las curvas salen del mismo sitio que
    # los del Excel -serie() y nombres_series()-, para que la leyenda del
    # grafico diga lo mismo que el encabezado de la tabla que tiene al lado y
    # para que los dos cambien juntos al cambiar de base.
    cb, cl, cvar = nombres_series(serie("VM2")["prefijo"])
    vm2 = _tanda_graficos(bloques_vm2, cb, cl, cvar,
                          f"Comparación VM2 {etiqueta}",
                          f"VM2 vigencia {v_base}", f"VM2 vigencia {v_liq}",
                          f"Valor por m² {etiqueta} (millones de pesos)", "VM2",
                          os.path.join(carpeta_base, "VM2"), fecha)
    if vm2:
        salida[f"VM2 {base}"] = vm2
    cb, cl, cvar = nombres_series(serie("AVALUO")["prefijo"])
    aval = _tanda_graficos(bloques_aval, cb, cl, cvar,
                           f"Comparación Avalúo {etiqueta}",
                           f"Avalúo vigencia {v_base}",
                           f"Avalúo vigencia {v_liq}",
                           f"Avalúo {etiqueta} (millones de pesos)", "AVALUO",
                           os.path.join(carpeta_base, "AVALUO"), fecha)
    if aval:
        salida[f"AVALÚO {base}"] = aval
    return salida


def _tanda_graficos(bloques: dict, col_base: str, col_liq: str, col_var: str,
                    titulo: str, serie_base: str, serie_liq: str, ylabel: str,
                    sufijo: str, carpeta: str, fecha: str) -> list:
    """
    Las dos curvas de percentiles de un bloque, una encima de la otra: la
    vigencia que trae la base contra la que daria la liquidacion.

    El eje Y va en millones porque en el avaluo los numeros crudos no caben,
    y el X son los seis cortes de la tabla, no una escala continua.
    """
    if not bloques:
        return []
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import FuncFormatter
    except ImportError:
        print("   ! matplotlib no esta instalado: se omiten los graficos "
              "(pip install matplotlib)")
        return []

    os.makedirs(carpeta, exist_ok=True)
    # Los nombres llevan un consecutivo que cambia cuando cambia el conjunto de
    # bloques (por ejemplo si llega una tabla nueva), asi que sin esto la
    # carpeta se va llenando de PNG huerfanos de corridas anteriores que ya no
    # corresponden a ningun bloque del Excel.
    for viejo in os.listdir(carpeta):
        if viejo.lower().endswith(".png"):
            os.remove(os.path.join(carpeta, viejo))

    plt.rcParams["font.family"] = ["Segoe UI", "DejaVu Sans", "sans-serif"]
    millones = FuncFormatter(lambda v, _: f"{v / 1e6:,.1f}".replace(",", "."))

    generados = []
    orden = [c for _, claves in _por_tabla(bloques) for c in claves]
    for i, clave in enumerate(orden, start=1):
        df = bloques[clave]
        y_base = pd.to_numeric(df[col_base], errors="coerce").to_numpy(dtype=float)
        y_liq = pd.to_numeric(df[col_liq], errors="coerce").to_numpy(dtype=float)
        x = np.arange(len(df))

        predios = int(df["NUM_PREDIOS"].iloc[-1])
        mediana = df.loc[df["PERCENTIL"] == "50%", col_var]
        pie = ("" if mediana.empty or pd.isna(mediana.iloc[0])
               else f"  ·  en la mediana {mediana.iloc[0] * 100:+.1f}%")

        fig, ax = plt.subplots(figsize=(8, 5), facecolor=VIZ["surface"])
        _estilo_ejes(ax, f"{titulo} - {clave}",
                     f"{predios:,} predios{pie}", "Percentil", ylabel)
        # Azul = liquidacion en todo el proyecto (igual que en el reporte de
        # ofertas), naranja = el valor contra el que se compara.
        for y, color, etiqueta in ((y_base, VIZ["serie_2"], serie_base),
                                   (y_liq, VIZ["serie_1"], serie_liq)):
            ax.plot(x, y, color=color, linewidth=2, marker="o", markersize=6,
                    solid_capstyle="round", zorder=3, label=etiqueta,
                    markeredgecolor=VIZ["surface"], markeredgewidth=1.5)

        ax.set_xticks(x)
        ax.set_xticklabels(df["PERCENTIL"], fontsize=10)
        ax.set_xlim(-0.35, len(df) - 0.65)
        tope = float(np.nanmax([y_base.max(), y_liq.max()])) * 1.18
        ax.set_ylim(0, tope if tope > 0 else 1)
        ax.yaxis.set_major_formatter(millones)
        leg = ax.legend(frameon=False, loc="upper left", fontsize=10)
        for t in leg.get_texts():
            t.set_color(VIZ["ink_2"])

        ruta = os.path.join(carpeta, f"{i:02d}_{clave}_{sufijo}_{fecha}.png")
        fig.savefig(ruta, dpi=120, facecolor=VIZ["surface"], bbox_inches="tight")
        plt.close(fig)
        generados.append((clave, ruta))

    print(f"   {len(generados)} graficos en {carpeta}")
    return generados


# =====================================================================
# ORQUESTADOR
# =====================================================================
def comparacion_vigencia(df_liq: pd.DataFrame | None = None,
                         tolerancia_pct: float | None = None,
                         familias: list | None = None,
                         base_valor: str | None = None,
                         solo_una_construccion: bool | None = None,
                         solo_valor_de_tabla: bool | None = None,
                         exportar: bool = True) -> pd.DataFrame:
    """
    Compara el VM2 que daria la liquidacion contra el que hoy trae la base.

    Parametros
    ----------
    df_liq        : DataFrame de construcciones liquidadas. Si es None se lee
                    ./output/LIQUIDACION_TABLAS.parquet
    tolerancia_pct: % de variacion aceptada (default CONFIG)
    familias      : lista de prefijos de tabla, p.ej. ["T1_RESIDENCIAL"]
    base_valor    : "CATASTRAL" (default) o "COMERCIAL". Las dos se calculan
                    siempre; esto decide cual se imprime en el Excel
    solo_una_construccion: False deja entrar tambien los predios de varias
                    construcciones (el avaluo los sigue dejando fuera)
    solo_valor_de_tabla: False deja entrar tambien los especiales e integrales,
                    cuyo valor de base no sale de la tabla (ver
                    filtrar_comparables)
    exportar      : False devuelve el detalle sin escribir Excel ni PNG

    Retorna
    -------
    DataFrame con una fila por construccion comparada.
    """
    if tolerancia_pct is not None:
        CONFIG["tolerancia_pct"] = float(tolerancia_pct)
    if familias:
        CONFIG["familias"] = [(p, p.split("_", 1)[-1]) for p in familias]
    if base_valor is not None:
        if base_valor.upper() not in ("CATASTRAL", "COMERCIAL"):
            raise ValueError("base_valor debe ser CATASTRAL o COMERCIAL, "
                             f"no {base_valor!r}")
        CONFIG["base_valor"] = base_valor.upper()
    if solo_una_construccion is not None:
        CONFIG["solo_una_construccion"] = bool(solo_una_construccion)
    if solo_valor_de_tabla is not None:
        CONFIG["solo_valor_de_tabla"] = bool(solo_valor_de_tabla)

    if df_liq is None:
        crono.inicio("COMPARACION VIGENCIA")

    print("\n" + "=" * 60)
    print("=== COMPARACION VM2: LIQUIDACION 2026 vs VIGENCIA 2026 ===")
    print("=" * 60)
    print(f"\n-- PASO 1: carga y preparacion "
          f"(factor comercial->catastral {CONFIG['factor_catastral']})")

    d = preparar(cargar(df_liq))
    crono.marca("VIGENCIA: carga y preparacion")
    if d.empty:
        print("   ** No hay construcciones comparables. Revise que el parquet "
              "traiga TABLA_ORIGEN de las familias configuradas.")
        return d

    tol = CONFIG["tolerancia_pct"]
    fuera = int(d["FUERA_TOLERANCIA"].sum())
    s_vm2 = serie("VM2")
    print(f"\n-- PASO 2: variaciones (base {CONFIG['base_valor']})")
    print(f"   VM2 vigencia mediano   : {d[s_vm2['vig']].median():,.0f}")
    print(f"   VM2 liquidacion mediano: {d[s_vm2['liq']].median():,.0f}")
    print(f"   Variacion mediana      : {d[s_vm2['var']].median():+.2f}%")
    print(f"   Variacion promedio     : {d[s_vm2['var']].mean():+.2f}%")
    print(f"   Suben / bajan          : "
          f"{(d[s_vm2['dif']] > 0).mean() * 100:.1f}% / "
          f"{(d[s_vm2['dif']] < 0).mean() * 100:.1f}%")
    print(f"   Fuera de tolerancia (±{tol:.1f}%): {fuera:,} "
          f"({fuera / len(d) * 100:.2f}%)")
    print(f"   Impacto en valor de construccion: "
          f"{d['DIF_VALORCONS'].sum() / 1e12:,.2f} billones")

    aval = preparar_avaluo(d)
    crono.marca("VIGENCIA: variaciones y avaluo")

    if not exportar:
        return d

    # --- Tablas del reporte -------------------------------------------------
    print("\n-- PASO 3: tablas del reporte")
    por_tabla = resumen_por_tabla(d)
    s_vm2, s_aval = serie("VM2"), serie("AVALUO")
    bloques_vm2 = bloques_percentiles(d, s_vm2["vig"], s_vm2["liq"],
                                      nombres_series(s_vm2["prefijo"]))
    bloques_aval = (bloques_percentiles(aval, s_aval["vig"], s_aval["liq"],
                                        nombres_series(s_aval["prefijo"]))
                    if not aval.empty else {})
    general = resumen_general(d, aval)
    rangos = rangos_variacion(d)
    seleccion = seleccion_por_comuna(d)
    concl = conclusiones(d, aval)
    print(f"   Bloques de percentiles: {len(bloques_vm2)} de VM2, "
          f"{len(bloques_aval)} de avaluo")

    fecha = datetime.now().strftime("%Y%m%d")
    # Las salidas de la base comercial llevan sufijo para que las dos
    # corridas puedan convivir en la carpeta sin pisarse.
    sufijo = "" if CONFIG["base_valor"] == "CATASTRAL" else "_COMERCIAL"
    os.makedirs(CONFIG["carpeta_results"], exist_ok=True)

    v_base, v_liq = CONFIG["vigencia_base"], CONFIG["vigencia_liq"]
    comercial = CONFIG["base_valor"] == "COMERCIAL"
    f_act, f_resto = CONFIG["factor_comercial_act"], CONFIG["factor_comercial_resto"]
    vm2_base, vm2_liq, _ = nombres_series(s_vm2["prefijo"])
    av_base, av_liq, _ = nombres_series(s_aval["prefijo"])
    filas_resumen = [
        ("Fecha de ejecucion", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Fuente", CONFIG["parquet_liquidacion"]),
        ("Base de valor", CONFIG["base_valor"]),
        ("Que se compara",
         f"lo que daria la liquidacion para la vigencia {v_liq} contra lo que "
         f"trae hoy la base, que es la vigencia {v_base}; los dos en "
         f"{CONFIG['base_valor'].lower()}"),
        ("Nombres de las series",
         f"el numero es LA VIGENCIA, no el ano de la corrida: _VIG_{v_base} es "
         f"lo que cobra hoy la base y _VIG_{v_liq} lo que quedaria con la "
         f"liquidacion (el ejercicio anterior los llamaba VM2_2025 / VM2_2026)"),
        (f"{vm2_base} (base)",
         f"VALORCONS / ACONCONS / factor de la comuna" if comercial
         else "VALORCONS / ACONCONS"),
        (f"{vm2_liq} (liquidacion)",
         "VM2 de tabla, que ya viene comercial" if comercial else
         f"VM2 de tabla x {CONFIG['factor_catastral']}"),
        (f"{av_base} (base)",
         f"VTER/{CONFIG['factor_comercial_terreno']} + (VALORCONS + VANEXO) / "
         f"factor de la comuna" if comercial
         else "VTER + VALORCONS + VANEXO"),
        (f"{av_liq} (liquidacion)",
         f"VTER/{CONFIG['factor_comercial_terreno']} + (AREA_CONST x VM2) + "
         f"VANEXO / factor de la comuna" if comercial
         else f"VTER + (AREA_CONST x VM2 x {CONFIG['factor_catastral']}) + VANEXO"),
        ("Factor catastral -> comercial de la vigencia",
         f"{f_act} en las comunas actualizadas 2024-2025 "
         f"({', '.join(f'{c:02d}' for c in CONFIG['comunas_act_2024_2025'])}) y "
         f"{f_resto} en las demas; el TERRENO va siempre por "
         f"{CONFIG['factor_comercial_terreno']}"),
        ("Predios por factor comercial",
         "; ".join(f"{k}: {v:,}" for k, v in
                   d["ACTUALIZACION"].value_counts().items())
         if "ACTUALIZACION" in d.columns else "n/d"),
        ("NOTA anexo",
         "el avaluo suma VANEXO (el total de anexos del predio) y no VALOANEX "
         "(el valor de UNA fila de anexo, que en la fila de la construccion "
         "viene en cero): con VALOANEX, 41.824 predios entraban sin su anexo y "
         "el avaluo reconstruido solo cuadraba con el AVALPRED de la base en el "
         "89.1% de los casos, contra el 99.99% con VANEXO"),
        ("Familias", ", ".join(p for p, _ in CONFIG["familias"])),
        ("Que predios entran",
         "predios de UNA SOLA construccion (contada sobre el predio completo, "
         "sin anexos), con esa construccion valorada (ACONCONS, VALORCONS y "
         "PUNTCONS > 0) y saliendo de la tabla de valor EN LAS DOS VIGENCIAS"
         + ("" if CONFIG["solo_una_construccion"]
            else " -- FILTRO DE UNA CONSTRUCCION DESACTIVADO en esta corrida")
         + ("" if CONFIG["solo_valor_de_tabla"]
            else " -- FILTRO DE TABLA DESACTIVADO en esta corrida")),
        ("Que predios NO entran",
         "los de varias construcciones (el terreno y el anexo no se pueden "
         "repartir por tabla) y los valorados por fuera de tabla: ESPECIAL = 1 "
         "en la base (incluye los integrales, donde VALORCONS trae terreno y "
         "construccion juntos), ESPECIAL_2026 = 1, y los de predios con "
         "METODO_LIQUIDACION INTEGRAL o MIXTO"),
        ("Descartadas por motivo (en cascada)",
         "; ".join(f"{m}: {n:,}"
                   for m, n in d.attrs.get("descartes", {}).items() if n)
         or "ninguna"),
        ("Bloques del resumen", "TABLA_ORIGEN x ACTIVIDAD_ECONOMICA de la ZHF "
                                "(residencial 011-016, comercial 021-023, "
                                "industrial 031-033, el resto OTRAS)"),
        ("ACTIVIDAD_ECONOMICA", "ultimos 3 digitos del codigo de ZHF; NO se usa "
                                "la columna TIPOLOGIA_ZHF del parquet, que sale "
                                "de una posicion fija (ZHF[9:11]) y queda "
                                "corrida en los codigos de 13 caracteres"),
        ("Percentiles", ", ".join(f"{p}%" for p in CONFIG["percentiles"])),
        ("Minimo de predios por bloque", CONFIG["min_predios_bloque"]),
        ("Tolerancia (%)", tol),
        ("Construcciones comparadas", len(d)),
        ("Predios", d["ID_PREDIO"].nunique()),
        ("Excluidas por no tener VM2 de tabla",
         ", ".join(f"{fam}: {n:,}"
                   for fam, n in d.attrs.get("excluidas_sin_vm2", {}).items())
         or "ninguna"),
        ("Tablas presentes en el reporte",
         ", ".join(sorted(d["TABLA_ORIGEN"].unique()))),
        ("VM2 vigencia mediano", round(d[s_vm2["vig"]].median())),
        ("VM2 liquidacion mediano", round(d[s_vm2["liq"]].median())),
        ("Variacion mediana (%)", round(d[s_vm2["var"]].median(), 2)),
        ("Variacion promedio (%)", round(d[s_vm2["var"]].mean(), 2)),
        ("Construcciones que suben (%)",
         round((d[s_vm2["dif"]] > 0).mean() * 100, 2)),
        ("Construcciones que bajan (%)",
         round((d[s_vm2["dif"]] < 0).mean() * 100, 2)),
        ("Fuera de tolerancia", fuera),
        ("Fuera de tolerancia (%)", round(fuera / len(d) * 100, 2)),
        ("Impacto en valor de construccion", round(d["DIF_VALORCONS"].sum())),
        ("Predios en la comparacion de avaluo", len(aval)),
        ("NOTA percentiles",
         "cada serie se ordena por separado: compara distribuciones, no casos"),
        ("NOTA NUM_PREDIOS",
         "conteo acumulado de predios del bloque (percentil x total de predios); "
         "el VM2 se ordena sobre construcciones, el avaluo sobre predios"),
        ("NOTA avaluo",
         "sale de los mismos predios que el VM2: todo el reporte es de predios "
         "de una sola construccion, contada sobre el predio completo y no sobre "
         "las filas que pasaron el filtro, asi que un predio con casa y "
         "parqueadero no entra"),
    ]
    resumen = pd.DataFrame(filas_resumen, columns=["CONCEPTO", "VALOR"])

    # --- Graficos (antes del Excel: si el xlsx esta abierto, no se pierden) --
    graficos = {}
    if CONFIG["generar_graficos"]:
        print("\n-- PASO 4: graficos")
        # Carpeta propia por base: cada tanda borra los PNG que encuentra, asi
        # que compartirla dejaria en disco los de la ultima corrida y no los
        # que correspondan al libro que se este mirando.
        graficos = graficos_vigencia(
            bloques_vm2, bloques_aval,
            os.path.join(CONFIG["carpeta_results"], f"GRAFICOS{sufijo}"), fecha)
    crono.marca("VIGENCIA: graficos")

    # --- Detalle fila a fila: a parquet, no a Excel -------------------------
    # Este archivo se queda ADENTRO: lleva ID_PREDIO y numero predial nacional
    # de todos los predios comparados. Lo que sale a la app publica es el
    # recorte anonimo que se escribe justo despues.
    if CONFIG["guardar_detalle"]:
        # El avaluo se calcula aparte (solo predios de una construccion), asi
        # que sus columnas -las dos bases- se traen de vuelta al detalle.
        for c in ("AVALUO_VIGENCIA", "AVALUO_LIQ", "DIF_AVALUO",
                  "VARIACION_AVALUO_PCT", "AVALUO_COM_VIGENCIA",
                  "AVALUO_COM_LIQ", "DIF_AVALUO_COM", "VARIACION_AVALUO_COM_PCT"):
            if not aval.empty and c in aval.columns:
                d[c] = aval[c]      # el indice de aval es un subconjunto del de d
        cols = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID",
                "N_CONST_PREDIO", "COMUNA", "ACTUALIZACION", "F_COMERCIAL",
                "USO_LADM", "TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA", "CLAVE",
                "PUNTCONS", "ACONCONS", "AREA_CONST",
                "VALORCONS", "VALORCONS_LIQ", "VALORCONS_COM_LIQ",
                "DIF_VALORCONS",
                "VM2_VIGENCIA", "VM2_LIQ", "DIF_ABS", "VARIACION_PCT",
                "VM2_COM_VIGENCIA", "VM2_COM_LIQ", "DIF_COM_ABS",
                "VARIACION_COM_PCT",
                "SENTIDO", "RANGO_VARIACION", "FUERA_TOLERANCIA",
                "AVALPRED", "AVALUO_VIGENCIA", "AVALUO_LIQ", "DIF_AVALUO",
                "VARIACION_AVALUO_PCT",
                "AVALUO_COM_VIGENCIA", "AVALUO_COM_LIQ", "DIF_AVALUO_COM",
                "VARIACION_AVALUO_COM_PCT"]
        det = d[[c for c in cols if c in d.columns]].copy()
        det["RANGO_VARIACION"] = det["RANGO_VARIACION"].astype(str)
        det.to_parquet(CONFIG["parquet_detalle"], index=False)
        print(f"\n   Detalle fila a fila: {CONFIG['parquet_detalle']} "
              f"({len(det):,} construcciones)")

        # --- Recorte anonimo: es lo unico que sube al repositorio publico ---
        # Sin ID_PREDIO, sin numero predial, sin area ni puntaje: solo la
        # comuna, la tabla, la actividad y los valores. Una fila queda en "un
        # predio de la comuna 17 en T1_RESIDENCIAL_013 que vale tanto", que no
        # identifica a nadie.
        #
        # Va fila a fila y no agregado porque los percentiles se recalculan
        # sobre lo que el usuario filtre: no hay forma de precalcularlos para
        # todas las combinaciones de tabla x comuna x actividad.
        #
        # Se ordena por valor a proposito: asi se pierde el orden original del
        # parquet, que corre en paralelo al del ID_PREDIO y permitiria volver a
        # pegar las filas contra la base fila por fila.
        publicas = ["COMUNA", "ACTUALIZACION", "TABLA_ORIGEN",
                    "ACTIVIDAD_ECONOMICA", "CLAVE",
                    "VM2_VIGENCIA", "VM2_LIQ", "VARIACION_PCT",
                    "AVALUO_VIGENCIA", "AVALUO_LIQ", "VARIACION_AVALUO_PCT",
                    "VM2_COM_VIGENCIA", "VM2_COM_LIQ", "VARIACION_COM_PCT",
                    "AVALUO_COM_VIGENCIA", "AVALUO_COM_LIQ",
                    "VARIACION_AVALUO_COM_PCT"]
        pub = det[[c for c in publicas if c in det.columns]].copy()

        # Quitar el ID no basta: el valor exacto es una llave igual de buena.
        # La mitad de los avaluos (49.7%) es un numero que aparece una sola vez
        # en todo el archivo, asi que quien tuviera la base podria devolverle el
        # predio a cada fila cruzando por valor. Redondeados casi ninguna fila
        # queda sola -del 49.7% al 1.2% en el avaluo, del 13.0% al 1.5% en el
        # VM2- y los percentiles no se corren mas de 0.07%, que sobre una
        # mediana de 146 millones no se ve.
        redondeo = {"VM2_VIGENCIA": 100, "VM2_LIQ": 100,
                    "VM2_COM_VIGENCIA": 100, "VM2_COM_LIQ": 100,
                    "AVALUO_VIGENCIA": 100_000, "AVALUO_LIQ": 100_000,
                    "AVALUO_COM_VIGENCIA": 100_000, "AVALUO_COM_LIQ": 100_000}
        for col, paso in redondeo.items():
            if col in pub.columns:
                pub[col] = (pub[col] / paso).round() * paso
        # Las variaciones se rehacen sobre los valores ya redondeados: si se
        # copiaran del detalle, la columna no cuadraria con la division de las
        # dos que tiene al lado. Y se cortan a dos decimales, que es como se
        # muestran de todos modos: con el decimal largo la variacion volvia a
        # ser unica en el 25% de las filas, o sea otra llave.
        for vig, liq, var in (("VM2_VIGENCIA", "VM2_LIQ", "VARIACION_PCT"),
                              ("VM2_COM_VIGENCIA", "VM2_COM_LIQ",
                               "VARIACION_COM_PCT"),
                              ("AVALUO_VIGENCIA", "AVALUO_LIQ",
                               "VARIACION_AVALUO_PCT"),
                              ("AVALUO_COM_VIGENCIA", "AVALUO_COM_LIQ",
                               "VARIACION_AVALUO_COM_PCT")):
            if {vig, liq} <= set(pub.columns):
                pub[var] = ((pub[liq] / pub[vig] - 1) * 100).round(2)

        # Y se reordena por valor para perder el orden original del parquet,
        # que corre en paralelo al del ID_PREDIO: sin esto se podrian pegar las
        # dos tablas fila por fila sin necesidad de cruzar por valor.
        pub = pub.sort_values(["COMUNA", "TABLA_ORIGEN", "VM2_VIGENCIA"],
                              kind="stable", ignore_index=True)
        pub.to_parquet(CONFIG["parquet_publico"], index=False)
        print(f"   Recorte publico (sin identificadores): "
              f"{CONFIG['parquet_publico']} ({len(pub):,} filas, "
              f"{len(pub.columns)} columnas)")

    # --- Excel --------------------------------------------------------------
    ruta = os.path.join(CONFIG["carpeta_results"],
                        f"COMPARACION_VIGENCIA{sufijo}_{fecha}.xlsx")
    # Anexos: van despues de Conclusiones para no romper el orden de hojas del
    # ejercicio anterior, pero se siguen escribiendo porque son los unicos que
    # traen la variacion PAREADA (construccion contra si misma).
    anexos = {
        "Seleccion por comuna": seleccion,
        "Comparacion tablas": por_tabla,
        "Rangos variacion": rangos,
    }
    escribir_excel(general, bloques_vm2, bloques_aval, graficos, resumen,
                   concl, anexos, ruta)
    print(f"\n   Excel generado: {ruta}")
    print(f"     General                {len(general):>7,} filas")
    print(f"     Resumen VM2            {len(bloques_vm2):>7,} bloques")
    print(f"     Resumen Avaluos        {len(bloques_aval):>7,} bloques")
    print(f"     Graficos               "
          f"{sum(len(v) for v in graficos.values()):>7,} imagenes")
    print(f"     Reglas                 {len(resumen):>7,} parametros")
    print(f"     Conclusiones           {len(concl):>7,} filas")
    print(f"     Seleccion por comuna   {len(seleccion):>7,} filas")
    print(f"     Comparacion tablas     {len(por_tabla):>7,} filas")
    print(f"     Rangos variacion       {len(rangos):>7,} filas")
    crono.marca("VIGENCIA: exportar excel")

    if df_liq is None:
        crono.resumen()
    return d


def _cli():
    import argparse
    p = argparse.ArgumentParser(
        description="Compara el VM2 liquidado contra el que trae hoy la base.")
    p.add_argument("--tolerancia", type=float, default=None,
                   help="%% de variacion aceptada (default 10)")
    p.add_argument("--familias", default=None,
                   help="prefijos separados por coma, p.ej. T1_RESIDENCIAL,T2_EDIFICIOS")
    p.add_argument("--base", default=None, choices=["catastral", "comercial"],
                   help="en que base sale el reporte (default catastral)")
    p.add_argument("--sin-graficos", action="store_true")
    p.add_argument("--sin-filtro-tablas", action="store_true",
                   help="deja entrar tambien los especiales e integrales, cuyo "
                        "valor de base no sale de la tabla (no recomendado)")
    p.add_argument("--con-varias-construcciones", action="store_true",
                   help="deja entrar tambien los predios de varias "
                        "construcciones, donde el terreno y el anexo no se "
                        "pueden repartir por tabla (no recomendado)")
    a = p.parse_args()
    if a.sin_graficos:
        CONFIG["generar_graficos"] = False
    if a.sin_filtro_tablas:
        CONFIG["solo_valor_de_tabla"] = False
    if a.con_varias_construcciones:
        CONFIG["solo_una_construccion"] = False
    fam = [s.strip() for s in a.familias.split(",")] if a.familias else None
    comparacion_vigencia(tolerancia_pct=a.tolerancia, familias=fam,
                         base_valor=a.base)


if __name__ == "__main__":
    _cli()
