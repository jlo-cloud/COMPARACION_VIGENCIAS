"""
Los insumos de una corrida: que archivo es cada uno, como se reconoce, si
esta bien, y que comunas se liquidan.

Lo usa la ventana (preliquidar_app.py) para detectar y validar, y lo leen los
modulos del proceso para saber que archivo abrir. La ventana deja un
manifiesto (JSON) en la carpeta de la corrida y lo pasa en PRELIQ_MANIFIESTO.

Sin manifiesto -python src/main.py- ruta() devuelve la ruta de siempre de cada
modulo y comunas() devuelve None: la corrida es exactamente la de antes.
"""
import json
import os
import re
from pathlib import Path


# (clave, etiqueta, obligatorio, para que se usa, regla para reconocerlo)
# La regla mira el NOMBRE y las COLUMNAS: el nombre solo no alcanza (hay varios
# export de predio con las mismas columnas) y las columnas solas tampoco.
def _tiene(cols, *nombres):
    return set(nombres) <= set(cols)


INSUMOS = [
    ("predio_zhf", "Predios con ZHF de la vigencia", True,
     "La base de la corrida: predio, ZHF, estrato, condicion",
     lambda n, c: "zhf" in n and _tiene(c, "ID_PREDIO", "ZHF", "NUMERO_PREDIAL_NACIONAL", "AVALPRED")),
    ("construcciones_conv", "Construcciones convencionales", True,
     "Las construcciones que se liquidan por tabla o por modelo",
     lambda n, c: _tiene(c, "ID_PREDIO", "DESTINOCONS", "PUNTCONS", "ESPECIAL")),
    ("construcciones_noconv", "Construcciones no convencionales (anexos)", True,
     "Los anexos (T10)",
     lambda n, c: _tiene(c, "ID_PREDIO", "DESTANEX", "TIPOANEXO", "ACONANEX") and "DESTINOCONS" not in c),
    ("predio_anterior", "Predios de la entrega anterior", True,
     "ZHF_ANTERIOR (cambio de tipologia) y las variables de los modelos",
     lambda n, c: re.search(r"export_predio_\d{8}", n) is not None
     and _tiene(c, "ID_PREDIO", "ZHF", "NUMERO_PREDIAL_NACIONAL")),
    ("terreno_proyectado", "Terreno proyectado 2027", False,
     "El terreno del avaluo 2027 en la comparacion; sin el, cada predio conserva su VTER",
     lambda n, c: _tiene(c, "ID_PREDIO", "VTERR_COM_2027", "inc")),
    ("zhg", "ZHG 2024-2025", False,
     "Valor del suelo de los modelos y de los escenarios",
     lambda n, c: _tiene(c, "ID_PREDIO", "ZHG_2024", "ZHG_2025")),
    ("modelo_uso28", "Apoyo del modelo de uso 028", False,
     "Solo los modelos (hoy apagados)",
     lambda n, c: _tiene(c, "ID_CONSTRUCCION", "ID_PREDIO", "NUM_CONST_TERR")),
    ("export_predio_2025", "Export de predios 2025", False,
     "Solo los escenarios 2024/2025",
     lambda n, c: "2025" in n and "zhf" not in n
     and _tiene(c, "ID_PREDIO", "AVALPRED", "VIGEPRED", "COMUNA")),
    ("export_construccion_2025", "Export de construcciones 2025", False,
     "Solo los escenarios 2024/2025",
     lambda n, c: "2025" in n and _tiene(c, "ID_PREDIO", "ID_CONSTRUCCION", "DESTINOCONS", "CONSCONS")),
]
ETIQUETA = {k: e for k, e, *_ in INSUMOS}
OBLIGATORIO = {k: o for k, _, o, *_ in INSUMOS}
# Los que necesitan los escenarios (--todas), ademas de los obligatorios.
PARA_ESCENARIOS = ["zhg", "export_predio_2025", "export_construccion_2025"]
# Pares que no pueden ser el mismo archivo: con la entrega anterior igual a la
# actual, el cambio de tipologia sale en cero sin que nada avise.
DISTINTOS = [("predio_zhf", "predio_anterior"),
             ("construcciones_conv", "construcciones_noconv")]
EXTENSIONES = {".parquet", ".txt", ".csv"}

COMUNAS_URBANAS = [f"{i:02d}" for i in range(1, 23)]
COMUNAS_RURALES = [f"{i:02d}" for i in range(51, 66)]


# ---------------------------------------------------------------------------
# Lo que lee el proceso
# ---------------------------------------------------------------------------
_manifiesto = None


def manifiesto() -> dict:
    global _manifiesto
    if _manifiesto is None:
        ruta = os.environ.get("PRELIQ_MANIFIESTO")
        _manifiesto = (json.loads(Path(ruta).read_text(encoding="utf-8"))
                       if ruta and Path(ruta).is_file() else {})
    return _manifiesto


def ruta(clave: str, por_defecto=None):
    """El archivo que el manifiesto asigna a la clave, o la ruta de siempre."""
    return (manifiesto().get("insumos") or {}).get(clave) or por_defecto


def comunas():
    """Las comunas a liquidar, o None para todas (lo de siempre)."""
    return manifiesto().get("comunas") or None


# Cada vigencia se liquida con las reglas del ejercicio que la produjo: el
# ejercicio 2024 produjo la vigencia 2025, el 2025 la 2026 y la propuesta
# actual la 2027. Las tablas de 2024 y 2025 estan dentro de su codigo; las de
# 2027 se eligen por version en input/tablas/input/.
VIGENCIAS = {
    # 2027 todavia no tiene modelos: lo que va por modelo queda en 0 y la
    # casilla no se puede prender (usaria las familias 2024/2025).
    2027: {"etiqueta": "2027 - propuesta actual", "reglas": "Liquidacion_tablas.py",
           "tablas": "por version (input/tablas/input)", "modelos": None},
    2026: {"etiqueta": "2026 - reglas del ejercicio 2025", "reglas": "Liquidacion_tablas_2025.py",
           "tablas": "las del ejercicio 2025 (en el codigo)", "modelos": "models"},
    2025: {"etiqueta": "2025 - reglas del ejercicio 2024", "reglas": "Liquidacion_tablas_2024.py",
           "tablas": "las del ejercicio 2024 (en el codigo)", "modelos": "models_2024"},
}


def vigencia() -> int:
    return int(manifiesto().get("vigencia") or 2027)


def modelos_activos(vigencia_del_motor: int, por_defecto: bool) -> bool:
    """Si el motor de esa vigencia corre los modelos. Lo decide la casilla de
    la ventana, pero solo en una corrida de ESA vigencia: los escenarios que
    acompanan a una corrida 2027 siguen como siempre."""
    m = manifiesto()
    if m.get("modelos") is None or vigencia() != vigencia_del_motor:
        return por_defecto
    if VIGENCIAS[vigencia_del_motor]["modelos"] is None:
        return False
    return bool(m["modelos"])


def carpeta_modelos(subcarpeta: str, por_defecto: str) -> str:
    """Modelos/<subcarpeta> de la carpeta de modelos elegida, o la de siempre."""
    c = manifiesto().get("carpeta_modelos")
    return str(Path(c) / subcarpeta) if c else por_defecto


def base_construcciones(por_defecto: str) -> str:
    """La base cruzada (todas_las_construcciones.parquet). Una corrida que no
    actualiza la app la deja en su carpeta, para no pisar la de output/ con
    solo algunas comunas."""
    return os.environ.get("PRELIQ_BASE_CONSTRUCCIONES") or por_defecto


# ---------------------------------------------------------------------------
# Detectar y validar (la ventana)
# ---------------------------------------------------------------------------
def columnas(path: Path) -> list:
    """Los nombres de columna sin leer el archivo entero."""
    if path.suffix.lower() == ".parquet":
        import pyarrow.parquet as pq
        return pq.ParquetFile(path).schema_arrow.names
    with open(path, encoding="latin-1") as fh:
        linea = fh.readline()
    sep = "|" if "|" in linea else ("\t" if "\t" in linea else ",")
    return [c.strip().strip('"') for c in linea.rstrip("\r\n").split(sep)]


def _fecha(nombre: str) -> str:
    m = re.findall(r"(20\d{6})", nombre)
    return max(m) if m else ""


def detectar(carpeta) -> dict:
    """{clave: (ruta elegida o None, [candidatos], nota)} recorriendo la carpeta
    y sus subcarpetas. Entre varios candidatos gana la fecha AAAAMMDD mas
    reciente del nombre; si la fecha no decide, se avisa."""
    candidatos = {k: [] for k, *_ in INSUMOS}
    for actual, _, archivos in os.walk(carpeta):
        for a in archivos:
            p = Path(actual) / a
            if p.suffix.lower() not in EXTENSIONES or a.startswith("~$"):
                continue
            try:
                cols = columnas(p)
            except Exception:
                continue
            for clave, _, _, _, regla in INSUMOS:
                try:
                    if regla(a.lower(), cols):
                        candidatos[clave].append(p)
                except Exception:
                    pass
    salida = {}
    for clave, lista in candidatos.items():
        if not lista:
            salida[clave] = (None, [], "no se encontro")
            continue
        lista = sorted(lista, key=lambda p: (_fecha(p.name), p.name), reverse=True)
        nota = "unico" if len(lista) == 1 else f"el mas reciente de {len(lista)}"
        if len(lista) > 1 and _fecha(lista[0].name) == _fecha(lista[1].name):
            nota = f"AMBIGUO entre {len(lista)}: revise"
        salida[clave] = (str(lista[0]), [str(p) for p in lista], nota)
    return salida


def validar(asignados: dict, escenarios: bool = False, comunas_elegidas=None) -> tuple:
    """(errores, avisos). Con errores la corrida no arranca."""
    errores, avisos = [], []
    necesarios = {k for k, o in OBLIGATORIO.items() if o}
    if escenarios:
        necesarios |= set(PARA_ESCENARIOS)
    for clave, etiqueta, obligatorio, _, regla in INSUMOS:
        valor = (asignados.get(clave) or "").strip()
        if not valor:
            if clave in necesarios:
                errores.append(f"Falta: {etiqueta}.")
            elif clave == "terreno_proyectado":
                avisos.append(f"Sin {etiqueta}: en la comparacion cada predio conserva su VTER.")
            continue
        p = Path(valor)
        if not p.is_file():
            errores.append(f"{etiqueta}: no existe {p}.")
            continue
        if p.suffix.lower() not in EXTENSIONES:
            errores.append(f"{etiqueta}: extension {p.suffix} no valida.")
            continue
        if p.stat().st_size == 0:
            errores.append(f"{etiqueta}: el archivo esta vacio.")
            continue
        try:
            if not regla(p.name.lower(), columnas(p)):
                avisos.append(f"{etiqueta}: {p.name} no tiene el nombre o las columnas "
                              f"esperadas; revise que sea el archivo correcto.")
        except Exception as e:
            errores.append(f"{etiqueta}: no se pudo leer ({e}).")
    for a, b in DISTINTOS:
        ra, rb = asignados.get(a), asignados.get(b)
        if ra and rb and Path(ra).resolve() == Path(rb).resolve():
            errores.append(f"{ETIQUETA[a]} y {ETIQUETA[b]} no pueden ser el mismo archivo.")
    if comunas_elegidas is not None and not comunas_elegidas:
        errores.append("No hay comunas marcadas.")
    return errores, avisos
