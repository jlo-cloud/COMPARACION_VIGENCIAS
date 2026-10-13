"""
Escribe el DETALLE_LIQUIDADOS_<version>_<fecha>.xlsx a partir del parquet que
dejo la ultima corrida del main, sin volver a liquidar.

El main ya no escribe este Excel (cuesta ~5 min); guarda los mismos datos en
output/versiones/<VERSION>/COMPARACION_VIGENCIA_DETALLE.parquet. Este script
los pasa a Excel cuando se necesitan para entregar o revisar a mano.

Uso:  python src/exportar_detalle.py
      python src/exportar_detalle.py --muestra 5000   (solo una muestra)
"""
import argparse
import os
import time
from datetime import datetime

import pandas as pd

from comparacion_vigencia import CONFIG, exportar_detalle_excel


def main():
    p = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    p.add_argument("--muestra", type=int, default=None,
                   help="filas del Excel, repartidas entre las tablas "
                        "(por defecto salen todas)")
    a = p.parse_args()

    origen = CONFIG["parquet_detalle"]
    if not os.path.exists(origen):
        raise SystemExit(f"No existe {origen}. Corra primero: python src/main.py")

    hecho = datetime.fromtimestamp(os.path.getmtime(origen))
    print(f"Leyendo {origen}")
    print(f"   (lo dejo la corrida del {hecho:%Y-%m-%d %H:%M})")
    det = pd.read_parquet(origen)

    # El mismo nombre que le ponia el main.
    sufijo = "" if CONFIG["base_valor"] == "CATASTRAL" else "_COMERCIAL"
    ruta = os.path.join(
        CONFIG["carpeta_results"],
        f"DETALLE_LIQUIDADOS_{CONFIG['version_tablas']}{sufijo}_"
        f"{datetime.now():%Y%m%d}.xlsx")

    print(f"Escribiendo {len(det):,} construcciones a Excel (tarda unos minutos)...")
    inicio = time.time()
    exportar_detalle_excel(det, ruta, a.muestra)
    print(f"Listo: {ruta}")
    print(f"   {time.time() - inicio:.0f} s")


if __name__ == "__main__":
    main()
