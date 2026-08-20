import numpy as np
import pandas as pd

def uso_principal_terr(df_predio, df_conv, df_noconv):

    # --------------------------------------------------
    # 1. Merge información del predio
    # --------------------------------------------------
    # Check which columns exist in df_predio_def
    print(f'tipo variables PREDIOS {df_predio.dtypes}')

    ids_parte_1 = df_predio[df_predio['INFORMALIDAD_P1']!=1]['ID_PREDIO'].unique().tolist()
    

    df_predio_def = (
    df_predio[df_predio['ID_PREDIO'].isin(ids_parte_1)]
    .copy()
    )
    df_predio_def['NO_MEJORAS_ACT'] = df_predio_def.groupby('ID_TERR')['ID_TERR'].transform('size')
    df_predio_def['IGUAL_NO_MEJORAS'] = np.where(df_predio_def['NO_MEJORAS'] > df_predio_def['NO_MEJORAS_ACT'],0,1).astype(int)

        
    print(f'PREDIOS PRUEBA {df_predio_def[df_predio_def['ID_TERR']=='760010100090300180021']['ID_PREDIO'].tolist()}')



    df_predio_def['ACT_ECON'] = df_predio_def['ZHF'].astype(str).str[8:10]#9 y 10
    
   
    df = pd.merge(df_conv, df_predio_def[['ID_PREDIO','ARECPRED','ACONANEXT','ESTRPRED','CONDICION','ID_TERR','ACT_ECON','NO_MEJORAS','NO_MEJORAS_ACT','IGUAL_NO_MEJORAS',
                                      'CAMBIO_NPN','INFORMALIDAD_P1','INFORMALIDAD_P2','INFORMALIDAD_IGUAL_1','INFORMALIDAD_MAYOR_1']], on='ID_PREDIO',  how='left' )
    
    
    df['ACONANEXT'] = pd.to_numeric(df['ACONANEXT'], errors='coerce')
    df['ARECPRED'] = pd.to_numeric(df['ARECPRED'], errors='coerce')

    df['ESTRPRED'] = pd.to_numeric(df['ESTRPRED'], errors='coerce')
    
    df_noconv = pd.merge(df_noconv, df_predio_def[['ID_PREDIO','ARECPRED','ACONANEXT','ESTRPRED','CONDICION','ID_TERR','ACT_ECON', 'NO_MEJORAS','NO_MEJORAS_ACT','IGUAL_NO_MEJORAS', 
                                      'CAMBIO_NPN','INFORMALIDAD_P1','INFORMALIDAD_P2','INFORMALIDAD_IGUAL_1','INFORMALIDAD_MAYOR_1']], on='ID_PREDIO',  how='left' )
    print(f'tipo variables PREDIOS {df.dtypes}')
    # --------------------------------------------------
    # 2. Clasificación de uso (CAT_USO)
    # --------------------------------------------------

    

    df_noconv['ACONANEXT'] = pd.to_numeric(df_noconv['ACONANEXT'], errors='coerce')
    df_noconv['ARECPRED'] = pd.to_numeric(df_noconv['ARECPRED'], errors='coerce')

    df_noconv['ESTRPRED'] = pd.to_numeric(df_noconv['ESTRPRED'], errors='coerce')
    print(f'tipo variables NO CONVENCIONAL {df_noconv.dtypes}')
    # --------------------------------------------------
    # 2. Clasificación de uso (CAT_USO)
    # --------------------------------------------------

    condiciones_uso = [
        (df['DESTINOCONS'].between(1, 15)),
        (df['DESTINOCONS'].between(16, 44)),
        (df['DESTINOCONS'].between(45, 49)),
        (df['DESTINOCONS'].between(50, 76)),
        (df['ARECPRED'].eq(0) & df['ACONANEXT'].gt(0))
    ]

    cat_uso = [
        'RESIDENCIAL',
        'COMERCIAL',
        'INDUSTRIAL',
        'INSTITUCIONAL',
        'NO CONVENCIONAL'
    ]

    df['CAT_USO'] = np.select(condiciones_uso, cat_uso, default='SIN CATEGORIA')

    # --------------------------------------------------
    # 3. IPU
    # --------------------------------------------------
    condiciones_ipu = [
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 1)),
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 2)),
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 3)),
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 4)),
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 5)),
        ((df['CAT_USO'] == 'RESIDENCIAL') & (df['ESTRPRED'] == 6)),
        (df['CAT_USO'] == 'COMERCIAL'),
        (df['CAT_USO'] == 'INDUSTRIAL'),
        ((df['CAT_USO'] == 'INSTITUCIONAL') & df['DESTINOCONS'].isin([54,67,56,71,72])),
        ((df['CAT_USO'] == 'INSTITUCIONAL') & df['DESTINOCONS'].isin([51,55,57,60,61,62,68,69,70,73,74,76]))
    ]

    ipu = [4, 8, 10, 11, 13, 14, 14.5, 14.5, 14.5, 10]

    df['IPU'] = np.select(condiciones_ipu, ipu, default=0)

    # --------------------------------------------------
    # 4. Agregación por predio y uso
    # --------------------------------------------------
    
    df_agg = (
        df.sort_values(['ID_TERR', 'ACONCONS'], ascending=[True, False])
        .groupby(['ID_TERR', 'CAT_USO'], as_index=False)
        .agg(
            ACONCONS=('ACONCONS', 'sum'),
            IPU=('IPU', 'min'),
            DESTINOCONS=('DESTINOCONS', 'first')
        )
    )

    # --------------------------------------------------
    # 5. Selección de uso principal
    #    - mayor ACONCONS
    #    - desempate: menor IPU
    # --------------------------------------------------

    df_sorted = df_agg.sort_values(
        ['ID_TERR', 'ACONCONS', 'IPU'],
        ascending=[True, False, True],
        kind='mergesort'
    )

    uso_principal = (
        df_sorted
        .drop_duplicates('ID_TERR', keep='first')
        .reset_index(drop=True)
    )

    # --------------------------------------------------
    # 6. Merge final
    # --------------------------------------------------
   
   ### 

    df_predio_def = df_predio_def[['ID_TERR', 'TIPOUSO','TIPOPRED','IGUAL_NO_MEJORAS']].drop_duplicates()
    df_uso_p =   pd.merge(df_predio_def, uso_principal[['ID_TERR', 'CAT_USO', 'IPU','DESTINOCONS']].drop_duplicates(),
                          on='ID_TERR',how='left')
   
    #df_uso_p =  uso_principal[['ID_TERR', 'CAT_USO', 'IPU','DESTINOCONS']].drop_duplicates()
    condiciones = [
          
            # 4. Uso principal residencial
            (df_uso_p['CAT_USO'] == 'RESIDENCIAL'),

            # 5. Uso principal comercial
            (df_uso_p['CAT_USO'] == 'COMERCIAL'),

            # 6. Uso principal industrial
            (df_uso_p['CAT_USO'] == 'INDUSTRIAL'),

            # 7—14. Uso institucional por DESTINOCONS
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([50, 55, 63]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([54, 67]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([53, 60, 61]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([51, 68, 70]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([73]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([64]),
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') & df_uso_p['DESTINOCONS'].isin([56, 58, 71, 72]),

            # 15. INSTITUCIONAL no clasificado
            (df_uso_p['CAT_USO'] == 'INSTITUCIONAL') &
            (~df_uso_p['DESTINOCONS'].isin([50, 55, 63, 54, 67, 53, 60, 61,
                                        51, 68, 70, 73, 64, 56, 58, 71, 72]))
    ]   

    valores = [
       
        'A',
        'C',
        'B',
        'J',
        'H',
        'K',
        'F',
        'I',
        'Q',
        'G',
        'I'
    ]

    df_uso_p['TIPOUSO_AJUSTADO'] = np.select(
        condiciones,
        valores,
        default=''
    )

    df_uso_p['TIPOPRED'] = np.where(
        df_uso_p['TIPOPRED'].isin([' CONST. ', ' CONST.']),
        'CONST.',
        df_uso_p['TIPOPRED']
    )

    df_uso_p['CAMBIA_TIPOUSO'] = np.where(
        df_uso_p['TIPOUSO'] != df_uso_p['TIPOUSO_AJUSTADO'],
        1,
        0
    )   

    df_uso_p['TIPOPRED_AJUSTADO'] = np.where(
        ~df_uso_p['TIPOUSO_AJUSTADO'].isin(['S', 'R', 'T', 'P']),
        'CONST.',
        'LOTE'
    )
    
    
#     # Definir los rangos 
#     rango_completo = set(range(77, 121))
#     no_condicionante = {79, 80, 81, 96, 99, 100, 101, 108}
#     predominante = {95, 110}
#     condicionante = rango_completo - no_condicionante - predominante

#     condiciones = [
#         (~df_noconv['DESTANEX'].isin(rango_completo)),
#         (df_noconv['DESTANEX'].isin(no_condicionante)),
#         (df_noconv['DESTANEX'].isin(predominante)),
#         (df_noconv['DESTANEX'].isin(condicionante))
#     ]

#     valores = ['CONVENCIONAL', 'NO CONDICIONANTE', 'PREDOMINANTE', 'CONDICIONANTE']

#     df_noconv['CAT_ANEXO'] = np.select(condiciones, valores, default='ERROR: np.select tipo anexo')

#     df_noconv['ACONANEX_COND'] = df_noconv['ACONANEX'] * (df_noconv['CAT_ANEXO'] == 'CONDICIONANTE')
#     df_noconv['ES_PREDOMINANTE'] = df_noconv['CAT_ANEXO'] == 'PREDOMINANTE'



#     # agregación por terreno
#     agrupado_terr = (
#         df_uso_p
#         .groupby('ID_TERR', as_index=False)
#         .agg(
#             AREA_TERRENO=('AREAPRED', 'sum')
#         )
#         .merge(
#             df_noconv
#             .groupby('ID_TERR', as_index=False)
#             .agg(
#                 AREA_CONVENCIONAL=('ARECPRED', 'sum'),
#                 AREA_CONDICIONANTE=('ACONANEX_COND', 'sum'),
#                 PREDOMINANTE=('ES_PREDOMINANTE', 'any')
#             ),
#             on='ID_TERR',
#             how='left'
#         )
#     )

#     df_resultado = df_predio_def.copy()


#     df_resultado = (
#         df_resultado.merge(agrupado_terr,
#             on = 'ID_TERR',
#             how='left'
#         ).fillna({
#             'AREA_CONVENCIONAL': 0,
#             'AREA_CONDICIONANTE': 0,
#             'PREDOMINANTE': False
#         })
#     )

#     condiciones = [
#         (df_resultado['AREA_CONVENCIONAL'] > 0),
#         (df_resultado['AREA_CONVENCIONAL'] == 0) & (df_resultado['PREDOMINANTE']),
#         (df_resultado['AREA_CONVENCIONAL'] == 0) & (~df_resultado['PREDOMINANTE']) & (df_resultado['AREA_CONDICIONANTE']/df_resultado['AREA_TERRENO']>0.2),
#         (df_resultado['AREA_CONVENCIONAL'] == 0) & (~df_resultado['PREDOMINANTE']) & (df_resultado['AREA_CONDICIONANTE']/df_resultado['AREA_TERRENO']<=0.2)
#     ]

#     valores = ['CONST.', 
#                'CONST.', 
#                'CONST.',
#                'LOTE'
#               ]

#     df_resultado['TIPOPRED_asig'] = np.select(
#         condiciones,
#         valores,
#         default=df_resultado['TIPOPRED']
#     )

#     # Merge
#     df_uso_p = df_uso_p.merge(
#         df_resultado[['ID_TERR','TIPOPRED_asig']],
#         on='ID_TERR',
#         how='left'
#     ).drop_duplicates()

#     # Ajuste final
#     df_uso_p['TIPOPRED_AJUSTADO'] = np.where(
#         df_uso_p['TIPOPRED_asig'].notna(),
#         df_uso_p['TIPOPRED_asig'],
#         np.where(
#             ~df_uso_p['TIPOUSO_AJUSTADO'].isin(['S', 'R', 'T', 'P']),
#             'CONST.',
#             'LOTE'
#         )
#     )

# # ============================================================
# # 1. NORMALIZAR ACT_ECON (CRÍTICO)
# # ============================================================
#     df_uso_p['ACT_ECON'] = (
#         df_uso_p['ACT_ECON']
#         .astype(str)
#         .str.strip()
#         .str.replace('.0', '', regex=False)
#         .str.zfill(2)
#     )

# # ============================================================
# # 2. MAPEO DEFINITIVO ACT_ECON → TIPOUSO
# # ============================================================
#     mapa_uso = {
#         '01': 'A',
#         '02': 'C',
#         '03': 'B',
#         '04': 'I',
#         '05': 'G',
#         '06': 'S',
#         '07': 'P'
#     }

# # ============================================================
# # 3. MÁSCARA BASE (SOLO CONST. Y USOS P / S / NA)
# # ============================================================
#     mask_base = (
#         (df_uso_p['TIPOPRED_AJUSTADO'] == 'CONST.') &
#         (
#             df_uso_p['TIPOUSO_AJUSTADO'].isin(['P', 'S']) |
#             df_uso_p['TIPOUSO_AJUSTADO'].isna()
#         )
#     )

# # ============================================================
# # 4. MÁSCARA FINAL (SOLO SI ACT_ECON EXISTE EN MAPA)
# # ============================================================
#     mask_final = mask_base & df_uso_p['ACT_ECON'].isin(mapa_uso)

# # ============================================================
# # 5. ASIGNACIÓN SEGURA (NO SE PUEDE PISAR MAL)
# # ============================================================
#     df_uso_p.loc[mask_final, 'TIPOUSO_AJUSTADO'] = (
#         df_uso_p.loc[mask_final, 'ACT_ECON']
#         .map(mapa_uso)
#         .values
#     )

# # ============================================================
# # 6. VALIDACIÓN FINAL (OPCIONAL PERO RECOMENDADA)
# # ============================================================
#     print(
#         df_uso_p.loc[
#             (df_uso_p['ACT_ECON'] == '01') &
#             (df_uso_p['TIPOPRED_AJUSTADO'] == 'CONST.'),
#             'TIPOUSO_AJUSTADO'
#         ].value_counts(dropna=False)
#     )
#     df_uso_p.to_excel('./output/resultado_p1.xlsx',index=False)
#     df_terr_unico = df_uso_p[df_uso_p['AREAPRED']>0]
    return df_uso_p


