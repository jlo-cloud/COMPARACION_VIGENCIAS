# Preliquidación vigencia 2027

Liquida las construcciones de Cali con las tablas de valor propuestas para la
vigencia 2027 y compara el resultado contra lo que trae hoy la base (vigencia
2026). Incluye la app de Streamlit que muestra esa comparación.

## Cómo se corre

```
python src/main.py                 la liquidación y la comparación (~5 min)
python src/exportar_detalle.py     el Excel del detalle, cuando se necesite (~3 min)
streamlit run src/app_vigencias.py la app
```

La versión de las tablas de valor se elige con `VERSION_TABLAS` en
`src/consolidar_tablas.py` (hoy `V2`), o sin tocar el código:

```
VERSION_TABLAS=V1 python src/main.py
```

## Qué hace el main

| Paso | Qué hace | Módulo |
|---|---|---|
| 0 | Consolida las tablas de valor de la versión, solo si cambiaron | `consolidar_tablas` |
| 1 | Carga predios y construcciones de `input/export_liq/` | `tabla_construccion` |
| 2 | Homologa usos, cruza con el predio y descuenta los predios incompletos | `tabla_construccion`, `Homologacion`, `uso_principal`, `pre_inconsistencias` |
| 3 | Asigna tabla y VM² a cada construcción; los usos por modelo van con los `.pkl` | `Liquidacion_tablas`, `model_liq` |
| 4 | Guarda la liquidación y arma el libro de homologación con la hoja USOS | `hoja_usos` |
| 6 | Compara contra la vigencia 2026, por construcción y por predio | `comparacion_vigencia` |

Al final imprime el tiempo de cada paso y un control de filas: cuántas
construcciones entran, cuántas salen en cada etapa y por qué.

## Qué produce

Cada versión de tablas deja sus salidas en su propia carpeta,
`output/versiones/<VERSION>/`, para poder comparar unas contra otras.

| Salida | Qué es |
|---|---|
| `output/versiones/<V>/LIQUIDACION_TABLAS.parquet` | La liquidación, una fila por construcción |
| `output/versiones/<V>/COMPARACION_VIGENCIA_DETALLE.parquet` | La comparación con identificadores (ID de predio, número predial) |
| `output/versiones/<V>/COMPARACION_VIGENCIA_PUBLICO.parquet` | La misma, anónima, por construcción: la lee la app |
| `output/versiones/<V>/COMPARACION_VIGENCIA_PUBLICO_PREDIO.parquet` | La misma, anónima, por predio: la lee la app |
| `output/todas_las_construcciones.parquet` | La base de entrada ya cruzada |
| `input/tablas/output/Tablas_Valor_Consolidado_<V>_<fecha>.xlsx` | Las tablas de valor consolidadas |
| `results/HOMOLOGACION/HOMOLOGACION_Y_TABLAS_DE_VALOR_<V>_<fecha>.xlsx` | El consolidado más la hoja USOS |
| `results/COMPARACION_VIGENCIA/DETALLE_LIQUIDADOS_<V>_<fecha>.xlsx` | El detalle en Excel; lo escribe `exportar_detalle.py` |

`exportar_detalle.py` no vuelve a liquidar: pasa a Excel el
`COMPARACION_VIGENCIA_DETALLE.parquet` de la última corrida, y al arrancar
dice de qué fecha es. Si se cambian las tablas y se corre el main, hay que
volver a correrlo para que el Excel quede al día.

## Lo que está apagado

Estos libros no se escriben en la corrida normal. Cada uno se enciende con su
interruptor:

| Libro | Interruptor |
|---|---|
| Excel del detalle dentro del main | `CONFIG["excel_detalle"]` en `comparacion_vigencia.py` |
| Comparación entre versiones de tablas (V1 vs V2) | `CONFIG["excel_versiones"]` en `comparacion_vigencia.py`, o `python src/comparacion_versiones.py` |
| Libro de agregados con gráficos | `CONFIG["excel_reporte"]` en `comparacion_vigencia.py` |
| Reporte de pre-inconsistencias | `EXCEL_REPORTE` en `pre_inconsistencias.py` |
| Diagnóstico de tablas con VM² en cero | `EXCEL_DIAGNOSTICO` en `Liquidacion_tablas.py` |

Apagar el reporte de pre-inconsistencias no cambia la liquidación: los predios
incompletos se descuentan igual.

## Escenarios con reglas de otros años

```
python src/main.py --todas               agrega los escenarios al final
python src/escenarios.py                 solo los escenarios
python src/escenarios.py --solo-actual   solo la propuesta 2027
```

Liquida la base de hoy con las reglas de 2024, 2025 y la propuesta actual, y
deja `output/ESCENARIOS.parquet` con el VM² de cada una lado a lado.

| Ejercicio | Vigencia que rige | Dónde están sus valores | Factor catastral |
|---|---|---|---|
| 2024 | 2025 | dentro de `src/Liquidacion_tablas_2024.py` | 0,6 |
| 2025 | 2026 | dentro de `src/Liquidacion_tablas_2025.py` | 0,7 |
| actual | 2027 | en el Excel consolidado | 0,7 |

Mide **cuánto cambia el resultado al cambiar las reglas**. No reproduce lo que
se cobró esos años, porque aquellas liquidaciones corrieron sobre otra base.
Una regla que no existía en un ejercicio queda en cero, sin extrapolar.

## Qué hay en este repositorio

El repositorio es **público**, así que solo trae:

```
src/                  el código
requirements.txt      lo que necesita la app en Streamlit Cloud
.streamlit/           la configuración de la app
output/versiones/*/COMPARACION_VIGENCIA_PUBLICO*.parquet   los recortes anónimos que lee la app
```

**No trae los datos catastrales** (insumos, liquidación, detalle con
identificadores, Excel de resultados), ni las tablas de valor ni los modelos.
Lo que hace falta para correr el main está en [INSUMOS.md](INSUMOS.md).

Lo que entra y lo que no lo decide el `.gitignore`, que ignora todo por
defecto y solo deja pasar lo de arriba. Antes de agregar algo, revisar que no
lleve ID de predio ni número predial.

## Código que no se usa hoy

- `Liquidacion_final.py` y `liquidar_avaluo_2026.py`: la preliquidación por
  predio del ejercicio anterior (aprobados y no aprobados). Está apagada en el
  main; habría que actualizarla a las vigencias de este año antes de volver a
  usarla.
- `post_inconsistencias.py` y `uso_principal_terr.py`: solo los usa
  `Liquidacion_final.py`.
