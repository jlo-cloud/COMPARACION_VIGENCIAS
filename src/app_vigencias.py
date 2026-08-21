"""
=====================================================================
COMPARACION DE VIGENCIAS - version interactiva (Streamlit)
=====================================================================

Lo mismo que entrega comparacion_vigencia.py en Excel, pero como app: se abre
en el navegador desde cualquier PC con el enlace y los percentiles y los
graficos se recalculan sobre lo que el usuario filtre. En el libro de Excel los
bloques vienen fijos (tabla x actividad economica); aqui se puede pedir, por
ejemplo, el percentil 90 de la comuna 17 en T1_RESIDENCIAL_013, que en el Excel
no existe y habria que sacarlo a mano.

Dos hojas, con los mismos filtros al lado en las dos:

    Tablas          el resumen por grupo -cuantos predios, las dos medianas y
                    cuantos suben o bajan- y los percentiles 10-100, primero
                    del total de la seleccion y despues abiertos por tabla,
                    comuna o actividad economica. Los dos se descargan en CSV.
    Graficos        las mismas dos curvas del reporte, dibujadas sobre lo
                    filtrado, mas el reparto de la variacion.

Arriba se eligen dos cosas y toda la pantalla responde a ellas:

    MEDIDA   VALOR POR M2 de la construccion, VALOR TOTAL CONSTRUIDO (ese m2
             por el area) o AVALUO del predio completo
    BASE     CATASTRAL, que es sobre lo que se cobra, o COMERCIAL, que es lo
             que se estima que vale el inmueble

El comercial de la VIGENCIA sale de dividir el catastral por el factor de la
comuna: 0.7 en las actualizadas en 2024-2025 y 0.6 en las demas (el terreno va
siempre por 0.7). El de la LIQUIDACION no necesita conversion: el VM2 de las
tablas ya viene comercial. Por eso la variacion comercial no es igual a la
catastral -la vigencia se convierte con dos factores distintos segun la comuna
y la liquidacion con uno solo-, y por eso vale la pena mirar las dos.

SOLO SALEN AGREGADOS. No hay hoja de predio a predio ni descarga fila a fila:
la app esta hecha para publicarse abierta, asi que aqui no entran ID_PREDIO,
numero predial, area ni puntaje. Lo mas fino que se puede pedir es un grupo, y
los grupos por debajo del minimo de predios ni siquiera se abren.

Fuente
------
output/COMPARACION_VIGENCIA_PUBLICO.parquet, que escribe comparacion_vigencia.py
al lado del detalle: las mismas filas pero sin identificadores, solo comuna,
tabla, actividad y valores. El detalle completo -ese si con ID_PREDIO y numero
predial- se queda adentro y NO se versiona (ver .gitignore).

Trae solo los predios comparables (una sola construccion y valor de tabla en
las dos vigencias), asi que la app no vuelve a filtrar nada de eso: lo que se
ve aqui es exactamente el universo del reporte.

Uso
---
    python -m streamlit run src/app_vigencias.py

Para publicarla gratis y que se abra con un enlace, ver PUBLICAR al final.
"""

import os
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
RUTA_DATOS = RAIZ / "output" / "COMPARACION_VIGENCIA_PUBLICO.parquet"

# Las dos vigencias salen del modulo que genero el parquet, para que la app no
# quede con los anos escritos a mano cuando alla se corran. Si el import falla
# -en el servidor puede no estar matplotlib, que arrastra comparacion_ofertas-
# se usan los mismos valores por defecto que trae aquel CONFIG.
try:
    from comparacion_vigencia import CONFIG as CONFIG_VIGENCIA
    V_BASE = CONFIG_VIGENCIA["vigencia_base"]
    V_LIQ = CONFIG_VIGENCIA["vigencia_liq"]
except Exception:                                            # pragma: no cover
    V_BASE, V_LIQ = 2026, 2027

# Los mismos seis cortes del reporte y del ejercicio 2025.
PERCENTILES = [10, 25, 50, 75, 90, 100]

# La misma paleta de los PNG del reporte (VIZ en comparacion_ofertas.py):
# azul = liquidacion, naranja = el valor contra el que se compara.
AZUL, NARANJA = "#2a78d6", "#eb6834"

# Que se lee: tres MEDIDAS -el VM2 de la construccion, el valor total
# construido (ese VM2 por el area) y el avaluo del predio- en dos BASES
# (catastral, que es sobre lo que se cobra, o comercial, que es lo que se
# estima que vale). Son seis combinaciones y el parquet trae las seis, asi que
# cambiar de una a otra no vuelve a calcular nada pesado.
#
# El VM2 y el total construido se mueven igual en porcentaje -el area es la
# misma a los dos lados- pero no en pesos: el total dice cuanto vale el
# cambio, el VM2 solo a que precio quedo el metro.
#
# El comercial de la vigencia sale de dividir el catastral por el factor de la
# comuna: 0.7 en las actualizadas en 2024-2025 y 0.6 en el resto. Por eso la
# variacion comercial NO es igual a la catastral: la liquidacion se baja con un
# 0.7 parejo y la vigencia no.
MEDIDAS = {
    "Valor por m² (construcción)": ("VM2", "Valor por m²"),
    "Valor total construido": ("VALORCONS", "Valor total construido"),
    "Avalúo (predio completo)": ("AVALUO", "Avalúo"),
}
BASES = {"Catastral": "CATASTRAL", "Comercial": "COMERCIAL"}

SERIES = {
    ("VALORCONS", "CATASTRAL"): {
        "vig": "VALORCONS_CAT_VIGENCIA", "liq": "VALORCONS_CAT_LIQ",
        "var": "VARIACION_VALORCONS_CAT_PCT", "prefijo": "VALORCONS_CAT"},
    ("VALORCONS", "COMERCIAL"): {
        "vig": "VALORCONS_COM_VIGENCIA", "liq": "VALORCONS_COM_LIQ",
        "var": "VARIACION_VALORCONS_COM_PCT", "prefijo": "VALORCONS_COM"},
    ("VM2", "CATASTRAL"): {
        "vig": "VM2_CAT_VIGENCIA", "liq": "VM2_CAT_LIQ",
        "var": "VARIACION_CAT_PCT", "prefijo": "VM2_CAT"},
    ("VM2", "COMERCIAL"): {
        "vig": "VM2_COM_VIGENCIA", "liq": "VM2_COM_LIQ",
        "var": "VARIACION_COM_PCT", "prefijo": "VM2_COM"},
    ("AVALUO", "CATASTRAL"): {
        "vig": "AVALUO_CAT_VIGENCIA", "liq": "AVALUO_CAT_LIQ",
        "var": "VARIACION_AVALUO_CAT_PCT", "prefijo": "AVALÚO_CAT"},
    ("AVALUO", "COMERCIAL"): {
        "vig": "AVALUO_COM_VIGENCIA", "liq": "AVALUO_COM_LIQ",
        "var": "VARIACION_AVALUO_COM_PCT", "prefijo": "AVALÚO_COM"},
}

# Por que columna se abren los percentiles y los graficos.
APERTURAS = {
    "Tabla de valor": "TABLA_ORIGEN",
    "Comuna": "COMUNA",
    "Actividad económica de la ZHF": "ACTIVIDAD_ECONOMICA",
    "Actualización 2024-2025": "ACTUALIZACION",
    "Tabla x actividad (bloques del reporte)": "CLAVE",
}

# Todo lo que trae el parquet publico. Si alguna vez hay que sumar una columna,
# revisar primero que no permita senalar a un predio en concreto.
COLUMNAS = ["COMUNA", "ACTUALIZACION", "TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA",
            "CLAVE",
            "VALORCONS_CAT_VIGENCIA", "VALORCONS_CAT_LIQ",
            "VARIACION_VALORCONS_CAT_PCT",
            "VALORCONS_COM_VIGENCIA", "VALORCONS_COM_LIQ",
            "VARIACION_VALORCONS_COM_PCT",
            "VM2_CAT_VIGENCIA", "VM2_CAT_LIQ", "VARIACION_CAT_PCT",
            "AVALUO_CAT_VIGENCIA", "AVALUO_CAT_LIQ",
            "VARIACION_AVALUO_CAT_PCT",
            "VM2_COM_VIGENCIA", "VM2_COM_LIQ", "VARIACION_COM_PCT",
            "AVALUO_COM_VIGENCIA", "AVALUO_COM_LIQ", "VARIACION_AVALUO_COM_PCT"]


st.set_page_config(page_title=f"Comparación de vigencias {V_BASE} → {V_LIQ}",
                   page_icon="🏙️", layout="wide")

st.markdown(
    """
    <style>
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            background:#ffffff; border:1px solid #e6e9ef; border-radius:12px;
            padding:14px 16px; box-shadow:0 1px 3px rgba(16,24,40,.06);
        }
        div[data-testid="stMetricLabel"] p {color:#667085; font-weight:600;}
        .app-hero {
            background:linear-gradient(120deg,#1e3a8a 0%,#2563eb 55%,#0ea5e9 100%);
            color:#fff; padding:24px 28px; border-radius:16px; margin-bottom:16px;
        }
        .app-hero h1 {margin:0; font-size:26px;}
        .app-hero p  {margin:6px 0 0; opacity:.9; font-size:15px;}
    </style>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# DATOS
# =====================================================================
@st.cache_data(show_spinner="Leyendo el detalle de la comparación…")
def cargar(ruta: str, marca_tiempo: float) -> pd.DataFrame:
    """
    El detalle, con solo las columnas que usa la app.

    marca_tiempo es la fecha del archivo: no se usa adentro, pero al entrar en
    la firma hace que el cache se invalide solo cuando se vuelve a correr
    comparacion_vigencia.py, sin tener que reiniciar la app.
    """
    try:
        import pyarrow.parquet as pq
        hay = set(pq.ParquetFile(ruta).schema_arrow.names)
        d = pd.read_parquet(ruta, columns=[c for c in COLUMNAS if c in hay])
    except ImportError:                                      # pragma: no cover
        d = pd.read_parquet(ruta)
        d = d[[c for c in COLUMNAS if c in d.columns]]
    d["COMUNA"] = d["COMUNA"].astype(str).str.strip().str.zfill(2)
    for c in ("TABLA_ORIGEN", "ACTIVIDAD_ECONOMICA", "CLAVE"):
        if c in d.columns:
            d[c] = d[c].astype(str)
    return d


if not os.path.exists(RUTA_DATOS):
    st.error(
        f"No se encontró **{RUTA_DATOS.name}**.\n\n"
        "Corra primero `python src/comparacion_vigencia.py`, que es quien lo "
        "escribe en `output/`."
    )
    st.stop()

df = cargar(str(RUTA_DATOS), os.path.getmtime(RUTA_DATOS))

st.markdown(
    f"""
    <div class="app-hero">
        <h1>🏙️ Comparación de vigencias · {V_BASE} → {V_LIQ}</h1>
        <p>Lo que quedaría con la liquidación (vigencia {V_LIQ}) contra lo que
        cobra hoy la base (vigencia {V_BASE}), sobre
        <b>{len(df):,} predios</b> de una sola construcción y con valor de tabla
        en las dos vigencias.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


# =====================================================================
# FILTROS (uno solo para las tres hojas)
# =====================================================================
with st.sidebar:
    st.header("⚙️ Filtros")
    st.caption("Se aplican a las tres hojas. Vacío = todo.")

    etiqueta_medida = st.radio("Medida", list(MEDIDAS), index=0)
    etiqueta_base = st.radio(
        "Base de valor", list(BASES), index=0, horizontal=True,
        help="Catastral es lo que se cobra. Comercial es lo que se estima que "
             "vale: el catastral de la vigencia dividido por 0,7 en las comunas "
             "actualizadas en 2024-2025 y por 0,6 en las demás.")
    clave_medida, titulo_medida = MEDIDAS[etiqueta_medida]
    medida = SERIES[(clave_medida, BASES[etiqueta_base])]
    unidad_eje = f"{titulo_medida} {etiqueta_base.lower()} (millones de pesos)"

    familias = sorted({t.split("_")[0] + "_" + t.split("_")[1]
                       for t in df["TABLA_ORIGEN"].unique() if "_" in t})
    sel_familia = st.multiselect("Categoría de tabla", familias)

    # Las tablas que se ofrecen dependen de la familia elegida, para no dar a
    # escoger entre 40 codigos cuando ya se acoto a residencial.
    de_la_familia = (df["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))
                     if sel_familia else slice(None))
    tablas = sorted(df.loc[de_la_familia, "TABLA_ORIGEN"].unique())
    sel_tabla = st.multiselect("Tabla de valor", tablas)

    sel_comuna = st.multiselect("Comuna", sorted(df["COMUNA"].unique()))
    sel_actividad = st.multiselect("Actividad económica de la ZHF",
                                   sorted(df["ACTIVIDAD_ECONOMICA"].unique()))
    sel_act = st.multiselect("Actualización 2024-2025",
                             sorted(df["ACTUALIZACION"].unique()),
                             help="Separa las comunas cuyo catastral quedó al "
                                  "70% del comercial de las que quedaron al 60%.")

    st.divider()
    etiqueta_apertura = st.selectbox("Abrir percentiles y gráficos por",
                                     list(APERTURAS), index=0)
    col_apertura = APERTURAS[etiqueta_apertura]
    min_predios = st.number_input("Mínimo de predios por grupo", 1, 5000, 5,
                                  help="Los grupos con menos predios no se "
                                       "abren: con tan pocos casos un percentil "
                                       "no dice nada.")

dff = df
if sel_familia:
    dff = dff[dff["TABLA_ORIGEN"].str.startswith(tuple(sel_familia))]
if sel_tabla:
    dff = dff[dff["TABLA_ORIGEN"].isin(sel_tabla)]
if sel_comuna:
    dff = dff[dff["COMUNA"].isin(sel_comuna)]
if sel_actividad:
    dff = dff[dff["ACTIVIDAD_ECONOMICA"].isin(sel_actividad)]
if sel_act:
    dff = dff[dff["ACTUALIZACION"].isin(sel_act)]

# La medida de avaluo puede venir vacia si se corrio la comparacion sin las
# columnas de terreno; mejor decirlo que mostrar una hoja en blanco.
dff = dff[dff[medida["vig"]].notna() & dff[medida["liq"]].notna()]

if dff.empty:
    st.warning("Ningún predio cumple los filtros elegidos. Quite alguno en la "
               "barra lateral.")
    st.stop()

c_base, c_liq, c_var = (f"{medida['prefijo']}_VIG_{V_BASE}",
                        f"{medida['prefijo']}_VIG_{V_LIQ}",
                        f"VARIACIÓN_{medida['prefijo']}_{V_LIQ}_vs_{V_BASE}")

k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Predios", f"{len(dff):,}",
          f"{len(dff) / len(df) * 100:.1f}% del total")
k2.metric(f"Mediana vigencia {V_BASE}", f"$ {dff[medida['vig']].median():,.0f}")
k3.metric(f"Mediana vigencia {V_LIQ}", f"$ {dff[medida['liq']].median():,.0f}")
k4.metric("Variación mediana", f"{dff[medida['var']].median():+.2f}%")
k5.metric("Bajan", f"{(dff[medida['var']] < 0).mean() * 100:.1f}%")

st.divider()


# =====================================================================
# CALCULOS (los mismos que arma comparacion_vigencia.py)
# =====================================================================
def percentiles(s: pd.DataFrame) -> pd.DataFrame:
    """
    Los seis cortes de un grupo, con las dos series y su variacion.

    Cada serie se ordena POR SEPARADO, igual que en el Excel: el p90 de una
    vigencia y el p90 de la otra no son el mismo predio, asi que esto compara
    distribuciones, no casos. La variacion pareada -predio contra si mismo- es
    la que sale en los KPI de arriba y en la hoja de graficos.
    """
    v = pd.to_numeric(s[medida["vig"]], errors="coerce").dropna()
    l = pd.to_numeric(s[medida["liq"]], errors="coerce").dropna()
    if v.empty or l.empty:
        return pd.DataFrame()
    filas = []
    for p in PERCENTILES:
        pv, pl = float(v.quantile(p / 100)), float(l.quantile(p / 100))
        filas.append({"PERCENTIL": f"{p}%", c_base: pv, c_liq: pl,
                      c_var: (pl / pv - 1) if pv else None,
                      "NUM_PREDIOS": int(round(p / 100 * len(s)))})
    return pd.DataFrame(filas)


def por_grupo(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """Los percentiles de cada grupo, uno debajo de otro y en una sola tabla."""
    salida = []
    for clave, s in d.groupby(col, sort=True):
        if len(s) < min_predios:
            continue
        t = percentiles(s)
        if t.empty:
            continue
        t.insert(0, etiqueta_apertura, str(clave))
        salida.append(t)
    return pd.concat(salida, ignore_index=True) if salida else pd.DataFrame()


def formato_tabla() -> dict:
    """Pesos en las series, porcentaje en la variacion, entero en los predios."""
    return {
        c_base: st.column_config.NumberColumn(c_base, format="$ %d"),
        c_liq: st.column_config.NumberColumn(c_liq, format="$ %d"),
        c_var: st.column_config.NumberColumn(c_var, format="percent"),
        "NUM_PREDIOS": st.column_config.NumberColumn("NUM_PREDIOS",
                                                     format="%d"),
    }


def resumen(d: pd.DataFrame, col: str) -> pd.DataFrame:
    """
    Una fila por grupo: cuantos predios, las dos medianas y como se mueve.

    Es la hoja General del reporte, pero sobre lo filtrado y por la columna que
    se elija. Todo son agregados de por lo menos min_predios predios: ninguna
    fila describe a un predio en particular.
    """
    g = d.groupby(col, sort=True)
    t = pd.DataFrame({
        "PREDIOS": g.size(),
        c_base: g[medida["vig"]].median(),
        c_liq: g[medida["liq"]].median(),
        "VAR_MEDIANA_%": g[medida["var"]].median(),
        "BAJAN_%": g[medida["var"]].apply(lambda s: (s < 0).mean() * 100),
        "SUBEN_%": g[medida["var"]].apply(lambda s: (s > 0).mean() * 100),
    })
    t = t[t["PREDIOS"] >= min_predios]
    return t.reset_index().rename(columns={col: etiqueta_apertura})


hoja_tablas, hoja_graf = st.tabs(["📊 Tablas", "📈 Gráficos"])


# ---------------------------------------------------------------------
# HOJA 1 - TABLAS
# ---------------------------------------------------------------------
with hoja_tablas:
    st.subheader(f"Tablas · {etiqueta_medida} · base {etiqueta_base.lower()}")

    st.markdown(f"**Resumen por {etiqueta_apertura.lower()}**")
    st.caption("Las dos medianas son de distribuciones separadas; "
               "VAR_MEDIANA_% es predio contra sí mismo. Por eso pueden "
               "apuntar a lados distintos: si en un grupo conviven comunas que "
               "suben mucho y comunas que caen mucho, la mediana de los valores "
               "se va con las más pesadas y la de las variaciones no.")
    res = resumen(dff, col_apertura)
    if res.empty:
        st.info(f"Ningún grupo llega a {min_predios} predios con estos filtros.")
    else:
        st.dataframe(
            res, width="stretch", hide_index=True,
            column_config={
                "PREDIOS": st.column_config.NumberColumn("PREDIOS", format="%d"),
                c_base: st.column_config.NumberColumn(c_base, format="$ %d"),
                c_liq: st.column_config.NumberColumn(c_liq, format="$ %d"),
                "VAR_MEDIANA_%": st.column_config.NumberColumn(
                    "VAR_MEDIANA_%", format="%.2f%%"),
                "BAJAN_%": st.column_config.NumberColumn("BAJAN_%",
                                                         format="%.1f%%"),
                "SUBEN_%": st.column_config.NumberColumn("SUBEN_%",
                                                         format="%.1f%%"),
            },
        )
        st.download_button(
            "⬇️ Descargar el resumen (CSV)",
            data=res.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"resumen_{medida['prefijo']}_{col_apertura}.csv",
            mime="text/csv", key="csv_resumen",
        )

    st.divider()
    st.markdown(f"**Percentiles del total de la selección** · {len(dff):,} predios")
    total = percentiles(dff)
    st.dataframe(total, width="stretch", hide_index=True,
                 column_config=formato_tabla())

    st.divider()
    st.markdown(f"**Percentiles abiertos por {etiqueta_apertura.lower()}**")
    abierto = por_grupo(dff, col_apertura)
    if abierto.empty:
        st.info(f"Ningún grupo llega a {min_predios} predios con estos filtros. "
                f"Baje el mínimo en la barra lateral.")
    else:
        n_grupos = abierto[etiqueta_apertura].nunique()
        n_fuera = dff[col_apertura].nunique() - n_grupos
        st.caption(f"{n_grupos} grupos"
                   + (f" · {n_fuera} quedaron fuera por tener menos de "
                      f"{min_predios} predios" if n_fuera else ""))
        st.dataframe(abierto, width="stretch", hide_index=True,
                     column_config=formato_tabla())
        st.download_button(
            "⬇️ Descargar los percentiles (CSV)",
            data=abierto.to_csv(index=False).encode("utf-8-sig"),
            file_name=f"percentiles_{medida['prefijo']}_{col_apertura}.csv",
            mime="text/csv", key="csv_percentiles",
        )


# ---------------------------------------------------------------------
# HOJA 3 - GRAFICOS
# ---------------------------------------------------------------------
with hoja_graf:
    st.subheader(f"Gráficos · {etiqueta_medida} · base {etiqueta_base.lower()}")

    def curvas(t: pd.DataFrame, titulo: str) -> alt.Chart:
        """Las dos curvas de percentiles, en millones y con los mismos colores
        que los PNG del reporte."""
        largo = t.melt(id_vars="PERCENTIL", value_vars=[c_base, c_liq],
                       var_name="Serie", value_name="Valor")
        largo["Millones"] = largo["Valor"] / 1e6
        return (
            alt.Chart(largo, title=titulo)
            .mark_line(point=alt.OverlayMarkDef(size=70), strokeWidth=2.5)
            .encode(
                x=alt.X("PERCENTIL:N", title="Percentil",
                        sort=[f"{p}%" for p in PERCENTILES]),
                y=alt.Y("Millones:Q", title=unidad_eje),
                color=alt.Color("Serie:N", title=None,
                                scale=alt.Scale(domain=[c_base, c_liq],
                                                range=[NARANJA, AZUL]),
                                legend=alt.Legend(orient="top")),
                tooltip=["PERCENTIL", "Serie",
                         alt.Tooltip("Valor:Q", format="$,.0f")],
            )
            .properties(height=340)
        )

    st.altair_chart(
        curvas(percentiles(dff), f"Total de la selección · {len(dff):,} predios"),
        width="stretch")

    st.divider()
    st.markdown(f"**Por {etiqueta_apertura.lower()}**")
    abierto = por_grupo(dff, col_apertura)
    if abierto.empty:
        st.info(f"Ningún grupo llega a {min_predios} predios con estos filtros.")
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
                predios = int(t["NUM_PREDIOS"].iloc[-1])
                mediana = t.loc[t["PERCENTIL"] == "50%", c_var]
                pie = ("" if mediana.empty or pd.isna(mediana.iloc[0])
                       else f" · en la mediana {mediana.iloc[0] * 100:+.1f}%")
                col.altair_chart(
                    curvas(t, f"{nombre} · {predios:,} predios{pie}"),
                    width="stretch")

    st.divider()
    st.markdown("**Cómo se reparte la variación**")
    st.caption("Aquí sí es predio contra sí mismo, no distribución contra "
               "distribución: cada predio cae en el rango de su propia "
               "variación.")
    reparto = (dff[medida["var"]]
               .pipe(pd.cut,
                     bins=[-float("inf"), -50, -25, -10, 10, 25, 50, float("inf")],
                     labels=["baja más de 50%", "baja 25-50%", "baja 10-25%",
                             "estable (±10%)", "sube 10-25%", "sube 25-50%",
                             "sube más de 50%"])
               .value_counts(sort=False).rename_axis("RANGO").reset_index(name="PREDIOS"))
    reparto["%"] = reparto["PREDIOS"] / reparto["PREDIOS"].sum() * 100
    st.altair_chart(
        alt.Chart(reparto).mark_bar(color=AZUL, cornerRadiusEnd=3).encode(
            x=alt.X("RANGO:N", title=None, sort=list(reparto["RANGO"])),
            y=alt.Y("PREDIOS:Q", title="Predios"),
            tooltip=["RANGO", "PREDIOS", alt.Tooltip("%:Q", format=".1f")],
        ).properties(height=300),
        width="stretch")


st.caption(
    f"Fuente: {RUTA_DATOS.name} · generado por comparacion_vigencia.py el "
    f"{pd.Timestamp(os.path.getmtime(RUTA_DATOS), unit='s'):%Y-%m-%d %H:%M}. "
    f"Solo predios de una sola construcción con valor de tabla en las dos "
    f"vigencias. Datos agregados, sin identificador de predio ni número "
    f"predial: el VM2 viene redondeado a $100 y el avalúo a $100.000, así que "
    f"puede haber diferencias de centésimas contra el reporte en Excel, que "
    f"trabaja con el valor exacto y es el documento de referencia."
)


# =====================================================================
# PUBLICAR (gratis, con enlace)
# =====================================================================
# Streamlit Community Cloud publica esto sin costo y da una URL fija que se
# abre desde cualquier PC:
#
#   1. En el repositorio de GitHub tienen que estar:
#          src/app_vigencias.py
#          output/COMPARACION_VIGENCIA_PUBLICO.parquet   (~7 MB)
#          requirements.txt
#      Y NO puede estar COMPARACION_VIGENCIA_DETALLE.parquet: lleva ID_PREDIO
#      y numero predial. El .gitignore ya lo deja fuera.
#   2. En share.streamlit.io, "Create app", elegir el repositorio y poner
#      src/app_vigencias.py como archivo principal.
#   3. Queda en https://<lo-que-se-elija>.streamlit.app
#
# OJO con el historial: borrar un archivo en un commit nuevo no lo saca de los
# commits anteriores, que se siguen pudiendo descargar. Si el detalle llego a
# subirse alguna vez, no basta con borrarlo: hay que rehacer el repositorio.
