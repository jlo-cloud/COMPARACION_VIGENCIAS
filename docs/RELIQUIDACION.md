# Reliquidación de un listado de predios

`src/reliquidacion.py` vuelve a liquidar un grupo de predios cambiando las condiciones de la liquidación. Se usa para reclamaciones, radicados o verificaciones de una vigencia anterior. El caso que lo originó fue: *"liquidar las construcciones con las tablas de la actualización 2025 y conservar el valor de suelo asignado en la actualización 2024"*.

## Qué hace

1. **Lee el listado de predios.** Es un Excel, CSV o parquet con una columna `ID_PREDIO`. Las demás columnas (radicado, NPN, estado) se conservan en el resultado.
2. **Toma las construcciones de hoy de esos predios** de la base de construcciones (`todas_las_construcciones.parquet`, que deja el paso 1 del liquidador).
3. **Ajusta las condiciones que pida la configuración:**
   - la **ZHF** de otro export, por ejemplo la de la vigencia anterior;
   - la **comuna** cuyos valores se aplican, para el caso de una comuna que no hizo parte del ejercicio;
   - lo que en ese ejercicio iba **por modelo** se manda a tabla, como la condición 8;
   - las **especiales** pierden su valor especial.
4. **Liquida por tabla** con el motor del ejercicio elegido (`Liquidacion_tablas_2024.py` o `Liquidacion_tablas_2025.py`). El valor catastral es el valor comercial × el factor (0,7) × el área. Los parqueaderos se liquidan por cupo.
5. **Arma el avalúo de cada predio:** terreno de referencia + construcciones + anexos, redondeado a miles. El terreno no se recalcula: se conserva el de la vigencia de referencia.
6. **Compara** contra el avalúo de referencia, por predio y por construcción.
7. **Marca las novedades** (ver más abajo).

Con `excluir_modelo`, los predios que tienen alguna construcción que iba por modelo salen del archivo. Quedan listados, sin valores, en la hoja EXCLUIDOS_MODELO.

## Cómo se corre

- **Ejecutable, pestaña "3. Reliquidar predios":** se llenan los campos, o se pulsa *Cargar configuración...*, y luego *Reliquidar*. La configuración usada queda guardada junto al resultado.
- **Ejecutable por línea de comandos:**

  ```text
  LiquidadorCatastral.exe --reliquidar configuracion.json
  ```

- **Desde el código:**

  ```text
  python src\reliquidacion.py configuracion.json
  ```

## La configuración

Ejemplo completo: [ejemplos/reliquidacion_radicados_comuna02.json](../ejemplos/reliquidacion_radicados_comuna02.json). Las rutas relativas se resuelven desde la carpeta donde está el JSON.

| Campo | Obligatorio | Qué es |
|---|---|---|
| `nombre` | sí | Nombre del ejercicio; va en el nombre del archivo de salida |
| `predios` | sí | Listado de predios con `ID_PREDIO` |
| `base_construcciones` | sí | `todas_las_construcciones.parquet` de una corrida del liquidador |
| `reglas` | sí | `"2025"` (tablas que rigen la vigencia 2026) o `"2024"` (vigencia 2025) |
| `comuna_reglas` | no | Comuna cuyos valores se aplican a todos los predios del listado. Vacío = la comuna de cada predio. |
| `comuna_referencia` | no | Otra comuna con la que se liquida solo para comparar (columnas `*_COMUNA_xx`) |
| `factor_catastral` | no | 0,7 por defecto |
| `excluir_modelo` | no | `true` deja fuera los predios con construcciones que iban por modelo |
| `etiqueta_referencia` | no | Nombre de la referencia en las columnas, por ejemplo `VIG2025` → `AVALUO_VIG2025` |
| `etiqueta_nueva` | no | Nombre de la nueva liquidación, por ejemplo `TABLAS_VIG2026` → `AVALUO_TABLAS_VIG2026` |
| `terreno` | sí | Foto de predios de referencia. Columnas: `avaluo` (AVALPRED), `terreno` (VTER), `construccion` (VCONST), `anexos` (VANEXO), `area_terreno` (AREAPRED) |
| `zhf` | no | Export con la ZHF a usar (columna `zhf`). Vacío = la ZHF de la base de construcciones. |
| `actual` | no | Export de predios actual (columna `avaluo`), para mostrar también el avalúo de hoy |
| `export_construcciones` | no | Export de construcciones de la referencia (ID_PREDIO, ACONCONS, PUNTCONS, VALORCONS). Sirve para el valor de cada construcción en la referencia y para detectar mutaciones. |
| `export_anexos` | no | Export de anexos de la referencia (ID_PREDIO, DESTANEX, TIPOANEXO, ACONANEX, VALOANEX) |
| `zona_control` | no | Valor de zona por predio (columna `zona`, por ejemplo ZHG_2024). Sirve para validar que terreno = zona × área × factor. |
| `salida` | no | Carpeta del Excel (`output/reliquidacion` por defecto) |

Los archivos pueden ser parquet, Excel o texto separado por `|`, que es el formato de los export de Sistemas.

## El resultado

`RELIQUIDACION_<nombre>_<AAAAMMDD_HHMM>.xlsx`, con estas hojas:

| Hoja | Contenido |
|---|---|
| RESUMEN_RANGOS | Predios y avalúos por rango de variación (baja más de 50 %, …, sube más de 30 %), separando con y sin novedad |
| SUBEN_BAJAN | Cuántos suben, bajan o quedan igual (±1 %) |
| RANGOS_SIN_NOVEDAD | Los rangos solo con los predios sin novedad |
| NOVEDADES | Conteo por tipo de novedad |
| PREDIOS | Una fila por predio: avalúo de referencia y nuevo, diferencia, variación, rango, terreno, construcciones y anexos, mutación y validación del terreno. Las filas con novedad salen en amarillo. |
| CONSTRUCCIONES | Una fila por construcción y anexo: datos con que se liquida, ZHF usada y de la base, tabla, valor por m² comercial y catastral, valor nuevo, valor en la referencia, diferencia y novedad |
| REFERENCIA_YA_NO_ESTA | Construcciones y anexos de la referencia que hoy no están iguales |
| EXCLUIDOS_MODELO | Con `excluir_modelo`: los predios que quedaron fuera |
| PARAMETROS | La configuración con que se corrió, para poder repetirla |
| NOTAS | Cómo leer las columnas |

Cómo leer las columnas:

- **Todos los valores son catastrales**, salvo la columna `VM2_COMERCIAL_O_VALOR_UNIDAD`.
- `DIFERENCIA` = nuevo − referencia. `VARIACION_PCT` se calcula sobre la referencia.
- **Parqueaderos T12 (usos 007, 008, 036 y 037):** `VM2_COMERCIAL_O_VALOR_UNIDAD` es el valor total del parqueadero, no un valor por m².
- **Lotes:** los predios sin construcciones quedan con su terreno de referencia, así que su variación es 0.

## Novedades

| Novedad | Cuándo |
|---|---|
| mutación | Una construcción de hoy no está igual en la referencia, o una de la referencia no está igual hoy. Se cruzan por predio + área + puntaje; los anexos por predio + destino + tipo + área. Un cambio de área o de puntaje cuenta como mutación. |
| tipología de la ZHF distinta | La ZHF usada (la de la configuración) tiene otra tipología, los tres últimos dígitos, que la de la base de hoy. La tipología define la tabla. |
| iban por modelo | Construcciones que en ese ejercicio se valoraban con modelo. En 2025 son los usos 001, 028 y 034 con condición 9. Por tabla suelen quedar muy por debajo, porque el valor de modelo era integral (incluía el suelo). |
| especial | Construcción con valor especial en la base, liquidada aquí por tabla |
| sin valor por tabla | La tabla del ejercicio no trae valor para esa combinación |
| terreno no cuadra | El terreno de referencia no es igual a zona × área × factor. Suele pasar en lotes con más de una zona o con un área distinta. |

## Límites

- Los datos físicos (área, puntaje, uso) son los de la base de hoy. Para reproducir otra fecha se cambia la base de construcciones.
- `reglas: "2024"` usa el motor de tablas de 2024. Ese ejercicio liquidaba gran parte de la propiedad horizontal por modelo; aquí todo va por tabla y queda marcado.
- La comuna de `comuna_reglas` se aplica a todo el listado. Si el listado mezcla comunas con tratamientos distintos, se corre una configuración por grupo.
