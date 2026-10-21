import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from publicar_resultados import publicar  # noqa: E402


class PublicarResultadosTests(unittest.TestCase):
    def _archivo(self, root: Path, rel: str, viejo=False):
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
        if viejo:
            os.utime(p, (time.time() - 3600, time.time() - 3600))
        return p

    def test_cada_accion_en_su_carpeta_con_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            viejo = self._archivo(root, "output/archivo_de_otra_corrida.parquet", viejo=True)
            inicio = time.time() - 1
            self._archivo(root, "output/Calidad_insumos/CALIDAD_INSUMOS_X.xlsx")
            self._archivo(root, "output/LIQUIDACION_TABLAS.parquet")
            self._archivo(root, "results/REVISION_LIQUIDACION_20261005.xlsx")
            self._archivo(root, "results/DETALLE_VIGENCIAS.xlsx")
            manifiesto = self._archivo(root, "manifests/manifest_2027.json")
            df = pd.DataFrame({"ID_PREDIO": ["1", "2"], "AVALUO_2026_CAT": [1000.5, 2000.0],
                               "ZHF": [82104421013.0, None]})

            movidos = publicar(inicio, "liquidacion", ["txt", "parquet", "xlsx"], df, raiz=str(root),
                               manifiesto=str(manifiesto))

            ver = Path(movidos["05_RESULTADO_PREDIOS"][0]).parent.name
            self.assertTrue(ver.endswith("_LIQUIDACION"))
            for accion, nombre in [("01_CALIDAD_INSUMOS", "CALIDAD_INSUMOS_X.xlsx"),
                                   ("03_LIQUIDACION_CONSTRUCCIONES", "LIQUIDACION_TABLAS.parquet"),
                                   ("05_RESULTADO_PREDIOS", "REVISION_LIQUIDACION_20261005.xlsx"),
                                   ("05_RESULTADO_PREDIOS", "PREDIOS_LIQUIDACION.txt"),
                                   ("05_RESULTADO_PREDIOS", "PREDIOS_LIQUIDACION.parquet"),
                                   ("06_ESCENARIOS", "DETALLE_VIGENCIAS.xlsx"),
                                   ("00_MANIFIESTOS", "manifest_2027.json")]:
                self.assertTrue((root / accion / ver / nombre).is_file(), f"{accion}/{nombre}")
            # lo de otra corrida no se toca, y el manifiesto original se conserva
            self.assertTrue(viejo.is_file())
            self.assertTrue(manifiesto.is_file())
            # txt con el formato de Sistemas: '|' y coma decimal
            txt = (root / "05_RESULTADO_PREDIOS" / ver / "PREDIOS_LIQUIDACION.txt").read_text(encoding="latin-1")
            self.assertIn("ID_PREDIO|AVALUO_2026_CAT|ZHF", txt)
            self.assertIn("1000,5", txt)
            self.assertIn("|82104421013\n", txt.replace("\r\n", "\n"))   # codigo sin ',0'

    def test_preliquidacion_no_genera_txt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inicio = time.time() - 1
            df = pd.DataFrame({"ID_PREDIO": ["1"]})
            movidos = publicar(inicio, "preliquidacion", ["parquet", "xlsx"], df, raiz=str(root))
            nombres = [Path(p).name for p in movidos["05_RESULTADO_PREDIOS"]]
            self.assertIn("PREDIOS_PRELIQUIDACION.parquet", nombres)
            self.assertNotIn("PREDIOS_PRELIQUIDACION.txt", nombres)


if __name__ == "__main__":
    unittest.main()
