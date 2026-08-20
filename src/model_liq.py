"""
Script de Liquidación - Modelos de Valoración
==============================================

Este script ejecuta los tres modelos de Machine Learning para 
predecir valores de construcciones.
"""

import pickle
import pandas as pd
import numpy as np
import joblib
import dill
import sys
import builtins

# Hacer numpy disponible globalmente para deserialización de modelos
builtins.np = np
sys.modules['__main__'].np = np


def ejecutar_modelos(df_const):
    """
    Ejecuta modelos de ML sobre construcciones y retorna predicciones.
    Si no se puede predecir, asigna 0 para conservar índices.
    
    Parameters:
    -----------
    df_const : pandas.DataFrame
        DataFrame con construcciones
        
    Returns:
    --------
    pandas.DataFrame
        DataFrame con predicciones
    """
    
    # Filtrar registros de modelo

    df_num_terr= pd.read_csv('./input/otros/modelo_uso28.txt', sep = '|', dtype = {'ZHF': 'object','ID_PREDIO':'object'})
    df_num_terr = df_num_terr[['ID_PREDIO','NUM_CONST_TERR']].drop_duplicates()
    df_mod = df_const[df_const['TABLA_ORIGEN'] == 'MODELO'].copy()
    df_mod = df_mod[df_mod['PUNTCONS']>0].copy() ### df_construccion que no tenga puntaje
    df_mod = pd.merge(df_mod, df_num_terr, on ="ID_PREDIO",how='left')
    df_mod = df_mod.rename(columns={'NUM_CONST_TERR_y':'NUM_CONST_TERR'})
    if df_mod.empty:
        print("⚠️ No hay registros con TABLA_ORIGEN='MODELO'")
        return pd.DataFrame()

    # Preparar campos derivados de ZHF
    df_mod['ZHF'] = df_mod['ZHF'].astype(str)
    df_mod['CLASE_SUELO'] = df_mod['ZHF'].str[0:1]#1
    df_mod['AREA_ACT'] = df_mod['ZHF'].str[1:2]#2
    df_mod['TRAT_URB'] = df_mod['ZHF'].str[2:4]#3 y 4
    df_mod['SERV_PUBL_DOM'] = df_mod['ZHF'].str[4:5]#5
    df_mod['CLASE_VIA'] = df_mod['ZHF'].str[5:6]#6
    df_mod['INFLUENCIA_VIA'] = df_mod['ZHF'].str[6:7]#7
    df_mod['TOPOGRAFIA'] = df_mod['ZHF'].str[7:8]#8
    df_mod['ACT_ECON'] = df_mod['ZHF'].str[8:10]#9 y 10
    df_mod['TIPO_SEGUN_ACT'] = df_mod['ZHF'].str[8:11] #9,10m11

    df_modelos = []

    # =========================================================================
    # MODELO 1 - DESTINOCONS '001'
    # =========================================================================
    print("\n" + "="*70)
    print("EJECUTANDO MODELO 1 (DESTINOCONS='001')")
    print("="*70)
    
    base_m1 = df_mod[df_mod["DESTINOCONS"] == '001'].copy()

    base_m1['VM2_MOD'] = 0
    
    if not base_m1.empty:
        try:
            with open("./Modelos/models/modelo_gbr_M1.pkl", "rb") as file:
                M1 = pickle.load(file)
            
            m1_vars = ['VALOR_M2_SUELO', 'ANOCONST', 'ESTRPRED', 'PUNTCONS',
                       'TPISCONS', 'LONGITUDE', 'LATITUDE', 'COMUNA', 'INFLUENCIA_VIA']

            missing_cols = [col for col in m1_vars if col not in base_m1.columns]
            if missing_cols:
                print(f"⚠️ MODELO 1: Columnas faltantes: {missing_cols}")
            else:
                # Guardar índices originales antes de dropna
                base_m1_clean = base_m1.dropna(subset=m1_vars)
                indices_validos = base_m1_clean.index
                
                x_m1 = base_m1_clean[m1_vars].copy()

                # Preprocesamiento
                x_m1['INFLUENCIA_VIA'] = pd.to_numeric(x_m1['INFLUENCIA_VIA'], errors='coerce').fillna(0).astype(int)
                x_m1['COMUNA'] = x_m1['COMUNA'].astype(str).str.zfill(2)
                x_m1['COMUNA'] = x_m1['COMUNA'].replace({
                    '09': '09_10_11_12', '10': '09_10_11_12', '11': '09_10_11_12', '12': '09_10_11_12',
                    '01': '01_03', '03': '01_03'
                })
                x_m1 = pd.get_dummies(x_m1, drop_first=False, dtype=int)

                # Alinear columnas con las esperadas por el modelo
                expected_features = getattr(M1, 'feature_names_in_', None)
                print(f'VARIABLES del MODELO 1{expected_features}')
                if expected_features is not None:
                    for c in expected_features:
                        if c not in x_m1.columns:
                            x_m1[c] = 0
                    # Eliminar columnas extra
                    extra_cols = [c for c in x_m1.columns if c not in expected_features]
                    if extra_cols:
                        x_m1 = x_m1.drop(columns=extra_cols)
                    x_m1 = x_m1[expected_features]
                
                print(f'TIPOS DE VARIABLES MODELO 1 {x_m1.dtypes}')

                # Predecir
                y_m1 = M1.predict(x_m1)
                base_m1.loc[indices_validos, 'VM2_MOD'] = y_m1
                print(f"✅ MODELO 1: Predicciones generadas para {len(y_m1)} registros")
                print(f"📊 Estadísticas - Min: {y_m1.min():.2f}, Max: {y_m1.max():.2f}, Media: {y_m1.mean():.2f}")
                    
        except Exception as e:
            print(f"⚠️ Error en MODELO 1: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("ℹ️ No hay registros para MODELO 1")
    
    df_modelos.append(base_m1)

    # =========================================================================
    # MODELO 2 - DESTINOCONS '028' - TIPO_SEGUN_ACT DIFERENTE 023
    # =========================================================================
    print("\n" + "=" * 70)
    print("EJECUTANDO MODELO 2 (DESTINOCONS = '028')")
    print("=" * 70)

    # ------------------------------------------------------------
    # 1️⃣ Filtrar base
    # ------------------------------------------------------------
    base_M2_1 = df_mod[df_mod["DESTINOCONS"] == '028'].copy()
    base_M2_1 = base_M2_1[base_M2_1["TIPO_SEGUN_ACT"] != '023'].copy()
    base_M2_1['TIPO_SEGUN_ACT_013'] = np.where(base_M2_1['TIPO_SEGUN_ACT']=='013',1,0).astype(int)
    base_M2_1['VM2_MOD'] = 0.0

    if base_M2_1.empty:
        print("ℹ️ MODELO 2: No hay registros para procesar")
    else:
        try:
            # ------------------------------------------------------------
            # 2️⃣ Cargar modelo con contexto correcto
            # ------------------------------------------------------------
            print("🔄 Cargando MODELO 2...")
            
            # Preparar el entorno para deserialización
            import __main__
            __main__.np = np
            __main__.pd = pd
            
            ruta_modelo = './Modelos/models/pipeline_M02_DIF_023.pkl'
            
            # Intentar primero con dill
            try:
                with open(ruta_modelo, 'rb') as f:
                    M2_1 = dill.load(f)
                print("✅ MODELO 2 DIF 023 cargado correctamente (dill)")
            except:
                # Si falla, intentar con pickle
                with open(ruta_modelo, 'rb') as f:
                    M2_1 = pickle.load(f)
                print("✅ MODELO 2 DIF 023 cargado correctamente (pickle)")

            # ------------------------------------------------------------
            # 3️⃣ Variables EXACTAS del entrenamiento
            # ------------------------------------------------------------
            if hasattr(M2_1, "feature_names_in_"):
                m2_vars_1 = list(M2_1.feature_names_in_)
                print(f"📋 Variables del modelo: {m2_vars_1}")
            else:
                m2_vars_1 = [
                    'VALOR_M2_SUELO',                 
                    'TIPO_SEGUN_ACT_013',             
                    'LATITUDE', 'LONGITUDE'
                ]
                print(f"📋 Variables por defecto: {m2_vars_1}")

            # ------------------------------------------------------------
            # 4️⃣ Validar columnas
            # ------------------------------------------------------------
            missing_cols = [c for c in m2_vars_1 if c not in base_M2_1.columns]
            if missing_cols:
                print(f"⚠️ MODELO 2: Columnas faltantes: {missing_cols}")
            else:
                # ------------------------------------------------------------
                # 5️⃣ Preparar X
                # ------------------------------------------------------------
                print(f"📊 Registros antes de limpiar: {len(base_M2_1)}")
                
                X_M2_1 = base_M2_1[m2_vars_1].copy()
                
                # Mostrar cuántos NaN hay
                nan_counts = X_M2_1.isna().sum()
                if nan_counts.any():
                    print(f"⚠️ Valores NaN por columna:\n{nan_counts[nan_counts > 0]}")
                
                X_M2_1 = X_M2_1.dropna()
                print(f"📊 Registros después de limpiar: {len(X_M2_1)}")

                if X_M2_1.empty:
                    print("⚠️ MODELO 2: No hay filas válidas luego de eliminar NA")
                else:
                    indices_validos = X_M2_1.index
                    print(f"✅ {len(indices_validos)} registros listos para predicción")

                    # ------------------------------------------------------------
                    # 6️⃣ Predicción
                    # ------------------------------------------------------------
                    print("🔮 Ejecutando predicción...")
                    y_M2_1 = M2_1.predict(X_M2_1)
                    print(f"✅ Predicción completada")

                    # ------------------------------------------------------------
                    # 7️⃣ Asignar resultados
                    # ------------------------------------------------------------
                    base_M2_1.loc[indices_validos, 'VM2_MOD'] = y_M2_1

                    print(f"✅ MODELO 2: Predicciones generadas para {len(y_M2_1)} registros")
                    print(
                        f"📊 Estadísticas → "
                        f"Min: {y_M2_1.min():.2f} | "
                        f"Max: {y_M2_1.max():.2f} | "
                        f"Media: {y_M2_1.mean():.2f}"
                    )
                    
                    # Verificar asignación
                    count_assigned = (base_M2_1['VM2_MOD'] > 0).sum()
                    print(f"✅ Valores asignados en base_M2_1: {count_assigned}")

        except Exception as e:
            print(f"❌ Error en MODELO 2: {e}")
            import traceback
            traceback.print_exc()

    # ✅ CORRECCIÓN: Agregar base_M2_1 UNA SOLA VEZ, fuera del bloque try-except
    df_modelos.append(base_M2_1)
    print(f"📦 base_M2_1 agregada a lista (registros con VM2_MOD>0: {(base_M2_1['VM2_MOD'] > 0).sum()})")



     # =========================================================================
    # MODELO 2 - DESTINOCONS '028' - TIPO_SEGUN_ACT IGUAL 023
    # =========================================================================
    base_M2_2 = df_mod[df_mod["DESTINOCONS"] == '028'].copy()
    base_M2_2 = base_M2_2[base_M2_2["TIPO_SEGUN_ACT"] == '023'].copy()
    base_M2_2['ACONCONS_17'] = np.where(base_M2_2["ACONCONS"]>=17,1,0).astype(int)
    base_M2_2['VM2_MOD'] = 0.0

    if base_M2_2.empty:
        print("ℹ️ MODELO 2: No hay registros para procesar")
    else:
        try:
            # ------------------------------------------------------------
            # 2️⃣ Cargar modelo con contexto correcto
            # ------------------------------------------------------------
            print("🔄 Cargando MODELO 2...")
            
            # Preparar el entorno para deserialización
            import __main__
            __main__.np = np
            __main__.pd = pd
            
            ruta_modelo = './Modelos/models/pipeline_M02_IGUAL_023.pkl'
            
            # Intentar primero con dill
            try:
                with open(ruta_modelo, 'rb') as f:
                    M2_2 = dill.load(f)
                print("✅ MODELO 2 IGUAL A 023 cargado correctamente (dill)")
            except:
                # Si falla, intentar con pickle
                with open(ruta_modelo, 'rb') as f:
                    M2_2 = pickle.load(f)
                print("✅ MODELO 2 IGUAL A 023  cargado correctamente (pickle)")

            # ------------------------------------------------------------
            # 3️⃣ Variables EXACTAS del entrenamiento
            # ------------------------------------------------------------
            if hasattr(M2_2, "feature_names_in_"):
                m2_vars_2 = list(M2_2.feature_names_in_)
                print(f"📋 Variables del modelo: {m2_vars_2}")
            else:
                m2_vars_2 = [
                    'NUM_CONST_TERR',            
                    'LATITUDE',                
                    'LONGITUDE',
                    'ACONCONS_17'
                ]
                print(f"📋 Variables por defecto: {m2_vars_2}")

            # ------------------------------------------------------------
            # 4️⃣ Validar columnas
            # ------------------------------------------------------------
            missing_cols = [c for c in m2_vars_2 if c not in base_M2_2.columns]
            if missing_cols:
                print(f"⚠️ MODELO 2: Columnas faltantes: {missing_cols}")
            else:
                # ------------------------------------------------------------
                # 5️⃣ Preparar X
                # ------------------------------------------------------------
                print(f"📊 Registros antes de limpiar: {len(base_M2_2)}")
                
                X_M2_2 = base_M2_2[m2_vars_2].copy()
                
                # Mostrar cuántos NaN hay
                nan_counts = X_M2_2.isna().sum()
                if nan_counts.any():
                    print(f"⚠️ Valores NaN por columna:\n{nan_counts[nan_counts > 0]}")
                
                X_M2_2 = X_M2_2.dropna()
                print(f"📊 Registros después de limpiar: {len(X_M2_2)}")

                if X_M2_2.empty:
                    print("⚠️ MODELO 2: No hay filas válidas luego de eliminar NA")
                else:
                    indices_validos = X_M2_2.index
                    print(f"✅ {len(indices_validos)} registros listos para predicción")

                    # ------------------------------------------------------------
                    # 6️⃣ Predicción
                    # ------------------------------------------------------------
                    print("🔮 Ejecutando predicción...")
                    y_M2_2 = M2_2.predict(X_M2_2)
                    print(f"✅ Predicción completada")

                    # ------------------------------------------------------------
                    # 7️⃣ Asignar resultados
                    # ------------------------------------------------------------
                    base_M2_2.loc[indices_validos, 'VM2_MOD'] = y_M2_2

                    print(f"✅ MODELO 2: Predicciones generadas para {len(y_M2_2)} registros")
                    print(
                        f"📊 Estadísticas → "
                        f"Min: {y_M2_2.min():.2f} | "
                        f"Max: {y_M2_2.max():.2f} | "
                        f"Media: {y_M2_2.mean():.2f}"
                    )
                    
                    # Verificar asignación
                    count_assigned = (base_M2_2['VM2_MOD'] > 0).sum()
                    print(f"✅ Valores asignados en base_M2_2: {count_assigned}")

        except Exception as e:
            print(f"❌ Error en MODELO 2: {e}")
            import traceback
            traceback.print_exc()

    # ✅ CORRECCIÓN: Agregar base_M2_2 UNA SOLA VEZ, fuera del bloque try-except
    df_modelos.append(base_M2_2)
    print(f"📦 base_M2_2 agregada a lista (registros con VM2_MOD>0: {(base_M2_2['VM2_MOD'] > 0).sum()})")


    # =========================================================================
    # MODELO 3 - DESTINOCONS '034'
    # =========================================================================
    print("\n" + "="*70)
    print("EJECUTANDO MODELO 3 (DESTINOCONS='034')")
    print("="*70)
    
    base_m3 = df_mod[df_mod["DESTINOCONS"] == '034'].copy()
    base_m3['VM2_MOD'] = 0

    if not base_m3.empty:
        variables_categoricas = [
            'COMUNA', 'TRAT_URB', 'ACT_ECON',
            'INFLUENCIA_VIA', 'TIPO_SEGUN_ACT', 'AREA_ACT', 'SERV_PUBL_DOM'
        ]
        variables_numericas = [
            'LATITUDE', 'LONGITUDE', 'VALOR_M2_SUELO', 'ACONCONS'
        ]

        # 1️⃣ Crear dummies

        base_m3['SERV_PUBL_DOM_6'] = np.where(base_m3['SERV_PUBL_DOM']=='6',1,0).astype('int64')
        base_m3['COMUNA_22'] = np.where(base_m3['COMUNA']=='22',1,0).astype('int64')
        base_m3['INFLUENCIA_VIA_4'] = np.where(base_m3['INFLUENCIA_VIA']=='4',1,0).astype('int64')
        base_m3['TRAT_URB_04'] = np.where(base_m3['TRAT_URB']=='04',1,0).astype('int64')
        base_m3['TRAT_URB_11'] = np.where(base_m3['TRAT_URB']=='11',1,0).astype('int64')
        base_m3['COMUNA_10'] = np.where(base_m3['COMUNA']=='10',1,0).astype('int64')
        base_m3['ACT_ECON_02'] = np.where(base_m3['ACT_ECON']=='02',1,0).astype('int64')

        variables_dummies = ['SERV_PUBL_DOM_6', 'COMUNA_22', 'INFLUENCIA_VIA_4', 
                    'TRAT_URB_04','TRAT_URB_11', 'COMUNA_10', 'ACT_ECON_02']
        
        dummies = base_m3[variables_dummies]
        print(f'VARIABLES DUMMIES {dummies.dtypes}')
        # 2️⃣ Concatenar SIN reemplazar base_m3
        base_m3_features = pd.concat(
            [
                base_m3[variables_numericas],
                dummies
            ],
            axis=1
        )

        try:
            with open("./Modelos/models/M3_RF_20251221.pkl", "rb") as file:
                M3 = pickle.load(file)
            
            m3_vars = ['VALOR_M2_SUELO', 'LATITUDE', 'ACONCONS', 'LONGITUDE',
                    'SERV_PUBL_DOM_6', 'COMUNA_22', 'INFLUENCIA_VIA_4', 
                    'TRAT_URB_04','TRAT_URB_11', 'COMUNA_10', 'ACT_ECON_02']
            
            missing_cols = [col for col in m3_vars if col not in base_m3_features.columns]
            if missing_cols:
                print(f"⚠️ MODELO 3: Columnas faltantes: {missing_cols}")
            else:
                # Limpiar NAs
                base_m3_features_clean = base_m3_features.dropna(subset=m3_vars)
                indices_validos = base_m3_features_clean.index
                
                x_m3 = base_m3_features_clean[m3_vars].copy()
                
                # Predecir
                y_m3 = M3.predict(x_m3)
                
                # ✅ Actualizar en el DataFrame ORIGINAL usando índices
                base_m3.loc[indices_validos, 'VM2_MOD'] = y_m3
                
                print(f"✅ MODELO 3: Predicciones generadas para {len(y_m3)} registros")
                print(f"📊 Estadísticas - Min: {y_m3.min():.2f}, Max: {y_m3.max():.2f}, Media: {y_m3.mean():.2f}")
                    
        except Exception as e:
            print(f"⚠️ Error en MODELO 3: {e}")
            import traceback
            traceback.print_exc()
    else:
        print("ℹ️ No hay registros para MODELO 3")

    df_modelos.append(base_m3)
        
    # =========================================================================
    # CONCATENAR Y RETORNAR
    # =========================================================================
    print("\n" + "="*70)
    print("🔗 CONCATENANDO RESULTADOS...")
    print("="*70)
    
    for i, df in enumerate(df_modelos):
        dest = ['001', '028', '034'][i] if i < 3 else 'N/A'
        print(f"DataFrame {i} (DEST {dest}): {len(df)} registros, {(df['VM2_MOD'] > 0).sum()} con predicción")
    
    df_liq_modelos = pd.concat(df_modelos, ignore_index=True)
    
    print("\n" + "="*70)
    print("📊 RESUMEN FINAL DE MODELOS")
    print("="*70)
    print(f"Total de registros procesados: {len(df_liq_modelos)}")
    print(f"Registros con predicción > 0: {(df_liq_modelos['VM2_MOD'] > 0).sum()}")
    print(f"Registros sin predicción: {(df_liq_modelos['VM2_MOD'] == 0).sum()}")
    
    # Estadísticas por modelo
    print("\n📈 Distribución por DESTINOCONS:")
    for dest in ['001', '028', '034']:
        count = (df_liq_modelos['DESTINOCONS'] == dest).sum()
        count_pred = ((df_liq_modelos['DESTINOCONS'] == dest) & (df_liq_modelos['VM2_MOD'] > 0)).sum()
        if count > 0:
            print(f"  - {dest}: {count} registros | {count_pred} con predicción ({count_pred/count*100:.1f}%)")
    
    print("="*70)
    
    return df_liq_modelos