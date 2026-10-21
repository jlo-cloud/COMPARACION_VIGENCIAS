# Liquidador Catastral para Windows

## Requisitos del equipo (leer antes de probar)

- **Memoria:** la corrida con la ciudad completa (unos 900.000 registros) usa hasta **10 GB de RAM**. Cierre Chrome, ChatGPT y otros programas pesados antes de "Generar liquidacion". Si falta memoria, el log muestra `Unable to allocate ...` y la corrida se detiene sin dejar resultados a medias.
- **Tiempo:** de 40 a 60 minutos para la corrida completa con los escenarios 2024/2025. "Revisar calidad" tarda alrededor de 1 minuto.
- **Bloqueo de Windows:** el ejecutable no tiene firma digital. En Windows 11 con *Control inteligente de aplicaciones* activo, Windows puede bloquearlo ("Una directiva de Control de aplicaciones bloqueó este archivo"). En ese caso hay tres salidas: firmar el ejecutable con un certificado de la Alcaldía (solución definitiva), usar un equipo administrado por Sistemas (suelen tenerlo desactivado), o correr desde el código fuente con `run_dev.ps1`. Desactivar esa protección en Windows no se puede revertir sin reinstalar.
- Se copia **la carpeta completa** `dist\LiquidadorCatastral`, no solo el `.exe`.

## Uso por el operador

1. Abra `LiquidadorCatastral.exe` dentro de la carpeta distribuida.
2. Seleccione la vigencia. La aplicacion solo permite ejecutar perfiles que tengan contrato validado.
3. Elija una carpeta de resultados. Los insumos originales no se modifican.
4. Seleccione la carpeta con los insumos y pulse **Detectar archivos**. Complete manualmente los campos que queden vacios o ambiguos.
5. En **Comunas a liquidar** marque las comunas. Por defecto vienen las 17 de `Reglas.xlsx`; los atajos marcan las 17, todas o ninguna. Solo se liquida lo que quede marcado. La casilla de parqueaderos T12 se activa cuando sus valores esten avalados.
6. Pulse **Validar insumos**. La liquidacion no inicia si falta un archivo, si esta vacio, si tiene una extension incorrecta, si el mismo archivo esta en dos insumos que deben ser distintos (por ejemplo predios actuales y anteriores) o si no hay comunas marcadas.
7. (Recomendado) Pulse **Revisar calidad**: compara cada export con el de la vigencia anterior y deja `CALIDAD_INSUMOS_<run_id>.xlsx`. Los ERROR detienen la liquidacion; las ADVERTENCIAS solo se reportan.
8. Pulse **Prevalidar comunas**. Para cada comuna marcada dice si se puede liquidar: regla y grupo de tablas, tablas con valores en el consolidado, parqueaderos, modelo de propiedad horizontal, especiales y los datos de cada predio. Deja `01B_PREVALIDACION_COMUNAS\...\PREVALIDACION_COMUNAS_<run_id>.xlsx` con estas hojas:
   - **COMUNAS:** APTA, APTA CON ADVERTENCIAS o NO APTA, con QUE_NO_CUMPLE.
   - **CRITERIOS:** cada criterio por comuna, con cuantas construcciones o predios afecta y la accion.
   - **PREDIOS_NO_CUMPLEN:** cada predio con QUE_NO_CUMPLE.
   - **TABLAS_CONSOLIDADO:** que tablas tienen valores.
9. Elija el **Tipo de corrida** y los **Formatos del resultado**:
   - *Preliquidacion* (por defecto): resultado por predio en Parquet + el Excel de revision. Si hay comunas NO APTAS se avisa y se sigue; sus predios quedan marcados.
   - *Liquidacion*: ademas el `.txt` con el formato de los export de Sistemas (`|`, coma decimal, latin-1). **Si alguna comuna marcada es NO APTA, la corrida se detiene.**
10. Pulse **Generar liquidacion**. La prevalidacion se repite al comenzar.

Despues de liquidar, cada predio queda con `ESTADO_PRELIQUIDACION` (CUMPLE / CUMPLE CON OBSERVACIONES / NO CUMPLE) y `QUE_NO_CUMPLE`. Hay dos lugares para revisarlo:
- `REVISION_LIQUIDACION_<fecha>.xlsx`, con las hojas RESUMEN, NO_CUMPLEN y CUMPLEN;
- `PREDIOS_POR_CORREGIR_<fecha>.xlsx`, que junta prevalidacion, inconsistencias y validacion final, con la columna QUE_NO_CUMPLE y PASA_PRELIQUIDACION.

Al terminar, cada accion queda en su carpeta y cada corrida en una version, dentro de la carpeta de resultados:

```text
00_MANIFIESTOS/<AAAA-MM-DD_HHMM>_<TIPO>/          manifiesto con que se corrio
01_CALIDAD_INSUMOS/<version>/                      control de calidad de los exports
01B_PREVALIDACION_COMUNAS/<version>/               comunas aptas o no, criterios y predios que no cumplen
02_INCONSISTENCIAS_PREVIAS/<version>/              reporte de pre-inconsistencias
03_LIQUIDACION_CONSTRUCCIONES/<version>/           liquidacion por construccion y diagnostico de tablas
04_INCONSISTENCIAS_POSTERIORES/<version>/          construcciones sin valor y su causa
05_RESULTADO_PREDIOS/<version>/                    PREDIOS_<TIPO>.parquet / .txt y REVISION_LIQUIDACION.xlsx
06_ESCENARIOS/<version>/                           escenarios 2024/2025 (ESCENARIOS.parquet, DETALLE_VIGENCIAS.xlsx)
07_PREDIOS_POR_CORREGIR/<version>/                 predios con su inconsistencia y el dato que les falta
```

Las versiones anteriores no se borran. Use una carpeta de resultados distinta a la de insumos. Los logs quedan visibles y las salidas se escriben en `output/` y `results/` dentro de la carpeta de resultados.

La vigencia 2027 esta habilitada. La vigencia 2026 aparece como pendiente y no se puede ejecutar hasta disponer de su contrato y una muestra dorada de regresion; cambiar solo la etiqueta del ano produciria resultados engañosos.

## Reliquidar un listado de predios (pestana 3)

Para reclamaciones, radicados o revisiones de una vigencia anterior: vuelve a liquidar un listado de predios con las reglas de otro ejercicio, la ZHF de otro export y el terreno de otra vigencia.

1. Abra la pestana **3. Reliquidar predios**.
2. Elija el listado (Excel con `ID_PREDIO`), la base de construcciones (`output\todas_las_construcciones.parquet` de una corrida), las reglas (2025 o 2024) y la foto de predios de referencia (avaluo y terreno que se conserva).
3. Si la comuna de los predios no estuvo en ese ejercicio, escriba en *Comuna cuyos valores se aplican* la comuna cuyas tablas se usaran (por ejemplo `01`).
4. Opcional: el export con la ZHF a usar, los exports de construcciones y anexos de referencia (para detectar mutaciones) y los valores de zona (para validar el terreno).
5. Pulse **Reliquidar**. El Excel queda en la carpeta de salida, junto con la configuracion usada; con **Guardar/Cargar configuracion** se repite el ejercicio.

Por linea de comandos: `LiquidadorCatastral.exe --reliquidar configuracion.json`. La guia completa esta en `docs/RELIQUIDACION.md`.

## Construccion reproducible

Requisitos: Windows x64 y Python 3.12.x. Esta version es obligatoria porque los modelos fueron serializados con scikit-learn 1.5.1/1.5.2 y XGBoost 2.1.2; el autoexamen demostro que scikit-learn 1.8.0 no puede cargar todos los artefactos.

```powershell
.\build_exe.ps1 -Clean
```

El script crea `.venv-build`, instala versiones fijadas, ejecuta las pruebas y genera:

```text
dist\LiquidadorCatastral\LiquidadorCatastral.exe
```

Se distribuye la carpeta completa `dist\LiquidadorCatastral`, no solo el `.exe`, porque contiene las bibliotecas numericas y los modelos. El usuario final no necesita Python.

Para reconstruir sin volver a instalar paquetes:

```powershell
.\build_exe.ps1 -SkipInstall
```

## Verificacion automatizable

```powershell
dist\LiquidadorCatastral\LiquidadorCatastral.exe --validate-manifest C:\ruta\manifest_2027.json
```

Un codigo de salida `0` significa que el contrato de archivos fue aceptado. Esto no sustituye una regresion end-to-end con datos reales.

El build ejecuta ademas `LiquidadorCatastral.exe --self-test`, que importa las bibliotecas nativas y deserializa los siete modelos incluidos. Una corrida end-to-end sigue requiriendo los insumos catastrales reales.
