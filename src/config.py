import json
import os
from pathlib import Path

from manifest_contract import resolve_path, validate_manifest

# Valores por defecto en caso de no cargar manifiesto
MANIFEST_DATA = {
    "run_id": "DEFAULT",
    "vigencia_objetivo": 2027,
    "insumos": {
        "export_predio_2024": "./input/export_liq/export_predio_2025.txt",
        "export_predio_2025": "./input/export_liq/export_predio_20260717.parquet",
        "export_predio_actual": "./input/export_liq/export_predio_20260717.parquet",
        "export_construccion_2024": "./input/export_liq/export_construccion_2025.txt"
    },
    "parametros": {
        "generar_excel": True
    }
}

MANIFEST_PATH = None


def load_manifest(manifest_path, validate=True):
    # Carga el archivo JSON que contiene la definicion de insumos de la vigencia
    global MANIFEST_DATA, MANIFEST_PATH
    if os.path.exists(manifest_path):
        with open(manifest_path, 'r', encoding='utf-8') as f:
            MANIFEST_DATA = json.load(f)
            MANIFEST_PATH = str(Path(manifest_path).resolve())
            if validate:
                errors = validate_manifest(MANIFEST_DATA, MANIFEST_PATH)
                if errors:
                    raise ValueError("Manifiesto invalido:\n - " + "\n - ".join(errors))
            print(f"[OK] Manifiesto cargado: {manifest_path} (Run ID: {MANIFEST_DATA.get('run_id')})")
    else:
        print(f"[WARN] Manifiesto no encontrado en {manifest_path}. Usando valores por defecto.")

def get_insumo(key, default=None):
    value = MANIFEST_DATA.get('insumos', {}).get(key, default)
    if value is None:
        return None
    base = Path(MANIFEST_PATH).parent if MANIFEST_PATH else Path.cwd()
    return str(resolve_path(value, base))

def get_param(key, default=None):
    return MANIFEST_DATA.get('parametros', {}).get(key, default)


def get_workspace():
    value = MANIFEST_DATA.get('workspace') or os.environ.get('LIQUIDACION_WORKSPACE') or os.getcwd()
    base = Path(MANIFEST_PATH).parent if MANIFEST_PATH else Path.cwd()
    return str(resolve_path(value, base))

