import streamlit as st
import pandas as pd
import time
import os
from datetime import datetime

from tabla_construccion import procesar_construcciones, cruces_const_predio
from Liquidacion_tablas import tablas_liquidacion


# =========================================================
# CONFIGURACIÓN DE PÁGINA
# =========================================================
st.set_page_config(
    page_title="Liquidación Catastral 2026",
    page_icon="🏠",
    layout="wide",
)

# --- Estilos ---
st.markdown(
    """
    <style>
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        div[data-testid="stMetric"] {
            background: #ffffff;
            border: 1px solid #e6e9ef;
            border-radius: 12px;
            padding: 16px 18px;
            box-shadow: 0 1px 3px rgba(16,24,40,.06);
        }
        div[data-testid="stMetricLabel"] p {color:#667085; font-weight:600;}
        .app-hero {
            background: linear-gradient(120deg,#1e3a8a 0%,#2563eb 55%,#0ea5e9 100%);
            color:#fff; padding:26px 30px; border-radius:16px; margin-bottom:18px;
        }
        .app-hero h1 {margin:0; font-size:28px;}
        .app-hero p  {margin:6px 0 0; opacity:.9; font-size:15px;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="app-hero">
        <h1>🏠 Liquidación Catastral 2026</h1>
        <p>Proceso hasta el <b>valor de tablas (VM2)</b> · revisa cómo van quedando liquidadas las construcciones.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# Columnas relevantes para la vista de construcciones (se muestran solo las que existan)
COLS_VALOR = [
    "ID_PREDIO", "CONSTRUCCION_ID", "COMUNA", "CONDICION",
    "DESTINOCONS", "DESTANEX", "USO_LADM",
    "TABLA_ORIGEN", "METODO_LIQUIDACION",
    "PUNTCONS", "AREA_CONST",
    "VM2",             # valor de tablas (renombrado de VM2_FINAL_V3)
    "VM2_MOD",         # valor por modelo ML
    "LIQ_PARQUEADERO",
    "VM2_ESP_2026",    # valor de especiales
]
COLS_MONEDA = ["VM2", "VM2_MOD", "LIQ_PARQUEADERO", "VM2_ESP_2026"]


# =========================================================
# SIDEBAR — CONTROLES
# =========================================================
with st.sidebar:
    st.header("⚙️ Opciones")
    preview_rows = st.slider(
        "Filas a previsualizar en la tabla",
        min_value=100, max_value=5000, value=1000, step=100,
    )
    st.caption("La descarga incluye todos los registros filtrados.")
    st.divider()
    ejecutar = st.button(
        "▶️ Ejecutar liquidación (hasta tablas)",
        type="primary",
        use_container_width=True,
    )
    if "df_liq" in st.session_state:
        if st.button("🗑️ Limpiar resultado", use_container_width=True):
            del st.session_state["df_liq"]
            st.session_state.pop("tiempo", None)
            st.rerun()


# =========================================================
# EJECUCIÓN DEL PROCESO (PASOS 1 → 3)
# =========================================================
def _paso(contenedor, texto):
    contenedor.info(texto)


if ejecutar:
    inicio = time.time()
    progreso = st.progress(0, text="Iniciando…")
    estado = st.empty()

    try:
        # ---- PASO 1: Procesar construcciones ----
        _paso(estado, "Paso 1 de 3 · Procesando construcciones y predios…")
        df_predio, df_conv, df_noconv = procesar_construcciones()
        progreso.progress(25, text="Construcciones cargadas")

        # ---- PASO 2: Cruces predio – construcción ----
        _paso(estado, "Paso 2 de 3 · Cruzando predios y construcciones (homologación + uso principal)…")
        df_const_predio_final = cruces_const_predio(df_predio, df_conv, df_noconv)
        progreso.progress(60, text="Cruces y homologación listos")

        # ---- PASO 3: Aplicar tablas de liquidación ----
        _paso(estado, "Paso 3 de 3 · Aplicando tablas de valor (VM2)…")
        df_liquidacion = tablas_liquidacion(df_const_predio_final)
        progreso.progress(90, text="Valores de tablas asignados")

        # ---- Guardar intermedio ----
        os.makedirs("./output", exist_ok=True)
        df_liquidacion.to_parquet("./output/LIQUIDACION_TABLAS.parquet", index=False)
        progreso.progress(100, text="Completado")

        estado.empty()
        st.session_state["df_liq"] = df_liquidacion
        st.session_state["tiempo"] = round(time.time() - inicio, 2)
        st.toast("✅ Liquidación de tablas completada", icon="✅")

    except Exception as e:
        progreso.empty()
        estado.empty()
        st.error(f"❌ Error durante el proceso: {e}")
        st.stop()


# =========================================================
# RESULTADOS
# =========================================================
if "df_liq" not in st.session_state:
    st.info("Configura las opciones en la barra lateral y pulsa **▶️ Ejecutar liquidación**.")
    st.stop()

df = st.session_state["df_liq"]
cols_mostrar = [c for c in COLS_VALOR if c in df.columns]
tiene_vm2 = "VM2" in df.columns

# --- KPIs ---
total_const = len(df)
con_valor = int((df["VM2"] > 0).sum()) if tiene_vm2 else 0
pct_valor = (con_valor / total_const * 100) if total_const else 0
predios = df["ID_PREDIO"].nunique() if "ID_PREDIO" in df.columns else 0
vm2_prom = float(df.loc[df["VM2"] > 0, "VM2"].mean()) if (tiene_vm2 and con_valor) else 0
sin_tabla = int((df["TABLA_ORIGEN"] == "SIN TABLA").sum()) if "TABLA_ORIGEN" in df.columns else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Predios", f"{predios:,}")
c2.metric("Construcciones", f"{total_const:,}")
c3.metric("Con VM2 > 0", f"{con_valor:,}", f"{pct_valor:.1f}%")
c4.metric("VM2 promedio", f"$ {vm2_prom:,.0f}")
c5.metric("Sin tabla", f"{sin_tabla:,}")

if "tiempo" in st.session_state:
    st.caption(f"⏱️ Procesado en {st.session_state['tiempo']} s · {datetime.now():%Y-%m-%d %H:%M}")

st.divider()

tab_const, tab_tablas, tab_resumen = st.tabs(
    ["🏗️ Construcciones", "📋 Por tabla de origen", "📊 Resumen"]
)

# ---------------------------------------------------------
# TAB 1 — CONSTRUCCIONES (con filtros)
# ---------------------------------------------------------
with tab_const:
    f1, f2, f3 = st.columns([2, 2, 1])

    comunas = sorted(df["COMUNA"].dropna().astype(str).unique()) if "COMUNA" in df.columns else []
    tablas = sorted(df["TABLA_ORIGEN"].dropna().astype(str).unique()) if "TABLA_ORIGEN" in df.columns else []

    sel_comunas = f1.multiselect("Comuna", comunas, default=[])
    sel_tablas = f2.multiselect("Tabla de origen", tablas, default=[])
    solo_valor = f3.toggle("Solo VM2 > 0", value=False)

    dff = df
    if sel_comunas:
        dff = dff[dff["COMUNA"].astype(str).isin(sel_comunas)]
    if sel_tablas:
        dff = dff[dff["TABLA_ORIGEN"].astype(str).isin(sel_tablas)]
    if solo_valor and tiene_vm2:
        dff = dff[dff["VM2"] > 0]

    st.caption(
        f"Mostrando {min(preview_rows, len(dff)):,} de {len(dff):,} registros filtrados "
        f"(de {total_const:,} totales)."
    )

    column_config = {
        c: st.column_config.NumberColumn(c, format="$ %d")
        for c in COLS_MONEDA if c in dff.columns
    }
    st.dataframe(
        dff[cols_mostrar].head(preview_rows),
        use_container_width=True,
        hide_index=True,
        column_config=column_config,
    )

    # Descarga (se prepara solo bajo demanda para no serializar en cada interacción)
    if st.checkbox("Preparar descarga CSV de los registros filtrados"):
        csv = dff[cols_mostrar].to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Descargar CSV",
            data=csv,
            file_name="construcciones_valor_tablas.csv",
            mime="text/csv",
            use_container_width=True,
        )

# ---------------------------------------------------------
# TAB 2 — RESUMEN POR TABLA DE ORIGEN
# ---------------------------------------------------------
with tab_tablas:
    if "TABLA_ORIGEN" in df.columns and tiene_vm2:
        resumen = (
            df.groupby("TABLA_ORIGEN")
            .agg(
                CONSTRUCCIONES=("TABLA_ORIGEN", "size"),
                CON_VM2=("VM2", lambda s: int((s > 0).sum())),
                VM2_PROMEDIO=("VM2", lambda s: s[s > 0].mean()),
                VM2_MAX=("VM2", "max"),
            )
            .reset_index()
            .sort_values("CONSTRUCCIONES", ascending=False)
        )
        st.dataframe(
            resumen,
            use_container_width=True,
            hide_index=True,
            column_config={
                "VM2_PROMEDIO": st.column_config.NumberColumn("VM2_PROMEDIO", format="$ %d"),
                "VM2_MAX": st.column_config.NumberColumn("VM2_MAX", format="$ %d"),
            },
        )
        st.bar_chart(resumen.set_index("TABLA_ORIGEN")["CONSTRUCCIONES"])
    else:
        st.warning("No están disponibles las columnas TABLA_ORIGEN / VM2 para el resumen.")

# ---------------------------------------------------------
# TAB 3 — RESUMEN GENERAL
# ---------------------------------------------------------
with tab_resumen:
    cols_existentes = [c for c in cols_mostrar if c in df.columns]
    st.write("**Columnas disponibles en el resultado:**")
    st.write(", ".join(cols_existentes))

    if "METODO_LIQUIDACION" in df.columns:
        st.write("**Distribución por método de liquidación:**")
        met = df["METODO_LIQUIDACION"].value_counts().rename_axis("METODO").reset_index(name="CANTIDAD")
        st.dataframe(met, use_container_width=True, hide_index=True)

    if tiene_vm2:
        st.write("**Estadísticas de VM2 (solo VM2 > 0):**")
        st.dataframe(
            df.loc[df["VM2"] > 0, "VM2"].describe().to_frame().T,
            use_container_width=True,
        )

# python -m streamlit run src/app.py
