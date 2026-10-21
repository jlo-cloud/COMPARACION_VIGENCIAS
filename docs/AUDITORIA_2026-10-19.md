# Auditoría del liquidador — 19/10/2026

Revisión hecha por ingeniería inversa: se leyó el código y se contrastó con la especificación de `input/Reglas.xlsx`, con los resultados de la corrida certificada del 01/10/2026 y con el export oficial de predios. Las validaciones se probaron con casos buenos y casos dañados.

**Base de la revisión:**
- **Código:** rama `feature/codigo-base-2027`, commit `2a5061d`.
- **Liquidación por construcción:** `LIQUIDACION_TABLAS.parquet`, con 900.888 construcciones de 727.863 predios.
- **Resultado por predio:** `PREDIOS_LIQUIDACION.parquet`, con 130.531 predios.
- **Scripts de la auditoría:** `scripts_sesion/auditoria_reglas_tablas.py` y las consultas que se describen en cada hallazgo.

---

## Estado de los hallazgos al 20/10/2026

| Hallazgo | Estado | Cómo quedó |
|---|---|---|
| C1. Solo 7 comunas | **Corregido** | Las comunas se eligen antes de liquidar (interfaz o `comunas_liquidar`). El filtro fijo desapareció y la base se recorta al cargar los exports (`src/comunas.py`). |
| C2. Tablas sin valores marcadas como "Liquidado" | **Corregido en el proceso**; las tablas siguen pendientes (duda 5) | La prevalidación (paso 0B) dice, por comuna, qué tablas faltan y qué predios afectan. En una liquidación detiene la corrida. |
| A1. Marca "Liquidado" con todo en $0 | **Corregido** | Nueva marca "Sin valor de construcción" |
| A2. Variación entre vigencias oficiales | **Corregido** | `VAR_AVALUO` compara el avalúo calculado con el vigente; la comparación anterior queda en `VAR_VIGENTE_VS_ANTERIOR` |
| A3. `OBSERVACION` sobrescrita | **Corregido** | `CATEGORIA_IGUAL_VIGENTE` e `IGUAL_AL_VIGENTE` por un lado; `OBSERVACION` por el otro |
| A4. "Aprobado" = igual al vigente | **Corregido** | `ESTADO_PRELIQUIDACION` (CUMPLE / CUMPLE CON OBSERVACIONES / NO CUMPLE) con `QUE_NO_CUMPLE`. El Excel de revisión trae las hojas NO_CUMPLEN y CUMPLEN. |
| A5. Mismo archivo en dos insumos | **Corregido** | La validación previa compara la huella de los archivos |
| A6. Componentes que no suman el avalúo | **Corregido** | Cada componente se reporta solo si entra; el avalúo es la suma de los componentes redondeados |
| M1. Listas de predios en el código | **Corregido** | Ahora es un insumo opcional (`predios_en_revision`) |
| M2. Terreno vigente con IVP | Duda 9 | Se protegió la división por área 0 |
| M3. Terreno completo en mixtos | Duda 11 | — |
| M4. Modelos 2025 en 2027 | Duda 4 | La prevalidación lo informa por comuna |
| M5. Uso 017 sin tipología | **Corregido** | 017 entra en las reglas industriales (031/032/033) |
| B2, B3, B4 | **Corregidos** | Rango 7, `print` de depuración y grupo de comunas (7C / 10C / SIN GRUPO) |
| B1. Columnas con "2026" | Pendiente | Renombrarlas cambia el formato que leen otros procesos; se deja para una entrega coordinada |
| Tipos y unidades de las variables de los modelos (solicitud 20/10) | **Nuevo control** | `contrato_modelos.py` verifica tipo, unidad y rango antes de cada predicción. En las comunas 04 y 12 encontró `INFLUENCIA_VIA` en texto (convertida), 2 construcciones con valor de suelo 0, 1 con 0 pisos y 1 longitud fuera de Cali. |
| B5. Pruebas del motor | Avance | Se agregaron pruebas del cálculo del avalúo, de la validación por predio y de la prevalidación (24 en total) |

Las decisiones de negocio quedaron en [DUDAS_PENDIENTES.md](DUDAS_PENDIENTES.md).

---

## Resumen

| Severidad | Hallazgos |
|---|---|
| Crítico | 2 |
| Alto | 6 |
| Medio | 5 |
| Bajo | 5 |
| Ambigüedades sin resolver | 11 |

**Funciona bien:**
- **Asignación de tabla:** cumple `Reglas.xlsx` en el 100,00 % de las construcciones evaluables (527.452 de 527.454).
- **Control de calidad:** detiene la corrida cuando hay errores.
- **Inconsistencias posteriores:** el reporte explica el 100 % de las construcciones que quedan en $0.
- **Reglas de 2024 y 2025:** reproducen las vigencias oficiales (99,4 % y 96,9 %).

**No funciona como debería:**
- **Cobertura:** la liquidación final solo cubre 7 comunas.
- **Valores faltantes:** cuatro tablas del consolidado vienen sin valores y dejan 21.101 predios en $0 marcados como "Liquidado".
- **Validación de la preliquidación:** compara contra el avalúo vigente, no contra la preliquidación.

---

## Críticos

### C1. La liquidación final solo deja 7 comunas

- **Dónde:** `src/Liquidacion_final.py:185`

  ```python
  df_predio = df_predio[df_predio['COMUNA'].isin(['01','03','09','10','11','12','22'])]
  ```

- **Evidencia:** el motor de tablas asigna tabla y valor en toda la ciudad (727.863 predios, comunas 01 a 22 y rurales 51 a 65). El resultado por predio solo trae 130.531 predios de las comunas 01, 03, 09, 10, 11, 12 y 22. La preliquidación de marzo (vigencia 2026) cubría exactamente esas 7 comunas (129.940 predios), así que el filtro viene del script de 2026.
- **Contradice:**
  - `Reglas.xlsx`, que define 17 comunas para 2027 (grupo 10C: 1, 7, 9, 10, 11, 12, 14, 15, 20, 21; grupo 7C: 2, 3, 4, 8, 17, 19, 22);
  - `tabla_construccion.py`, que por decisión incluye además las comunas 05, 06, 13, 16 y 18 en el grupo 10.
- **Efecto:** el `.txt` y el parquet de resultado de la vigencia 2027 dejan por fuera 15 comunas.
- **Acción:** definir el alcance (ver ambigüedad AMB-1) y llevar el filtro al manifiesto como parámetro, en lugar de tenerlo fijo en el código.

### C2. Cuatro tablas del consolidado no traen valores: construcciones en $0 marcadas como "Liquidado"

- **Evidencia:** en las 7 comunas liquidadas, el 100 % de estas construcciones queda en $0:

  | Tabla | Construcciones en $0 |
  |---|---|
  | T10 anexos | 26.549 |
  | T12 parqueaderos | 20.536 |
  | T7 servicios | 1.725 |
  | T8 iglesias | 289 |
  | Especiales | 239 |

  En el resto de la ciudad pasa lo mismo.
- **Efecto:** **21.101 predios quedan con avalúo $0.** El 96 % son unidades en propiedad horizontal cuyo uso principal es garaje o depósito. Hoy suman $0,83 billones de avalúo vigente, y de ellos 20.862 salen con `MARCA_LIQUIDACION = "Liquidado"`.
- **Causa:** el consolidado `Tablas_Valor_Consolidado_V1_20260916.xlsx` no trae esas tablas. Esto ya se conocía, pero el proceso no lo bloquea ni lo hace visible en el resultado por predio.
- **Acción:**
  1. Completar el consolidado; es un pendiente de negocio.
  2. Que la liquidación se detenga, o al menos advierta en el paso 0, cuando una tabla asignada no existe en el consolidado.
  3. Corregir la marca (ver A1).

---

## Altos

### A1. `MARCA_LIQUIDACION` no detecta predios con todas sus construcciones en $0

- **Dónde:** `Liquidacion_final.py:791-827`.
- La marca "Liquidación parcial" exige `CONST_CON_VALOR > 0`. Un predio con todas sus construcciones en $0 cae en el valor por defecto, "Liquidado". Por eso los 20.862 predios de C2 aparecen como liquidados.
- **Acción:** agregar la categoría "Sin valor de construcción" cuando `TOTAL_CONST > 0` y `CONST_CON_VALOR == 0`.

### A2. La variación del resultado no usa el avalúo calculado

- **Dónde:** `Liquidacion_final.py:699-707`.
- `VAR_AVALUO`, `VAR_ABSOLUTA`, `BAJO_AVALUO` y `RANGO_AVALUO` comparan `AVALPRED` (el avalúo vigente del export) contra `AVALPRED_2025`. Es decir, miden el cambio entre dos vigencias oficiales, no el de la nueva liquidación.
- **Ejemplo:** el predio con avalúo vigente de 157.500.000 muestra +25,5 %, que es su cambio de 2025 a 2026, no el de la liquidación 2027.
- **Acción:** calcular la variación con `AVALUO_2026_CAT` (el calculado) frente al vigente, y mantener la otra solo si se renombra.

### A3. La columna `OBSERVACION` se sobrescribe

- **Dónde:** `Liquidacion_final.py:639` y `677`.
- Primero guarda la categoría de aprobación y luego se reemplaza por otras observaciones, con "APROBADO" como valor por defecto.
- **Evidencia:** **100.047 predios dicen `OBSERVACION = APROBADO` y `ESTADO = NO_APROBADO`.**
- **Acción:** usar dos columnas distintas (`CATEGORIA_APROBACION` y `OBSERVACION_TERRENO`).

### A4. La validación de la preliquidación compara contra el avalúo vigente

- `ESTADO = APROBADO` significa que el avalúo calculado coincide en ±$1.000 con el avalúo vigente del export, con terreno, construcción y anexos iguales. Para la vigencia 2027, con tablas nuevas, eso quiere decir "no cambió", no "está bien calculado". Hoy hay 26.945 predios aprobados y 103.586 no aprobados.
- Contra la preliquidación de referencia (marzo) se calcula `DIF_PRELIQ`, pero no entra en el estado: 103.870 de 129.638 predios difieren en más de $1.000. Ya se explicó que la diferencia viene de las tablas V1 incompletas (ver `COMPARACION_MOTOR_vs_PRELIQUIDACION_MARZO_01102026.xlsx`).
- **Conclusión:** la validación de la preliquidación *funciona como reporte*, pero el estado APROBADO no valida la liquidación 2027. Ver la ambigüedad AMB-8.

### A5. La validación previa (preflight) no revisa el contenido, y nadie detecta el mismo archivo en dos insumos

Se probó `--validate-manifest` con estos casos:

| Caso | Preflight | Control de calidad (paso 0A) |
|---|---|---|
| Manifiesto correcto | OK (0) | — |
| Archivo inexistente | Rechaza (2) | — |
| Archivo vacío | Rechaza (2) | — |
| Extensión equivocada | Rechaza (2) | — |
| Archivo equivocado (ZHG en lugar de predios) | **Acepta (0)** | Lo detecta: ERROR, código 3 |
| **El mismo archivo como predios actuales y anteriores** | **Acepta (0)** | **No lo detecta: 0 errores** |

Con el mismo archivo en los dos campos, la "ZHF anterior" sería igual a la actual y toda comparación entre vigencias daría cero cambios sin que nada avise.

- **Acción:** que el preflight compare la huella (hash) de los archivos y rechace un mismo archivo en dos insumos distintos. También, que el paso 0A advierta si la entrega anterior es idéntica a la actual.

### A6. Terreno, construcción y anexos no suman el avalúo

- **Regla oficial:** en el export oficial, `AVALPRED = VTER + VCONST + VANEXO` en el 99,88 % de los 792.205 predios.
- **Lo que hace el motor:**
  - **Predios integrales e informales:** el avalúo se calcula sin terreno, pero `VTER_2026_CAT` sale con valor. En 136 predios la diferencia pasa de $1.000 y llega a $6.415 millones.
  - **Redondeo:** se redondea a miles cada componente y también el total por separado (`Liquidacion_final.py:575-578`). Por eso 878 predios más difieren en hasta $1.000.
- **Acción:**
  1. Poner `VTER_2026_CAT = 0` cuando el terreno no entra al avalúo.
  2. Calcular el total como suma de los componentes ya redondeados, o definir la regla (ver AMB-7).

---

## Medios

### M1. Listas de predios escritas en el código desde la vigencia 2026

- **Dónde:** `Liquidacion_final.py:888-936`.
- Son tres listas: `id_hoyo` (36 predios, "hoyo y piloto"), `cambio_const` (unos 330) y `cambio_avaluo` (20). Sacan esos predios de la hoja APROBADOS.
- Son casos de la revisión de 2026 que no se sabe si aplican a 2027.
- **Acción:** pasarlas a un insumo del manifiesto o quitarlas.

### M2. El terreno 2027 es el terreno vigente, con su IVP

- **Dónde:** `Liquidacion_final.py:176-179`.
- La fórmula es `VALOR_M2_SUELO = VALOTERR / AMETTERR / 0,7` y `VALOTERR_COM = AMETTERR × VALOR_M2_SUELO`. El resultado catastral vuelve a ser el `VALOTERR` actual, que ya incluye el IVP de 2026. Solo cambia el terreno de los predios especiales (hoja `Terrenos_especiales`).
- Si `AMETTERR = 0`, la división da infinito o NaN.
- Ver AMB-6.

### M3. En los predios mixtos se suma el terreno completo

- **Dónde:** `Liquidacion_final.py:427-432`.
- La proporción de terreno quedó desactivada (`* 1`). Un predio MIXTO, con parte integral (modelo o parqueadero) y parte por tabla, suma todo su terreno además del valor integral, que ya incluye suelo.
- **Afecta:** 204 predios MIXTO, de los cuales 63 tienen la marca "Liquidado mixto".

### M4. Los modelos se tratan distinto en la liquidación y en los escenarios

- En la liquidación principal, la propiedad horizontal por modelo (usos 001, 028 y 034 con condición 9) se valora con los **modelos 2025**: 22.931 construcciones en las 7 comunas, todas con valor.
- En el escenario ACTUAL (`escenarios.py:199-214`), esas mismas construcciones quedan en $0 con la marca "sin modelo en esta vigencia".
- Ver AMB-2.

### M5. Dos construcciones no siguen la regla

- **Una construcción de uso 017 con tipología 013:** la regla dice T4_INDUSTRIAL_031 y el motor asignó T4_INDUSTRIAL_032. La causa es una condición al final de la lista (`Liquidacion_tablas.py:487`) que manda todo el uso 017 a la 032 sin mirar la tipología.
- **Un anexo** con destino que no está en la lista de anexos de las reglas quedó "SIN TABLA".

---

## Bajos

- **B1. Nombres de columnas:** las columnas dicen 2026 en una liquidación de vigencia 2027: `AVALUO_2026_CAT`, `VTER_2026_COM`, `ESPECIAL_2026`, `AVALPRED_2025`, entre otras. Se presta a confusión al leer el resultado.
- **B2. Orden de los rangos:** en `RANGO_AVALUO` la etiqueta `(Entre -5% y 0%)` no tiene el número 7, así que el orden alfabético de los rangos se rompe.
- **B3. Restos de depuración e identificador de terreno:**
  - quedó un `print` de depuración para un predio puntual (`Liquidacion_final.py:499-500`);
  - `ID_TERR` usa `NPN[1:21]` (20 dígitos), mientras que en otros módulos el terreno es `NPN[:21]`. Es consistente dentro del módulo, pero no entre módulos.
- **B4. Grupos de comunas:** `GRUPO_COMUNAS` etiqueta como "3 Y 22" a cualquier comuna que no esté en 1, 9, 10, 11, 12.
- **B5. Pruebas automáticas:** las 17 pruebas cubren contrato, calidad, publicación, reportes y reliquidación. **No hay pruebas del motor de tablas ni de `Liquidacion_final`**, que es donde están todos los hallazgos de arriba.

---

## Lo que se verificó y está bien

| Qué | Cómo | Resultado |
|---|---|---|
| Asignación de tabla | Se reimplementó `Reglas.xlsx` de forma independiente (zona primero, luego estrato, luego estrato 6; tipologías 021-023 y 031-033; tablas fijas; anexos) y se comparó con el motor | 527.452 de 527.454 iguales (100,00 %); las 2 diferencias están en M5 |
| Calidad de insumos (paso 0A) | Insumo equivocado, y el `main` con `calidad_bloqueante` | Detecta el error y la corrida se detiene |
| Preflight | Archivo inexistente, vacío, con extensión equivocada | Los rechaza con código 2 |
| Inconsistencias posteriores | Suma de causas contra las construcciones en $0 | 364.329 de 364.329 explicadas |
| Reglas 2024 y 2025 | Escenarios contra los exports oficiales | 99,4 % y 96,9 % exactos |
| Reproducibilidad | Dos corridas completas | 0 predios distintos |
| Ejecutable | `--self-test` y `--reliquidar` | OK; la reliquidación da igual que el código |
| Redondeo a miles del avalúo calculado | Resultado por predio | 100 % múltiplos de 1.000 |
| Avalúos negativos o vacíos | Resultado por predio | 0 negativos, 0 vacíos (sí hay $0, ver C2) |

---

## Ambigüedades que no se pueden resolver desde el código

Requieren una decisión del equipo de valoración o de catastro.

| # | Pregunta | Qué hace hoy el código | Por qué no se puede decidir solo |
|---|---|---|---|
| AMB-1 | ¿Qué comunas liquida la vigencia 2027: 7, 17 o 22? ¿Y la zona rural? | Asigna tabla en las 22 urbanas y en las rurales 51-65, pero el avalúo final sale solo para 7 | `Reglas.xlsx` dice 17; `tabla_construccion.py` agrega 5 "por decisión"; el filtro final dice 7; las reglas no cubren lo rural |
| AMB-2 | La propiedad horizontal (001, y 028/034 con condición 9) no está en `Reglas.xlsx`. ¿Modelo 2025, tabla o nada? | Liquidación: modelo 2025. Escenario ACTUAL: $0 | No hay modelo 2027 ni regla de tabla |
| AMB-3 | Uso 003 con condición 8/9 y comercial o industrial con condición 8/9 | Van a MODELO (7.908) o a tabla | Las reglas dicen "diferente de 8 y 9" y no dicen qué hacer con el resto (8.078 construcciones) |
| AMB-4 | Usos 020/023 (especiales, 3.070), 043 y 064 | Especiales sin valor; 043 a T11; 064 sin tabla | No están en las reglas; el archivo de especiales es de la actualización 2025 (03/03/2026) y `LIQUIDAR_CON_ESPECIALES = False` |
| AMB-5 | Uso 003 con tipología fuera de 011-016 | Usa el estrato, como el residencial | Las reglas solo dan la excepción para el residencial |
| AMB-6 | Terreno 2027: ¿el vigente con IVP, una zona nueva o la zona 2024? | El vigente / 0,7 (incluye el IVP de 2026) | No hay tabla de zonas 2027 en los insumos |
| AMB-7 | Redondeo: ¿a miles por componente, del total, o sin redondear como el export oficial? | Cada componente y el total, por separado | El export oficial no redondea (solo el 6,8 % de los avalúos son múltiplos de 1.000) y suma exacto |
| AMB-8 | ¿Qué es "APROBADO" en la preliquidación 2027? | Igual al avalúo vigente ±$1.000 | Podría ser igual a la preliquidación de referencia, sin inconsistencias, o dentro de un rango de variación |
| AMB-9 | Terreno de los predios mixtos | Completo (proporción desactivada) | No se sabe si la desactivación fue intencional |
| AMB-10 | Comunas 05, 06, 13, 16 y 18 | Se liquidan con los valores del grupo de 10 comunas | El código lo marca como DECISIÓN pendiente de una tabla propia |
| AMB-11 | Listas de predios fijas de 2026 (M1) | Los sacan de APROBADOS | No se sabe si siguen vigentes |

---

## Recomendaciones, en orden

1. **Definir AMB-1 y AMB-2.** Cambian el resultado de cientos de miles de predios. Después, llevar el filtro de comunas al manifiesto.
2. **Completar T7, T8, T10 y T12** en el consolidado. Mientras tanto:
   - hacer que el paso 0 avise cuando falta una tabla asignada;
   - corregir la marca A1 para que esos predios no salgan como "Liquidado".
3. **Corregir A2, A3 y A6.** Son de código, no de negocio, y hoy hacen que el resultado diga algo distinto de lo que es.
4. **Rechazar en el preflight un mismo archivo en dos insumos** (A5).
5. **Pasar las listas fijas (M1) a un insumo** y decidir AMB-6 a AMB-9.
6. **Agregar pruebas del motor** con un pequeño conjunto de predios de referencia ("muestra dorada") que cubra cada rama de las reglas y del cálculo del avalúo.
