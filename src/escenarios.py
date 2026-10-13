# -*- coding: utf-8 -*-
"""Liquida la base de hoy con las reglas de 2024, 2025 y la propuesta 2027.

Mide cuanto cambia el resultado al cambiar las reglas. NO reproduce lo que se
cobro en 2024: aquella liquidacion corrio sobre otra base.

Lo que no existe va en cero: ni se cae a otro metodo ni se extrapola. El METODO
de cada escenario dice por que.
"""
import os
import sys

import numpy as np
import pandas as pd

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(RAIZ, "src") not in sys.path:
    sys.path.insert(0, os.path.join(RAIZ, "src"))

RUTA_BASE = os.path.join(RAIZ, "output", "todas_las_construcciones.parquet")
RUTA_SALIDA = os.path.join(RAIZ, "output", "ESCENARIOS.parquet")

# CONSTRUCCION_ID no sirve para cruzar: se arma pegando predio, consecutivo y
# destino sin separador, y 31 pares de construcciones distintas terminan con
# el mismo. Al cruzar por ahi, un apartamento de la comuna 03 recibia el
# resultado de un anexo rural. LLAVE_CONST es unica por construccion.
LLAVE = "LLAVE_CONST"

# El catastral es el comercial por este factor, y NO es el mismo en los tres.
FACTOR_CATASTRAL = {"2024": 0.6, "2025": 0.7, "ACTUAL": 0.7}

# El ejercicio de 2024 produce la vigencia 2025, y asi.
VIGENCIA_QUE_RIGE = {"2024": 2025, "2025": 2026, "ACTUAL": 2027}

COLUMNAS_PREDIO = ["ID_PREDIO", "NUMERO_PREDIAL_NACIONAL", "CONSTRUCCION_ID",
                   "LLAVE_CONST",
                   "COMUNA", "USO_LADM", "DESTINOCONS", "CONDICION",
                   "ESTRPRED", "ZHF", "PUNTCONS", "AREA_CONST", "ACONCONS"]

# En 2024 T2 es COMERCIAL y T8 EDIFICIOS; hoy T2 es EDIFICIOS y T3 COMERCIAL.
# Los codigos no son comparables entre vigencias, solo los nombres.
FAMILIA_2024 = {
    "T1_RESIDENCIAL": "RESIDENCIAL", "T2_COMERCIAL": "COMERCIAL",
    "T3_INDUSTRIAL": "INDUSTRIAL", "T4_INSTITUCIONAL_ED": "INSTITUCIONAL_ED",
    "T5_INSTITUCIONAL_SA": "INSTITUCIONAL_SA",
    "T6_INSTITUCIONAL_SER": "INSTITUCIONAL_SER",
    "T7_INSTITUCIONAL_IG": "INSTITUCIONAL_IG", "T8_EDIFICIOS": "EDIFICIOS",
    "T9_HOTELES": "HOTELES", "T10_ANEXOS": "ANEXOS",
    "T11_CCOMERCIALES": "CCOMERCIALES", "T12_PARQUEADEROS": "PARQUEADEROS",
    "MODELO": "MODELO", "ESPECIAL": "ESPECIAL",
}

# Que comuna actualizo cada ejercicio. 2025 repitio la 03 y la 22.
ACTUALIZO_2024 = ["02", "03", "04", "08", "17", "19", "22"]
ACTUALIZO_2025 = ["01", "09", "10", "11", "12", "03", "22"]

_CACHE = {}


def _familia(tabla):
    """El nombre de la familia, sin el numero."""
    t = str(tabla)
    if t in FAMILIA_2024:
        return FAMILIA_2024[t]
    if t in ("MODELO", "ESPECIALES", "ESPECIAL", "SIN TABLA", ""):
        return t or "SIN TABLA"
    partes = t.split("_")
    return "_".join(p for p in partes[1:] if not p.isdigit()) or t


def _normalizar(d):
    """Los tipos que los tres motores dan por supuestos."""
    d = d.copy()
    d["COMUNA"] = d["COMUNA"].astype(str).str.strip().str.zfill(2)
    d["DESTINOCONS"] = d["DESTINOCONS"].astype(str).str.strip().str.zfill(3)
    d["CONDICION"] = (pd.to_numeric(d["CONDICION"], errors="coerce")
                      .fillna(0).round(0).astype("int64"))
    return d


def _resultado(d, escenario):
    """Una fila por construccion: el valor, por que via salio y en que unidad.

    Cada motor reparte su resultado en columnas distintas -el de 2025 usa
    cinco- asi que se miran todas y gana la primera con valor.
    """
    def col(nombre):
        return (pd.to_numeric(d[nombre], errors="coerce").fillna(0)
                if nombre in d.columns else pd.Series(0.0, index=d.index))

    vm2, mod = col("VM2"), col("VM2_MOD")
    parq, esp = col("LIQ_PARQUEADERO"), col("VM2_ESP_2026")
    tabla = (d["TABLA_ORIGEN"].astype(str) if "TABLA_ORIGEN" in d.columns
             else pd.Series("", index=d.index))

    valor = np.select([mod > 0, parq > 0, esp > 0, vm2 > 0],
                      [mod, parq, esp, vm2], default=0.0)

    # El parqueadero vale por unidad, no por metro. Eso va en UNIDAD y no en
    # METODO: la via por la que sale es una tabla, la T12, igual que cualquier
    # otra. Tenerlo como metodo aparte mezclaba dos preguntas distintas -por
    # donde salio el valor y en que unidad esta- y escondia que T12 es tabla.
    # Se reconoce por el nombre de la tabla porque 2024 y el actual lo meten
    # dentro de VM2 y solo 2025 lo deja en LIQ_PARQUEADERO.
    es_parq = tabla.str.contains("PARQUEADERO", na=False) | (parq > 0)

    # Sin valor hay tres situaciones distintas y antes caian todas en
    # "sin tabla": que las reglas no le asignaran ninguna, que le asignaran una
    # que todavia no tiene valores -T7, T8, T10, y ahora T12 sin aval- y que la
    # tabla exista pero no cubra su comuna o su puntaje. La primera es un vacio
    # de la regla; las otras dos son un entregable pendiente.
    sin_asignar = tabla.isin(["SIN TABLA", "", "nan", "None"])

    metodo = np.select(
        [mod > 0, esp > 0, valor > 0,
         tabla == "MODELO", tabla == "ESPECIALES", sin_asignar],
        ["modelo", "especial", "tabla",
         "sin modelo en esta vigencia", "especial sin valorar",
         "sin tabla asignada"],
        default="tabla sin valorar")

    return pd.DataFrame({
        LLAVE: d[LLAVE].astype(str),
        f"VM2_{escenario}": valor,
        f"TABLA_{escenario}": tabla.values,
        f"FAMILIA_{escenario}": [_familia(t) for t in tabla],
        f"METODO_{escenario}": metodo,
        f"UNIDAD_{escenario}": np.where(es_parq, "por unidad", "por m2"),
    })


def _no_se_valora(r, fuera, escenario):
    """Comuna que ese ejercicio no actualizo: en cero, y ni tabla ni modelo."""
    motivo = f"no se valora en la vigencia {VIGENCIA_QUE_RIGE[escenario]}"
    r.loc[fuera, f"VM2_{escenario}"] = 0.0
    for c in ("TABLA", "FAMILIA", "METODO"):
        r.loc[fuera, f"{c}_{escenario}"] = motivo


def escenario_2024(base):
    """Tablas de 2024 mas los modelos de esa familia."""
    from Liquidacion_tablas_2024 import tablas_liquidacion_2024
    import model_liq

    d = _normalizar(tablas_liquidacion_2024(base))

    # ejecutar_modelos devuelve SOLO las filas de MODELO: hay que pegar la
    # prediccion por llave, no reasignar el frame.
    mod = model_liq.ejecutar_modelos(d)
    if LLAVE in mod.columns and "VM2_MOD" in mod.columns:
        pred = (mod.drop_duplicates(LLAVE)
                   .assign(**{LLAVE: lambda x: x[LLAVE].astype(str)})
                   .set_index(LLAVE)["VM2_MOD"])
        d["VM2_MOD"] = (d[LLAVE].astype(str).map(pred)
                        .astype("float64").fillna(0))
        print(f"   modelos pegados: {int((d['VM2_MOD'] > 0).sum()):,} "
              f"de {int((d['TABLA_ORIGEN'] == 'MODELO').sum()):,} en MODELO")

    r = _resultado(d, "2024")
    fuera = ~d["COMUNA"].isin(ACTUALIZO_2024).values
    _no_se_valora(r, fuera, "2024")
    print(f"   comunas fuera de la actualizacion 2024: {int(fuera.sum()):,}")
    return r


def escenario_2025(base):
    """Las reglas de 2025 sobre sus propias comunas.

    Cada ejercicio valora solo las comunas que actualizo. Antes, las cinco que
    2024 actualizo y 2025 no volvio a tocar -02, 04, 08, 17 y 19- heredaban las
    tablas de aquel anio, porque en la vigencia 2026 esos predios si tenian
    avaluo: el de 2024, que sigue en firme hasta que se actualice. Al quitar la
    herencia son 320.136 construcciones que salen en cero, asi que comparar esas
    comunas contra la vigencia actual muestra un salto desde cero que no es una
    variacion real.
    """
    from Liquidacion_tablas_2025 import tablas_liquidacion
    r25 = _resultado(_normalizar(tablas_liquidacion(base.copy())), "2025")

    # drop_duplicates antes del map: con la llave repetida pandas rechaza el
    # reindex.
    comuna = (base.assign(_k=base[LLAVE].astype(str))
                  .drop_duplicates("_k").set_index("_k")["COMUNA"]
                  .astype(str).str.strip().str.zfill(2))
    fuera = ~r25[LLAVE].map(comuna).isin(ACTUALIZO_2025).fillna(False).to_numpy()

    _no_se_valora(r25, fuera, "2025")
    print(f"   comunas fuera de la actualizacion 2025: {int(fuera.sum()):,}")
    return r25


# Los tres usos en PH van por modelo, salvo condicion 8.
USOS_POR_MODELO = ["Apartamentos_4_y_mas_pisos_en_PH", "Comercio_en_PH",
                   "Oficinas_Consultorios_en_PH"]
CONDICION_POR_TABLA = 8


def escenario_actual(base):
    """Tablas de la propuesta 2027. Esta vigencia no tiene modelo todavia."""
    from Liquidacion_tablas import tablas_liquidacion

    d = _normalizar(tablas_liquidacion(base.copy()))

    # El motor ya los marca MODELO; aqui se anulan porque 2027 no tiene modelo.
    va_por_modelo = (d["USO_LADM"].isin(USOS_POR_MODELO)
                     & (d["CONDICION"] != CONDICION_POR_TABLA))
    d.loc[va_por_modelo, "VM2"] = 0
    d.loc[va_por_modelo, "TABLA_ORIGEN"] = "MODELO"
    if "VM2_MOD" in d.columns:
        d.loc[va_por_modelo, "VM2_MOD"] = 0
    print(f"   por modelo (sin modelo en esta vigencia): "
          f"{int(va_por_modelo.sum()):,}")
    return _resultado(d, "ACTUAL")


MOTORES = {"2024": escenario_2024, "2025": escenario_2025,
           "ACTUAL": escenario_actual}


def comparar(escenarios=("2024", "2025", "ACTUAL"), ruta_salida=RUTA_SALIDA,
             con_excel=True):
    """Corre los escenarios sobre la misma base y deja el parquet comparativo."""
    base = pd.read_parquet(RUTA_BASE)
    print(f"Base: {len(base):,} construcciones\n")

    t = base[[LLAVE]].copy()
    t[LLAVE] = t[LLAVE].astype(str)
    for nombre in escenarios:
        print(f"{'=' * 66}\n=== ESCENARIO {nombre}\n{'=' * 66}")
        r = _CACHE.get(nombre)
        if r is None:
            r = MOTORES[nombre](base)
            _CACHE[nombre] = r
        r = r.drop_duplicates(LLAVE)
        t = t.merge(r, on=LLAVE, how="left")
        t[f"VM2_{nombre}"] = t[f"VM2_{nombre}"].fillna(0)
        t[f"METODO_{nombre}"] = t[f"METODO_{nombre}"].fillna("fuera del motor")
        con = int((t[f"VM2_{nombre}"] > 0).sum())
        print(f"\n--> {nombre}: {con:,} con valor, {len(t) - con:,} en cero\n")

    # Despues de la cobertura, no antes: si no, sale con valor donde el
    # escenario termina en cero.
    for nombre in escenarios:
        col = f"VM2_{nombre}"
        if col in t.columns:
            t[f"VM2_COM_{nombre}"] = t[col]
            t[f"VM2_CAT_{nombre}"] = t[col] * FACTOR_CATASTRAL.get(nombre, 0.7)

    t.to_parquet(ruta_salida, index=False)
    print(f"{'=' * 66}\nEscrito: {ruta_salida}")
    print(f"         {len(t):,} filas, {len(t.columns)} columnas")

    # El Excel sale de aqui y no del CLI: separados, el parquet se
    # regeneraba y el detalle se quedaba con los numeros de la corrida
    # anterior sin que nada lo dijera. Quien no lo quiera, --sin-excel.
    if con_excel:
        detalle_excel(t, base)
    return t


def _exigir_escribible(ruta):
    """Falla ANTES de armar el archivo, no despues de siete minutos.

    Excel bloquea lo que tiene abierto, y el escritor solo lo descubria al
    final: la corrida se perdia entera. En la sensibilidad, donde se reliquida
    con el detalle abierto para mirarlo, eso pasa seguido.
    """
    if not os.path.exists(ruta):
        return
    try:
        with open(ruta, "r+b"):
            pass
    except PermissionError:
        raise RuntimeError(
            f"{os.path.basename(ruta)} esta abierto en Excel y no se puede "
            f"reescribir. Cierrelo y vuelva a correr.\n   {ruta}") from None


def detalle_excel(t=None, base=None, ruta=None):
    """Las tres vigencias en una hoja, una fila por construccion.

    En hojas separadas habria que buscar la misma construccion tres veces para
    compararla, y la mitad de la base tiene valor en dos o mas.
    """
    if t is None:
        t = pd.read_parquet(RUTA_SALIDA)
    if base is None:
        base = pd.read_parquet(RUTA_BASE)
    ruta = ruta or os.path.join(RAIZ, "results", "DETALLE_VIGENCIAS.xlsx")
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    _exigir_escribible(ruta)

    cols = [c for c in COLUMNAS_PREDIO if c in base.columns]
    d = base[cols].copy()
    d[LLAVE] = d[LLAVE].astype(str)
    d = d.drop_duplicates(LLAVE)

    for esc in ("2024", "2025", "ACTUAL"):
        vig = VIGENCIA_QUE_RIGE[esc]
        cambio = {f"VM2_COM_{esc}": f"VIG{vig}_COMERCIAL",
                  f"VM2_CAT_{esc}": f"VIG{vig}_CATASTRAL",
                  f"TABLA_{esc}": f"VIG{vig}_TABLA",
                  f"METODO_{esc}": f"VIG{vig}_METODO"}
        hay = [c for c in cambio if c in t.columns]
        if hay:
            d = d.merge(t[[LLAVE] + hay].rename(columns=cambio),
                        on=LLAVE, how="left")

    vals = [c for c in d.columns if c.endswith(("_COMERCIAL", "_CATASTRAL"))]
    d = d[d[vals].fillna(0).gt(0).any(axis=1)]

    # A un temporal y no directo al destino: xlsxwriter trunca el archivo
    # al abrirlo, asi que una corrida interrumpida dejaba sin detalle
    # viejo y sin detalle nuevo.
    # pandas elige el motor por la extension: tiene que terminar en .xlsx.
    provisional = os.path.splitext(ruta)[0] + ".parcial.xlsx"
    with pd.ExcelWriter(provisional, engine="xlsxwriter") as xl:
        libro = xl.book
        f_encab = libro.add_format({"bold": True, "bg_color": "#1F3864",
                                    "font_color": "white", "border": 1,
                                    "text_wrap": True, "valign": "vcenter"})
        f_pesos = libro.add_format({"num_format": "$ #,##0"})

        hoja = "TRES VIGENCIAS"
        d.to_excel(xl, sheet_name=hoja, index=False, startrow=1, header=False)
        h = xl.sheets[hoja]
        for j, col in enumerate(d.columns):
            h.write(0, j, col, f_encab)
            if col.endswith(("_COMERCIAL", "_CATASTRAL")):
                fmt, ancho = f_pesos, 17
            else:
                fmt, ancho = None, max(12, min(len(col) + 2, 30))
            h.set_column(j, j, ancho, fmt)
        h.set_row(0, 30)
        h.freeze_panes(1, 3)
        h.autofilter(0, 0, len(d), len(d.columns) - 1)

    print(f"   {len(d):,} construcciones, {len(d.columns)} columnas")
    os.replace(provisional, ruta)

    print(f"\nDetalle: {ruta}")
    print(f"         {os.path.getsize(ruta) / 1e6:.1f} MB")
    return ruta


def _cli():
    """Desde consola se elige que vigencias liquidar."""
    import argparse

    a = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    a.add_argument("--solo-actual", action="store_true",
                   help="liquida unicamente la vigencia actual")
    a.add_argument("-e", "--escenarios", default="2024,2025,ACTUAL",
                   help="cuales liquidar, separados por coma")
    a.add_argument("-o", "--salida", default=RUTA_SALIDA)
    a.add_argument("--sin-excel", action="store_true",
                   help="deja solo el parquet, sin el detalle en Excel")
    args = a.parse_args()

    pedidos = (("ACTUAL",) if args.solo_actual
               else tuple(x.strip().upper() for x in args.escenarios.split(",")
                          if x.strip()))
    desconocidos = [x for x in pedidos if x not in MOTORES]
    if desconocidos:
        a.error(f"escenario(s) que no existen: {', '.join(desconocidos)}. "
                f"Hay: {', '.join(MOTORES)}")

    print("Escenarios a liquidar: " + ", ".join(pedidos))
    print()
    comparar(pedidos, args.salida, con_excel=not args.sin_excel)


if __name__ == "__main__":
    _cli()
