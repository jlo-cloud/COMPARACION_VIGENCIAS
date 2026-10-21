"""Comunas: grupos de las tablas de valor y seleccion de lo que se liquida.

Un solo lugar para las listas de comunas. Antes estaban repetidas en
tabla_construccion.py, Liquidacion_tablas.py y Liquidacion_final.py, y la
liquidacion final seguia filtrando las 7 comunas de la vigencia 2026.

La comuna sale del numero predial nacional, posiciones [9:11]. En lo rural esas
posiciones traen el corregimiento (51 a 65).
"""

from __future__ import annotations

# Grupos de las tablas de valor 2027 (input/Reglas.xlsx).
COMUNAS_7 = ["02", "03", "04", "08", "17", "19", "22"]
COMUNAS_10_REGLAS = ["01", "07", "09", "10", "11", "12", "14", "15", "20", "21"]

# Las cinco comunas que Reglas.xlsx no nombra. Se liquidan con los valores del
# grupo de 10 por DECISION (no sale de los datos); si les hacen tabla propia,
# se agrega una columna *_5C_* al consolidado y pasan a un grupo nuevo.
COMUNAS_FALTANTES = ["05", "06", "13", "16", "18"]
INCLUIR_COMUNAS_FALTANTES = True

COMUNAS_10 = COMUNAS_10_REGLAS + (COMUNAS_FALTANTES if INCLUIR_COMUNAS_FALTANTES else [])
COMUNAS_REGLAS = sorted(COMUNAS_7 + COMUNAS_10_REGLAS)          # las 17 de Reglas.xlsx
COMUNAS_URBANAS = [f"{i:02d}" for i in range(1, 23)]
CORREGIMIENTOS = [f"{i:02d}" for i in range(51, 66)]

# Que familia de modelo tiene cada comuna (model_liq.py).
COMUNAS_MODELO_2025 = ["01", "03", "09", "10", "11", "12", "22"]
COMUNAS_MODELO_2024 = ["02", "04", "08", "17", "19"]


def normalizar(comunas) -> list[str]:
    """['1', 3, '03', 'rural'] -> ['01', '03', + corregimientos]. Sin duplicados, ordenadas."""
    salida = []
    for c in comunas or []:
        t = str(c).strip().lower()
        if t in ("rural", "rurales", "corregimientos"):
            salida += CORREGIMIENTOS
        elif t.isdigit():
            salida.append(f"{int(t):02d}")
    return sorted(set(salida))


def grupo_tablas(comuna: str) -> str | None:
    """'7C', '10C' o None (sin tablas de valor)."""
    if comuna in COMUNAS_7:
        return "7C"
    if comuna in COMUNAS_10:
        return "10C"
    return None


def familia_modelo(comuna: str) -> str | None:
    if comuna in COMUNAS_MODELO_2025:
        return "2025"
    if comuna in COMUNAS_MODELO_2024:
        return "2024"
    return None


def seleccionadas() -> list[str]:
    """Las comunas que pide el manifiesto (parametro comunas_liquidar).

    Sin el parametro -manifiestos anteriores a la seleccion- se toman las 17 de
    Reglas.xlsx y se avisa, para que nunca se liquide un alcance sin decirlo.
    """
    import config

    pedidas = config.get_param("comunas_liquidar")
    if not pedidas:
        print("[WARN] El manifiesto no trae 'comunas_liquidar': se liquidan las 17 comunas de Reglas.xlsx.")
        return list(COMUNAS_REGLAS)
    return normalizar(pedidas)


def de_npn(npn) -> "object":
    """Comuna (o corregimiento) a partir del numero predial nacional. Acepta una Serie."""
    return npn.astype(str).str[9:11]
