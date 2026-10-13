"""Control de filas entre etapas: que no se pierdan ni se dupliquen.

Se marca la base al salir de cada etapa. Como LLAVE_CONST es unica, no se
comparan cantidades sino las llaves mismas: en cada corte se sabe cuales
desaparecieron y cuales aparecieron, no solo cuantas. Una etapa que pierda 500
y gane 500 distintas cuadra en el conteo y aqui no pasa.

Cuando una etapa pierde filas sin haberlo declarado se avisa EN ESE MOMENTO,
con ejemplos de las llaves, no al final del proceso. Con estricto=True ademas
se detiene, para no gastar veinte minutos produciendo una salida incompleta.

    from control_filas import control

    control.marca("entrada", convencionales=df_conv, no_convencionales=df_noconv)
    control.marca("homologacion", df_const)
    control.marca("pre_inconsistencias", df, baja_ok="predios sin informacion")
    control.resumen()

Cuesta ~1 s por corte sobre 900.000 filas. Con Control(rapido=True) solo vigila
totales y baja a milisegundos. Se apaga con la variable SIN_CONTROL_FILAS.
"""

import os
import time

import pandas as pd


LLAVE = "LLAVE_CONST"

# Sin LLAVE_CONST se cuenta con esto, que es lo mejor que dan los insumos y
# deja 47 repetidas. En texto no sirven -los nulos se colapsan entre si y dan
# 800 falsas-, por eso se usa duplicated(subset=).
COLS_LLAVE = ["ID_PREDIO", "ID_CONSTRUCCION", "CONSANEX"]


def acunar_llave(df, prefijo):
    """ID_PREDIO mas la fila con que el registro entro al proceso.

    En estos insumos no hay llave natural: 12 filas son identicas en todas sus
    columnas. CONCONS y CONSANEX tampoco sirven -se repiten 192 y 10 veces-, y
    CONSECUTIVO menos, porque se asigna despues de ordenar por area y puntaje y
    entre empatadas el orden lo decide quicksort.

    La fila de entrada es unica por definicion y dice donde buscar el registro
    en el archivo de origen: C69-0000042 es la fila 42 del export de
    convencionales. El prefijo separa los dos archivos, que se numeran cada uno
    desde 1.
    """
    fila = pd.Series(range(1, len(df) + 1), index=df.index)
    return (prefijo + df["ID_PREDIO"].astype(str) + "-"
            + fila.astype(str).str.zfill(7))


def _llaves(df):
    """La columna llave como Index, o None si la etapa todavia no la tiene.

    Tiene que ser astype(object) y no to_numpy(dtype=object): con el segundo,
    pd.Index vuelve a inferir el dtype de cadena y el isin pasa de 0.3 s a 25 s
    por corte.
    """
    if LLAVE not in df.columns:
        return None
    return pd.Index(df[LLAVE].astype(object))


def _contar(df, rapido=False):
    n = len(df)
    dato = {"filas": n, "conv": None, "noconv": None,
            "predios": None, "dups": None}

    if "DESTINOCONS" in df.columns:
        conv = int((pd.to_numeric(df["DESTINOCONS"], errors="coerce") > 0).sum())
        dato["conv"], dato["noconv"] = conv, n - conv
    elif "DESTANEX" in df.columns:
        dato["conv"], dato["noconv"] = 0, n

    if rapido:
        return dato

    if "ID_PREDIO" in df.columns:
        dato["predios"] = int(df["ID_PREDIO"].nunique())

    if LLAVE in df.columns:
        llave = [LLAVE]
    else:
        llave = [c for c in COLS_LLAVE if c in df.columns]
        if not llave and "CONSTRUCCION_ID" in df.columns:
            llave = ["CONSTRUCCION_ID"]
    if llave:
        dato["dups"] = int(df.duplicated(subset=llave).sum())
    return dato


class Control:
    """Acumula los cortes, avisa en el momento y al final dice donde fallo."""

    def __init__(self, activo=None, rapido=False, estricto=False, ejemplos=5):
        if activo is None:
            activo = os.environ.get("SIN_CONTROL_FILAS", "") == ""
        self.activo = activo
        self.rapido = rapido
        self.estricto = estricto
        self.ejemplos = ejemplos
        self.etapas = []
        self.costo = 0.0
        self._entrada = None
        self._previa = None

    def marca(self, nombre, df=None, convencionales=None,
              no_convencionales=None, baja_ok=None):
        """Registra una etapa. baja_ok es el motivo por el que puede bajar."""
        if not self.activo:
            return
        t0 = time.perf_counter()

        if df is not None:
            dato = _contar(df, self.rapido)
            llaves = None if self.rapido else _llaves(df)
        else:
            partes = [p for p in (convencionales, no_convencionales)
                      if p is not None]
            if not partes:
                return
            dato = {
                "filas": sum(len(p) for p in partes),
                "conv": len(convencionales) if convencionales is not None else 0,
                "noconv": (len(no_convencionales)
                           if no_convencionales is not None else 0),
                "predios": None, "dups": None,
            }
            llaves = None
            if not self.rapido:
                dato["dups"] = sum(_contar(p)["dups"] or 0 for p in partes)
                trozos = [_llaves(p) for p in partes]
                if all(t is not None for t in trozos):
                    llaves = (trozos[0].append(trozos[1:]) if len(trozos) > 1
                              else trozos[0])

        dato.update(nombre=nombre, baja_ok=baja_ok,
                    perdidas=None, nuevas=None, ejemplos=[])

        if llaves is not None:
            if self._previa is not None:
                faltan = self._previa[~self._previa.isin(llaves)]
                dato["perdidas"] = len(faltan)
                dato["nuevas"] = int((~llaves.isin(self._previa)).sum())
                dato["ejemplos"] = list(faltan[:self.ejemplos])
            if self._entrada is None:
                self._entrada = llaves
            self._previa = llaves

        self.etapas.append(dato)
        self.costo += time.perf_counter() - t0
        self._avisar(dato)

    def _avisar(self, e):
        """Grita en el momento, no al final de veinte minutos."""
        problemas = []
        if e["perdidas"] and not e["baja_ok"]:
            problemas.append(f"perdio {e['perdidas']:,} llaves")
        if e["nuevas"]:
            problemas.append(f"aparecieron {e['nuevas']:,} llaves nuevas")
        if not problemas:
            return
        print(f"\n   !! CONTROL DE FILAS - {e['nombre']}: {', '.join(problemas)}")
        if e["ejemplos"]:
            print(f"      ejemplos: {', '.join(map(str, e['ejemplos']))}")
        if self.estricto:
            raise RuntimeError(
                f"control de filas: {e['nombre']} {', '.join(problemas)}")

    def perdidas(self):
        """Las llaves que estaban en la entrada y ya no estan."""
        if self._entrada is None or self._previa is None:
            return pd.Index([])
        return self._entrada[~self._entrada.isin(self._previa)]

    def volcar(self, ruta="./output/control_filas_perdidas.txt"):
        """Deja en un archivo las llaves que se perdieron desde la entrada."""
        p = self.perdidas()
        if not len(p):
            return None
        carpeta = os.path.dirname(ruta)
        if carpeta:
            os.makedirs(carpeta, exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as f:
            f.write("\n".join(map(str, p)))
        print(f"   {len(p):,} llaves perdidas listadas en {ruta}")
        return ruta

    def resumen(self, titulo="CONTROL DE FILAS"):
        """Imprime la tabla y devuelve la lista de descuadres."""
        if not self.activo or not self.etapas:
            return []

        def f(v):
            return "-" if v is None else f"{v:,}"

        ancho = max(22, max(len(e["nombre"]) for e in self.etapas))
        linea = "=" * (ancho + 62)
        print("\n" + linea)
        print(titulo)
        print(linea)
        print(f"{'etapa':<{ancho}} {'filas':>10} {'conv':>9} {'no conv':>9} "
              f"{'dup':>5} {'se fueron':>10} {'llegaron':>9}")
        print("-" * (ancho + 62))

        alertas = []
        for e in self.etapas:
            if e["perdidas"] and not e["baja_ok"]:
                alertas.append((e["nombre"],
                                f"perdio {e['perdidas']:,} llaves",
                                e["ejemplos"]))
            if e["nuevas"]:
                alertas.append((e["nombre"],
                                f"aparecieron {e['nuevas']:,} llaves", []))

            print(f"{e['nombre']:<{ancho}} {f(e['filas']):>10} {f(e['conv']):>9} "
                  f"{f(e['noconv']):>9} {f(e['dups']):>5} "
                  f"{f(e['perdidas']):>10} {f(e['nuevas']):>9}")
            if e["baja_ok"] and e["perdidas"]:
                print(f"{'':<{ancho}}   baja prevista, "
                      f"{e['perdidas']:,}: {e['baja_ok']}")

        print("-" * (ancho + 62))
        ent, sal = self.etapas[0]["filas"], self.etapas[-1]["filas"]
        print(f"entrada {ent:,} -> salida {sal:,}   ({sal - ent:+,})")
        print(f"el control costo {self.costo:.1f} s")

        if alertas:
            print("\nDESCUADRES SIN EXPLICAR:")
            for nombre, que, ejs in alertas:
                print(f"   {nombre}: {que}")
                if ejs:
                    print(f"      ejemplos: {', '.join(map(str, ejs))}")
        else:
            print("\nSin descuadres: entraron y salieron las mismas filas.")
        print(linea + "\n")
        return alertas


def _si(nombre):
    return os.environ.get(nombre, "").strip().lower() in ("1", "true", "si", "s")


# Compartido por todos los modulos, como perf.crono: cada uno marca su etapa y
# main.py imprime la tabla al final.
#
#   SIN_CONTROL_FILAS=1        lo apaga entero
#   CONTROL_FILAS_RAPIDO=1     solo totales, sin llaves ni duplicados (15 ms)
#   CONTROL_FILAS_ESTRICTO=1   detiene el proceso en el primer descuadre
#
# Estricto queda apagado por defecto porque hoy hay dos descuadres conocidos
# -las 26 de cruce_uso_ladm y las 538 del dedup de salida-. Cuando esos dos
# esten resueltos o declarados, se puede encender y el pipeline deja de
# producir salidas incompletas en silencio.
control = Control(rapido=_si("CONTROL_FILAS_RAPIDO"),
                  estricto=_si("CONTROL_FILAS_ESTRICTO"))
