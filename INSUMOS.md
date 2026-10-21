# Insumos que no vienen en el repositorio

Son 593 MB de datos catastrales. No entran en git: dos archivos pasan de
100 MB y GitHub los rechaza, y todos se reescriben enteros en cada corrida,
así que el repositorio crecería sin control.

**Están en Drive:**
https://drive.google.com/drive/folders/10J0s4rOm-8i3qsqMWds74rOagPapvi0B

Las carpetas `input` y `output` de Drive tienen **la misma estructura que el
proyecto**: se descargan y se dejan caer en la raíz, sobre las carpetas del
mismo nombre. No hay que colocar archivo por archivo.

Las tablas de abajo son para verificar que no falte nada y que los tamaños
cuadren. Si un archivo queda en otra carpeta, el pipeline falla con un error
que no dice cuál falta.

## Si solo quiere ver los escenarios funcionando

Con **un** archivo basta:

| Archivo | Va en | Peso |
|---|---|---|
| `todas_las_construcciones.parquet` | `output/` | 98,0 MB |

Es la base de entrada ya procesada. Con eso corre:

```
python src/escenarios.py
```

y obtiene `output/ESCENARIOS.parquet` y el detalle de las tres vigencias. No
hace falta nada más.

## Si quiere regenerar la base desde cero

Entonces sí hacen falta los exports. `tabla_construccion.py` barre la carpeta
`input/export_liq/` completa, así que tienen que estar los seis.

### `input/export_liq/`

| Archivo | Peso |
|---|---|
| `export_predio_2025.txt` | 179,5 MB |
| `export_construccion_2025.txt` | 125,0 MB |
| `20260804_export_predio_zhf_2026.parquet` | 60,1 MB |
| `export_predio_20260717.parquet` | 49,4 MB |
| `construccion_convencional_20260715_100736.parquet` | 25,6 MB |
| `construccion_no_convencional_20260715_100736.parquet` | 1,6 MB |

### `input/otros/`

| Archivo | Peso | Para qué |
|---|---|---|
| `predio_20251209_150206.parquet` | 39,1 MB | homologación |
| `PREDIO_20260307.parquet` | 10,8 MB | homologación |
| `ZHG_2024_2025.parquet` | 2,8 MB | variables de los modelos |
| `CAMBIO_NPN.xlsx` | 0,6 MB | cambios de predial nacional |
| `modelo_uso28.txt` | 0,1 MB | uso principal |

Con todo eso en su sitio:

```
python src/main.py
```

## Lo que YA viene en el repositorio

No hay que bajarlo de ningún lado:

```
Modelos/models/           los .pkl de la familia 2025
Modelos/models_2024/      los .pkl de la familia 2024
input/tablas/output/      las tablas de valor consolidadas
input/Reglas.xlsx         la especificación de asignación de tabla
```

## Cómo verificar que la descarga quedó completa

Compare el tamaño de cada archivo contra las tablas de arriba. Un parquet
truncado no da error al copiarse: falla después, al leerlo, con un mensaje
sobre el formato que no ayuda a entender que el problema fue la descarga.
