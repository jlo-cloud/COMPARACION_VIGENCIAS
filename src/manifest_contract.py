"""Contrato versionado de entradas para el liquidador de escritorio.

Este modulo no importa pandas ni el motor. Por eso se puede usar desde la
interfaz y desde las pruebas aun cuando el entorno cientifico no este cargado.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


SUPPORTED_EXTENSIONS = {
    ".parquet", ".txt", ".csv", ".xlsx", ".xls", ".xlsm"
}


@dataclass(frozen=True)
class InputSpec:
    key: str
    label: str
    required: bool = True
    extensions: tuple[str, ...] = tuple(SUPPORTED_EXTENSIONS)
    hint: str = ""


# El motor actual corresponde a la preliquidacion de la vigencia 2027. No se
# habilita 2026 porque el codigo conserva nombres y reglas 2026 internamente;
# ejecutar el mismo contrato con otra etiqueta seria una falsa certificacion.
YEAR_PROFILES = {
    2027: {
        "enabled": True,
        "engine": "preliquidacion-2027",
        "description": "Preliquidacion 2027 con modelos y reglas vigentes.",
    },
    2026: {
        "enabled": False,
        "engine": None,
        "description": "Pendiente de contrato y validacion de regresion 2026.",
    },
}


INPUT_SPECS = (
    InputSpec("export_predio_actual", "Predios de la vigencia", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_construccion_actual_conv", "Construcciones convencionales", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_construccion_actual_noconv", "Construcciones no convencionales", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_terreno_actual", "Terrenos de la vigencia", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_predio_anterior", "Predios entrega anterior (ZHF anterior)", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_predio_2024", "Predios historicos para modelos 2024", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_predio_2025", "Predios historicos para modelos 2025", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("export_construccion_2024", "Construcciones historicas 2024", extensions=(".parquet", ".txt", ".csv")),
    InputSpec("zhg_historico", "ZHG 2024-2025", extensions=(".parquet",)),
    InputSpec("modelo_uso28", "Apoyo modelo uso 028", required=False, extensions=(".txt", ".csv")),
    InputSpec("predios_especiales", "Predios y terrenos especiales", extensions=(".xlsx", ".xlsm", ".xls")),
    InputSpec("cambio_npn", "Cambios de numero predial", extensions=(".xlsx", ".xlsm", ".xls")),
    InputSpec("predio_vigencia_anterior", "Predios para comparar avaluos", extensions=(".parquet",)),
    InputSpec("preliquidacion_referencia", "Preliquidacion de referencia", extensions=(".parquet",)),
    # Opcional: sin el, se usan las de la version configurada que vienen de la
    # fuente (upstream.json), sincronizadas en el repositorio y en el ejecutable.
    InputSpec("tablas_valor", "Tablas de valor consolidadas", required=False, extensions=(".xlsx", ".xlsm", ".xls")),
)


def enabled_years() -> list[int]:
    return [year for year, profile in YEAR_PROFILES.items() if profile["enabled"]]


def resolve_path(value: str | os.PathLike[str], manifest_dir: Path) -> Path:
    path = Path(os.path.expandvars(os.path.expanduser(str(value))))
    if not path.is_absolute():
        path = manifest_dir / path
    return path.resolve()


# Insumos que NUNCA pueden ser el mismo archivo. Con la entrega anterior igual
# a la actual, la ZHF anterior sale igual a la actual y toda comparacion entre
# vigencias da cero cambios sin que nada avise. (export_predio_anterior y
# export_predio_2025 si pueden coincidir: hoy son el mismo archivo.)
DEBEN_SER_DISTINTOS = [
    ("export_predio_actual", "export_predio_anterior"),
    ("export_predio_actual", "predio_vigencia_anterior"),
    ("export_predio_actual", "export_predio_2024"),
    ("export_predio_actual", "export_predio_2025"),
    ("export_construccion_actual_conv", "export_construccion_actual_noconv"),
    ("export_construccion_actual_conv", "export_construccion_2024"),
]

COMUNAS_VALIDAS = {f"{i:02d}" for i in list(range(1, 23)) + list(range(51, 66))}


def huella(path: Path) -> str:
    """Tamano + hash del primer y ultimo MB: distingue archivos sin leerlos completos."""
    h = hashlib.sha1()
    tam = path.stat().st_size
    with open(path, "rb") as fh:
        h.update(fh.read(1 << 20))
        if tam > (2 << 20):
            fh.seek(-(1 << 20), os.SEEK_END)
            h.update(fh.read(1 << 20))
    return f"{tam}:{h.hexdigest()}"


def validate_manifest(data: dict, manifest_path: str | os.PathLike[str] | None = None) -> list[str]:
    errors: list[str] = []
    base = Path(manifest_path).resolve().parent if manifest_path else Path.cwd()
    year = data.get("vigencia_objetivo")
    profile = YEAR_PROFILES.get(year)
    if profile is None:
        errors.append(f"La vigencia {year!r} no tiene un perfil registrado.")
    elif not profile["enabled"]:
        errors.append(f"La vigencia {year} no esta habilitada: {profile['description']}")

    run_id = str(data.get("run_id", "")).strip()
    if not run_id:
        errors.append("Falta run_id.")

    workspace = data.get("workspace")
    if not workspace:
        errors.append("Falta workspace.")
    else:
        workspace_path = resolve_path(workspace, base)
        if workspace_path.exists() and not workspace_path.is_dir():
            errors.append(f"El workspace no es una carpeta: {workspace_path}")

    insumos = data.get("insumos") or {}
    for spec in INPUT_SPECS:
        value = insumos.get(spec.key)
        if not value:
            if spec.required:
                errors.append(f"Falta el insumo obligatorio: {spec.label} ({spec.key}).")
            continue
        path = resolve_path(value, base)
        if not path.is_file():
            errors.append(f"No existe {spec.label}: {path}")
        elif path.suffix.lower() not in spec.extensions:
            allowed = ", ".join(spec.extensions)
            errors.append(f"Formato no valido para {spec.label}: {path.suffix} (use {allowed}).")
        elif path.stat().st_size == 0:
            errors.append(f"El archivo esta vacio: {path}")

    etiquetas = {s.key: s.label for s in INPUT_SPECS}
    huellas = {}
    for key, value in insumos.items():
        if not value:
            continue
        path = resolve_path(value, base)
        if path.is_file() and path.stat().st_size > 0:
            try:
                huellas[key] = huella(path)
            except OSError:
                pass
    for a, b in DEBEN_SER_DISTINTOS:
        if a in huellas and huellas.get(a) == huellas.get(b):
            errors.append(f"{etiquetas.get(a, a)} y {etiquetas.get(b, b)} son el mismo archivo: "
                          f"deben ser entregas distintas.")

    params = data.get("parametros") or {}
    comunas = params.get("comunas_liquidar")
    if comunas is not None:
        if not isinstance(comunas, list) or not comunas:
            errors.append("comunas_liquidar debe ser una lista con al menos una comuna.")
        else:
            malas = [c for c in comunas if f"{int(c):02d}" not in COMUNAS_VALIDAS] if all(
                str(c).strip().isdigit() for c in comunas) else [c for c in comunas if not str(c).strip().isdigit()]
            if malas:
                errors.append(f"Comunas no validas en comunas_liquidar: {malas} (01-22 urbanas, 51-65 rurales).")
    return errors


TIPOS_CORRIDA = ("preliquidacion", "liquidacion")
FORMATOS_SALIDA = ("txt", "parquet", "xlsx")


def build_manifest(year: int, workspace: str, inputs: dict[str, str], include_scenarios: bool = True,
                   tipo_corrida: str = "preliquidacion", formatos: list[str] | None = None,
                   comunas: list[str] | None = None, liquidar_parqueaderos: bool = False,
                   prevalidacion_bloqueante: bool = True, version_tablas: str | None = None,
                   carpeta_modelos: str | None = None) -> dict:
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return {
        "schema_version": 1,
        "run_id": f"LIQ-{year}-{stamp}",
        "vigencia_objetivo": year,
        "engine_profile": YEAR_PROFILES.get(year, {}).get("engine"),
        "workspace": str(Path(workspace).resolve()),
        "insumos": {key: str(Path(value).resolve()) for key, value in inputs.items() if value},
        "parametros": {
            "generar_excel": True,
            "comuna_urbana_maxima": 22,
            "generar_escenarios": bool(include_scenarios),
            "calidad_bloqueante": True,
            # preliquidacion: parquet + Excel de revision; liquidacion: ademas .txt.
            "tipo_corrida": tipo_corrida if tipo_corrida in TIPOS_CORRIDA else "preliquidacion",
            "formatos_salida": [f for f in (formatos or []) if f in FORMATOS_SALIDA] or None,
            "publicar_por_carpetas": True,
            # Comunas a liquidar (se eligen en la interfaz). Sin esta lista se
            # toman las 17 de Reglas.xlsx y se avisa.
            "comunas_liquidar": sorted({f"{int(c):02d}" for c in comunas}) if comunas else None,
            # Parqueaderos T12: sus valores son los de 2025 y no estan avalados.
            "liquidar_parqueaderos": bool(liquidar_parqueaderos),
            # En una liquidacion, una comuna NO APTA en la prevalidacion detiene la corrida.
            "prevalidacion_bloqueante": bool(prevalidacion_bloqueante),
            # Version de las tablas de valor (V1, V2...). Sin tablas_valor en los
            # insumos se usa el consolidado de esta version sincronizado de la fuente.
            "version_tablas": (version_tablas or "").strip().upper() or None,
            # Carpeta con modelos (subcarpetas models/ y models_2024/) para probar
            # modelos nuevos sin recompilar. Vacio = los del repositorio / ejecutable.
            "carpeta_modelos": carpeta_modelos or None,
        },
    }


def save_manifest(data: dict, destination: str | os.PathLike[str]) -> Path:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    temporary.replace(path)
    return path


# ---------------------------------------------------------------------------
# Deteccion automatica de insumos
#
# Los nombres cambian de una entrega a otra (export_predio.txt vs
# export_predio_2025.txt, construccion_convencional vs export_construccion_
# homologado), asi que el nombre solo no alcanza. Cada insumo se reconoce por
# su CONTENIDO -las columnas del parquet/txt o las hojas del Excel- y el nombre
# solo desempata. Entre varios candidatos validos gana la fecha AAAAMMDD mas
# reciente del nombre, como hacia el motor original; si no hay fecha que
# decida, no se adivina y se reporta la ambiguedad.
# ---------------------------------------------------------------------------

_DATE_IN_NAME = re.compile(r"(20\d{2})(0[1-9]|1[0-2])([0-3]\d)")
_SKIP_DIRS = {".git", ".venv", ".venv-build", "__pycache__", "node_modules", "build", "dist"}
_TEXT_EXT = {".txt", ".csv"}
_EXCEL_EXT = {".xlsx", ".xlsm"}
_MAX_EXCEL_HEADER_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class DetectionRule:
    columns: frozenset[str] = frozenset()     # todas deben estar
    sheets: frozenset[str] = frozenset()      # todas deben estar (Excel)
    without_columns: frozenset[str] = frozenset()
    name: str | None = None                   # regex que el nombre debe cumplir
    exclude_name: str | None = None           # regex que descarta por nombre
    extensions: tuple[str, ...] = ()
    prefer: str = "newest"                    # newest | oldest (por fecha en el nombre)


def _rule(columns=(), sheets=(), without=(), **kwargs) -> DetectionRule:
    return DetectionRule(frozenset(columns), frozenset(sheets), frozenset(without), **kwargs)


_PREDIO_COLS = ("ID_PREDIO", "AVALPRED", "ZHF")
DETECTION_RULES: dict[str, DetectionRule] = {
    # <fecha>_export_predio_zhf_<vigencia>: el predio principal de la corrida.
    "export_predio_actual": _rule(_PREDIO_COLS, name=r"zhf", extensions=(".parquet",)),
    "export_construccion_actual_conv": _rule(
        ("ID_CONSTRUCCION", "PUNTCONS", "VALOR_M2", "INTEGRAL"),
        exclude_name=r"no.?conv|anexo", extensions=(".parquet", ".txt", ".csv")),
    "export_construccion_actual_noconv": _rule(
        ("ID_PREDIO", "TIPOANEXO", "ACONANEX"), extensions=(".parquet", ".txt", ".csv")),
    "export_terreno_actual": _rule(
        ("ID_PREDIO", "AMETTERR", "VALOTERR"), extensions=(".parquet", ".txt", ".csv")),
    # export_predio_<fecha>: entrega anterior (ZHF_ANTERIOR) y base de los
    # modelos 2025. Es el mismo archivo para los dos insumos.
    "export_predio_anterior": _rule(_PREDIO_COLS, name=r"export_predio_\d{8}", exclude_name=r"zhf",
                                    extensions=(".parquet",)),
    "export_predio_2025": _rule(_PREDIO_COLS + ("VALOR_M2_SUELO", "LATITUDE"), name=r"export_predio_\d{8}",
                                exclude_name=r"zhf", extensions=(".parquet",)),
    # Los export .txt de la vigencia pasada (export_predio_2025.txt o
    # export_predio.txt, segun quien lo descargue).
    "export_predio_2024": _rule(_PREDIO_COLS + ("VALOR_M2_SUELO",), name=r"predio",
                                exclude_name=r"zhf", extensions=(".txt", ".csv")),
    "export_construccion_2024": _rule(("ID_CONSTRUCCION", "PUNTCONS", "VALORCONS"), name=r"construccion",
                                      extensions=(".txt", ".csv")),
    "zhg_historico": _rule(("ID_PREDIO", "ZHG_2024", "ZHG_2025"), extensions=(".parquet",)),
    "modelo_uso28": _rule(("ID_CONSTRUCCION", "NUM_CONST_TERR"), extensions=(".txt", ".csv")),
    "predios_especiales": _rule(sheets=("TERRENOS_ESPECIALES",), exclude_name=r"revisar|malo|_ante\b|\(\d\)",
                                extensions=(".xlsx", ".xlsm")),
    "cambio_npn": _rule(("ID_PREDIO", "NPN_ANTERIOR", "NPN_AJUSTADO"), extensions=(".xlsx", ".xlsm")),
    # predio_<fecha>.parquet de la vigencia anterior: de las fotos del predio
    # es la MAS VIEJA; las recientes son la vigencia en curso.
    "predio_vigencia_anterior": _rule(("ID_PREDIO", "AVALPRED"), without=("AVALUO_COM_2026",),
                                      name=r"^predio_\d{8}", extensions=(".parquet",), prefer="oldest"),
    "preliquidacion_referencia": _rule(("ID_PREDIO", "AVALUO_COM_2026"), extensions=(".parquet",)),
    "tablas_valor": _rule(sheets=("CONVENCIONALES", "NO_CONVENCIONALES"), extensions=(".xlsx", ".xlsm")),
}


@dataclass
class Discovery:
    found: dict[str, str]
    reasons: dict[str, str]
    ambiguous: dict[str, list[str]]
    missing: list[str]
    scanned: int

    def report(self) -> str:
        lines = [f"Archivos revisados: {self.scanned}"]
        for spec in INPUT_SPECS:
            if spec.key in self.found:
                lines.append(f"[OK]    {spec.label}: {Path(self.found[spec.key]).name}  ({self.reasons[spec.key]})")
            elif spec.key in self.ambiguous:
                names = ", ".join(Path(p).name for p in self.ambiguous[spec.key])
                lines.append(f"[DUDA]  {spec.label}: varios candidatos sin fecha que desempate -> {names}")
            else:
                tag = "[FALTA]" if spec.required else "[OPC]  "
                lines.append(f"{tag} {spec.label}: no hay ningun archivo con la estructura esperada")
        return "\n".join(lines)


def _clean(value: str) -> str:
    return value.strip().strip('"').strip("'").strip().upper()


def _text_columns(path: Path) -> set[str]:
    with open(path, "r", encoding="latin-1", errors="replace") as handle:
        first = handle.readline().lstrip("﻿ï»¿")
    for sep in ("|", ";", "\t", ","):
        if sep in first:
            return {_clean(c) for c in first.split(sep)}
    return {_clean(first)}


def _excel_structure(path: Path) -> tuple[set[str], set[str]]:
    """Hojas (via zip, barato) y encabezados de la primera fila de cada hoja."""
    import zipfile

    with zipfile.ZipFile(path) as archive:
        workbook = archive.read("xl/workbook.xml").decode("utf-8", errors="replace")
    sheets = {_clean(s) for s in re.findall(r'<sheet[^>]*\bname="([^"]+)"', workbook)}
    columns: set[str] = set()
    if path.stat().st_size <= _MAX_EXCEL_HEADER_BYTES:
        try:
            import openpyxl

            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
            try:
                for sheet in book.worksheets:
                    for row in sheet.iter_rows(max_row=1, values_only=True):
                        columns |= {_clean(str(v)) for v in row if v is not None}
            finally:
                book.close()
        except Exception:
            pass
    return sheets, columns


def _structure(path: Path) -> tuple[set[str], set[str]] | None:
    """(columnas, hojas) del archivo, o None si no se puede leer."""
    ext = path.suffix.lower()
    try:
        if ext == ".parquet":
            import pyarrow.parquet as pq

            return {_clean(c) for c in pq.read_schema(path).names}, set()
        if ext in _TEXT_EXT:
            return _text_columns(path), set()
        if ext in _EXCEL_EXT:
            sheets, columns = _excel_structure(path)
            return columns, sheets
    except Exception:
        return None
    return None


def _name_date(path: Path) -> str | None:
    dates = ["".join(m) for m in _DATE_IN_NAME.findall(path.name)]
    return max(dates) if dates else None


def _matches(rule: DetectionRule, path: Path, columns: set[str], sheets: set[str]) -> bool:
    name = path.name.lower()
    if rule.extensions and path.suffix.lower() not in rule.extensions:
        return False
    if rule.name and not re.search(rule.name, name, re.IGNORECASE):
        return False
    if rule.exclude_name and re.search(rule.exclude_name, name, re.IGNORECASE):
        return False
    return (rule.columns <= columns and rule.sheets <= sheets
            and not (rule.without_columns & columns))


def _iter_files(root: Path) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in _SKIP_DIRS and not d.startswith(".")]
        for filename in files:
            path = Path(current) / filename
            if filename.startswith("~$") or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            yield path


def discover_inputs_detailed(folder: str | os.PathLike[str]) -> Discovery:
    root = Path(folder)
    if not root.is_dir():
        return Discovery({}, {}, {}, [s.key for s in INPUT_SPECS], 0)

    structures = {}
    for path in _iter_files(root):
        info = _structure(path)
        if info is not None:
            structures[path] = info

    found: dict[str, str] = {}
    reasons: dict[str, str] = {}
    ambiguous: dict[str, list[str]] = {}
    for spec in INPUT_SPECS:
        rule = DETECTION_RULES[spec.key]
        candidates = [p for p, (cols, sheets) in structures.items() if _matches(rule, p, cols, sheets)]
        if not candidates:
            continue
        if len(candidates) == 1:
            chosen, why = candidates[0], "unico con esa estructura"
        else:
            dated = [p for p in candidates if _name_date(p)]
            if not dated:
                ambiguous[spec.key] = [str(p.resolve()) for p in candidates]
                continue
            ordered = sorted(dated, key=_name_date, reverse=(rule.prefer == "newest"))
            if len(ordered) > 1 and _name_date(ordered[0]) == _name_date(ordered[1]):
                ambiguous[spec.key] = [str(p.resolve()) for p in candidates]
                continue
            chosen = ordered[0]
            which = "mas reciente" if rule.prefer == "newest" else "mas antigua"
            why = f"fecha {which} entre {len(candidates)} candidatos"
        found[spec.key] = str(chosen.resolve())
        reasons[spec.key] = why

    missing = [s.key for s in INPUT_SPECS if s.key not in found]
    return Discovery(found, reasons, ambiguous, missing, len(structures))


def discover_inputs(folder: str | os.PathLike[str]) -> dict[str, str]:
    """Sugiere archivos por contenido; nunca elige a ciegas entre dos candidatos."""
    return discover_inputs_detailed(folder).found
