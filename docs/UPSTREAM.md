# Tablas y modelos desde la fuente (COMPARACION_VIGENCIAS)

Las tablas de valor cambian con cada entrega del equipo de valoración, y los modelos se pueden reentrenar o agregar. Por eso no se editan en este repositorio: se publican en el repositorio **fuente** y aquí se traen.

| Repositorio | Papel | Qué hace este repositorio con él |
|---|---|---|
| `jlo-cloud/COMPARACION_VIGENCIAS`, rama `main` | **Fuente:** tablas de valor, `Reglas.xlsx` y modelos | Solo lee. Nunca se escribe en él: el envío está deshabilitado en el remoto `upstream`. |
| `jlo-cloud/LIQUIDACION-VIG-2027` (este) | **Consumidor:** el liquidador, el ejecutable y la reliquidación | Trae de la fuente solo las rutas declaradas en `upstream.json` |

Los dos repositorios no comparten historia en git. Volver este una rama de la fuente obligaría a mezclar las dos historias y a reemplazar este código con el de la fuente. En su lugar, la fuente queda como **remoto de solo lectura** (`upstream`) y se importan archivos puntuales.

## Qué se trae

Lo define `upstream.json`, en la raíz del repositorio:

| Categoría | Rutas en la fuente | Para qué |
|---|---|---|
| tablas | `input/tablas/input/<V>/Consolidado_*.xlsx` | El libro tal como lo entrega valoración, por versión |
| tablas | `input/tablas/output/Tablas_Valor_Consolidado_<V>_*.xlsx` | El consolidado que lee el motor |
| tablas | `input/tablas/HOMOLOGACION_Y_TABLAS_DE_VALOR_USOS_LADM_*.xlsx`, `input/Reglas.xlsx` | Homologación y especificación de reglas |
| modelos | `Modelos/models/*.pkl`, `Modelos/models_2024/*.pkl` | Modelos de la propiedad horizontal |

**El código de la fuente no se trae.** La sincronización lista qué archivos de `src/` cambiaron allá desde la última vez. Así se puede revisar si un cambio de regla debe llevarse también a este liquidador.

## Cómo se actualiza

```powershell
.\.venv-build\Scripts\python.exe src\sincronizar_upstream.py            # revisión: qué cambiaría (no toca nada)
.\.venv-build\Scripts\python.exe src\sincronizar_upstream.py --aplicar  # trae los archivos y actualiza UPSTREAM.lock.json
```

La sincronización valida lo que llega:

- **Tablas:** que el consolidado tenga las hojas que lee el motor, y qué familias y anexos trae con valores. Las que falten aparecen después en la prevalidación por comuna.
- **Modelos:** que carguen, y que cada variable que esperan esté en el contrato de variables (`contrato_modelos.py`). Si un modelo nuevo pide una variable sin contrato, el código de este repositorio no la construye y hay que adaptar `model_liq.py` antes de usarlo.

Deja el informe en `output/upstream/SINCRONIZACION_<fecha>.md`. Después:

1. Revisar el informe.
2. Hacer commit, en la rama de trabajo, de los archivos traídos y de `UPSTREAM.lock.json`.
3. Reconstruir el ejecutable (`build_exe.ps1`). El ejecutable lleva por dentro las tablas consolidadas y los modelos sincronizados, y también `UPSTREAM.lock.json`.

## Cómo se usan en la liquidación

- **Versión de tablas.** Se elige en la interfaz o con el parámetro `version_tablas` del manifiesto (V1, V2…). Por defecto se usa la de `upstream.json`.
- **De dónde sale el consolidado.** Se busca en este orden:
  1. el insumo `tablas_valor` de la carpeta de insumos, si viene;
  2. la carpeta de trabajo;
  3. lo sincronizado en el repositorio;
  4. lo empaquetado en el ejecutable.

  Ya no es obligatorio poner las tablas en la carpeta de insumos.
- **Modelos.** Se usan los del repositorio o los del ejecutable. Para probar un modelo nuevo sin recompilar, el parámetro `carpeta_modelos` del manifiesto apunta a una carpeta con `models/` y `models_2024/`. El contrato de variables lo revisa antes de predecir.
- **Procedencia.** Cada corrida guarda en su manifiesto de ejecución (`procedencia`):
  - el commit de la fuente;
  - el nombre y la huella del consolidado usado;
  - si ese consolidado es el que vino de la fuente.

## Estado al 21/10/2026

La fuente **todavía no publica tablas ni modelos**: su `.gitignore` solo deja pasar el código, la app y los recortes anónimos, y las tablas y los modelos siguen en el Drive. La sincronización lo informa y no trae nada. Mientras tanto, las tablas siguen llegando por la carpeta de insumos.

Para que el flujo funcione, el equipo de la fuente debe agregar esas rutas a su `.gitignore` y publicarlas. Tener en cuenta que **la fuente es pública**: lo que se publique ahí queda visible para cualquiera. Ver la duda 14 en [DUDAS_PENDIENTES.md](DUDAS_PENDIENTES.md).
