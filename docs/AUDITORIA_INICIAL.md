# Auditoría inicial — Liquidación vigencia 2027

Fecha de corte: 2026-09-25  
Repositorio auditado: `jlo-cloud/LIQUIDACION-VIG-2027`  
Commit base: `bfb9877170966c1fc11da561e9612c455ff388f0` (`main`)  
Rama local de trabajo: `audit/preliquidacion-2027`

## Dictamen ejecutivo

Estado: **PARCIAL / NO LISTO para preliquidación y liquidación final 2027**.

El repositorio contiene una base valiosa para liquidar construcciones por tablas y por los modelos históricos de 2024 y 2025, generar escenarios y reportar algunas inconsistencias. Sin embargo, todavía no constituye el producto reproducible solicitado a la Subdirección porque:

1. una instalación basada únicamente en `requirements.txt` no puede importar el orquestador;
2. la liquidación final está desactivada en `main.py`, aunque el proceso termina anunciando éxito;
3. no existe un contrato versionado de entradas, columnas y variables;
4. el código excluye expresamente la zona rural del universo de modelos;
5. no hay pruebas automatizadas ni datos mínimos de prueba;
6. no existe el front o visualizador requerido;
7. la base de modelación reproducible y actualizable con puntos muestra no está implementada.

La recomendación es conservar la lógica histórica como referencia y refactorizar por envoltura: primero contratos, validaciones y orquestación; después separar reglas y vigencias. No se deben renombrar las variables existentes. Cuando sea necesario normalizar internamente, se deben usar adaptadores y conservar el nombre oficial en entradas, salidas y diccionario de datos.

## Alcance y evidencia revisada

- Código, notebooks, modelos serializados, tablas y reglas del commit base.
- Inventario de la carpeta compartida de alistamiento:
  - `01_INSUMOS/LIQ_2024` y `01_INSUMOS/LIQ_2025`;
  - `02_ZHF_ZHG`, actualmente vacía;
  - `03_MODELOS_2026`, actualmente vacía;
  - `Asinación de responsabilidades.xlsx`.
- Cronograma `CRONOGRAMA_CONSOLIDADO_CALI_20260921.xlsx`, modificado el 2026-09-24.
- Compilación estática de los 17 módulos Python de `src/`.
- Importación real de `src/main.py` en el Python disponible.
- Inspección de estructura, dependencias, rutas, reglas, modelos `.pkl` y salidas declaradas.

No se ejecutó una liquidación masiva: los 593 MB de insumos operativos declarados en `INSUMOS.md` no están en el clon. Por ello no se certifican cifras, tiempos, cobertura ni equivalencia de resultados.

## Cobertura frente a las obligaciones

| Requisito | Evidencia actual | Estado |
|---|---|---|
| Código base para 2024, 2025 y propuesta 2027 | `escenarios.py` y motores históricos | Parcial: compara reglas sobre una base común; no reproduce liquidaciones históricas completas |
| Orquestador principal | `src/main.py` | Parcial: ejecuta hasta tabla intermedia; la liquidación final está apagada |
| Base de modelación 2024→2025, actualizable con puntos muestra | No hay generador ni contrato de dataset de entrenamiento | No implementado |
| Conservar nombres de variables y dummies históricas | Variables embebidas en `model_liq.py` y en los objetos serializados | Parcial: no hay diccionario/versionado contractual |
| Usos 001, 028 y 034, condición 9 únicamente | `DESTINOS_MODELO_*` y `mask_modelo()` | Implementado en la selección urbana actual |
| Modelo rural de apartamentos | `model_liq.py` limita modelos a comunas ≤ 22 | No implementado; rural excluido explícitamente |
| Lectura de predio, ID, ZHF y coordenadas desde parquet | `tabla_construccion.py` lee exports y conserva `ID_PREDIO`, `ZHF`, `LATITUDE`, `LONGITUDE` | Parcial: selección por patrones y nombres fechados, sin manifiesto de corrida |
| Consolidación con anexos y otros insumos | `tabla_construccion.py`, `Homologacion.py`, `Liquidacion_tablas.py` | Parcial: lógica existente, monolítica y sin pruebas de regresión |
| Reporte de inconsistencias de fuente | `pre_inconsistencias.py` y `post_inconsistencias.py` | Parcial: falta contrato de severidad, sistema responsable y umbral de bloqueo |
| Uso predominante del predio | `uso_principal.py` y `uso_principal_terr.py` | Implementado, no certificado con pruebas |
| Archivos de homologación | Reglas incrustadas como texto/tablas dentro de código | Parcial: deben externalizarse y versionarse sin cambiar sus códigos |
| Visualizador con indicadores, predio y mapas de calor | No hay código de front en el commit | No implementado |
| Preliquidación serializada con comentarios de cambios | Hay parquet y reportes, pero no manifiesto de cambios por corrida | No implementado como producto auditable |

## Hallazgos priorizados

### P0 — bloquean reproducibilidad o aprobación

1. **El entorno declarado no ejecuta el pipeline.** `requirements.txt` solo fija Streamlit, pandas, pyarrow y motores Excel, y además dice corresponder a `src/app_vigencias.py`, archivo que no existe. La importación real de `main.py` falla primero por `dbfread`; también faltan del manifiesto `numpy`, `tqdm`, `joblib`, `dill`, `cloudpickle`, `scikit-learn` y `xgboost`.

2. **El orquestador no ejecuta la liquidación final.** `main.py` importa `liquidacion_completa`, pero el bloque que la invocaba está comentado. El flujo guarda `output/LIQUIDACION_TABLAS.parquet` y después imprime “Proceso completado exitosamente”. Esto puede confundir una preliquidación parcial con un producto final.

3. **Los fallos no siempre bloquean la corrida.** Si la generación de escenarios falla, `main.py` solo imprime una advertencia. En el manejador superior, una excepción fatal se captura y se imprime sin devolver un código de salida distinto de cero. Un servidor, tarea programada o CI podría registrar como exitosa una corrida fallida.

4. **La liquidación final conserva lógica fechada y excepciones manuales.** `Liquidacion_final.py` usa nombres 2025/2026, rutas con fecha, un predio de depuración y listas extensas de IDs marcados manualmente. Para 2027 estas reglas deben ser entradas versionadas con origen, justificación, vigencia y aprobador; no constantes dentro del motor.

5. **Rural no está cubierto por los modelos.** `model_liq.py` establece `COMUNA_URBANA_MAXIMA = 22` y documenta que rural todavía no se liquida por tabla ni modelo. El modelo rural de apartamentos requiere dataset, entrenamiento, validación y ruta de inferencia propios.

6. **No hay pruebas ni baseline certificado.** No existen `tests/`, CI, fixtures ni una muestra dorada que compare conteos y valores contra una corrida aprobada. La compilación estática fue correcta, pero no certifica resultados.

### P1 — riesgo alto de errores y mantenimiento

7. **Las funciones centrales son demasiado grandes.** `model_liq.py` tiene 2.397 líneas; `ejecutar_modelos()` ocupa aproximadamente 850. `Liquidacion_tablas.py` tiene 1.866 líneas en una sola función y `Liquidacion_final.py` 977. Esto dificulta probar reglas de forma aislada.

8. **Duplicación entre vigencias.** `Liquidacion_tablas_2025.py` y `Liquidacion_tablas.py` difieren en 876 inserciones y 938 eliminaciones, pero conservan la misma estructura extensa. Las correcciones pueden quedar aplicadas en una vigencia y no en otra.

9. **Entradas seleccionadas por rutas y patrones, no por manifiesto.** El pipeline depende del directorio de ejecución, patrones `glob` y archivos fechados. Falta registrar por corrida la ruta, tamaño, hash, vigencia, fecha de corte y esquema de cada insumo.

10. **Los modelos serializados no tienen ficha reproducible completa.** Los `.pkl` dependen de scikit-learn y, en 2024, de XGBoost; dos pipelines incluyen referencias a `__main__`. Faltan versiones de entrenamiento, métricas, hash del dataset, lista ordenada de variables y prueba de carga/predicción.

11. **Las reglas están repartidas.** Parte vive en `Reglas.xlsx`, parte en arreglos y condiciones Python, y parte en comentarios. La fuente de verdad debe ser inequívoca y validada antes de liquidar.

### P2 — eficiencia y operación

12. **El progreso no representa el flujo real.** La barra se crea para siete pasos, se actualiza para cinco y se cierra antes de los escenarios. La lista de archivos generados se calcula antes del paso opcional, por lo que puede omitir sus productos.

13. **Salida y temporales no están aislados por corrida.** Los nombres fijos pueden sobrescribirse y dificultan comparar iteraciones de sensibilidad. Cada ejecución debe usar un `run_id` inmutable y un manifiesto.

14. **Exceso de trazas y código de diagnóstico dentro del motor.** Hay impresiones de data types, conteos y un ID concreto. Deben reemplazarse por logging estructurado y métricas resumidas.

## Arquitectura objetivo mínima

```text
CLI / front local
    -> preflight de insumos y esquema
    -> construir base canónica (sin renombrar variables oficiales)
    -> homologar + uso predominante
    -> motor de reglas por vigencia
    -> motor de modelos por familia (urbano / rural)
    -> cálculo predial y controles contables
    -> inconsistencias con causa y responsable
    -> paquete versionado de preliquidación
    -> visualizador de sensibilidad
```

El `main` debe limitarse a orquestar etapas con entradas/salidas explícitas. Cada etapa debe devolver métricas y fallar si incumple su contrato. Las reglas de negocio no deben depender de la interfaz.

## Secuencia recomendada de mejora

1. Congelar un baseline de entrada y salida aprobada; calcular hashes y conteos.
2. Crear un entorno reproducible completo y una prueba de importación.
3. Definir contratos de columnas, tipos y llaves sin cambiar nombres existentes.
4. Convertir `main.py` en orquestador con `run_id`, preflight, códigos de salida y manifiesto.
5. Extraer configuración por vigencia y homologaciones; conservar motores históricos como adaptadores.
6. Crear pruebas unitarias de reglas y pruebas de regresión contra el baseline.
7. Construir la base de modelación versionada y la actualización de puntos muestra.
8. Incorporar y validar el modelo rural de apartamentos.
9. Activar la liquidación final solo después de pasar reconciliaciones y aprobación funcional.
10. Construir el visualizador sobre productos versionados, no sobre lógica duplicada.

## Criterios mínimos de aceptación de una corrida

- entorno recreado desde cero;
- manifiesto de insumos con hashes y esquemas;
- cero cambios de nombres de variables oficiales;
- unicidad y cobertura de `ID_PREDIO` reportadas;
- conteos antes/después de cada cruce;
- inconsistencias clasificadas por causa y equipo responsable;
- cobertura por tabla/modelo, zona y condición;
- reconciliación de avalúo comercial y catastral;
- comparación contra baseline dentro de tolerancias aprobadas;
- código de salida distinto de cero ante un bloqueo;
- paquete de corrida inmutable con parámetros, comentarios y resultados.

## Límites de esta auditoría

La compilación de Python pasó. La importación del orquestador falló por dependencia ausente. No se descargaron los insumos masivos ni se ejecutaron modelos o liquidaciones; por tanto, el resultado funcional permanece **NO CERTIFICADO** hasta contar con una corrida controlada y un baseline aprobado.
