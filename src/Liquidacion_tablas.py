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
from perf import crono  # ⏱️ medición de tiempos
from consolidar_tablas import tabla_valor_vigente
from tabla_construccion import (convertir_a_cero, convertir_a_float,
                                convertir_a_string, COMUNAS_7, COMUNAS_10)



warnings.filterwarnings("ignore")

### Cargar archivos
# 1. Tabla df_const

def tablas_liquidacion(df_const):  

    ruta_especiales = "./input/ESPECIALES/20260303_PREDIOS_ESPECIALES_ACT_2025.xlsx" ### Ojo aqui


    print(f'Tipo de columnas df const {df_const.dtypes}')
  
    

    #df_const['ZHF'] = df_const['ZHF'].astype(str).where(df_const['ZHF'].notna(), np.nan)
    df_const = df_const[df_const['ZHF'].notna()].copy()

    df_const['ZHF'] = df_const['ZHF'].astype(str)

    # La tipologia son los ULTIMOS TRES digitos del ZHF, no una posicion fija.
    # El codigo viene en dos largos, 11 y 13 caracteres, y con str[8:11] los de
    # 13 quedaban corridos dos posiciones: devolvian 110, 210, 310... que no
    # existen como tipologia, asi que esos predios parecian no tenerla y se
    # liquidaban por estrato aunque su ZHF si la traia.
    # Menos de 11 caracteres no es un codigo de ZHF (hay filas en '0' y codigos
    # truncados de 7 a 9): esas quedan vacias, igual que antes.
    _zhf = df_const['ZHF'].str.strip()
    _tipologia = _zhf.str[-3:].where(_zhf.str.len() >= 11, '')

    df_const['TIPOLOGIA_ZHF'] = _tipologia          # p.ej. '013'
    df_const['ACT_ECON'] = _tipologia.str[:2]       # '01'
    df_const['TIPO_SEGUN_ACT'] = _tipologia.str[2:]  # '3'
    df_const['ACTIVIDAD'] = _tipologia.str[1:]      # '13'

    # La tipologia de la ENTREGA ANTERIOR, con la misma regla, mas la marca de
    # cambio. Es lo que el equipo de tipologias necesita para ver de un golpe
    # que predios se movieron de zona. ZHF_ANTERIOR la pega
    # tabla_construccion.py desde export_predio_<fecha>; si no llega, las dos
    # columnas salen vacia y en cero sin romper nada.
    if 'ZHF_ANTERIOR' in df_const.columns:
        _zhf_ant = df_const['ZHF_ANTERIOR'].astype(str).str.strip()
        _tip_ant = _zhf_ant.str[-3:].where(_zhf_ant.str.len() >= 11, '')
    else:
        _tip_ant = pd.Series('', index=df_const.index)
    df_const['TIPOLOGIA_ZHF_ANTERIOR'] = _tip_ant

    # Tres estados, no dos. Solo se dice 1 o 0 cuando las DOS tipologias
    # existen; si a alguna le falta -vacia o en cero- no hay con que comparar
    # y se marca SIN COMPARACION.
    #
    # Antes era 1/0 literal y la cifra salia inflada: de las 29.701 marcadas
    # como cambio, unas 18.800 no habian cambiado de tipologia sino que la
    # habian GANADO -antes vacia, ahora con valor-, y el equipo de tipologias
    # habria salido a buscar reclasificaciones que no existen.
    _VACIAS = ['', '0', '000', 'nan', 'None']
    _falta = _tip_ant.isin(_VACIAS) | _tipologia.isin(_VACIAS)
    df_const['CAMBIO_TIPOLOGIA'] = np.where(
        _falta, 'SIN COMPARACIÓN',
        np.where(_tip_ant != _tipologia, '1', '0'))
        # Transformar valores
    # Primero aseguramos que los valores sean numéricos

    df_const['DESTINOCONS'] = df_const['DESTINOCONS'].astype(str).str.zfill(3)
    df_const['DESTANEX'] = df_const['DESTANEX'].astype(str).str.zfill(3)
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

    # CONDICION llega como texto ('0', '9', '5'...). Sin esto, las condiciones de
    # abajo comparan '9' == 9, que es False siempre: la rama de PH no se aplica
    # nunca y las columnas COND_9 del Excel quedan sin usar.
    df_const['CONDICION'] = pd.to_numeric(df_const['CONDICION'], errors='coerce')
    df_const['CONDICION'] = df_const['CONDICION'].fillna(0).round(0).astype('int64')

    # Grupos de comunas de las tablas de valor. Van aqui arriba porque las
    # condiciones de TABLA_ORIGEN los necesitan; la carga del Excel los vuelve a
    # usar mas abajo. En las 10 comunas el residencial se separa por condicion
    # (COND_0 / COND_9); en las 7 no, y edificios no se separa en ninguna.
    # Los dos grupos viven en tabla_construccion.py, junto al interruptor que
    # decide si las comunas 05, 06, 13, 16 y 18 entran o no. Aqui solo se leen:
    # tener una segunda copia era la forma segura de que se desincronizaran.
    comunas_7 = COMUNAS_7
    comunas_10 = COMUNAS_10

    # Por ahora la liquidacion es solo por tablas. En True, las construcciones
    # de la condicion 2 salen de su tabla y pasan a TABLA_ORIGEN = 'MODELO';
    # solo tiene sentido cuando VM2_MOD venga con valores.
    LIQUIDAR_CON_MODELO = False

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
                df_const['DESTINOCONS'].isin(['020','023']) 
             
            )
        ),

        # -------------------------------------------
        # 2. MODELO
        # -------------------------------------------
        # Apagada mientras la liquidacion sea solo por tablas: VM2_MOD viene en
        # cero en todo el parquet, asi que mandar estas construcciones a MODELO
        # las dejaria sin valor (el merge de tablas excluye TABLA_ORIGEN=MODELO).
        # Se enciende poniendo LIQUIDAR_CON_MODELO = True, arriba.
        (
            LIQUIDAR_CON_MODELO &
            (
                (
                    df_const['DESTINOCONS'].isin(['001']) &
                    (df_const['CONDICION'] == 9) &
                    df_const['COMUNA'].isin(['01','09','10','11','12','03','22'])
                )
                |
                (
                    df_const['DESTINOCONS'].isin(['028']) &
                    (df_const['CONDICION'] == 9) &
                    df_const['COMUNA'].isin(['01','09','10','11','12','03','22'])
                )
                |
                (
                    df_const['DESTINOCONS'].isin(['034']) &
                    (df_const['CONDICION'] == 9) &
                    df_const['COMUNA'].isin(['01','09','10','11','12','03','22'])
                )
            )
        ),
        
              
            # |
         # -------------------------------------------
        # 3. RESIDENCIAL POR ESTRATOS (T1) CONDICION 9 
        # -------------------------------------------
        
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '011')
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '012')
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '013')
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '014')
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '015')
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'] == '016')
        ),

        # Estrato fallback - 6 condiciones
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 1)
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 2)
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 3)
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 4)
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED'] == 5)
        ),
        (
            df_const['DESTINOCONS'].isin(["004","012","013","063"]) &
            (df_const['CONDICION'] == 9) &
            df_const['COMUNA'].isin(comunas_10) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            # Esta es la sexta del grupo y le corresponde T1_RESIDENCIAL_016_9:
            # decia ESTRPRED == 1, que ya lo habia tomado la primera condicion,
            # asi que el estrato 6 en PH se quedaba sin esta rama.
            (df_const['ESTRPRED'] == 6)
        ),



        #####

        # -------------------------------------------
        # 3. RESIDENCIAL POR ESTRATOS (T1)
        # -------------------------------------------
        # Aqui NO se vuelve a filtrar por condicion: np.select se queda con la
        # primera condicion verdadera, y los PH de las 10 comunas ya los tomo el
        # bloque de arriba (tabla _9). Si se filtrara, los casos que ese bloque
        # no alcanza -por ejemplo el destino 001, que no esta en su lista- se
        # quedarian sin tabla en vez de caer aqui.
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '011')
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '012')
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '013')
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '014')
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '015')
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'] == '016')
        ),


        # --- BLOQUE ESTRATO (sin ZHF válida) ---
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==1)
        ),
        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==2)
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==3)
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==4)
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==5)
        ),

        (
            df_const['DESTINOCONS'].isin(["001","004","012","013","063"]) &
            (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) &
            (df_const['ESTRPRED']==6)
        ),
        
        # -------------------------------------------
        # 4. EDIFICIOS (T2)
        # -------------------------------------------
        
        # ZHF primero
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '011')),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '012')),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '013')),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '014')),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '015')),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'] == '016')),

        # Estrato fallback
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 1)),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 2)),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 3)),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 4)),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 5)),
        (df_const['DESTINOCONS'].isin(["003"]) & (df_const['TIPOLOGIA_ZHF'].isna() | ~df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])) & (df_const['ESTRPRED'] == 6)),

        # -------------------------------------------
        # 5. COMERCIAL T3
        # -------------------------------------------
        (
            df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","049","028"]) &
            df_const['TIPOLOGIA_ZHF'].isin(['011','012','013','014','015','016'])
        ),

        (
            df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","049","028"]) &
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

        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="021")),
        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="022")),
        (df_const['DESTINOCONS'].isin(["016","021","024","025","039","041","049","028"]) & (df_const['TIPOLOGIA_ZHF']=="023")),

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
    # for i, cond in enumerate(condiciones_tabla):
    #     print(f"Condición {i} → tipo: {type(cond)} | válido: {isinstance(cond, (pd.Series, np.ndarray))}")
    valores_tipomode = [
        'ESPECIALES',
        'MODELO',
        'T1_RESIDENCIAL_011_9',
        'T1_RESIDENCIAL_012_9',
        'T1_RESIDENCIAL_013_9',
        'T1_RESIDENCIAL_014_9',
        'T1_RESIDENCIAL_015_9',
        'T1_RESIDENCIAL_016_9',
        'T1_RESIDENCIAL_011_9',
        'T1_RESIDENCIAL_012_9',
        'T1_RESIDENCIAL_013_9',
        'T1_RESIDENCIAL_014_9',
        'T1_RESIDENCIAL_015_9',
        'T1_RESIDENCIAL_016_9',
        

        'T1_RESIDENCIAL_011',
        'T1_RESIDENCIAL_012',
        'T1_RESIDENCIAL_013',
        'T1_RESIDENCIAL_014',
        'T1_RESIDENCIAL_015',
        'T1_RESIDENCIAL_016',
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

        print("\n📂 Cargando archivo de especiales...")

        df_especiales = pd.read_excel(ruta_especiales,sheet_name='Construcciones_especiales')

        print(f'OJOOOOOOOOOOOOOOO AQUI {df_especiales.dtypes}')
        #df_const['ID_PREDIO'] = df_const['ID_PREDIO'].astype(str)
        df_especiales['ID_PREDIO'] = df_especiales['ID_PREDIO'].round(0).astype(int).astype(str)
        df_especiales['DESTINOCONS'] = df_especiales['DESTINOCONS'].astype(str).str.zfill(3)
        df_especiales['DESTANEX'] = df_especiales['DESTANEX'].astype(str).str.zfill(3)
        df_const['CONSTRUCCION_ID'] = df_const['CONSTRUCCION_ID'].astype(str)
          
      

        print(f"   ✓ Archivo cargado: {len(df_especiales):,} registros")

        # Verificar columnas necesarias
        columnas_requeridas = ['ID_PREDIO','DESTINOCONS','DESTANEX','USO_LADM','PUNTCONS','TIPOANEXO','ACONCONS','ACONANEX','VIM2_ESPECIAL', 'ORIGEN', 'INTEGRAL_ESP_2026']


        for col in columnas_requeridas:
            if col not in df_especiales.columns:
                print(f"   ⚠️ Advertencia: Columna '{col}' no encontrada en archivo de especiales")

        print(f"\n   📋 Columnas encontradas: {list(df_especiales.columns)}")
        
        df_const['LLAVE'] = np.where(
        df_const['DESTINOCONS'] != '000',
        df_const['ID_PREDIO'].astype(str) +
        df_const['DESTINOCONS'] +
        df_const['ACONCONS'].round(0).astype(int).astype(str) +
        df_const['PUNTCONS'].astype(str),
        
        df_const['ID_PREDIO'].astype(str) +
        df_const['DESTANEX'] +
        df_const['ACONANEX'].round(0).astype(int).astype(str) +
        df_const['TIPOANEXO'].astype(str)
    )
        
        no_registros_antes_merge = len(df_const)

        df_especiales['LLAVE'] = np.where(
        df_especiales['DESTINOCONS'] != '000',
        df_especiales['ID_PREDIO'].astype(str) +
        df_especiales['DESTINOCONS'] +
        df_especiales['ACONCONS'].round(0).astype(int).astype(str) +
        df_especiales['PUNTCONS'].astype(str),
        
        df_especiales['ID_PREDIO'].astype(str) +
        df_especiales['DESTANEX'] +
        df_especiales['ACONANEX'].round(0).astype(int).astype(str) +
        df_especiales['TIPOANEXO'].astype(str))

        df_especiales.to_excel('./output/df_especiales.xlsx')
                                                                                            
        df_const = pd.merge(df_const,df_especiales[['LLAVE', 'VIM2_ESPECIAL','INTEGRAL_ESP_2026','ORIGEN']],on='LLAVE', how='left')

        df_const['VIM2_ESPECIAL'] = df_const['VIM2_ESPECIAL'].fillna(0)
        df_const['INTEGRAL_ESP_2026'] = df_const['INTEGRAL_ESP_2026'].fillna(0).astype(int)
        df_const['ORIGEN'] = df_const['ORIGEN'].fillna('NORMAL')


        no_registros_post_merge = len(df_const)
        print(f"\n✅ VERIFICAR  ANTES MERGE CON ESPECIALES {no_registros_antes_merge - no_registros_post_merge}")  
        
        condiciones_integral =  ((df_const['TABLA_ORIGEN'] == 'MODELO') |
        (df_const['TABLA_ORIGEN'] == 'T12_PARQUEADEROS') |(df_const['INTEGRAL_ESP_2026'] == 1) 
        )
        df_const['ES_INTEGRAL'] = condiciones_integral.astype(int)

        

        # ============================================================
        # 3. IDENTIFICAR CONSTRUCCIONES CON TABLA
        # ============================================================
        
        # Una construcción usa TABLA si NO es integral Y NO es anexo
        # (Los anexos se liquidarán junto con la construcción principal)
        df_const['ES_TABLA'] = (
        (df_const['ES_INTEGRAL'] == 0) &
        (df_const['TABLA_ORIGEN'] != 'T10_ANEXOS')).astype(int)

        
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
                COUNT_INFORMAL =('INFORMALIDAD','sum'),
                TOTAL_CONST=('CONSTRUCCION_ID', 'count')
            )
        )
        
        # ============================================================
        # 5. ASIGNAR MÉTODO DE LIQUIDACIÓN
        # ============================================================
        
        # Inicializar con valor por defecto
        # df_metodo['METODO_LIQUIDACION'] = 'REVISAR'
        
        # # CASO 1: MIXTO - Tiene ambos tipos (integrales y tabla)
        # df_metodo.loc[
        #     (df_metodo['COUNT_INTEGRAL'] > 0) & (df_metodo['COUNT_TABLA'] > 0),
        #     'METODO_LIQUIDACION'
        # ] = 'MIXTO'
        
        # # CASO 2: INTEGRAL - Solo tiene construcciones integrales
        # df_metodo.loc[
        #     (df_metodo['COUNT_INTEGRAL'] > 0) & (df_metodo['COUNT_TABLA'] == 0),
        #     'METODO_LIQUIDACION'
        # ] = 'INTEGRAL'
        
        # # CASO 3: TABLA + TERRENO - Solo tiene construcciones con tabla
        # df_metodo.loc[
        #     (df_metodo['COUNT_INTEGRAL'] == 0) & (df_metodo['COUNT_TABLA'] > 0),
        #     'METODO_LIQUIDACION'
        # ] = 'TABLA + TERRENO'

        #  # CASO 3: TABLA  - Solo tiene construcciones con tabla
        # df_metodo.loc[
        #     (df_metodo['COUNT_INFORMAL'] == 1) & (df_metodo['COUNT_TABLA'] > 0),
        #     'METODO_LIQUIDACION'
        # ] = 'TABLA SIN TERRENO' 
        
        # # CASO 4: SOLO ANEXOS - Solo tiene anexos (sin construcción principal)
        # df_metodo.loc[
        #     (df_metodo['COUNT_INTEGRAL'] == 0) & 
        #     (df_metodo['COUNT_TABLA'] == 0) & 
        #     (df_metodo['COUNT_ANEXOS'] > 0),
        #     'METODO_LIQUIDACION'
        # ] = 'SOLO ANEXOS'

        # Inicializar con valor por defecto
        df_metodo['METODO_LIQUIDACION'] = 'REVISAR'

        # CASO 1: MIXTO
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] > 0) & 
            (df_metodo['COUNT_TABLA'] > 0),
            'METODO_LIQUIDACION'
        ] = 'MIXTO'

        # CASO 2: INTEGRAL
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] > 0) & 
            (df_metodo['COUNT_TABLA'] == 0),
            'METODO_LIQUIDACION'
        ] = 'INTEGRAL'

        # CASO 3: TABLA SIN TERRENO (informal)
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] == 0) &
            (df_metodo['COUNT_TABLA'] > 0) &
            (df_metodo['COUNT_INFORMAL'] > 0),
            'METODO_LIQUIDACION'
        ] = 'TABLA SIN TERRENO'

        # CASO 4: TABLA + TERRENO
        df_metodo.loc[
            (df_metodo['COUNT_INTEGRAL'] == 0) &
            (df_metodo['COUNT_TABLA'] > 0) &
            (df_metodo['COUNT_INFORMAL'] == 0),
            'METODO_LIQUIDACION'
        ] = 'TABLA + TERRENO'

        # CASO 5: SOLO ANEXOS
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
    crono.marca("3.1 prep+TABLA_ORIGEN+especiales(LLAVE)+metodo")  # ⏱️

    # ✅ (Opcional) Filtrar y mostrar resumen
    
    #print(f'CONTEO POR METODO DE LIQUIDACION {df_const['METODO_LIQUIDACION'].value_counts(dropna=False)}')
    



    # =============================================================================
    # CARGAR VALORES DESDE EXCEL
    # =============================================================================
    # (comunas_7 y comunas_10 se definen arriba, junto a las condiciones de tabla:
    #  son las mismas listas y no deben quedar dos versiones que se desincronicen)
    # El consolidado mas reciente que dejo consolidar_tablas.py en
    # input/tablas/output/. Sin nombre con fecha escrito a mano: se corre el
    # consolidador y la liquidacion toma el nuevo sola.
    ruta_tabla = tabla_valor_vigente()
    if ruta_tabla is None:
        raise FileNotFoundError(
            "No hay Tablas_Valor_Consolidado_*.xlsx en input/tablas/output/. "
            "Corra primero: python src/consolidar_tablas.py")
    ruta = str(ruta_tabla)
    print(f"Tablas de valor: {ruta_tabla.name}")

    # Grupos de comunas usados tanto en CONVENCIONALES como en NO_CONVENCIONALES
    grupos_comunas = {'7': comunas_7, '10': comunas_10}

    # Cargar hoja CONVENCIONALES
    df_tablas = pd.read_excel(ruta, sheet_name='CONVENCIONALES')
    puntaje_col = df_tablas.columns[0]
    df_tablas = df_tablas.set_index(puntaje_col)

    valores_por_tabla = {}

    for col in df_tablas.columns:
        col_str = str(col).strip()
        
        valores = df_tablas[col].dropna().astype(int).tolist()
        if not valores:
            continue
        
        partes = col_str.split('_')
        
        idx_comunas = None
        num_comunas = None
        for i, p in enumerate(partes):
            if re.match(r'^(\d+)C$', p):   # 7C, 10C, ...
                idx_comunas = i
                num_comunas = p[:-1]
                break

        if idx_comunas is None:
            continue

        grupo = f'COMUNAS_{num_comunas}'

        partes_sin_comunas = partes[:idx_comunas] + partes[idx_comunas+1:]

        # 'COND_0' no hace parte del nombre de la tabla; 'COND_9' se conserva como sufijo _9
        partes_sin_comunas = [p for p in partes_sin_comunas if p != 'COND']

        if '9' not in partes_sin_comunas and '0' in partes_sin_comunas:
            partes_sin_comunas.remove('0')

        if '9' in partes_sin_comunas:
            idx_9 = partes_sin_comunas.index('9')
            partes_sin_comunas.pop(idx_9)
            partes_sin_comunas.append('9')
        
        tabla_nombre = '_'.join(partes_sin_comunas)
        
        if tabla_nombre not in valores_por_tabla:
            valores_por_tabla[tabla_nombre] = {}
        
        valores_por_tabla[tabla_nombre][grupo] = valores

    print(f"✅ Cargadas {len(valores_por_tabla)} tablas desde Excel")

    # -----------------------------------------------------------------
    # Cargar hoja NO_CONVENCIONALES (anexos T10)
    # CLAVE = DESTANEX_TIPOANEXO (ej. 077_60) y una columna por grupo de
    # comunas (NO_CONVENCIONAL_7C / NO_CONVENCIONAL_10C)
    # -----------------------------------------------------------------
    df_no_conv = pd.read_excel(ruta, sheet_name='NO_CONVENCIONALES')
    clave_col = df_no_conv.columns[0]

    # La hoja puede venir SIN FILAS: es lo que pasa mientras no se entregue la
    # tabla T10, porque consolidar_tablas.py la escribe con encabezados y nada
    # mas. Con la hoja vacia, str.split(expand=True) devuelve un DataFrame sin
    # columnas y pedirle la [0] revienta con KeyError. Se arma entonces el
    # frame vacio con las dos columnas que espera el resto del bloque: los
    # T10_ANEXOS terminan en VM2 = 0, que es lo correcto cuando no hay tabla
    # que aplicarles, y el aviso de mas abajo dice cuantos quedaron asi.
    if df_no_conv.empty:
        print("⚠️ Hoja NO_CONVENCIONALES sin filas: los anexos T10 quedan en 0 "
              "(esperado mientras no se entregue esa tabla)")
        df_no_conv['DESTANEX'] = pd.Series(dtype='object')
        df_no_conv['TIPOANEXO'] = pd.Series(dtype='int64')
    else:
        partes_clave = df_no_conv[clave_col].astype(str).str.strip().str.split('_', n=1, expand=True)
        df_no_conv['DESTANEX'] = partes_clave[0].str.zfill(3)
        df_no_conv['TIPOANEXO'] = pd.to_numeric(partes_clave[1], errors='coerce')
        df_no_conv = df_no_conv.dropna(subset=['TIPOANEXO'])
        df_no_conv['TIPOANEXO'] = df_no_conv['TIPOANEXO'].round(0).astype('int64')

    bloques_anexos = []

    for col in df_no_conv.columns:
        col_str = str(col).strip()

        match_comunas = re.search(r'_(\d+)C$', col_str)
        if match_comunas is None:
            continue

        num_comunas = match_comunas.group(1)
        comunas = grupos_comunas.get(num_comunas)

        if comunas is None:
            print(f"⚠️ Columna '{col_str}' sin grupo de comunas definido, se omite")
            continue

        valores_col = df_no_conv[['DESTANEX', 'TIPOANEXO', col]].dropna(subset=[col])

        for comuna in comunas:
            bloque = valores_col[['DESTANEX', 'TIPOANEXO']].copy()
            bloque['COMUNA'] = comuna
            bloque['VM2_ANEXO'] = valores_col[col].round(0).astype('int64').to_numpy()
            bloques_anexos.append(bloque)

    if bloques_anexos:
        df_mapeo_anexos = pd.concat(bloques_anexos, ignore_index=True)
    else:
        # Ni una columna *_7C / *_10C en la hoja: concat de una lista vacia
        # lanza "No objects to concatenate", asi que se arma el frame a mano
        # con los tipos que espera el cruce de mas abajo.
        df_mapeo_anexos = pd.DataFrame({'DESTANEX': pd.Series(dtype='object'),
                                        'TIPOANEXO': pd.Series(dtype='int64'),
                                        'COMUNA': pd.Series(dtype='object'),
                                        'VM2_ANEXO': pd.Series(dtype='int64')})
    df_mapeo_anexos = df_mapeo_anexos.drop_duplicates(subset=['DESTANEX', 'TIPOANEXO', 'COMUNA'], keep='last')

    serie_anexos = df_mapeo_anexos.set_index(['DESTANEX', 'TIPOANEXO', 'COMUNA'])['VM2_ANEXO']

    print(f"✅ Cargados {len(df_no_conv)} anexos (CLAVE) x {len(grupos_comunas)} grupos de comunas desde Excel")

    crono.marca("3.2 cargar tablas de valor (read_excel)")  # ⏱️

    # =============================================================================
    # FUNCIÓN DE LIQUIDACIÓN
    # =============================================================================
    def tablas_liquidacion(df_const):
        
        # Ajustar tipos de datos
        df_const['COMUNA'] = df_const['COMUNA'].astype(str)
        df_const['TABLA_ORIGEN'] = df_const['TABLA_ORIGEN'].astype(str)
        df_const['DESTINOCONS'] = df_const['DESTINOCONS'].fillna('').astype(str)
        df_const['ACTIVIDAD'] = df_const['ACTIVIDAD'].fillna('').astype(str)
        df_const['TIPO_PARQ'] = df_const['TIPO_PARQ'].fillna('').astype(str)

        if 'PUNTCONS' in df_const.columns:
            df_const['PUNTCONS'] = pd.to_numeric(df_const['PUNTCONS'], errors='coerce').astype(int)

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
            comunas = {'COMUNAS_7': comunas_7, 'COMUNAS_10': comunas_10}[clave_grupo]
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
    crono.marca("3.3 liquidar T1-T9/T11 (merge)")  # ⏱️

    # -----------------------------------------------------------------
    # Cobertura del merge: cuantas filas quedaron con valor y cuantas en 0
    # por no haber columna en el Excel (o por comuna/puntaje sin fila en el
    # mapeo). Es informativo: no corta el proceso ni lanza excepcion.
    # OJO: T10_ANEXOS y T12_PARQUEADEROS se liquidan mas abajo, en sus propios
    # bloques, asi que aqui todavia aparecen sin valor.
    # -----------------------------------------------------------------
    mask_liquidables = ~df_const['TABLA_ORIGEN'].isin(['SIN TABLA', 'MODELO', 'ESPECIALES'])

    resumen_cobertura = (
        df_const.loc[mask_liquidables]
        # fillna: las filas que no cruzaron quedan en NaN, y NaN != 0 daria True
        .assign(TIENE_VALOR=lambda d: d['VM2_FINAL_V3'].fillna(0) != 0)
        .groupby('TABLA_ORIGEN')['TIENE_VALOR']
        .agg(n_filas='size', n_con_valor='sum')
        .assign(n_sin_valor=lambda d: d['n_filas'] - d['n_con_valor'])
        .sort_values('n_sin_valor', ascending=False)
    )

    print("📊 Cobertura de VM2_FINAL_V3 por TABLA_ORIGEN (antes de T10 y T12):")
    print(resumen_cobertura.to_string())

    total_filas = int(mask_liquidables.sum())
    total_con_valor = int((df_const.loc[mask_liquidables, 'VM2_FINAL_V3'].fillna(0) != 0).sum())
    print(f"📊 Total: {total_con_valor}/{total_filas} filas liquidadas "
          f"({total_con_valor / total_filas * 100:.1f}%)")


    # =============================================================================
    # 2️⃣ ANEXOS (T10) - VALORES NO CONVENCIONALES POR GRUPO DE COMUNAS (7C / 10C)
    # =============================================================================

    print("📦 Liquidando anexos T10 con la hoja NO_CONVENCIONALES...")

    mask_anexos = df_const['TABLA_ORIGEN'] == 'T10_ANEXOS'
    comuna_norm = df_const['COMUNA'].astype(str).str.zfill(2)

    # Clave de cruce: DESTANEX + TIPOANEXO + COMUNA (misma clave del Excel)
    claves_anexos = pd.MultiIndex.from_arrays(
        [
            df_const.loc[mask_anexos, 'DESTANEX'].astype(str).str.zfill(3),
            df_const.loc[mask_anexos, 'TIPOANEXO'].astype('int64'),
            comuna_norm[mask_anexos],
        ],
        names=['DESTANEX', 'TIPOANEXO', 'COMUNA']
    )

    valores_anexos = serie_anexos.reindex(claves_anexos)
    sin_valor = valores_anexos.isna().to_numpy()

    df_const.loc[mask_anexos, 'VM2_FINAL_V3'] = valores_anexos.fillna(0).to_numpy()

    total_anexos = int(mask_anexos.sum())
    print(f"✓ T10_ANEXOS liquidados: {total_anexos - int(sin_valor.sum())} de {total_anexos}")

    for num_comunas, comunas in grupos_comunas.items():
        n_grupo = int((mask_anexos & comuna_norm.isin(comunas)).sum())
        print(f"  · T10_ANEXOS en {num_comunas} comunas: {n_grupo}")

    n_fuera = int((mask_anexos & ~comuna_norm.isin([c for cs in grupos_comunas.values() for c in cs])).sum())
    if n_fuera:
        print(f"⚠️ {n_fuera} anexos en comunas fuera de los grupos 7C/10C (quedan en 0)")

    if sin_valor.any():
        faltantes = df_const.loc[mask_anexos, ['DESTANEX', 'TIPOANEXO', 'COMUNA']][sin_valor].drop_duplicates()
        print(f"⚠️ {int(sin_valor.sum())} anexos sin valor en el Excel (quedan en 0) - {len(faltantes)} combinaciones:")
        print(faltantes.head(20).to_string(index=False))

    print(f"✓ construcciones total: {len(df_const)}")

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
            ((df_const['DESTINOCONS'].isin(['007', '008'])) & (df_const['AREA_CONST'] < 26 )),
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
    crono.marca("3.4 T10 anexos + T12 parqueaderos + factor area")  # ⏱️
        

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
  
    #tabla_especiales =  df_const[df_const['TABLA_ORIGEN'] == 'ESPECIALES']
    #tabla_especiales['VM2_ESP_2026'] = 0

    tabla_especiales = df_const[df_const['TABLA_ORIGEN'] == 'ESPECIALES'].copy()
    # 0.0 y no 0: la columna recibe mas abajo el VIM2_ESPECIAL, que trae
    # decimales. Inicializada en entero, pandas 3 rechaza la asignacion con
    # "Invalid value ... for dtype 'int64'" y tumba toda la liquidacion.
    tabla_especiales['VM2_ESP_2026'] = 0.0

    #tabla_especiales['INTEGRAL_ESP_2026'] = 1

    
    df_liq_modelo = ejecutar_modelos(df_const)
    crono.marca("3.5 modelos ML (ejecutar_modelos)")  # ⏱️
    
    
    if df_liq_modelo is None or df_liq_modelo.empty:
        df_const_liq = pd.concat(
            [df_liq_tabla, tabla_especiales],
            ignore_index=True
        )
        df_const_liq['VM2_MOD'] = 0
    else:
        df_const_liq = pd.concat(
            [df_liq_tabla, df_liq_modelo, tabla_especiales],
            ignore_index=True
        )

    print(f'COLUMNAS MODELO {len(df_liq_modelo)}')
    #df_const_liq = pd.concat([df_liq_tabla, df_liq_modelo,tabla_especiales], ignore_index=True)
    df_const_liq['VM2'] = df_const_liq['VM2'].fillna(0)
    df_const_liq['VM2_MOD'] = df_const_liq['VM2_MOD'].fillna(0)
    df_const_liq['LIQ_PARQUEADERO'] = df_const_liq['LIQ_PARQUEADERO'].fillna(0)
 
    df_const_liq = convertir_a_float(df_const_liq,['VM2','VM2_MOD','LIQ_PARQUEADERO'])
  
  
  
    # ============================================================================
    # CRUCE DE ARCHIVO DE ESPECIALES
    # ============================================================================

    print("\n📂 Cargando archivo de especiales...")

         # Inicializar columnas con 0
    # Las dos primeras son banderas 0/1 y pueden ser enteras; las de VALOR van
    # en flotante porque reciben el VIM2_ESPECIAL, que trae decimales (ver el
    # comentario de tabla_especiales, mas arriba).
    df_const_liq['ESPECIAL_2026'] = 0
    df_const_liq['INTEGRAL_ESP_2026'] = 0
    df_const_liq['VM2_ESP_2026'] = 0.0
    df_const_liq['VM2_INT_ESP_2026'] = 0.0
    df_const_liq['ORIGEN_ESPECIAL'] = ''

    print("   ✓ Columnas inicializadas")

    # 
    # ======================================================================
    # ASIGNAR VALORES SEGÚN REGLAS
    # ============================================================================
    mask_cruzo = df_const_liq['VIM2_ESPECIAL']>0
    print("\n📝 Asignando valores según reglas...")
    # REGLA 1: Marcar ESPECIAL_2026 = 1 para todos los que cruzaron
    df_const_liq['ESPECIAL_2026'] = (df_const_liq['VIM2_ESPECIAL'] > 0).astype(int)

    print(f"   ✓ ESPECIAL_2026 = 1: {df_const_liq['VIM2_ESPECIAL'].value_counts()} registros")

    # REGLA 2: Asignar VM2_ESP_2026 con el valor de VIM2_ESPECIAL
    df_const_liq.loc[mask_cruzo, 'VM2_ESP_2026'] = df_const_liq.loc[mask_cruzo, 'VIM2_ESPECIAL']
    df_const_liq['INTEGRAL_ESP_2026'] = (df_const_liq['INTEGRAL_ESP_2026'] > 0).astype(int)

    print(f"   ✓ VM2_ESP_2026 asignado: {df_const_liq['INTEGRAL_ESP_2026'].value_counts()} registros")

    # REGLA 3: Traer columna ORIGEN como marca identificadora

    df_const_liq['ORIGEN'] = np.where(df_const_liq['VIM2_ESPECIAL'] > 0, 'ORIGEN_ESPECIAL',df_const_liq['ORIGEN'])

   

    # REGLA 4: Si INTEGRAL_ESP_2026_archivo = 1, marcar y asignar valor integral
    # IMPORTANTE: Ahora usamos 'INTEGRAL_ESP_2026_archivo' del merge
    # mask_integral = (
    #     df_const_liq['VIM2_ESPECIAL'] > 1 & 
    #     (df_const_liq['INTEGRAL_ESP_2026'] == 1)
    # )
    mask_integral = (
    (df_const_liq['VIM2_ESPECIAL'] > 1) & 
    (df_const_liq['INTEGRAL_ESP_2026'] == 1)
    )

    df_const_liq.loc[mask_integral, 'INTEGRAL_ESP_2026'] = 1
    df_const_liq.loc[mask_integral, 'VM2_INT_ESP_2026'] = df_const_liq.loc[mask_integral, 'VIM2_ESPECIAL']

    print(f"   ✓ INTEGRAL_ESP_2026 = 1: {mask_integral.sum():,} registros")
    print(f"   ✓ VM2_INT_ESP_2026 asignado: {mask_integral.sum():,} registros")

    # ============================================================================
    # LIMPIAR COLUMNAS TEMPORALES
    # ============================================================================

    print("\n🧹 Limpiando columnas temporales...")

    # Eliminar columnas del merge que ya no se necesitan
    # IMPORTANTE: Ahora eliminamos 'INTEGRAL_ESP_2026_archivo' en lugar de 'INTEGRAL_ESP_2026'
    columnas_eliminar = ['VIM2_ESPECIAL', 'ORIGEN', 'INTEGRAL_ESP_2026_archivo']

    for col in columnas_eliminar:
        if col in df_const_liq.columns:
            df_const_liq = df_const_liq.drop(columns=[col])

    print("   ✓ Columnas temporales eliminadas")

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
    crono.marca("3.6 cruce especiales")  # ⏱️
    


    print(f'DIFERENCIA ENTRE  DF_CONST_LIQ -DF_CONST  {len(df_const_liq)-len(df_const)}')

    #print(f'DUPLICADO {df_const_liq['CONSTRUCCION_ID'].duplicated().sum()}')

    ### Ojo aqui
    #df_const_liq = df_const_liq.drop_duplicates(subset='CONSTRUCCION_ID', keep='first')
    
    print(f'DIFERENCIA ENTRE  DF_CONST_LIQ -DF_CONST DESPUES DE QUITAR DUPLICADOS {len(df_const_liq)-len(df_const)}')

    antes = len(df_const_liq)
    df_const_liq = df_const_liq.drop_duplicates(
        subset=[
            'ID_PREDIO',
            'DESTINOCONS',
            'DESTANEX',
            'ACONCONS',
            'ACONANEX',
            'PUNTCONS',
            'TIPOANEXO',
            'VM2_ESP_2026'
        ],
        keep='first'
    )
    print(f'DUPLICADOS ELIMINADOS EN SALIDA: {antes - len(df_const_liq):,} filas')
    print(f'REGISTROS FINALES df_const_liq:  {len(df_const_liq):,}')
    # ⏸️ DESACTIVADO: escribir 725k filas a .xlsx tardaba ~555s (82% del proceso).
    # Reactivar solo cuando se necesite exportar a Excel. La data ya queda en LIQUIDACION_TABLAS.parquet.
    # df_const_liq.to_excel('./output/LIQUIDACION_CONST.xlsx')
    crono.marca("3.7 to_excel LIQUIDACION_CONST (DESACTIVADO)")  # ⏱️

    # ============================================================================
    # DIAGNOSTICO: SOLO LAS CONSTRUCCIONES QUE SE LIQUIDAN POR TABLA
    # Responde "por que quedan en VM2 = 0". El valor sale del merge
    #     TABLA_ORIGEN + PUNTCONS + COMUNA
    # contra la hoja CONVENCIONALES del Excel de tablas de valor. Si cualquiera
    # de los tres no existe en el Excel, el merge no encuentra nada y el VM2 se
    # queda en el 0 con el que se inicializa.
    # ============================================================================
    print("\n" + "="*70)
    print("🔎 DIAGNOSTICO DE LAS CONSTRUCCIONES QUE SE VAN POR TABLA")
    print("="*70)

    # Tablas que NO pasan por este merge: se liquidan por otra via.
    OTRA_VIA = ['SIN TABLA', 'MODELO', 'ESPECIALES', 'T10_ANEXOS', 'T12_PARQUEADEROS']
    comunas_con_valores = set(comunas_7) | set(comunas_10)

    diag = df_const_liq[~df_const_liq['TABLA_ORIGEN'].isin(OTRA_VIA)].copy()
    diag['VM2'] = pd.to_numeric(diag['VM2'], errors='coerce').fillna(0)
    diag['COMUNA'] = diag['COMUNA'].astype(str)
    diag['PUNTCONS'] = pd.to_numeric(diag['PUNTCONS'], errors='coerce')

    # Puntajes que trae cada tabla del Excel (las filas de la hoja CONVENCIONALES)
    puntajes_por_tabla = {t: max(len(v) for v in g.values())
                          for t, g in valores_por_tabla.items()}

    sin_tabla_excel = ~diag['TABLA_ORIGEN'].isin(valores_por_tabla.keys())
    sin_comuna = ~diag['COMUNA'].isin(comunas_con_valores)
    tope = diag['TABLA_ORIGEN'].map(puntajes_por_tabla)
    sin_puntaje = diag['PUNTCONS'].isna() | (diag['PUNTCONS'] < 1) | (diag['PUNTCONS'] > tope)

    # Se informa la PRIMERA causa que aplica, en orden de importancia.
    diag['MOTIVO_VM2_CERO'] = np.select(
        [diag['VM2'] > 0, sin_tabla_excel, sin_comuna, sin_puntaje],
        ['OK (tiene valor)',
         'La TABLA no tiene valores en el Excel de tablas',
         'La COMUNA no esta en los grupos 7C/10C',
         'El PUNTCONS esta fuera del rango de la tabla'],
        default='SIN EXPLICAR (revisar)')

    n_cero = int((diag['VM2'] == 0).sum())
    print(f"Construcciones que se liquidan por tabla : {len(diag):,}")
    print(f"   ... con VM2 = 0                       : {n_cero:,} "
          f"({n_cero/len(diag)*100:.1f}%)" if len(diag) else "")
    print("\nMotivo de los ceros:")
    for motivo, cnt in diag.loc[diag['VM2'] == 0, 'MOTIVO_VM2_CERO'].value_counts().items():
        print(f"   {cnt:>8,}  {motivo}")

    faltantes = sorted(set(diag.loc[sin_tabla_excel, 'TABLA_ORIGEN'].unique()))
    if faltantes:
        print(f"\n⚠️ {len(faltantes)} TABLAS ASIGNADAS QUE NO TIENEN VALORES EN EL EXCEL:")
        print(f"   ({os.path.basename(ruta)}, hoja CONVENCIONALES)")
        for t in faltantes:
            sub = diag[diag['TABLA_ORIGEN'] == t]
            print(f"   {t:<24} {len(sub):>7,} construcciones  "
                  f"{sub['AREA_CONST'].sum():>12,.0f} m2")

    comunas_huerfanas = sorted(set(diag.loc[sin_comuna, 'COMUNA'].unique()))
    if comunas_huerfanas:
        n = int(sin_comuna.sum())
        print(f"\n⚠️ {len(comunas_huerfanas)} COMUNAS SIN GRUPO DE VALORES "
              f"({n:,} construcciones):")
        print(f"   {', '.join(comunas_huerfanas)}")
        print(f"   comunas_7  = {comunas_7}")
        print(f"   comunas_10 = {comunas_10}")

    # --- Salida a disco -----------------------------------------------------
    # Los resumenes van a Excel (son chicos). El detalle va a CSV porque son
    # cientos de miles de filas y escribirlas a .xlsx tarda minutos.
    carpeta_diag = './results/LIQUIDACION_TABLAS'
    os.makedirs(carpeta_diag, exist_ok=True)
    fecha_diag = datetime.now().strftime('%Y%m%d')

    res_tabla = (diag.assign(EN_CERO=(diag['VM2'] == 0))
                 .groupby('TABLA_ORIGEN')
                 .agg(CONSTRUCCIONES=('VM2', 'size'), EN_CERO=('EN_CERO', 'sum'),
                      PREDIOS=('ID_PREDIO', 'nunique'), AREA_M2=('AREA_CONST', 'sum'),
                      VM2_PROM=('VM2', 'mean'))
                 .reset_index())
    res_tabla['TIENE_VALORES_EN_EXCEL'] = np.where(
        res_tabla['TABLA_ORIGEN'].isin(valores_por_tabla.keys()), 'SI', 'NO')
    res_tabla['%_EN_CERO'] = (res_tabla['EN_CERO'] / res_tabla['CONSTRUCCIONES'] * 100).round(1)
    res_tabla = res_tabla.sort_values('EN_CERO', ascending=False)

    res_comuna = (diag.assign(EN_CERO=(diag['VM2'] == 0))
                  .groupby('COMUNA')
                  .agg(CONSTRUCCIONES=('VM2', 'size'), EN_CERO=('EN_CERO', 'sum'),
                       PREDIOS=('ID_PREDIO', 'nunique'), AREA_M2=('AREA_CONST', 'sum'))
                  .reset_index())
    res_comuna['GRUPO'] = np.where(res_comuna['COMUNA'].isin(comunas_7), '7C',
                          np.where(res_comuna['COMUNA'].isin(comunas_10), '10C', 'NINGUNO'))
    res_comuna['%_EN_CERO'] = (res_comuna['EN_CERO'] / res_comuna['CONSTRUCCIONES'] * 100).round(1)
    res_comuna = res_comuna.sort_values('EN_CERO', ascending=False)

    res_motivo = (diag['MOTIVO_VM2_CERO'].value_counts()
                  .rename_axis('MOTIVO_VM2_CERO').reset_index(name='CONSTRUCCIONES'))

    ruta_diag = f'{carpeta_diag}/DIAGNOSTICO_TABLAS_{fecha_diag}.xlsx'
    try:
        with pd.ExcelWriter(ruta_diag, engine='xlsxwriter') as xw:
            res_motivo.to_excel(xw, sheet_name='RESUMEN_MOTIVOS', index=False)
            res_tabla.to_excel(xw, sheet_name='POR_TABLA', index=False)
            res_comuna.to_excel(xw, sheet_name='POR_COMUNA', index=False)
        print(f"\n✅ Resumen del diagnostico: {ruta_diag}")
    except Exception as e:
        print(f"\n⚠️ No se pudo escribir {ruta_diag}: {e}")

    cols_diag = [c for c in ['ID_PREDIO', 'NUMERO_PREDIAL_NACIONAL', 'CONSTRUCCION_ID',
                             'USO_LADM', 'TABLA_ORIGEN', 'METODO_LIQUIDACION', 'COMUNA',
                             'PUNTCONS', 'AREA_CONST', 'DESTINOCONS', 'TIPOUSO',
                             'TIPOUSO_AJUSTADO', 'ANOCONST', 'VM2', 'VALORCONS',
                             'MOTIVO_VM2_CERO'] if c in diag.columns]
    ruta_det = f'{carpeta_diag}/CONSTRUCCIONES_TABLA_VM2_CERO_{fecha_diag}.txt'
    diag.loc[diag['VM2'] == 0, cols_diag].to_csv(ruta_det, sep='|', index=False,
                                                 encoding='utf-8-sig')
    print(f"✅ Detalle de las que quedan en 0: {ruta_det}")
    print("="*70)
    crono.marca("3.8 diagnostico tablas VM2=0")  # ⏱️

    print("Liquidacion tablas: OK")

    return df_const_liq




