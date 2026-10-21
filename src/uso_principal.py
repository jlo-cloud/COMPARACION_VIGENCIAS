import numpy as np
import pandas as pd

def uso_principal(df_predio, df_conv, df_noconv):

    # --------------------------------------------------
    # 1. Merge información del predio
    # --------------------------------------------------
    # Check which columns exist in df_predio
    # ACT_ECON son los dos primeros digitos de la tipologia, y la tipologia son
    # los ULTIMOS TRES del ZHF: el codigo viene en 11 y en 13 caracteres, y con
    # str[8:10] los de 13 quedaban corridos dos posiciones (devolvian 21, 31,
    # 11...), que no estan en mapa_uso y por eso no asignaban TIPOUSO.
    # Menos de 11 caracteres no es un codigo de ZHF y queda vacio, como antes.
    _zhf = df_predio['ZHF'].astype(str).str.strip()
    df_predio['ACT_ECON'] = _zhf.str[-3:-1].where(_zhf.str.len() >= 11, '')

    df = pd.merge(df_conv, df_predio[['ID_PREDIO','ARECPRED','ACONANEXT','ESTRPRED','CONDICION','ID_TERR','ZHF','ACT_ECON',
                                      'CAMBIO_NPN','INFORMALIDAD_P1','INFORMALIDAD_P2','INFORMALIDAD_IGUAL_1','INFORMALIDAD_MAYOR_1']], on='ID_PREDIO',  how='left' )
    
      
    df_noconv = pd.merge(df_noconv, df_predio[['ID_PREDIO','ARECPRED','ACONANEXT','ESTRPRED','CONDICION','ID_TERR','ZHF','ACT_ECON',
                                      'CAMBIO_NPN','INFORMALIDAD_P1','INFORMALIDAD_P2','INFORMALIDAD_IGUAL_1','INFORMALIDAD_MAYOR_1']], on='ID_PREDIO',  how='left' )
    print(f'tipo variables PREDIOS {df.dtypes}')



    
    # -----------------------------------------------
    # 2. Clasificación de uso (CAT_USO)
    # --------------------------------------------------
    
    print(f'tipo variables PREDIOS {df.dtypes}')
    df['DESTINOCONS'] = pd.to_numeric(
        df['DESTINOCONS'],
        errors='coerce'
    )

    print("dtype DESTINOCONS:", df['DESTINOCONS'].dtype)

    print(
        df[df['DESTINOCONS'].isna()][['DESTINOCONS']]
        .head()
    )
    
    print("TIPOS REALES:")
    print(df['DESTINOCONS'].apply(type).value_counts())
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
        df.sort_values(['ID_PREDIO', 'ACONCONS'], ascending=[True, False])
        .groupby(['ID_PREDIO', 'CAT_USO'], as_index=False)
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
        ['ID_PREDIO', 'ACONCONS', 'IPU'],
        ascending=[True, False, True],
        kind='mergesort'
    )

    uso_principal = (
        df_sorted
        .drop_duplicates('ID_PREDIO', keep='first')
        .reset_index(drop=True)
    )

    # --------------------------------------------------
    # 6. Merge final
    # --------------------------------------------------
   
    df_uso_p = pd.merge(
        df_predio,
        uso_principal[['ID_PREDIO', 'CAT_USO', 'IPU','DESTINOCONS']],
        on='ID_PREDIO',
        how='left'
    )

    condiciones = [
        # 2. ARECPRED == 0 & CONDICION %in% c('3','4')
        ((df_uso_p['ARECPRED'] == 0) & (df_uso_p['CONDICION'].isin([3,4])) |
         (df_uso_p['TIPOUSO']=='P') & (~df_uso_p['CONDICION'].isin([3,4]))),

        # 3. ARECPRED == 0
        (df_uso_p['ARECPRED'] == 0),

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
        'P',
        'S',
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
        default=df_uso_p['TIPOUSO']
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

    # ============================================================
# NORMALIZAR ACT_ECON
# ============================================================
    df_uso_p['ACT_ECON'] = (
        df_uso_p['ACT_ECON']
        .astype(str)
        .str.strip()
        .str.replace('.0', '', regex=False)
        .str.zfill(2)
    )

    mapa_uso = {
        '01': 'A',
        '02': 'C',
        '03': 'B',
        '04': 'I',
        '05': 'G',
        '06': 'S',
        '07': 'P'
    }

    mask_final = (
        (df_uso_p['TIPOPRED_AJUSTADO'] == 'CONST.') &
        (
            df_uso_p['TIPOUSO_AJUSTADO'].isin(['P','S']) |
            df_uso_p['TIPOUSO_AJUSTADO'].isna()
        ) &
        (df_uso_p['ACT_ECON'].isin(mapa_uso))
    )

    df_uso_p.loc[mask_final, 'TIPOUSO_AJUSTADO'] = (
        df_uso_p.loc[mask_final, 'ACT_ECON'].map(mapa_uso)
    )

    df_uso_p['CAMBIA_TIPOPRED'] = np.where(
        df_uso_p['TIPOPRED'] != df_uso_p['TIPOPRED_AJUSTADO'],
        1,
        0
    )


    df_uso_p['TIPOPRED'] = np.where(
        df_uso_p['TIPOPRED'].isin([' CONST. ', ' CONST.']),
        'CONST.',
        df_uso_p['TIPOPRED']
    )

    ######################## AQUI TODO LO DE TIPO PRED #################

    # Función formato codigo homologado
    

    # Definir los rangos 
    rango_completo = set(range(77, 121))
    no_condicionante = {79, 80, 81, 96, 99, 100, 101, 108}
    predominante = {95, 110}
    condicionante = rango_completo - no_condicionante - predominante

    condiciones = [
        (~df_noconv['DESTANEX'].isin(rango_completo)),
        (df_noconv['DESTANEX'].isin(no_condicionante)),
        (df_noconv['DESTANEX'].isin(predominante)),
        (df_noconv['DESTANEX'].isin(condicionante))
    ]

    valores = ['CONVENCIONAL', 'NO CONDICIONANTE', 'PREDOMINANTE', 'CONDICIONANTE']

    df_noconv['CAT_ANEXO'] = np.select(condiciones, valores, default='ERROR: np.select tipo anexo')

    df_noconv['ACONANEX_COND'] = df_noconv['ACONANEX'] * (df_noconv['CAT_ANEXO'] == 'CONDICIONANTE')
    df_noconv['ES_PREDOMINANTE'] = df_noconv['CAT_ANEXO'] == 'PREDOMINANTE'

    # agregación por predio
    agrupado_pred = df_uso_p.groupby('ID_PREDIO', as_index=False).agg(AREA_TERRENO=('AREAPRED', 'sum')).merge(
        df_noconv.groupby('ID_PREDIO', as_index=False).agg(
            AREA_CONVENCIONAL=('ARECPRED', 'sum'),
            AREA_CONDICIONANTE=('ACONANEX_COND', 'sum'),
            PREDOMINANTE=('ES_PREDOMINANTE', 'any')
        ),                                                                                   
        on='ID_PREDIO',
        how='left'
    )

    df_resultado = df_predio[['ID_PREDIO', 'TIPOUSO', 'TIPOPRED','AREAPRED', 'ARECPRED', 'ACONANEXT','NPN_ANTERIOR','INFORMALIDAD_P1', 'INFORMALIDAD_P2', 'ID_TERR', 'CONDICION']]

    df_resultado = (
        df_resultado.merge(agrupado_pred,
            on = 'ID_PREDIO',
            how='left'
        ).fillna({
            'AREA_CONVENCIONAL': 0,
            'AREA_CONDICIONANTE': 0,
            'PREDOMINANTE': False
        })
    )

    condiciones = [
        (df_resultado['AREA_CONVENCIONAL'] > 0),
        (df_resultado['AREA_CONVENCIONAL'] == 0) & (df_resultado['PREDOMINANTE']),
        (df_resultado['AREA_CONVENCIONAL'] == 0) & (~df_resultado['PREDOMINANTE']) & (df_resultado['AREA_CONDICIONANTE']/df_resultado['AREA_TERRENO']>0.2),
        (df_resultado['AREA_CONVENCIONAL'] == 0) & (~df_resultado['PREDOMINANTE']) & (df_resultado['AREA_CONDICIONANTE']/df_resultado['AREA_TERRENO']<=0.2)
    ]

    valores = ['CONST.', 
               'CONST.', 
               'CONST.',
               'LOTE'
              ]

    df_resultado['TIPOPRED_asig'] = np.select(
        condiciones,
        valores,
        default=df_resultado['TIPOPRED']
    )

    # Merge
    df_uso_p = df_uso_p.merge(
        df_resultado[['ID_PREDIO','TIPOPRED_asig']],
        on='ID_PREDIO',
        how='left'
    )

    # Ajuste final
    df_uso_p['TIPOPRED_AJUSTADO'] = np.where(
        df_uso_p['TIPOPRED_asig'].notna(),
        df_uso_p['TIPOPRED_asig'],
        np.where(
            ~df_uso_p['TIPOUSO_AJUSTADO'].isin(['S', 'R', 'T', 'P']),
            'CONST.',
            'LOTE'
        )
    )

    # ============================================================
# 1. NORMALIZAR ACT_ECON (CRÍTICO)
# ============================================================
    df_uso_p['ACT_ECON'] = (
        df_uso_p['ACT_ECON']
        .astype(str)
        .str.strip()
        .str.replace('.0', '', regex=False)
        .str.zfill(2)
    )

# ============================================================
# 2. MAPEO DEFINITIVO ACT_ECON → TIPOUSO
# ============================================================
    mapa_uso = {
        '01': 'A',
        '02': 'C',
        '03': 'B',
        '04': 'I',
        '05': 'G',
        '06': 'S',
        '07': 'P'
    }

# ============================================================
# 3. MÁSCARA BASE (SOLO CONST. Y USOS P / S / NA)
# ============================================================
    mask_base = (
        (df_uso_p['TIPOPRED_AJUSTADO'] == 'CONST.') &
        (
            df_uso_p['TIPOUSO_AJUSTADO'].isin(['P', 'S']) |
            df_uso_p['TIPOUSO_AJUSTADO'].isna()
        )
    )

# ============================================================
# 4. MÁSCARA FINAL (SOLO SI ACT_ECON EXISTE EN MAPA)
# ============================================================
    mask_final = mask_base & df_uso_p['ACT_ECON'].isin(mapa_uso)

# ============================================================
# 5. ASIGNACIÓN SEGURA (NO SE PUEDE PISAR MAL)
# ============================================================
    df_uso_p.loc[mask_final, 'TIPOUSO_AJUSTADO'] = (
        df_uso_p.loc[mask_final, 'ACT_ECON']
        .map(mapa_uso)
        .values
    )

# ============================================================
# 6. VALIDACIÓN FINAL (OPCIONAL PERO RECOMENDADA)
# ============================================================
    print(
        df_uso_p.loc[
            (df_uso_p['ACT_ECON'] == '01') &
            (df_uso_p['TIPOPRED_AJUSTADO'] == 'CONST.'),
            'TIPOUSO_AJUSTADO'
        ].value_counts(dropna=False)
    )

    return df_uso_p


def uso_principal_const(df_predio, df_conv):

    # --------------------------------------------------
    # 1. Merge información del predio
    # --------------------------------------------------
    # Check which columns exist in df_predio

    df = pd.merge(df_conv, df_predio[['ID_PREDIO','ARECPRED','ACONANEXT','ESTRPRED','CONDICION']], on='ID_PREDIO',  how='left')
    df['INFORMALIDAD_P1'] = 0
    df['ACONANEXT'] = pd.to_numeric(df['ACONANEXT'], errors='coerce')
    df['ARECPRED'] = pd.to_numeric(df['ARECPRED'], errors='coerce')

    df['ESTRPRED'] = pd.to_numeric(df['ESTRPRED'], errors='coerce')
    
    print(f'tipo variables PREDIOS {df.dtypes}')
    
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
        df.sort_values(['ID_PREDIO', 'ACONCONS'], ascending=[True, False])
        .groupby(['ID_PREDIO', 'CAT_USO'], as_index=False)
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
        ['ID_PREDIO', 'ACONCONS', 'IPU'],
        ascending=[True, False, True],
        kind='mergesort'
    )

    uso_principal = (
        df_sorted
        .drop_duplicates('ID_PREDIO', keep='first')
        .reset_index(drop=True)
    )

    # --------------------------------------------------
    # 6. Merge final
    # --------------------------------------------------
   
    df_uso_p = pd.merge(
        df_predio,
        uso_principal[['ID_PREDIO', 'CAT_USO', 'IPU','DESTINOCONS']],
        on='ID_PREDIO',
        how='left'
    )

    condiciones = [
        # 2. ARECPRED == 0 & CONDICION %in% c('3','4')
        ((df_uso_p['ARECPRED'] == 0) & (df_uso_p['CONDICION'].isin([3,4])) |
         (df_uso_p['TIPOUSO']=='P') & (~df_uso_p['CONDICION'].isin([3,4]))),

        # 3. ARECPRED == 0
        (df_uso_p['ARECPRED'] == 0),

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
        'P',
        'S',
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
        default=df_uso_p['TIPOUSO']
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

    df_uso_p['CAMBIA_TIPOPRED'] = np.where(
        df_uso_p['TIPOPRED'] != df_uso_p['TIPOPRED_AJUSTADO'],
        1,
        0
    )

    return df_uso_p