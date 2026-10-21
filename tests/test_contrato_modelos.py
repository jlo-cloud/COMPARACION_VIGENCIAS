import contextlib
import io
import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import contrato_modelos as cm  # noqa: E402


class ModeloFalso:
    feature_names_in_ = np.array(["VALOR_M2_SUELO", "ANOCONST", "LATITUDE", "COMUNA_22"])


def verificar(X, modelo=None):
    cm.REGISTRO.clear()
    with contextlib.redirect_stdout(io.StringIO()):
        out = cm.verificar("PRUEBA", X, modelo)
    return out, pd.DataFrame(cm.REGISTRO)


class ContratoTests(unittest.TestCase):
    def test_numero_en_texto_se_convierte_sin_cambiar_el_valor(self):
        X = pd.DataFrame({"VALOR_M2_SUELO": ["1500000", "2000000,5"], "ANOCONST": ["1990", "2005"],
                          "LATITUDE": [3.4, 3.45], "COMUNA_22": [0, 1]})
        out, h = verificar(X, ModeloFalso())
        self.assertTrue(pd.api.types.is_numeric_dtype(out.VALOR_M2_SUELO))
        self.assertEqual(out.VALOR_M2_SUELO.tolist(), [1500000.0, 2000000.5])
        self.assertEqual(set(h.NIVEL), {"AJUSTE"})

    def test_texto_que_no_es_numero_es_error(self):
        X = pd.DataFrame({"ANOCONST": ["1990", "SIN DATO"]})
        _, h = verificar(X)
        self.assertIn("ERROR", h.NIVEL.tolist())
        self.assertIn("no son numeros", h.MENSAJE.iloc[0])

    def test_variable_perdida_queda_fuera_de_rango(self):
        # Lo que deja get_dummies cuando el año llega como texto: la columna en 0.
        _, h = verificar(pd.DataFrame({"ANOCONST": [0, 0, 0], "LATITUDE": [3.4, 3.41, 3.42]}))
        fila = h[h.VARIABLE.eq("ANOCONST")].iloc[0]
        self.assertEqual(fila.NIVEL, "ERROR")
        self.assertIn("se perdio", fila.MENSAJE)

    def test_indicadora_solo_0_y_1(self):
        _, h = verificar(pd.DataFrame({"TRAT_URB_04": [0, 1, 4]}))
        self.assertEqual(h.NIVEL.tolist(), ["ERROR"])

    def test_falta_una_variable_del_modelo(self):
        X = pd.DataFrame({"VALOR_M2_SUELO": [1e6], "ANOCONST": [2000], "LATITUDE": [3.4]})
        _, h = verificar(X, ModeloFalso())
        self.assertTrue(((h.VARIABLE == "COMUNA_22") & (h.NIVEL == "ERROR")).any())

    def test_matriz_correcta_no_deja_hallazgos(self):
        X = pd.DataFrame({"VALOR_M2_SUELO": [1e6], "ANOCONST": [2000], "LATITUDE": [3.4], "COMUNA_22": [1]})
        _, h = verificar(X, ModeloFalso())
        self.assertTrue(h.empty)


if __name__ == "__main__":
    unittest.main()
