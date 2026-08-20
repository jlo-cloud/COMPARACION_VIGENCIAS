import pandas as pd
import numpy as np
import os
import glob
import re
from io import StringIO
import gc
from datetime import datetime

from tabla_construccion import convertir_a_cero, convertir_a_float, convertir_a_string, convertir_a_int
from liquidar_avaluo_2026 import calcular_avaluo_2026
from post_inconsistencias import validar_vm2_cero
from uso_principal import uso_principal
from uso_principal_terr import uso_principal_terr


# Configuración
pd.set_option('display.float_format', '{:.2f}'.format)


def liquidacion_completa(df_const_liq, base_path='./input/',generar_excel=0):
    """
    Función para calcular liquidación completa de predios
    
    Args:
        df_const_liq: DataFrame con datos de construcciones
        base_path: Ruta base donde se encuentran los archivos txt
    
    Returns:
        df_predio_final: DataFrame con datos de liquidación por predio
    """
    
    # ============================================================
    # 1. CARGAR ARCHIVOS
    # ============================================================

    ruta_especiales = "./input/ESPECIALES/20260303_PREDIOS_ESPECIALES_ACT_2025.xlsx"

    def leer_archivo(path, sep="|", decimal="."):
        ext = os.path.splitext(path)[1].lower()

        if ext == ".parquet":
            return pd.read_parquet(path)

        elif ext in [".txt", ".csv"]:
            codificaciones = ["utf-8", "latin1", "ISO-8859-1", "cp1252"]

            for enc in codificaciones:
                try:
                    return pd.read_csv(
                        path,
                        sep=sep,
                        encoding=enc,
                        decimal=decimal
                    )
                except UnicodeDecodeError:
                    continue

            raise ValueError(
                f"No se pudo leer {path} con las codificaciones probadas."
            )

        else:
            raise ValueError(
                f"Formato no soportado: {ext}"
            )

    file_patterns = {
        "predio": r"predio_",
        "conv": r"convencional",
        "no_conv": r"no_convencional",
        "terreno": r"terreno_"
    }

    dataframes = {k: None for k in file_patterns}

    # Busca txt y parquet
    files = (
        glob.glob(f"{base_path}*.txt") +
        glob.glob(f"{base_path}*.parquet")
    )

    print("📂 Archivos encontrados:")
    for f in files:
        print(" -", f)

    for name, pattern in file_patterns.items():

        matched_files = [
            f for f in files
            if re.search(pattern, os.path.basename(f), re.IGNORECASE)
        ]

        if matched_files:
            try:
                archivo = matched_files[0]

                dataframes[name] = leer_archivo(archivo)

                print(
                    f"✅ {name}: {os.path.basename(archivo)} "
                    f"({os.path.splitext(archivo)[1]})"
                )

            except Exception as e:
                print(f"⚠️ Error leyendo {archivo}: {e}")

        else:
            print(f"⚠️ No se encontró archivo para '{name}'")

    for k, v in dataframes.items():
        print(f"📊 {k}: {'OK' if v is not None else 'None'}")

 

    df_predio = dataframes['predio']
    df_terreno = dataframes['terreno']
    df_const = dataframes['conv']
    df_noconv = dataframes['no_conv']
    df_const_liq = df_const_liq.copy()
    print(f'codigos {df_const_liq['ESPECIAL_2026'].value_counts()}')
    
    # ============================================================
    # 2. PREPARAR DATAFRAMES
    # ============================================================
    
    # Quitar columnas del df_predio


    # Conversiones de tipos
    df_predio = convertir_a_cero(df_predio, ['AREAPRED', 'ARECPRED', 'VTER','AVALPRED', 'VCONST', 'VANEXO', 'ESTRPRED'])
    df_predio = convertir_a_float(df_predio, ['AREAPRED', 'ARECPRED', 'VTER', 'AVALPRED', 'VCONST', 'VANEXO'])
    df_predio = convertir_a_int(df_predio, ['ESTRPRED'])
    df_predio = convertir_a_string(df_predio, ['ID_PREDIO', 'NUMERO_PREDIAL_NACIONAL'])
    df_predio = df_predio.rename(columns={'ACONANEX': 'ACONANEXT'})
    df_const_liq = convertir_a_cero(df_const_liq, ['VM2', 'VM2_MOD', 'LIQ_PARQUEADERO','VM2_ESP_2026','VM2_INT_ESP_2026'])
    df_terreno = convertir_a_string(df_terreno, ['ID_PREDIO'])
    df_terreno = convertir_a_float(df_terreno, ["AMETTERR","VALOTERR"])
    df_const = convertir_a_cero(df_const,['PUNTCONS', 'ACONCONS', 'VALORCONS', 'TPISCONS', 'ANOCONST','DESTINOCONS'])
    df_const = convertir_a_float(df_const, ['ACONCONS', 'VALORCONS'])
    df_const = convertir_a_int(df_const, ['PUNTCONS', 'ANOCONST','TPISCONS','DESTINOCONS'])
    df_const = convertir_a_string(df_const,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL'])
    df_noconv = convertir_a_string(df_noconv,['ID_PREDIO'])

    ### Temporal 
    #df_predio['VANEXO'] = df_predio['VANEXO']*0.7
    # df_predio['VTER'] = df_predio['VTER']*0.7
    # df_predio['AVALPRED'] = df_predio['VTER']+df_predio['VCONST']+df_predio['VANEXO']
    # df_terreno['VALOTERR'] = df_terreno['VALOTERR']

    ### Importar los terrenos especiales
    terr_esp = pd.read_excel(ruta_especiales,sheet_name='Terrenos_especiales')
    terr_esp['ID_PREDIO'] = terr_esp['ID_PREDIO'].astype('string')

    df_terreno['VALOR_M2_SUELO'] = (df_terreno['VALOTERR']/df_terreno['AMETTERR'])/0.7
    df_terreno = pd.merge(df_terreno, terr_esp, on= 'ID_PREDIO', how='left')
    df_terreno['VM2_TERR_2026_COM'] = df_terreno['VM2_TERR_2026_COM'].fillna(0)
    df_terreno['VALOTERR_COM'] = np.where(df_terreno['VM2_TERR_2026_COM']>0,df_terreno['AMETTERR']*df_terreno['VM2_TERR_2026_COM'],df_terreno['AMETTERR']*df_terreno['VALOR_M2_SUELO'])

    # Extraer campos de número predial
    df_predio['CONDICION'] = df_predio['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(int)
    df_predio['COMUNA'] = df_predio['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
    df_predio['ID_TERR'] = df_predio['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
    df_predio = df_predio[df_predio['COMUNA'].isin(['01', '03', '09', '10', '11', '12', '22'])]



    # Obtener valores únicos de construcciones
    
    ### Aplicar uso principal

    cambio_npn = pd.read_excel('./input/otros/CAMBIO_NPN.xlsx')
    cambio_npn = convertir_a_string(cambio_npn,['ID_PREDIO','NPN_ANTERIOR','ID_TERR_ANT'])
    cambio_npn['NO_MEJORAS'] = (
    cambio_npn
        .groupby('ID_TERR_ANT')['ID_TERR_ANT']
        .transform('size')
        .sub(1)
        .clip(lower=0))


    ### cruzar el cambio de NPN
    df_predio = pd.merge(
    df_predio,
    cambio_npn[['ID_PREDIO','NPN_ANTERIOR','ID_TERR_ANT','NO_MEJORAS']],
    on='ID_PREDIO',
    how='left')

    mask_cambio = df_predio['NPN_ANTERIOR'].notna()

    df_predio['ID_TERR'] = np.where(
    mask_cambio,
    df_predio['ID_TERR_ANT'],
    df_predio['NUMERO_PREDIAL_NACIONAL'].astype(str).str[1:21])

    
    df_predio['NO_MEJORAS_EXPORT'] = df_predio.groupby('ID_TERR')['ID_TERR'].transform('size')

    df_predio['DIFERENTES_MEJORAS'] = np.where(abs(df_predio['NO_MEJORAS']-df_predio['NO_MEJORAS_EXPORT'])==0,1,0).astype(int)

    
    df_predio['CAMBIO_NPN'] = (
        df_predio['ID_PREDIO'].isin(cambio_npn['ID_PREDIO'])
    ).astype(int)

    df_predio['CONDICION_ANT'] = df_predio['NPN_ANTERIOR'].str[21:22]

    df_predio['CONDICION_ANT'] = np.where(
    df_predio['NPN_ANTERIOR'].notna(),
    df_predio['NPN_ANTERIOR'].astype(str).str[21:22],'0')


    df_predio['NUM_EDIF_ANT'] = np.where(
    df_predio['NPN_ANTERIOR'].notna(),
    df_predio['NPN_ANTERIOR'].astype(str).str[-4:],
    '0').astype(int)

    df_predio['INFORMALIDAD_P1'] = (
        (df_predio['CONDICION_ANT'] == "5") &
        (df_predio['NUM_EDIF_ANT'] == 1)
    ).fillna(0).astype(int)

    df_predio['INFORMALIDAD_P2'] = (
        (df_predio['CONDICION_ANT'] == "5") &
        (df_predio['NUM_EDIF_ANT'] > 1)
    ).fillna(0).astype(int)



    cambio_npn['ID_TERR'] = cambio_npn['NPN_ANTERIOR'].astype(str).str[1:21].astype(str)
    cambio_npn['NO_PREDIOS'] = (
    cambio_npn.groupby('ID_TERR')
    .transform('size'))

    informalidades_1 = cambio_npn[cambio_npn['NO_PREDIOS']<=2]
    informalidades_2 = cambio_npn[cambio_npn['NO_PREDIOS']>2]

    ids_informalidades_1 = informalidades_1['ID_PREDIO'].unique().tolist()
    ids_informalidades_2 = informalidades_2['ID_PREDIO'].unique().tolist()

    df_predio['INFORMALIDAD_IGUAL_1'] = np.where(
    df_predio['ID_PREDIO'].isin(ids_informalidades_1),
    1,
    0).astype(int)

    df_predio['INFORMALIDAD_MAYOR_1'] = np.where(
    df_predio['ID_PREDIO'].isin(ids_informalidades_2),
    1,
    0).astype(int)

    ids_parte_1 = (
    df_predio[
        df_predio['INFORMALIDAD_P1'].fillna(0).astype(int) == 1
    ]['ID_TERR']
    .unique()
    .tolist())

    df_predio_p1 = df_predio[df_predio['ID_TERR'].isin(ids_parte_1)]

    #df_predio_p1[df_predio_p1['ID_TERR'].isin(['760010100090300180021'])].to_excel('./output/REVISION_P1.xlsx',index=False)

      
    df_predio_p1_usop = uso_principal_terr(df_predio_p1,df_const,df_noconv)
    

    df_predio_p1_usop = df_predio_p1_usop[['ID_TERR','TIPOUSO_AJUSTADO','TIPOPRED_AJUSTADO']].drop_duplicates()


    ## cruzo el predio parte unos con el tipo uso
    df_predio_p1 = df_predio_p1[df_predio_p1['INFORMALIDAD_P1']==1]
    df_predio_p1_usop = pd.merge(df_predio_p1,df_predio_p1_usop, on= 'ID_TERR',how='left')

    df_predio_p2 = df_predio[df_predio['INFORMALIDAD_P1']!=1]
    df_predio_p2_usop = uso_principal(df_predio_p2,df_const,df_noconv)

    df_predio_total = pd.concat([df_predio_p1_usop,df_predio_p2_usop],ignore_index=True)

    df_predio_total['CAMBIA_TIPOUSO'] = np.where(
    df_predio_total['TIPOUSO'] != df_predio_total['TIPOUSO_AJUSTADO'],
    1,
    0)   

    df_predio_total['CAMBIA_TIPOPRED'] = np.where(
        df_predio_total['TIPOPRED'] != df_predio_total['TIPOPRED_AJUSTADO'],
        1,
        0
    )

    
    print(f'✅predios total {len(df_predio_total)- len(df_predio)}')
    print(f'✅ LAS VARIABLES CON USO P {df_predio_total.dtypes}')
    print(f'✅ CAMBIAN DE TIPOUSO {df_predio_total['CAMBIA_TIPOUSO'].value_counts()}')
    print(f'✅ CAMBIAN DE TIPOPRED {df_predio_total['CAMBIA_TIPOPRED'].value_counts()}')

    #Marcar los apartamentos que estan fuera de la regla del muestrep


    df_predio_total['TERRENO_ID'] = df_predio_total['NUMERO_PREDIAL_NACIONAL'].astype(str).str[1:21]

    df_predio_total['AREA_LOTE_PH'] = df_predio_total.groupby('TERRENO_ID')['AREAPRED'].transform('sum')
    df_predio_total['NO_UNIDADES_PH'] = df_predio_total.groupby('TERRENO_ID')['ID_PREDIO'].transform('count')


    # ============================================================
    # 3. PROCESAR CONSTRUCCIONES
    # ============================================================
    
    print(f"\n📋 Columnas de df_const_liq: {df_const_liq.columns.tolist()}")

    df_const_liq['ID_PREDIO'] = df_const_liq['ID_PREDIO'].astype(str)

    # Identificar registros sin tabla
    sin_tabla = df_const_liq[df_const_liq['TABLA_ORIGEN'].isin(['SIN TABLA', 'ESPECIALES', 'MODELO'])]
    print("\n📊 Crosstab USO_LADM vs TABLA_ORIGEN:")
    print(pd.crosstab(sin_tabla['USO_LADM'], sin_tabla['TABLA_ORIGEN']))

    # # Calcular VM2_2026_COM
    df_const_liq['VM2_2026_COM_PRE'] = np.where(
        (df_const_liq['VM2'] == 0) & (df_const_liq['TABLA_ORIGEN'] == 'MODELO'),
        df_const_liq['VM2_MOD'],
        df_const_liq['VM2']
    )

    # # Marcar registros sin valor de construcción
    # df_const_liq['SIN_VALOR_CONST'] = np.where(
    #     df_const_liq['VM2_2026_COM'] == 0,
    #     1,
    #     0
    # )

    df_const_liq['VM2_2026_COM'] = np.where(df_const_liq['VM2_ESP_2026'] >0, 
                                            df_const_liq['VM2_ESP_2026'],
                                            df_const_liq['VM2_2026_COM_PRE'])


    df_const_liq['SIN_VALOR_CONST'] = np.where(
        df_const_liq['VM2_2026_COM'] == 0,
        1,
        0
    )


    print(f"\n✅ Predios únicos: {df_const_liq['ID_PREDIO'].nunique()}")


    # ============================================================
    # 4. PROCESAR TERRENOS
    # ============================================================
    
    

    ### hacer un filtro de df_const_liq mixtos
    # Filtrar los mixtos (hacer copia para evitar warnings)
    df_mixtos = df_const_liq[df_const_liq['METODO_LIQUIDACION'] == 'MIXTO'].copy()
    df_mixtos = df_mixtos[df_mixtos['INTEGRAL_ESP_2026']==0].copy()

    # Clasificar si son mixtos integrales
    df_mixtos['MIXTOS_INTEGRALES'] = np.where(
        (df_mixtos['TABLA_ORIGEN'].isin(['MODELO', 'T12_PARQUEADEROS'])),
        1,
        0
    )

    # Filtrar los NO integrales
    df_mixtos_no_integrales = df_mixtos[df_mixtos['MIXTOS_INTEGRALES'] == 0].copy()

    # Sumar el área no integral por predio
    df_area_no_integral = (
        df_mixtos_no_integrales
        .groupby('ID_PREDIO', as_index=False)
        .agg(AREA_NO_INTEGRAL=('ACONCONS', 'sum'))
    )

    print(f'❌ COLUMNAS DE df_predio_total {df_predio_total.dtypes}')
    # Agregar área del predio
    df_area_no_integral = df_area_no_integral.merge(
        df_predio_total[['ID_PREDIO', 'ARECPRED']],
        on='ID_PREDIO',
        how='left'
    )

    # Porcentaje del área no integral sobre área del predio
    df_area_no_integral['PORCENTAJE_AREAPRED'] = (
        df_area_no_integral['AREA_NO_INTEGRAL'] /
        df_area_no_integral['ARECPRED']
    )
        
    ## Identificar los usos integrales y no integrales
    ## grouby para calcular la suma por ID PREDIO de area construida no integral y dividir sobre arecpred
    ### El porcentaje de lo no integral dataframe ID_PREDIO POR_NO_INTEGRAL

    df_terreno_predio = (df_terreno.groupby('ID_PREDIO')
                        .agg({'VALOTERR_COM': 'sum'})
                        .rename(columns={'VALOTERR_COM': 'VTER_2026_COM_PARCIAL'})
                        .reset_index())
    
    ### merge df_terreno_predio con df_porc_mix
    df_terreno_predio = pd.merge(df_terreno_predio,df_area_no_integral[['ID_PREDIO','PORCENTAJE_AREAPRED']],on='ID_PREDIO', how = 'left')
    df_terreno_predio['PORCENTAJE_AREAPRED'] = df_terreno_predio['PORCENTAJE_AREAPRED'].fillna(0)
    df_terreno_predio['VTER_2026_COM'] = np.where(
    df_terreno_predio['PORCENTAJE_AREAPRED'] == 0,
    df_terreno_predio['VTER_2026_COM_PARCIAL'],
    df_terreno_predio['VTER_2026_COM_PARCIAL'] *1
     # df_terreno_predio['PORCENTAJE_AREAPRED']
    )


    # ============================================================
    # 5. AGREGAR COLUMNAS DE AGRUPACIÓN
    # ============================================================
    
    df_const_liq['NO_CONST'] = df_const_liq.groupby('ID_PREDIO')['ID_PREDIO'].transform('count')
    df_const_liq['CONDICION_JURIDICA'] = df_const_liq['CONDICION'].apply(
        lambda x: 'PH' if x == 9 else 'NPH'
    )
    df_const_liq['GRUPO_COMUNAS'] = df_const_liq['COMUNA'].apply(
        lambda x: '1, 9, 10, 11, 12' if x in ['01', '09', '10', '11', '12'] else '3 Y 22'
    )

    print(f"\n📊 Distribución por grupo de comunas:")
    print(df_const_liq['GRUPO_COMUNAS'].value_counts())

    # Identificar tipo de liquidación
    df_const_liq['TIPO_LIQ'] = 'VM2'
    df_const_liq.loc[df_const_liq['DESTINOCONS'].isin(['007', '008', '036', '037']), 'TIPO_LIQ'] = 'Global'


    # ============================================================
    # 6. CALCULAR VM2_2025_COM
    # ============================================================


    # ============================================================
      ####PROYECCIÓN A VALOR COMERCIAL 2026
    # ============================================================
    
    # df_const_liq['VALORCONS_2026_COM'] = 0
    # df_const_liq.loc[df_const_liq['TABLA_ORIGEN'] == 'T12_PARQUEADEROS' & df_const_liq['ESPECIAL_2026']!=1, 'VALORCONS_2026_COM'] = \
    # df_const_liq['LIQ_PARQUEADERO']
    codigos_afectados = ['007', '008', '036', '037']

    df_const_liq['VALORCONS_2026_COM'] = 0
    df_const_liq['VALOANEX_2026_COM'] = 0

# 1️⃣ Parqueaderos afectados (NO especiales)
    mask_parq_afect = (
    (df_const_liq['TABLA_ORIGEN'] == 'T12_PARQUEADEROS') &
    (df_const_liq['DESTINOCONS'].isin(codigos_afectados)) &
    (df_const_liq['ESPECIAL_2026'] != 1)
    )

    df_const_liq.loc[mask_parq_afect, 'VALORCONS_2026_COM'] = \
        df_const_liq.loc[mask_parq_afect, 'LIQ_PARQUEADERO']

    # 2️⃣ Anexos
    mask_anexos = df_const_liq['TABLA_ORIGEN'] == 'T10_ANEXOS'

    df_const_liq.loc[mask_anexos, 'VALOANEX_2026_COM'] = \
        df_const_liq.loc[mask_anexos, 'AREA_CONST'] * df_const_liq.loc[mask_anexos, 'VM2_2026_COM']

    # 3️⃣ Resto de construcciones
    mask_resto = ~(mask_parq_afect | mask_anexos)

    df_const_liq.loc[mask_resto, 'VALORCONS_2026_COM'] = \
        df_const_liq.loc[mask_resto, 'AREA_CONST'] * df_const_liq.loc[mask_resto, 'VM2_2026_COM']


    df_const_liq.loc[df_const_liq['ID_PREDIO'] == '130817', ['ID_PREDIO', 'USO_LADM','DESTINOCONS','VALORCONS_2026_COM']]
    print(df_const_liq.loc[df_const_liq['ID_PREDIO'] == '130817', ['ID_PREDIO', 'USO_LADM','DESTINOCONS','VALORCONS_2026_COM']])

    # Agrupar construcciones por predio
    df_liquidacion_const = (df_const_liq.groupby('ID_PREDIO')
                    .agg({
                        'VALORCONS_2026_COM': 'sum',
                        'VALOANEX_2026_COM': 'sum'
                    })
                    .rename(columns={
                        'VALORCONS_2026_COM': 'VCONST_2026_COM',
                        'VALOANEX_2026_COM': 'VANEXO_2026_COM'
                    })
                    .reset_index())

    
    # Merge construcciones
    df_predio_total = df_predio_total.merge(df_liquidacion_const, on='ID_PREDIO', how='left')

    # Merge con terreno
    df_predio_total = df_predio_total.merge(df_terreno_predio[['ID_PREDIO','VTER_2026_COM']], on='ID_PREDIO', how='left')

    # Identificar registros sin valor de terreno
    # sin_valor_ter = df_predio_total[
    #     df_predio_total['VTER_2026_COM'].isna() & 
    #     (df_predio_total['GRUPO_COMUNAS'] == '1, 9, 10, 11, 12')
    # ]
    #print(f"\n⚠️ Registros sin VTER_2026_COM: {len(sin_valor_ter)}")
    df_predio_total['GRUPO_COMUNAS'] = df_predio_total['COMUNA'].apply(
        lambda x: '1, 9, 10, 11, 12' if x in ['01', '09', '10', '11', '12'] else '3 Y 22'
    )


    # ============================================================
    # 10. MARCAR INFORMALIDAD Y MÉTODOS DE LIQUIDACIÓN
    # ============================================================
    
    # Marcar informalidad
    df_predio_total['INFORMALIDAD'] = np.where(
        ((df_predio_total['CONDICION'] == 5) & 
         (df_predio_total["NUMERO_PREDIAL_NACIONAL"].astype(str).str[-1] != "1")) | 
        (df_predio_total['CONDICION'] == 2),
        1, 0
    )

    # Identificar métodos de liquidación
    integrales = df_const_liq[df_const_liq['METODO_LIQUIDACION'] == 'INTEGRAL']['ID_PREDIO'].unique()
    mixtos = df_const_liq[df_const_liq['METODO_LIQUIDACION'] == 'MIXTO']['ID_PREDIO'].unique()
    terr_const = df_const_liq[df_const_liq['METODO_LIQUIDACION'] == 'TABLA + TERRENO']['ID_PREDIO'].unique()
    solo_const = df_const_liq[df_const_liq['METODO_LIQUIDACION'] == 'TABLA SIN TERRENO']['ID_PREDIO'].unique()
    predios_especiales_2026 = df_const_liq[df_const_liq['ESPECIAL_2026'] == 1]['ID_PREDIO'].unique()
    predios_especiales_2026_integrales = df_const_liq[df_const_liq['INTEGRAL_ESP_2026'] == 1]['ID_PREDIO'].unique()
    predios_informales = df_const_liq[df_const_liq['INFORMALIDAD'] == 1]['ID_PREDIO'].unique()
   
    


    df_predio_total['INTEGRAL'] = np.where(df_predio_total['ID_PREDIO'].isin(integrales), 1, 0)
    df_predio_total['MIXTO'] = np.where(df_predio_total['ID_PREDIO'].isin(mixtos), 1, 0)
    df_predio_total['TERRENO_MAS_CONST'] = np.where(df_predio_total['ID_PREDIO'].isin(terr_const), 1, 0)
    df_predio_total['CONST_SIN_TERRENO'] = np.where(df_predio_total['ID_PREDIO'].isin(solo_const), 1, 0)
    df_predio_total['ESPECIAL_2026'] = np.where(df_predio_total['ID_PREDIO'].isin(predios_especiales_2026), 1, 0)
    df_predio_total['INTEGRAL_ESP_2026'] = np.where(df_predio_total['ID_PREDIO'].isin(predios_especiales_2026_integrales), 1, 0)
    df_predio_total['INFORMALIDAD'] = np.where(df_predio_total['ID_PREDIO'].isin(predios_informales), 1, 0)
    # ============================================================
    # 11. CALCULAR AVALÚO 2026 SEGÚN CONDICIONES
    # ============================================================

   

    df_predio_total = calcular_avaluo_2026(df_predio_total)
    

    #### HACER VERIFICACIONES

    confis =0.7
    df_predio_total['VTER_2026_CAT'] = (df_predio_total['VTER_2026_COM']*confis).round(-3)
    df_predio_total['VCONST_2026_CAT'] = (df_predio_total['VCONST_2026_COM']*confis).round(-3)
    df_predio_total['VANEXO_2026_CAT'] = (df_predio_total['VANEXO_2026_COM']*confis).round(-3)
    df_predio_total['AVALUO_2026_CAT'] = (df_predio_total['AVALUO_COM_2026']*confis).round(-3)
    df_predio_total['DIFERENCIA_AVALUO'] = abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT'])

    print(df_predio_total.dtypes)
    ### condiciones de aprobado

    condiciones_aprobado = [

    # 1. INTEGRALES E INFORMALIDAD
    (
        (df_predio_total['VTER'] == 0) & 
        (df_predio_total['INTEGRAL'] == 1) &
        (abs(df_predio_total['VANEXO'] - df_predio_total['VANEXO_2026_CAT']) <= 1000) &
        (abs(df_predio_total['VCONST'] - df_predio_total['VCONST_2026_CAT']) <= 1000) &
        (abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT']) <= 1000)
    ),

    (
        (df_predio_total['VTER'] == 0) & 
        (df_predio_total['INFORMALIDAD'] == 1) &
        (abs(df_predio_total['VANEXO'] - df_predio_total['VANEXO_2026_CAT']) <= 1000) &
        (abs(df_predio_total['VCONST'] - df_predio_total['VCONST_2026_CAT']) <= 1000) &
        (abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT']) <= 1000)
    ),

    # 2. SOLO TERRENO
    (
        (df_predio_total['VTER'] > 0) &
        (abs(df_predio_total['VTER'] - df_predio_total['VTER_2026_CAT']) <= 1000) &
        (df_predio_total['VCONST_2026_CAT'] == 0) &
        (df_predio_total['VANEXO_2026_CAT'] == 0) &
        (abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT']) <= 1000)
    ),

    # 3. SOLO TERRENO + ANEXOS
    (
        (df_predio_total['VTER'] > 0) &
        (abs(df_predio_total['VTER'] - df_predio_total['VTER_2026_CAT']) <= 1000) &
        (abs(df_predio_total['VANEXO'] - df_predio_total['VANEXO_2026_CAT']) <= 1000) &
        (df_predio_total['VCONST'] == 0) &
        (abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT']) <= 1000)
    ),

    # 4. TERRENO + CONVENCIONALES + ANEXOS
    (
        (df_predio_total['VTER'] > 0) &
        (abs(df_predio_total['VTER'] - df_predio_total['VTER_2026_CAT']) <= 1000) &
        (abs(df_predio_total['VANEXO'] - df_predio_total['VANEXO_2026_CAT']) <= 1000) &
        (abs(df_predio_total['VCONST'] - df_predio_total['VCONST_2026_CAT']) <= 1000) &
        (abs(df_predio_total['AVALPRED'] - df_predio_total['AVALUO_2026_CAT']) <= 1000)
    )
]

    aprobado = [
        'APROBADO INTEGRALES',
        'APROBADO INFORMALIDAD',
        'APROBADO SOLO TERRENO',
        'APROBADO TERRENO + ANEXOS',
        'APROBADO TERRENO + CONVENCIONALES + ANEXOS'
    ]

    df_predio_total['OBSERVACION'] = np.select(
        condiciones_aprobado,
        aprobado,
        default='NO_APROBADO'
    )


    df_predio_total['ESTADO_1'] = np.where(
    df_predio_total['OBSERVACION'].isin(['NO_APROBADO']),
    'NO_APROBADO',
    'REVISION'
    )

    df_predio_total['ESTADO'] = np.where(
    (df_predio_total['OBSERVACION'].isin(['NO_APROBADO'])) & (~df_predio_total['ESTADO_1'].isin(['REVISION'])) ,
    'NO_APROBADO',
    'APROBADO'
    )

    print(f'CONTEO POR ESTADO DEL PREDIO {df_predio_total['ESTADO'].value_counts()}')

    otras_condiciones = [

    ((df_predio_total['INTEGRAL'] == 1) & (df_predio_total['VTER']>0)),
    ((df_predio_total['INFORMALIDAD'] == 1) & (df_predio_total['VTER']>0)),
    ((df_predio_total['MIXTO'] == 1) & (df_predio_total['VTER'] == 0)),
    ((df_predio_total['TERRENO_MAS_CONST'] == 1) & (df_predio_total['VTER']==0)),


    ]

    observacion = [
    'INTEGRAL Y TIENE TERRENO',
    'INFORMAL Y TIENE TERRENO',
    'MIXTO MAL CALCULADO EL TERRENO',
    'NO SE SUMO EL TERRENO'
    ]

    df_predio_total['OBSERVACION'] = np.select(otras_condiciones, observacion, default='APROBADO')


    # ============================================================
    # 12. CALCULAR VARIACIONES
    # ============================================================

    df_predio_2025 = pd.read_parquet('./input/otros/predio_20251209_150206.parquet')

    df_predio_2025 = df_predio_2025.rename(columns={'AVALPRED':'AVALPRED_2025'})
    df_predio_2025 = convertir_a_cero(df_predio_2025,['AVALPRED_2025'])
    df_predio_2025 = convertir_a_float(df_predio_2025,['AVALPRED_2025'])
    df_predio_2025 = convertir_a_string(df_predio_2025,['ID_PREDIO'])

    df_predio_total = pd.merge(df_predio_total, df_predio_2025[['ID_PREDIO','AVALPRED_2025']], on='ID_PREDIO',  how='left')

    
    def calcular_variacion(val_2026, val_2025):
        if pd.notna(val_2026) and pd.notna(val_2025) and val_2026 > 0 and val_2025 > 0:
            return round((val_2026 / val_2025 - 1) * 100, 2)
        return np.nan

    df_predio_total['VAR_AVALUO'] = df_predio_total.apply(
        lambda x: calcular_variacion(x['AVALPRED'], x['AVALPRED_2025']), axis=1)
    
    df_predio_total['VAR_ABSOLUTA'] = ((df_predio_total['AVALPRED'] - df_predio_total['AVALPRED_2025'])).round(3)
    # ============================================================
    # 13. FLAGS DE BAJA
    # ============================================================
    
    df_predio_total['BAJO_AVALUO'] = ((df_predio_total['AVALPRED'] - df_predio_total['AVALPRED_2025']) < 0).astype(int)

    # ============================================================
    # 14. CREAR RANGOS DE VARIACIÓN
    # ============================================================
    
    def crear_rango(valor):

        if pd.isna(valor):
            return "19. Sin comparación 2025"
        
        if valor < -100:
            return "(1. Menor a menos 100]"
        elif valor <= -50:
            return "(2. Entre -100% y -50%]"
        elif valor <= -30:
            return "(3. Entre -50% y -30%]"
        elif valor <= -20:
            return "(4. Entre -30% y -20%]"
        elif valor <= -10:
            return "(5. Entre -20% y -10%]"
        elif valor < -5:
            return "(6. Entre -10% y -5%)"
        elif valor < 0:
            return "(Entre -5% y 0%)"
        elif valor == 0:
            return "[8. Igual a 0%]"
        elif valor < 5:
            return "(9. Entre 0% y 5%)"
        elif valor <= 10:
            return "(10. Entre 5% y 10%]"
        elif valor <= 20:
            return "(11. Entre 10% y 20%]"
        elif valor <= 50:
            return "(12. Entre 20% y 50%]"
        elif valor <= 80:
            return "(13. Entre 50% y 80%]"
        elif valor <= 100:
            return "(14. Entre 80% y 100%]"
        elif valor <= 150:
            return "(15. Entre 100% y 150%]"
        elif valor <= 200:
            return "(16. Entre 150% y 200%]"
        elif valor <= 300:
            return "(17. Entre 200% y 300%]"
        else:
            return "(18. Mayor a 300%]"


    # Aplicar rangos
    df_predio_total['RANGO_AVALUO'] = df_predio_total['VAR_AVALUO'].apply(crear_rango)


    # ============================================================
    # 15. MARCA DE LIQUIDACIÓN
    # ============================================================
    
    # Primero calcular construcciones con valor
    df_const_liq['CONST_OK'] = np.where(
        (df_const_liq['VALORCONS_2026_COM'] > 0) | (df_const_liq['VALOANEX_2026_COM'] > 0),
        1,
        0
    )
    
    df_const_verificacion = (df_const_liq.groupby('ID_PREDIO')
        .agg({'CONST_OK': 'sum', 'CONSTRUCCION_ID': 'count'})
        .reset_index())
    
    df_const_verificacion.columns = ['ID_PREDIO', 'CONST_CON_VALOR', 'TOTAL_CONST']
    
    df_predio_total = df_predio_total.merge(
        df_const_verificacion[['ID_PREDIO', 'CONST_CON_VALOR', 'TOTAL_CONST']],
        on='ID_PREDIO',
        how='left'
    )
    
    df_predio_total['CONST_CON_VALOR'] = df_predio_total['CONST_CON_VALOR'].fillna(0).astype(int)
    df_predio_total['TOTAL_CONST'] = df_predio_total['TOTAL_CONST'].fillna(0).astype(int)
    
    # Ahora la marca con 4 categorías

    df_predio_total =  convertir_a_cero(df_predio_total, ['AREAPRED', 'ARECPRED','ACONANEXT'])

# Condiciones en orden de evaluación
    condiciones = [

# 1. LIQUIDACIÓN PARCIAL (prioridad)
    (
    (df_predio_total['TOTAL_CONST'] > 0) &
    (df_predio_total['CONST_CON_VALOR'] > 0) &
    (df_predio_total['CONST_CON_VALOR'] < df_predio_total['TOTAL_CONST'])
),

    # 2. FALTA TERRENO
    (
    (df_predio_total['TERRENO_MAS_CONST'] == 1) &
    (df_predio_total['VTER_2026_COM'] == 0) &
    (df_predio_total['INFORMALIDAD'] == 0) 
  
    ),

    (df_predio_total['MIXTO'] == 1),
    
  
    ]   


    # Resultados en el mismo orden
    resultados = [
    'Liquidación parcial',
    'Falta terreno',
    'Liquidado mixto'
    ]


    # Valor por defecto si no cae en ningún caso
    df_predio_total['MARCA_LIQUIDACION'] = np.select(
        condiciones,
        resultados,
        default='Liquidado'
    )

    
    
    print("CONTEOS MARCA_LIQUIDACION:")
    print(df_predio_total["MARCA_LIQUIDACION"].value_counts())

  
    

    

    print(f' COLUMNAS DE CONSTRUCCIONES (FINAL){df_predio_total.columns.to_list()}')
   


    # ============================================================
    # 16. PREPARAR DATOS DE SALIDA
    # ============================================================

    df_const_liq_p = (
    df_const_liq
    .sort_values('VALORCONS_2026_COM', ascending=False)
    .drop_duplicates(subset='ID_PREDIO')
    [['ID_PREDIO', 'TABLA_ORIGEN', 'METODO_LIQUIDACION']]
    )

    df_predio_total = pd.merge(df_predio_total,df_const_liq_p, on='ID_PREDIO', how='left')
    
    print(f'CONTEO ESPECIALES {df_predio_total['ESPECIAL_2026'].value_counts()}')

    # Columnas de predios
    columnas_predio = ['ID_PREDIO','NUMERO_PREDIAL_NACIONAL','ZHF','ID_TERR', 'DIREPRED','COMUNA', 'AREAPRED', 'ARECPRED', 'ACONANEXT', 'TABLA_ORIGEN', 
                       'METODO_LIQUIDACION','MARCA_LIQUIDACION',
                       'CONDICION',  'INFORMALIDAD','CAT_USO',
                       'VTER','VTER_2026_CAT','VCONST','VCONST_2026_CAT',
                        'VANEXO','VANEXO_2026_CAT',
                        'AVALPRED', 'AVALUO_2026_CAT','DIFERENCIA_AVALUO','AVALPRED_2025',        
                       'VAR_AVALUO',  'RANGO_AVALUO', 'ESPECIAL_2026','INTEGRAL_ESP_2026','ORIGEN','OBSERVACION','ESTADO','TIPOUSO','TIPOUSO_AJUSTADO','TIPOPRED','TIPOPRED_AJUSTADO',
                       'CAMBIA_TIPOUSO','CAMBIA_TIPOPRED','INFORMALIDAD_P1','INFORMALIDAD_P2','INFORMALIDAD_IGUAL_1','INFORMALIDAD_MAYOR_1','DIFERENTES_MEJORAS']

    # Filtrar solo columnas que existan
    columnas_predio_existentes = [col for col in columnas_predio if col in df_predio_total.columns]


    df_predio_final = (df_predio_total[columnas_predio_existentes]
                       .drop_duplicates(subset=['ID_PREDIO'], keep='first'))
    
    print(f'VARIABLES FINALES {df_predio_final.dtypes}')


    preliquidacion = pd.read_parquet('./input/otros/PREDIO_20260307.parquet')
    preliquidacion = preliquidacion.rename(columns={'AVALUO_COM_2026':'AVALUO_COM_2026_PRE'})

    df_predio_final['CAMBIO_NPN'] = np.where(df_predio_final['ID_PREDIO'].isin(cambio_npn['ID_PREDIO']),1,0)
    
    df_predio_final = pd.merge(df_predio_final,preliquidacion[['ID_PREDIO','AVALUO_COM_2026_PRE']],on="ID_PREDIO",how='left')
    df_predio_final['DIF_PRELIQ'] = abs(df_predio_final['AVALUO_COM_2026_PRE']*0.7 - df_predio_final['AVALUO_2026_CAT'])

    

    id_hoyo = ["132481",	"132482",	"132483",	"634165",	"626550",	"626551",	"626552",	"634523",	"125660",	"125661",	
               "125662",	"125663",	"125664",	"132487",	"132503",	"132504",	"132505",	"132506",	"132511",	"132512",
                   	"125688",	"125689",	"125690",	"125691",	"125692",	"125693",	"125695",	"132517",	"132533",	"132534",	
                    "132535",	"132536",	"132537",	"132538",	"132539",	"132540"]

    cambio_const = [    
    ## otros
    "594007",	"617246",	"622658",	"632797",	"830074",	
    "830077",	"856648",	"856650",	"964018",	"42796",	"43579",	"63202",	
    "83607",	"83680",	"84117",			
    "85270",	"87337",	"87975",	"89415",	"92065",	"92394",	"92637",	"92738",	"92739",	"92746",
	"93032",	"97544",	"112033",	"112034",	"112541",	"112544",	"112545",	"116220",	"121472",	"122273",
	"122636",	"123083",	"123087",	"123280",	"123371",	"123514",	"123567",	"124283",	"125167",	"125168",
	"125187",	"126098",	"126271",	"126361",	"126666",	"127012",	"127096",	"127124",	"127189",	"127247",
	"127525",	"127798",	"127869",	"127932",	"131465",	"133130",	"133219",	"134274",	"134431",	"134854",
	"134883",	"135270",	"135339",	"135340",	"135341",	"135342",	"135476",	"135666",	"136026",	"136151",
	"136197",	"136267",	"136595",	"136722",	"136867",	"137821",	"138211",	"139075",	"139326",	"139776",
	"143776",	"144235",	"144263",	"144655",	"144683",	"144702",	"144915",	"145115",	"145534",	"145631",
	"145658",	"145772",	"145773",	"145774",	"146049",	"146135",	"146136",	"183390",	"185105",	"185536",
	"185619",	"185635",	"187116",	"187281",	"187551",	"188498",	"190076",	"190925",	"191409",	"192113",
	"192243",	"192244",	"192395",	"192768",	"193898",	"194041",	"194334",	"195286",	"195430",	"195981",
	"311137",	"311570",	"313472",	"320893",	"444654",	"444922",	"450008",	"450541",	"451606",	"452587",
	"454460",	"455422",	"455761",	"455915",	"455985",	"456158",	"457609",	"457964",	"458043",	"458272",
	"460326",	"461705",	"461929",	"462680",	"463367",	"464035",	"464637",	"465060",	"466386",	"466933",
	"468719",	"469777",	"470057",	"470089",	"472498",	"472882",	"476634",	"477070",	"477079",	"479940",
	"663089",	"663764",	"668279",	"668745",	"668746",	"668747",	"668748",	"668753",	"668754",	"669515",
	"675126",	"675127",	"678794",	"701971",	"707802",	"708725",	"739169",	"746597",	"747987",	"748345",
	"750614",	"750615",	"751063",	"766741",	"766742",	"766743",	"769960",	"772969",	"777185",	"788675",
	"789871",	"792561",	"800779",	"801469",	"854310",	"854403",	"854784",	"868731",	"869112",	"870509",
	"870513",	"870514",	"870516",	"874292",	"874295",	"874296",	"874297",	"874299",	"874300",	"874301",
	"888401",	"902794",	"902800",	"902805",	"902809",	"902817",	"902823",	"902832",	"902836",	"902840",
	"903647",	"903648",	"928050",	"951881",	"960649",	"963399",	"963400",	"963401",	"963410",	"1010279",
	"1010280",	"1010281",	"1010282",	"59746",	"112570",	"121823",	"130076",	"135003",	"140045",	"192229",
	"262771",	"265437",	"289017",	"305081",	"431431",	"474925",	"957194",	"960304",	"960305",	"960307",
	"989841",	"121050",	"308596",	"467640",	"310734",	"89460",	"89504",	"91650",	"97311",	"98479",
	"98576",	"98748",	"98749",	"98807",	"98844",	"99275",	"100935",	"103437",	"103438",	"103702",
	"103778",	"106972",	"109928",	"111194",	"113147",	"118076",	"122235",	"125079",	"125604",	"125622",
	"125631",	"125809",	"125932",	"126034",	"128937",	"128940",	"129271",	"129556",	"129731",	"129788",
	"129829",	"130183",	"130186",	"130418",	"130614",	"130801",	"130848",	"130945",	"130960",	"131555",
	"131577",	"132309",	"518675",	"1065358",	"88602",	"89557",	"95506",	"95644",	"96720",	"97338",
	"113299",	"113900",	"121247",	"121284",	"121852",	"122303",	"122581",	"123516",	"123601",	"128000",
	"136499",	"138069",	"138823",	"194531",	"200405",	"204519",	"210079",	"309071",	"447324",	"449107",
	"453001",	"455540",	"458540",	"462261",	"465058",	"466332",	"468020",	"891466",	"305368",	"305430",
    
        ]
    
    
    cambio_avaluo = ["129210",	"95917",	"130614",	"580693",	"1003703",	"89860",	"132537",	"125662",	"132540",	"125664",
	"805984",	"96860",	"129726",	"111168",	"532895",	"132503",	"125663",	"619322",	"580541",	"98091" ]

    df_predio_final['MARCA'] = np.where(df_predio_final['ID_PREDIO'].isin(id_hoyo),"HOYO Y PILOTO",
                                  np.where(df_predio_final['ID_PREDIO'].isin(cambio_const),"CAMBIO CONST",
                                        np.where(df_predio_final['ID_PREDIO'].isin(cambio_avaluo),"CAMBIO_AVALUO", "SIN MARCA")))


    aprobados = df_predio_final[df_predio_final['ESTADO']=='APROBADO']
    

    predios_aprobados = len(aprobados)


    aprobados = aprobados[aprobados['MARCA'] == 'SIN MARCA']


    print(f'✅predios aprobados inicial {predios_aprobados}')
    print(f'✅predios  no aprobados  {predios_aprobados- len(aprobados)}')
    print(f'✅predios aprobados final {len(aprobados)}')

    no_aprobados = df_predio_final[~df_predio_final['ID_PREDIO'].isin(aprobados['ID_PREDIO'])]
    print(f'✅predios  NO aprobados {len(no_aprobados)}')

    validar_vm2_cero(df_const_liq, exportar=True)
    print(f'AQUI LOS QUE NO ESTAN LIQUDANDO {df_predio_final.loc[df_predio_final['AVALUO_2026_CAT'] == 0].shape[0]}')

    # ============================================================
    # 16.1 EXCLUIR PREDIOS EN REVISIÓN
    # ============================================================
    print("\n🔍 Filtrando predios en revisión...")

    
    # ============================================================
    # 17. GUARDAR RESULTADOS
    # ============================================================
    
    fecha_hoy = datetime.now().strftime("%Y%m%d")
    nombre_archivo = f'./results/REVISION_LIQUIDACION_{fecha_hoy}.xlsx'

    ## imprimir formato largo
    #df_predio_final_long.to_parquet('./results/PRELIQUIDACION_FORMATO_LARGO.txt')


    if generar_excel:
        with pd.ExcelWriter(nombre_archivo, engine='openpyxl') as writer:
               aprobados.to_excel(writer, sheet_name='APROBADOS', index=False)
               no_aprobados.to_excel(writer, sheet_name='NO APROBADOS', index=False)

    print(f"✅ Archivo Excel generado: {nombre_archivo}")


   

    print(f"\n✅ Archivo guardado: {nombre_archivo}")
    print(f"📊 Total predios procesados: {len(df_predio_final)}")





    return df_predio_final


