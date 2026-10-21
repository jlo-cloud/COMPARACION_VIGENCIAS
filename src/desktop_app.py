"""Interfaz de escritorio y punto de entrada del ejecutable."""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import traceback
from pathlib import Path

from manifest_contract import (
    INPUT_SPECS,
    YEAR_PROFILES,
    build_manifest,
    discover_inputs_detailed,
    save_manifest,
    validate_manifest,
)


APP_NAME = "Liquidador Catastral 2027"


def _run_manifest(manifest_path: str) -> int:
    """Ejecuta el motor en un proceso dedicado y devuelve un codigo real."""
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(data, path)
    if errors:
        print("[ERROR] Manifiesto invalido:")
        for error in errors:
            print(f" - {error}")
        return 2

    workspace = Path(data["workspace"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    os.environ["LIQUIDACION_WORKSPACE"] = str(workspace)
    os.chdir(workspace)

    # En un bundle PyInstaller, los modulos ya estan en sys.path. En desarrollo
    # se garantiza que src siga disponible aun despues del cambio de cwd.
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))

    try:
        import main as engine

        mode = "--todas" if data.get("parametros", {}).get("generar_escenarios", True) else "--solo-actual"
        engine.main(["--manifest", str(path), mode])
        return 0
    except KeyboardInterrupt:
        print("[WARN] Ejecucion cancelada por el usuario.")
        return 130
    except Exception:
        print("[ERROR] La liquidacion termino con error.")
        traceback.print_exc()
        return 1


def _quality_manifest(manifest_path: str) -> int:
    """Solo el control de calidad de los insumos (paso 0A), sin liquidar."""
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(data, path)
    if errors:
        print("[ERROR] Manifiesto invalido:")
        for error in errors:
            print(f" - {error}")
        return 2
    workspace = Path(data["workspace"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    os.environ["LIQUIDACION_WORKSPACE"] = str(workspace)
    os.chdir(workspace)
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        import config
        from calidad_insumos import evaluar_calidad

        import time

        inicio = time.time()
        config.load_manifest(str(path))
        print("=== CALIDAD DE LOS INSUMOS ===")
        rep = evaluar_calidad(data.get("run_id"))
        if config.get_param("publicar_por_carpetas", True):
            from publicar_resultados import publicar

            publicar(inicio, "calidad", [], None, manifiesto=str(path))
        return 3 if rep.errores else 0
    except Exception:
        print("[ERROR] El control de calidad termino con error.")
        traceback.print_exc()
        return 1


def _prevalidar_manifest(manifest_path: str) -> int:
    """Solo la prevalidacion de las comunas seleccionadas (paso 0B), sin liquidar."""
    path = Path(manifest_path).resolve()
    data = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_manifest(data, path)
    if errors:
        print("[ERROR] Manifiesto invalido:")
        for error in errors:
            print(f" - {error}")
        return 2
    workspace = Path(data["workspace"]).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    os.environ["LIQUIDACION_WORKSPACE"] = str(workspace)
    os.chdir(workspace)
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        import time

        import config
        from prevalidacion_comunas import ejecutar_desde_config

        inicio = time.time()
        config.load_manifest(str(path))
        print("=== PREVALIDACION DE LAS COMUNAS SELECCIONADAS ===")
        r = ejecutar_desde_config()
        if config.get_param("publicar_por_carpetas", True):
            from publicar_resultados import publicar

            publicar(inicio, "prevalidacion", [], None, manifiesto=str(path))
        return 3 if r.no_aptas else 0
    except Exception:
        print("[ERROR] La prevalidacion termino con error.")
        traceback.print_exc()
        return 1


def _validate_cli(manifest_path: str) -> int:
    path = Path(manifest_path).resolve()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[ERROR] No se pudo leer el manifiesto: {exc}")
        return 2
    errors = validate_manifest(data, path)
    if errors:
        print("[ERROR] Preflight rechazado:")
        for error in errors:
            print(f" - {error}")
        return 2
    print("[OK] Preflight aprobado. Todos los insumos obligatorios existen y tienen formato valido.")
    return 0


def _reliquidar_cli(config_path: str) -> int:
    """Reliquidacion de un listado de predios con otras condiciones (ver docs/RELIQUIDACION.md)."""
    src_dir = Path(__file__).resolve().parent
    if str(src_dir) not in sys.path:
        sys.path.insert(0, str(src_dir))
    try:
        import reliquidacion

        return reliquidacion.main([config_path])
    except Exception:
        print("[ERROR] La reliquidacion termino con error.")
        traceback.print_exc()
        return 1


def _self_test() -> int:
    """Comprueba imports nativos y deserializa todos los modelos incluidos."""
    try:
        import pandas  # noqa: F401
        import pyarrow  # noqa: F401
        import sklearn  # noqa: F401
        import xgboost  # noqa: F401
        import model_liq

        if getattr(sys, "frozen", False):
            root = Path(sys._MEIPASS) / "Modelos"  # type: ignore[attr-defined]
        else:
            root = Path(__file__).resolve().parents[1] / "Modelos"
        models = sorted(root.rglob("*.pkl"))
        if not models:
            raise RuntimeError(f"No se encontraron modelos en {root}")
        for path in models:
            model_liq._cargar(str(path))
        print(f"[OK] Self-test: {len(models)} modelos cargados.")
        return 0
    except Exception:
        traceback.print_exc()
        return 1


class DesktopApp:
    def __init__(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.ttk = ttk
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1180x840")
        self.root.minsize(900, 620)
        self.process: subprocess.Popen[str] | None = None
        self.messages: queue.Queue[str | None] = queue.Queue()

        self.year = tk.StringVar(value="2027")
        default_workspace = Path.home() / "Documents" / "LiquidacionCatastral" / "2027"
        self.workspace = tk.StringVar(value=str(default_workspace))
        self.source_folder = tk.StringVar()
        self.include_scenarios = tk.BooleanVar(value=True)
        self.tipo_corrida = tk.StringVar(value="Preliquidacion")
        self.formatos = {f: tk.BooleanVar(value=f in ("parquet", "xlsx")) for f in ("txt", "parquet", "xlsx")}
        from comunas import COMUNAS_REGLAS, COMUNAS_URBANAS
        self.comunas = {c: tk.BooleanVar(value=c in COMUNAS_REGLAS) for c in COMUNAS_URBANAS}
        self.rurales = tk.BooleanVar(value=False)
        self.liquidar_parqueaderos = tk.BooleanVar(value=False)
        self.version_tablas = tk.StringVar(value=self._version_por_defecto())
        self.inputs = {spec.key: tk.StringVar() for spec in INPUT_SPECS}
        self.status = tk.StringVar(value="Seleccione los insumos y ejecute la validacion previa.")

        self._build_ui()

    def _build_ui(self) -> None:
        tk, ttk = self.tk, self.ttk
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(2, weight=1)

        header = ttk.Frame(root, padding=(18, 14))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 18, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(header, text="Carga los archivos, valida el contrato y genera la liquidacion sin usar Python.").grid(row=1, column=0, columnspan=3, sticky="w", pady=(3, 12))
        ttk.Label(header, text="Vigencia").grid(row=2, column=0, sticky="w")
        years = ttk.Combobox(header, textvariable=self.year, state="readonly", width=12, values=[str(y) for y in sorted(YEAR_PROFILES, reverse=True)])
        years.grid(row=2, column=1, sticky="w", padx=(8, 18))
        years.bind("<<ComboboxSelected>>", self._year_changed)
        ttk.Checkbutton(header, text="Generar escenarios 2024/2025", variable=self.include_scenarios).grid(row=2, column=2, sticky="e")
        # Tipo de corrida y formatos: la preliquidacion sale en parquet + Excel;
        # la liquidacion agrega el .txt con el formato de los export de Sistemas.
        salida = ttk.Frame(header)
        salida.grid(row=3, column=0, columnspan=3, sticky="w", pady=(8, 0))
        ttk.Label(salida, text="Tipo de corrida").pack(side="left")
        tipos = ttk.Combobox(salida, textvariable=self.tipo_corrida, state="readonly", width=16,
                             values=["Preliquidacion", "Liquidacion"])
        tipos.pack(side="left", padx=(8, 18))
        tipos.bind("<<ComboboxSelected>>", self._tipo_changed)
        ttk.Label(salida, text="Formatos del resultado:").pack(side="left")
        for f, etiqueta in (("txt", "TXT (Sistemas)"), ("parquet", "Parquet"), ("xlsx", "Excel")):
            ttk.Checkbutton(salida, text=etiqueta, variable=self.formatos[f]).pack(side="left", padx=(8, 0))
        ttk.Label(salida, text="   Cada accion queda en su carpeta, con una version por corrida.",
                  foreground="#555").pack(side="left", padx=(12, 0))

        # Que comunas se liquidan: la prevalidacion revisa SOLO estas, y la
        # liquidacion no ve las demas.
        sel = ttk.LabelFrame(header, text="Comunas a liquidar", padding=(8, 4))
        sel.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        for i, c in enumerate(sorted(self.comunas)):
            ttk.Checkbutton(sel, text=c, variable=self.comunas[c]).grid(row=i // 11, column=i % 11, sticky="w", padx=2)
        ttk.Checkbutton(sel, text="Rurales (51-65)", variable=self.rurales).grid(row=0, column=11, sticky="w", padx=(12, 0))
        atajos = ttk.Frame(sel)
        atajos.grid(row=1, column=11, sticky="w", padx=(12, 0))
        ttk.Button(atajos, text="17 de Reglas.xlsx", command=lambda: self._marcar_comunas("reglas")).pack(side="left")
        ttk.Button(atajos, text="Todas", command=lambda: self._marcar_comunas("todas")).pack(side="left", padx=4)
        ttk.Button(atajos, text="Ninguna", command=lambda: self._marcar_comunas("ninguna")).pack(side="left")
        ttk.Checkbutton(sel, text="Liquidar parqueaderos T12 (valores 2025 sin aval)",
                        variable=self.liquidar_parqueaderos).grid(row=2, column=0, columnspan=7, sticky="w", pady=(4, 0))
        ttk.Label(sel, text="Version de tablas").grid(row=2, column=7, columnspan=2, sticky="e", pady=(4, 0))
        ttk.Combobox(sel, textvariable=self.version_tablas, width=6,
                     values=self._versiones_disponibles()).grid(row=2, column=9, columnspan=2, sticky="w", pady=(4, 0))

        locations = ttk.LabelFrame(root, text="Carpetas", padding=10)
        locations.grid(row=1, column=0, sticky="ew", padx=18, pady=(0, 10))
        locations.columnconfigure(1, weight=1)
        ttk.Label(locations, text="Carpeta de resultados").grid(row=0, column=0, sticky="w")
        ttk.Entry(locations, textvariable=self.workspace).grid(row=0, column=1, sticky="ew", padx=8)
        ttk.Button(locations, text="Examinar...", command=self._choose_workspace).grid(row=0, column=2)
        ttk.Label(locations, text="Carpeta con insumos").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(locations, textvariable=self.source_folder).grid(row=1, column=1, sticky="ew", padx=8, pady=(8, 0))
        ttk.Button(locations, text="Detectar archivos", command=self._discover).grid(row=1, column=2, pady=(8, 0))

        notebook = ttk.Notebook(root)
        notebook.grid(row=2, column=0, sticky="nsew", padx=18)
        inputs_tab = ttk.Frame(notebook)
        logs_tab = ttk.Frame(notebook)
        notebook.add(inputs_tab, text="1. Insumos")
        notebook.add(logs_tab, text="2. Ejecucion y logs")
        reliq_tab = ttk.Frame(notebook, padding=10)
        notebook.add(reliq_tab, text="3. Reliquidar predios")
        self.notebook = notebook
        self.logs_tab = logs_tab
        self._build_reliquidacion(reliq_tab)
        inputs_tab.rowconfigure(0, weight=1)
        inputs_tab.columnconfigure(0, weight=1)
        logs_tab.rowconfigure(0, weight=1)
        logs_tab.columnconfigure(0, weight=1)

        canvas = tk.Canvas(inputs_tab, highlightthickness=0)
        scrollbar = ttk.Scrollbar(inputs_tab, orient="vertical", command=canvas.yview)
        rows = ttk.Frame(canvas, padding=10)
        rows.columnconfigure(1, weight=1)
        canvas.create_window((0, 0), window=rows, anchor="nw", tags=("rows",))
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")
        rows.bind("<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure("rows", width=e.width))

        for index, spec in enumerate(INPUT_SPECS):
            required = "*" if spec.required else ""
            ttk.Label(rows, text=f"{spec.label}{required}").grid(row=index, column=0, sticky="w", padx=(0, 8), pady=4)
            ttk.Entry(rows, textvariable=self.inputs[spec.key]).grid(row=index, column=1, sticky="ew", pady=4)
            ttk.Button(rows, text="Archivo...", command=lambda s=spec: self._choose_file(s)).grid(row=index, column=2, padx=(8, 0), pady=4)

        self.log = tk.Text(logs_tab, wrap="none", font=("Consolas", 9), state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        log_scroll = ttk.Scrollbar(logs_tab, orient="vertical", command=self.log.yview)
        log_scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=log_scroll.set)

        footer = ttk.Frame(root, padding=(18, 12))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        ttk.Label(footer, textvariable=self.status).grid(row=0, column=0, sticky="w")
        ttk.Button(footer, text="Validar insumos", command=self._validate).grid(row=0, column=1, padx=5)
        self.quality_button = ttk.Button(footer, text="Revisar calidad", command=lambda: self._start("--quality"))
        self.quality_button.grid(row=0, column=2, padx=5)
        self.prev_button = ttk.Button(footer, text="Prevalidar comunas", command=lambda: self._start("--prevalidar"))
        self.prev_button.grid(row=0, column=3, padx=5)
        self.run_button = ttk.Button(footer, text="Generar liquidacion", command=self._start)
        self.run_button.grid(row=0, column=4, padx=5)
        self.cancel_button = ttk.Button(footer, text="Cancelar", command=self._cancel, state="disabled")
        self.cancel_button.grid(row=0, column=5, padx=5)
        ttk.Button(footer, text="Abrir resultados", command=self._open_results).grid(row=0, column=6, padx=(5, 0))

    # Campos de la pestana 3: (clave, etiqueta, tipo). tipo: archivo, carpeta, texto, opcion.
    CAMPOS_RELIQ = [
        ("nombre", "Nombre del ejercicio", "texto"),
        ("predios", "Listado de predios (con ID_PREDIO)*", "archivo"),
        ("base_construcciones", "Base de construcciones (todas_las_construcciones.parquet)*", "archivo"),
        ("reglas", "Reglas y tablas del ejercicio", "opcion"),
        ("comuna_reglas", "Comuna cuyos valores se aplican (vacio = la del predio)", "texto"),
        ("comuna_referencia", "Comuna para comparar (opcional)", "texto"),
        ("terreno", "Foto de predios de referencia: avaluo y terreno que se conserva*", "archivo"),
        ("zhf", "Export con la ZHF a usar (vacio = la de la base)", "archivo"),
        ("actual", "Export de predios actual (opcional)", "archivo"),
        ("export_construcciones", "Export de construcciones de referencia (mutaciones)", "archivo"),
        ("export_anexos", "Export de anexos de referencia (mutaciones)", "archivo"),
        ("zona_control", "Valores de zona para validar el terreno (opcional)", "archivo"),
        ("etiqueta_referencia", "Etiqueta de la referencia (ej. VIG2025)", "texto"),
        ("etiqueta_nueva", "Etiqueta de la nueva liquidacion (ej. TABLAS_VIG2026)", "texto"),
        ("salida", "Carpeta de salida*", "carpeta"),
    ]
    # Columnas que se leen de cada archivo fuente (las de los export de Sistemas).
    COLUMNAS_RELIQ = {
        "terreno": {"avaluo": "AVALPRED", "terreno": "VTER", "construccion": "VCONST", "anexos": "VANEXO",
                    "area_terreno": "AREAPRED"},
        "zhf": {"zhf": "ZHF"}, "actual": {"avaluo": "AVALPRED"}, "zona_control": {"zona": "ZHG_2024"},
    }

    def _build_reliquidacion(self, tab) -> None:
        tk, ttk = self.tk, self.ttk
        tab.columnconfigure(1, weight=1)
        ttk.Label(tab, text=("Vuelve a liquidar un listado de predios con las reglas de otro ejercicio, la ZHF de otro "
                             "export y el terreno de otra vigencia. Todo por tabla; ver docs/RELIQUIDACION.md."),
                  wraplength=900).grid(row=0, column=0, columnspan=3, sticky="w", pady=(0, 8))
        defectos = {"nombre": "RELIQUIDACION", "reglas": "2025", "etiqueta_referencia": "REFERENCIA",
                    "etiqueta_nueva": "NUEVA", "salida": str(Path(self.workspace.get()) / "reliquidacion")}
        self.reliq = {k: tk.StringVar(value=defectos.get(k, "")) for k, _, _ in self.CAMPOS_RELIQ}
        self.reliq_excluir_modelo = tk.BooleanVar(value=True)
        for i, (k, etiqueta, tipo) in enumerate(self.CAMPOS_RELIQ, start=1):
            ttk.Label(tab, text=etiqueta).grid(row=i, column=0, sticky="w", pady=2)
            if tipo == "opcion":
                ttk.Combobox(tab, textvariable=self.reliq[k], state="readonly", width=10,
                             values=["2025", "2024"]).grid(row=i, column=1, sticky="w", padx=8)
                continue
            ttk.Entry(tab, textvariable=self.reliq[k]).grid(row=i, column=1, sticky="ew", padx=8, pady=2)
            if tipo in ("archivo", "carpeta"):
                ttk.Button(tab, text="...", width=4,
                           command=lambda k=k, t=tipo: self._reliq_elegir(k, t)).grid(row=i, column=2)
        fila = len(self.CAMPOS_RELIQ) + 1
        ttk.Checkbutton(tab, text="Dejar fuera los predios que en ese ejercicio iban por modelo",
                        variable=self.reliq_excluir_modelo).grid(row=fila, column=0, columnspan=2, sticky="w", pady=6)
        botones = ttk.Frame(tab)
        botones.grid(row=fila + 1, column=0, columnspan=3, sticky="e")
        ttk.Button(botones, text="Cargar configuracion...", command=self._reliq_cargar).pack(side="left", padx=4)
        ttk.Button(botones, text="Guardar configuracion...", command=self._reliq_guardar).pack(side="left", padx=4)
        self.reliq_button = ttk.Button(botones, text="Reliquidar", command=self._reliq_ejecutar)
        self.reliq_button.pack(side="left", padx=4)

    def _reliq_elegir(self, clave: str, tipo: str) -> None:
        from tkinter import filedialog

        valor = (filedialog.askdirectory(title="Carpeta de salida") if tipo == "carpeta"
                 else filedialog.askopenfilename(title=clave))
        if valor:
            self.reliq[clave].set(valor)

    def _reliq_config(self) -> dict:
        v = {k: var.get().strip() for k, var in self.reliq.items()}
        cfg = {"nombre": v["nombre"] or "RELIQUIDACION", "reglas": v["reglas"],
               "excluir_modelo": bool(self.reliq_excluir_modelo.get())}
        for k in ("predios", "base_construcciones", "comuna_reglas", "comuna_referencia", "export_construcciones",
                  "export_anexos", "etiqueta_referencia", "etiqueta_nueva", "salida"):
            if v[k]:
                cfg[k] = v[k]
        for k, columnas in self.COLUMNAS_RELIQ.items():
            if v[k]:
                cfg[k] = {"archivo": v[k], "columnas": columnas}
        return cfg

    def _reliq_cargar(self) -> None:
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(title="Configuracion de reliquidacion", filetypes=[("JSON", "*.json")])
        if not ruta:
            return
        data = json.loads(Path(ruta).read_text(encoding="utf-8"))
        for k, var in self.reliq.items():
            valor = data.get(k, "")
            var.set(valor.get("archivo", "") if isinstance(valor, dict) else str(valor or ""))
        self.reliq_excluir_modelo.set(bool(data.get("excluir_modelo", False)))
        for k in self.COLUMNAS_RELIQ:
            if isinstance(data.get(k), dict) and data[k].get("columnas"):
                self.COLUMNAS_RELIQ[k] = data[k]["columnas"]

    def _reliq_guardar(self, ruta: Path | None = None) -> Path | None:
        from tkinter import filedialog

        if ruta is None:
            elegido = filedialog.asksaveasfilename(title="Guardar configuracion", defaultextension=".json",
                                                   filetypes=[("JSON", "*.json")])
            if not elegido:
                return None
            ruta = Path(elegido)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_text(json.dumps(self._reliq_config(), indent=2, ensure_ascii=False), encoding="utf-8")
        return ruta

    def _reliq_ejecutar(self) -> None:
        if self.process is not None:
            return
        cfg = self._reliq_config()
        carpeta = Path(cfg.get("salida") or Path(self.workspace.get()) / "reliquidacion")
        ruta = self._reliq_guardar(carpeta / f"reliquidacion_{cfg['nombre']}.json")
        self._append_log(f"[INFO] Configuracion de reliquidacion: {ruta}\n")
        self.notebook.select(self.logs_tab)
        self._lanzar(self._command(ruta, "--reliquidar"), "--reliquidar", "Reliquidacion en curso...")

    @staticmethod
    def _version_por_defecto() -> str:
        from consolidar_tablas import _version_por_defecto
        return _version_por_defecto()

    @staticmethod
    def _versiones_disponibles() -> list[str]:
        """Las versiones de tablas que trae el repositorio o el ejecutable (sincronizadas de la fuente)."""
        import re as _re
        from consolidar_tablas import carpetas_de_tablas
        versiones = {m.group(1) for c in carpetas_de_tablas() if c.is_dir()
                     for f in c.glob("Tablas_Valor_Consolidado_*.xlsx")
                     for m in [_re.match(r"Tablas_Valor_Consolidado_(V\d+)_", f.name)] if m}
        return sorted(versiones) or ["V1"]

    def _marcar_comunas(self, cuales: str) -> None:
        from comunas import COMUNAS_REGLAS

        for c, var in self.comunas.items():
            var.set(cuales == "todas" or (cuales == "reglas" and c in COMUNAS_REGLAS))
        self.rurales.set(cuales == "todas")

    def _comunas_elegidas(self) -> list[str]:
        elegidas = [c for c, var in self.comunas.items() if var.get()]
        return elegidas + (["rural"] if self.rurales.get() else [])

    def _year_changed(self, _event=None) -> None:
        year = int(self.year.get())
        profile = YEAR_PROFILES[year]
        self.workspace.set(str(Path.home() / "Documents" / "LiquidacionCatastral" / str(year)))
        self.status.set(profile["description"])

    def _choose_workspace(self) -> None:
        from tkinter import filedialog

        value = filedialog.askdirectory(title="Carpeta donde se guardaran resultados")
        if value:
            self.workspace.set(value)

    def _choose_file(self, spec) -> None:
        from tkinter import filedialog

        patterns = " ".join(f"*{ext}" for ext in spec.extensions)
        value = filedialog.askopenfilename(title=spec.label, filetypes=[("Archivos admitidos", patterns), ("Todos", "*.*")])
        if value:
            self.inputs[spec.key].set(value)

    def _discover(self) -> None:
        from tkinter import filedialog

        folder = self.source_folder.get() or filedialog.askdirectory(title="Carpeta que contiene los insumos")
        if not folder:
            return
        self.source_folder.set(folder)
        self.status.set("Revisando la estructura de los archivos...")
        self.root.update_idletasks()
        result = discover_inputs_detailed(folder)
        for key, value in result.found.items():
            self.inputs[key].set(value)
        self._append_log(f"[DETECCION] {folder}\n{result.report()}\n\n")
        faltan = [s.label for s in INPUT_SPECS if s.required and s.key not in result.found]
        self.status.set(f"Se detectaron {len(result.found)} de {len(INPUT_SPECS)} insumos."
                        + (f" Faltan {len(faltan)}: ver pestana 2." if faltan else ""))
        if faltan:
            from tkinter import messagebox

            messagebox.showwarning("Insumos sin detectar",
                                   "No se encontraron:\n- " + "\n- ".join(faltan)
                                   + "\n\nSeleccionelos con 'Archivo...' o agreguelos a la carpeta.")

    def _manifest(self) -> dict:
        return build_manifest(
            int(self.year.get()),
            self.workspace.get(),
            {key: var.get().strip() for key, var in self.inputs.items()},
            self.include_scenarios.get(),
            tipo_corrida=self.tipo_corrida.get().lower(),
            formatos=[f for f, var in self.formatos.items() if var.get()],
            comunas=self._comunas_elegidas_codigos(),
            liquidar_parqueaderos=self.liquidar_parqueaderos.get(),
            version_tablas=self.version_tablas.get(),
        )

    def _comunas_elegidas_codigos(self) -> list[str]:
        from comunas import normalizar

        return normalizar(self._comunas_elegidas())

    def _tipo_changed(self, _event=None) -> None:
        liquidacion = self.tipo_corrida.get().lower() == "liquidacion"
        self.formatos["txt"].set(liquidacion)
        self.formatos["parquet"].set(True)
        self.formatos["xlsx"].set(True)

    def _validate(self, show_dialog: bool = True) -> bool:
        from tkinter import messagebox

        data = self._manifest()
        errors = validate_manifest(data)
        if not self._comunas_elegidas():
            errors.append("Seleccione al menos una comuna para liquidar.")
        if errors:
            message = "\n".join(f"- {error}" for error in errors)
            self.status.set(f"Validacion rechazada: {len(errors)} problema(s).")
            if show_dialog:
                messagebox.showerror("Insumos incompletos", message)
            return False
        self.status.set("Validacion aprobada. La corrida puede comenzar.")
        if show_dialog:
            messagebox.showinfo("Validacion aprobada", "Todos los insumos obligatorios existen y tienen un formato valido.")
        return True

    def _command(self, manifest: Path, mode: str = "--run-manifest") -> list[str]:
        if getattr(sys, "frozen", False):
            return [sys.executable, mode, str(manifest)]
        return [sys.executable, str(Path(__file__).resolve()), mode, str(manifest)]

    def _start(self, mode: str = "--run-manifest") -> None:
        from tkinter import messagebox

        if self.process is not None or not self._validate(show_dialog=False):
            if self.process is None:
                messagebox.showerror("No se puede ejecutar", "Corrija los insumos indicados por la validacion.")
            return
        workspace = Path(self.workspace.get()).resolve()
        manifest = save_manifest(self._manifest(), workspace / "manifests" / f"manifest_{self.year.get()}.json")
        self._append_log(f"[INFO] Manifiesto: {manifest}\n")
        estado = {"--quality": "Revisando la calidad de los insumos...",
                  "--prevalidar": "Prevalidando las comunas seleccionadas..."}.get(mode, "Liquidacion en curso...")
        self._lanzar(self._command(manifest, mode), mode, estado)

    def _lanzar(self, comando: list[str], mode: str, estado: str) -> None:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        self.mode = mode
        self.process = subprocess.Popen(
            comando,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=flags,
        )
        for boton in (self.run_button, self.quality_button, self.prev_button, self.reliq_button):
            boton.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status.set(estado)
        threading.Thread(target=self._read_process, daemon=True).start()
        self.root.after(100, self._poll_messages)

    def _read_process(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        for line in self.process.stdout:
            self.messages.put(line)
        code = self.process.wait()
        self.messages.put(f"\n[FIN] Codigo de salida: {code}\n")
        self.messages.put(None)

    def _poll_messages(self) -> None:
        finished = False
        while True:
            try:
                item = self.messages.get_nowait()
            except queue.Empty:
                break
            if item is None:
                finished = True
            else:
                self._append_log(item)
        if finished:
            code = self.process.returncode if self.process else 1
            self.process = None
            for boton in (self.run_button, self.quality_button, self.prev_button, self.reliq_button):
                boton.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            if getattr(self, "mode", "") == "--reliquidar":
                self.status.set("Reliquidacion terminada: el Excel quedo en la carpeta de salida." if code == 0
                                else f"Reliquidacion fallida (codigo {code}). Revise los logs.")
            elif getattr(self, "mode", "") == "--prevalidar":
                self.status.set({0: "Prevalidacion: todas las comunas seleccionadas son aptas.",
                                 3: "Prevalidacion: hay comunas NO APTAS. Ver 01B_PREVALIDACION_COMUNAS (hoja COMUNAS)."}
                                .get(code, f"La prevalidacion fallo (codigo {code}). Revise los logs."))
            elif getattr(self, "mode", "") == "--quality":
                self.status.set({0: "Calidad revisada: sin errores. Ver output/Calidad_insumos.",
                                 3: "Calidad con ERRORES: corrija antes de liquidar. Ver output/Calidad_insumos."}
                                .get(code, f"El control de calidad fallo (codigo {code}). Revise los logs."))
            else:
                self.status.set("Liquidacion terminada correctamente." if code == 0
                                else f"Liquidacion fallida (codigo {code}). Revise los logs.")
        elif self.process is not None:
            self.root.after(100, self._poll_messages)

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _cancel(self) -> None:
        if self.process is not None:
            self.process.terminate()
            self.status.set("Cancelando la ejecucion...")

    def _open_results(self) -> None:
        from tkinter import messagebox

        workspace = Path(self.workspace.get()).resolve()
        workspace.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(workspace)  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror("No se pudo abrir", str(exc))

    def run(self) -> None:
        self.root.mainloop()


def _utf8_streams() -> None:
    # El motor imprime emojis; con la salida redirigida a la interfaz Windows
    # usa cp1252 y el primer print revienta. Linea a linea para ver el log vivo.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace", line_buffering=True)


def main(argv: list[str] | None = None) -> int:
    _utf8_streams()
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) == 2 and args[0] == "--run-manifest":
        return _run_manifest(args[1])
    if len(args) == 2 and args[0] == "--validate-manifest":
        return _validate_cli(args[1])
    if len(args) == 2 and args[0] == "--quality":
        return _quality_manifest(args[1])
    if len(args) == 2 and args[0] == "--prevalidar":
        return _prevalidar_manifest(args[1])
    if len(args) == 2 and args[0] == "--reliquidar":
        return _reliquidar_cli(args[1])
    if args == ["--self-test"]:
        return _self_test()
    if len(args) == 2 and args[0] == "--detect":
        result = discover_inputs_detailed(args[1])
        print(result.report())
        return 0 if not [s for s in INPUT_SPECS if s.required and s.key not in result.found] else 3
    if args:
        print("Uso: LiquidadorCatastral.exe [--run-manifest archivo.json | --validate-manifest archivo.json"
              " | --quality archivo.json | --prevalidar archivo.json | --reliquidar configuracion.json | --detect carpeta | --self-test]")
        return 2
    DesktopApp().run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
