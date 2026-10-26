# -*- mode: python ; coding: utf-8 -*-
# El .exe de la preliquidacion: src/preliquidar_app.py + el mismo codigo de src/.
# Los datos (input/, Modelos/, output/) NO van dentro: se leen de la carpeta
# del proyecto que se elige en la ventana.
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

repo = Path(SPEC).resolve().parent.parent
src = repo / 'src'
_sin_tests = lambda n: '.tests' not in n and not n.endswith('.conftest')

# Los modulos de src/ que se importan dentro de funciones, y las clases que
# solo nombran los .pkl de los modelos.
propios = [p.stem for p in src.glob('*.py') if p.stem not in ('app_vigencias', 'preliquidar_app')]
hidden = propios + [
    'sklearn._loss.link', 'sklearn._loss.loss', 'sklearn.dummy', 'sklearn.ensemble._forest',
    'sklearn.ensemble._gb', 'sklearn.pipeline', 'sklearn.preprocessing._data',
    'sklearn.tree._classes', 'sklearn.tree._tree', 'xgboost.core', 'xgboost.sklearn',
    'matplotlib.backends.backend_agg',
] + collect_submodules('statsmodels', filter=_sin_tests) + collect_submodules('patsy', filter=_sin_tests)

a = Analysis(
    [str(src / 'preliquidar_app.py')],
    pathex=[str(src)],
    binaries=collect_dynamic_libs('xgboost'),
    datas=collect_data_files('xgboost', include_py_files=False),
    hiddenimports=hidden,
    excludes=['streamlit', 'IPython', 'notebook', 'pytest', 'torch', 'tensorflow', 'cv2', 'numba'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='Liquidador',
          console=False, upx=False, strip=False)
coll = COLLECT(exe, a.binaries, a.datas, upx=False, strip=False, name='Liquidador')
