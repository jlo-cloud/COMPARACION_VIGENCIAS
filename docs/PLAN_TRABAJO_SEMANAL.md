# Plan de trabajo semanal — Brayan y Jennifer

Fecha de preparación: 2026-09-25  
Primer seguimiento: lunes 2026-09-28

Este plan toma las fechas del cronograma consolidado y prioriza el producto reproducible solicitado. Los nombres de variables existentes no se modificarán.

## Fechas rectoras tomadas del cronograma

| Actividad del cronograma | Inicio | Fin | Implicación para el plan |
|---|---:|---:|---|
| Analizar los métodos de liquidación por tablas de valor | 1 ago 2026 | 12 dic 2026 | La auditoría y las pruebas de reglas deben quedar cerradas antes de la corrida final |
| Programación de la preliquidación y reporte de inconsistencias | 1 ago 2026 | 12 dic 2026 | El orquestador reproducible es el frente principal de Brayan y Jennifer |
| Repositorio estructurado de tablas de valor | 1 ago 2026 | 15 oct 2026 | Primer hito técnico obligatorio y de recuperación inmediata |
| Consolidar la programación de los métodos de liquidación | 1 nov 2026 | 30 nov 2026 | En noviembre debe existir una ejecución integrada de las tres vigencias |
| Herramienta de visualización y revisión | 1 nov 2026 | 30 nov 2026 | El visualizador debe consumir productos versionados de la preliquidación |
| Análisis de sensibilidad físico, cartográfico y económico | 1 nov 2026 | 30 nov 2026 | Debe dejar trazabilidad de cada ajuste y permitir reliquidar |
| Proyección de escenarios comercial y catastral | 1 nov 2026 | 15 dic 2026 | Los escenarios deben mantenerse hasta después del cierre de sensibilidad |
| Entrega de insumos económicos a Sistemas | 10 dic 2026 | 11 dic 2026 | Fecha de congelamiento de tablas, modelos y valores especiales |
| Generación o actualización de valores de la base catastral | 12 dic 2026 | 18 dic 2026 | Ventana de liquidación con los insumos definitivos |
| Control de calidad y aprobación de avalúos | 18 ene 2027 | 25 ene 2027 | Cierre final y paquete aprobado |

Al corte del archivo, las actividades analíticas de métodos, preliquidación y repositorio de tablas aparecen con **0 % de avance**. Por ello las primeras tres semanas del plan son de recuperación y deben producir evidencia ejecutable, no únicamente documentos.

| Semana / corte | Trabajo principal | Producto verificable | Responsable principal | Dependencia |
|---|---|---|---|---|
| 28 sep–2 oct | Revisar auditoría, dibujar flujo actual y objetivo, acordar alcance 2024/2025/2027 y congelar diccionario de variables | Acta de decisiones, flujograma y matriz de insumos/variables | Brayan + Jennifer | Acceso a insumos y una corrida histórica aprobada |
| 5–9 oct | Completar entorno reproducible, preflight y manifiesto de entradas; definir muestra dorada | Instalación limpia, comando único y reporte de validación de insumos | Brayan | Archivos completos de Sistemas |
| 12–15 oct | Consolidar repositorio versionado de tablas y homologaciones | Paquete de tablas/reglas con hash, vigencia y validaciones; cumple hito del 15 oct | Jennifer + Brayan | Tablas aprobadas y responsables de cada fuente |
| 19–23 oct | Diseñar base canónica de modelación 2024→2025 sin renombrar variables; incluir actualización de puntos muestra | Dataset versionado, diccionario y reporte de cobertura | Brayan | Puntos muestra y variables históricas |
| 26–30 oct | Pruebas de reglas, uso predominante, anexos y reportes de inconsistencias | Suite de regresión y catálogo de causas/responsables | Brayan + Jennifer | Baseline aceptado |
| 2–6 nov | Refactorizar `main` como orquestador; separar configuración por vigencia | Ejecución por etapas, `run_id`, códigos de salida y manifiesto de corrida | Brayan | Contratos y pruebas previas |
| 9–13 nov | Integrar modelos urbanos y preparar interfaz del modelo rural de apartamentos | Prueba de inferencia, cobertura de usos 001/028/034 condición 9 y diseño rural | Brayan + equipo de Modelos | Modelos, variables y puntos muestra de John/Yuliana |
| 16–20 nov | Generar preliquidación controlada y primera versión del visualizador | Indicadores, detalle por predio, inconsistencias y mapa base | Brayan + Jennifer | Salida versionada del motor |
| 23–30 nov | Sensibilidad integral y cierre del hito de consolidación | Escenarios 2024/2025/2027, comparación y acta de ajustes; cumple hitos del 30 nov | Brayan + Jennifer | ZHF/ZHG y modelos ajustados |
| 1–4 dic | Congelar candidato de entrega económica y documentar cambios de insumos | Paquete candidato con comentarios, hashes y manual de ejecución | Brayan + Jennifer | Aprobación de sensibilidad |
| 7–11 dic | Entregar insumos económicos a Sistemas | Tablas, modelos, valores especiales y manifiesto; cumple hito 10–11 dic | Brayan + Jennifer | Aprobación de responsables funcionales |
| 12–18 dic | Ejecutar y reconciliar la liquidación de la base | Resultados finales de corrida, controles y pendientes; cumple hito 12–18 dic | Brayan + Jennifer | Export definitivo de Sistemas |
| 18–25 ene 2027 | Control de calidad y aprobación de avalúos | Acta de aprobación y paquete final inmutable | Equipo completo | Liquidación validada |

## Agenda del seguimiento semanal

Duración sugerida: 30 minutos.

Cortes propuestos: **28 sep; 5, 12, 19 y 26 oct; 2, 9, 16, 23 y 30 nov; 7 y 14 dic de 2026; 18 y 25 ene de 2027**. El corte del 14 de diciembre debe realizarse durante la ventana de liquidación, no después de terminarla.

1. Hito comprometido vs. entregado, con enlace o ruta.
2. Métricas: predios leídos, liquidados, inconsistentes y sin regla.
3. Cambios de insumos/modelos desde la corrida anterior.
4. Bloqueos y responsable de resolverlos.
5. Decisiones que requieren aprobación funcional.
6. Compromiso y evidencia esperada para la semana siguiente.

## Entregables del primer seguimiento — 28 de septiembre

- auditoría inicial revisada;
- flujograma actual y flujo objetivo acordados;
- responsable y fuente de cada insumo;
- lista oficial de variables que no se pueden renombrar;
- definición de los usos 001, 028 y 034 con condición 9;
- alcance y datos disponibles para el modelo rural de apartamentos;
- identificación de una corrida histórica que servirá como baseline;
- decisión sobre qué significa “liquidación 2024, 2025 y 2026”: reproducción histórica o aplicación de reglas históricas sobre una base común.

## Semáforo inicial

- Verde: clon aislado, ramas preservadas, motores históricos presentes, tablas y reglas livianas disponibles.
- Amarillo: homologación, uso predominante, inconsistencias y comparación de vigencias existen pero no tienen pruebas de regresión.
- Rojo: entorno incompleto, liquidación final desactivada, rural sin modelo, front ausente y corrida integral no certificada.
