import time
import os
import pandas as pd
from datetime import datetime
from tqdm import tqdm  # ✅ Barra de progreso

# Importar funciones modulares
from consolidar_tablas import (consolidar_tablas, consolidado_necesita_actualizacion,
                               tabla_valor_vigente)
from tabla_construccion import procesar_construcciones, cruces_const_predio
from Liquidacion_tablas import tablas_liquidacion
from Liquidacion_final import liquidacion_completa
from comparacion_vigencia import comparacion_vigencia
from perf import crono  # ⏱️ medición de tiempos


def main():
    inicio = time.time()
    crono.inicio("LIQUIDACION (main)")  # ⏱️

    pasos = [
        "Consolidar tablas de valor",
        "Generar base de construcciones y predios",
        "Cruzar construcciones con predios",
        "Aplicar tablas de liquidación",
        "Guardar resultados intermedios",
        "Liquidación completa y resultados finales",
        "Comparar VM2 liquidación vs vigencia 2026"
    ]
    
    print("\n" + "="*60)
    print("=== INICIO DEL PROCESO DE LIQUIDACIÓN ===")
    print("="*60 + "\n")
    
    os.makedirs('./output', exist_ok=True)
    os.makedirs('./results', exist_ok=True)
    os.makedirs('./results/LIQUIDACION_FINAL', exist_ok=True)

    
    with tqdm(total=len(pasos), desc="Progreso general", ncols=100, 
              bar_format="{l_bar}{bar} | {n_fmt}/{total_fmt} pasos") as pbar:
        
        print(f"\n{'='*60}")
        print(f"=== PASO 0: {pasos[0]} ===")
        print(f"{'='*60}")
        try:
            entrada_tablas, vigente, necesita_actualizar = consolidado_necesita_actualizacion()
            if necesita_actualizar:
                ruta_tablas = consolidar_tablas(entrada_tablas)
                print(f"✅ Tablas de valor consolidadas")
                print(f"   - {ruta_tablas}")
            elif vigente is not None:
                print("✅ Tablas de valor vigentes; no se requiere consolidar de nuevo")
                print(f"   - {vigente}")
            else:
                raise RuntimeError("No hay un consolidado de tablas vigente")
        except Exception as e:
            vigente = tabla_valor_vigente()
            print(f"⚠️ No se pudieron consolidar las tablas: {e}")
            if vigente is None:
                raise
            print(f"   Se sigue con el consolidado que ya estaba: {vigente.name}")
        pbar.update(1)
        crono.marca("PASO 0: consolidar tablas")  # ⏱️

        print(f"\n{'='*60}")
        print(f"=== PASO 1: {pasos[1]} ===")
        print(f"{'='*60}")
        try:
            df_predio, df_conv, df_noconv = procesar_construcciones()
            
            if df_predio is None or df_conv is None or df_noconv is None:
                raise ValueError("Error: No se pudieron cargar todos los archivos necesarios")
            
            print(f"✅ Base de construcciones generada correctamente")
            print(f"   - Predios: {len(df_predio):,}")
            print(f"   - Construcciones convencionales: {len(df_conv):,}")
            print(f"   - Construcciones no convencionales: {len(df_noconv):,}")

            pbar.update(1)
            crono.marca("PASO 1: procesar_construcciones")  # ⏱️
        except Exception as e:
            print(f"❌ Error en generación de construcciones: {str(e)}")
            raise
        
        print(f"\n{'='*60}")
        print(f"=== PASO 2: {pasos[2]} ===")
        print(f"{'='*60}")
        try:
            df_const_predio_final = cruces_const_predio(df_predio, df_conv, df_noconv)
            
            print(f"✅ Cruces realizados correctamente")
            print(f"   - Construcciones-Predio: {len(df_const_predio_final):,}")
            print(f"   - Predios únicos: {df_const_predio_final['ID_PREDIO'].nunique():,}")

            pbar.update(1)
            crono.marca("PASO 2: cruces_const_predio (homologacion+uso)")  # ⏱️
        except Exception as e:
            print(f"❌ Error en cruces: {str(e)}")
            raise
   
        print(f"\n{'='*60}")
        print(f"=== PASO 3: {pasos[3]} ===")
        print(f"{'='*60}")
        try:
            df_liquidacion = tablas_liquidacion(df_const_predio_final)
            
            print(f"✅ Tablas de liquidación aplicadas")
            print(f"   - Registros liquidados: {len(df_liquidacion):,}")
            print(f"   - Predios con liquidación: {df_liquidacion['ID_PREDIO'].nunique():,}")

            pbar.update(1)
            crono.marca("PASO 3: tablas_liquidacion (cola, ver 3.x)")  # ⏱️
        except Exception as e:
            print(f"❌ Error en tablas de liquidación: {str(e)}")
            raise
        
        print(f"\n{'='*60}")
        print(f"=== PASO 4: {pasos[4]} ===")
        print(f"{'='*60}")
        try:
            fecha_actual = datetime.now().strftime('%Y%m%d')
            
            archivo_parquet = './output/LIQUIDACION_TABLAS.parquet'
            df_liquidacion.to_parquet(archivo_parquet, index=False)
            print(f"✅ Archivo parquet guardado: {archivo_parquet}")

            pbar.update(1)
            crono.marca("PASO 4: guardar parquet")  # ⏱️
        except Exception as e:
            print(f"❌ Error al guardar resultados intermedios: {str(e)}")
            raise


        print(f"\n{'='*60}")
        print(f"=== PASO 6: {pasos[6]} ===")
        print(f"{'='*60}")
        archivo_comparacion = None
        try:
            df_comparacion = comparacion_vigencia(df_liquidacion)
            archivo_comparacion = (f'./results/COMPARACION_VIGENCIA/'
                                   f'DETALLE_LIQUIDADOS_{fecha_actual}.xlsx')
            print(f"✅ Comparación contra la vigencia 2026 generada")
            print(f"   - Construcciones comparadas: {len(df_comparacion):,}")

            pbar.update(1)
            crono.marca("PASO 6: comparacion_vigencia")  # ⏱️
        except Exception as e:
            print(f"⚠️ La comparación con la vigencia no se pudo generar: {str(e)}")
            print(f"   (la liquidación SÍ quedó guardada; puede reintentar solo")
            print(f"    la comparación con: python src/comparacion_vigencia.py)")

        #                 print(f"   - Máximo: {var_avaluo.max():.2f}%")
                
        #         # Estadísticas de avalúo total
        #         if 'AVALUO_CAT_2026' in df_predio_final.columns:
        #             avaluo_total = df_predio_final['AVALUO_CAT_2026'].sum()
        #             print(f"\n💰 Avalúo total catastral 2026: ${avaluo_total:,.0f}")
        #             print(f"   ({avaluo_total/1_000_000_000_000:.2f} Billones)")
                
        #         if 'AVALPRED' in df_predio_final.columns and 'AVALPRED_2025' in df_predio_final.columns:
        #             avaluo_2026 = df_predio_final['AVALPRED'].sum()
        #             avaluo_2025 = df_predio_final['AVALPRED_2025'].sum()
        #             diferencia = avaluo_2026 - avaluo_2025
        #             print(f"\n📊 Comparación con 2025:")
        #             print(f"   - Avalúo 2025: ${avaluo_2025:,.0f}")
        #             print(f"   - Avalúo 2026: ${avaluo_2026:,.0f}")
        #             print(f"   - Diferencia: ${diferencia:,.0f} ({diferencia/1_000_000_000_000:.2f} Billones)")
        #             if avaluo_2025 > 0:
        #                 variacion_porcentual = ((avaluo_2026 - avaluo_2025) / avaluo_2025) * 100
        #                 print(f"   - Variación: {variacion_porcentual:.2f}%")
        #     else:
        #         print("⚠️ La liquidación completa no retornó resultados")
            
        #     pbar.update(1)
        # except Exception as e:
        #     print(f"❌ Error en liquidación completa: {str(e)}")
        #     raise
        
    # ============================================================
    # RESUMEN FINAL
    # ============================================================
    fin = time.time()
    tiempo_total = round(fin - inicio, 2)
    
    print(f"\n{'='*60}")
    print("=== RESUMEN DE EJECUCIÓN ===")
    print(f"{'='*60}")
    print(f"⏱️  Tiempo total de ejecución: {tiempo_total} segundos ({tiempo_total/60:.2f} minutos)")

    crono.resumen()  # ⏱️ desglose por paso y sub-bloque
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
    generados = []
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

    print("")
    print("📁 Archivos generados:")
    if generados:
        for ruta in sorted(generados, key=os.path.getmtime):
            print(f"   - {ruta.replace(os.sep, '/')}")
    else:
        print("   (ninguno: revise los avisos de arriba)")
    
    print(f"\n✅ Proceso completado exitosamente.")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️ Proceso interrumpido por el usuario")
    except Exception as e:
        print(f"\n\n❌ Error fatal en la ejecución: {str(e)}")
        import traceback
        traceback.print_exc()