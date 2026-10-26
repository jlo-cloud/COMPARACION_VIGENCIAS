"""
Ventana para correr la preliquidacion sin abrir una terminal.

Se marcan las vigencias que se liquidan -2025, 2026 y 2027- y todas salen de
la data ACTUAL, cada una con las reglas de su ejercicio; no se usa ningun
export historico. Lo que no se marca no se liquida. Si 2027 esta marcada corre
ademas el main.py de siempre (comparacion con la vigencia y datos de la app).
La salida por vigencias (liquidar_vigencias.py) es una fila por construccion
con las columnas de cada una terminadas en _VIG_<vigencia>.

La ventana elige la carpeta del proyecto (la que tiene input/, Modelos/ y
output/), que archivo es cada insumo, que comunas se liquidan, la version de
las tablas 2027, si se corren los modelos (2025 y 2026; 2027 no tiene) y con
que carpeta de modelos; valida antes de empezar y muestra el log.

Tipo de corrida:
  Preliquidacion  parquet + resumen en Excel; los avisos de la validacion
                  (por ejemplo, comunas que una vigencia no valora) dejan seguir.
  Liquidacion     solo la vigencia 2027. Ademas del .txt por construccion, el
                  avaluo de cada predio (AVALUO_PREDIOS_VIG_2027.txt, formato
                  Sistemas) y su APROBACION contra el export de liquidacion de
                  Sistemas: aprobado si |avaluo - AVALPRED| < $1.000
                  (avaluo_liquidacion.py). La validacion es estricta: cualquier
                  aviso detiene.

Cada corrida queda en corridas/<AAAA-MM-DD_HHMM>_<version>/ con:
  manifiesto.json   que se uso (insumos con tamano y fecha, comunas, opciones)
  preliquidacion.log
  salidas/          copia de lo que la corrida escribio en output/ y results/
Las corridas anteriores no se borran.

Con todas las comunas, la corrida actualiza output/versiones/<version>/ -lo
que lee la app-, igual que python src/main.py. Con solo algunas comunas esas
salidas van a la carpeta de la corrida, para no dejar la app con datos a
medias.

Cada corrida es un proceso aparte (el mismo ejecutable con --correr): la
version de las tablas se lee al importar consolidar_tablas, y al terminar se
libera la memoria.

Uso:  python src/preliquidar_app.py
      Liquidador.exe
      Liquidador.exe --correr <carpeta de la corrida>
"""
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

CONGELADO = getattr(sys, "frozen", False)
if not CONGELADO:
    sys.path.insert(0, str(Path(__file__).resolve().parent))

import insumos  # noqa: E402


def raiz_por_defecto() -> Path:
    """La primera carpeta, subiendo desde el programa, que tenga input/."""
    inicio = Path(sys.executable if CONGELADO else __file__).resolve().parent
    for carpeta in [inicio, *inicio.parents]:
        if (carpeta / "input").is_dir():
            return carpeta
    return inicio


def versiones(raiz: Path) -> list:
    carpeta = raiz / "input" / "tablas" / "input"
    if not carpeta.is_dir():
        return []
    return sorted(p.name for p in carpeta.iterdir() if p.is_dir())


def describir(ruta: str) -> dict:
    p = Path(ruta)
    st = p.stat()
    return {"ruta": str(p.resolve()), "bytes": st.st_size,
            "modificado": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")}


def commit(raiz: Path) -> str:
    try:
        r = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                           capture_output=True, text=True, timeout=10,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip() or "?"
    except Exception:
        return "?"


# ---------------------------------------------------------------------------
# La corrida (proceso hijo)
# ---------------------------------------------------------------------------
def correr(carpeta: Path) -> int:
    man_path = carpeta / "manifiesto.json"
    man = json.loads(man_path.read_text(encoding="utf-8"))
    raiz = Path(man["raiz"])
    version = man["version_tablas"]
    vigs = [int(v) for v in man["vigencias"]]
    os.environ["VERSION_TABLAS"] = version
    os.environ["PRELIQ_RAIZ"] = str(raiz)
    os.environ["PRELIQ_MANIFIESTO"] = str(man_path)
    if 2027 not in vigs or not man["actualizar_app"]:
        os.environ["PRELIQ_CARPETA_VERSION"] = str(carpeta / "salidas" / "versiones" / version)
        os.environ["PRELIQ_BASE_CONSTRUCCIONES"] = str(carpeta / "salidas" / "todas_las_construcciones.parquet")
        (carpeta / "salidas").mkdir(parents=True, exist_ok=True)
    os.chdir(raiz)
    # Sin consola (el .exe es de ventana) no hay stdout: todo va al log.
    salida = open(carpeta / "preliquidacion.log", "a", encoding="utf-8", buffering=1)
    sys.stdout = sys.stderr = salida
    inicio = time.time()
    estado = "ERROR"
    try:
        import liquidar_vigencias
        if 2027 in vigs:
            # La preliquidacion de siempre: arma la base y compara con la vigencia.
            import main as preliquidacion
            preliquidacion.main(liquidar_otras=False)
        else:
            liquidar_vigencias.armar_base()
        liquidar_vigencias.correr(vigs, carpeta / "salidas", man["detalle_excel"],
                                  txt_sistemas=man.get("tipo_corrida") == "liquidacion")
        if man.get("tipo_corrida") == "liquidacion":
            # El avaluo de cada predio y su aprobacion contra Sistemas.
            import avaluo_liquidacion
            from comparacion_vigencia import CONFIG as CONFIG_VIG, terreno_proyectado
            import insumos as _ins
            avaluo_liquidacion.correr(CONFIG_VIG["parquet_liquidacion"], man["insumos"]["export_liquidacion"],
                                      terreno_proyectado(), carpeta / "salidas",
                                      ruta_predio=man["insumos"]["predio_zhf"], comunas=man.get("comunas"),
                                      ruta_base=_ins.base_construcciones("./output/todas_las_construcciones.parquet"))
        estado = "OK"
    except BaseException:
        import traceback
        traceback.print_exc()
    finally:
        # Copia de lo que ESTA corrida escribio en output/ y results/.
        copiados = []
        for base in ("output", "results"):
            for actual, _, archivos in os.walk(raiz / base):
                if Path(actual).name == "logs":
                    continue
                for a in archivos:
                    p = Path(actual) / a
                    if a.startswith("~$") or p.stat().st_mtime < inicio:
                        continue
                    destino = carpeta / "salidas" / p.relative_to(raiz)
                    destino.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(p, destino)
                    copiados.append(str(p.relative_to(raiz)))
        man.update(estado=estado, fin=datetime.now().isoformat(timespec="seconds"),
                   minutos=round((time.time() - inicio) / 60, 1), copiados=sorted(copiados))
        man_path.write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\nCorrida guardada en {carpeta}")
        print(f"[FIN {estado}]")
        salida.flush()
    return 0 if estado == "OK" else 1


# ---------------------------------------------------------------------------
# La ventana
# ---------------------------------------------------------------------------
def ventana():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    w = tk.Tk()
    w.title("Liquidador")
    w.geometry("1050x760")

    raiz = tk.StringVar(value=str(raiz_por_defecto()))
    carpeta_insumos = tk.StringVar(value=str(Path(raiz.get()) / "input"))
    version = tk.StringVar()
    detalle = tk.BooleanVar(value=False)
    tipo = tk.StringVar(value="Preliquidación")
    actualizar_app = tk.BooleanVar(value=True)
    marcadas = {v: tk.BooleanVar(value=(v == 2027)) for v in sorted(insumos.VIGENCIAS)}
    modelos = tk.BooleanVar(value=False)
    modelos_txt = tk.StringVar()
    carpeta_modelos = tk.StringVar(value=str(Path(raiz.get()) / "Modelos"))
    tablas_txt = tk.StringVar()
    estado = tk.StringVar(value="Listo")
    archivo = {k: tk.StringVar() for k, *_ in insumos.INSUMOS}
    nota = {k: tk.StringVar() for k, *_ in insumos.INSUMOS}
    comuna = {c: tk.BooleanVar(value=True)
              for c in insumos.COMUNAS_URBANAS + insumos.COMUNAS_RURALES}
    corrida = {"p": None, "carpeta": None, "pos": 0, "t0": 0}

    pestanas = ttk.Notebook(w)
    pestanas.pack(fill="both", expand=True, padx=8, pady=8)
    t1 = ttk.Frame(pestanas, padding=10)
    t2 = ttk.Frame(pestanas, padding=10)
    pestanas.add(t1, text="1. Insumos")
    pestanas.add(t2, text="2. Ejecución y log")

    # --- Carpetas -----------------------------------------------------------
    def fila_carpeta(padre, texto, var, accion=None):
        f = ttk.Frame(padre)
        f.pack(fill="x", pady=2)
        ttk.Label(f, text=texto, width=22).pack(side="left")
        ttk.Entry(f, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)

        def elegir():
            d = filedialog.askdirectory(initialdir=var.get())
            if d:
                var.set(d)
                if accion:
                    accion()
        ttk.Button(f, text="Elegir...", command=elegir).pack(side="left")
        return f

    def al_cambiar_raiz():
        carpeta_insumos.set(str(Path(raiz.get()) / "input"))
        carpeta_modelos.set(str(Path(raiz.get()) / "Modelos"))
        refrescar_versiones()
        detectar()

    fila_carpeta(t1, "Carpeta del proyecto:", raiz, al_cambiar_raiz)
    f_ins = fila_carpeta(t1, "Carpeta de insumos:", carpeta_insumos)
    ttk.Button(f_ins, text="Detectar archivos", command=lambda: detectar()).pack(side="left", padx=(6, 0))

    # --- Insumos ------------------------------------------------------------
    caja = ttk.LabelFrame(t1, text="Insumos (se reconocen por nombre y columnas; se pueden cambiar a mano)",
                          padding=6)
    caja.pack(fill="x", pady=(8, 4))
    for i, (clave, etiqueta, obligatorio, para_que, _) in enumerate(insumos.INSUMOS):
        ttk.Label(caja, text=etiqueta + (" *" if obligatorio else ""), width=40).grid(row=i, column=0, sticky="w")
        ttk.Entry(caja, textvariable=archivo[clave], width=70).grid(row=i, column=1, sticky="we", padx=4)

        def elegir_archivo(k=clave):
            f = filedialog.askopenfilename(initialdir=carpeta_insumos.get(),
                                           filetypes=[("Datos", "*.parquet *.txt *.csv"), ("Todos", "*.*")])
            if f:
                archivo[k].set(f)
                nota[k].set("elegido a mano")
        ttk.Button(caja, text="...", width=3, command=elegir_archivo).grid(row=i, column=2)
        ttk.Label(caja, textvariable=nota[clave], width=26, foreground="#555").grid(row=i, column=3, sticky="w", padx=4)
    caja.columnconfigure(1, weight=1)
    ttk.Label(t1, text="* obligatorio. El ZHG se pide solo con modelos y el export de liquidación de Sistemas solo en "
                       "una Liquidación. No se usa ningún export histórico.", foreground="#555").pack(anchor="w")

    def detectar():
        if not Path(carpeta_insumos.get()).is_dir():
            return
        estado.set("Detectando insumos...")
        w.update_idletasks()
        for clave, (ruta, _, n) in insumos.detectar(carpeta_insumos.get()).items():
            archivo[clave].set(ruta or "")
            nota[clave].set(n)
        estado.set("Insumos detectados: revise la columna de la derecha")

    # --- Comunas ------------------------------------------------------------
    cc = ttk.LabelFrame(t1, text="Comunas a liquidar", padding=6)
    cc.pack(fill="x", pady=4)
    for j, c in enumerate(insumos.COMUNAS_URBANAS):
        ttk.Checkbutton(cc, text=c, variable=comuna[c], command=lambda: al_cambiar_comunas()).grid(
            row=0, column=j, sticky="w")
    for j, c in enumerate(insumos.COMUNAS_RURALES):
        ttk.Checkbutton(cc, text=c, variable=comuna[c], command=lambda: al_cambiar_comunas()).grid(
            row=1, column=j, sticky="w")
    atajos = ttk.Frame(cc)
    atajos.grid(row=2, column=0, columnspan=22, sticky="w", pady=(4, 0))

    def marcar(lista):
        for c, v in comuna.items():
            v.set(c in lista)
        al_cambiar_comunas()
    ttk.Button(atajos, text="Todas", command=lambda: marcar(list(comuna))).pack(side="left")
    ttk.Button(atajos, text="Urbanas (01-22)", command=lambda: marcar(insumos.COMUNAS_URBANAS)).pack(side="left", padx=4)
    ttk.Button(atajos, text="Rurales (51-65)", command=lambda: marcar(insumos.COMUNAS_RURALES)).pack(side="left")
    ttk.Button(atajos, text="Ninguna", command=lambda: marcar([])).pack(side="left", padx=4)

    def elegidas():
        """None = todas (la corrida de siempre)."""
        lista = [c for c, v in comuna.items() if v.get()]
        return None if len(lista) == len(comuna) else lista

    # --- Opciones -----------------------------------------------------------
    op = ttk.LabelFrame(t1, text="Corrida", padding=6)
    op.pack(fill="x", pady=4)
    f1 = ttk.Frame(op)
    f1.pack(fill="x")
    ttk.Label(f1, text="Tipo de corrida:").pack(side="left")
    ttk.Combobox(f1, textvariable=tipo, values=["Preliquidación", "Liquidación"], width=15,
                 state="readonly").pack(side="left", padx=(4, 18))
    chk_vig = {}
    ttk.Label(f1, text="Vigencias a liquidar:").pack(side="left")
    for v in sorted(insumos.VIGENCIAS):
        chk_vig[v] = ttk.Checkbutton(f1, text=insumos.VIGENCIAS[v]["etiqueta"], variable=marcadas[v],
                                     command=lambda: al_cambiar_vigencia())
        chk_vig[v].pack(side="left", padx=(6, 0))
    f1b = ttk.Frame(op)
    f1b.pack(fill="x", pady=(6, 0))
    ttk.Label(f1b, text="Tablas 2027:").pack(side="left")
    combo = ttk.Combobox(f1b, textvariable=version, width=6, state="readonly")
    combo.pack(side="left", padx=4)
    ttk.Label(f1b, textvariable=tablas_txt, foreground="#555").pack(side="left", padx=(4, 0))

    f2 = ttk.Frame(op)
    f2.pack(fill="x", pady=(6, 0))
    chk_mod = ttk.Checkbutton(f2, text="Liquidar con modelos (PH condición 9)", variable=modelos)
    chk_mod.pack(side="left")
    ttk.Label(f2, textvariable=modelos_txt, foreground="#555").pack(side="left", padx=(4, 0))
    ttk.Label(f2, text="   Carpeta de modelos:").pack(side="left")
    ttk.Entry(f2, textvariable=carpeta_modelos, width=50).pack(side="left", padx=4, fill="x", expand=True)

    def elegir_modelos():
        d = filedialog.askdirectory(initialdir=carpeta_modelos.get())
        if d:
            carpeta_modelos.set(d)
    ttk.Button(f2, text="Elegir...", command=elegir_modelos).pack(side="left")

    f3 = ttk.Frame(op)
    f3.pack(fill="x", pady=(6, 0))
    chk_det = ttk.Checkbutton(f3, text="Detalle por vigencias en Excel (tarda unos minutos)", variable=detalle)
    chk_det.pack(side="left", padx=(0, 10))
    chk_app = ttk.Checkbutton(f3, text="Actualizar los datos de la app (output/versiones)",
                              variable=actualizar_app)
    chk_app.pack(side="left")

    def vigs() -> list:
        return [v for v, var in marcadas.items() if var.get()]

    def al_cambiar_tipo(*_):
        # En una liquidacion solo cuenta la vigencia 2027.
        liq = tipo.get() == "Liquidación"
        for v, chk in chk_vig.items():
            if v != 2027:
                if liq:
                    marcadas[v].set(False)
                chk.state(["disabled" if liq else "!disabled"])
        if liq:
            marcadas[2027].set(True)
        chk_vig[2027].state(["disabled" if liq else "!disabled"])
        al_cambiar_vigencia()

    def al_cambiar_vigencia(*_):
        vs = vigs()
        con_modelos = [v for v in vs if insumos.VIGENCIAS[v]["modelos"] is not None]
        if con_modelos:
            chk_mod.state(["!disabled"])
            modelos_txt.set("(familias " + ", ".join(insumos.VIGENCIAS[v]["modelos"] for v in con_modelos)
                            + "; 2027 no tiene modelos)")
        else:
            modelos.set(False)
            chk_mod.state(["disabled"])
            modelos_txt.set("(2027 no tiene modelos: quedan en $0)")
        combo.state(["!disabled" if 2027 in vs else "disabled"])
        otras = [f"{v}: {insumos.VIGENCIAS[v]['tablas']}" for v in vs if v != 2027]
        tablas_txt.set("   " + " | ".join(otras) if otras else "")
        al_cambiar_comunas()

    def al_cambiar_comunas():
        # Con solo algunas comunas, o con otra vigencia, no se pisan los datos
        # de la app.
        if elegidas() is None and 2027 in vigs():
            chk_app.state(["!disabled"])
        else:
            actualizar_app.set(False)
            chk_app.state(["disabled"])

    def refrescar_versiones():
        vs = versiones(Path(raiz.get()))
        combo["values"] = vs
        if vs and version.get() not in vs:
            version.set(vs[-1])

    botones = ttk.Frame(t1)
    botones.pack(fill="x", pady=(8, 0))
    ttk.Label(t1, textvariable=estado, foreground="#0a5").pack(anchor="w", pady=(6, 0))

    def validar(mostrar_ok=True) -> bool:
        asignados = {k: v.get() for k, v in archivo.items()}
        com = elegidas()
        errores, avisos = insumos.validar(
            asignados, modelos.get(),
            com if com is not None else list(comuna),
            liquidacion=tipo.get() == "Liquidación")
        if not vigs():
            errores.append("No hay ninguna vigencia marcada.")
        es_liq = tipo.get() == "Liquidación"
        if not es_liq and asignados.get("export_liquidacion"):
            avisos.append("El export de liquidación de Sistemas solo se usa en una Liquidación: aquí se ignora.")
        if es_liq and vigs() != [2027]:
            errores.append("Una liquidación es solo de la vigencia 2027.")
        marcadas_com = com if com is not None else list(comuna)
        for v in vigs():
            fuera = [c for c in marcadas_com if c not in insumos.comunas_que_valora(v)]
            if fuera:
                txt = (f"La vigencia {v} no valora las comunas {', '.join(fuera)}: quedarán en 0"
                       if len(fuera) <= 12 else
                       f"La vigencia {v} no valora {len(fuera)} de las comunas marcadas "
                       f"(solo {', '.join(insumos.comunas_que_valora(v))}): las demás quedarán en 0")
                (errores if es_liq else avisos).append(txt + ".")
        if not version.get():
            errores.append("No hay versiones de tablas en input/tablas/input/.")
        if modelos.get():
            cm = Path(carpeta_modelos.get())
            for v in vigs():
                sub = insumos.VIGENCIAS[v]["modelos"]
                if sub and not list((cm / sub).glob("*.pkl")):
                    errores.append(f"Liquidar con modelos: no hay modelos (.pkl) en {cm / sub}.")
        if es_liq and avisos:
            # En una liquidacion no se sigue con avisos.
            errores += [f"(liquidación) {a}" for a in avisos]
            avisos = []
        if errores:
            messagebox.showerror("Validar insumos", f"No se puede {'liquidar' if es_liq else 'preliquidar'}:\n\n- "
                                 + "\n- ".join(errores)
                                 + ("\n\nAvisos:\n- " + "\n- ".join(avisos) if avisos else ""))
            estado.set(f"Validación: {len(errores)} error(es)")
            return False
        if avisos and not messagebox.askokcancel(
                "Validar insumos", "Insumos válidos, con avisos:\n\n- " + "\n- ".join(avisos)
                + "\n\n¿Continuar?"):
            return False
        if mostrar_ok and not avisos:
            messagebox.showinfo("Validar insumos", "Insumos válidos.")
        estado.set("Insumos válidos")
        return True

    def preliquidar():
        if corrida["p"] is not None:
            return
        if not validar(mostrar_ok=False):
            return
        r = Path(raiz.get())
        com = elegidas()
        etiqueta_corrida = ("LIQ_" if tipo.get() == "Liquidación" else "PRELIQ_") + "VIG" + "_".join(str(v) for v in vigs()) + (f"_{version.get()}" if 2027 in vigs() else "")
        nombre = (f"{datetime.now():%Y-%m-%d_%H%M}_{etiqueta_corrida}" + ("_modelos" if modelos.get() else "")
                  + ("" if com is None else f"_{len(com)}comunas"))
        carpeta = r / "corridas" / nombre
        n = 1
        while carpeta.exists():
            n += 1
            carpeta = r / "corridas" / f"{nombre}_{n}"
        carpeta.mkdir(parents=True)
        man = {
            "raiz": str(r.resolve()),
            "inicio": datetime.now().isoformat(timespec="seconds"),
            "codigo": commit(r),
            "tipo_corrida": "liquidacion" if tipo.get() == "Liquidación" else "preliquidacion",
            "vigencias": vigs(),
            "reglas": {v: insumos.VIGENCIAS[v]["reglas"] for v in vigs()},
            "version_tablas": version.get(),
            "modelos": modelos.get(),
            "carpeta_modelos": str(Path(carpeta_modelos.get()).resolve()),
            "comunas": com,
            "detalle_excel": detalle.get(),
            "actualizar_app": actualizar_app.get() and com is None and 2027 in vigs(),
            "insumos": {k: str(Path(v.get()).resolve()) for k, v in archivo.items() if v.get().strip()},
            "insumos_detalle": {k: describir(v.get()) for k, v in archivo.items() if v.get().strip()},
        }
        (carpeta / "manifiesto.json").write_text(json.dumps(man, indent=2, ensure_ascii=False), encoding="utf-8")
        cmd = ([sys.executable] if CONGELADO else [sys.executable, str(Path(__file__).resolve())])
        cmd += ["--correr", str(carpeta)]
        texto.delete("1.0", "end")
        corrida.update(p=subprocess.Popen(cmd, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)),
                       carpeta=carpeta, pos=0, t0=time.time())
        estado.set(f"Corriendo {etiqueta_corrida}... (pestaña 2)")
        estado2.set(f"Corriendo vigencias {', '.join(map(str, vigs()))} · {carpeta}")
        b_pre.state(["disabled"])
        pestanas.select(t2)
        w.after(500, leer_log)

    ttk.Button(botones, text="Validar insumos", command=validar).pack(side="left")
    b_pre = ttk.Button(botones, text="Generar", command=preliquidar)
    b_pre.pack(side="left", padx=8)

    # --- Pestana 2: log -------------------------------------------------------
    estado2 = tk.StringVar(value="Sin corridas en esta sesión")
    arriba = ttk.Frame(t2)
    arriba.pack(fill="x")
    ttk.Label(arriba, textvariable=estado2).pack(side="left")

    def abrir_carpeta():
        destino = corrida["carpeta"] or (Path(raiz.get()) / "corridas")
        if Path(destino).exists():
            os.startfile(destino)
    ttk.Button(arriba, text="Abrir carpeta de la corrida", command=abrir_carpeta).pack(side="right")
    texto = ScrolledText(t2, font=("Consolas", 9), wrap="none")
    texto.pack(fill="both", expand=True, pady=(8, 0))

    def leer_log():
        p, carpeta = corrida["p"], corrida["carpeta"]
        log = carpeta / "preliquidacion.log"
        if log.exists():
            with open(log, encoding="utf-8", errors="replace") as fh:
                fh.seek(corrida["pos"])
                nuevo = fh.read()
                corrida["pos"] = fh.tell()
            if nuevo:
                # tqdm reescribe la linea con \r: se deja solo lo ultimo.
                nuevo = "\n".join(l.split("\r")[-1] for l in nuevo.split("\n"))
                texto.insert("end", nuevo)
                texto.see("end")
        if p.poll() is None:
            w.after(500, leer_log)
            return
        ok = p.returncode == 0
        minutos = (time.time() - corrida["t0"]) / 60
        msg = f"{'Terminó' if ok else 'Terminó con ERROR'} en {minutos:.1f} min · {carpeta}"
        estado.set(msg)
        estado2.set(msg)
        b_pre.state(["!disabled"])
        corrida["p"] = None
        (messagebox.showinfo if ok else messagebox.showerror)("Liquidador", msg)

    def cerrar():
        if corrida["p"] is not None and corrida["p"].poll() is None:
            if not messagebox.askyesno("Liquidador",
                                       "La preliquidación sigue corriendo. ¿Detenerla y salir?"):
                return
            corrida["p"].terminate()
        w.destroy()

    w.protocol("WM_DELETE_WINDOW", cerrar)
    refrescar_versiones()
    tipo.trace_add("write", al_cambiar_tipo)
    al_cambiar_vigencia()
    w.after(100, detectar)
    w.mainloop()


if __name__ == "__main__":
    if "--correr" in sys.argv:
        sys.exit(correr(Path(sys.argv[sys.argv.index("--correr") + 1])))
    ventana()
