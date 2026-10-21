# Liquidador catastral — vigencia 2027

> **Rama `liquidador-vig-2027` de COMPARACION_VIGENCIAS.** Es la rama de trabajo del liquidador; no modifica `main`. Como el repositorio es público, aquí no vienen modelos, tablas de valor, `Reglas.xlsx` ni datos de predios: se toman del Drive del proyecto o de `main` con `src/sincronizar_upstream.py` (ver [docs/UPSTREAM.md](docs/UPSTREAM.md)).

Código de la liquidación catastral de Cali por tablas de valor y por modelos.
Se usa de tres formas:

1. **Liquidación de la vigencia.** Toma los exports de Sistemas y entrega el avalúo de cada predio, junto con los reportes de calidad e inconsistencias.
2. **Escenarios.** Liquida la misma base con las reglas de 2024, 2025 y la vigencia actual, para ver cuánto cambia el resultado según la regla.
3. **Reliquidación de un listado de predios con otras condiciones.** Sirve para reclamaciones, radicados o revisiones de vigencias anteriores. Permite cambiar las reglas del ejercicio, la comuna cuyos valores se aplican, la ZHF y el terreno.

Todo se puede correr desde el ejecutable de Windows, sin instalar Python, o desde el código.

---

## Inicio rápido

**Con el ejecutable.** Se copia la carpeta `dist\LiquidadorCatastral\` completa y se abre `LiquidadorCatastral.exe`.

**Qué lleva el ejecutable por dentro y qué hay que darle.**
- **Por dentro:** Python y todas las bibliotecas, el código, los 7 modelos (`.pkl`), las tablas de los ejercicios 2024 y 2025, las reglas de asignación de tabla de `Reglas.xlsx` (escritas en el código) y la homologación de usos.
- **Hay que darle una carpeta con los insumos** (ver [INSUMOS.md](INSUMOS.md)): los exports de Sistemas (predios, construcciones, anexos, terrenos, vigencia anterior e históricos), las **tablas de valor consolidadas de la vigencia**, la ZHG histórica, predios especiales, cambios de número predial y la foto de predios para comparar. "Detectar archivos" los reconoce por su contenido.
- **Tablas de valor y modelos: vienen de la fuente** `jlo-cloud/COMPARACION_VIGENCIAS`, que este repositorio solo lee. `python src/sincronizar_upstream.py --aplicar` trae solo esas rutas y registra el commit en `UPSTREAM.lock.json`. Al reconstruir, el ejecutable las lleva por dentro con la versión de tablas elegida (V1, V2…), así que ya no hace falta ponerlas en la carpeta de insumos (si se ponen, mandan esas). Ver [docs/UPSTREAM.md](docs/UPSTREAM.md).

| Pestaña | Para qué |
|---|---|
| 1. Insumos | Elegir las **comunas a liquidar**, detectar o elegir los exports, validarlos, revisar su calidad, **prevalidar las comunas** y generar la liquidación |
| 2. Ejecución y logs | Ver lo que va haciendo el motor |
| 3. Reliquidar predios | Volver a liquidar un listado de predios con otras condiciones |

La guía del operador, con requisitos de memoria, tiempos y el bloqueo de Windows, está en [docs/EJECUTABLE_WINDOWS.md](docs/EJECUTABLE_WINDOWS.md).

**Desde el código.** Se necesita Python 3.12 con `requirements.txt`; esa versión es obligatoria porque los modelos se serializaron con scikit-learn 1.5.

```powershell
python src\desktop_app.py                                  # la interfaz
python src\main.py --manifest manifest_2027.json --todas   # liquidación + escenarios
python src\escenarios.py                                   # solo los escenarios, sobre una base ya generada
python src\reliquidacion.py ejemplos\reliquidacion_radicados_comuna02.json
```

El ejecutable acepta las mismas acciones por línea de comandos:

```text
LiquidadorCatastral.exe --run-manifest manifest.json        liquidación completa
LiquidadorCatastral.exe --quality manifest.json             solo la calidad de los insumos
LiquidadorCatastral.exe --prevalidar manifest.json          solo la prevalidacion de las comunas elegidas
LiquidadorCatastral.exe --validate-manifest manifest.json   solo verifica que los archivos existan
LiquidadorCatastral.exe --detect carpeta                    reconoce los insumos de una carpeta
LiquidadorCatastral.exe --reliquidar configuracion.json     reliquidación de un listado de predios
LiquidadorCatastral.exe --self-test                         comprueba bibliotecas y modelos
```

---

## Cómo funciona la liquidación

Todo parte de un **manifiesto** (JSON) que dice qué archivo es cada insumo, **qué comunas se liquidan** (`comunas_liquidar`), el tipo de corrida (preliquidación o liquidación) y los formatos de salida. La interfaz lo arma sola: reconoce cada insumo por su contenido (columnas, hojas y fecha en el nombre), no por el nombre del archivo. Con el manifiesto, `main.py` corre estos pasos:

| Paso | Qué hace | Módulo |
|---|---|---|
| 0A | Calidad de los insumos: compara cada export con el de la vigencia anterior (cobertura de ZHF, estrato, matrícula, coordenadas, duplicados). Los ERROR detienen la corrida. | `calidad_insumos.py` |
| 0B | **Prevalidación de las comunas elegidas**: para cada una revisa regla y grupo de tablas, que el consolidado tenga valores para cada tabla que necesitan sus construcciones, parqueaderos avalados, modelo para la propiedad horizontal, especiales, usos sin regla, y predio por predio ZHF, puntaje, área, terreno y coordenadas. Cada comuna queda APTA, APTA CON ADVERTENCIAS o NO APTA. En una **liquidación** una comuna NO APTA detiene la corrida; en una preliquidación se avisa y se sigue. | `prevalidacion_comunas.py`, `comunas.py` |
| 0 | Consolida las tablas de valor del Excel de la vigencia | `consolidar_tablas.py` |
| 1 | Arma la base de construcciones y predios desde los exports, **solo con las comunas elegidas** | `tabla_construccion.py` |
| 2 | Cruza construcciones con predios, homologa usos y define el uso principal | `tabla_construccion.py`, `Homologacion.py`, `uso_principal.py` |
| — | Inconsistencias previas: predios sin el dato necesario para liquidar | `pre_inconsistencias.py` |
| 3 | Asigna a cada construcción su tabla (por uso, tipología de la ZHF, estrato y condición) y su valor por m²; lo que va por modelo se estima con los `.pkl` | `Liquidacion_tablas.py`, `model_liq.py` |
| 3 | **Contrato de variables de los modelos**: antes de cada predicción revisa que lleguen todas las variables que el modelo espera, que las numéricas sean números (si llegan como texto y todas se pueden convertir, se convierten sin cambiar su valor; si no, es error), que estén dentro de su rango y unidad (latitud en Cali, año 1800-2027, puntaje 1-100, valor del suelo en pesos/m²...) y que las indicadoras valgan 0 o 1. Así se detecta una variable numérica leída como texto, que de otro modo el modelo recibiría en 0 sin avisar. Deja `CONTRATO_VARIABLES_MODELOS.xlsx`; en una liquidación un error detiene la corrida. | `sincronizar_upstream.py` | Trae tablas y modelos de la fuente (solo lectura) y registra su procedencia |
| `contrato_modelos.py` |
| — | Inconsistencias posteriores: construcciones que tenían todo y quedaron en $0 (falta de regla o de modelo) | `post_inconsistencias.py` |
| 4 | Guarda la liquidación por construcción (`LIQUIDACION_TABLAS.parquet`) | `main.py` |
| 5 | Avalúo de cada predio: terreno + construcciones + anexos. Catastral = comercial × 0,7 redondeado a miles por componente, y el avalúo es la suma de los componentes que entran según el método (un integral no lleva terreno). | `Liquidacion_final.py`, `liquidar_avaluo_2026.py`, `uso_principal_terr.py` |
| 5 | **Validación de la preliquidación**, predio por predio: `ESTADO_PRELIQUIDACION` (CUMPLE / CUMPLE CON OBSERVACIONES / NO CUMPLE) y `QUE_NO_CUMPLE` (avalúo en $0, construcciones en $0, sin terreno, comuna sin tablas...) | `validacion_preliquidacion.py` |
| — | Reporte de predios por corregir: una fila por predio con `QUE_NO_CUMPLE`, el dato que le falta, la acción y `PASA_PRELIQUIDACION`. Junta prevalidación, inconsistencias previas, posteriores y la validación final. | `reporte_predios_inconsistentes.py` |
| 7 | Escenarios 2024 / 2025 / actual sobre la misma base (opcional) | `escenarios.py` |
| fin | Publica los resultados en carpetas por acción y versión | `publicar_resultados.py` |

Módulos de apoyo:

| Módulo | Qué hace |
|---|---|
| `config.py` | Carga el manifiesto y da rutas y parámetros |
| `comunas.py` | Grupos de comunas de las tablas, familias de modelo y la selección de comunas del manifiesto |
| `manifest_contract.py` | Contrato de insumos, detección automática y validación |
| `control_filas.py` | Controles de conteo entre pasos |
| `perf.py` | Tiempos por paso |
| `contrato_modelos.py` | Tipo, unidad y rango de cada variable de los modelos, verificados antes de predecir |
| `desktop_app.py` | Interfaz y punto de entrada del ejecutable |

### Dónde están las reglas de cada ejercicio

| Ejercicio | Vigencia que rige | Tablas | Modelos |
|---|---|---|---|
| 2024 | 2025 | dentro de `src/Liquidacion_tablas_2024.py` | familia 2024 en `Modelos/models_2024/` |
| 2025 | 2026 | dentro de `src/Liquidacion_tablas_2025.py` | familia 2025 en `Modelos/models/` |
| actual | 2027 | Excel consolidado de `input/tablas/output/` | sin modelo propio todavía |

Los dos ejercicios históricos llevan sus valores escritos en el código, como se hizo en su momento. Así quedan como evidencia de con qué se liquidó cada año. `model_liq.py` maneja las dos familias de modelos.

Dos detalles que cambian los valores:

- **Comunas por tabla.** En el ejercicio 2025, las tablas T1 a T4 y los anexos tienen dos juegos de valores: uno para las comunas 03 y 22, y otro para las comunas 01, 09, 10, 11 y 12. Una comuna que el ejercicio no actualizó no tiene tabla y queda en $0 en ese escenario.
- **Factor catastral.** Es **0,7 en los tres ejercicios**. El de 2024 se verificó contra el export oficial: con 0,7 el 99,4 % de las construcciones liquidadas por tabla da exacto.

### Parqueaderos y depósitos (T12)

Los parqueaderos (usos 007, 008, 036 y 037) se liquidan por cupo: el valor de la tabla × un factor de área. Ese valor ya es el total de la construcción. Los depósitos (006 y 027) de la misma tabla van por m². `escenarios.py` y `reliquidacion.py` respetan esa diferencia.

---

## Reliquidación de un listado de predios

`reliquidacion.py` toma un listado de predios (Excel o CSV con `ID_PREDIO`) y una configuración JSON, y entrega un Excel con:

- la variación del avalúo **por predio y por construcción** frente a un avalúo de referencia;
- rangos de cuántos predios suben y cuántos bajan;
- las novedades marcadas: mutaciones, cambio de tipología de la ZHF, especiales, lo que iba por modelo y el terreno que no cuadra con su zona.

En la configuración se elige:

| Parámetro | Ejemplo |
|---|---|
| Reglas del ejercicio | `"2025"` |
| Comuna cuyos valores se aplican | `"01"`, para una comuna que no estuvo en ese ejercicio |
| ZHF | La de otro export, por ejemplo el de la vigencia anterior |
| Terreno y avalúo de referencia | Una foto de predios de la vigencia a comparar; el terreno se conserva |
| Exports de referencia | Para detectar mutaciones construcción por construcción |
| `excluir_modelo` | Deja fuera lo que en ese ejercicio iba por modelo |

La guía completa, con todos los parámetros y cómo leer el resultado, está en [docs/RELIQUIDACION.md](docs/RELIQUIDACION.md). El ejemplo [ejemplos/reliquidacion_radicados_comuna02.json](ejemplos/reliquidacion_radicados_comuna02.json) reproduce el ejercicio de los radicados de la comuna 02 de octubre de 2026.

---

## Qué produce

En la carpeta de resultados, cada acción en su carpeta y cada corrida en una versión (`AAAA-MM-DD_HHMM_TIPO`):

```text
00_MANIFIESTOS/                  manifiesto con que se corrió
01_CALIDAD_INSUMOS/              CALIDAD_INSUMOS_<run_id>.xlsx
01B_PREVALIDACION_COMUNAS/       PREVALIDACION_COMUNAS_<run_id>.xlsx (COMUNAS, CRITERIOS, PREDIOS_NO_CUMPLEN, TABLAS_CONSOLIDADO)
02_INCONSISTENCIAS_PREVIAS/      predios sin datos para liquidar
03_LIQUIDACION_CONSTRUCCIONES/   liquidación por construcción, diagnóstico de tablas y CONTRATO_VARIABLES_MODELOS.xlsx
04_INCONSISTENCIAS_POSTERIORES/  construcciones sin valor y su causa
05_RESULTADO_PREDIOS/            PREDIOS_<TIPO>.parquet / .txt (formato Sistemas) y REVISION_LIQUIDACION.xlsx (RESUMEN, NO_CUMPLEN, CUMPLEN)
06_ESCENARIOS/                   ESCENARIOS.parquet y DETALLE_VIGENCIAS.xlsx
07_PREDIOS_POR_CORREGIR/         PREDIOS_POR_CORREGIR_<fecha>.xlsx
```

El `.txt` de liquidación sale como los export de Sistemas: separador `|`, coma decimal y codificación latin-1. ZHF, NPN e identificadores salen como texto.

La reliquidación escribe `RELIQUIDACION_<nombre>_<fecha>.xlsx` en la carpeta `salida` de su configuración.

---

## Estructura del repositorio

```text
src/                       código (descrito arriba)
tests/                     pruebas unitarias (python -m unittest discover -s tests)
Modelos/models/            modelos de la familia 2025
Modelos/models_2024/       modelos de la familia 2024
input/tablas/output/       tablas de valor consolidadas de la vigencia actual
input/Reglas.xlsx          especificación de asignación de tabla
ejemplos/                  configuraciones de reliquidación de ejemplo
docs/                      guía del ejecutable, reliquidación, flujograma y auditoría inicial
notebooks/                 análisis exploratorios (no los usa el motor)
LiquidadorCatastral.spec   receta de PyInstaller
build_exe.ps1              construye el ejecutable: pruebas + PyInstaller + self-test
run_dev.ps1                abre la interfaz desde el código
INSUMOS.md                 qué insumos hacen falta, dónde están y cuánto pesan
upstream.json              de dónde vienen las tablas y los modelos (fuente de solo lectura)
UPSTREAM.lock.json         de qué commit de la fuente salieron los que están aquí
```

**No vienen los datos de predios.** Son más de 1 GB, varios archivos pasan el límite de GitHub y cambian en cada corrida. [INSUMOS.md](INSUMOS.md) dice cuáles son y dónde conseguirlos.

---

## Pruebas y construcción del ejecutable

```powershell
.\.venv-build\Scripts\python.exe -m unittest discover -s tests   # pruebas
.\build_exe.ps1 -Clean                                           # entorno, pruebas, PyInstaller y self-test
```

El ejecutable queda en `dist\LiquidadorCatastral\`. Se distribuye la carpeta completa, porque trae las bibliotecas y los modelos.

---

## Advertencias

- **Los escenarios miden reglas, no reproducen historia.** Correr las reglas de 2024 sobre la base de hoy muestra cuánto cambia el resultado al cambiar las reglas. Las ZHF, puntajes y áreas de hoy no son las de entonces. Para reproducir una vigencia anterior con sus condiciones se usa la reliquidación, que permite fijar la ZHF y el terreno de esa vigencia.
- **Construcciones entre vigencias.** `ID_CONSTRUCCION` no se conserva de una vigencia a otra. Las construcciones se cruzan por predio + área + puntaje, y los anexos por predio + destino + tipo + área.
- **Memoria.** La corrida completa de la ciudad usa hasta 10 GB de RAM; con menos comunas elegidas usa menos.
- **Decisiones pendientes de negocio:** están en [docs/DUDAS_PENDIENTES.md](docs/DUDAS_PENDIENTES.md). Las más importantes son el alcance de comunas, la propiedad horizontal sin modelo 2027, las tablas T7, T8, T10 y T12 y el terreno 2027.
- **Auditoría:** [docs/AUDITORIA_2026-10-19.md](docs/AUDITORIA_2026-10-19.md), con el estado de cada hallazgo.
- **Otros pendientes técnicos:**
  - Las tablas de 2024 y 2025 siguen dentro de su script y no en archivos de parámetros.
  - Falta la traducción automática de nombres de variables a partir del diccionario 2027.
  - Las columnas de salida conservan nombres con "2026".
