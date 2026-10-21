"""Trae las tablas de valor y los modelos desde el repositorio fuente (upstream).

El repositorio fuente (upstream.json -> url, rama) es donde el equipo publica
las tablas de valor, que cambian con cada entrega, y los modelos. Este
repositorio es un consumidor: NUNCA escribe en la fuente y NO trae su codigo.
Solo copia las rutas declaradas en upstream.json -> "importar".

    python src/sincronizar_upstream.py            muestra que cambiaria (no toca nada)
    python src/sincronizar_upstream.py --aplicar  copia los archivos y actualiza UPSTREAM.lock.json

Despues de aplicar:
  1. revisar el informe (output/upstream/SINCRONIZACION_<fecha>.md);
  2. hacer commit de los archivos y del UPSTREAM.lock.json en la rama;
  3. reconstruir el ejecutable (build_exe.ps1): lleva por dentro las tablas y
     los modelos sincronizados.

Validaciones de lo que llega:
  - tablas: que el consolidado tenga las hojas que lee el motor, y que tablas
    trae con valores (las que falten saldran en la prevalidacion);
  - modelos: que carguen y que cada variable que esperan este en el contrato
    de variables (contrato_modelos.py). Una variable nueva significa que el
    codigo de este repositorio no la construye: hay que adaptar model_liq.py.
  - codigo: que archivos de src/ cambiaron en la fuente desde la ultima
    sincronizacion. No se traen; se listan para revisar si cambia una regla.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
CONFIG = RAIZ / "upstream.json"
LOCK = RAIZ / "UPSTREAM.lock.json"


def git(*args, cwd=RAIZ, binario=False):
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=False)
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)}: {r.stderr.decode('utf-8', 'replace').strip()}")
    return r.stdout if binario else r.stdout.decode("utf-8", "replace")


def leer_config(ruta: Path = CONFIG) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def asegurar_remoto(cfg: dict, raiz: Path = RAIZ) -> None:
    """El remoto de la fuente, con el envio deshabilitado: aqui no se publica nada hacia alla."""
    remotos = git("remote", cwd=raiz).split()
    if cfg["remoto"] not in remotos:
        git("remote", "add", cfg["remoto"], cfg["url"], cwd=raiz)
    else:
        git("remote", "set-url", cfg["remoto"], cfg["url"], cwd=raiz)
    git("remote", "set-url", "--push", cfg["remoto"], "NO_PUSH_la_fuente_es_solo_lectura", cwd=raiz)


def archivos_fuente(cfg: dict, ref: str, raiz: Path = RAIZ) -> list[tuple[str, str, str]]:
    """(categoria, ruta, blob) de cada archivo de la fuente que cumple los patrones de importar."""
    todos = git("ls-tree", "-r", "--format=%(objectname) %(path)", ref, cwd=raiz).splitlines()
    salida = []
    for linea in todos:
        blob, ruta = linea.split(" ", 1)
        for categoria, patrones in cfg["importar"].items():
            if any(fnmatch.fnmatch(ruta, p) for p in patrones):
                salida.append((categoria, ruta, blob))
                break
    return salida


def blob_local(ruta: Path) -> str | None:
    if not ruta.is_file():
        return None
    datos = ruta.read_bytes()
    return hashlib.sha1(b"blob %d\0" % len(datos) + datos).hexdigest()


def sincronizar(aplicar: bool = False, raiz: Path = RAIZ, config: Path | None = None,
                validar: bool = True) -> dict:
    cfg = leer_config(config or raiz / "upstream.json")
    asegurar_remoto(cfg, raiz)
    git("fetch", "--quiet", cfg["remoto"], cfg["rama"], cwd=raiz)
    ref = f"{cfg['remoto']}/{cfg['rama']}"
    commit = git("rev-parse", ref, cwd=raiz).strip()
    fecha = git("log", "-1", "--format=%cI", ref, cwd=raiz).strip()
    lock_path = raiz / "UPSTREAM.lock.json"
    anterior = json.loads(lock_path.read_text(encoding="utf-8")) if lock_path.is_file() else {}

    cambios = []
    for categoria, ruta, blob in archivos_fuente(cfg, ref, raiz):
        local = raiz / ruta
        actual = blob_local(local)
        estado = "igual" if actual == blob else ("nuevo" if actual is None else "actualizado")
        cambios.append({"categoria": categoria, "ruta": ruta, "blob": blob, "estado": estado})
        if aplicar and estado != "igual":
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_bytes(git("cat-file", "blob", blob, cwd=raiz, binario=True))

    codigo = []
    previo = anterior.get("commit")
    if previo and previo != commit:
        try:
            codigo = git("diff", "--name-status", previo, ref, "--", *cfg.get("codigo_a_vigilar", []),
                         cwd=raiz).splitlines()
        except RuntimeError:
            codigo = ["(no se pudo comparar con el commit anterior)"]

    resultado = {"remoto": cfg["remoto"], "url": cfg["url"], "rama": cfg["rama"], "commit": commit,
                 "fecha_commit": fecha, "sincronizado": datetime.now().isoformat(timespec="seconds"),
                 "version_tablas": cfg.get("version_tablas"),
                 "archivos": [{k: c[k] for k in ("categoria", "ruta", "blob")} for c in cambios],
                 "commit_anterior": previo}
    validaciones = _validar(raiz, cambios) if (validar and aplicar) else []
    informe = _informe(resultado, cambios, codigo, validaciones, aplicar, raiz)
    if aplicar:
        lock_path.write_text(json.dumps(resultado, indent=2, ensure_ascii=False), encoding="utf-8")
    resultado.update({"cambios": cambios, "codigo_cambiado": codigo, "validaciones": validaciones,
                      "informe": informe})
    return resultado


def _validar(raiz: Path, cambios: list[dict]) -> list[str]:
    """Que lo que llego lo pueda usar el motor."""
    sys.path.insert(0, str(raiz / "src"))
    notas = []
    for c in cambios:
        ruta = raiz / c["ruta"]
        if c["estado"] == "igual" or not ruta.is_file():
            continue
        if c["categoria"] == "tablas" and "Tablas_Valor_Consolidado" in ruta.name:
            try:
                import pandas as pd
                from prevalidacion_comunas import tablas_disponibles
                hojas = pd.ExcelFile(ruta).sheet_names
                faltan = [h for h in ("CONVENCIONALES", "NO_CONVENCIONALES") if h not in hojas]
                conv, anexos = tablas_disponibles(str(ruta))
                familias = sorted({t.split("_")[0] for t in conv})
                notas.append(f"TABLAS {ruta.name}: hojas {'OK' if not faltan else 'FALTAN ' + ', '.join(faltan)}; "
                             f"familias con valores {', '.join(familias) or 'ninguna'}; "
                             f"anexos {', '.join(sorted(anexos)) or 'sin valores'}")
            except Exception as e:                                   # pragma: no cover
                notas.append(f"TABLAS {ruta.name}: no se pudo leer ({e})")
        elif c["categoria"] == "modelos" and ruta.suffix == ".pkl":
            try:
                import contrato_modelos
                import model_liq
                modelo = model_liq._cargar(str(ruta))
                variables = contrato_modelos._esperadas(modelo) or []
                sin_contrato = [v for v in variables if contrato_modelos.tipo_esperado(v)[0] == "sin contrato"]
                notas.append(f"MODELO {ruta.name}: carga OK; {len(variables)} variables"
                             + (f"; SIN CONTRATO (el codigo no las construye): {', '.join(sin_contrato)}"
                                if sin_contrato else "; todas con contrato"))
            except Exception as e:
                notas.append(f"MODELO {ruta.name}: NO CARGA ({e})")
    return notas


def _informe(r, cambios, codigo, validaciones, aplicar, raiz) -> str:
    lineas = [f"# Sincronizacion con la fuente ({'APLICADA' if aplicar else 'solo revision'})", "",
              f"- Fuente: {r['url']} rama {r['rama']}", f"- Commit: {r['commit']} ({r['fecha_commit']})",
              f"- Commit de la sincronizacion anterior: {r['commit_anterior'] or '(ninguna)'}",
              f"- Version de tablas configurada: {r['version_tablas']}", ""]
    if not cambios:
        lineas += ["**La fuente no trae ningun archivo de tablas ni de modelos** en las rutas de upstream.json. "
                   "Mientras no se publiquen ahi, siguen llegando por la carpeta de insumos.", ""]
    else:
        lineas += ["| Categoria | Archivo | Estado |", "|---|---|---|"]
        lineas += [f"| {c['categoria']} | {c['ruta']} | {c['estado']} |" for c in cambios]
        lineas.append("")
    if validaciones:
        lineas += ["## Validacion de lo que llego", ""] + [f"- {v}" for v in validaciones] + [""]
    if codigo:
        lineas += ["## Codigo que cambio en la fuente (NO se trae; revisar si cambia una regla)", ""]
        lineas += [f"- {x}" for x in codigo] + [""]
    texto = "\n".join(lineas)
    carpeta = raiz / "output" / "upstream"
    carpeta.mkdir(parents=True, exist_ok=True)
    (carpeta / f"SINCRONIZACION_{datetime.now():%Y%m%d_%H%M}.md").write_text(texto, encoding="utf-8")
    return texto


def procedencia(ruta_tablas: str | None = None) -> dict:
    """Para el manifiesto de la corrida: de que commit de la fuente salieron las tablas y los modelos."""
    lock = {}
    for base in (RAIZ, Path(getattr(sys, "_MEIPASS", RAIZ))):
        if (base / "UPSTREAM.lock.json").is_file():
            lock = json.loads((base / "UPSTREAM.lock.json").read_text(encoding="utf-8"))
            break
    salida = {"fuente": lock.get("url"), "commit_fuente": lock.get("commit"),
              "sincronizado": lock.get("sincronizado"), "version_tablas": os.environ.get("VERSION_TABLAS")}
    if ruta_tablas and os.path.isfile(ruta_tablas):
        sha = blob_local(Path(ruta_tablas))
        salida["tablas"] = os.path.basename(ruta_tablas)
        salida["tablas_blob"] = sha
        salida["tablas_de_la_fuente"] = any(a.get("blob") == sha for a in lock.get("archivos", []))
    return salida


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--aplicar", action="store_true", help="copia los archivos y actualiza UPSTREAM.lock.json")
    a = p.parse_args(argv)
    try:
        r = sincronizar(aplicar=a.aplicar)
    except RuntimeError as e:
        print(f"[ERROR] {e}")
        return 2
    print(r["informe"])
    pendientes = [c for c in r["cambios"] if c["estado"] != "igual"]
    if not a.aplicar and pendientes:
        print(f"{len(pendientes)} archivo(s) por traer. Para traerlos: python src/sincronizar_upstream.py --aplicar")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
