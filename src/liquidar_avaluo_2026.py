import pandas as pd
import numpy as np
import re

# False: liquidacion solo por tablas. True: aplica especiales.
LIQUIDAR_CON_ESPECIALES = False


def calcular_avaluo_2026(df_predio_total):
    """Calcula el avalúo comercial de referencia de 2026 por predio."""
    
    print("\n💰 Calculando avalúo comercial 2026...")
    
    # ============================================================
    # VERIFICAR COLUMNAS NECESARIAS
    # ============================================================
    
    columnas_requeridas = [
        'VTER_2026_COM', 'VCONST_2026_COM', 'VANEXO_2026_COM',
        'MIXTO', 'INTEGRAL', 'INFORMALIDAD', 'TERRENO_MAS_CONST',
        'ARECPRED', 'ACONANEXT', 'AREAPRED'
    ]
    
    faltantes = [col for col in columnas_requeridas if col not in df_predio_total.columns]
    if faltantes:
        raise ValueError(f"Faltan columnas necesarias: {faltantes}")
    
    # Rellenar NaN con 0 para evitar problemas en cálculos
    for col in ['VTER_2026_COM', 'VCONST_2026_COM', 'VANEXO_2026_COM','ARECPRED', 'ACONANEXT', 'AREAPRED']:
        df_predio_total[col] = df_predio_total[col].fillna(0)
    
    
    # ============================================================
    # DEFINIR CONDICIONES (en orden de prioridad)
    # ============================================================
    
    condiciones = [



    # 1. SOLO TERRENO
    # Sin área construida ni anexos
    (
        (df_predio_total['ARECPRED'] == 0) &
        (df_predio_total['ACONANEXT'] == 0) &
        (df_predio_total['AREAPRED'] > 0)
    ),

    # 2. SOLO TERRENO + ANEXOS
    (
        (df_predio_total['ARECPRED'] == 0) &
        (df_predio_total['ACONANEXT'] > 0) &
        (df_predio_total['AREAPRED'] > 0)
    ),
    ##2.1  Especiales no integrales.
    # Apagada mientras LIQUIDAR_CON_ESPECIALES = False: sin ella estos predios
    # caen en la rama que les corresponda por su metodo (MIXTO / INTEGRAL /
    # INFORMALIDAD / TERRENO_MAS_CONST), como cualquier predio de tabla.
    (LIQUIDAR_CON_ESPECIALES &
     (df_predio_total['ESPECIAL_2026']==1) & (df_predio_total['INTEGRAL_ESP_2026']== 0)),
    ##3
    (df_predio_total['MIXTO'] == 1),

    # 4. INTEGRAL (sin terreno)
    (df_predio_total['INTEGRAL'] == 1),

    # 5. INFORMALIDAD (sin terreno)
    (df_predio_total['INFORMALIDAD'] == 1),

    # 6. RESTO – TERRENO + CONSTRUCCIÓN + ANEXOS
    (df_predio_total['TERRENO_MAS_CONST'] == 1)
    ]
    
    # ============================================================
    # DEFINIR VALORES CORRESPONDIENTES
    # ============================================================
    
    valores = [


    # 1. SOLO TERRENO
    df_predio_total['VTER_2026_COM'],

    # 2. SOLO TERRENO + ANEXOS
    df_predio_total['VTER_2026_COM'] +
    df_predio_total['VANEXO_2026_COM'],

    # 2.1. Especiales no intetrales)
    df_predio_total['VTER_2026_COM'] +
    df_predio_total['VCONST_2026_COM'] +
    df_predio_total['VANEXO_2026_COM'],

     # 3. MIXTO)
    df_predio_total['VTER_2026_COM'] +
    df_predio_total['VCONST_2026_COM'] +
    df_predio_total['VANEXO_2026_COM'],

    # 4. INTEGRAL (sin terreno)
    df_predio_total['VCONST_2026_COM'] +
    df_predio_total['VANEXO_2026_COM'],

    # 5. INFORMALIDAD (sin terreno)
    df_predio_total['VCONST_2026_COM'] +
    df_predio_total['VANEXO_2026_COM'],

    # 6. RESTO – método tradicional
    df_predio_total['VTER_2026_COM'] +
    df_predio_total['VCONST_2026_COM'] +
    df_predio_total['VANEXO_2026_COM']
]


    
    # ============================================================
    # APLICAR CÁLCULO
    # ============================================================
    
    df_predio_total['AVALUO_COM_2026'] = np.select(condiciones, valores, default=0)

    # Que componente entra al avaluo en cada caso, en el mismo orden de las
    # condiciones. Sirve para reportar terreno, construccion y anexos de modo
    # que SUMEN el avaluo, como en el export oficial: un integral no lleva
    # terreno, y si se reporta su VTER el total no cuadra.
    #                    solo_t  t+anex  esp   mixto  integ  inform resto
    incluye = {
        'TERRENO_INCLUIDO': [1, 1, 1, 1, 0, 0, 1],
        'CONST_INCLUIDA':   [0, 0, 1, 1, 1, 1, 1],
        'ANEXO_INCLUIDO':   [0, 1, 1, 1, 1, 1, 1],
    }
    for col, banderas in incluye.items():
        df_predio_total[col] = np.select(condiciones, banderas, default=0)

    return df_predio_total

   