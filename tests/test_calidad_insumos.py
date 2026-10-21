import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import config  # noqa: E402
from calidad_insumos import evaluar_calidad  # noqa: E402

URB = "76001010001000100010000000{:04d}"   # zona 01, condicion 0
RUR = "76001000001000100010000000{:04d}"   # zona 00, condicion 0


def _predios(n_urb, n_rur, direccion_rural, extra=None):
    ids = [str(i) for i in range(1, n_urb + n_rur + 1)]
    npn = [URB.format(i) for i in range(1, n_urb + 1)] + [RUR.format(i) for i in range(n_urb + 1, n_urb + n_rur + 1)]
    df = pd.DataFrame({
        "ID_PREDIO": ids, "NUMERO_PREDIAL_NACIONAL": npn,
        "DIREPRED": ["CL 1 # 2 - 3"] * n_urb + [direccion_rural] * n_rur,
        "AVALPRED": "1000", "AREAPRED": "100", "ZHF": "8310444104", "ESTRPRED": "3", "TIPOPRED": "A",
        "MATCPRED": "370-1", "LATITUDE": 3.40, "LONGITUDE": -76.52,
    })
    if extra is not None:
        df = pd.concat([df, extra], ignore_index=True)
    return df


class CalidadInsumosTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.cwd)
        self.tmp.cleanup()

    def _correr(self, actual: pd.DataFrame, anterior: pd.DataFrame):
        actual.to_parquet(self.root / "actual.parquet", index=False)
        anterior.drop(columns=["LATITUDE", "LONGITUDE"]).to_csv(self.root / "anterior.txt", sep="|", index=False)
        config.MANIFEST_PATH = str(self.root / "m.json")
        config.MANIFEST_DATA = {"run_id": "TEST", "insumos": {
            "export_predio_actual": "actual.parquet", "export_predio_2024": "anterior.txt"}}
        return evaluar_calidad("TEST", carpeta=str(self.root / "out"))

    @staticmethod
    def _regla(rep, ambito, nombre):
        return next(r for r in rep.reglas if r["AMBITO"] == ambito and r["REGLA"] == nombre)

    def test_caida_de_direccion_rural_es_advertencia_con_recuperables(self):
        rep = self._correr(_predios(50, 50, "NA # - "), _predios(50, 50, "VDA PANCE"))
        r = self._regla(rep, "RURAL", "Direccion")
        self.assertEqual(r["NIVEL"], "ADVERTENCIA")
        self.assertEqual(r["PCT_VALIDO"], 0.0)
        self.assertEqual(r["PCT_VALIDO_VIGENCIA_ANTERIOR"], 100.0)
        self.assertEqual(r["RECUPERABLES_DESDE_ANTERIOR"], 50)
        self.assertEqual(self._regla(rep, "URBANO", "Direccion")["NIVEL"], "OK")
        self.assertEqual(rep.errores, 0)
        self.assertTrue(Path(rep.ruta).is_file())

    def test_id_predio_duplicado_es_error(self):
        base = _predios(10, 0, "")
        rep = self._correr(_predios(10, 0, "", extra=base.head(1)), base)
        self.assertEqual(self._regla(rep, "TODO", "ID_PREDIO unico")["NIVEL"], "ERROR")
        self.assertGreater(rep.errores, 0)

    def test_columna_obligatoria_faltante_es_error(self):
        base = _predios(10, 0, "")
        rep = self._correr(base.drop(columns=["ZHF"]), base)
        self.assertEqual(self._regla(rep, "TODO", "Columnas obligatorias")["NIVEL"], "ERROR")


if __name__ == "__main__":
    unittest.main()
