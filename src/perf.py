"""
Medición de tiempos del pipeline de liquidación (solo instrumentación).

Uso:
    from perf import crono
    crono.inicio("LIQUIDACION")        # marca el arranque (opcional)
    ...                                 # trabajo
    crono.marca("PASO 1: construcciones")   # registra el tiempo desde la marca anterior
    ...
    crono.resumen()                     # imprime la tabla ordenada por duración

Si se llama crono.marca() sin haber llamado crono.inicio() (p. ej. desde la app),
el cronómetro se auto-inicializa en la primera marca.
"""

import time


class Crono:
    def __init__(self):
        self.t0 = None
        self.tprev = None
        self.marcas = []

    def inicio(self, nombre="proceso"):
        now = time.perf_counter()
        self.t0 = now
        self.tprev = now
        self.nombre = nombre
        self.marcas = []
        print(f"\n⏱️  [CRONO] INICIO · {nombre}")

    def marca(self, etiqueta):
        now = time.perf_counter()
        if self.t0 is None:          # auto-inicio (p. ej. corriendo desde la app)
            self.t0 = now
            self.tprev = now
            self.nombre = "auto"
        delta = now - self.tprev
        total = now - self.t0
        self.tprev = now
        self.marcas.append((etiqueta, delta))
        print(f"⏱️  [CRONO] {etiqueta:<48s} +{delta:8.2f}s   (acum {total:8.2f}s)")

    def resumen(self):
        print("\n" + "=" * 72)
        print("⏱️  RESUMEN DE TIEMPOS (ordenado por duración)")
        print("=" * 72)
        total = 0.0
        for etq, d in sorted(self.marcas, key=lambda x: x[1], reverse=True):
            total += d
            print(f"  {etq:<50s} {d:9.2f}s")
        print("-" * 72)
        print(f"  {'SUMA DE MARCAS':<50s} {total:9.2f}s")
        print("=" * 72 + "\n")


# Instancia única compartida por todos los módulos
crono = Crono()
