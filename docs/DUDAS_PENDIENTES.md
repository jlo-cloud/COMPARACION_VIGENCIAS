# Dudas pendientes para valoración y catastro

Son decisiones que el código no puede tomar solo. Cada una dice qué hace hoy el liquidador y dónde se cambia cuando haya respuesta. Salen de la auditoría del 19/10/2026 ([AUDITORIA_2026-10-19.md](AUDITORIA_2026-10-19.md)); las fallas de código de esa auditoría ya quedaron corregidas.

| # | Pregunta | Qué hace hoy | Dónde se cambia |
|---|---|---|---|
| 1 | ¿Qué comunas se liquidan en la vigencia 2027? | Se eligen antes de cada corrida. Por defecto vienen marcadas las 17 de `Reglas.xlsx`. La prevalidación dice si cada comuna elegida se puede liquidar. | Interfaz ("Comunas a liquidar") o parámetro `comunas_liquidar` del manifiesto |
| 2 | Las comunas 05, 06, 13, 16 y 18 no están en `Reglas.xlsx`. ¿Se liquidan con los valores del grupo de 10 comunas o necesitan tabla propia? | Si se eligen, se liquidan con el grupo 10C y la prevalidación lo marca como advertencia | `src/comunas.py` (`INCLUIR_COMUNAS_FALTANTES`) |
| 3 | ¿Se liquida la zona rural (corregimientos 51 a 65)? | No tiene regla de tablas: si se elige, la prevalidación la marca NO APTA | `Reglas.xlsx` y `src/comunas.py` |
| 4 | La propiedad horizontal (uso 001, y 028/034 con condición 9) no está en `Reglas.xlsx`. ¿Modelo 2025/2024, tabla o nada? | Se valora con el modelo de la comuna (2025 en 01, 03, 09, 10, 11, 12, 22; 2024 en 02, 04, 08, 17, 19); en las demás comunas no hay modelo y la prevalidación lo marca NO APTA | `src/model_liq.py` y `src/comunas.py` |
| 5 | ¿Cuándo se entregan las tablas T7 (servicios), T8 (iglesias) y T10 (anexos)? | El consolidado V1 no las trae: esas construcciones quedan en $0 y la prevalidación las marca | `Tablas_Valor_Consolidado` (input/tablas) |
| 6 | ¿Se aprueban los valores de parqueaderos (T12)? Hoy son los de 2025. | Apagados: quedan en $0 y la prevalidación los marca | Casilla "Liquidar parqueaderos" o parámetro `liquidar_parqueaderos` |
| 7 | Especiales (usos 020 y 023): ¿con qué valor se liquidan? | En $0 (el Excel de especiales es el de la actualización 2025 y está apagado) | `src/liquidar_avaluo_2026.py` (`LIQUIDAR_CON_ESPECIALES`) |
| 8 | Uso 003 con condición 8/9, y comercial o industrial con condición 8/9: ¿qué tabla? | Van a modelo o a la tabla del uso; `Reglas.xlsx` solo dice "diferente de 8 y 9" | `src/Liquidacion_tablas.py` |
| 9 | Terreno 2027: ¿el vigente (incluye el IVP de 2026), una zona nueva o la zona 2024? | El vigente llevado a comercial (VALOTERR / 0,7) | `src/Liquidacion_final.py`, sección de terrenos |
| 10 | Redondeo: ¿a miles por componente, del total, o sin redondear como el export oficial? | Cada componente a miles y el avalúo como su suma (cuadra como en el export oficial) | `src/Liquidacion_final.py`, "Catastral = comercial x 0,7" |
| 11 | Predios mixtos: ¿terreno completo o en proporción a la parte no integral? | Completo (la proporción está desactivada en el código original) | `src/Liquidacion_final.py`, sección de mixtos |
| 12 | ¿Qué variación frente al avalúo vigente se considera para revisar? | Más de 50 % queda como observación (no bloquea) | `src/validacion_preliquidacion.py` (`UMBRAL_VARIACION`) |
| 13 | Predios en revisión de 2026 (hoyo y piloto, cambio de construcción, cambio de avalúo): ¿siguen vigentes? | Ya no están escritos en el código. Si se necesitan, se pasan como archivo con ID_PREDIO y MARCA. | Parámetro `predios_en_revision` del manifiesto |
| 14 | La fuente de tablas y modelos (`COMPARACION_VIGENCIAS`) es un repositorio **público** y hoy no publica tablas ni modelos (están en el Drive). ¿Se publican ahí, se vuelve privado el repositorio o se usa otra fuente? | La sincronización está lista y no trae nada; las tablas siguen llegando por la carpeta de insumos | `.gitignore` de la fuente; `upstream.json` |
| 15 | La fuente ya liquida con la versión **V2** de tablas; este liquidador se certificó con **V1** (20260916). ¿Se pasa a V2? | Usa V1 (`version_tablas` en `upstream.json`) | `upstream.json` o la versión en la interfaz, cuando V2 esté sincronizada |
| 16 | La fuente agregó el insumo `insumo_proyección_comuna_valor_terreno_20260930.parquet` (terreno proyectado 2027). ¿Es el terreno 2027 (duda 9)? | No se usa: el terreno 2027 es el vigente / 0,7 | `src/Liquidacion_final.py`, sección de terrenos, y `manifest_contract.py` (nuevo insumo) |
| 17 | Cuando la fuente cambie una regla en su código (`src/`), ¿quién decide si se lleva a este liquidador? | La sincronización lista los archivos de código que cambiaron allá; no los trae | `output/upstream/SINCRONIZACION_<fecha>.md` |

