# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules
repo = Path(SPEC).resolve().parent
# Los pipelines M02 (GLM) referencian statsmodels y patsy solo desde el .pkl;
# ningun modulo del codigo los importa, asi que PyInstaller no los detecta solo.
_sin_tests = lambda name: '.tests' not in name and not name.endswith('.conftest')
glm_modules = collect_submodules('statsmodels', filter=_sin_tests) + collect_submodules('patsy', filter=_sin_tests)
xgboost_binaries = collect_dynamic_libs('xgboost')
xgboost_data = collect_data_files('xgboost', include_py_files=False)
hidden = [
    # Clases referenciadas directamente dentro de los modelos .pkl.
    'sklearn._loss.link',
    'sklearn._loss.loss',
    'sklearn.dummy',
    'sklearn.ensemble._forest',
    'sklearn.ensemble._gb',
    'sklearn.pipeline',
    'sklearn.preprocessing._data',
    'sklearn.tree._classes',
    'sklearn.tree._tree',
    'xgboost.core',
    'xgboost.sklearn',
    # Se importan dentro de funciones: escenarios y reliquidacion.
    'escenarios',
    'reliquidacion',
    'Liquidacion_tablas_2024',
    'Liquidacion_tablas_2025',
    'comunas',
    'prevalidacion_comunas',
    'validacion_preliquidacion',
    'contrato_modelos',
    'sincronizar_upstream',
] + glm_modules

a = Analysis(
    [str(repo / 'src' / 'desktop_app.py')],
    pathex=[str(repo / 'src')],
    binaries=xgboost_binaries,
    # Modelos, tablas de valor consolidadas sincronizadas de la fuente
    # (upstream.json) y la procedencia (UPSTREAM.lock.json).
    datas=[(str(repo / 'Modelos'), 'Modelos'), (str(repo / 'input' / 'tablas' / 'output'), 'tablas'),
           (str(repo / 'upstream.json'), '.')]
          + ([(str(repo / 'UPSTREAM.lock.json'), '.')] if (repo / 'UPSTREAM.lock.json').is_file() else [])
          + xgboost_data,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'streamlit', 'matplotlib', 'IPython', 'notebook', 'pytest',
        'torch', 'torchvision', 'torchaudio', 'transformers', 'datasets',
        'spacy', 'cv2', 'numba', 'nltk', 'tensorflow', 'onnxruntime',
    ],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='LiquidadorCatastral',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='LiquidadorCatastral',
)
