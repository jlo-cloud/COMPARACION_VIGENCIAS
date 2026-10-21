import json
import sys
import tempfile
import unittest
from pathlib import Path


SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from manifest_contract import (  # noqa: E402
    INPUT_SPECS,
    build_manifest,
    discover_inputs,
    save_manifest,
    validate_manifest,
)


class ManifestContractTests(unittest.TestCase):
    def _complete_inputs(self, root: Path):
        result = {}
        for spec in INPUT_SPECS:
            if not spec.required:
                continue
            path = root / f"{spec.key}{spec.extensions[0]}"
            path.write_bytes(b"fixture " + spec.key.encode())
            result[spec.key] = str(path)
        return result

    def test_complete_2027_manifest_is_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = build_manifest(2027, str(root / "work"), self._complete_inputs(root))
            self.assertEqual(validate_manifest(data), [])

    def test_same_file_as_current_and_previous_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self._complete_inputs(root)
            inputs["export_predio_anterior"] = inputs["export_predio_actual"]
            errors = validate_manifest(build_manifest(2027, str(root / "work"), inputs))
            self.assertTrue(any("mismo archivo" in error for error in errors))

    def test_comunas_are_normalized_and_validated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = build_manifest(2027, str(root / "work"), self._complete_inputs(root), comunas=["1", "22", 3])
            self.assertEqual(data["parametros"]["comunas_liquidar"], ["01", "03", "22"])
            self.assertEqual(validate_manifest(data), [])
            data["parametros"]["comunas_liquidar"] = ["01", "40"]
            self.assertTrue(any("no validas" in e for e in validate_manifest(data)))

    def test_2026_is_explicitly_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = build_manifest(2026, str(root / "work"), self._complete_inputs(root))
            errors = validate_manifest(data)
            self.assertTrue(any("no esta habilitada" in error for error in errors))

    def test_missing_required_file_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            inputs = self._complete_inputs(root)
            Path(inputs["export_predio_actual"]).unlink()
            data = build_manifest(2027, str(root / "work"), inputs)
            errors = validate_manifest(data)
            self.assertTrue(any("Predios de la vigencia" in error for error in errors))

    def test_manifest_save_is_atomic_and_readable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = build_manifest(2027, str(root / "work"), self._complete_inputs(root))
            target = save_manifest(data, root / "manifests" / "run.json")
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["vigencia_objetivo"], 2027)
            self.assertFalse(target.with_suffix(".json.tmp").exists())

    def test_discovery_does_not_guess_between_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "a_export_predio_zhf.parquet").write_bytes(b"a")
            (root / "b_export_predio_zhf.parquet").write_bytes(b"b")
            self.assertNotIn("export_predio_actual", discover_inputs(root))

    def _parquet(self, path: Path, columns):
        import pyarrow as pa
        import pyarrow.parquet as pq

        pq.write_table(pa.table({c: ["1"] for c in columns}), path)

    def test_discovery_by_content_prefers_newest_dated_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            predio = ["ID_PREDIO", "AVALPRED", "ZHF", "VALOR_M2_SUELO", "LATITUDE"]
            self._parquet(root / "20260728_export_predio_zhf_2026.parquet", predio)
            self._parquet(root / "20260804_export_predio_zhf_2026.parquet", predio)
            # mismo contenido de construcciones pero sin VALOR_M2/INTEGRAL: no es la actual
            self._parquet(root / "export_construccion_homologado_20260717.parquet",
                          ["ID_CONSTRUCCION", "PUNTCONS", "VALORCONS"])
            self._parquet(root / "cualquier_nombre.parquet",
                          ["ID_CONSTRUCCION", "PUNTCONS", "VALOR_M2", "INTEGRAL"])
            (root / "export_predio.txt").write_text(
                '"ID_PREDIO"|"AVALPRED"|"ZHF"|"VALOR_M2_SUELO"\n1|2|3|4\n', encoding="latin-1")
            found = discover_inputs(root)
            self.assertTrue(found["export_predio_actual"].endswith("20260804_export_predio_zhf_2026.parquet"))
            self.assertTrue(found["export_construccion_actual_conv"].endswith("cualquier_nombre.parquet"))
            self.assertTrue(found["export_predio_2024"].endswith("export_predio.txt"))

    def test_previous_vigencia_snapshot_is_the_oldest(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._parquet(root / "predio_20251209_150206.parquet", ["ID_PREDIO", "AVALPRED"])
            self._parquet(root / "predio_20260715_100736.parquet", ["ID_PREDIO", "AVALPRED"])
            self._parquet(root / "PREDIO_20260307.parquet", ["ID_PREDIO", "AVALPRED", "AVALUO_COM_2026"])
            found = discover_inputs(root)
            self.assertTrue(found["predio_vigencia_anterior"].endswith("predio_20251209_150206.parquet"))
            self.assertTrue(found["preliquidacion_referencia"].endswith("PREDIO_20260307.parquet"))


if __name__ == "__main__":
    unittest.main()
