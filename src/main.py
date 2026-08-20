import time
import os
import pandas as pd
from datetime import datetime
from tqdm import tqdm  # ✅ Barra de progreso

# Importar funciones modulares
from tabla_construccion import procesar_construcciones, cruces_const_predio
from Liquidacion_tablas import tablas_liquidacion
from Liquidacion_final import liquidacion_completa
# APAGADO por ahora: comparacion contra la base de ofertas del mercado.
# El modulo sigue funcionando; para reactivarlo, descomente esta linea y el
# bloque del PASO 6-A mas abajo. Se puede correr suelto con:
#     python src/comparacion_ofertas.py
# from comparacion_ofertas import comparacion_ofertas
from comparacion_vigencia import comparacion_vigencia
from perf import crono  # ⏱️ medición de tiempos


def main():
    """
    Proceso de liquidación ajustado:
    1. Procesar construcciones (tabla_construccion.py)
    2. Aplicar tablas de liquidación (Liquidacion_tablas.py)
    3. Liquidación completa (Liquidacion_final.py)
    4. Comparación VM2 liquidación vs ofertas (comparacion_ofertas.py)
    """

    inicio = time.time()
    crono.inicio("LIQUIDACION (main)")  # ⏱️

    pasos = [
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
    
    # Crear directorios necesarios
    os.makedirs('./output', exist_ok=True)
    os.makedirs('./results', exist_ok=True)
    os.makedirs('./results/LIQUIDACION_FINAL', exist_ok=True)

    
    # Crear barra de progreso
    with tqdm(total=len(pasos), desc="Progreso general", ncols=100, 
              bar_format="{l_bar}{bar} | {n_fmt}/{total_fmt} pasos") as pbar:
        
        # ============================================================
        # PASO 1: GENERAR BASE DE CONSTRUCCIONES
        # ============================================================
        print(f"\n{'='*60}")
        print(f"=== PASO 1: {pasos[0]} ===")
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
        
        # ============================================================
        # PASO 2: CRUCES PREDIO - CONSTRUCCIÓN
        # ============================================================
        print(f"\n{'='*60}")
        print(f"=== PASO 2: {pasos[1]} ===")
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
   
        # ============================================================
        # PASO 3: APLICAR TABLAS DE LIQUIDACIÓN
        # ============================================================
        print(f"\n{'='*60}")
        print(f"=== PASO 3: {pasos[2]} ===")
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
        
        # ============================================================
        # PASO 4: GUARDAR RESULTADOS INTERMEDIOS
        # ============================================================
        print(f"\n{'='*60}")
        print(f"=== PASO 4: {pasos[3]} ===")
        print(f"{'='*60}")
        try:
            fecha_actual = datetime.now().strftime('%Y%m%d')
            
            # Guardar archivo de liquidación con tablas
            #archivo_liquidacion = f'./output/{fecha_actual}_LIQUIDACION_TABLAS.txt'
            #df_liquidacion.to_csv(archivo_liquidacion, sep="|", index=False)
            #print(f"✅ Archivo intermedio guardado: {archivo_liquidacion}")
            
            # Opcional: Guardar también en formato parquet para mejor rendimiento
            archivo_parquet = './output/LIQUIDACION_TABLAS.parquet'
            df_liquidacion.to_parquet(archivo_parquet, index=False)
            print(f"✅ Archivo parquet guardado: {archivo_parquet}")

            pbar.update(1)
            crono.marca("PASO 4: guardar parquet")  # ⏱️
        except Exception as e:
            print(f"❌ Error al guardar resultados intermedios: {str(e)}")
            raise

        # ============================================================
        # PASO 6: COMPARACIÓN VM2 LIQUIDACIÓN vs VIGENCIA 2026
        # ============================================================
        # Compara el VM2 que daría la liquidación contra el que hoy trae la
        # base catastral. Se le pasa df_liquidacion en memoria: es el mismo
        # contenido del parquet que se acaba de guardar, y así no se relee
        # (~77 MB).
        # NO se relanza la excepción a propósito: la liquidación ya quedó
        # guardada en el PASO 4, así que un problema del reporte (por ejemplo
        # el Excel abierto) no debe tumbar toda la corrida. Se avisa y se sigue.
        print(f"\n{'='*60}")
        print(f"=== PASO 6: {pasos[5]} ===")
        print(f"{'='*60}")
        archivo_comparacion = None
        try:
            df_comparacion = comparacion_vigencia(df_liquidacion)
            archivo_comparacion = (f'./results/COMPARACION_VIGENCIA/'
                                   f'COMPARACION_VIGENCIA_{fecha_actual}.xlsx')
            print(f"✅ Comparación contra la vigencia 2026 generada")
            print(f"   - Construcciones comparadas: {len(df_comparacion):,}")

            pbar.update(1)
            crono.marca("PASO 6: comparacion_vigencia")  # ⏱️
        except Exception as e:
            print(f"⚠️ La comparación con la vigencia no se pudo generar: {str(e)}")
            print(f"   (la liquidación SÍ quedó guardada; puede reintentar solo")
            print(f"    la comparación con: python src/comparacion_vigencia.py)")

        # ============================================================
        # PASO 6-A: COMPARACIÓN VM2 LIQUIDACIÓN vs OFERTAS  [APAGADO]
        # ============================================================
        # Descomentar este bloque y el import de arriba para reactivarlo.
        # print(f"\n{'='*60}")
        # print(f"=== PASO 6-A: Comparar VM2 liquidación vs ofertas ===")
        # print(f"{'='*60}")
        # try:
        #     df_ofertas = comparacion_ofertas(df_liquidacion)
        #     print(f"✅ Comparación con ofertas generada")
        #     print(f"   - Ofertas comparadas: {len(df_ofertas):,}")
        #     crono.marca("PASO 6-A: comparacion_ofertas")  # ⏱️
        # except Exception as e:
        #     print(f"⚠️ La comparación con ofertas no se pudo generar: {str(e)}")

        # # ============================================================
        # # PASO 5: LIQUIDACIÓN COMPLETA Y ARCHIVO FINAL
        # # ============================================================
        # print(f"\n{'='*60}")
        # print(f"=== PASO 5: {pasos[4]} ===")
        # print(f"{'='*60}")
        # try:
        #     df_predio_final = liquidacion_completa(
        #         df_liquidacion, 
        #         './input/',
        #         generar_excel= 1#### AQUI 
        #     )
            
        #     if df_predio_final is not None:
        #         print(f"✅ Liquidación completa finalizada")
        #         print(f"   - Predios procesados: {len(df_predio_final):,}")
                
        #         # Estadísticas de liquidación
        #         if 'MARCA_LIQUIDACION' in df_predio_final.columns:
        #             print("\n📊 Estadísticas de liquidación:")
        #             stats = df_predio_final['MARCA_LIQUIDACION'].value_counts()
        #             for marca, count in stats.items():
        #                 porcentaje = (count / len(df_predio_final)) * 100
        #                 print(f"   - {marca}: {count:,} ({porcentaje:.2f}%)")
                
        #         # Estadísticas de variación de avalúo
        #         if 'VAR_AVALUO' in df_predio_final.columns:
        #             var_avaluo = df_predio_final['VAR_AVALUO'].dropna()
        #             if len(var_avaluo) > 0:
        #                 print("\n📈 Estadísticas de variación de avalúo:")
        #                 print(f"   - Promedio: {var_avaluo.mean():.2f}%")
        #                 print(f"   - Mediana: {var_avaluo.median():.2f}%")
        #                 print(f"   - Mínimo: {var_avaluo.min():.2f}%")
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
    print(f"\n📁 Archivos generados:")
    print(f"   - ./output/LIQUIDACION_TABLAS.parquet")
    print(f"   - ./results/REVISION_LIQUIDACION_{fecha_actual}.xlsx")
    print(f"   - ./results/LIQUIDACION_FINAL/CONSTRUCCIONES_{fecha_actual}.txt")
    if archivo_comparacion:
        print(f"   - {archivo_comparacion}")
    
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