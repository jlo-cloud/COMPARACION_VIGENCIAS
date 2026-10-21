import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

import sincronizar_upstream as su  # noqa: E402


def git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def repo(path: Path):
    path.mkdir(parents=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.email", "prueba@example.com")
    git(path, "config", "user.name", "Prueba")


class SincronizarTests(unittest.TestCase):
    def test_trae_solo_lo_declarado_y_registra_la_procedencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            t = Path(tmp)
            fuente, nuestro = t / "fuente", t / "nuestro"
            repo(fuente)
            (fuente / "input/tablas/output").mkdir(parents=True)
            (fuente / "input/tablas/output/Tablas_Valor_Consolidado_V2_20261020.xlsx").write_bytes(b"tablas v2")
            (fuente / "Modelos/models").mkdir(parents=True)
            (fuente / "Modelos/models/nuevo.pkl").write_bytes(b"modelo")
            (fuente / "src").mkdir()
            (fuente / "src/regla.py").write_text("x = 1\n")
            git(fuente, "add", "-A")
            git(fuente, "commit", "-q", "-m", "primera entrega")

            repo(nuestro)
            (nuestro / "upstream.json").write_text(json.dumps({
                "remoto": "upstream", "url": str(fuente), "rama": "main", "version_tablas": "V2",
                "importar": {"tablas": ["input/tablas/output/Tablas_Valor_Consolidado_*.xlsx"],
                             "modelos": ["Modelos/models/*.pkl"]},
                "codigo_a_vigilar": ["src/"]}), encoding="utf-8")

            with contextlib.redirect_stdout(io.StringIO()):
                r = su.sincronizar(aplicar=False, raiz=nuestro, validar=False)
            self.assertEqual({c["estado"] for c in r["cambios"]}, {"nuevo"})
            self.assertFalse((nuestro / "Modelos/models/nuevo.pkl").exists())       # revisar no toca nada

            with contextlib.redirect_stdout(io.StringIO()):
                r = su.sincronizar(aplicar=True, raiz=nuestro, validar=False)
            self.assertEqual((nuestro / "Modelos/models/nuevo.pkl").read_bytes(), b"modelo")
            self.assertFalse((nuestro / "src/regla.py").exists())                  # el codigo no se trae
            lock = json.loads((nuestro / "UPSTREAM.lock.json").read_text(encoding="utf-8"))
            self.assertEqual(len(lock["archivos"]), 2)
            self.assertEqual(lock["commit"], r["commit"])

            # nueva entrega en la fuente: cambia la tabla y una regla del codigo
            (fuente / "input/tablas/output/Tablas_Valor_Consolidado_V2_20261020.xlsx").write_bytes(b"tablas v2b")
            (fuente / "src/regla.py").write_text("x = 2\n")
            git(fuente, "commit", "-qam", "segunda entrega")
            with contextlib.redirect_stdout(io.StringIO()):
                r = su.sincronizar(aplicar=True, raiz=nuestro, validar=False)
            estados = {c["ruta"]: c["estado"] for c in r["cambios"]}
            self.assertEqual(estados["input/tablas/output/Tablas_Valor_Consolidado_V2_20261020.xlsx"], "actualizado")
            self.assertEqual(estados["Modelos/models/nuevo.pkl"], "igual")
            self.assertTrue(any("src/regla.py" in x for x in r["codigo_cambiado"]))

            push = subprocess.run(["git", "remote", "get-url", "--push", "upstream"], cwd=nuestro,
                                  capture_output=True, text=True).stdout
            self.assertIn("NO_PUSH", push)


if __name__ == "__main__":
    unittest.main()
