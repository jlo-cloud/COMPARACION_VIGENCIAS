import pandas as pd
import numpy as np
from dbfread import DBF
import re
import pyarrow.feather as feather
import os
from io import StringIO
import re
import warnings
import glob
from datetime import datetime
import gc

from model_liq import ejecutar_modelos
import insumos
from tabla_construccion import convertir_a_cero, convertir_a_float,convertir_a_string



warnings.filterwarnings("ignore")

### Cargar archivos
# 1. Tabla df_const

def tablas_liquidacion(df_const):  

    print(f'Tipo de columnas df const {df_const.dtypes}')
  
    ############ CRUZAR TABLAS
    comunas_act_2025 = ['01','09','10','11','12']
        
    comunas_act_2024 = ['02','03','04','08','17','19','22']

    #df_const['ZHF'] = df_const['ZHF'].astype(str).where(df_const['ZHF'].notna(), np.nan)
    df_const = df_const[df_const['ZHF'].notna()]
    # La tipologia son las TRES ULTIMAS del ZHF, sin importar el largo. El
    # codigo viene en 11 y en 13 caracteres, y con str[8:11] los de 13 quedaban
    # corridos dos posiciones: devolvian 110, 210, 310... que no existen como
    # tipologia, asi que esos predios caian al estrato teniendo zona.
    # Menos de 11 caracteres no es un ZHF (hay filas en '0' y codigos rurales
    # con otra estructura): esas quedan vacias.
    # La ZHF llega como entero en la base de hoy; en 2025 llegaba como texto.
    _zhf = df_const['ZHF'].astype(str).str.strip()
    _tipologia = _zhf.str[-3:].where(_zhf.str.len() >= 11, '')
    df_const['TIPOLOGIA_ZHF'] = _tipologia.astype('string')
    df_const['ACT_ECON'] = _tipologia.str[:2]
    df_const['TIPO_SEGUN_ACT'] = _tipologia.str[2:]
    df_const['ACTIVIDAD'] = _tipologia.str[1:]
    # Transformar valores
    # Primero aseguramos que los valores sean numéricos

    df_const['DESTINOCONS'] = df_const['DESTINOCONS'].astype(str).str.zfill(3)
    df_const['DESTANEX'] = df_const['DESTANEX'].astype(str).str.zfill(3)

    # CONDICION llega como TEXTO ('0', '9', '5'...). Sin esto, las ocho
    # comparaciones 'CONDICION == 9' de mas abajo comparan '9' == 9, que es
    # False siempre: ni la rama de MODELO ni las de PH se aplican nunca.
    df_const['CONDICION'] = pd.to_numeric(df_const['CONDICION'], errors='coerce')
    df_const['CONDICION'] = df_const['CONDICION'].fillna(0).round(0).astype('int64')
    # Luego aplicamos el formato con ceros a la izquierda, ignorando valores nulos

    #df_const['ESTRATO_PARQ'] = df_const['ESTRATO_PARQ'].astype(str).str.replace('.0', '')
    df_const['PUNTCONS'] = pd.to_numeric(df_const['PUNTCONS'], errors='coerce')
    df_const['PUNTCONS'] = df_const['PUNTCONS'].fillna(0)
    df_const['PUNTCONS'] = df_const['PUNTCONS'].round(0).astype('int64') 

    df_const['TIPOANEXO'] = pd.to_numeric(df_const['TIPOANEXO'], errors='coerce')
    df_const['TIPOANEXO'] = df_const['TIPOANEXO'].fillna(0)
    df_const['TIPOANEXO'] = df_const['TIPOANEXO'].round(0).astype('int64')

    df_const['ESTRPRED'] = pd.to_numeric(df_const['ESTRPRED'], errors='coerce')
    df_const['ESTRPRED'] = df_const['ESTRPRED'].fillna(0)
    df_const['ESTRPRED'] = df_const['ESTRPRED'].round(0).astype('int64')

    df_const['VM2_ESP'] = np.where(df_const['ESPECIAL'] == 1, df_const['VALOR_M2'],0) ## este es el especial 2025
    df_const['VM2_ESP'] = pd.to_numeric(df_const['VM2_ESP'], errors='coerce')  # Agregar esto

    df_const['ACONCONS'] = pd.to_numeric(df_const['ACONCONS'], errors='coerce')

    df_const['TIPO_PARQ'] = np.where(
        df_const['DESTINOCONS'].isin(["007", "008", "036", "037"]),  # Solo para estos códigos
        np.where(df_const['ACONCONS'] <= 50, "Sencillo", "Doble"),  # Sencillo si ACONCONS < 17, Doble en caso contrario
        pd.NA  # Dejar vacío para los demás códigos
    )


   
    print(df_const['TIPOLOGIA_ZHF'].value_counts())

    condiciones_tabla = [

        # -------------------------------------------
        # 1. ESPECIAL
        # -------------------------------------------
        (
            (
                df_const['DESTINOCONS'].isin(['020','023']) &
                df_const['COMUNA'].isin(['01','09','10','11','12','03','22'])
            )
        ),

        # -------------------------------------------
        # 2. MODELO
        # -------------------------------------------
        # PH en condicion 9 va por modelo en todas las comunas, como en 2024 y
        # 2027. Antes estaba limitado a 01, 03, 09, 10, 11, 12 y 22.
        (
            df_const['DESTINOCONS'].isin(['001', '028', '034'])
            & (df_const['CONDICION'] == 9)
        ),
        
              
            # |
         # -------------------------------------------
        # 3. RESIDENCIAL POR ESTRATOS (T1) CONDICION 9 
        # -------------------------------------------
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 1) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 2)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 3)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 4)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 5)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'].isin([0,6]))&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),
        
        
        ##### CON LAS ZONAS COND 9 
        
                (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 1) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 2)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 3)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 4)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 5)&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),

        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'].isin([0,6]))&
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(['01','09','10','11','12'])
        ),
        
        
        
        #####

        # -------------------------------------------
        # 3. RESIDENCIAL POR ESTRATOS (T1)
        # -------------------------------------------
        
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 1) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
        ),
   

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 2) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
       
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 3) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(["001",'011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 4) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 5) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'].isin([0,6])) &
            (
                # CONDICION 9 en comunas 03, 22
                ((df_const['CONDICION'] == 9) & df_const['COMUNA'].isin(['03','22'])) |
                # O cualquier otra condición diferente de 9 en todas las comunas
                (df_const['CONDICION'] != 9)
            )
        ),

        # -------------------------------------------
        # 4. EDIFICIOS (T2)
        # -------------------------------------------
        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 1)
        ),

        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 2)
        ),

        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 3)
        ),

        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 4)
        ),

        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 5)
        ),

        (
            df_const['DESTINOCONS'].isin(["003"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'].isin([0,6]))
        ),

        # -------------------------------------------
        # 5. COMERCIAL T3
        # -------------------------------------------
        (
            df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","042","049","028"]) &
            df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])
        ),

        (
            df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","042","049","028"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016','021','022','023']))
        ),

        # -------------------------------------------
        # 6. INDUSTRIAL T4
        # -------------------------------------------
        (
            df_const['DESTINOCONS'].isin(["009","018","047","048"]) &
            df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])
        ),

        (
            df_const['DESTINOCONS'].isin(["009","018","047","048"]) &
            df_const['TIPOLOGIA_ZHF'].notna() &
            (~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016','031','032','033']))
        ),

        # -------------------------------------------
        # 7. OTRAS CATEGORÍAS (GENERAL)
        # -------------------------------------------
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="011")),
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="012")),
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="013")),
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="014")),
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="015")),
        (df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) & (df_const['TIPOLOGIA_ZHF']=="016")),

        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="011")),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="012")),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="013")),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="014")),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="015")),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF']=="016")),

        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","042","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="021")),
        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","042","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="022")),
        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","042","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="023")),

        (df_const['DESTINOCONS'].isin(["009","018","047","048"]) & (df_const['TIPOLOGIA_ZHF']=="031")),
        (df_const['DESTINOCONS'].isin(["009","018","047","048"]) & (df_const['TIPOLOGIA_ZHF']=="032")),
        (df_const['DESTINOCONS'].isin(["009","018","047","048"]) & (df_const['TIPOLOGIA_ZHF']=="033")),

        # Institucional
        df_const['DESTINOCONS'].isin(["050","051","055","068","070"]),
        df_const['DESTINOCONS'].isin(["054","067"]),
        df_const['DESTINOCONS'].isin(["073","074","075","076","033","052","032",'034']),
        df_const['DESTINOCONS'].isin(["060","061","053"]),
        # Hoteles
        df_const['DESTINOCONS'].isin(["030","031"]),

        # Anexos
        df_const['DESTANEX'].isin([
            "077","078","113","110","080","081","082","114","085","086","089",
            "092","094","111","098","100","101","102","103","104","105","109",
            "112","115","079","083","084","091","097","118","056","088","116"
        ]),

        # C. comerciales
        df_const['DESTINOCONS'].isin(["019","043","022"]),

        # Parqueaderos
        df_const['DESTINOCONS'].isin(["006","007","008","027","036","037"]),

        # Unidad deportiva
        df_const['DESTINOCONS'].isin(["071"]),
        
        #pensiones y residencias
        df_const['DESTINOCONS'].isin(["038"]) & df_const['COMUNA'].isin(['01','09','10','11','12']),

        df_const['DESTINOCONS'].isin(["038"]) & df_const['COMUNA'].isin(['03','22']),

        df_const['DESTINOCONS'].isin(["017"])
     

    ]
    for i, cond in enumerate(condiciones_tabla):
        print(f"Condición {i} → tipo: {type(cond)} | válido: {isinstance(cond, (pd.Series, np.ndarray))}")
    valores_tipomode = [
        'ESPECIALES',
        'MODELO',
        'T1_RESIDENCIAL_011_9',
        'T1_RESIDENCIAL_012_9',
        'T1_RESIDENCIAL_013_9',
        'T1_RESIDENCIAL_014_9',
        'T1_RESIDENCIAL_015_9',
        'T1_RESIDENCIAL_016_9',
        #
        'T1_RESIDENCIAL_011_9',
        'T1_RESIDENCIAL_012_9',
        'T1_RESIDENCIAL_013_9',
        'T1_RESIDENCIAL_014_9',
        'T1_RESIDENCIAL_015_9',
        'T1_RESIDENCIAL_016_9',
        #
        'T1_RESIDENCIAL_011',
        'T1_RESIDENCIAL_012',
        'T1_RESIDENCIAL_013',
        'T1_RESIDENCIAL_014',
        'T1_RESIDENCIAL_015',
        'T1_RESIDENCIAL_016',
        'T2_EDIFICIOS_011',
        'T2_EDIFICIOS_012',
        'T2_EDIFICIOS_013',
        'T2_EDIFICIOS_014',
        'T2_EDIFICIOS_015',
        'T2_EDIFICIOS_016',
        'T3_COMERCIAL_021',
        'T3_COMERCIAL_022',
        'T4_INDUSTRIAL_031',
        'T4_INDUSTRIAL_032',
        'T1_RESIDENCIAL_011',
        'T1_RESIDENCIAL_012',
        'T1_RESIDENCIAL_013',
        'T1_RESIDENCIAL_014',
        'T1_RESIDENCIAL_015',
        'T1_RESIDENCIAL_016',
        'T2_EDIFICIOS_011',
        'T2_EDIFICIOS_012',
        'T2_EDIFICIOS_013',
        'T2_EDIFICIOS_014',
        'T2_EDIFICIOS_015',
        'T2_EDIFICIOS_016',
        'T3_COMERCIAL_021',
        'T3_COMERCIAL_022',
        'T3_COMERCIAL_023',
        'T4_INDUSTRIAL_031',
        'T4_INDUSTRIAL_032',
        'T4_INDUSTRIAL_033',
        'T5_INSTITUCIONAL_ED',
        'T6_INSTITUCIONAL_SA', 
        'T7_INSTITUCIONAL_SER', 
        'T8_INSTITUCIONAL_IG',
        'T9_HOTELES',
        'T10_ANEXOS', 
        'T11_CCOMERCIALES',
        'T12_PARQUEADEROS',
        'T13_UNIDAD_DEPORTIVA',
        #pensiones
        'T3_COMERCIAL_023',
        'T9_HOTELES',
        'T4_INDUSTRIAL_032'
    ]
        
        
    print(len(condiciones_tabla))
    print(len(valores_tipomode))
        
    df_const['TABLA_ORIGEN'] = np.select(condiciones_tabla, valores_tipomode, default='SIN TABLA')

    df_const['TABLA_ORIGEN'] = df_const['TABLA_ORIGEN'].astype('string')

    print(df_const.shape)
    print(df_const['TABLA_ORIGEN'].value_counts().sort_values())




    df_const = df_const[df_const['ZHF'].notna() & (df_const['ZHF'] != '')]
    df_const['COMUNA'] = df_const['COMUNA'].astype(str).str.zfill(2)
    ### Filtrar que no sea ni modelos ni especiales 
    
   
    # # ✅ Crear variables auxiliares

    # df_const['ESP_INTEGRAL'] = df_const['INTEGRAL'] ### AQUI HAY QUE CAMBIAR CUANDO DEN LOS ESPECIALES
    # df_const['ESP_INTEGRAL'] = pd.to_numeric(df_const['ESP_INTEGRAL'], errors='coerce').fillna(0).astype(int)
    # ## La liquidación es integral 

    # df_const['ES_INTEGRAL'] = (
    # df_const['TABLA_ORIGEN'].isin(['MODELO', 'T12_PARQUEADERO']) 
    # | (
    #     (df_const['TABLA_ORIGEN'] == 'ESPECIALES') 
    #     & (df_const['ESP_INTEGRAL'] == 1)
    #   )
    # ).a

    # df_const['NO_ES_INTEGRAL'] = ~df_const['ES_INTEGRAL']

    # #df_filtrado = df_const[~df_const['TABLA_ORIGEN']=='T10_ANEXOS'] # No se tiene en cuenta las no convencionales
    # # ✅ Agrupar por predio y verificar presencia de tipos
    # df_metodo = (
    #     df_const.groupby('ID_PREDIO', as_index=False)
    #     .agg(
    #         TIENE_INTEGRAL=('ES_INTEGRAL', 'any'),
    #         TIENE_TABLA=('NO_ES_INTEGRAL', 'any')
    #         ))

    # # ✅ Crear variable METODO_LIQUIDACION
    # df_metodo['METODO_LIQUIDACION'] = 'OTRO'
    # df_metodo.loc[df_metodo['TIENE_INTEGRAL'] & df_metodo['TIENE_TABLA'], 'METODO_LIQUIDACION'] = 'MIXTO'
    # df_metodo.loc[df_metodo['TIENE_INTEGRAL'] & ~df_metodo['TIENE_TABLA'], 'METODO_LIQUIDACION'] = 'INTEGRAL'
    # df_metodo.loc[~df_metodo['TIENE_INTEGRAL'] & df_metodo['TIENE_TABLA'], 'METODO_LIQUIDACION'] = 'TABLA + TERRENO'
    

    # # ✅ Unir resultado y dejar solo la columna final
    # df_const = df_const.merge(df_metodo[['ID_PREDIO', 'METODO_LIQUIDACION']], on='ID_PREDIO', how='left')

    # # ✅ Eliminar columnas auxiliares
    # df_const = df_const.drop(columns=['ES_INTEGRAL', 'NO_ES_INTEGRAL'], errors='ignore')
    def asignar_metodo_liquidacion(df_const):
        """
        Asigna el método de liquidación correcto a cada predio
        
        Reglas:
        - INTEGRAL: Solo tiene construcciones integrales (MODELO, PARQUEADEROS, ESPECIALES con ESP_INTEGRAL=1)
        - TABLA + TERRENO: Solo tiene construcciones con tabla (no integrales)
        - MIXTO: Tiene tanto integrales como no integrales
        
        Args:
            df_const: DataFrame con construcciones
        
        Returns:
            df_const: DataFrame con columna METODO_LIQUIDACION corregida
        """
        
        print("\n🔍 Asignando método de liquidación...")
        
        # ============================================================
        # 1. PREPARAR VARIABLE ESP_INTEGRAL
        # ============================================================
        
        # df_const['ESP_INTEGRAL'] = df_const['ESP_INTEGRAL'].copy()
        # df_const['ESP_INTEGRAL'] = pd.to_numeric(df_const['ESP_INTEGRAL'], errors='coerce').fillna(0).astype(int)


        # ============================================================================
    # CRUCE DE ARCHIVO DE ESPECIALES
    # ============================================================================

        # ====================================================================
        # ESPECIALES: salen de la base CONVENCIONAL, no de un Excel aparte.
        # ESPECIAL marca la construccion, VALOR_M2 trae su valor por m2 -que no
        # es VALORCONS/ACONCONS, sino el valor especial- e INTEGRAL dice si
        # ademas es integral. Antes esto se cruzaba contra
        # ESPECIALES/20260303_PREDIOS_ESPECIALES_ACT_2025.xlsx, que ya no se usa.
        # ====================================================================
        print("\nEspeciales desde la base convencional...")

        if 'ESPECIAL' in df_const.columns:
            es_especial = df_const['ESPECIAL'].astype(str).str.strip() == '1'
        else:
            es_especial = pd.Series(False, index=df_const.index)
        vm2_esp = (pd.to_numeric(df_const['VALOR_M2'], errors='coerce').fillna(0)
                   if 'VALOR_M2' in df_const.columns
                   else pd.Series(0.0, index=df_const.index))
        integral = (pd.to_numeric(df_const['INTEGRAL'], errors='coerce').fillna(0)
                    if 'INTEGRAL' in df_const.columns
                    else pd.Series(0, index=df_const.index))

        df_const['VIM2_ESPECIAL'] = np.where(es_especial, vm2_esp, 0.0)
        df_const['INTEGRAL_ESP_2026'] = np.where(es_especial, integral, 0).astype(int)

        print(f"   Especiales: {int(es_especial.sum()):,} construcciones, "
              f"{int(df_const['INTEGRAL_ESP_2026'].sum()):,} de ellas integrales")
        # ============================================================
        # 2. IDENTIFICAR CONSTRUCCIONES INTEGRALES
        # ============================================================
        
        # Una construcción es INTEGRAL si cumple alguna de estas condiciones:
        # condiciones_integral = [
        # # 1. MODELO (siempre integral)
        #     df_const['TABLA_ORIGEN'] == 'MODELO',

        #     # 2. Parqueaderos integrales especiales
        #     (df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS') &
        #     (df_const['INTEGRAL_ESP_2026'] == 1),

        #     # 3. Integrales especiales
        #     df_const['INTEGRAL_ESP_2026'] == 1,

        #     # 4. Parqueaderos
        #     df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS'
        # ]

        # valores_integral = [1, 1, 1, 1]

        # df_const['ES_INTEGRAL'] = np.select(condiciones_integral, valores_integral, default=0)

        # condiciones_integral = [
        # # 1. MODELO (siempre integral)
        #     df_const['TABLA_ORIGEN'] == 'MODELO',

        #     # 2. Parqueaderos integrales especiales
        #     (df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS') 

        #      ]

        # valores_integral = [1, 1]

        # df_const['ES_INTEGRAL'] = np.select(condiciones_integral, valores_integral, default=0)
        condiciones_integral = (
            # Modelos (siempre integrales)
            (df_const['TABLA_ORIGEN'] == 'MODELO') |
            
            # Parqueaderos (siempre integrales)
            (df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS') & (df_const['INTEGRAL_ESP_2026'] == 0) |
            
            # Especiales marcados como integrales
            ((df_const['INTEGRAL_ESP_2026'] == 1))
        )
        
        df_const['ES_INTEGRAL'] = condiciones_integral
        df_const = df_const.drop(columns=['INTEGRAL_ESP_2026'], errors='ignore')
        
        #print(f'ES INTEGRAL NO ESPECIAL {df_const['ES_INTEGRAL_NO_ESP'].value_counts()}')
              
        print(f'ES INTEGRAL CON ESPECIALES {df_const['ES_INTEGRAL'].value_counts()}')


        
        df_const = df_const.drop(columns=['INTEGRAL_ESP_2026'], errors='ignore')

        # ============================================================
        # 3. IDENTIFICAR CONSTRUCCIONES CON TABLA
        # ============================================================
        
        # Una construcción usa TABLA si NO es integral Y NO es anexo
        # (Los anexos se liquidarán junto con la construcción principal)
        df_const['ES_TABLA'] = (
                ~df_const['ES_INTEGRAL'] & 
                (df_const['TABLA_ORIGEN'] != 'T10_ANEXOS')
            )
        
        # ============================================================
        # 4. AGRUPAR POR PREDIO Y CONTAR TIPOS
        # ============================================================
        
        df_metodo = (
            df_const.groupby('ID_PREDIO', as_index=False)
            .agg(
                #COUNT_INTEGRAL_NO_ESP =('ES_INTEGRAL_NO_ESP','sum'), ##CAmtodad de predios integrales no especiales
                COUNT_INTEGRAL=('ES_INTEGRAL', 'sum'),  # Cantidad de construcciones integrales
                COUNT_TABLA=('ES_TABLA', 'sum'),        # Cantidad de construcciones con tabla
                COUNT_ANEXOS=('TABLA_ORIGEN', lambda x: (x == 'T10_ANEXOS').sum()),
                TOTAL_CONST=('CONSTRUCCION_ID', 'count')
            )
        )
        
        # ============================================================
        # 5. ASIGNAR MÉTODO DE LIQUIDACIÓN
        # ============================================================
        
        # Inicializar con valor por defecto
        df_metodo['METODO_LIQUIDACION'] = 'REVISAR'
        
        # CASO 1: MIXTO - Tiene ambos tipos (integrales y tabla)
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] > 0) & (df_metodo['COUNT_TABLA'] > 0),
            'METODO_LIQUIDACION'
        ] = 'MIXTO'
        
        # CASO 2: INTEGRAL - Solo tiene construcciones integrales
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] > 0) & (df_metodo['COUNT_TABLA'] == 0),
            'METODO_LIQUIDACION'
        ] = 'INTEGRAL'
        
        # CASO 3: TABLA + TERRENO - Solo tiene construcciones con tabla
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] == 0) & (df_metodo['COUNT_TABLA'] > 0),
            'METODO_LIQUIDACION'
        ] = 'TABLA + TERRENO'
        
        # CASO 4: SOLO ANEXOS - Solo tiene anexos (sin construcción principal)
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] == 0) & 
            (df_metodo['COUNT_TABLA'] == 0) & 
            (df_metodo['COUNT_ANEXOS'] > 0),
            'METODO_LIQUIDACION'
        ] = 'SOLO ANEXOS'
        
        # ============================================================
        # 6. UNIR CON DATAFRAME ORIGINAL
        # ============================================================
        
        # Eliminar METODO_LIQUIDACION si ya existe
        if 'METODO_LIQUIDACION' in df_const.columns:
            df_const = df_const.drop(columns=['METODO_LIQUIDACION'])
        
        # Unir resultado
        df_const = df_const.merge(
            df_metodo[['ID_PREDIO', 'METODO_LIQUIDACION']], 
            on='ID_PREDIO', 
            how='left'
        )
        
        # ============================================================
        # 7. VALIDACIÓN Y REPORTE
        # ============================================================
        
        print("\n📊 Distribución de métodos de liquidación:")
        metodos = df_const.groupby('METODO_LIQUIDACION').agg({
            'ID_PREDIO': 'nunique',
            'CONSTRUCCION_ID': 'count'
        }).rename(columns={
            'ID_PREDIO': 'Predios',
            'CONSTRUCCION_ID': 'Construcciones'
        })
        
        for metodo, row in metodos.iterrows():
            pct_predios = (row['Predios'] / df_const['ID_PREDIO'].nunique()) * 100
            print(f"   {metodo:20s}: {row['Predios']:6,} predios ({pct_predios:5.2f}%) - {row['Construcciones']:6,} construcciones")
        
        # Casos para revisar
        revisar = df_const[df_const['METODO_LIQUIDACION'] == 'REVISAR']
        if len(revisar) > 0:
            print(f"\n⚠️ Hay {revisar['ID_PREDIO'].nunique()} predios marcados como 'REVISAR'")
            print("   Estos predios no tienen ni construcciones integrales ni con tabla")
        
        # Mostrar ejemplos de cada método
        print("\n📋 Ejemplos por método:")
        for metodo in df_const['METODO_LIQUIDACION'].unique():
            ejemplo = df_const[df_const['METODO_LIQUIDACION'] == metodo].iloc[0]
            print(f"\n   {metodo}:")
            print(f"      ID_PREDIO: {ejemplo['ID_PREDIO']}")
            
            # Mostrar todas las construcciones de este predio
            const_predio = df_const[df_const['ID_PREDIO'] == ejemplo['ID_PREDIO']]
            for _, c in const_predio.iterrows():
                integral = "✓" if c['ES_INTEGRAL'] else " "
                tabla = "✓" if c['ES_TABLA'] else " "
                print(f"         - {c['TABLA_ORIGEN']:20s} [Integral:{integral}] [Tabla:{tabla}]")
        
        # ============================================================
        # 8. LIMPIAR COLUMNAS AUXILIARES
        # ============================================================
        
        df_const = df_const.drop(columns=['ES_INTEGRAL', 'ES_TABLA'], errors='ignore')
        
        print("\n✅ Método de liquidación asignado correctamente")
        
        return df_const
    df_const = asignar_metodo_liquidacion(df_const)

    # ✅ (Opcional) Filtrar y mostrar resumen
    
    #print(f'CONTEO POR METODO DE LIQUIDACION {df_const['METODO_LIQUIDACION'].value_counts(dropna=False)}')
    




    # =============================================================================
    # CONFIGURACIÓN
    # =============================================================================
    comunas_2 = ['03', '22']
    comunas_5 = ['01', '09', '10', '11', '12']
    comunas_7 = ['01', '09', '10', '11', '12', '03', '22']

    valores_por_tabla = {
        # ---------- T1_RESIDENCIAL_011_9 ----------
        
        'T1_RESIDENCIAL_011_9': {

            'COMUNAS_5': [
                264479,	274929,	285378,	295828,	306278,	316728,	327177,	337627,	348077,	358527,	368976,	379426,	389876,	400326,	410775,	421225,	431675,	442125,	452575,	463024,	473474,	483924,	494374,	504823,	515273,	525723,	536173,	546622,	557072,	567522,	577972,	588422,	598871,	609321,	619771,	630221,	640670,	651120,	661570,	672020,	682469,	692919,	703369,	713819,	724268,	734718,	745168,	755618,	766068,	776517,	786967,	797417,	807867,	818316,	828766,	839216,	849666,	860115,	870565,	881015,	891465,	901915,	912364,	922814,	933264,	943714,	954163,	964613,	975063,	985513,	995962,	1006412,	1016862,	1027312,	1037761,	1048211,	1058661,	1069111,	1079561,	1090010,	1100460,	1110910,	1121360,	1131809,	1142259,	1152709,	1163159,	1173608,	1184058,	1194508,	1204958,	1215407,	1225857,	1236307,	1246757,	1257207,	1267656,	1278106,	1288556,	1299006
            ]
        },
        'T1_RESIDENCIAL_012_9': {

            'COMUNAS_5': [
                333087,	345207,	357327,	369447,	381567,	393687,	405807,	417926,	430046,	442166,	454286,	466406,	478526,	490646,	502766,	514886,	527006,	539125,	551245,	563365,	575485,	587605,	599725,	611845,	623965,	636085,	648204,	660324,	672444,	684564,	696684,	708804,	720924,	733044,	745164,	757284,	769403,	781523,	793643,	805763,	817883,	830003,	842123,	854243,	866363,	878482,	890602,	902722,	914842,	926962,	939082,	951202,	963322,	975442,	987562,	999681,	1011801,	1023921,	1036041,	1048161,	1060281,	1072401,	1084521,	1096641,	1108760,	1120880,	1133000,	1145120,	1157240,	1169360,	1181480,	1193600,	1205720,	1217840,	1229959,	1242079,	1254199,	1266319,	1278439,	1290559,	1302679,	1314799,	1326919,	1339038,	1351158,	1363278,	1375398,	1387518,	1399638,	1411758,	1423878,	1435998,	1448117,	1460237,	1472357,	1484477,	1496597,	1508717,	1520837,	1532957
            ]
        },
        'T1_RESIDENCIAL_013_9': {

            'COMUNAS_5': [
                379043,	393458,	407872,	422287,	436702,	451117,	465532,	479946,	494361,	508776,	523191,	537606,	552020,	566435,	580850,	595265,	609680,	624095,	638509,	652924,	667339,	681754,	696169,	710583,	724998,	739413,	753828,	768243,	782658,	797072,	811487,	825902,	840317,	854732,	869146,	883561,	897976,	912391,	926806,	941221,	955635,	970050,	984465,	998880,	1013295,	1027709,	1042124,	1056539,	1070954,	1085369,	1099784,	1114198,	1128613,	1143028,	1157443,	1171858,	1186272,	1200687,	1215102,	1229517,	1243932,	1258346,	1272761,	1287176,	1301591,	1316006,	1330421,	1344835,	1359250,	1373665,	1388080,	1402495,	1416909,	1431324,	1445739,	1460154,	1474569,	1488984,	1503398,	1517813,	1532228,	1546643,	1561058,	1575472,	1589887,	1604302,	1618717,	1633132,	1647547,	1661961,	1676376,	1690791,	1705206,	1719621,	1734035,	1748450,	1762865,	1777280,	1791695,	1806110
            ]
        },   
        'T1_RESIDENCIAL_014_9': {

            'COMUNAS_5': [
                480845,	495433,	510020,	524607,	539194,	553781,	568368,	582955,	597542,	612130,	626717,	641304,	655891,	670478,	685065,	699652,	714239,	728827,	743414,	758001,	772588,	787175,	801762,	816349,	830936,	845524,	860111,	874698,	889285,	903872,	918459,	933046,	947633,	962221,	976808,	991395,	1005982,	1020569,	1035156,	1049743,	1064331,	1078918,	1093505,	1108092,	1122679,	1137266,	1151853,	1166440,	1181028,	1195615,	1210202,	1224789,	1239376,	1253963,	1268550,	1283137,	1297725,	1312312,	1326899,	1341486,	1356073,	1370660,	1385247,	1399834,	1414422,	1429009,	1443596,	1458183,	1472770,	1487357,	1501944,	1516532,	1531119,	1545706,	1560293,	1574880,	1589467,	1604054,	1618641,	1633229,	1647816,	1662403,	1676990,	1691577,	1706164,	1720751,	1735338,	1749926,	1764513,	1779100,	1793687,	1808274,	1822861,	1837448,	1852035,	1866623,	1881210,	1895797,	1910384,	1924971
            ]
        },
        'T1_RESIDENCIAL_015_9': {

            'COMUNAS_5': [
                507313,	523646,	539979,	556311,	572644,	588977,	605309,	621642,	637975,	654307,	670640,	686973,	703305,	719638,	735971,	752303,	768636,	784969,	801301,	817634,	833967,	850299,	866632,	882965,	899297,	915630,	931963,	948295,	964628,	980961,	997294,	1013626,	1029959,	1046292,	1062624,	1078957,	1095290,	1111622,	1127955,	1144288,	1160620,	1176953,	1193286,	1209618,	1225951,	1242284,	1258616,	1274949,	1291282,	1307614,	1323947,	1340280,	1356612,	1372945,	1389278,	1405610,	1421943,	1438276,	1454608,	1470941,	1487274,	1503606,	1519939,	1536272,	1552604,	1568937,	1585270,	1601602,	1617935,	1634268,	1650600,	1666933,	1683266,	1699599,	1715931,	1732264,	1748597,	1764929,	1781262,	1797595,	1813927,	1830260,	1846593,	1862925,	1879258,	1895591,	1911923,	1928256,	1944589,	1960921,	1977254,	1993587,	2009919,	2026252,	2042585,	2058917,	2075250,	2091583,	2107915,	2124248
            ]
        },  
        'T1_RESIDENCIAL_016_9': {

            'COMUNAS_5': [
                619809,	637111,	654414,	671716,	689019,	706321,	723624,	740926,	758228,	775531,	792833,	810136,	827438,	844740,	862043,	879345,	896648,	913950,	931253,	948555,	965857,	983160,	1000462,	1017765,	1035067,	1052370,	1069672,	1086974,	1104277,	1121579,	1138882,	1156184,	1173486,	1190789,	1208091,	1225394,	1242696,	1259999,	1277301,	1294603,	1311906,	1329208,	1346511,	1363813,	1381116,	1398418,	1415720,	1433023,	1450325,	1467628,	1484930,	1502233,	1519535,	1536837,	1554140,	1571442,	1588745,	1606047,	1623349,	1640652,	1657954,	1675257,	1692559,	1709862,	1727164,	1744466,	1761769,	1779071,	1796374,	1813676,	1830979,	1848281,	1865583,	1882886,	1900188,	1917491,	1934793,	1952095,	1969398,	1986700,	2004003,	2021305,	2038608,	2055910,	2073212,	2090515,	2107817,	2125120,	2142422,	2159725,	2177027,	2194329,	2211632,	2228934,	2246237,	2263539,	2280842,	2298144,	2315446,	2332749
            ]
        },                                                                            

        # ---------- T1_RESIDENCIAL_011 ----------
        'T1_RESIDENCIAL_011': {
            'COMUNAS_2': [
                198636,	205194,	211967,	218965,	226193,	233660,	241374,	249342,	257573,	266076,	274860,	283933,	293306,	302989,	312991,	323323,	333997,	345023,	356412,	368178,	380332,	392888,	405858,	419256,	433096,	447393,	462162,	477419,	493179,	509460,	526278,	543651,	561598,	580138,	599289,	619072,	639509,	660620,	682428,	704956,	728228,	752268,	777102,	802755,	829256,	856631,	884909,	914122,	944298,	975471,	1007673,	1040938,	1075301,	1110799,	1147468,	1185348,	1224478,	1264900,	1306656,	1349791,	1394350,	1440380,	1487929,	1537048,	1587789,	1640204,	1694350,	1750283,	1808063,	1867750,	1929408,	1993101,	2058896,	2126864,	2197075,	2269604,	2344528,	2421924,	2501876,	2584467,	2669784,	2757918,	2848962,	2943011,	3040164,	3140525,	3244199,	3351296,	3461927,	3576211,	3694268,	3816222,	3942201,	4072340,	4206775,	4345647,	4489104,	4637297,	4790382,	4948520,

            ],
            'COMUNAS_5': [
                168324,	175629,	182934,	190240,	197545,	204850,	212156,	219461,	226766,	234072,	241377,	248682,	255988,	263293,	270598,	277904,	285209,	292514,	299820,	307125,	314430,	321736,	329041,	336346,	343652,	350957,	358262,	365568,	372873,	380178,	387484,	394789,	402094,	409400,	416705,	424010,	431316,	438621,	445926,	453232,	460537,	467842,	475148,	482453,	489758,	497064,	504369,	511674,	518980,	526285,	533590,	540896,	548201,	555506,	562812,	570117,	577422,	584728,	592033,	599338,	606644,	613949,	621254,	628560,	635865,	643170,	650476,	657781,	665086,	672392,	679697,	687002,	694308,	701613,	708918,	716224,	723529,	730834,	738140,	745445,	752750,	760056,	767361,	774666,	781972,	789277,	796582,	803888,	811193,	818498,	825804,	833109,	840414,	847720,	855025,	862331,	869636,	876941,	884247,	891552
                                                                                                              
            ]
        },
        
        # ---------- T1_RESIDENCIAL_012 ----------
        'T1_RESIDENCIAL_012': {
            'COMUNAS_2': [
               199603,	206187,	212988,	220014,	227271,	234768,	242512,	250512,	258776,	267312,	276129,	285238,	294647,	304366,	314406,	324777,	335491,	346557,	357989,	369798,	381996,	394597,	407613,	421059,	434948,	449296,	464117,	479426,	495241,	511577,	528452,	545884,	563891,	582491,	601706,	621554,	642057,	663236,	685114,	707713,	731058,	755174,	780084,	805816,	832397,	859855,	888219,	917518,	947784,	979048,	1011343,	1044704,	1079165,	1114763,	1151535,	1189520,	1228758,	1269291,	1311160,	1354411,	1399088,	1445239,	1492913,	1542159,	1593029,	1645578,	1699859,	1755932,	1813854,	1873687,	1935493,	1999338,	2065289,	2133416,	2203790,	2276485,	2351579,	2429149,	2509278,	2592051,	2677553,	2765876,	2857113,	2951359,	3048714,	3149281,	3253164,	3360475,	3471325,	3585832,	3704116,	3826302,	3952519,	4082898,	4217579,	4356702,	4500415,	4648867,	4802217,	4960626,

            ],
            'COMUNAS_5': [
                179748,	188528,	197309,	206089,	214869,	223649,	232429,	241210,	249990,	258770,	267550,	276330,	285111,	293891,	302671,	311451,	320231,	329012,	337792,	346572,	355352,	364132,	372913,	381693,	390473,	399253,	408033,	416814,	425594,	434374,	443154,	451934,	460715,	469495,	478275,	487055,	495835,	504616,	513396,	522176,	530956,	539736,	548517,	557297,	566077,	574857,	583637,	592418,	601198,	609978,	618758,	627538,	636319,	645099,	653879,	662659,	671439,	680220,	689000,	697780,	706560,	715340,	724121,	732901,	741681,	750461,	759241,	768022,	776802,	785582,	794362,	803142,	811923,	820703,	829483,	838263,	847043,	855824,	864604,	873384,	882164,	890944,	899724,	908505,	917285,	926065,	934845,	943625,	952406,	961186,	969966,	978746,	987526,	996307,	1005087,	1013867,	1022647,	1031427,	1040208,	1048988
            ]
        },
        
        # ---------- T1_RESIDENCIAL_013 ----------
        'T1_RESIDENCIAL_013': {
            'COMUNAS_2': [ 
                213322,	220362,	227635,	235148,	242909,	250926,	259208,	267763,	276601,	285730,	295160,	304902,	314965,	325360,	336098,	347191,	358650,	370487,	382715,	395346,	408395,	421873,	435797,	450180,	465039,	480387,	496242,	512620,	529539,	547016,	565070,	583720,	602985,	622887,	643445,	664681,	686619,	709281,	732690,	756872,	781852,	807657,	834314,	861850,	890295,	919678,	950032,	981387,	1013778,	1047237,	1081801,	1117505,	1154388,	1192488,	1231845,	1272502,	1314500,	1357885,	1402701,	1448997,	1496820,	1546222,	1597254,	1649971,	1704428,	1760682,	1818792,	1878821,	1940830,	2004887,	2071057,	2139411,	2210022,	2282963,	2358311,	2436146,	2516550,	2599607,	2685406,	2774037,	2865593,	2960170,	3057870,	3158793,	3263048,	3370743,	3481993,	3596915,	3715630,	3838262,	3964943,	4095804,	4230984,	4370626,	4514876,	4663888,	4817818,	4976828,	5141086,	5310765,
            ],
            'COMUNAS_5': [
                193070,	205274,	217479,	229683,	241888,	254092,	266297,	278501,	290706,	302910,	315115,	327319,	339524,	351728,	363933,	376137,	388342,	400546,	412751,	424955,	437160,	449364,	461569,	473773,	485978,	498182,	510387,	522591,	534796,	547000,	559205,	571409,	583614,	595818,	608023,	620227,	632432,	644636,	656841,	669045,	681250,	693454,	705659,	717863,	730068,	742272,	754477,	766681,	778886,	791090,	803295,	815499,	827704,	839908,	852113,	864318,	876522,	888727,	900931,	913136,	925340,	937545,	949749,	961954,	974158,	986363,	998567,	1010772,	1022976,	1035181,	1047385,	1059590,	1071794,	1083999,	1096203,	1108408,	1120612,	1132817,	1145021,	1157226,	1169430,	1181635,	1193839,	1206044,	1218248,	1230453,	1242657,	1254862,	1267066,	1279271,	1291475,	1303680,	1315884,	1328089,	1340293,	1352498,	1364702,	1376907,	1389111,	1401316

            ]   
        },
        # ---------- T1_RESIDENCIAL_014 ----------
        'T1_RESIDENCIAL_014': {
            'COMUNAS_2': [
                216093,	223218,	230578,	238180,	246033,	254145,	262525,	271180,	280121,	289357,	298897,	308752,	318932,	329448,	340310,	351530,	363120,	375093,	387460,	400235,	413431,	427062,	441143,	455688,	470712,	486232,	502263,	518823,	535929,	553599,	571852,	590707,	610183,	630301,	651082,	672549,	694724,	717629,	741290,	765731,	790978,	817057,	843996,	871824,	900568,	930261,	960932,	992615,	1025343,	1059149,	1094070,	1130143,	1167404,	1205895,	1245654,	1286724,	1329149,	1372972,	1418240,	1465001,	1513303,	1563198,	1614738,	1667977,	1722972,	1779780,	1838461,	1899076,	1961690,	2026369,	2093180,	2162194,	2233484,	2307123,	2383191,	2461767,	2542934,	2626776,	2713384,	2802846,	2895258,	2990718,	3089324,	3191182,	3296398,	3405083,	3517351,	3633322,	3753115,	3876859,	4004682,	4136720,	4273111,	4413999,	4559533,	4709865,	4865153,	5025561,	5191258,	5362419,

            ],
            'COMUNAS_5': [
                199540,	213864,	228188,	242513,	256837,	271161,	285485,	299810,	314134,	328458,	342782,	357107,	371431,	385755,	400079,	414404,	428728,	443052,	457376,	471701,	486025,	500349,	514673,	528998,	543322,	557646,	571970,	586295,	600619,	614943,	629267,	643592,	657916,	672240,	686564,	700889,	715213,	729537,	743861,	758186,	772510,	786834,	801158,	815483,	829807,	844131,	858455,	872780,	887104,	901428,	915752,	930077,	944401,	958725,	973049,	987374,	1001698,	1016022,	1030346,	1044671,	1058995,	1073319,	1087643,	1101968,	1116292,	1130616,	1144940,	1159265,	1173589,	1187913,	1202237,	1216562,	1230886,	1245210,	1259534,	1273859,	1288183,	1302507,	1316831,	1331156,	1345480,	1359804,	1374128,	1388453,	1402777,	1417101,	1431425,	1445750,	1460074,	1474398,	1488722,	1503047,	1517371,	1531695,	1546019,	1560344,	1574668,	1588992,	1603316,	1617641

            ]
        },
        
        # ---------- T1_RESIDENCIAL_015 ----------
        'T1_RESIDENCIAL_015': {
            'COMUNAS_2': [
                216734,	223889,	231280,	238914,	246801,	254949,	263365,	272059,	281040,	290317,	299901,	309801,	320028,	330592,	341505,	352779,	364424,	376454,	388882,	401719,	414980,	428679,	442830,	457449,	472549,	488149,	504263,	520909,	538105,	555869,	574218,	593174,	612755,	632983,	653879,	675464,	697762,	720795,	744590,	769169,	794561,	820790,	847885,	875875,	904788,	934656,	965510,	997383,	1030308,	1064319,	1099453,	1135748,	1173240,	1211970,	1251978,	1293307,	1336001,	1380104,	1425663,	1472725,	1521341,	1571563,	1623442,	1677033,	1732394,	1789582,	1848658,	1909684,	1972725,	2037847,	2105119,	2174611,	2246397,	2320553,	2397157,	2476290,	2558035,	2642478,	2729710,	2819820,	2912906,	3009064,	3108396,	3211008,	3317007,	3426505,	3539618,	3656464,	3777168,	3901856,	4030661,	4163718,	4301166,	4443153,	4589826,	4741341,	4897858,	5059542,	5226563,	5399097,

            ],
            'COMUNAS_5': [
               211993,	227586,	243180,	258774,	274368,	289962,	305556,	321150,	336743,	352337,	367931,	383525,	399119,	414713,	430307,	445900,	461494,	477088,	492682,	508276,	523870,	539464,	555057,	570651,	586245,	601839,	617433,	633027,	648621,	664214,	679808,	695402,	710996,	726590,	742184,	757778,	773371,	788965,	804559,	820153,	835747,	851341,	866935,	882528,	898122,	913716,	929310,	944904,	960498,	976092,	991685,	1007279,	1022873,	1038467,	1054061,	1069655,	1085249,	1100842,	1116436,	1132030,	1147624,	1163218,	1178812,	1194406,	1209999,	1225593,	1241187,	1256781,	1272375,	1287969,	1303563,	1319156,	1334750,	1350344,	1365938,	1381532,	1397126,	1412720,	1428314,	1443907,	1459501,	1475095,	1490689,	1506283,	1521877,	1537471,	1553064,	1568658,	1584252,	1599846,	1615440,	1631034,	1646628,	1662221,	1677815,	1693409,	1709003,	1724597,	1740191,	1755785

            ]
        },
        
        # ---------- T1_RESIDENCIAL_016 ----------
        'T1_RESIDENCIAL_016': {
            'COMUNAS_2': [ 
                219681,	226905,	234366,	242073,	250032,	258254,	266746,	275517,	284577,	293934,	303599,	313582,	323894,	334544,	345544,	356907,	368642,	380764,	393284,	406217,	419574,	433370,	447620,	462339,	477542,	493244,	509463,	526215,	543518,	561390,	579850,	598917,	618611,	638952,	659962,	681663,	704077,	727229,	751142,	775841,	801352,	827702,	854919,	883030,	912066,	942057,	973033,	1005029,	1038076,	1072210,	1107467,	1143883,	1181496,	1220346,	1260474,	1301921,	1344731,	1388948,	1434620,	1481793,	1530517,	1580844,	1632825,	1686516,	1741972,	1799252,	1858415,	1919524,	1982642,	2047835,	2115172,	2184724,	2256562,	2330762,	2407403,	2486563,	2568327,	2652778,	2740007,	2830105,	2923164,	3019284,	3118564,	3221109,	3327026,	3436426,	3549423,	3666135,	3786685,	3911199,	4039808,	4172645,	4309851,	4451567,	4597944,	4749134,	4905296,	5066592,	5233192,	5405271,

            ],  
            'COMUNAS_5': [
                228120,	248443,	268767,	289090,	309414,	329737,	350061,	370384,	390708,	411031,	431355,	451678,	472002,	492325,	512649,	532973,	553296,	573620,	593943,	614267,	634590,	654914,	675237,	695561,	715884,	736208,	756531,	776855,	797178,	817502,	837825,	858149,	878473,	898796,	919120,	939443,	959767,	980090,	1000414,	1020737,	1041061,	1061384,	1081708,	1102031,	1122355,	1142678,	1163002,	1183326,	1203649,	1223973,	1244296,	1264620,	1284943,	1305267,	1325590,	1345914,	1366237,	1386561,	1406884,	1427208,	1447531,	1467855,	1488179,	1508502,	1528826,	1549149,	1569473,	1589796,	1610120,	1630443,	1650767,	1671090,	1691414,	1711737,	1732061,	1752384,	1772708,	1793032,	1813355,	1833679,	1854002,	1874326,	1894649,	1914973,	1935296,	1955620,	1975943,	1996267,	2016590,	2036914,	2057237,	2077561,	2097884,	2118208,	2138532,	2158855,	2179179,	2199502,	2219826,	2240149
            ]   
        },
        #------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#
        # ---------- T2_EDIFICIOS_011 ----------
        'T2_EDIFICIOS_011': {
            'COMUNAS_2': [
                178550,	209622,	240694,	271766,	302838,	333909,	364981,	396053,	427125,	458197,	489269,	520341,	551413,	582485,	613557,	644629,	675700,	706772,	737844,	768916,	799988,	831060,	862132,	893204,	924276,	955348,	986420,	1017491,	1048563,	1079635,	1110707,	1141779,	1172851,	1203923,	1234995,	1266067,	1297139,	1328211,	1359282,	1390354,	1421426,	1452498,	1483570,	1514642,	1545714,	1576786,	1607858,	1638930,	1670002,	1701074,	1732145,	1763217,	1794289,	1825361,	1856433,	1887505,	1918577,	1949649,	1980721,	2011793,	2042865,	2073936,	2105008,	2136080,	2167152,	2198224,	2229296,	2260368,	2291440,	2322512,	2353584,	2384656,	2415727,	2446799,	2477871,	2508943,	2540015,	2571087,	2602159,	2633231,	2664303,	2695375,	2726447,	2757518,	2788590,	2819662,	2850734,	2881806,	2912878,	2943950,	2975022,	3006094,	3037166,	3068238,	3099310,	3130381,	3161453,	3192525,	3223597,	3254669

            ],
            'COMUNAS_5': [
                219842,	225468,	231094,	236720,	242346,	247972,	253599,	259225,	264851,	270477,	276103,	281729,	287355,	292981,	298607,	304233,	309859,	315485,	321111,	326737,	332364,	337990,	343616,	349242,	354868,	360494,	366120,	371746,	377372,	382998,	388624,	394250,	399876,	405502,	411128,	416755,	422381,	428007,	433633,	439259,	444885,	450511,	456137,	461763,	467389,	473015,	478641,	484267,	489893,	495520,	501146,	506772,	512398,	518024,	523650,	529276,	534902,	540528,	546154,	551780,	557406,	563032,	568658,	574284,	579911,	585537,	591163,	596789,	602415,	608041,	613667,	619293,	624919,	630545,	636171,	641797,	647423,	653049,	658676,	664302,	669928,	675554,	681180,	686806,	692432,	698058,	703684,	709310,	714936,	720562,	726188,	731814,	737440,	743067,	748693,	754319,	759945,	765571,	771197,	776823,

            ]
        },
        
        # ---------- T2_EDIFICIOS_012 ----------
        'T2_EDIFICIOS_012': {
            'COMUNAS_2': [
                382877,	414197,	445517,	476837,	508157,	539477,	570797,	602117,	633437,	664757,	696076,	727396,	758716,	790036,	821356,	852676,	883996,	915316,	946636,	977956,	1009276,	1040596,	1071916,	1103236,	1134556,	1165876,	1197196,	1228516,	1259836,	1291156,	1322476,	1353796,	1385116,	1416436,	1447756,	1479076,	1510396,	1541716,	1573036,	1604356,	1635676,	1666996,	1698316,	1729636,	1760956,	1792275,	1823595,	1854915,	1886235,	1917555,	1948875,	1980195,	2011515,	2042835,	2074155,	2105475,	2136795,	2168115,	2199435,	2230755,	2262075,	2293395,	2324715,	2356035,	2387355,	2418675,	2449995,	2481315,	2512635,	2543955,	2575275,	2606595,	2637915,	2669235,	2700555,	2731875,	2763195,	2794515,	2825835,	2857155,	2888474,	2919794,	2951114,	2982434,	3013754,	3045074,	3076394,	3107714,	3139034,	3170354,	3201674,	3232994,	3264314,	3295634,	3326954,	3358274,	3389594,	3420914,	3452234,	3483554

            ],
            'COMUNAS_5': [
                286704,	291700,	296696,	301691,	306687,	311683,	316678,	321674,	326669,	331665,	336661,	341656,	346652,	351648,	356643,	361639,	366635,	371630,	376626,	381621,	386617,	391613,	396608,	401604,	406600,	411595,	416591,	421587,	426582,	431578,	436573,	441569,	446565,	451560,	456556,	461552,	466547,	471543,	476539,	481534,	486530,	491525,	496521,	501517,	506512,	511508,	516504,	521499,	526495,	531490,	536486,	541482,	546477,	551473,	556469,	561464,	566460,	571456,	576451,	581447,	586442,	591438,	596434,	601429,	606425,	611421,	616416,	621412,	626408,	631403,	636399,	641394,	646390,	651386,	656381,	661377,	666373,	671368,	676364,	681360,	686355,	691351,	696346,	701342,	706338,	711333,	716329,	721325,	726320,	731316,	736312,	741307,	746303,	751298,	756294,	761290,	766285,	771281,	776277,	781272,

            ]
        },
        
        # ---------- T2_EDIFICIOS_013 ----------
        'T2_EDIFICIOS_013': {
            'COMUNAS_2': [ 
                437497,	469530,	501562,	533595,	565627,	597660,	629692,	661725,	693757,	725790,	757822,	789855,	821887,	853920,	885952,	917985,	950017,	982050,	1014082,	1046115,	1078147,	1110180,	1142212,	1174245,	1206277,	1238309,	1270342,	1302374,	1334407,	1366439,	1398472,	1430504,	1462537,	1494569,	1526602,	1558634,	1590667,	1622699,	1654732,	1686764,	1718797,	1750829,	1782862,	1814894,	1846927,	1878959,	1910992,	1943024,	1975057,	2007089,	2039122,	2071154,	2103187,	2135219,	2167252,	2199284,	2231317,	2263349,	2295382,	2327414,	2359447,	2391479,	2423512,	2455544,	2487577,	2519609,	2551642,	2583674,	2615707,	2647739,	2679772,	2711804,	2743836,	2775869,	2807901,	2839934,	2871966,	2903999,	2936031,	2968064,	3000096,	3032129,	3064161,	3096194,	3128226,	3160259,	3192291,	3224324,	3256356,	3288389,	3320421,	3352454,	3384486,	3416519,	3448551,	3480584,	3512616,	3544649,	3576681,	3608714
            ],  
            'COMUNAS_5': [
                495554,	499809,	504063,	508318,	512572,	516827,	521081,	525336,	529590,	533845,	538099,	542354,	546608,	550863,	555117,	559371,	563626,	567880,	572135,	576389,	580644,	584898,	589153,	593407,	597662,	601916,	606171,	610425,	614680,	618934,	623189,	627443,	631698,	635952,	640207,	644461,	648716,	652970,	657225,	661479,	665734,	669988,	674243,	678497,	682752,	687006,	691261,	695515,	699770,	704024,	708279,	712533,	716788,	721042,	725297,	729551,	733806,	738060,	742315,	746569,	750824,	755078,	759333,	763587,	767842,	772096,	776351,	780605,	784860,	789114,	793369,	797623,	801878,	806132,	810387,	814641,	818896,	823150,	827405,	831659,	835914,	840168,	844423,	848677,	852932,	857186,	861441,	865695,	869950,	874204,	878459,	882713,	886968,	891222,	895477,	899731,	903986,	908240,	912495,	916749,

            ]   
        },
        # ---------- T2_EDIFICIOS_014 ----------
        'T2_EDIFICIOS_014': {
            'COMUNAS_2': [
                454310,	486413,	518517,	550620,	582723,	614826,	646930,	679033,	711136,	743240,	775343,	807446,	839550,	871653,	903756,	935860,	967963,	1000066,	1032169,	1064273,	1096376,	1128479,	1160583,	1192686,	1224789,	1256893,	1288996,	1321099,	1353203,	1385306,	1417409,	1449512,	1481616,	1513719,	1545822,	1577926,	1610029,	1642132,	1674236,	1706339,	1738442,	1770546,	1802649,	1834752,	1866856,	1898959,	1931062,	1963165,	1995269,	2027372,	2059475,	2091579,	2123682,	2155785,	2187889,	2219992,	2252095,	2284199,	2316302,	2348405,	2380508,	2412612,	2444715,	2476818,	2508922,	2541025,	2573128,	2605232,	2637335,	2669438,	2701542,	2733645,	2765748,	2797851,	2829955,	2862058,	2894161,	2926265,	2958368,	2990471,	3022575,	3054678,	3086781,	3118885,	3150988,	3183091,	3215195,	3247298,	3279401,	3311504,	3343608,	3375711,	3407814,	3439918,	3472021,	3504124,	3536228,	3568331,	3600434,	3632538

            ],
            'COMUNAS_5': [
               508008,	516615,	525223,	533830,	542438,	551045,	559652,	568260,	576867,	585475,	594082,	602690,	611297,	619904,	628512,	637119,	645727,	654334,	662941,	671549,	680156,	688764,	697371,	705979,	714586,	723193,	731801,	740408,	749016,	757623,	766231,	774838,	783445,	792053,	800660,	809268,	817875,	826483,	835090,	843697,	852305,	860912,	869520,	878127,	886734,	895342,	903949,	912557,	921164,	929772,	938379,	946986,	955594,	964201,	972809,	981416,	990024,	998631,	1007238,	1015846,	1024453,	1033061,	1041668,	1050276,	1058883,	1067490,	1076098,	1084705,	1093313,	1101920,	1110527,	1119135,	1127742,	1136350,	1144957,	1153565,	1162172,	1170779,	1179387,	1187994,	1196602,	1205209,	1213817,	1222424,	1231031,	1239639,	1248246,	1256854,	1265461,	1274069,	1282676,	1291283,	1299891,	1308498,	1317106,	1325713,	1334321,	1342928,	1351535,	1360143,

            ]
        },
        
        # ---------- T2_EDIFICIOS_015 ----------
        'T2_EDIFICIOS_015': {
            'COMUNAS_2': [
                571220,	602806,	634391,	665976,	697562,	729147,	760732,	792318,	823903,	855489,	887074,	918659,	950245,	981830,	1013415,	1045001,	1076586,	1108171,	1139757,	1171342,	1202927,	1234513,	1266098,	1297683,	1329269,	1360854,	1392439,	1424025,	1455610,	1487195,	1518781,	1550366,	1581951,	1613537,	1645122,	1676708,	1708293,	1739878,	1771464,	1803049,	1834634,	1866220,	1897805,	1929390,	1960976,	1992561,	2024146,	2055732,	2087317,	2118902,	2150488,	2182073,	2213658,	2245244,	2276829,	2308414,	2340000,	2371585,	2403170,	2434756,	2466341,	2497926,	2529512,	2561097,	2592683,	2624268,	2655853,	2687439,	2719024,	2750609,	2782195,	2813780,	2845365,	2876951,	2908536,	2940121,	2971707,	3003292,	3034877,	3066463,	3098048,	3129633,	3161219,	3192804,	3224389,	3255975,	3287560,	3319145,	3350731,	3382316,	3413901,	3445487,	3477072,	3508658,	3540243,	3571828,	3603414,	3634999,	3666584,	3698170

            ],
            'COMUNAS_5': [
                828000,	839939,	851878,	863817,	875757,	887696,	899635,	911574,	923513,	935453,	947392,	959331,	971270,	983209,	995148,	1007088,	1019027,	1030966,	1042905,	1054844,	1066784,	1078723,	1090662,	1102601,	1114540,	1126480,	1138419,	1150358,	1162297,	1174236,	1186176,	1198115,	1210054,	1221993,	1233932,	1245872,	1257811,	1269750,	1281689,	1293628,	1305568,	1317507,	1329446,	1341385,	1353324,	1365264,	1377203,	1389142,	1401081,	1413020,	1424959,	1436899,	1448838,	1460777,	1472716,	1484655,	1496595,	1508534,	1520473,	1532412,	1544351,	1556291,	1568230,	1580169,	1592108,	1604047,	1615987,	1627926,	1639865,	1651804,	1663743,	1675683,	1687622,	1699561,	1711500,	1723439,	1735379,	1747318,	1759257,	1771196,	1783135,	1795075,	1807014,	1818953,	1830892,	1842831,	1854770,	1866710,	1878649,	1890588,	1902527,	1914466,	1926406,	1938345,	1950284,	1962223,	1974162,	1986102,	1998041,	2009980,

            ]
        },
        
        # ---------- T2_EDIFICIOS_016 ----------
        'T2_EDIFICIOS_016': {
            'COMUNAS_2': [ 
                673749,	704911,	736072,	767234,	798395,	829557,	860719,	891880,	923042,	954203,	985365,	1016526,	1047688,	1078850,	1110011,	1141173,	1172334,	1203496,	1234657,	1265819,	1296980,	1328142,	1359304,	1390465,	1421627,	1452788,	1483950,	1515111,	1546273,	1577435,	1608596,	1639758,	1670919,	1702081,	1733242,	1764404,	1795565,	1826727,	1857889,	1889050,	1920212,	1951373,	1982535,	2013696,	2044858,	2076020,	2107181,	2138343,	2169504,	2200666,	2231827,	2262989,	2294150,	2325312,	2356474,	2387635,	2418797,	2449958,	2481120,	2512281,	2543443,	2574605,	2605766,	2636928,	2668089,	2699251,	2730412,	2761574,	2792735,	2823897,	2855059,	2886220,	2917382,	2948543,	2979705,	3010866,	3042028,	3073190,	3104351,	3135513,	3166674,	3197836,	3228997,	3260159,	3291320,	3322482,	3353644,	3384805,	3415967,	3447128,	3478290,	3509451,	3540613,	3571775,	3602936,	3634098,	3665259,	3696421,	3727582,	3758744
            ],  
            'COMUNAS_5': [
                982937,	1001078,	1019220,	1037361,	1055502,	1073643,	1091784,	1109925,	1128067,	1146208,	1164349,	1182490,	1200631,	1218772,	1236914,	1255055,	1273196,	1291337,	1309478,	1327619,	1345760,	1363902,	1382043,	1400184,	1418325,	1436466,	1454607,	1472749,	1490890,	1509031,	1527172,	1545313,	1563454,	1581595,	1599737,	1617878,	1636019,	1654160,	1672301,	1690442,	1708584,	1726725,	1744866,	1763007,	1781148,	1799289,	1817430,	1835572,	1853713,	1871854,	1889995,	1908136,	1926277,	1944419,	1962560,	1980701,	1998842,	2016983,	2035124,	2053265,	2071407,	2089548,	2107689,	2125830,	2143971,	2162112,	2180254,	2198395,	2216536,	2234677,	2252818,	2270959,	2289100,	2307242,	2325383,	2343524,	2361665,	2379806,	2397947,	2416089,	2434230,	2452371,	2470512,	2488653,	2506794,	2524935,	2543077,	2561218,	2579359,	2597500,	2615641,	2633782,	2651924,	2670065,	2688206,	2706347,	2724488,	2742629,	2760770,	2778912,
            ]   
        },
        #--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#
        # ---------- T3_COMERCIAL_021 ----------FALTAN
        'T3_COMERCIAL_021': {
            'COMUNAS_2': [ 
                78327,	116285,	154243,	192200,	230158,	268116,	306074,	344032,	381990,	419948,	457906,	495864,	533821,	571779,	609737,	647695,	685653,	723611,	761569,	799527,	837485,	875442,	913400,	951358,	989316,	1027274,	1065232,	1103190,	1141148,	1179106,	1217063,	1255021,	1292979,	1330937,	1368895,	1406853,	1444811,	1482769,	1520726,	1558684,	1596642,	1634600,	1672558,	1710516,	1748474,	1786432,	1824390,	1862347,	1900305,	1938263,	1976221,	2014179,	2052137,	2090095,	2128053,	2166011,	2203968,	2241926,	2279884,	2317842,	2355800,	2393758,	2431716,	2469674,	2507632,	2545589,	2583547,	2621505,	2659463,	2697421,	2735379,	2773337,	2811295,	2849253,	2887210,	2925168,	2963126,	3001084,	3039042,	3077000,	3114958,	3152916,	3190873,	3228831,	3266789,	3304747,	3342705,	3380663,	3418621,	3456579,	3494537,	3532494,	3570452,	3608410,	3646368,	3684326,	3722284,	3760242,	3798200,	3836158,

            ],  
            'COMUNAS_5': [
                95307,	109481,	123654,	137828,	152001,	166174,	180348,	194521,	208695,	222868,	237041,	251215,	265388,	279562,	293735,	307909,	322082,	336255,	350429,	364602,	378776,	392949,	407123,	421296,	435469,	449643,	463816,	477990,	492163,	506336,	520510,	534683,	548857,	563030,	577204,	591377,	605550,	619724,	633897,	648071,	662244,	676417,	690591,	704764,	718938,	733111,	747285,	761458,	775631,	789805,	803978,	818152,	832325,	846499,	860672,	874845,	889019,	903192,	917366,	931539,	945712,	959886,	974059,	988233,	1002406,	1016580,	1030753,	1044926,	1059100,	1073273,	1087447,	1101620,	1115793,	1129967,	1144140,	1158314,	1172487,	1186661,	1200834,	1215007,	1229181,	1243354,	1257528,	1271701,	1285875,	1300048,	1314221,	1328395,	1342568,	1356742,	1370915,	1385088,	1399262,	1413435,	1427609,	1441782,	1455956,	1470129,	1484302,	1498476

            ]   
        },
        # ---------- T3_COMERCIAL_022 ----------
        'T3_COMERCIAL_022': {
            'COMUNAS_2': [ 
                175843,	215307,	254770,	294234,	333697,	373161,	412624,	452088,	491551,	531015,	570478,	609941,	649405,	688868,	728332,	767795,	807259,	846722,	886186,	925649,	965113,	1004576,	1044040,	1083503,	1122967,	1162430,	1201894,	1241357,	1280820,	1320284,	1359747,	1399211,	1438674,	1478138,	1517601,	1557065,	1596528,	1635992,	1675455,	1714919,	1754382,	1793846,	1833309,	1872772,	1912236,	1951699,	1991163,	2030626,	2070090,	2109553,	2149017,	2188480,	2227944,	2267407,	2306871,	2346334,	2385798,	2425261,	2464725,	2504188,	2543651,	2583115,	2622578,	2662042,	2701505,	2740969,	2780432,	2819896,	2859359,	2898823,	2938286,	2977750,	3017213,	3056677,	3096140,	3135603,	3175067,	3214530,	3253994,	3293457,	3332921,	3372384,	3411848,	3451311,	3490775,	3530238,	3569702,	3609165,	3648629,	3688092,	3727555,	3767019,	3806482,	3845946,	3885409,	3924873,	3964336,	4003800,	4043263,	4082727,

            ],  
            'COMUNAS_5': [
                114870,	131711,	148552,	165392,	182233,	199074,	215914,	232755,	249595,	266436,	283277,	300117,	316958,	333799,	350639,	367480,	384320,	401161,	418002,	434842,	451683,	468524,	485364,	502205,	519046,	535886,	552727,	569567,	586408,	603249,	620089,	636930,	653771,	670611,	687452,	704292,	721133,	737974,	754814,	771655,	788496,	805336,	822177,	839018,	855858,	872699,	889539,	906380,	923221,	940061,	956902,	973743,	990583,	1007424,	1024264,	1041105,	1057946,	1074786,	1091627,	1108468,	1125308,	1142149,	1158990,	1175830,	1192671,	1209511,	1226352,	1243193,	1260033,	1276874,	1293715,	1310555,	1327396,	1344236,	1361077,	1377918,	1394758,	1411599,	1428440,	1445280,	1462121,	1478962,	1495802,	1512643,	1529483,	1546324,	1563165,	1580005,	1596846,	1613687,	1630527,	1647368,	1664208,	1681049,	1697890,	1714730,	1731571,	1748412,	1765252,	1782093

            ]   
        },
        # ---------- T3_COMERCIAL_023 ----------
        'T3_COMERCIAL_023': {
            'COMUNAS_2': [ 
                453516,	490318,	527119,	563921,	600722,	637523,	674325,	711126,	747928,	784729,	821531,	858332,	895134,	931935,	968737,	1005538,	1042339,	1079141,	1115942,	1152744,	1189545,	1226347,	1263148,	1299950,	1336751,	1373552,	1410354,	1447155,	1483957,	1520758,	1557560,	1594361,	1631163,	1667964,	1704765,	1741567,	1778368,	1815170,	1851971,	1888773,	1925574,	1962376,	1999177,	2035978,	2072780,	2109581,	2146383,	2183184,	2219986,	2256787,	2293589,	2330390,	2367192,	2403993,	2440794,	2477596,	2514397,	2551199,	2588000,	2624802,	2661603,	2698405,	2735206,	2772007,	2808809,	2845610,	2882412,	2919213,	2956015,	2992816,	3029618,	3066419,	3103220,	3140022,	3176823,	3213625,	3250426,	3287228,	3324029,	3360831,	3397632,	3434434,	3471235,	3508036,	3544838,	3581639,	3618441,	3655242,	3692044,	3728845,	3765647,	3802448,	3839249,	3876051,	3912852,	3949654,	3986455,	4023257,	4060058,	4096860,

            ],  
            'COMUNAS_5': [
                397046,	414501,	431956,	449411,	466866,	484321,	501776,	519231,	536686,	554141,	571596,	589050,	606505,	623960,	641415,	658870,	676325,	693780,	711235,	728690,	746145,	763600,	781055,	798510,	815965,	833420,	850875,	868330,	885785,	903240,	920695,	938150,	955605,	973060,	990515,	1007970,	1025425,	1042880,	1060335,	1077790,	1095245,	1112700,	1130155,	1147610,	1165065,	1182520,	1199974,	1217429,	1234884,	1252339,	1269794,	1287249,	1304704,	1322159,	1339614,	1357069,	1374524,	1391979,	1409434,	1426889,	1444344,	1461799,	1479254,	1496709,	1514164,	1531619,	1549074,	1566529,	1583984,	1601439,	1618894,	1636349,	1653804,	1671259,	1688714,	1706169,	1723624,	1741079,	1758534,	1775989,	1793444,	1810898,	1828353,	1845808,	1863263,	1880718,	1898173,	1915628,	1933083,	1950538,	1967993,	1985448,	2002903,	2020358,	2037813,	2055268,	2072723,	2090178,	2107633,	2125088

            ]   
        },
        #--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#
        
        # ---------- T4_INDUSTRIAL_031 ---------- FALTAN 
        'T4_INDUSTRIAL_031': {
            'COMUNAS_2': [ 
                199691,	234241,	268791,	303341,	337891,	372441,	406991,	441542,	476092,	510642,	545192,	579742,	614292,	648842,	683392,	717943,	752493,	787043,	821593,	856143,	890693,	925243,	959793,	994344,	1028894,	1063444,	1097994,	1132544,	1167094,	1201644,	1236194,	1270745,	1305295,	1339845,	1374395,	1408945,	1443495,	1478045,	1512595,	1547146,	1581696,	1616246,	1650796,	1685346,	1719896,	1754446,	1788996,	1823547,	1858097,	1892647,	1927197,	1961747,	1996297,	2030847,	2065397,	2099948,	2134498,	2169048,	2203598,	2238148,	2272698,	2307248,	2341798,	2376348,	2410899,	2445449,	2479999,	2514549,	2549099,	2583649,	2618199,	2652749,	2687300,	2721850,	2756400,	2790950,	2825500,	2860050,	2894600,	2929150,	2963701,	2998251,	3032801,	3067351,	3101901,	3136451,	3171001,	3205551,	3240102,	3274652,	3309202,	3343752,	3378302,	3412852,	3447402,	3481952,	3516503,	3551053,	3585603,	3620153

            ],  
            'COMUNAS_5': [
               106842,	120507,	134173,	147839,	161505,	175170,	188836,	202502,	216167,	229833,	243499,	257165,	270830,	284496,	298162,	311827,	325493,	339159,	352825,	366490,	380156,	393822,	407487,	421153,	434819,	448484,	462150,	475816,	489482,	503147,	516813,	530479,	544144,	557810,	571476,	585142,	598807,	612473,	626139,	639804,	653470,	667136,	680802,	694467,	708133,	721799,	735464,	749130,	762796,	776461,	790127,	803793,	817459,	831124,	844790,	858456,	872121,	885787,	899453,	913119,	926784,	940450,	954116,	967781,	981447,	995113,	1008778,	1022444,	1036110,	1049776,	1063441,	1077107,	1090773,	1104438,	1118104,	1131770,	1145436,	1159101,	1172767,	1186433,	1200098,	1213764,	1227430,	1241096,	1254761,	1268427,	1282093,	1295758,	1309424,	1323090,	1336755,	1350421,	1364087,	1377753,	1391418,	1405084,	1418750,	1432415,	1446081,	1459747

            ]   
        },
        # ---------- T4_INDUSTRIAL_032 ----------
        'T4_INDUSTRIAL_032': {
            'COMUNAS_2': [ 
                222835,	257360,	291885,	326410,	360935,	395461,	429986,	464511,	499036,	533561,	568086,	602611,	637136,	671661,	706186,	740711,	775236,	809761,	844286,	878812,	913337,	947862,	982387,	1016912,	1051437,	1085962,	1120487,	1155012,	1189537,	1224062,	1258587,	1293112,	1327637,	1362163,	1396688,	1431213,	1465738,	1500263,	1534788,	1569313,	1603838,	1638363,	1672888,	1707413,	1741938,	1776463,	1810988,	1845514,	1880039,	1914564,	1949089,	1983614,	2018139,	2052664,	2087189,	2121714,	2156239,	2190764,	2225289,	2259814,	2294339,	2328865,	2363390,	2397915,	2432440,	2466965,	2501490,	2536015,	2570540,	2605065,	2639590,	2674115,	2708640,	2743165,	2777690,	2812216,	2846741,	2881266,	2915791,	2950316,	2984841,	3019366,	3053891,	3088416,	3122941,	3157466,	3191991,	3226516,	3261041,	3295567,	3330092,	3364617,	3399142,	3433667,	3468192,	3502717,	3537242,	3571767,	3606292,	3640817

            ],  
            'COMUNAS_5': [
               108926,	125064,	141202,	157340,	173478,	189616,	205755,	221893,	238031,	254169,	270307,	286445,	302584,	318722,	334860,	350998,	367136,	383274,	399413,	415551,	431689,	447827,	463965,	480103,	496242,	512380,	528518,	544656,	560794,	576932,	593071,	609209,	625347,	641485,	657623,	673761,	689900,	706038,	722176,	738314,	754452,	770590,	786729,	802867,	819005,	835143,	851281,	867419,	883558,	899696,	915834,	931972,	948110,	964248,	980387,	996525,	1012663,	1028801,	1044939,	1061077,	1077216,	1093354,	1109492,	1125630,	1141768,	1157906,	1174045,	1190183,	1206321,	1222459,	1238597,	1254735,	1270874,	1287012,	1303150,	1319288,	1335426,	1351564,	1367703,	1383841,	1399979,	1416117,	1432255,	1448393,	1464532,	1480670,	1496808,	1512946,	1529084,	1545222,	1561361,	1577499,	1593637,	1609775,	1625913,	1642051,	1658190,	1674328,	1690466,	1706604

            ]   
        },
        # ---------- T4_INDUSTRIAL_033 ----------
        'T4_INDUSTRIAL_033': {
            'COMUNAS_2': [ 
                558433,	589656,	620878,	652101,	683324,	714546,	745769,	776992,	808214,	839437,	870660,	901882,	933105,	964328,	995550,	1026773,	1057996,	1089218,	1120441,	1151664,	1182886,	1214109,	1245332,	1276554,	1307777,	1339000,	1370222,	1401445,	1432668,	1463890,	1495113,	1526336,	1557558,	1588781,	1620004,	1651226,	1682449,	1713672,	1744894,	1776117,	1807340,	1838562,	1869785,	1901008,	1932230,	1963453,	1994676,	2025898,	2057121,	2088344,	2119566,	2150789,	2182012,	2213234,	2244457,	2275680,	2306902,	2338125,	2369348,	2400570,	2431793,	2463016,	2494238,	2525461,	2556684,	2587906,	2619129,	2650352,	2681574,	2712797,	2744020,	2775242,	2806465,	2837688,	2868910,	2900133,	2931356,	2962578,	2993801,	3025024,	3056246,	3087469,	3118692,	3149914,	3181137,	3212360,	3243582,	3274805,	3306028,	3337250,	3368473,	3399696,	3430918,	3462141,	3493364,	3524586,	3555809,	3587032,	3618254,	3649477

            ],  
            'COMUNAS_5': [
                158768,	189174,	219580,	249986,	280392,	310799,	341205,	371611,	402017,	432423,	462829,	493235,	523641,	554047,	584453,	614859,	645265,	675671,	706077,	736483,	766889,	797296,	827702,	858108,	888514,	918920,	949326,	979732,	1010138,	1040544,	1070950,	1101356,	1131762,	1162168,	1192574,	1222980,	1253386,	1283793,	1314199,	1344605,	1375011,	1405417,	1435823,	1466229,	1496635,	1527041,	1557447,	1587853,	1618259,	1648665,	1679071,	1709477,	1739883,	1770290,	1800696,	1831102,	1861508,	1891914,	1922320,	1952726,	1983132,	2013538,	2043944,	2074350,	2104756,	2135162,	2165568,	2195974,	2226380,	2256787,	2287193,	2317599,	2348005,	2378411,	2408817,	2439223,	2469629,	2500035,	2530441,	2560847,	2591253,	2621659,	2652065,	2682471,	2712877,	2743284,	2773690,	2804096,	2834502,	2864908,	2895314,	2925720,	2956126,	2986532,	3016938,	3047344,	3077750,	3108156,	3138562,	3168968

            ]   
        },
        #-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#
        # ---------- T5_INSTITUCIONAL_ED ----------  
        'T5_INSTITUCIONAL_ED': {
            'COMUNAS_7': [
                15310,	36509,	60699,	87062,	115168,	144746,	175608,	207612,	240650,	274635,	309495,	345169,	381607,	418763,	456600,	495082,	534181,	573867,	614117,	654909,	696222,	738037,	780338,	823108,	866333,	909998,	954093,	998603,	1043520,	1088831,	1134526,	1180598,	1227037,	1273834,	1320981,	1368472,	1416299,	1464455,	1512934,	1561729,	1610835,	1660246,	1709956,	1759960,	1810254,	1860832,	1911690,	1962824,	2014228,	2065900,	2117834,	2170028,	2222477,	2275177,	2328126,	2381320,	2434755,	2488429,	2542338,	2596480,	2650851,	2705449,	2760270,	2815313,	2870575,	2926053,	2981744,	3037647,	3093759,	3150078,	3206601,	3263327,	3320253,	3377377,	3434698,	3492213,	3549920,	3607817,	3665904,	3724177,	3782635,	3841277,	3900101,	3959105,	4018287,	4077646,	4137181,	4196890,	4256771,	4316823,	4377044,	4437434,	4497991,	4558713,	4619599,	4680648,	4741859,	4803230,	4864760,	4926448
            ]
        },
        # ---------- T6_INSTITUCIONAL_SA ----------  
        'T6_INSTITUCIONAL_SA': {
            'COMUNAS_7': [
                25496,	56993,	91239,	127401,	165058,	203952,	243905,	284788,	326501,	368966,	412119,	455908,	500287,	545217,	590666,	636605,	683007,	729849,	777111,	824774,	872822,	921238,	970009,	1019121,	1068563,	1118324,	1168393,	1218760,	1269418,	1320356,	1371568,	1423045,	1474782,	1526770,	1579005,	1631480,	1684190,	1737128,	1790291,	1843673,	1897270,	1951077,	2005090,	2059305,	2113718,	2168325,	2223124,	2278110,	2333280,	2388631,	2444160,	2499864,	2555741,	2611787,	2668000,	2724377,	2780916,	2837614,	2894470,	2951480,	3008643,	3065957,	3123419,	3181028,	3238782,	3296678,	3354715,	3412892,	3471206,	3529656,	3588240,	3646957,	3705804,	3764782,	3823887,	3883119,	3942476,	4001957,	4061561,	4121285,	4181130,	4241094,	4301175,	4361372,	4421684,	4482111,	4542650,	4603301,	4664063,	4724935,	4785915,	4847003,	4908197,	4969497,	5030902,	5092411,	5154023,	5215737,	5277552,	5339467
            ]
        },


        # ---------- T7_INSTITUCIONAL_SER ----------  
        'T7_INSTITUCIONAL_SER': {
            'COMUNAS_7': [
                332490,	367080,	401660,	436250,	470830,	505420,	540010,	574590,	609180,	643760,	678350,	712940,	747520,	782110,	816690,	851280,	885860,	920450,	955040,	989620,	1024210,	1058790,	1093380,	1127970,	1162550,	1197140,	1231720,	1266310,	1300890,	1335480,	1370070,	1404650,	1439240,	1473820,	1508410,	1543000,	1577580,	1612170,	1646750,	1681340,	1715930,	1750510,	1785100,	1819680,	1854270,	1888850,	1923440,	1958030,	1992610,	2027200,	2061780,	2096370,	2130960,	2165540,	2200130,	2234710,	2269300,	2303880,	2338470,	2373060,	2407640,	2442230,	2476810,	2511400,	2545990,	2580570,	2615160,	2649740,	2684330,	2718920,	2753500,	2788090,	2822670,	2857260,	2891840,	2926430,	2961020,	2995600,	3030190,	3064770,	3099360,	3133950,	3168530,	3203120,	3237700,	3272290,	3306870,	3341460,	3376050,	3410630,	3445220,	3479800,	3514390,	3548980,	3583560,	3618150,	3652730,	3687320,	3721910,	3756490

            ]
        },
        
        # ---------- T8_INSTITUCIONAL_IG ----------  
        'T8_INSTITUCIONAL_IG': {
            'COMUNAS_7': [
                524450,	574260,	624070,	673880,	723680,	773490,	823300,	873110,	922920,	972730,	1022530,	1072340,	1122150,	1171960,	1221770,	1271580,	1321380,	1371190,	1421000,	1470810,	1520620,	1570420,	1620230,	1670040,	1719850,	1769660,	1819470,	1869270,	1919080,	1968890,	2018700,	2068510,	2118320,	2168120,	2217930,	2267740,	2317550,	2367360,	2417160,	2466970,	2516780,	2566590,	2616400,	2666210,	2716010,	2765820,	2815630,	2865440,	2915250,	2965060,	3014860,	3064670,	3114480,	3164290,	3214100,	3263900,	3313710,	3363520,	3413330,	3463140,	3512950,	3562750,	3612560,	3662370,	3712180,	3761990,	3811800,	3861600,	3911410,	3961220,	4011030,	4060840,	4110650,	4160450,	4210260,	4260070,	4309880,	4359690,	4409490,	4459300,	4509110,	4558920,	4608730,	4658540,	4708340,	4758150,	4807960,	4857770,	4907580,	4957390,	5007190,	5057000,	5106810,	5156620,	5206430,	5256230,	5306040,	5355850,	5405660,	5455470
            ]
        },
        #-----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------#
        
        # ---------- T9_HOTELES ----------  FALTA
        'T9_HOTELES': {
            'COMUNAS_7': [
            54610,	108939,	163164,	217320,	271426,	325492,	379524,	433527,	487506,	541462,	595398,	649316,	703217,	757103,	810975,	864833,	918679,	972513,	1026336,	1080149,	1133952,	1187745,	1241529,	1295304,	1349072,	1402831,	1456582,	1510327,	1564064,	1617794,	1671518,	1725235,	1778946,	1832651,	1886350,	1940043,	1993731,	2047414,	2101091,	2154763,	2208430,	2262093,	2315750,	2369403,	2423052,	2476696,	2530336,	2583971,	2637603,	2691230,	2744854,	2798473,	2852089,	2905701,	2959309,	3012914,	3066515,	3120113,	3173707,	3227298,	3280885,	3334470,	3388051,	3441629,	3495204,	3548775,	3602344,	3655910,	3709473,	3763033,	3816590,	3870145,	3923697,	3977246,	4030792,	4084335,	4137877,	4191415,	4244951,	4298484,	4352015,	4405544,	4459070,	4512594,	4566115,	4619634,	4673151,	4726665,	4780177,	4833687,	4887195,	4940701,	4994204,	5047705,	5101205,	5154702,	5208197,	5261690,	5315181,	5368670
            ]
        },
        

        
        # ---------- T11_CCOMERCIALES ----------  
        'T11_CCOMERCIALES': {
            'COMUNAS_7': [
            66590,	123828,	177998,	230266,	281164,	330997,	379960,	428192,	475793,	522840,	569395,	615507,	661217,	706558,	751560,	796247,	840642,	884764,	928628,	972251,	1015645,	1058822,	1101794,	1144570,	1187159,	1229569,	1271808,	1313884,	1355801,	1397567,	1439187,	1480667,	1522010,	1563222,	1604306,	1645268,	1686110,	1726837,	1767451,	1807955,	1848354,	1888649,	1928843,	1968940,	2008940,	2048848,	2088664,	2128392,	2168032,	2207588,	2247061,	2286453,	2325765,	2364999,	2404157,	2443240,	2482250,	2521188,	2560056,	2598855,	2637585,	2676249,	2714848,	2753382,	2791853,	2830262,	2868610,	2906898,	2945127,	2983297,	3021411,	3059468,	3097469,	3135416,	3173309,	3211149,	3248937,	3286673,	3324359,	3361994,	3399580,	3437117,	3474606,	3512048,	3549443,	3586792,	3624095,	3661353,	3698567,	3735737,	3772863,	3809947,	3846988,	3883988,	3920946,	3957864,	3994741,	4031578,	4068375,	4105134

            ]
        },

        # ---------- T13_UNIDAD_DEPORTIVA ----------  
        'T13_UNIDAD_DEPORTIVA': {
            'COMUNAS_7': [
            67185,	83645,	100106,	116566,	133027,	149488,	165948,	182409,	198869,	215330,	231791,	248251,	264712,	281172,	297633,	314093,	330554,	347015,	363475,	379936,	396396,	412857,	429318,	445778,	462239,	478699,	495160,	511621,	528081,	544542,	561002,	577463,	593924,	610384,	626845,	643305,	659766,	676226,	692687,	709148,	725608,	742069,	758529,	774990,	791451,	807911,	824372,	840832,	857293,	873754,	890214,	906675,	923135,	939596,	956057,	972517,	988978,	1005438,	1021899,	1038359,	1054820,	1071281,	1087741,	1104202,	1120662,	1137123,	1153584,	1170044,	1186505,	1202965,	1219426,	1235887,	1252347,	1268808,	1285268,	1301729,	1318190,	1334650,	1351111,	1367571,	1384032,	1400492,	1416953,	1433414,	1449874,	1466335,	1482795,	1499256,	1515717,	1532177,	1548638,	1565098,	1581559,	1598020,	1614480,	1630941,	1647401,	1663862,	1680323,	1696783,

            ]
            
        }
        
    }		

    print("🚀 Iniciando liquidación optimizada...")

    # =============================================================================
    # PREPARACIÓN INICIAL (UNA SOLA VEZ)
    # =============================================================================
    print("🔧 Preparando datos...")

    # Ajustar tipos de datos UNA SOLA VEZ
    df_const['COMUNA'] = df_const['COMUNA'].astype(str)
    df_const['TABLA_ORIGEN'] = df_const['TABLA_ORIGEN'].astype(str)
    df_const['DESTINOCONS'] = df_const['DESTINOCONS'].fillna('').astype(str)
    df_const['ACTIVIDAD'] = df_const['ACTIVIDAD'].fillna('').astype(str)
    df_const['TIPO_PARQ'] = df_const['TIPO_PARQ'].fillna('').astype(str)

    if 'PUNTCONS' in df_const.columns:
        df_const['PUNTCONS'] = df_const['PUNTCONS'].astype(int)

    # Crear columna resultado (UNA SOLA VEZ)
    df_const['VM2_FINAL_V3'] = 0

    # =============================================================================
    # 1️⃣ TABLAS NORMALES (T1-T9, T11) - CON MERGE
    # =============================================================================
    print("📊 Liquidando tablas T1-T9 y T11...")

    # ⚠️ Filtrar para no liquidar tablas SIN TABLA, MODELO o ESPECIALES
    tablas_a_liquidar = df_const[~df_const['TABLA_ORIGEN'].isin(['SIN TABLA', 'MODELO', 'ESPECIALES'])].copy()

    lista_mapping = []
    for tabla, grupos_valores in valores_por_tabla.items():
        for clave_grupo, lista_valores in grupos_valores.items():
            comunas = {'COMUNAS_2': comunas_2, 'COMUNAS_5': comunas_5, 'COMUNAS_7': comunas_7}[clave_grupo]
            for puntcons, valor in enumerate(lista_valores, start=1):
                for comuna in comunas:
                    lista_mapping.append({
                        'TABLA_ORIGEN': tabla,
                        'PUNTCONS': puntcons,
                        'COMUNA': comuna,
                        'VM2_FINAL_V3_nuevo': valor  # ← nombre temporal
                    })

    df_mapeo = pd.DataFrame(lista_mapping)
    df_mapeo['PUNTCONS'] = df_mapeo['PUNTCONS'].astype(int)
    df_mapeo['COMUNA'] = df_mapeo['COMUNA'].astype(str)
    df_mapeo['TABLA_ORIGEN'] = df_mapeo['TABLA_ORIGEN'].astype(str)

    # Merge solo con las tablas permitidas
    tablas_a_liquidar = tablas_a_liquidar.merge(
        df_mapeo,
        on=['TABLA_ORIGEN', 'PUNTCONS', 'COMUNA'],
        how='left'
    )

    # Actualizar SOLO donde existe el valor mapeado
    mask_con_valor = tablas_a_liquidar['VM2_FINAL_V3_nuevo'].notna()
    tablas_a_liquidar.loc[mask_con_valor, 'VM2_FINAL_V3'] = tablas_a_liquidar.loc[mask_con_valor, 'VM2_FINAL_V3_nuevo']
    tablas_a_liquidar.drop(columns=['VM2_FINAL_V3_nuevo'], inplace=True)

    # 🔄 Reintegrar los resultados de vuelta al df_const original
    df_const.loc[
    df_const['TABLA_ORIGEN'].isin(tablas_a_liquidar['TABLA_ORIGEN'].unique()), 'VM2_FINAL_V3'
    ] = tablas_a_liquidar['VM2_FINAL_V3'].values
    
    # =============================================================================
    # PASO 1: SEPARAR LAS 5 COMUNAS PRIMERO (antes de liquidar)
    # =============================================================================

    print("📦 Separando anexos por comunas...")


    df_anexos_2 = df_const[
    (df_const['TABLA_ORIGEN'] == 'T10_ANEXOS') &
    (df_const['COMUNA'].isin(['03', '22']))].copy()

    print(df_anexos_2.dtypes)
    
    df_anexos_5 = df_const[
    (df_const['TABLA_ORIGEN'] == 'T10_ANEXOS') &
    (~df_const['COMUNA'].isin(['03', '22']))].copy()
    
    print(df_anexos_5.dtypes)
    
    df_conv_liq = df_const[df_const['TABLA_ORIGEN'] != 'T10_ANEXOS'].copy()
    
    
    
    
    print(f"✓ T10_ANEXOS (2 comunas): {len(df_anexos_2)}")
    print(f"✓ T10_ANEXOS (5 comunas): {len(df_anexos_5)}")
    
    
    print(f"✓ construcciones convencionales: {len(df_conv_liq)}")
    
    print(f"✓ construcciones total: {len(df_const)}")
    del df_const
    gc.collect()
    # =============================================================================
    # 2️⃣ ANEXOS (T10) 2 COMUNAS 
    # =============================================================================


    condiciones_anexos_2  = [
        
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "077") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "077") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "078") & (df_anexos_2['TIPOANEXO'] == 10)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "078") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "113") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "110") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "080") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "080") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "080") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "080") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "081") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "081") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "081") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "082") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "082") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "082") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "082") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "114") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "114") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "085") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "085") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "085") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "086") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "086") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "086") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "089") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "089") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "089") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "089") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "092") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "092") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "092") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "092") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "094") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "094") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "094") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "094") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "111") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "111") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "111") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "098") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "098") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "098") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "098") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "098") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "100") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "100") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "101") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "101") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "101") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "101") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "101") & (df_anexos_2['TIPOANEXO'] == 90)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "102") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "103") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "103") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "104") & (df_anexos_2['TIPOANEXO'] == 20)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "104") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "104") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "104") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "105") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "105") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "105") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "079") & (df_anexos_2['TIPOANEXO'] == 10)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "083") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "084") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "091") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "097") & (df_anexos_2['TIPOANEXO'] == 40)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "097") & (df_anexos_2['TIPOANEXO'] == 60)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "118") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "109") & (df_anexos_2['TIPOANEXO'] == 30)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "109") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "109") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "112") & (df_anexos_2['TIPOANEXO'] == 30)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "112") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "112") & (df_anexos_2['TIPOANEXO'] == 80)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "115") & (df_anexos_2['TIPOANEXO'] == 30)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "115") & (df_anexos_2['TIPOANEXO'] == 50)),
        ((df_anexos_2['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_2['DESTANEX'] == "115") & (df_anexos_2['TIPOANEXO'] == 80))
        
        ]

    valores_anexos_2  = [
        322359,	264772,	227205,	169255,	184409,	1894559,	403959,	582989,	605120,	1124194,	313340,	567339,	736096,	358589,	656246,	823887,	965363,	1118735,	1736860,	87998,	196916,	658524,	373286,	639143,	1104999,	306067,	515746,	613393,	861409,	442090,	567383,	645197,	1109845,	276086,	435638,	540028,	764118,	124355,	160276,	270241,	1062896,	1259182,	1547400,	1741858,	2108509,	798215,	1770636,	230083,	455681,	520195,	767402,	1049951,	262937,	1466809,	3523696,	596827,	782898,	1293343,	3256335,	971469,	2279142,	3911668,	277431,	765761,	3142651,	1042886,	524504,	759355,	596317,	167448,	213116,	270274,	2620691,	3335438,	4230005,	1572620,	2001525,	2538335,
    ]

    print("Condiciones:", len(condiciones_anexos_2))
    print("Valores:", len(valores_anexos_2))

    df_anexos_2['VM2_FINAL_V3'] = np.select(
        condiciones_anexos_2,     
        valores_anexos_2,          
        default=0
    )
    # =============================================================================
    # 2️⃣ ANEXOS (T10) 5 COMUNAS 
    # =============================================================================

    condiciones_anexos_5  = [
        
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "077") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "077") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "078") & (df_anexos_5['TIPOANEXO'] == 10)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "078") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "113") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "110") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "080") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "080") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "080") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "080") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "081") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "081") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "081") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "082") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "082") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "082") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "082") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "114") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "114") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "085") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "085") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "085") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "086") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "086") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "086") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "086") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "089") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "089") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "089") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "089") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "092") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "092") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "092") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "092") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "094") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "094") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "094") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "094") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "111") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "111") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "111") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "098") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "098") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "098") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "098") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "098") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "100") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "100") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "101") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "101") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "101") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "101") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "101") & (df_anexos_5['TIPOANEXO'] == 90)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "102") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "103") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "103") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "104") & (df_anexos_5['TIPOANEXO'] == 20)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "104") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "104") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "104") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "105") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "105") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "105") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "105") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "079") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "083") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "084") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "091") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "091") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "097") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "097") & (df_anexos_5['TIPOANEXO'] == 60)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "118") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "109") & (df_anexos_5['TIPOANEXO'] == 30)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "109") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "109") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "112") & (df_anexos_5['TIPOANEXO'] == 30)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "112") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "112") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "115") & (df_anexos_5['TIPOANEXO'] == 30)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "115") & (df_anexos_5['TIPOANEXO'] == 50)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "115") & (df_anexos_5['TIPOANEXO'] == 80)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "088") & (df_anexos_5['TIPOANEXO'] == 40)),
        ((df_anexos_5['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_anexos_5['DESTANEX'] == "116") & (df_anexos_5['TIPOANEXO'] == 40))

        
        ]
    valores_anexos_5  = [
    # ---------- T10_ANEXOS ----------  
          148160,	173186,	94711,	127138,	103191,	1060149,	196817,	318848,	440879,	562910,	183192,	301413,	419634,	225009,	336329,	447650,	558970,	625693,	971402,	16253,	175861,	335468,	157411,	190211,	394819,	599426,	172503,	271428,	370354,	469279,	211194,	327879,	444563,	561247,	150020,	237932,	325844,	413757,	63268,	114958,	132188,	560196,	762502,	863655,	964808,	1167113,	446479,	990805,	113416,	231616,	349817,	468017,	527117,	146677,	820366,	1970754,	117143,	591882,	1066621,	1541360,	688573,	1075869,	1699036,	2237756,	154762,	428501,	1758551,	583272,	947461,	292590,	498782,	333684,	94702,	117584,	151907,	1481396,	1839332,	2376236,	888954,	1103743,	1425928,	1309671,	202362,
    ]

    print("Condiciones:", len(condiciones_anexos_5))
    print("Valores:", len(valores_anexos_5))

    df_anexos_5['VM2_FINAL_V3'] = np.select(
        condiciones_anexos_5,
        valores_anexos_5,
        default=0
    )

    df_const = pd.concat([df_anexos_5,df_anexos_2,df_conv_liq],ignore_index=True)
    
    del df_anexos_2, df_anexos_5, df_conv_liq
    
    gc.collect()
    
    # =============================================================================
    # 3️⃣ PARQUEADEROS (T12) - CON NP.SELECT
    # =============================================================================
    print("🚗 Liquidando parqueaderos...")

    mask_parq = df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS'
    df_parq = df_const[mask_parq].copy()

    # Condiciones SIN repetir TABLA_ORIGEN (ya están filtrados)
    condiciones_parqueaderos = [
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 1) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '11') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble'])))
        )
        # 1 - 4.800.000
        ,

        ( 
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 2) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '12') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble'])))
            
        ),
        #2 - 12.000.000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 3) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '13') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo', 'Doble'])))
        ),
        #3 - 18.000.0000
        (
            
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 4) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '14') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo'])))

        ),
        #4 - 27.000.000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 5) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '15') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo'])))
        ),
        #5 - 37.000.0000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 6) & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '16') & 
            (df_parq['TIPO_PARQ'].isin(['Sencillo'])))
        ),
        #6 - 48.000.0000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (df_parq['ACTIVIDAD'].isin(['21', '22'])) & 
            (df_parq['TIPO_PARQ'] == 'Sencillo')
        ),
        #7 - 46.000.0000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (df_parq['ACTIVIDAD'] == '23') & 
            (df_parq['TIPO_PARQ'] == 'Sencillo')
        ),
        #8 - 48.000.000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 4) & 
            (df_parq['TIPO_PARQ'].isin(['Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '14') & 
            (df_parq['TIPO_PARQ'].isin(['Doble'])))  
        ),
        ### 9- 30.590.000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 5) & 
            (df_parq['TIPO_PARQ'].isin(['Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '15') & 
            (df_parq['TIPO_PARQ'].isin(['Doble'])))  
        ),
        #10 - 42.624.000
        (
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 6) & 
            (df_parq['TIPO_PARQ'].isin(['Doble']))) |
            ((df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '16') & 
            (df_parq['TIPO_PARQ'].isin(['Doble'])))  
        ),
        #11- 57.790.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (df_parq['ACTIVIDAD'].isin(['21', '22'])) & 
            (df_parq['TIPO_PARQ'] == 'Doble')
        ),
        #12 - 70.299.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (df_parq['ACTIVIDAD'] == '23') & 
            (df_parq['TIPO_PARQ'] == 'Doble')
        ),
        #13 - 77.275.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (~df_parq['ACTIVIDAD'].isin(['21', '22', '23'])) & 
            (df_parq['TIPO_PARQ'] == 'Sencillo')
        ),

        #14 - 48.000.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['036', '037'])) & 
            (~df_parq['ACTIVIDAD'].isin(['21', '22', '23'])) & 
            (df_parq['TIPO_PARQ'] == 'Doble')
        ),

        #15 - 57.790.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 1)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '11')
        ),
        #16- 750.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 2)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '12')

        ),
        #17 - 750.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 3)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '13')
        ),
        #18 - 850.000
        (
        (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 4)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '14')
        ),
        #19 - 1300.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 5)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '15')
        ),
        #20 - 1600.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'] == 6)) | 
            (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])) & 
            (df_parq['ESTRPRED'].isna() | (df_parq['ESTRPRED'] == 0)) & 
            (df_parq['ACTIVIDAD'] == '16')
        ),
        #21 - 1800.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006'])|df_parq['DESTINOCONS'].isin(['027'])) & 
            (df_parq['ESTRPRED'] == 0) &
            (df_parq['ACTIVIDAD'].isin(['11','12','13','14','15','16','21', '22'])) ### Aqui agregue los residenciales
        ),
        #22 - 1450000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['006']) | df_parq['DESTINOCONS'].isin(['027'])) & 
            (df_parq['ESTRPRED'] == 0) & 
            (~df_parq['ACTIVIDAD'].isin(['11','12','13','14','15','16','21', '22']))  ## aqui los quite es decir que liquidaran a 1.8 los 023
        ),
        ##23- 1.800.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 0) & 
            (df_parq['ACTIVIDAD'].isin(['21', '22'])) & 
            (df_parq['TIPO_PARQ'] == 'Sencillo') 
        ),

        ##24 - 46.000.0000 cuando es un  garaje sin estrato en zona 21 y 22
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 0) & 
            (df_parq['ACTIVIDAD'].isin(['21', '22'])) & 
            (df_parq['TIPO_PARQ'] == 'Doble') 
        ),
        ##25- 70.299.000
        (
            (df_parq['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
            (df_parq['DESTINOCONS'].isin(['007', '008'])) & 
            (df_parq['ESTRPRED'] == 0) & 
            (~df_parq['ACTIVIDAD'].isin(['21', '22'])) & 
            (df_parq['TIPO_PARQ'] == 'Doble') 
        )

        ##77.275.000
    ]

    # Valores correspondientes a cada condición
    valores_parqueaderos = [
    #T12_PARQUEADEROS
        #1             #2          #3          #4          #5          #6          #7          #8          #9          #10         #11         #12         #13
        4800000,	12000000,	18000000,	27000000,	37000000,	48000000,	46000000,	48000000,	30590000,	42624000,	57790000,	70299000,	77275000,
        #14            #15        #16     #17     #18    #19          #20        #21          #22        #23        #24        #25             #26
        48000000,	57790000,	750000,	750000,	850000,	1300000,	1600000,	1800000,	1450000,	1800000,	46000000,	70299000,	77275000

    ]

    df_const.loc[mask_parq, 'VM2_FINAL_V3'] = np.select(
        condiciones_parqueaderos,
        valores_parqueaderos,
        default=0
    )
    
    def actualizar_valores(df_const):
        """
        Aplica factor de área y calcula LIQ_PARQUEADERO solo para códigos 007, 008, 036, 037
        """
        
        # Códigos afectados
        codigos_afectados = ['007', '008', '036', '037']
        
        # Condiciones solo para códigos afectados
        condiciones = [       
            ((df_const['DESTINOCONS'].isin(['007', '008'])) & (df_const['AREA_CONST'].between(1, 25))),
            ((df_const['DESTINOCONS'].isin(['007', '008'])) & (df_const['AREA_CONST'].between(26, 500))),
            ((df_const['DESTINOCONS'].isin(['007', '008'])) & (df_const['AREA_CONST'] > 500)),
            ((df_const['DESTINOCONS'].isin(['036', '037'])) & (df_const['AREA_CONST'] <= 50)),
            ((df_const['DESTINOCONS'].isin(['036', '037'])) & (df_const['AREA_CONST'] > 50))
        ]

        factores = [
            1,  # entre 1 y 25
            df_const['AREA_CONST'] / 25,
            df_const['AREA_CONST'] / 50,
            1,
            df_const['AREA_CONST'] / 50
        ]

        # Calcular FACTOR_AREA (NaN para no afectados)
        df_const['FACTOR_AREA'] = np.select(condiciones, factores, default=np.nan)
        
        # LIQ_PARQUEADERO solo para códigos afectados, NaN para el resto
        df_const['LIQ_PARQUEADERO'] = np.where(
            df_const['DESTINOCONS'].isin(codigos_afectados),  # Solo códigos afectados
            df_const['VM2_FINAL_V3'] * df_const['FACTOR_AREA'],  # Con factor
            np.nan  # NaN para todos los demás
        )
        # Renombrar la columna
        df_const = df_const.rename(columns={'VM2_FINAL_V3': 'VM2'})

        # Mover VM2 al final
        cols = [c for c in df_const.columns if c != 'VM2'] + ['VM2']
        df_const = df_const[cols]



        return df_const

    # Aplicar actualización
    df_const = actualizar_valores(df_const)
        

    # Agrupar y contar la cantidad de registros por TABLA_ORIGEN y VM2_2026
    tabla_resumen = (
        df_const.groupby(['TABLA_ORIGEN'])
        .size()
        .reset_index(name='CANTIDAD')
        .sort_values(by='CANTIDAD', ascending=False)
    )
    
    
    
    # Mostrar la tabla
    print(tabla_resumen)
 
    df_liq_tabla = df_const[~df_const['TABLA_ORIGEN'].isin(['MODELO', 'ESPECIALES'])].copy()
  
    tabla_especiales =  df_const[df_const['TABLA_ORIGEN'] == 'ESPECIALES']
    tabla_especiales['VM2_ESP_2026'] = 0

    tabla_especiales['INTEGRAL_ESP_2026'] = 1
    
    # La casilla de modelos de la ventana, en una corrida de la vigencia 2026.
    if insumos.modelos_activos(2026, True):
        df_liq_modelo = ejecutar_modelos(df_const)
    else:
        print("   Modelos apagados: lo que va por modelo queda en 0")
        df_liq_modelo = pd.DataFrame()
    #df_liq_modelo.to_excel('./output/liquidacion_modelo.xlsx')
    print(f'COLUMNAS MODELO {len(df_liq_modelo)}')

    # ejecutar_modelos devuelve solo las que predice: las demas se reponen en
    # cero o desaparecen de la salida.
    tabla_modelo = df_const[df_const['TABLA_ORIGEN'] == 'MODELO'].copy()
    if df_liq_modelo is None or df_liq_modelo.empty:
        tabla_modelo['VM2_MOD'] = 0.0
        df_liq_modelo = tabla_modelo
    else:
        predichas = set(df_liq_modelo['CONSTRUCCION_ID'].astype(str))
        sin_modelo = tabla_modelo[
            ~tabla_modelo['CONSTRUCCION_ID'].astype(str).isin(predichas)].copy()
        if not sin_modelo.empty:
            sin_modelo['VM2_MOD'] = 0.0
            print(f"   {len(sin_modelo):,} construcciones van por modelo y no "
                  f"tienen familia entrenada: quedan sin valorar")
            df_liq_modelo = pd.concat([df_liq_modelo, sin_modelo],
                                      ignore_index=True)
    df_const_liq = pd.concat([df_liq_tabla, df_liq_modelo,tabla_especiales], ignore_index=True)
    

    df_const_liq['VM2'] = df_const_liq['VM2'].fillna(0)
    # Si ninguna construccion fue a modelo, ejecutar_modelos no crea la columna.
    if 'VM2_MOD' not in df_const_liq.columns:
        df_const_liq['VM2_MOD'] = 0.0
    df_const_liq['VM2_MOD'] = df_const_liq['VM2_MOD'].fillna(0)
    df_const_liq['LIQ_PARQUEADERO'] = df_const_liq['LIQ_PARQUEADERO'].fillna(0)
    #df_const_liq['VM2_ESP_2026'] = df_const_liq['VM2_ESP_2026'].fillna(0)
    #df_const_liq['INTEGRAL_ESP_2026'] = df_const_liq['INTEGRAL_ESP_2026'].fillna(0)
    df_const_liq = convertir_a_float(df_const_liq,['VM2','VM2_MOD','LIQ_PARQUEADERO'])
    #df_const_liq = convertir_a_string(df_const_liq['ID_PREDIO','NUMERO_PREDIAL_NACIONAL','CONSTRUCCION_ID','ZHF'])
    # ============================================================================
    # CRUCE DE ARCHIVO DE ESPECIALES
    # ============================================================================

    # ========================================================================
    # ESPECIALES: de la base CONVENCIONAL (ESPECIAL / VALOR_M2 / INTEGRAL).
    # ORIGEN_ESPECIAL queda vacia: esa marca solo existia en el Excel.
    # ========================================================================
    print("\nEspeciales desde la base convencional...")

    if 'ESPECIAL' in df_const_liq.columns:
        es_especial = df_const_liq['ESPECIAL'].astype(str).str.strip() == '1'
    else:
        es_especial = pd.Series(False, index=df_const_liq.index)
    vm2_esp = (pd.to_numeric(df_const_liq['VALOR_M2'], errors='coerce').fillna(0)
               if 'VALOR_M2' in df_const_liq.columns
               else pd.Series(0.0, index=df_const_liq.index))
    integral = (pd.to_numeric(df_const_liq['INTEGRAL'], errors='coerce').fillna(0)
                if 'INTEGRAL' in df_const_liq.columns
                else pd.Series(0, index=df_const_liq.index))

    df_const_liq['ESPECIAL_2026'] = es_especial.astype(int)
    df_const_liq['VM2_ESP_2026'] = np.where(es_especial, vm2_esp, 0.0)
    df_const_liq['INTEGRAL_ESP_2026'] = np.where(es_especial, integral, 0).astype(int)
    df_const_liq['VM2_INT_ESP_2026'] = np.where(
        df_const_liq['INTEGRAL_ESP_2026'] == 1, vm2_esp, 0.0)
    df_const_liq['ORIGEN_ESPECIAL'] = ''

    print(f"   ESPECIAL_2026 = 1: {int(es_especial.sum()):,} registros")
    print(f"   INTEGRAL_ESP_2026 = 1: "
          f"{int((df_const_liq['INTEGRAL_ESP_2026'] == 1).sum()):,} registros")

    # ============================================================================
    # RELLENAR NaN CON 0 (POR SEGURIDAD)
    # ============================================================================

    df_const_liq['VM2_ESP_2026'] = df_const_liq['VM2_ESP_2026'].fillna(0)
    df_const_liq['VM2_INT_ESP_2026'] = df_const_liq['VM2_INT_ESP_2026'].fillna(0)
    df_const_liq['INTEGRAL_ESP_2026'] = df_const_liq['INTEGRAL_ESP_2026'].fillna(0)
    df_const_liq['ESPECIAL_2026'] = df_const_liq['ESPECIAL_2026'].fillna(0)
    df_const_liq['ORIGEN_ESPECIAL'] = df_const_liq['ORIGEN_ESPECIAL'].fillna('')

    # ============================================================================
    # RESUMEN
    # ============================================================================

    print("\n" + "="*70)
    print("📊 RESUMEN DEL CRUCE CON ESPECIALES")
    print("="*70)
    print(f"Total registros en df_const_liq:     {len(df_const_liq):,}")
    print(f"Registros marcados ESPECIAL_2026=1:  {(df_const_liq['ESPECIAL_2026'] == 1).sum():,}")
    print(f"Registros con INTEGRAL_ESP_2026=1:   {(df_const_liq['INTEGRAL_ESP_2026'] == 1).sum():,}")
    print(f"Registros con VM2_ESP_2026 > 0:      {(df_const_liq['VM2_ESP_2026'] > 0).sum():,}")
    print(f"Registros con VM2_INT_ESP_2026 > 0:  {(df_const_liq['VM2_INT_ESP_2026'] > 0).sum():,}")
    print("="*70)

    # Mostrar estadísticas de valores asignados
    if (df_const_liq['VM2_ESP_2026'] > 0).sum() > 0:
        print("\n📈 Estadísticas de VM2_ESP_2026:")
        print(df_const_liq[df_const_liq['VM2_ESP_2026'] > 0]['VM2_ESP_2026'].describe())

    if (df_const_liq['VM2_INT_ESP_2026'] > 0).sum() > 0:
        print("\n📈 Estadísticas de VM2_INT_ESP_2026:")
        print(df_const_liq[df_const_liq['VM2_INT_ESP_2026'] > 0]['VM2_INT_ESP_2026'].describe())

    # Mostrar distribución por ORIGEN_ESPECIAL
    if (df_const_liq['ESPECIAL_2026'] == 1).sum() > 0:
        print("\n📋 Distribución por ORIGEN_ESPECIAL:")
        print(df_const_liq[df_const_liq['ESPECIAL_2026'] == 1]['ORIGEN_ESPECIAL'].value_counts())

    print("\n✅ Cruce con especiales completado exitosamente")
    


    print(f'DIFERENCIA ENTRE  DF_CONST_LIQ -DF_CONST  {len(df_const_liq)-len(df_const)}')

    #print(f'DUPLICADO {df_const_liq['CONSTRUCCION_ID'].duplicated().sum()}')

    ### Ojo aqui
    #df_const_liq = df_const_liq.drop_duplicates(subset='CONSTRUCCION_ID', keep='first')
    
    print(f'DIFERENCIA ENTRE  DF_CONST_LIQ -DF_CONST DESPUES DE QUITAR DUPLICADOS {len(df_const_liq)-len(df_const)}')

    
    fecha_actual = datetime.now().strftime('%Y%m%d')



    # Guardar el DataFrame en un archivo de texto delimitado por comas (txt)
    #df_const_liq.to_csv(f'./output/{fecha_actual}_LIQUIDACION_TABLAS.txt',sep ="|", index=False)

    ### Generar marca para los que van con avaluo 2025

    # df_const_liq['NO_CAMBIA_AVALUO'] = (
    # df_const_liq['DESTINOCONS'].isin(['028']) &
    # (df_const_liq['CONDICION'] == 9)
    # ).astype(int)

    df_const_liq['NO_CAMBIA_AVALUO'] = 0
    print(f'LOS QUE QUEDAN CON EL MISMO AVALUO 2025 {df_const_liq['NO_CAMBIA_AVALUO'].value_counts()}')

    print(f'USOS {df_const_liq.columns.tolist()}')

    return df_const_liq


print("Liquidacion tablas: OK")


