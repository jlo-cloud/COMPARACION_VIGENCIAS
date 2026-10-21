import contextlib
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import comunas as C  # noqa: E402
import prevalidacion_comunas as pv  # noqa: E402
import validacion_preliquidacion as vp  # noqa: E402
from liquidar_avaluo_2026 import calcular_avaluo_2026  # noqa: E402


class ComunasTests(unittest.TestCase):
    def test_normalizar_y_grupos(self):
        self.assertEqual(C.normalizar(["1", 3, "03", "22"]), ["01", "03", "22"])
        self.assertEqual(len(C.normalizar(["rural"])), 15)
        self.assertEqual(C.grupo_tablas("02"), "7C")
        self.assertEqual(C.grupo_tablas("14"), "10C")
        self.assertEqual(C.grupo_tablas("05"), "10C")      # decision: faltantes en el grupo 10
        self.assertIsNone(C.grupo_tablas("51"))
        self.assertEqual(len(C.COMUNAS_REGLAS), 17)


class AvaluoTests(unittest.TestCase):
    def test_integral_no_lleva_terreno_y_los_componentes_suman(self):
        d = pd.DataFrame({
            "VTER_2026_COM": [100.0, 100.0, 100.0], "VCONST_2026_COM": [0.0, 50.0, 50.0],
            "VANEXO_2026_COM": [0.0, 10.0, 10.0], "MIXTO": [0, 0, 0], "INTEGRAL": [0, 1, 0],
            "INFORMALIDAD": [0, 0, 0], "TERRENO_MAS_CONST": [0, 0, 1],
            "ARECPRED": [0, 30, 30], "ACONANEXT": [0, 5, 5], "AREAPRED": [200, 200, 200],
            "ESPECIAL_2026": [0, 0, 0], "INTEGRAL_ESP_2026": [0, 0, 0]})
        with contextlib.redirect_stdout(io.StringIO()):     # el motor imprime emojis
            r = calcular_avaluo_2026(d)
        self.assertEqual(r.AVALUO_COM_2026.tolist(), [100.0, 60.0, 160.0])
        self.assertEqual(r.TERRENO_INCLUIDO.tolist(), [1, 0, 1])
        self.assertEqual(r.CONST_INCLUIDA.tolist(), [0, 1, 1])
        suma = r.VTER_2026_COM * r.TERRENO_INCLUIDO + r.VCONST_2026_COM * r.CONST_INCLUIDA \
            + r.VANEXO_2026_COM * r.ANEXO_INCLUIDO
        self.assertTrue(np.allclose(suma, r.AVALUO_COM_2026))


class ValidacionPredioTests(unittest.TestCase):
    def test_criterios(self):
        d = pd.DataFrame({
            "ID_PREDIO": ["ok", "cero", "parcial", "sin_ter", "sin_grupo", "obs"],
            "AVALUO_2026_CAT": [1e6, 0, 5e5, 3e5, 2e5, 9e5],
            "TOTAL_CONST": [2, 1, 3, 1, 1, 1], "CONST_CON_VALOR": [2, 0, 1, 1, 1, 1],
            "VTER_2026_COM": [1, 0, 1, 0, 1, 1], "TERRENO_INCLUIDO": [1, 1, 1, 1, 1, 1],
            "AREAPRED": [100] * 6, "ARECPRED": [50] * 6, "VTER": [1] * 6,
            "INTEGRAL": [0, 0, 0, 0, 0, 1], "INFORMALIDAD": [0] * 6, "MIXTO": [0] * 6, "TERRENO_MAS_CONST": [1] * 6,
            "VAR_AVALUO": [2.0, -100.0, -40.0, 5.0, 1.0, 80.0],
            "GRUPO_COMUNAS": ["7C", "7C", "7C", "10C", "SIN GRUPO", "7C"]})
        r, det = vp.evaluar(d)
        r = r.set_index("ID_PREDIO")
        self.assertEqual(r.loc["ok", "ESTADO_PRELIQUIDACION"], "CUMPLE")
        self.assertIn("Avaluo en $0", r.loc["cero", "QUE_NO_CUMPLE"])
        self.assertIn("Ninguna construccion con valor", r.loc["cero", "QUE_NO_CUMPLE"])
        self.assertIn("Construcciones en $0 (2 de 3)", r.loc["parcial", "QUE_NO_CUMPLE"])
        self.assertIn("Sin valor de terreno", r.loc["sin_ter", "QUE_NO_CUMPLE"])
        self.assertIn("Comuna sin grupo", r.loc["sin_grupo", "QUE_NO_CUMPLE"])
        self.assertEqual(r.loc["obs", "ESTADO_PRELIQUIDACION"], "CUMPLE CON OBSERVACIONES")
        self.assertIn("Integral y el export trae terreno", r.loc["obs", "OBSERVACIONES_REVISAR"])
        self.assertTrue(set(det.ID_PREDIO) >= {"cero", "parcial", "sin_ter", "sin_grupo", "obs"})


class PrevalidacionTests(unittest.TestCase):
    def _insumos(self, t: Path):
        npn = lambda com, cond: f"76001010{0}{com}0000000000{cond}00000000".replace(" ", "")[:30]
        # NPN: [9:11] comuna, [21] condicion
        def npn(com, cond):
            base = list("760010100000000000000000000000")
            base[9:11] = list(com)
            base[21] = str(cond)
            return "".join(base)
        pd.DataFrame({
            "ID_PREDIO": ["1", "2", "3", "4"],
            "NUMERO_PREDIAL_NACIONAL": [npn("02", 0), npn("02", 9), npn("51", 0), npn("14", 0)],
            "ZHF": ["83114461013", "83114461013", "0", "81024441015"], "ESTRPRED": ["3", "4", "0", "2"],
            "AREAPRED": ["100", "0", "500", "80"], "ARECPRED": ["60", "50", "0", "40"],
            "LATITUDE": ["3.45", "", "3.4", "3.4"], "LONGITUDE": ["-76.53", "", "-76.5", "-76.5"],
        }).to_parquet(t / "predio.parquet")
        pd.DataFrame({
            "ID_PREDIO": ["1", "1", "2", "4"], "DESTINOCONS": ["12", "8", "1", "32"],
            "ACONCONS": ["60", "12", "50", "40"], "PUNTCONS": ["40", "0", "50", "30"],
        }).to_parquet(t / "conv.parquet")
        pd.DataFrame({"ID_PREDIO": ["1"], "DESTANEX": ["101"], "TIPOANEXO": ["80"], "ACONANEX": ["10"]}
                     ).to_parquet(t / "noconv.parquet")
        pd.DataFrame({"ID_PREDIO": ["1", "4"], "AMETTERR": ["100", "80"], "VALOTERR": ["5000000", "3000000"]}
                     ).to_parquet(t / "terreno.parquet")
        cols = {"PUNTAJE": list(range(1, 101))}
        for c in ("T1_RESIDENCIAL_7C_013", "T1_RESIDENCIAL_10C_COND_0_015", "T5_INSTITUCIONAL_ED_17C_000"):
            cols[c] = [1000] * 100
        with pd.ExcelWriter(t / "tablas.xlsx") as w:
            pd.DataFrame(cols).to_excel(w, sheet_name="CONVENCIONALES", index=False)
            pd.DataFrame(columns=["CLAVE", "NO_CONVENCIONAL_10C", "NO_CONVENCIONAL_7C"]).to_excel(
                w, sheet_name="NO_CONVENCIONALES", index=False)
        return {"export_predio_actual": str(t / "predio.parquet"),
                "export_construccion_actual_conv": str(t / "conv.parquet"),
                "export_construccion_actual_noconv": str(t / "noconv.parquet"),
                "export_terreno_actual": str(t / "terreno.parquet")}

    def setUp(self):
        # La prueba no depende de que los .pkl esten en el equipo (la rama
        # publica no los trae): se simula que estan.
        self._faltantes = pv.modelos_faltantes
        pv.modelos_faltantes = lambda familia: []

    def tearDown(self):
        pv.modelos_faltantes = self._faltantes

    def test_comunas_y_predios_que_no_cumplen(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            r = pv.prevalidar(self._insumos(t), ["02", "14", "51"], str(t / "tablas.xlsx"),
                              carpeta=str(t / "out"), run_id="TEST")
            c = r.comunas.set_index("COMUNA")
            self.assertEqual(c.loc["51", "ESTADO"], "NO APTA")
            self.assertIn("sin regla de tablas", c.loc["51", "QUE_NO_CUMPLE"])
            self.assertEqual(c.loc["02", "ESTADO"], "NO APTA")
            self.assertIn("Parqueaderos T12", c.loc["02", "QUE_NO_CUMPLE"])
            self.assertIn("Anexos T10 (7C)", c.loc["02", "QUE_NO_CUMPLE"])
            self.assertIn("sin coordenadas", c.loc["02", "QUE_NO_CUMPLE"])      # PH por modelo sin coordenadas
            self.assertIn("T7_INSTITUCIONAL_SER", c.loc["14", "QUE_NO_CUMPLE"])
            self.assertIn("sin modelo", c.loc["14", "QUE_NO_CUMPLE"].lower()) if "MODELO" in c.loc["14", "QUE_NO_CUMPLE"] \
                else None
            p = r.predios.set_index("ID_PREDIO")
            self.assertEqual(p.loc["1", "ESTADO"], "NO CUMPLE")
            self.assertIn("Parqueaderos", p.loc["1", "QUE_NO_CUMPLE"])
            self.assertTrue(os.path.isfile(r.ruta))
            self.assertTrue((t / "out" / "detalle_prevalidacion.parquet").is_file())
            m = r.tablas.set_index(["TABLA", "GRUPO"]).DISPONIBLE
            self.assertEqual(m[("T1_RESIDENCIAL", "7C")], "SI")
            self.assertEqual(m[("T7_INSTITUCIONAL_SER", "17C")], "NO")

    def test_parqueaderos_avalados_no_bloquean(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            r = pv.prevalidar(self._insumos(t), ["02"], str(t / "tablas.xlsx"), liquidar_parqueaderos=True,
                              carpeta=str(t / "out"), run_id="TEST")
            self.assertNotIn("Parqueaderos", r.comunas.QUE_NO_CUMPLE.iloc[0])


if __name__ == "__main__":
    unittest.main()
