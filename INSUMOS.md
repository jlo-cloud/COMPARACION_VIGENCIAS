# Insumos que no vienen en el repositorio

El repositorio es público y solo trae el código. Los datos catastrales, las
tablas de valor y los modelos están en el Drive del proyecto; pida acceso al
equipo de catastro.

Las carpetas `input` y `Modelos` del Drive tienen **la misma estructura que el
proyecto**: se descargan y se ponen en la raíz, sobre las carpetas del mismo
nombre.

Las tablas de abajo sirven para verificar que no falte nada y que los tamaños
cuadren. Un parquet truncado no da error al copiarse: falla después, al
leerlo, con un mensaje sobre el formato que no deja ver que el problema fue la
descarga.

## Para correr el main

### `input/export_liq/`

`tabla_construccion.py` toma de aquí el predio y las construcciones;
reconoce cada archivo por su nombre.

| Archivo | Peso | Para qué |
|---|---|---|
| `20260804_export_predio_zhf_2026.parquet` | 60,1 MB | El predio, con la ZHF 2026 |
| `export_predio_20260717.parquet` | 49,4 MB | La ZHF anterior y las variables de los modelos |
| `construccion_convencional_20260715_100736.parquet` | 25,6 MB | Construcciones convencionales |
| `construccion_no_convencional_20260715_100736.parquet` | 1,6 MB | Construcciones no convencionales |
| `insumo_proyección_comuna_valor_terreno_20260930.parquet` | 8,9 MB | El terreno proyectado para el avalúo 2027 |

### `input/otros/`

| Archivo | Peso | Para qué |
|---|---|---|
| `predio_20251209_150206.parquet` | 39,1 MB | Homologación |
| `PREDIO_20260307.parquet` | 10,8 MB | Homologación |
| `CAMBIO_NPN.xlsx` | 0,6 MB | Cambios de número predial nacional |
| `modelo_uso28.txt` | 0,1 MB | Uso principal |

### `input/tablas/`

| Carpeta o archivo | Para qué |
|---|---|
| `input/<V>/Consolidado_<fecha>.xlsx` | Las tablas de valor de cada versión (V1, V2…), tal como se entregan |
| `output/Tablas_Valor_Consolidado_<V>_<fecha>.xlsx` | El consolidado; si no está o es viejo, el paso 0 lo regenera |
| `HOMOLOGACION_Y_TABLAS_DE_VALOR_USOS_LADM_<fecha>.xlsx` | El libro de homologación con el que se arma la hoja USOS |
| `Entregas/` | Las entregas originales por familia; no las lee el main |

### `input/Reglas.xlsx`

La especificación de asignación de tabla.

### `Modelos/`

Los modelos de los usos que no van por tabla (apartamentos de 4 y más pisos,
comercio y oficinas en PH).

| Carpeta | Archivos |
|---|---|
| `Modelos/models/` | `modelo_gbr_M1.pkl`, `M3_RF_20251221.pkl`, `pipeline_M02_DIF_023.pkl`, `pipeline_M02_IGUAL_023.pkl` |
| `Modelos/models_2024/` | `21_12_2024_model_GBR_M1.pkl`, `21_12_2024_model_XGB_M3.pkl`, `M4_OFICINAS_20241227.pkl` |

Con todo eso en su sitio:

```
python src/main.py
```

## Solo para los escenarios 2024 y 2025

`escenarios.py` necesita además la familia de modelos 2024 completa y estos
insumos, que hoy **no están** en la carpeta de trabajo:

| Archivo | Va en |
|---|---|
| `ZHG_2024_2025.parquet` | `input/otros/` |
| `export_predio_2025.txt` | `input/export_liq/` |
| `export_construccion_2025.txt` | `input/export_liq/` |

Si ya se corrió el main, `output/todas_las_construcciones.parquet` sirve de
base y no hace falta regenerarla.

## Solo para la app

La app no necesita ningún insumo: lee los parquets anónimos de
`output/versiones/`, que sí vienen en el repositorio. La hoja Detalle, que
lleva identificadores, solo funciona donde esté
`COMPARACION_VIGENCIA_DETALLE.parquet`, es decir, en el equipo donde se corrió
el main.
