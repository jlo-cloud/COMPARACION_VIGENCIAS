import json
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import reliquidacion as rq  # noqa: E402


def _motor_falso(d):
    """Tabla fija: 1.000.000 por m2, salvo el parqueadero (por cupo) y lo que iba por modelo."""
    d = d.copy()
    d["TABLA_ORIGEN"] = "T1_RESIDENCIAL_015"
    d["VM2"] = 1_000_000.0
    parq = d.DESTINOCONS.astype(str).str.zfill(3).eq("008")
    d.loc[parq, "TABLA_ORIGEN"] = "T12_PARQUEADEROS"
    d.loc[parq, "VM2"] = 0.0
    d["LIQ_PARQUEADERO"] = 0.0
    d.loc[parq, "LIQ_PARQUEADERO"] = 48_000_000.0
    return d


class ReliquidacionTests(unittest.TestCase):
    def test_llaves_iguales_aunque_cambie_el_formato_del_numero(self):
        a = rq.llave_construccion(pd.Series(["10"]), pd.Series(["42,0"]), pd.Series(["24.0"]))
        b = rq.llave_construccion(pd.Series(["10"]), pd.Series(["42"]), pd.Series(["24"]))
        self.assertEqual(a.iloc[0], b.iloc[0])

    def test_modelo_2025_solo_ph_condicion_9(self):
        b = pd.DataFrame({"DESTINOCONS": ["1", "001", "028", "012"], "CONDICION": ["9", "0", "9", "9"],
                          "USO_LADM": [""] * 4})
        self.assertEqual(rq.iba_por_modelo(b, "2025").tolist(), [True, False, True, False])

    def test_configuracion_rutas_relativas_y_validacion(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "c.json"
            ruta.write_text(json.dumps({"nombre": "X", "predios": "p.xlsx", "base_construcciones": "b.parquet",
                                        "reglas": "2030"}), encoding="utf-8")
            cfg = rq.Configuracion.desde_json(ruta)
            self.assertEqual(Path(cfg.predios), (Path(tmp) / "p.xlsx").resolve())
            errores = " ".join(cfg.validar())
            self.assertIn("reglas", errores)
            self.assertIn("terreno es obligatorio", errores)
            self.assertIn("no existe", errores)

    def test_reliquidacion_completa(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            pd.DataFrame({"RADICACION": ["R1", "R2", "R3"], "ID_PREDIO": ["1", "2", "3"]}).to_excel(t / "p.xlsx",
                                                                                                    index=False)
            pd.DataFrame({
                "ID_PREDIO": ["1", "1", "2"], "LLAVE_CONST": ["C1", "C2", "C3"],
                "ZHF": ["83114461022", "83114461022", "83114461015"], "COMUNA": ["02"] * 3,
                "DESTINOCONS": ["12", "8", "1"], "CONDICION": ["0", "0", "9"], "USO_LADM": ["", "", ""],
                "ESPECIAL": ["0", "0", "0"], "DESTANEX": ["0", "0", "0"], "TIPOANEXO": ["0", "0", "0"],
                "ACONANEX": ["0", "0", "0"], "AREA_CONST": ["100", "12", "50"], "ACONCONS": ["100", "12", "50"],
                "PUNTCONS": ["40", "20", "60"],
            }).to_parquet(t / "b.parquet")
            pd.DataFrame({"ID_PREDIO": ["1", "2", "3"], "AVALPRED": [100e6, 50e6, 30e6], "VTER": [20e6, 0, 30e6],
                          "VCONST": [80e6, 50e6, 0], "VANEXO": [0, 0, 0], "AREAPRED": [200, 0, 300]}
                         ).to_parquet(t / "ref.parquet")
            pd.DataFrame({"ID_PREDIO": ["1", "2"], "ZHF": ["83114451012", "83114461015"]}).to_parquet(t / "z.parquet")
            # Construccion de referencia: la C1 cambio de area (95 -> 100); la C2 esta igual.
            pd.DataFrame({"ID_PREDIO": ["1", "1"], "ACONCONS": ["95", "12"], "PUNTCONS": ["40", "20"],
                          "VALORCONS": ["60000000", "20000000"]}).to_csv(t / "c.txt", sep="|", index=False)
            (t / "cfg.json").write_text(json.dumps({
                "nombre": "PRUEBA", "predios": "p.xlsx", "base_construcciones": "b.parquet", "reglas": "2025",
                "comuna_reglas": "01", "excluir_modelo": True, "etiqueta_referencia": "REF", "etiqueta_nueva": "NUEVA",
                "terreno": {"archivo": "ref.parquet"}, "zhf": {"archivo": "z.parquet"},
                "export_construcciones": "c.txt", "salida": "out"}), encoding="utf-8")

            original = rq.MOTORES["2025"]
            rq.MOTORES["2025"] = _motor_falso
            try:
                archivo = rq.reliquidar(rq.Configuracion.desde_json(t / "cfg.json"))
            finally:
                rq.MOTORES["2025"] = original

            p = pd.read_excel(archivo, "PREDIOS", dtype={"ID_PREDIO": str}).set_index("ID_PREDIO")
            c = pd.read_excel(archivo, "CONSTRUCCIONES", dtype={"LLAVE_CONST": str}).set_index("LLAVE_CONST")
            excl = pd.read_excel(archivo, "EXCLUIDOS_MODELO", dtype={"ID_PREDIO": str})

            # El 2 va por modelo (uso 001, condicion 9): fuera. El 3 es lote: solo terreno.
            self.assertEqual(sorted(p.index), ["1", "3"])
            self.assertEqual(excl.ID_PREDIO.tolist(), ["2"])
            # Predio 1: terreno 20M + 100 m2 x 1M x 0,7 + parqueadero 48M x 0,7 (por cupo, sin area).
            self.assertAlmostEqual(c.loc["C2", "VALOR_NUEVA"], 48e6 * 0.7)
            self.assertAlmostEqual(p.loc["1", "AVALUO_NUEVA"], 20e6 + 70e6 + 33.6e6)
            self.assertEqual(p.loc["3", "AVALUO_NUEVA"], 30e6)
            self.assertEqual(p.loc["3", "GRUPO"], "LOTE (solo terreno)")
            # Mutacion de la C1 y cambio de tipologia de ZHF (012 usada, 022 en la base).
            self.assertIn("MUTACION", c.loc["C1", "NOVEDAD"])
            self.assertIn("ZHF", c.loc["C1", "NOVEDAD"])
            self.assertTrue(str(p.loc["1", "OBSERVACION_MUTACION"]).startswith("MUTACION"))
            self.assertEqual(p.loc["1", "TIENE_NOVEDAD"], "SI")
            r = pd.read_excel(archivo, "RESUMEN_RANGOS")
            self.assertEqual(int(r.loc[r.RANGO_VARIACION.eq("TOTAL"), "PREDIOS"].iloc[0]), 2)


if __name__ == "__main__":
    unittest.main()
