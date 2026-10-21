import time
import os
import gc
from datetime import datetime

# Importar funciones modulares
from perf import crono  # [CRONO] medición de tiempos

import argparse
import config
import traceback

# ---------------------------------------------------------------------------
# Al arrancar se pregunta que se va a liquidar: solo la vigencia actual -lo de
# siempre- o tambien las reglas de 2024 y 2025 sobre esta misma base, que dejan
# output/ESCENARIOS.parquet para compararlas.
# ---------------------------------------------------------------------------
def parse_args(args_list=None):
    parser = argparse.ArgumentParser(description="Liquidador Catastral")
    parser.add_argument("--todas", action="store_true", help="Liquidar la actual más las reglas de 2024 y 2025")
    parser.add_argument("--solo-actual", action="store_true", help="Liquidar solo la vigencia actual")
    parser.add_argument("--manifest", type=str, default=None, help="Ruta al archivo JSON de manifiesto con insumos")
    return parser.parse_args(args_list)

def preguntar_vigencias(args):
    """True si ademas hay que liquidar 2024 y 2025."""
    import sys as _sys

    if args.todas:
        return True
    if args.solo_actual:
        return False

    # Sin terminal no hay a quien preguntarle.
    if not _sys.stdin or not _sys.stdin.isatty():
        print("(sin consola interactiva: se liquida solo la vigencia actual. Use --todas si las quiere todas.)")
        return False

    print("\n" + "=" * 60)
    print("  ¿QUE SE VA A LIQUIDAR?")
    print("=" * 60)
    print("   1) Solo la vigencia actual")
    print("   2) Todas: la actual mas las reglas de 2024 y 2025")
    print("=" * 60)

    while True:
        try:
            r = input("   Opcion [1]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n   (sin respuesta: solo la vigencia actual)")
            return False
        if r in ("", "1"):
            print("   -> Solo la vigencia actual")
            return False
        if r == "2":
            print("   -> Todas las vigencias")
            return True
        print("   Responda 1 o 2.")


def _tipos_homogeneos(df):
    """
    Deja cada columna de texto con un solo tipo antes de escribir parquet.

    Caso real: VALOR_M2_SUELO llega del export como TEXTO y model_liq le pone
    un NUMERO solo a las filas que van por modelo (sale del ZHG). Con la ciudad
    completa (export 20260804) la columna quedo mezclada y pyarrow no la pudo
    escribir. Si todo lo diligenciado es numerico pasa a numero; si no, a texto.
    """
    import pandas as pd

    for col in df.columns[df.dtypes == object]:
        no_nulos = df[col].dropna()
        if no_nulos.empty:
            continue
        tipos = no_nulos.map(type).unique()
        if len(tipos) <= 1:
            continue
        texto = no_nulos.astype(str).str.strip()
        numeros = pd.to_numeric(texto.str.replace(",", ".", regex=False), errors="coerce")
        vacios = texto.eq("")
        if numeros[~vacios].notna().all():
            df[col] = pd.to_numeric(df[col].astype(str).str.strip().str.replace(",", ".", regex=False)
                                    .replace({"": None, "nan": None, "None": None}), errors="coerce")
            print(f"   [AJUSTE] {col}: tipos mezclados -> numerico")
        else:
            df[col] = df[col].astype("string")
            print(f"   [AJUSTE] {col}: tipos mezclados -> texto")


def main(args_list=None):
    inicio = time.time()
    args = parse_args(args_list)

    # Cargar manifiesto si se proporcionó
    if args.manifest:
        config.load_manifest(args.manifest)

    workspace = config.get_workspace()
    os.makedirs(workspace, exist_ok=True)
    os.environ["LIQUIDACION_WORKSPACE"] = workspace
    tablas_valor = config.get_insumo("tablas_valor")
    if tablas_valor:
        os.environ["LIQUIDACION_TABLAS_VALOR"] = tablas_valor
    if config.get_param("version_tablas"):
        os.environ["VERSION_TABLAS"] = str(config.get_param("version_tablas")).upper()
    os.chdir(workspace)

    # Estos modulos consumen rutas de config durante la importacion.
    # Deben cargarse despues de leer y validar el manifiesto.
    from tqdm import tqdm
    from consolidar_tablas import (consolidar_tablas, consolidado_necesita_actualizacion,
                                   tabla_valor_vigente)
    from tabla_construccion import procesar_construcciones, cruces_const_predio
    from Liquidacion_tablas import tablas_liquidacion
    from Liquidacion_final import liquidacion_completa
    from control_filas import control

    liquidar_otras = preguntar_vigencias(args)

    crono.inicio("LIQUIDACION (main)")  # [CRONO]

    pasos = [
        "Calidad de los insumos (exports de Sistemas)",
        "Consolidar tablas de valor",
        "Generar base de construcciones y predios",
        "Cruzar construcciones con predios",
        "Aplicar tablas de liquidación",
        "Guardar resultados intermedios",
        "Liquidación completa y resultados finales",
        "Liquidar las vigencias 2024 y 2025 para comparar"
    ]
    
    print("\n" + "="*60)
    print("=== INICIO DEL PROCESO DE LIQUIDACIÓN ===")
    print("="*60 + "\n")
    
    os.makedirs('./output', exist_ok=True)
    os.makedirs('./results', exist_ok=True)
    os.makedirs('./results/LIQUIDACION_FINAL', exist_ok=True)

    
    with tqdm(total=len(pasos), desc="Progreso general", ncols=100, 
              bar_format="{l_bar}{bar} | {n_fmt}/{total_fmt} pasos") as pbar:

        # PASO 0A: antes de gastar memoria y tiempo en la liquidacion, se
        # revisa cada export en bruto y se compara con la vigencia anterior.
        # Los ERROR detienen la corrida salvo que el manifiesto diga
        # "calidad_bloqueante": false; las ADVERTENCIAS solo se reportan.
        print(f"\n{'='*60}")
        print(f"=== PASO 0A: {pasos[0]} ===")
        print(f"{'='*60}")
        from calidad_insumos import evaluar_calidad
        calidad = evaluar_calidad(config.MANIFEST_DATA.get('run_id'))
        if calidad.errores and config.get_param('calidad_bloqueante', True):
            raise RuntimeError(
                f"La calidad de los insumos tiene {calidad.errores} error(es). "
                f"Revise {calidad.ruta} (hoja REGLAS) o corra con \"calidad_bloqueante\": false.")
        pbar.update(1)
        crono.marca("PASO 0A: calidad de insumos")  # [CRONO]

        # PASO 0B: las comunas seleccionadas, ¿tienen regla, tablas con
        # valores, modelo y datos para salir con un avaluo completo? En una
        # LIQUIDACION una comuna NO APTA detiene la corrida (salvo
        # "prevalidacion_bloqueante": false); en una PRELIQUIDACION se avisa y
        # se sigue, para ver el resultado y el detalle de lo que falta.
        print(f"\n{'='*60}")
        print("=== PASO 0B: Prevalidacion de las comunas seleccionadas ===")
        print(f"{'='*60}")
        from prevalidacion_comunas import ejecutar_desde_config as prevalidar
        prev = prevalidar()
        tipo = str(config.get_param('tipo_corrida', 'preliquidacion')).lower()
        if prev.no_aptas:
            mensaje = (f"Comunas NO APTAS para liquidar: {', '.join(prev.no_aptas)}. "
                       f"Detalle en {prev.ruta} (hojas COMUNAS y CRITERIOS).")
            if tipo == 'liquidacion' and config.get_param('prevalidacion_bloqueante', True):
                raise RuntimeError(mensaje + " Corrija, quite esas comunas de la seleccion o corra como preliquidacion.")
            print(f"[WARN] {mensaje} Se sigue porque es una {tipo}: sus predios quedaran marcados.")
        crono.marca("PASO 0B: prevalidacion de comunas")  # [CRONO]

        print(f"\n{'='*60}")
        print(f"=== PASO 0: {pasos[1]} ===")
        print(f"{'='*60}")
        try:
            entrada_tablas, vigente, necesita_actualizar = consolidado_necesita_actualizacion()
            if necesita_actualizar:
                ruta_tablas = consolidar_tablas(entrada_tablas)
                print(f"[OK] Tablas de valor consolidadas")
                print(f"   - {ruta_tablas}")
            elif vigente is not None:
                print("[OK] Tablas de valor vigentes; no se requiere consolidar de nuevo")
                print(f"   - {vigente}")
            else:
                raise RuntimeError("No hay un consolidado de tablas vigente")
        except Exception as e:
            vigente = tabla_valor_vigente()
            print(f"[WARN] No se pudieron consolidar las tablas: {e}")
            if vigente is None:
                raise
            print(f"   Se sigue con el consolidado que ya estaba: {vigente.name}")
        pbar.update(1)
        crono.marca("PASO 0: consolidar tablas")  # [CRONO]

        print(f"\n{'='*60}")
        print(f"=== PASO 1: {pasos[2]} ===")
        print(f"{'='*60}")
        try:
            df_predio, df_conv, df_noconv = procesar_construcciones()
            
            if df_predio is None or df_conv is None or df_noconv is None:
                raise ValueError("Error: No se pudieron cargar todos los archivos necesarios")
            
            print(f"[OK] Base de construcciones generada correctamente")
            print(f"   - Predios: {len(df_predio):,}")
            print(f"   - Construcciones convencionales: {len(df_conv):,}")
            print(f"   - Construcciones no convencionales: {len(df_noconv):,}")
            control.marca("entrada (insumos)", convencionales=df_conv,
                          no_convencionales=df_noconv)

            pbar.update(1)
            crono.marca("PASO 1: procesar_construcciones")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Error estructural en PASO 1 (Generación de construcciones): {str(e)}")
            print("--- DETALLE TÉCNICO DE LA FALLA ---")
            traceback.print_exc()
            print("-----------------------------------")
            raise
        
        print(f"\n{'='*60}")
        print(f"=== PASO 2: {pasos[3]} ===")
        print(f"{'='*60}")
        try:
            df_const_predio_final = cruces_const_predio(df_predio, df_conv, df_noconv)
            # Con la ciudad completa la corrida llega a ~10 GB: lo que ya no se
            # usa se suelta al terminar cada paso.
            del df_predio, df_conv, df_noconv
            gc.collect()
            
            print(f"[OK] Cruces realizados correctamente")
            print(f"   - Construcciones-Predio: {len(df_const_predio_final):,}")
            print(f"   - Predios únicos: {df_const_predio_final['ID_PREDIO'].nunique():,}")

            pbar.update(1)
            crono.marca("PASO 2: cruces_const_predio (homologacion+uso)")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Error estructural en PASO 2 (Cruces Const-Predio): {str(e)}")
            print("--- DETALLE TÉCNICO DE LA FALLA ---")
            traceback.print_exc()
            print("-----------------------------------")
            raise
   
        print(f"\n{'='*60}")
        print(f"=== PASO 3: {pasos[4]} ===")
        print(f"{'='*60}")
        try:
            df_liquidacion = tablas_liquidacion(df_const_predio_final)
            del df_const_predio_final
            gc.collect()
            
            print(f"[OK] Tablas de liquidación aplicadas")
            print(f"   - Registros liquidados: {len(df_liquidacion):,}")
            print(f"   - Predios con liquidación: {df_liquidacion['ID_PREDIO'].nunique():,}")

            # Contrato de variables de los modelos (tipo, unidad, rango): un
            # ERROR significa que un modelo recibio una variable que no es la
            # que espera. En una liquidacion detiene la corrida.
            import contrato_modelos
            if contrato_modelos.errores():
                msg = (f"Contrato de variables de los modelos con {len(contrato_modelos.errores())} error(es): "
                       "ver output/modelos/CONTRATO_VARIABLES_MODELOS.xlsx (hoja HALLAZGOS).")
                if str(config.get_param('tipo_corrida', 'preliquidacion')).lower() == 'liquidacion':
                    raise RuntimeError(msg)
                print(f"[WARN] {msg} Se sigue porque es una preliquidacion.")

            pbar.update(1)
            crono.marca("PASO 3: tablas_liquidacion (cola, ver 3.x)")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Error estructural en PASO 3 (Tablas de Liquidación): {str(e)}")
            print("--- DETALLE TÉCNICO DE LA FALLA ---")
            traceback.print_exc()
            print("-----------------------------------")
            raise
        
        print(f"\n{'='*60}")
        print(f"=== PASO 4: {pasos[5]} ===")
        print(f"{'='*60}")
        try:
            fecha_actual = datetime.now().strftime('%Y%m%d')
            
            archivo_parquet = './output/LIQUIDACION_TABLAS.parquet'
            _tipos_homogeneos(df_liquidacion)
            df_liquidacion.to_parquet(archivo_parquet, index=False)
            print(f"[OK] Archivo parquet guardado: {archivo_parquet}")

            pbar.update(1)
            crono.marca("PASO 4: guardar parquet")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Error estructural en PASO 4 (Guardar Resultados): {str(e)}")
            print("--- DETALLE TÉCNICO DE LA FALLA ---")
            traceback.print_exc()
            print("-----------------------------------")
            raise

        print(f"\n{'='*60}")
        print(f"=== PASO 5: {pasos[6]} ===")
        print(f"{'='*60}")
        try:
            df_predio_final = liquidacion_completa(
                df_liquidacion,
                base_path='./input/',
                generar_excel=int(bool(config.get_param('generar_excel', True))),
            )
            if df_predio_final is not None:
                print(f"[OK] Liquidación final completada")
                print(f"   - Predios procesados: {len(df_predio_final):,}")
                
                # Estadísticas de avalúo total
                if 'AVALUO_CAT_2026' in df_predio_final.columns:
                    avaluo_total = df_predio_final['AVALUO_CAT_2026'].sum()
                    print(f"\n[FIN] Avalúo total catastral 2026: ${avaluo_total:,.0f}")
                    print(f"   ({avaluo_total/1_000_000_000_000:.2f} Billones)")
                
                if 'AVALPRED' in df_predio_final.columns and 'AVALPRED_2025' in df_predio_final.columns:
                    avaluo_2026 = df_predio_final['AVALPRED'].sum()
                    avaluo_2025 = df_predio_final['AVALPRED_2025'].sum()
                    diferencia = avaluo_2026 - avaluo_2025
                    print(f"\n[DATA] Comparación con 2025:")
                    print(f"   - Avalúo 2025: ${avaluo_2025:,.0f}")
                    print(f"   - Avalúo 2026: ${avaluo_2026:,.0f}")
                    print(f"   - Diferencia: ${diferencia:,.0f} ({diferencia/1_000_000_000_000:.2f} Billones)")
                    if avaluo_2025 > 0:
                        variacion_porcentual = ((avaluo_2026 - avaluo_2025) / avaluo_2025) * 100
                        print(f"   - Variación: {variacion_porcentual:.2f}%")
            else:
                print("[WARN] La liquidación completa no retornó resultados")
            
            # Un Excel con los predios que no cumplen una condicion o les falta
            # un dato para liquidar (junta pre y post inconsistencias).
            try:
                from reporte_predios_inconsistentes import generar as predios_por_corregir
                predios_por_corregir('./output')
            except Exception as e:
                print(f"[WARN] No se pudo generar el reporte de predios por corregir: {e}")

            pbar.update(1)
            crono.marca("PASO 5: liquidacion_completa")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Error estructural en PASO 5 (Liquidación Final): {str(e)}")
            print("--- DETALLE TÉCNICO DE LA FALLA ---")
            traceback.print_exc()
            print("-----------------------------------")
            raise
        
    # ============================================================
    # SERIALIZACIÓN Y MANIFIESTO FINAL DE LA PRELIQUIDACIÓN
    # ============================================================
    import json
    
    fin = time.time()
    tiempo_total = round(fin - inicio, 2)

    # Agregar metadatos y comentarios al archivo de corrida
    metadata_corrida = config.MANIFEST_DATA.copy()
    # De donde salieron las tablas y los modelos (commit de la fuente).
    try:
        from consolidar_tablas import tabla_valor_vigente as _tv
        from sincronizar_upstream import procedencia
        _t = _tv()
        metadata_corrida["procedencia"] = procedencia(str(_t) if _t else None)
    except Exception as e:
        metadata_corrida["procedencia"] = {"error": str(e)}
    metadata_corrida["resultados"] = {
        "tiempo_total_segundos": tiempo_total,
        "fecha_ejecucion": datetime.now().isoformat()
    }
    
    archivo_metadatos = f"./output/manifiesto_ejecucion_{metadata_corrida.get('run_id', 'DEFAULT')}.json"
    with open(archivo_metadatos, 'w', encoding='utf-8') as f:
        json.dump(metadata_corrida, f, indent=4, ensure_ascii=False)
    
    print(f"\n{'='*60}")
    print("=== RESUMEN DE EJECUCIÓN ===")
    print(f"{'='*60}")
    print(f"[CRONO]  Tiempo total de ejecución: {tiempo_total} segundos ({tiempo_total/60:.2f} minutos)")

    crono.resumen()  # [CRONO] desglose por paso y sub-bloque
    control.resumen()
    # Lo que se anuncia sale de LO QUE QUEDO EN DISCO, no de una lista escrita
    # a mano. Antes se nombraban REVISION_LIQUIDACION_<fecha>.xlsx y
    # LIQUIDACION_FINAL/CONSTRUCCIONES_<fecha>.txt, que los genera el PASO 5
    # -hoy comentado-, asi que el resumen mandaba a buscar dos archivos que no
    # existian. Recorriendo las carpetas de salida y filtrando por fecha de
    # modificacion se imprime lo que ESTA corrida escribio, y la lista no se
    # puede volver a desactualizar cuando se prenda o apague un paso.
    carpetas_salida = [
        './input/tablas/output',            # PASO 0
        './output',                         # parquets y reportes
        './results/LIQUIDACION_TABLAS',     # diagnosticos de tabla
        './results/COMPARACION_VIGENCIA',   # entregable de la comparacion
        './results/LIQUIDACION_FINAL',      # PASO 5, cuando se reactive
    ]
    
    generados = [archivo_metadatos] # Empezamos incluyendo el metadato serializado
    for carpeta in carpetas_salida:
        for raiz, _, archivos in os.walk(carpeta):
            for nombre in archivos:
                if nombre.startswith('~$'):      # bloqueos que deja Excel
                    continue
                ruta = os.path.join(raiz, nombre)
                try:
                    if os.path.getmtime(ruta) >= inicio:
                        generados.append(ruta)
                except OSError:
                    pass

    # ------------------------------------------------------------------
    # PASO 7 (opcional): las otras vigencias sobre esta misma base
    # ------------------------------------------------------------------
    # El paso 7 lee su base del disco: la liquidacion en memoria ya no hace falta.
    df_liquidacion = None
    gc.collect()
    if liquidar_otras:
        print("")
        print("=" * 60)
        print(f"=== PASO 7: {pasos[7]} ===")
        print("=" * 60)
        try:
            from escenarios import comparar
            comparar()
            crono.marca("PASO 7: escenarios 2024/2025")  # [CRONO]
        except Exception as e:
            print(f"[ERROR] Los escenarios no se pudieron generar: {str(e)}")
            raise
            print("   (la liquidación actual SÍ quedó guardada)")
    else:
        print("")
        print("(PASO 7 omitido: se pidio solo la vigencia actual. "
              "Para las otras: `python src/escenarios.py`.)")

    # Una carpeta por accion y una version por corrida (ver publicar_resultados).
    # Con "publicar_por_carpetas": false todo queda en ./output y ./results como antes.
    if config.get_param('publicar_por_carpetas', True):
        from publicar_resultados import FORMATOS_POR_TIPO, publicar
        tipo = str(config.get_param('tipo_corrida', 'preliquidacion')).lower()
        formatos = config.get_param('formatos_salida') or FORMATOS_POR_TIPO.get(tipo, ['parquet', 'xlsx'])
        publicar(inicio, tipo, formatos, df_predio_final, manifiesto=config.MANIFEST_PATH)
    else:
        print("")
        print("📁 Archivos generados:")
        if generados:
            for ruta in sorted(generados, key=os.path.getmtime):
                print(f"   - {ruta.replace(os.sep, '/')}")
        else:
            print("   (ninguno: revise los avisos de arriba)")

    print(f"\n[OK] Proceso completado exitosamente.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[WARN] Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"\n\n[ERROR] Error fatal en la ejecución: {str(e)}")
        import traceback
        traceback.print_exc()
