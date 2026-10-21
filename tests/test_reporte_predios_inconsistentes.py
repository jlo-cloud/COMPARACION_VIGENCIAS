import os
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from reporte_predios_inconsistentes import generar  # noqa: E402


class ReportePrediosInconsistentesTests(unittest.TestCase):
    def test_una_fila_por_predio_con_inconsistencia_y_dato_faltante(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "output"
            (out / "Pre_inconsistencias").mkdir(parents=True)
            (out / "post_inconsistencias").mkdir(parents=True)
            pd.DataFrame({
                "ID_PREDIO": ["1", "1"], "LLAVE_CONST": ["C1-1", "C1-2"],
                "MOTIVO": ["Sin puntaje condicionado", "Sin LATITUDE"], "CAMPO": ["PUNTCONS", "LATITUDE"],
                "VALOR_ACTUAL": ["0", "nan"], "DESCUENTA_PREDIO": [True, True],
            }).to_parquet(out / "Pre_inconsistencias" / "detalle_pre_inconsistencias.parquet")
            pd.DataFrame({
                "ID_PREDIO": ["2", "3", "4"], "LLAVE_CONST": ["C2-1", "C3-1", "C4-1"],
                "TABLA_ORIGEN": ["T7_INSTITUCIONAL_SER", "MODELO", "MODELO"],
                "CAUSA": ["FALTA REGLA - la tabla no esta en el consolidado", "MODELO - sin valor del modelo",
                          "MODELO - sin valor del modelo"],
                "CATEGORIA": ["FALTA REGLA", "MODELO", "MODELO"], "GRUPO_MODELO": ["", "2025", "None"],
                "DESTINOCONS": ["32", "1", "001"],
                "VALOR_M2_SUELO": ["", "500000", "1"], "ANOCONST": ["", "2000", "1"], "ESTRPRED": ["", "4", "1"],
                "PUNTCONS": ["", "60", "1"], "TPISCONS": ["", "10", "1"], "LATITUDE": ["", "nan", "3.4"],
                "LONGITUDE": ["", "", "-76.5"], "ZHF_MODELO": ["", "83104441042", "1"], "ACONCONS": ["", "80", "1"],
                "NUM_CONST_TERR": ["", "1", "1"],
            }).to_parquet(out / "post_inconsistencias" / "detalle_post_inconsistencias.parquet")

            archivo = generar(str(out))
            p = pd.read_excel(archivo, sheet_name="PREDIOS", dtype={"ID_PREDIO": str}).set_index("ID_PREDIO")

            self.assertEqual(len(p), 4)
            self.assertIn("Sin familia de modelo", p.loc["4", "QUE_NO_CUMPLE"])   # GRUPO_MODELO 'None'
            self.assertTrue(p.loc["1", "ESTADO_LIQUIDACION"].startswith("NO SE LIQUIDA"))
            self.assertIn("Sin puntaje", p.loc["1", "QUE_NO_CUMPLE"])
            self.assertIn("PUNTCONS", p.loc["1", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertIn("LATITUDE", p.loc["1", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertIn("Tabla T7_INSTITUCIONAL_SER", p.loc["2", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertTrue(p.loc["2", "ESTADO_LIQUIDACION"].startswith("LIQUIDADO PARCIAL"))
            self.assertIn("faltan variables", p.loc["3", "QUE_NO_CUMPLE"])
            self.assertIn("LATITUDE", p.loc["3", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertIn("LONGITUDE", p.loc["3", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertNotIn("ANOCONST", p.loc["3", "DATOS_FALTANTES_PARA_LIQUIDAR"])
            self.assertTrue(os.path.basename(archivo).startswith("PREDIOS_POR_CORREGIR_"))


if __name__ == "__main__":
    unittest.main()
