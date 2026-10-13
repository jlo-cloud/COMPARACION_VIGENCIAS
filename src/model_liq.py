"""
Script de Liquidación - Modelos de Valoración
==============================================

Este script ejecuta los tres modelos de Machine Learning para 
predecir valores de construcciones.
"""

import os
import glob
import pickle
try:
    import cloudpickle
except ImportError:                      # sin el, el M4 de 2024 no carga
    cloudpickle = None
import pandas as pd
import numpy as np
import joblib
import dill
import sys
import builtins

# Hacer numpy disponible globalmente para deserialización de modelos
builtins.np = np
sys.modules['__main__'].np = np


# =====================================================================
# LAS DOS ACTUALIZACIONES: 2024 Y 2025
# =====================================================================
# Cada familia de modelos se selecciona por comuna y usa su propio valor de
# suelo. Las comunas 03 y 22 se resuelven con la familia 2025.
COMUNAS_MODELO_2025 = ['01', '03', '09', '10', '11', '12', '22']
COMUNAS_MODELO_2024 = ['02', '04', '08', '17', '19']

# Destinos modelados por cada familia.
DESTINOS_MODELO_2025 = ['001', '028', '034']
DESTINOS_MODELO_2024 = ['001', '028', '034']

# Lo rural no se liquida todavia, ni por tabla ni por modelo. Sin este limite
# entraban 34.683 construcciones de las comunas 51 y 52, que ningun modelo vio
# al entrenarse y cuya ZHF tiene otra estructura.
COMUNA_URBANA_MAXIMA = 22

# Incremento aplicado sobre la salida del modelo por familia.
INCREMENTO_MODELO = {'2024': 1.00, '2025': 1.00}

# Modo de compatibilidad con el ejercicio 2024.
MODO_DUMMY_2024 = 'real'

# Compatibilidad con el nombre anterior.
REPLICAR_DUMMY_COMUNA_2024 = MODO_DUMMY_2024 == 'cero'

# Los ESPECIALES no van por modelo. Basta la marca ESPECIAL que trae el export
# de construcciones: se comprobo contra las tres listas del ejercicio 2024
# -centros comerciales, predios nuevos e incremento 3,72- y de las 95.461
# construcciones de la familia 2024 que quedaban en el universo de modelo, solo
# 2 estaban en esas listas sin venir ya marcadas. Las listas se retiraron por
# redundantes; el criterio vive en mask_modelo().


# El valor de suelo se obtiene de ZHG_2024/ZHG_2025 porque el export de predios
# llega vacío para las unidades PH.
RUTA_ZHG = './input/otros/ZHG_2024_2025.parquet'

# El avaluo de la vigencia 2025, con el que se compara la familia 2024. Es la
# vigencia que ESE ejercicio produjo: contra la 2026 no cuadra nada, porque
# lleva un anio mas encima. Pipe, decimal con COMA, y se cruza por
# NUMERO_PREDIAL_NACIONAL -el ID_CONSTRUCCION cambio entre vigencias-.
RUTA_EXPORT_2025 = './input/export_liq/export_predio_2025.txt'
_vigencia_2025 = None

# =====================================================================
# LA HOJA DE LOS QUE VAN POR MODELO  (informe, no liquidacion)
# =====================================================================
# Cada familia se corre leyendo el export de la vigencia que ESE ejercicio
# produjo, no el que liquida las tablas -ese es el de la vigencia 2027 y trae
# otra ZHF-. Comprobado sobre los predios que estan en los tres exports:
#
#   comunas de 2024   ZHF 2025 == ZHF 2026: 98,2%   ZHF 2025 == ZHF 2027: 56,3%
#   comunas de 2025   ZHF 2026 == ZHF 2027: 75,6%   ZHF 2026 == ZHF 2025: 32,3%
#
# O sea: la familia 2024 tiene que leer el export de 2025 y la 2025 el de 2026.
# Con el export de las tablas, casi la mitad de las construcciones de 2024
# entraria al modelo con una ZHF que ese modelo nunca vio.
RUTA_EXPORT_2026 = './input/export_liq/export_predio_20260717.parquet'
_vigencia_2026 = None

# El VALOR_M2_SUELO sale del export de cada vigencia CUANDO ese export lo trae.
#
#   2025  lo trae completo, y en las unidades PH de sus comunas coincide con
#         ZHG_2024 en 236.764 de 238.666 -99,2%-; ademas cubre 1.214 que el ZHG
#         no tiene. Manda el export, con el ZHG de respaldo.
#   2026  NO sirve: de las 58.473 unidades PH de las comunas de 2025 solo
#         12.270 lo traen poblado, y donde hay ZHG_2025 no coincide ni una vez.
#         Alli manda el ZHG, que esta verificado 537/537 contra la base de
#         entrenamiento.
FUENTE_SUELO_INFORME = {'2024': 'export', '2025': 'zhg'}

# Las demas variables de los modelos que salen del export de predio. Se traen
# del export de la vigencia de cada familia, igual que la ZHF: lo que va de
# 2025 sale del export de 2025 y lo que va de 2026, del de 2026.
#
# El de 2025 NO trae coordenadas -mire su encabezado: no estan LATITUDE ni
# LONGITUDE-, asi que la familia 2024 las toma del export de JULIO (el de 2026),
# que es el mas cercano que las tiene. No cuesta nada: en las unidades PH de las
# comunas de 2024, las coordenadas de julio y las de agosto -el del pipeline-
# son identicas en el 100,00% de 240.158 predios, distancia maxima 0.
COLUMNAS_EXPORT_INFORME = {
    '2024': ['ESTRPRED', 'ARECPRED', 'AREAPRED'],
    '2025': ['ESTRPRED', 'ARECPRED', 'AREAPRED', 'LATITUDE', 'LONGITUDE'],
}

# Lo que el export de la familia no trae y se busca en el de 2026. Ojo con el
# respaldo del pipeline: el export de julio deja 4.836 unidades PH de esas
# comunas SIN coordenada y el de agosto solo 50, asi que sin el fillna se
# perderian ~4.800 construcciones en el dropna del modelo.
COLUMNAS_DESDE_2026_INFORME = {'2024': ['LATITUDE', 'LONGITUDE']}

# ARECPRED y AREAPRED en cero no son un dato: son el area que en PH cuelga de
# la matriz. Si el export las trae asi, se deja la del pipeline. ESTRPRED no
# entra aqui: el estrato 0 existe y es un valor legitimo.
COLUMNAS_CERO_NO_SIRVE = {'ARECPRED', 'AREAPRED'}

# Las comunas de cada ACTUALIZACION, completas.
#
# Ojo que la 03 y la 22 estan en las DOS. La liquidacion las resuelve a favor de
# 2025 -un predio no se puede liquidar dos veces-, pero el informe las corre por
# las dos familias, cada una contra su vigencia, y por eso alli esas dos comunas
# salen DUPLICADAS: una fila por familia, y GRUPO_MODELO dice cual es cual.
COMUNAS_ACTUALIZACION_2024 = ['02', '03', '04', '08', '17', '19', '22']
COMUNAS_ACTUALIZACION_2025 = ['01', '03', '09', '10', '11', '12', '22']

# Las SIETE banderas de comuna del ejercicio 2024, no solo la de M1.
# input_model_consolidado.py las arma todas igual -np.where(COMUNA.isin([3,4,
# 8,17,19]), 1, 0)- comparando contra ENTEROS mientras la COMUNA llega como
# texto ('03','17'), asi que el isin da False siempre y las siete quedaron en
# cero. M1 lee la primera, M3 lee cinco y M4 lee la ultima: el defecto toca a
# los tres modelos, y por eso el comparativo se hace por modelo con las
# banderas que cada uno declara.
BANDERAS_COMUNA_2024 = ['COMUNA_03_04_08_17_19', 'COMUNA_03', 'COMUNA_04_08',
                        'COMUNA_17', 'COMUNA_19', 'COMUNA_22',
                        'COMUNA_3_4_17_19']

# Lo pone hoja_modelos(): fuerza a que todo el frame vaya por esa familia, con
# la ZHF y el suelo del export de SU vigencia. En None -la corrida normal de
# liquidacion- no cambia absolutamente nada.
MODO_INFORME = None

# El frame completo de construcciones que deja el pipeline. El informe se arma
# de aqui y no de LIQUIDACION_TABLAS.parquet porque en aquel el reparto por
# comuna ya esta hecho, y hecho a favor de 2025 en las comunas 03 y 22.
RUTA_CONSTRUCCIONES = './output/todas_las_construcciones.parquet'

RUTA_MODELOS_2025 = './Modelos/models'
RUTA_MODELOS_2024 = './Modelos/models_2024'
# Los de PRODUCCION, los que nombra Modelos/models_2024/model_liq_consolidado.py.
# El M4 es un CombinedModel con el RobustScaler adentro y se carga con
# cloudpickle; el M4_OFICINAS_20241213.pkl que hay al lado es el estimador
# pelado, sin escalador, y da R2 = -0.93: no usarlo.
ARCHIVOS_MODELOS_2024 = {
    'M1': '21_12_2024_model_GBR_M1.pkl',   # Apartamentos_4_y_mas_pisos_en_PH
    'M3': '21_12_2024_model_XGB_M3.pkl',   # Comercio_en_PH
    'M4': 'M4_OFICINAS_20241227.pkl',      # Oficinas_Consultorios_en_PH
}


def vigencia_2025():
    """
    Integral catastral por m2 de la vigencia 2025, por predial nacional.

    Solo de los predios que siguen en VIGEPRED 01/01/25: los que ya pasaron a
    01/01/26 cambiaron despues del ejercicio y su valor de hoy ya no es el que
    aquel produjo, asi que no sirven para comparar.
    """
    global _vigencia_2025
    if _vigencia_2025 is None:
        try:
            v = pd.read_csv(RUTA_EXPORT_2025, sep='|', decimal=',',
                            encoding='ISO-8859-1', low_memory=False,
                            usecols=['NUMERO_PREDIAL_NACIONAL', 'AVALPRED',
                                     'ARECPRED', 'VIGEPRED'],
                            dtype={'NUMERO_PREDIAL_NACIONAL': 'string'})
        except Exception as e:
            print(f"No se pudo leer {RUTA_EXPORT_2025}: {e}")
            _vigencia_2025 = pd.Series(dtype='float64')
            return _vigencia_2025
        v = v[v['VIGEPRED'].astype(str).str.strip() == '01/01/25']
        area = pd.to_numeric(v['ARECPRED'], errors='coerce').replace(0, np.nan)
        v['VM2'] = pd.to_numeric(v['AVALPRED'], errors='coerce') / area
        v['NPN'] = v['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
        _vigencia_2025 = (v.dropna(subset=['VM2'])
                           .drop_duplicates('NPN')
                           .set_index('NPN')['VM2'])
        print(f"Vigencia 2025 para comparar la familia 2024: "
              f"{len(_vigencia_2025):,} predios")
    return _vigencia_2025


def vigencia_2026():
    """
    Integral catastral por m2 de la vigencia 2026, por predial nacional.

    Es la vigencia que produjo el ejercicio de 2025, la que sirve para
    comprobar esa familia. Sale del mismo export del que el informe toma la ZHF
    -export_predio_20260717-, asi que la referencia y las variables vienen de
    la misma foto.
    """
    global _vigencia_2026
    if _vigencia_2026 is None:
        try:
            v = pd.read_parquet(RUTA_EXPORT_2026,
                                columns=['NUMERO_PREDIAL_NACIONAL', 'AVALPRED',
                                         'ARECPRED'])
        except Exception as e:
            print(f"No se pudo leer {RUTA_EXPORT_2026}: {e}")
            _vigencia_2026 = pd.Series(dtype='float64')
            return _vigencia_2026
        area = pd.to_numeric(v['ARECPRED'], errors='coerce').replace(0, np.nan)
        v['VM2'] = pd.to_numeric(v['AVALPRED'], errors='coerce') / area
        v['NPN'] = v['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
        _vigencia_2026 = (v.dropna(subset=['VM2'])
                           .drop_duplicates('NPN')
                           .set_index('NPN')['VM2'])
        print(f"Vigencia 2026 para comparar la familia 2025: "
              f"{len(_vigencia_2026):,} predios")
    return _vigencia_2026


_export_informe = {}


def export_de_grupo(grupo):
    """
    Todo lo que los modelos leen del export de predio, del export de la
    vigencia que produjo esa familia, por ID_PREDIO.

    2024 -> export_predio_2025.txt   ZHF, VALOR_M2_SUELO, ESTRPRED, ARECPRED,
                                     AREAPRED. NO trae coordenadas.
    2025 -> export_predio_20260717   lo mismo mas LATITUDE y LONGITUDE. Su
                                     VALOR_M2_SUELO no sirve (ver arriba).
    """
    if grupo in _export_informe:
        return _export_informe[grupo]
    pedidas = ['ID_PREDIO', 'ZHF', 'VALOR_M2_SUELO'] + COLUMNAS_EXPORT_INFORME[grupo]
    try:
        if grupo == '2024':
            e = pd.read_csv(RUTA_EXPORT_2025, sep='|', decimal=',',
                            encoding='ISO-8859-1', low_memory=False,
                            usecols=pedidas,
                            dtype={'ID_PREDIO': 'string', 'ZHF': 'string'})
            fuente = os.path.basename(RUTA_EXPORT_2025)
        else:
            e = pd.read_parquet(RUTA_EXPORT_2026, columns=pedidas)
            fuente = os.path.basename(RUTA_EXPORT_2026)
    except Exception as e:
        print(f"No se pudo leer el export de la familia {grupo}: {e}")
        _export_informe[grupo] = None
        return None
    e['ID_PREDIO'] = e['ID_PREDIO'].astype(str).str.strip()
    e['ZHF'] = e['ZHF'].astype(str).str.strip()
    for c in ['VALOR_M2_SUELO'] + COLUMNAS_EXPORT_INFORME[grupo]:
        e[c] = pd.to_numeric(e[c], errors='coerce')
    e = e.drop_duplicates('ID_PREDIO').set_index('ID_PREDIO')
    print(f"Export de la familia {grupo}: {fuente}, {len(e):,} predios")
    _export_informe[grupo] = e
    return e


def modelos_2024_disponibles():
    """True solo si estan los tres .pkl de la familia 2024."""
    return all(os.path.exists(os.path.join(RUTA_MODELOS_2024, f))
               for f in ARCHIVOS_MODELOS_2024.values())


def comunas_con_modelo():
    """
    Comunas que HOY se pueden liquidar por modelo.

    Vive aqui, junto a los modelos, para que no haya dos listas de comunas que
    se puedan desincronizar.
    """
    comunas = list(COMUNAS_MODELO_2025)
    if modelos_2024_disponibles():
        comunas += COMUNAS_MODELO_2024
    return sorted(comunas)


def mask_modelo(df_const):
    """
    Que construcciones van por modelo. La usa Liquidacion_tablas para poner
    TABLA_ORIGEN = 'MODELO'.

    La condicion se arma aqui y no en Liquidacion_tablas porque cada
    actualizacion tiene su propia lista de comunas y de destinos, y esas listas
    son la misma decision que la de los .pkl: tienen que moverse con ellos.
    """
    comuna = df_const['COMUNA'].astype(str).str.zfill(2)
    destino = df_const['DESTINOCONS'].astype(str)
    ph = pd.to_numeric(df_const['CONDICION'], errors='coerce') == 9

    # Que va por modelo lo decide el USO, no la comuna. Que reciba valor es
    # otra cosa: solo predicen las comunas con modelo entrenado, y las demas
    # quedan en cero.
    urbana = pd.to_numeric(comuna, errors='coerce') <= COMUNA_URBANA_MAXIMA
    m = destino.isin(DESTINOS_MODELO_2025) & ph & urbana

    # Los ESPECIALES quedan fuera, como en el ejercicio original: la ultima
    # linea del armado de la base de 2024 -input_model_consolidado.py- es
    # df_const[df_const['ESPECIAL_2025'] == 0]. Su valor no sale de un modelo
    # de mercado sino de una valoracion aparte, y el modelo no ve nada de lo
    # que los hace especiales.
    #
    # Sin esto entraban 8.197 construcciones marcadas (5.634 de 2024 y 2.563 de
    # 2025) y el modelo les bajaba el valor un 13,9% en conjunto. Se nota
    # ademas en que el 98% de ellas NO reproduce su avaluo vigente, contra el
    # 1,9% de las no especiales: es la marca, no el modelo.
    #
    # Ojo: esto NO es ESPECIAL_2026, que hoy esta en cero en todas porque el
    # archivo de especiales de este anio todavia no se entrega. Es la marca que
    # trae el export de construcciones.
    if 'ESPECIAL' in df_const.columns:
        especial = pd.to_numeric(df_const['ESPECIAL'], errors='coerce').fillna(0)
        fuera = int((m & (especial > 0)).sum())
        if fuera:
            print(f"{fuera:,} construcciones marcadas ESPECIAL se dejan "
                  f"FUERA del modelo (se liquidan por tabla)")
        m = m & (especial <= 0)
    return m


def _cargar(ruta):
    """
    Carga un .pkl probando dill, pickle y cloudpickle.

    cloudpickle hace falta para M4_OFICINAS_20241227.pkl: no es un estimador de
    sklearn sino un CombinedModel, una clase propia que viaja DENTRO del
    archivo, y solo cloudpickle la sabe reconstruir. Con los otros dos falla
    con ModuleNotFoundError.
    """
    ultimo = None
    for cargador in (dill, pickle, cloudpickle):
        if cargador is None:
            continue
        try:
            with open(ruta, 'rb') as f:
                return cargador.load(f)
        except Exception as e:
            ultimo = e
    raise ultimo


def _variables_declaradas(modelo):
    """
    Las variables que el modelo dice esperar, en su orden.

    M1 y M3 las traen en feature_names_in_. El M4 de produccion es un
    CombinedModel y no expone ninguna: las tiene su RobustScaler interno, que
    es quien recibe las columnas primero.
    """
    nombres = getattr(modelo, 'feature_names_in_', None)
    if nombres is None:
        nombres = getattr(getattr(modelo, 'scaler', None),
                          'feature_names_in_', None)
    return None if nombres is None else [str(v) for v in nombres]


def _bandera_por_predio(modelo, x, df_mod_24):
    """
    Predice M1 dandole a cada predio la bandera con que fue liquidado en 2024.

    Cual le tocó no esta escrito en ningun archivo: se deduce. Se calculan las
    dos predicciones -bandera 0 y bandera real- y se mira cual reproduce el
    avaluo de la vigencia 2025 del predio. Solo una puede: se llevan un 9% de
    diferencia, y de 59.397 construcciones apenas 25 coinciden con las dos.

    Los que no tienen referencia -o no coinciden con ninguna- heredan la
    mayoria de su manzana: el ejercicio 2024 se corrio por lotes geograficos y
    196 de las 245 manzanas de la comuna 19 son puras. Si la manzana tampoco
    dice nada, cae en 0, que es la mayoria global.

    Devuelve la prediccion y, al lado, de donde salio la bandera de cada fila.
    """
    col = 'COMUNA_03_04_08_17_19'
    x0 = x.copy(); x0[col] = 0
    y0 = np.asarray(modelo.predict(x0)).ravel()
    y1 = np.asarray(modelo.predict(x)).ravel()          # x ya trae la real

    idx = x.index
    npn = df_mod_24.loc[idx, 'NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
    ref = npn.map(vigencia_2025())

    tol = 1_000
    ok0 = (y0 * 0.7 - ref).abs() <= tol
    ok1 = (y1 * 0.7 - ref).abs() <= tol
    # Si coincide con las dos no aporta informacion: se deja sin decidir.
    bandera = pd.Series(np.nan, index=idx)
    bandera[ok0 & ~ok1] = 0
    bandera[ok1 & ~ok0] = 1
    origen = pd.Series('', index=idx)
    origen[bandera.notna()] = 'avaluo 2025'

    # Los indecisos heredan la mayoria de su manzana.
    manzana = npn.str[:17]
    faltan = bandera.isna()
    if faltan.any():
        moda = bandera.groupby(manzana).mean()          # proporcion de unos
        heredada = manzana[faltan].map(moda)
        bandera[faltan] = (heredada >= 0.5).astype(float)
        origen[faltan & heredada.notna().reindex(idx, fill_value=False)] = 'manzana'

    # (heredada >= 0.5) ya convirtio los NaN en 0, asi que 'bandera' no queda
    # nula: los que caen aqui son los que no tenian ni avaluo ni manzana con
    # informacion. Se marcan por la etiqueta vacia, no por el valor.
    bandera = bandera.fillna(0)
    origen[origen == ''] = 'defecto (0)'

    y = np.where(bandera.to_numpy() == 1, y1, y0)
    print("   bandera por predio -> " + ", ".join(
        f"{k}: {v:,}" for k, v in origen.value_counts().items()))
    print(f"   con bandera 1: {int((bandera == 1).sum()):,} de {len(bandera):,}")
    return y, origen


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

    df_mod = df_const[df_const['TABLA_ORIGEN'] == 'MODELO'].copy()
    df_mod = df_mod[df_mod['PUNTCONS']>0].copy() ### df_construccion que no tenga puntaje
    if df_mod.empty:
        print("⚠️ No hay registros con TABLA_ORIGEN='MODELO'")
        return pd.DataFrame()

    # NUM_CONST_TERR ya viene de cruces_const_predio, contada por ID_TERR sobre
    # TODAS las construcciones. modelo_uso28.txt solo trae 3.162 predios y
    # entra a COMPLETAR los que falten. Antes se hacia al reves -merge y
    # rename de NUM_CONST_TERR_y-, que dejaba la columna del archivo, nula en
    # el 99% de las filas, y el M2 de los 023 se quedaba sin una sola fila
    # despues del dropna.
    df_mod['NUM_CONST_TERR'] = pd.to_numeric(df_mod.get('NUM_CONST_TERR'),
                                             errors='coerce')
    try:
        df_num_terr = pd.read_csv('./input/otros/modelo_uso28.txt', sep='|',
                                  dtype={'ZHF': 'object', 'ID_PREDIO': 'object'})
        df_num_terr = (df_num_terr[['ID_PREDIO', 'NUM_CONST_TERR']]
                       .drop_duplicates('ID_PREDIO'))
        completa = df_mod['ID_PREDIO'].astype(str).map(
            df_num_terr.set_index('ID_PREDIO')['NUM_CONST_TERR'])
        df_mod['NUM_CONST_TERR'] = df_mod['NUM_CONST_TERR'].fillna(completa)
    except Exception as e:
        print(f"⚠️ No se pudo leer modelo_uso28.txt: {e}")

    # ---------------------------------------------------------------------
    # GRUPO DE ACTUALIZACION Y VALOR DE SUELO
    # ---------------------------------------------------------------------
    df_mod['COMUNA'] = df_mod['COMUNA'].astype(str).str.zfill(2)
    if MODO_INFORME:
        # El informe corre UNA familia por vez, sobre las comunas de su propia
        # actualizacion. Por eso el grupo no se deduce de la comuna: viene
        # impuesto, y asi la 03 y la 22 pueden pasar por las dos familias.
        df_mod['GRUPO_MODELO'] = MODO_INFORME
    else:
        # Sin familia se queda la comuna que ningun modelo vio al entrenarse:
        # no se predice. Va por modelo -asi la clasifica mask_modelo, que mira
        # el uso- pero sin valor, que es distinto de liquidarla por tabla.
        df_mod['GRUPO_MODELO'] = np.where(
            df_mod['COMUNA'].isin(COMUNAS_MODELO_2025), '2025',
            np.where(df_mod['COMUNA'].isin(COMUNAS_MODELO_2024), '2024', ''))

    # ---------------------------------------------------------------------
    # LO DEMAS QUE SALE DEL EXPORT DE PREDIO
    # ---------------------------------------------------------------------
    # En el informe, todo lo que el modelo lee del predio sale del export de SU
    # vigencia, no del que arrastra el pipeline: lo que va de 2025 del export de
    # 2025 y lo que va de 2026 del de 2026. La ZHF y el suelo se resuelven mas
    # abajo, que tienen su propia regla; aqui van ESTRPRED, ARECPRED, AREAPRED
    # y -solo en 2025, que es el unico export que las trae- las coordenadas.
    #
    # Donde el export no tenga el dato se deja el del pipeline: es preferible
    # un valor de otra vigencia a un NaN, que tumba la fila entera en el dropna
    # del modelo.
    if MODO_INFORME:
        ids_exp = df_mod['ID_PREDIO'].astype(str).str.strip()

        def _del_export(exp, columnas, etiqueta):
            for col in columnas:
                if col not in df_mod.columns or exp is None or col not in exp:
                    continue
                nuevo = pd.to_numeric(ids_exp.map(exp[col]), errors='coerce')
                if col in COLUMNAS_CERO_NO_SIRVE:
                    nuevo = nuevo.where(nuevo > 0)
                viejo = pd.to_numeric(df_mod[col], errors='coerce')
                cambian = int((nuevo.notna() & viejo.notna()
                               & (nuevo.round(2) != viejo.round(2))).sum())
                df_mod[col] = nuevo.fillna(viejo)
                print(f"📄 {col} desde {etiqueta}: "
                      f"{int(nuevo.notna().sum()):,} de {len(df_mod):,} "
                      f"({cambian:,} cambian de valor, "
                      f"{int(nuevo.isna().sum()):,} se quedan con la del pipeline)")

        _del_export(export_de_grupo(MODO_INFORME),
                    COLUMNAS_EXPORT_INFORME[MODO_INFORME],
                    f"el export de {MODO_INFORME}")
        # Lo que ese export no trae y si esta en el de 2026 (hoy, las
        # coordenadas de la familia 2024).
        prestadas = COLUMNAS_DESDE_2026_INFORME.get(MODO_INFORME, [])
        if prestadas:
            _del_export(export_de_grupo('2025'), prestadas,
                        "el export de 2026 (el de julio, que si las trae)")

    try:
        zhg = pd.read_parquet(RUTA_ZHG)
        zhg['ID_PREDIO'] = zhg['ID_PREDIO'].astype(str)
        zhg = zhg.drop_duplicates('ID_PREDIO').set_index('ID_PREDIO')
        ids = df_mod['ID_PREDIO'].astype(str).str.strip()
        suelo = np.where(df_mod['GRUPO_MODELO'] == '2025',
                         ids.map(zhg['ZHG_2025']),
                         ids.map(zhg['ZHG_2024']))
        suelo = pd.to_numeric(pd.Series(suelo, index=df_mod.index),
                              errors='coerce')
        # En el informe, la familia 2024 toma el suelo de SU export -el de
        # 2025, que lo trae completo, coincide con ZHG_2024 en el 99,2% de sus
        # unidades PH y ademas cubre 1.214 que el ZHG no tiene-; el ZHG queda
        # de respaldo. La familia 2025 se queda con el ZHG: el suelo del export
        # de 2026 solo esta poblado en el 21% de sus PH y donde hay ZHG_2025 no
        # coincide ni una vez.
        if MODO_INFORME and FUENTE_SUELO_INFORME.get(MODO_INFORME) == 'export':
            exp = export_de_grupo(MODO_INFORME)
            if exp is not None:
                del_export = pd.to_numeric(ids.map(exp['VALOR_M2_SUELO']),
                                           errors='coerce')
                print(f"🏷️ Suelo del export de la vigencia: "
                      f"{int(del_export.gt(0).sum()):,} de {len(df_mod):,} "
                      f"(el ZHG cubre {int(suelo.gt(0).sum()):,})")
                suelo = del_export.where(del_export > 0, suelo)
        # El VALOR_M2_SUELO del export queda como ultimo recurso: hoy es cero
        # en todas las comunas actualizadas, pero si manana llega poblado no
        # tiene sentido descartarlo.
        df_mod['VALOR_M2_SUELO'] = suelo.fillna(
            pd.to_numeric(df_mod['VALOR_M2_SUELO'], errors='coerce')).fillna(0)
        sin_suelo = int((df_mod['VALOR_M2_SUELO'] <= 0).sum())
        print(f"🏷️ VALOR_M2_SUELO desde ZHG_2024/ZHG_2025: "
              f"{len(df_mod) - sin_suelo:,} de {len(df_mod):,} construcciones "
              f"({sin_suelo:,} sin valor de suelo)")
    except Exception as e:
        print(f"❌ No se pudo leer {RUTA_ZHG}: {e}")
        print("   Los modelos correrian con VALOR_M2_SUELO = 0, que es su "
              "variable principal. Se abandona la liquidacion por modelo.")
        return pd.DataFrame()

    # ---------------------------------------------------------------------
    # CAMPOS DERIVADOS DE LA ZHF **ANTERIOR**
    # ---------------------------------------------------------------------
    # La ZHF que leen los modelos es la de la entrega ANTERIOR
    # -export_predio_<fecha>, pegada como ZHF_ANTERIOR-, no la de la vigencia
    # que se esta liquidando: es la codificacion con la que se entrenaron.
    # Entre las dos entregas cambiaron de ZHF 293.312 predios, TODOS en comunas
    # actualizadas, que son justamente las que van por modelo: leer la nueva
    # les cambiaria TRAT_URB, INFLUENCIA_VIA, ACT_ECON y TIPO_SEGUN_ACT sin que
    # nada avisara.
    zhf = df_mod['ZHF'].astype(str)
    if MODO_INFORME:
        # En el informe la ZHF sale del export de la vigencia que produjo la
        # familia, no de la que arrastra el pipeline: la del pipeline es la de
        # la vigencia 2027 y en las comunas de 2024 difiere en el 43,7%.
        exp = export_de_grupo(MODO_INFORME)
        if exp is None:
            print(f"⚠️ Sin el export de la familia {MODO_INFORME}: los modelos "
                  f"leen la ZHF del pipeline")
        else:
            del_export = df_mod['ID_PREDIO'].astype(str).str.strip().map(
                exp['ZHF'])
            usable = del_export.notna() & del_export.astype(str).str.len().ge(11)
            zhf = del_export.where(usable, zhf)
            print(f"🧭 ZHF de los modelos (informe {MODO_INFORME}): "
                  f"{int(usable.sum()):,} de {len(df_mod):,} desde el export de "
                  f"esa vigencia ({int((~usable).sum()):,} caen a la del "
                  f"pipeline)")
    elif 'ZHF_ANTERIOR' in df_mod.columns:
        previa = df_mod['ZHF_ANTERIOR'].astype(str)
        usable = previa.notna() & previa.str.len().ge(11) & (previa != 'nan')
        zhf = previa.where(usable, zhf)
        print(f"🧭 ZHF de los modelos: {int(usable.sum()):,} de "
              f"{len(df_mod):,} desde ZHF_ANTERIOR "
              f"({int((~usable).sum()):,} caen a la ZHF de la vigencia)")
    else:
        print("⚠️ No hay ZHF_ANTERIOR: los modelos leen la ZHF de la vigencia")

    df_mod['ZHF_MODELO'] = zhf
    df_mod['CLASE_SUELO'] = zhf.str[0:1]#1
    df_mod['AREA_ACT'] = zhf.str[1:2]#2
    df_mod['TRAT_URB'] = zhf.str[2:4]#3 y 4
    df_mod['SERV_PUBL_DOM'] = zhf.str[4:5]#5
    df_mod['CLASE_VIA'] = zhf.str[5:6]#6
    df_mod['INFLUENCIA_VIA'] = zhf.str[6:7]#7
    df_mod['TOPOGRAFIA'] = zhf.str[7:8]#8
    df_mod['ACT_ECON'] = zhf.str[8:10]#9 y 10
    df_mod['TIPO_SEGUN_ACT'] = zhf.str[8:11] #9,10m11

    # De aqui abajo, cada familia se queda con SU grupo.
    df_mod_25 = df_mod[df_mod['GRUPO_MODELO'] == '2025'].copy()
    df_mod_24 = df_mod[df_mod['GRUPO_MODELO'] == '2024'].copy()
    huerfanas = df_mod[df_mod['GRUPO_MODELO'] == ''].copy()
    print(f"\n📌 Universo de modelo: {len(df_mod):,} construcciones  ->  "
          f"2025: {len(df_mod_25):,} | 2024: {len(df_mod_24):,} | "
          f"sin actualizacion: {len(huerfanas):,}")

    df_modelos = []

    # =========================================================================
    # MODELO 1 - DESTINOCONS '001'
    # =========================================================================
    print("\n" + "="*70)
    print("EJECUTANDO MODELO 1 (DESTINOCONS='001')")
    print("="*70)
    
    base_m1 = df_mod_25[df_mod_25["DESTINOCONS"] == '001'].copy()

    # 0.0 y no 0: la columna recibe abajo la prediccion, que trae decimales.
    # Inicializada en entero, pandas 3 rechaza la asignacion con
    # "Invalid value ... for dtype 'int64'" y el modelo entero se cae al except.
    base_m1['VM2_MOD'] = 0.0
    base_m1['MODELO_USADO'] = 'M1_2025'
    
    if not base_m1.empty:
        try:
            with open(os.path.join(RUTA_MODELOS_2025, "modelo_gbr_M1.pkl"), "rb") as file:
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
    base_M2_1 = df_mod_25[df_mod_25["DESTINOCONS"] == '028'].copy()
    base_M2_1 = base_M2_1[base_M2_1["TIPO_SEGUN_ACT"] != '023'].copy()
    base_M2_1['TIPO_SEGUN_ACT_013'] = np.where(base_M2_1['TIPO_SEGUN_ACT']=='013',1,0).astype(int)
    base_M2_1['VM2_MOD'] = 0.0
    base_M2_1['MODELO_USADO'] = 'M2_DIF_023_2025'

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
            
            ruta_modelo = os.path.join(RUTA_MODELOS_2025, 'pipeline_M02_DIF_023.pkl')
            
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
    base_M2_2 = df_mod_25[df_mod_25["DESTINOCONS"] == '028'].copy()
    base_M2_2 = base_M2_2[base_M2_2["TIPO_SEGUN_ACT"] == '023'].copy()
    base_M2_2['ACONCONS_17'] = np.where(base_M2_2["ACONCONS"]>=17,1,0).astype(int)
    base_M2_2['VM2_MOD'] = 0.0
    base_M2_2['MODELO_USADO'] = 'M2_IGUAL_023_2025'

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
            
            ruta_modelo = os.path.join(RUTA_MODELOS_2025, 'pipeline_M02_IGUAL_023.pkl')
            
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
    
    base_m3 = df_mod_25[df_mod_25["DESTINOCONS"] == '034'].copy()
    base_m3['VM2_MOD'] = 0.0   # float por lo mismo que base_m1, ver arriba
    base_m3['MODELO_USADO'] = 'M3_2025'

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
            with open(os.path.join(RUTA_MODELOS_2025, "M3_RF_20251221.pkl"), "rb") as file:
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
    # FAMILIA 2024 - COMUNAS 02, 04, 08, 17, 19
    # =========================================================================
    # Los modelos de la actualizacion 2024 se reparten por USO_LADM, no por
    # DESTINOCONS, y leen otras variables que los de 2025. Las que salen de la
    # ZHF se cortan distinto: aqui TIPO_SEGUN_ACT es UN digito -ZHF[10:11]- y
    # no los tres de la familia 2025. Verificado contra los 523 registros de
    # MODELOS/bases/PM/BASE_MODELACION_2024.xlsx: las ocho derivaciones dan
    # 523 de 523.
    if not df_mod_24.empty:
        print("\n" + "="*70)
        print("EJECUTANDO FAMILIA 2024 (comunas "
              f"{', '.join(sorted(df_mod_24['COMUNA'].unique()))})")
        print("="*70)

        df_mod_24['VM2_MOD'] = 0.0
        # Que modelo puso cada valor. Sirve para revisar el detalle sin
        # tener que reconstruir el ruteo a mano.
        df_mod_24['MODELO_USADO'] = ''
        # Las dos corridas de cada construccion: banderas de comuna como
        # corresponde y banderas en cero -el defecto de 2024-.
        df_mod_24['VM2_BANDERA_OK'] = np.nan
        df_mod_24['VM2_BANDERA_CERO'] = np.nan
        df_mod_24['BANDERAS_DEL_MODELO'] = ''
        print(f"♻️ MODO_DUMMY_2024 = '{MODO_DUMMY_2024}' para la bandera "
              f"COMUNA_03_04_08_17_19 de M1")

        # Las variables se arman en un frame APARTE, no como columnas de
        # df_mod_24. Dos razones: TIPO_SEGUN_ACT y TOPOGRAFIA ya existen en el
        # resto del proceso como TEXTO y aqui son numericas -al concatenar con
        # la rama de tablas la columna quedaba mezclando str e int y pyarrow no
        # la podia escribir: "Expected bytes, got a 'int' object"-, y ademas no
        # tiene sentido cargar el parquet final con doce dummies que solo usa
        # este bloque.
        npn = df_mod_24['NUMERO_PREDIAL_NACIONAL'].astype(str)
        zhf24 = df_mod_24['ZHF_MODELO'].astype(str)
        com = df_mod_24['COMUNA']
        # Un digito, no tres: es la diferencia con la familia 2025.
        t24 = pd.to_numeric(zhf24.str[10:11], errors='coerce')
        e24 = pd.to_numeric(zhf24.str[8:10], errors='coerce')
        a24 = pd.to_numeric(zhf24.str[1:2], errors='coerce')

        lon = pd.to_numeric(df_mod_24['LONGITUDE'], errors='coerce')
        lat = pd.to_numeric(df_mod_24['LATITUDE'], errors='coerce')

        x24 = pd.DataFrame(index=df_mod_24.index)
        x24['LONGITUD'] = lon
        x24['LATITUD'] = lat
        x24['LONGITUDLATITUD'] = lon * lat
        x24['NO_PISO'] = pd.to_numeric(npn.str[24:26], errors='coerce')
        x24['NO_CONST'] = pd.to_numeric(df_mod_24['NUM_CONST_TERR'], errors='coerce')
        # EDAD contra 2024, el mismo anio con que se entreno. Correrla a la
        # vigencia que se liquida la sacaria del rango que el modelo vio.
        x24['EDAD'] = 2024 - pd.to_numeric(df_mod_24['ANOCONST'], errors='coerce')
        x24['TIPO_SEGUN_ACT'] = t24
        x24['TOPOGRAFIA'] = pd.to_numeric(zhf24.str[7:8], errors='coerce')
        x24['ACT_ECON_01'] = (e24 == 1).astype(int)
        # Las banderas van SIEMPRE con su valor real. El modo 'cero' -el que
        # replica el defecto- se aplica al predecir, no aqui: asi el mismo
        # marco sirve para las dos corridas y el comparativo del informe no
        # tiene que rearmar las variables.
        x24['COMUNA_03_04_08_17_19'] = com.isin(
            ['03', '04', '08', '17', '19']).astype(int)
        for c in ['03', '17', '19', '22']:
            x24[f'COMUNA_{c}'] = (com == c).astype(int)
        x24['COMUNA_04_08'] = com.isin(['04', '08']).astype(int)
        x24['COMUNA_3_4_17_19'] = com.isin(['03', '04', '17', '19']).astype(int)
        for k in [3, 5]:
            x24[f'AREA_ACT_{k}'] = (a24 == k).astype(int)
        for k in ['02', '03']:
            x24[f'TRAT_URB_{k}'] = (zhf24.str[2:4] == k).astype(int)
        x24['INFLUENCIA_VIA_6'] = (
            pd.to_numeric(zhf24.str[6:7], errors='coerce') == 6).astype(int)
        # TIPO_SEGUN_ACT_<a>_ECON_<b> = ACT_ECON == a AND TIPO_SEGUN_ACT == b.
        # El nombre engaña -dice TIPO_SEGUN_ACT_3 pero el 3 es el ACT_ECON- y
        # leerlo al reves no da error, da un dummy distinto: con el orden
        # invertido salen 8.230 unos donde deben ir 9, y el M4 pasa de fallar el
        # 3% a fallar el 37%.
        #
        # Manda la base de produccion v2, que coincide 100% con esta lectura en
        # los tres dummies. Ojo que BASE_MODELACION_2024.xlsx -la de
        # entrenamiento- los trae al reves: el ejercicio entreno con una
        # convencion y liquido con la otra. Aqui se replica la de LIQUIDACION,
        # que es la que produjo el avaluo vigente.
        for econ, tipo in [(3, 2), (3, 3), (5, 1)]:
            x24[f'TIPO_SEGUN_ACT_{econ}_ECON_{tipo}'] = (
                (e24 == econ) & (t24 == tipo)).astype(int)
        # Las que se leen tal cual del proceso.
        for c in ['ESTRPRED', 'ARECPRED', 'TPISCONS', 'PUNTCONS',
                  'VALOR_M2_SUELO']:
            x24[c] = pd.to_numeric(df_mod_24[c], errors='coerce')

        # El destino de cada uso, para no correr un modelo cuyo destino esta
        # apagado en DESTINOS_MODELO_2024 (hoy, el M4 de oficinas).
        DESTINO_DE_USO = {'M1': '001', 'M3': '028', 'M4': '034'}

        familias_24 = [
            ('M1', 'Apartamentos_4_y_mas_pisos_en_PH',
             ['LONGITUD', 'LATITUD', 'ESTRPRED', 'NO_PISO', 'ARECPRED',
              'TPISCONS', 'PUNTCONS', 'TOPOGRAFIA', 'TIPO_SEGUN_ACT',
              'ACT_ECON_01', 'EDAD', 'COMUNA_03_04_08_17_19']),
            ('M3', 'Comercio_en_PH',
             ['VALOR_M2_SUELO', 'LONGITUD', 'LATITUD', 'NO_PISO', 'NO_CONST',
              'ARECPRED', 'TPISCONS', 'PUNTCONS', 'EDAD', 'COMUNA_03',
              'COMUNA_04_08', 'COMUNA_17', 'COMUNA_19', 'COMUNA_22']),
            ('M4', 'Oficinas_Consultorios_en_PH',
             ['LONGITUDLATITUD', 'COMUNA_3_4_17_19', 'TIPO_SEGUN_ACT_3_ECON_2',
              'VALOR_M2_SUELO', 'ARECPRED', 'NO_CONST', 'AREA_ACT_3',
              'TIPO_SEGUN_ACT_5_ECON_1', 'PUNTCONS', 'NO_PISO', 'TRAT_URB_02',
              'TRAT_URB_03', 'TPISCONS', 'TIPO_SEGUN_ACT_3_ECON_3',
              'AREA_ACT_5', 'INFLUENCIA_VIA_6']),
        ]

        if not modelos_2024_disponibles():
            faltan = [f for f in ARCHIVOS_MODELOS_2024.values()
                      if not os.path.exists(os.path.join(RUTA_MODELOS_2024, f))]
            print(f"❌ FALTAN los .pkl de la familia 2024 en {RUTA_MODELOS_2024}: "
                  f"{', '.join(faltan)}")
            print(f"   Las {len(df_mod_24):,} construcciones de las comunas "
                  f"{', '.join(COMUNAS_MODELO_2024)} quedan en VM2_MOD = 0.")
            print("   Las variables ya estan armadas: en cuanto lleguen los "
                  "archivos, este bloque predice sin tocar nada mas.")
        else:
            for clave, uso, variables in familias_24:
                if DESTINO_DE_USO[clave] not in DESTINOS_MODELO_2024:
                    print(f"⏭️ MODELO {clave} 2024 ({uso}): apagado, sus "
                          f"construcciones se liquidan por tabla")
                    continue
                base = x24[df_mod_24['USO_LADM'] == uso]
                if base.empty:
                    print(f"ℹ️ MODELO {clave} 2024 ({uso}): sin registros")
                    continue
                try:
                    modelo = _cargar(os.path.join(RUTA_MODELOS_2024,
                                                  ARCHIVOS_MODELOS_2024[clave]))
                    # Manda el modelo: las variables que el declara, en su
                    # orden. La lista de arriba es solo el respaldo. Importa
                    # porque en M4 el orden es lo unico que identifica cada
                    # columna, y equivocarlo no da error: da un numero mal.
                    declaradas = _variables_declaradas(modelo)
                    if declaradas is not None:
                        variables = declaradas
                    faltan = [v for v in variables if v not in base.columns]
                    if faltan:
                        print(f"⚠️ MODELO {clave} 2024: columnas faltantes: {faltan}")
                        continue
                    n_esperadas = getattr(modelo, 'n_features_in_', len(variables))
                    if n_esperadas != len(variables):
                        print(f"⚠️ MODELO {clave} 2024: espera {n_esperadas} "
                              f"variables y se le arman {len(variables)}. No se predice.")
                        continue
                    x = base[variables].apply(pd.to_numeric, errors='coerce').dropna()
                    if x.empty:
                        print(f"⚠️ MODELO {clave} 2024: sin filas validas tras dropna")
                        continue
                    # Sin nombres declarados se pasa el array pelado: un
                    # DataFrame con nombres haria que xgboost los compare
                    # contra los suyos, que no tiene.
                    def _predice(marco):
                        return np.asarray(modelo.predict(
                            marco if declaradas is not None
                            else marco.to_numpy())).ravel()

                    # Las banderas de comuna que ESTE modelo lee. Se predice dos
                    # veces -con las banderas como corresponde y con las suyas
                    # en cero- y la diferencia es, exactamente, lo que el
                    # defecto de 2024 le hizo al valor. Son los tres modelos, no
                    # solo M1: M3 lee cinco banderas y M4 lee COMUNA_3_4_17_19,
                    # y las siete salieron del mismo isin contra enteros.
                    banderas = [v for v in variables
                                if v in BANDERAS_COMUNA_2024]
                    y_ok = _predice(x)
                    if banderas:
                        x_cero = x.copy()
                        x_cero[banderas] = 0
                        y_cero = _predice(x_cero)
                    else:
                        y_cero = y_ok
                    df_mod_24.loc[x.index, 'VM2_BANDERA_OK'] = y_ok
                    df_mod_24.loc[x.index, 'VM2_BANDERA_CERO'] = y_cero
                    df_mod_24.loc[x.index, 'BANDERAS_DEL_MODELO'] = (
                        ', '.join(banderas) if banderas else 'ninguna')

                    # Lo que se liquida. 'cero' replica la corrida de 2024 y
                    # toca solo a M1, que es donde se comprobo que el avaluo
                    # vigente salio con la bandera apagada.
                    if clave == 'M1' and MODO_DUMMY_2024 == 'por_predio':
                        y, origen = _bandera_por_predio(modelo, x, df_mod_24)
                        df_mod_24.loc[x.index, 'ORIGEN_BANDERA'] = origen
                    elif clave == 'M1' and MODO_DUMMY_2024 == 'cero':
                        y = y_cero
                    else:
                        y = y_ok
                    df_mod_24.loc[x.index, 'VM2_MOD'] = y
                    df_mod_24.loc[x.index, 'MODELO_USADO'] = f'{clave}_2024'
                    perdidas = len(base) - len(x)
                    print(f"✅ MODELO {clave} 2024 ({uso}): {len(y):,} predicciones "
                          f"de {len(base):,} | Min: {y.min():,.0f} "
                          f"Max: {y.max():,.0f} Media: {y.mean():,.0f}"
                          + (f" | {perdidas:,} sin variables completas" if perdidas else ""))
                except Exception as e:
                    print(f"⚠️ Error en MODELO {clave} 2024: {e}")
                    import traceback
                    traceback.print_exc()

        df_modelos.append(df_mod_24)

    # =========================================================================
    # CONCATENAR Y RETORNAR
    # =========================================================================
    print("\n" + "="*70)
    print("🔗 CONCATENANDO RESULTADOS...")
    print("="*70)

    etiquetas = ['2025 DEST 001', '2025 DEST 028 (dif 023)',
                 '2025 DEST 028 (= 023)', '2025 DEST 034', 'familia 2024']
    for i, df in enumerate(df_modelos):
        etiqueta = etiquetas[i] if i < len(etiquetas) else 'N/A'
        print(f"DataFrame {i} ({etiqueta}): {len(df)} registros, {(df['VM2_MOD'] > 0).sum()} con predicción")

    df_liq_modelos = pd.concat(df_modelos, ignore_index=True)

    # El incremento por familia, sobre la prediccion. Queda tambien como columna
    # para que en el detalle se vea que se aplico y cuanto.
    df_liq_modelos['INCREMENTO'] = (df_liq_modelos['GRUPO_MODELO']
                                    .map(INCREMENTO_MODELO).fillna(1.0))
    df_liq_modelos['VM2_MOD'] = df_liq_modelos['VM2_MOD'] * df_liq_modelos['INCREMENTO']
    # Las dos corridas de la bandera llevan el mismo incremento que el valor
    # liquidado; si no, el comparativo del informe estaria restando un valor
    # con incremento contra otro sin el.
    for _c in ('VM2_BANDERA_OK', 'VM2_BANDERA_CERO'):
        if _c in df_liq_modelos.columns:
            df_liq_modelos[_c] = (pd.to_numeric(df_liq_modelos[_c],
                                                errors='coerce')
                                  * df_liq_modelos['INCREMENTO'])
    for _g, _f in INCREMENTO_MODELO.items():
        _n = int((df_liq_modelos['GRUPO_MODELO'] == _g).sum())
        if _n and _f != 1.0:
            print(f"📈 Familia {_g}: incremento x{_f} aplicado a {_n:,} "
                  f"construcciones")
    
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

    print("\n📈 Distribución por actualización:")
    for grupo in ['2025', '2024']:
        sub = df_liq_modelos[df_liq_modelos['GRUPO_MODELO'] == grupo]
        if len(sub) == 0:
            continue
        con = sub[sub['VM2_MOD'] > 0]
        print(f"  - {grupo}: {len(sub):,} registros | {len(con):,} con predicción "
              f"({len(con)/len(sub)*100:.1f}%)"
              + (f" | VM2_MOD mediana {con['VM2_MOD'].median():,.0f}" if len(con) else ""))

    print("="*70)
    
    return df_liq_modelos


# =====================================================================
# DETALLE DE LO LIQUIDADO POR MODELO
# =====================================================================
# El detalle de lo liquidado por TABLA lo entrega comparacion_vigencia en
# DETALLE_LIQUIDADOS_<fecha>.xlsx, y alli las construcciones de modelo NO
# aparecen: esa comparacion arma el valor liquidado como VM2_COM_LIQ = VM2, y
# en las filas de modelo VM2 es 0 -su valor esta en VM2_MOD-, asi que se caen
# por "sin VM2 de tabla". Este es el archivo que falta.
#
# Dos avisos para leerlo:
#   - VM2_MOD es INTEGRAL: lleva el suelo dentro. Se compara contra el integral
#     de la vigencia (VALORCONS/ACONCONS), no contra un VM2 de construccion.
#   - VM2_MOD es COMERCIAL, como el VM2 de las tablas. El catastral es x0.7.
COLUMNAS_DETALLE_MODELO = [
    # --- que predio es ---
    'ID_PREDIO', 'NUMERO_PREDIAL_NACIONAL', 'ID_CONSTRUCCION',
    'COMUNA', 'GRUPO_MODELO', 'MODELO_USADO',
    'USO_LADM', 'DESTINOCONS', 'CONDICION', 'ESTRPRED',
    # --- con que se predijo ---
    'ZHF_ANTERIOR', 'ZHF', 'CAMBIO_ZHF', 'VALOR_M2_SUELO',
    'PUNTCONS', 'ACONCONS', 'AREA_CONST', 'ARECPRED', 'ANOCONST', 'TPISCONS',
    'NO_PISO', 'NUM_CONST_TERR', 'LATITUDE', 'LONGITUDE',
    # --- ejercicio de sismo: vacias en una corrida normal ---
    'Escenario', 'Estado', 'prc_Estado', 'ORIGEN_BANDERA',
    # --- lo que liquida ---
    'VM2_MOD_COM', 'VM2_MOD_CAT', 'VALORCONS_MOD_COM', 'VALORCONS_MOD_CAT',
    'INCREMENTO_APLICADO', 'INCREMENTO_IMPLICITO', 'VM2_MOD_CAT_CON_IMPLICITO',
    # --- contra la vigencia ---
    'AVALPRED', 'VALORCONS', 'VM2_CAT_VIGENCIA', 'VM2_COM_VIGENCIA',
    'DIF_CAT_ABS', 'VARIACION_CAT_PCT', 'SENTIDO', 'RANGO_VARIACION',
    # --- replica el ejercicio que produjo el avaluo vigente? ---
    'VIGENCIA_REF', 'VM2_CAT_REF', 'DIF_VS_REF', 'COINCIDE', 'BANDERA_2024',
    'VM2_CAT_CON_DEFECTO', 'VM2_CAT_CORRECTO', 'EXCESO_VM2_CAT',
    'EXCESO_AVALUO',
]

DICCIONARIO_DETALLE_MODELO = [
    ('GRUPO_MODELO', 'Actualizacion por la que va el predio: 2024 o 2025. La decide la comuna.'),
    ('MODELO_USADO', 'Modelo que puso el valor: M1/M2/M3 de 2025, o M1/M3/M4 de 2024.'),
    ('VM2_MOD_COM', 'La prediccion DEPURADA: valor limpio del modelo, sin ningun incremento encima.'),
    ('INCREMENTO_APLICADO', 'Factor que la liquidacion le puso encima. Hoy 1.00 en las dos familias: VM2_MOD_COM y VM2_MOD_CAT son el valor puro del modelo.'),
    ('INCREMENTO_IMPLICITO', 'El incremento que ESTE predio trae de verdad: VM2_CAT_VIGENCIA / VM2_MOD_CAT. En 2024 cae en escalones (1.0370 el 15%, 1.0300 el 11%, 1.0490 el 8%, 1.0510 el 5%...); en 2025 da 1.0000 porque alli el vigente ES la salida del modelo. Vacio si no hay valor vigente con que compararlo.'),
    ('Escenario', 'Escenario del ejercicio de sismo: bajo, moderado o alto. Vacio en una corrida normal.'),
    ('Estado', 'Estado de afectacion de la construccion: Sin afectacion, Posible Dano Estructural, Dano Moderado, Evidente Dano Estructural o Colapso.'),
    ('prc_Estado', 'Porcentaje con que ese estado castiga el PUNTCONS. Es por donde el sismo entra al modelo: PUNTCONS es variable de los tres modelos 2024 y del M1 de 2025.'),
    ('ORIGEN_BANDERA', 'Solo en modo por_predio: de donde salio la bandera de comuna de esa fila. \'avaluo 2025\' = se dedujo de cual prediccion reproduce su avaluo; \'manzana\' = heredada de la mayoria de su manzana; \'defecto (0)\' = sin informacion.'),
    ('COINCIDE', 'SI cuando el modelo reproduce el avaluo del ejercicio que valoro ese predio, con tolerancia de 1.000 pesos/m2. SIN REFERENCIA cuando no hay con que comparar (la familia 2024 solo se puede comparar contra predios que sigan en VIGEPRED 01/01/25).'),
    ('VM2_CAT_REF', 'El m2 catastral que el predio tiene REGISTRADO en la vigencia de referencia (2025 para la familia 2024, 2026 para la 2025).'),
    ('VM2_CAT_CON_DEFECTO', 'Lo que da M1 con la bandera de comuna en cero: la corrida que llevaba el defecto. Es lo que quedo registrado en 48.152 construcciones.'),
    ('VM2_CAT_CORRECTO', 'Lo que da M1 con la bandera como corresponde. Es el valor que el predio DEBERIA tener, y el que produjo la preliquidacion del 31/12/2024.'),
    ('EXCESO_VM2_CAT', 'VM2_CAT_REF menos VM2_CAT_CORRECTO. Cuanto tiene de mas por m2. Solo se llena donde BANDERA_2024 dice "0 - con el defecto".'),
    ('EXCESO_AVALUO', 'EXCESO_VM2_CAT por el area construida: cuanto tiene de mas el avaluo de ese predio, en pesos.'),
    ('BANDERA_2024', 'Solo M1 de 2024. A cual de las dos corridas de 2024 corresponde el avaluo vigente del predio: "0 - con el defecto" es la que llevaba COMUNA_03_04_08_17_19 en cero por el isin de input_model_consolidado.py, y quedo ~9% por encima; "1 - correcta" es la buena. Las comunas 02 y 22 salen como "no distingue" porque alli la bandera vale 0 de las dos formas y no estan afectadas.'),
    ('VIGENCIA_REF', 'Contra que vigencia se compara: 2025 para la familia 2024 -es la que ese ejercicio produjo- y 2026 para la familia 2025.'),
    ('VM2_CAT_REF', 'El integral catastral por m2 de esa vigencia. Para 2024 sale de export_predio_2025.txt (AVALPRED/ARECPRED); para 2025, de VALORCONS/ACONCONS.'),
    ('DIF_VS_REF', 'VM2_MOD_CAT - VM2_CAT_REF. Es la diferencia que decide COINCIDE.'),
    ('VM2_MOD_CAT_CON_IMPLICITO', 'VM2_MOD_CAT x INCREMENTO_IMPLICITO. Reproduce el avaluo vigente por construccion: sirve para ver el efecto del incremento, NO para liquidar.'),
    ('ZHF_ANTERIOR', 'La ZHF que LEYO el modelo (export_predio anterior). Es la codificacion con la que se entreno.'),
    ('ZHF', 'La ZHF de la vigencia que se liquida. Informativa: el modelo no la usa.'),
    ('CAMBIO_ZHF', '1 si la ZHF de la vigencia difiere de la anterior.'),
    ('VALOR_M2_SUELO', 'ZHG_2024 o ZHG_2025 segun el grupo. NO es el del export, que viene en cero en estas comunas.'),
    ('NO_PISO', 'Piso de la unidad, del predial nacional (posiciones 25-26). Variable de los modelos 2024.'),
    ('VM2_MOD_COM', 'Prediccion del modelo. Es INTEGRAL (suelo + construccion) y COMERCIAL.'),
    ('VM2_MOD_CAT', 'VM2_MOD_COM x 0.7 (factor catastral).'),
    ('VALORCONS_MOD_COM', 'AREA_CONST x VM2_MOD_COM: lo que vale la construccion liquidada.'),
    ('VM2_CAT_VIGENCIA', 'VALORCONS / ACONCONS: el integral catastral por m2 de HOY.'),
    ('VARIACION_CAT_PCT', 'Cuanto se mueve el m2 integral catastral frente a la vigencia.'),
    ('TIPO_SEGUN_ACT', 'Ojo: en el parquet va cortada a 3 digitos (criterio 2025). Los modelos 2024 usan UN digito.'),
]


def _bandera_del_avaluo_2024(d):
    """
    A cual de las dos corridas de 2024 corresponde el avaluo vigente de cada
    construccion de M1.

    Se predice con la bandera de comuna en 0 -la corrida que llevaba el defecto
    del isin- y con su valor correcto, y se mira cual reproduce el avaluo de la
    vigencia 2025. Solo una puede: se llevan un 9%.

    Las comunas 02 y 22 quedan aparte: alli la bandera vale 0 de las dos
    formas, las dos predicciones son identicas y la comparacion no distingue
    nada. Contarlas como "con el defecto" seria enganoso - no estan afectadas.
    """
    fuera = 'no aplica (no es M1 2024)'
    marca = pd.Series(fuera, index=d.index)
    cat0_out = pd.Series(np.nan, index=d.index)
    cat1_out = pd.Series(np.nan, index=d.index)
    es_m1 = d.get('MODELO_USADO', pd.Series('', index=d.index)) == 'M1_2024'
    if not es_m1.any():
        return marca, cat0_out, cat1_out
    try:
        modelo = _cargar(os.path.join(RUTA_MODELOS_2024,
                                      ARCHIVOS_MODELOS_2024['M1']))
        vs = [str(v) for v in modelo.feature_names_in_]
    except Exception as e:
        print(f"   (no se pudo clasificar la bandera 2024: {e})")
        return marca, cat0_out, cat1_out

    s = d[es_m1]
    z = s['ZHF_ANTERIOR'].astype(str)
    com = s['COMUNA'].astype(str).str.zfill(2)
    npn = s['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
    x = pd.DataFrame(index=s.index)
    x['LONGITUD'] = pd.to_numeric(s['LONGITUDE'], errors='coerce')
    x['LATITUD'] = pd.to_numeric(s['LATITUDE'], errors='coerce')
    x['ESTRPRED'] = pd.to_numeric(s['ESTRPRED'], errors='coerce')
    x['NO_PISO'] = pd.to_numeric(npn.str[24:26], errors='coerce')
    x['ARECPRED'] = pd.to_numeric(s['ARECPRED'], errors='coerce')
    x['TPISCONS'] = pd.to_numeric(s['TPISCONS'], errors='coerce')
    x['PUNTCONS'] = pd.to_numeric(s['PUNTCONS'], errors='coerce')
    x['TOPOGRAFIA'] = pd.to_numeric(z.str[7:8], errors='coerce')
    x['TIPO_SEGUN_ACT'] = pd.to_numeric(z.str[10:11], errors='coerce')
    x['ACT_ECON_01'] = (pd.to_numeric(z.str[8:10], errors='coerce') == 1).astype(int)
    x['EDAD'] = 2024 - pd.to_numeric(s['ANOCONST'], errors='coerce')

    x1 = x.copy()
    x1['COMUNA_03_04_08_17_19'] = com.isin(['03', '04', '08', '17', '19']).astype(int)
    x0 = x.copy(); x0['COMUNA_03_04_08_17_19'] = 0
    x1, x0 = x1[vs], x0[vs]
    ok = x1.notna().all(axis=1)
    if not ok.any():
        return marca, cat0_out, cat1_out

    cat1 = pd.Series(np.nan, index=s.index); cat0 = pd.Series(np.nan, index=s.index)
    cat1[ok] = modelo.predict(x1[ok]) * 0.7
    cat0[ok] = modelo.predict(x0[ok]) * 0.7
    ref = pd.to_numeric(s['VM2_CAT_REF'], errors='coerce')

    tol = 1_000
    m = pd.Series('no corresponde a ninguna', index=s.index)
    m[(cat0 - ref).abs() <= tol] = '0 - con el defecto'
    m[(cat1 - ref).abs() <= tol] = '1 - correcta'
    m[ref.isna()] = 'sin referencia'
    m[com.isin(['02', '22'])] = 'no distingue (comuna 02 y 22)'
    marca.loc[s.index] = m
    cat0_out.loc[s.index] = cat0
    cat1_out.loc[s.index] = cat1
    return marca, cat0_out, cat1_out


def detalle_modelo_excel(df_const_liq, ruta=None, fecha=None):
    """
    Excel con el detalle de las construcciones que liquido el MODELO.

    Se arma del mismo frame que se guarda en LIQUIDACION_TABLAS.parquet, asi
    que dice exactamente lo que quedo liquidado.
    """
    from datetime import datetime

    d = df_const_liq[df_const_liq['TABLA_ORIGEN'] == 'MODELO'].copy()
    if d.empty:
        print("No hay construcciones liquidadas por modelo: no se escribe el detalle")
        return None

    def num(c):
        return (pd.to_numeric(d[c], errors='coerce') if c in d.columns
                else pd.Series(np.nan, index=d.index))

    factor = 0.7                       # catastral = comercial x 0.7
    d['VM2_MOD_COM'] = num('VM2_MOD')
    d['VM2_MOD_CAT'] = d['VM2_MOD_COM'] * factor
    area = num('AREA_CONST')
    d['VALORCONS_MOD_COM'] = area * d['VM2_MOD_COM']
    d['VALORCONS_MOD_CAT'] = d['VALORCONS_MOD_COM'] * factor

    # Todas las comunas que van por modelo son actualizadas, asi que el factor
    # comercial de la vigencia es 0.7 para todas; queda escrito y no supuesto.
    aconcons = num('ACONCONS').replace(0, np.nan)
    d['VM2_CAT_VIGENCIA'] = num('VALORCONS') / aconcons
    d['VM2_COM_VIGENCIA'] = d['VM2_CAT_VIGENCIA'] / factor
    d['DIF_CAT_ABS'] = d['VM2_MOD_CAT'] - d['VM2_CAT_VIGENCIA']
    d['VARIACION_CAT_PCT'] = d['DIF_CAT_ABS'] / d['VM2_CAT_VIGENCIA'] * 100
    # La tolerancia no es cosmetica: en las comunas de 2025 el avaluo vigente YA
    # salio de estos mismos modelos, asi que la mayoria de las filas reproduce
    # el valor de hoy. Sin tolerancia, ese ruido sale rotulado como "BAJA con la
    # liquidacion" en decenas de miles de construcciones que no se movieron.
    #
    # Mil pesos por m2 sobre valores de ~2.5 millones es un 0.04%: por debajo de
    # eso no hay diferencia que revisar. Es el corte que separa "reproduce el
    # valor vigente" de "hay algo que mirar".
    TOLERANCIA_M2 = 1_000
    d['SENTIDO'] = np.select(
        [d['DIF_CAT_ABS'].abs() <= TOLERANCIA_M2, d['DIF_CAT_ABS'] > 0],
        ['IGUAL (reproduce el valor vigente)', 'SUBE con la liquidacion'],
        default='BAJA con la liquidacion')
    d['RANGO_VARIACION'] = pd.cut(
        d['VARIACION_CAT_PCT'],
        bins=[-np.inf, -50, -25, -10, 10, 25, 50, np.inf],
        labels=['baja mas de 50%', 'baja 25-50%', 'baja 10-25%',
                'estable (+-10%)', 'sube 10-25%', 'sube 25-50%',
                'sube mas de 50%']).astype(str)

    # El incremento que la liquidacion aplico (hoy 1.00) y el que el predio trae
    # de verdad, deducido de su avaluo vigente. El implicito solo tiene sentido
    # donde hay valor vigente y prediccion: si alguno es cero, queda vacio.
    d['INCREMENTO_APLICADO'] = (pd.to_numeric(d['INCREMENTO'], errors='coerce')
                                if 'INCREMENTO' in d.columns else 1.0)
    d['INCREMENTO_IMPLICITO'] = np.where(
        d['VM2_MOD_CAT'] > 0, d['VM2_CAT_VIGENCIA'] / d['VM2_MOD_CAT'], np.nan)
    d['VM2_MOD_CAT_CON_IMPLICITO'] = d['VM2_MOD_CAT'] * d['INCREMENTO_IMPLICITO']

    # ---- COINCIDE: reproduce el avaluo del ejercicio que lo valoro? ----
    # Cada familia se compara contra SU vigencia: la 2024 valoro para 2025 y la
    # 2025 para 2026. Comparar las dos contra 2026 fue el error que mas tiempo
    # costo: contra la 2026 la familia 2024 no cuadra con nada.
    ref_2025 = vigencia_2025()
    npn = (d['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
           if 'NUMERO_PREDIAL_NACIONAL' in d.columns
           else pd.Series('', index=d.index))
    es24 = d['GRUPO_MODELO'].astype(str) == '2024'
    d['VIGENCIA_REF'] = np.where(es24, '2025', '2026')
    d['VM2_CAT_REF'] = np.where(es24, npn.map(ref_2025), d['VM2_CAT_VIGENCIA'])
    d['VM2_CAT_REF'] = pd.to_numeric(d['VM2_CAT_REF'], errors='coerce')
    d['DIF_VS_REF'] = d['VM2_MOD_CAT'] - d['VM2_CAT_REF']
    d['COINCIDE'] = np.where(
        d['VM2_CAT_REF'].isna(), 'SIN REFERENCIA',
        np.where(d['DIF_VS_REF'].abs() <= TOLERANCIA_M2, 'SI', 'NO'))
    _n = len(d)
    for _v in ('SI', 'NO', 'SIN REFERENCIA'):
        _k = int((d['COINCIDE'] == _v).sum())
        if _k:
            print(f"   COINCIDE={_v}: {_k:,} ({_k / _n * 100:.1f}%)")

    (d['BANDERA_2024'],
     d['VM2_CAT_CON_DEFECTO'],
     d['VM2_CAT_CORRECTO']) = _bandera_del_avaluo_2024(d)
    _b = d.loc[d['BANDERA_2024'] != 'no aplica (no es M1 2024)', 'BANDERA_2024']
    if len(_b):
        print("   bandera del avaluo 2024 -> " + ", ".join(
            f"{k}: {v:,}" for k, v in _b.value_counts().items()))

    # Cuanto tiene de mas el predio por el defecto: lo que quedo registrado
    # menos lo que el modelo da con la bandera bien puesta. Solo tiene sentido
    # donde el avaluo SI salio de la corrida con el defecto.
    _con_defecto = d['BANDERA_2024'] == '0 - con el defecto'
    d['EXCESO_VM2_CAT'] = np.where(
        _con_defecto, d['VM2_CAT_REF'] - d['VM2_CAT_CORRECTO'], np.nan)
    d['EXCESO_AVALUO'] = d['EXCESO_VM2_CAT'] * area
    if _con_defecto.any():
        _e = pd.to_numeric(d.loc[_con_defecto, 'EXCESO_AVALUO'], errors='coerce')
        print(f"   con el defecto: {int(_con_defecto.sum()):,} construcciones, "
              f"{_e.sum():,.0f} de mas en avaluo")

    if 'ZHF_ANTERIOR' in d.columns and 'ZHF' in d.columns:
        d['CAMBIO_ZHF'] = (d['ZHF'].astype(str)
                           != d['ZHF_ANTERIOR'].astype(str)).astype(int)
    if 'NO_PISO' not in d.columns and 'NUMERO_PREDIAL_NACIONAL' in d.columns:
        d['NO_PISO'] = pd.to_numeric(
            d['NUMERO_PREDIAL_NACIONAL'].astype(str).str[24:26], errors='coerce')

    cols = [c for c in COLUMNAS_DETALLE_MODELO if c in d.columns]
    faltan = [c for c in COLUMNAS_DETALLE_MODELO if c not in d.columns]
    if faltan:
        print(f"   (al detalle de modelo le faltan columnas: {faltan})")
    det = d[cols].sort_values(['GRUPO_MODELO', 'MODELO_USADO', 'COMUNA',
                               'ID_PREDIO'], kind='stable')

    resumen = (det.groupby(['GRUPO_MODELO', 'MODELO_USADO', 'COMUNA'],
                           dropna=False)
                  .agg(CONSTRUCCIONES=('ID_PREDIO', 'size'),
                       PREDIOS=('ID_PREDIO', 'nunique'),
                       AREA_M2=('AREA_CONST', 'sum'),
                       VM2_MOD_CAT_MEDIANA=('VM2_MOD_CAT', 'median'),
                       VM2_CAT_VIGENCIA_MEDIANA=('VM2_CAT_VIGENCIA', 'median'),
                       VARIACION_CAT_PCT_MEDIANA=('VARIACION_CAT_PCT', 'median'),
                       VALORCONS_MOD_CAT=('VALORCONS_MOD_CAT', 'sum'))
                  .reset_index())

    fecha = fecha or datetime.now().strftime('%Y%m%d')
    if ruta is None:
        ruta = os.path.join('./results/COMPARACION_VIGENCIA',
                            f'DETALLE_LIQUIDADOS_MODELO_{fecha}.xlsx')
    os.makedirs(os.path.dirname(ruta) or '.', exist_ok=True)
    if os.path.exists(ruta):
        try:
            with open(ruta, 'a+b'):
                pass
        except PermissionError:
            print(f"No se pudo sobrescribir '{os.path.basename(ruta)}': "
                  f"esta abierto en Excel. Cierrelo y vuelva a correr.")
            return None

    with pd.ExcelWriter(ruta, engine='xlsxwriter') as xls:
        det.to_excel(xls, sheet_name='DETALLE', index=False)
        resumen.to_excel(xls, sheet_name='RESUMEN', index=False)
        pd.DataFrame(DICCIONARIO_DETALLE_MODELO,
                     columns=['COLUMNA', 'QUE ES']).to_excel(
            xls, sheet_name='DICCIONARIO', index=False)
        libro = xls.book
        miles = libro.add_format({'num_format': '#,##0'})
        pct = libro.add_format({'num_format': '0.0"%"'})
        cabecera = libro.add_format({'bold': True, 'bg_color': '#DDEBF7',
                                     'border': 1, 'text_wrap': True,
                                     'valign': 'vcenter'})
        for hoja, marco in (('DETALLE', det), ('RESUMEN', resumen)):
            h = xls.sheets[hoja]
            h.freeze_panes(1, 0)
            h.autofilter(0, 0, len(marco), len(marco.columns) - 1)
            for i, c in enumerate(marco.columns):
                h.write(0, i, c, cabecera)
                if 'PCT' in c:
                    fmt, ancho = pct, 14
                elif marco[c].dtype.kind in 'fi':
                    fmt, ancho = miles, 16
                else:
                    fmt, ancho = None, max(12, min(30, len(c) + 4))
                h.set_column(i, i, ancho, fmt)
        h = xls.sheets['DICCIONARIO']
        h.set_column(0, 0, 26)
        h.set_column(1, 1, 110)

    # Gemelo en parquet, al lado del Excel. Pesa una decima parte y se lee en
    # segundos: es lo que se usa para comparar escenarios entre si, donde hay
    # que abrir cuatro detalles seguidos.
    try:
        det.to_parquet(os.path.splitext(ruta)[0] + '.parquet', index=False)
    except Exception as e:
        print(f"   (no se pudo escribir el parquet del detalle: {e})")

    print(f"Detalle de liquidados por MODELO: {ruta} "
          f"({len(det):,} construcciones, {det['ID_PREDIO'].nunique():,} predios)")
    return ruta


# =====================================================================
# LA HOJA DE LOS QUE VAN POR MODELO
# =====================================================================
# DOS Excel, uno por actualizacion, cada uno con su universo completo y cada
# familia corrida contra el export de la vigencia que ese ejercicio produjo:
#
#   HOJA_MODELOS_2024_<fecha>.xlsx   comunas 02, 03, 04, 08, 17, 19, 22
#                                    export_predio_2025.txt
#   HOJA_MODELOS_2025_<fecha>.xlsx   comunas 01, 03, 09, 10, 11, 12, 22
#                                    export_predio_20260717
#
# Las comunas 03 y 22 estan en las dos actualizaciones y por eso aparecen en
# los dos archivos: son dos liquidaciones contra dos vigencias distintas, no un
# cruce repetido.
#
# Cada hoja lleva DOS analisis, y cada uno empieza por su columna de marca:
#
#   AFECTADOS_MODELOS   solo en 2024. Si el defecto de las banderas de comuna
#                       esta dentro del avaluo registrado, y detras el
#                       comparativo: como quedo contra como debio quedar.
#   AFECTADOS_SISMO     en las dos. Si el ejercicio de sismo le castiga el
#                       puntaje, y detras la liquidacion en los tres
#                       escenarios con el PUNTCONS ya castigado.
#
# En 2025 va solo el de sismo: esa familia no tiene el defecto de la bandera.
#
# Se corre solo:  python src/model_liq.py
ESCENARIOS_INFORME = ['bajo', 'moderado', 'alto']

# Rangos de la diferencia que deja la bandera. Para el m2 los cortes van en
# pesos; para construccion y avaluo van escalados a millones, porque diez mil
# pesos sobre un avaluo de 500 millones no dicen nada.
CORTES_M2 = [0, 10_000, 50_000, 100_000, 150_000, np.inf]
ETIQ_M2 = ['0 a 10 mil', '10 a 50 mil', '50 a 100 mil', '100 a 150 mil',
           'mayor a 150 mil']
CORTES_VALOR = [0, 10e6, 50e6, 100e6, 150e6, np.inf]
ETIQ_VALOR = ['0 a 10 millones', '10 a 50 millones', '50 a 100 millones',
              '100 a 150 millones', 'mayor a 150 millones']

# Cada familia liquida sobre la tabla de construcciones de SU vigencia, y sus
# escenarios de sismo estan calculados sobre esa misma tabla. Mezclarlas seria
# lo peor de los dos mundos: la diferencia entre la liquidacion base y la del
# escenario dejaria de ser el sismo y pasaria a ser sismo mas cambio de tabla.
#
#   2024 -> export_construccion_2025.txt      y export_construccion_<esc>.parquet
#   2025 -> el export de construccion de hoy  y *homologado*_<esc>.parquet
#
# Se cruza por NUMERO_PREDIAL_NACIONAL, no por ID_CONSTRUCCION: ese cambio
# entre vigencias y contra la tabla de 2025 la cobertura por ID es del 0,0%
# contra 99,9% por predial.
RUTA_CONSTRUCCION_2025 = './input/export_liq/export_construccion_2025.txt'
COLUMNAS_CONSTRUCCION_2025 = ['PUNTCONS', 'TPISCONS', 'ANOCONST', 'ACONCONS']
PATRON_ESCENARIO_POR_GRUPO = {
    '2024': './input/export_liq/Escenarios/export_construccion_{esc}.parquet',
    '2025': './input/export_liq/Escenarios/*homologado*_{esc}.parquet',
}

_escenarios = {}


def escenario_sismo(esc, grupo):
    """
    PUNTCONS castigado, Estado y prc_Estado del escenario, por ID_CONSTRUCCION.

    El PUNTCONS del archivo YA viene castigado: es el del export crudo por
    (1 - prc_Estado), comprobado exacto en las 37.705 construcciones con
    prc > 0. No hay que aplicarle nada, se toma tal cual.

    Los tres escenarios traen el MISMO Estado -el sismo es uno solo- y lo que
    cambia es cuanto castiga cada estado:

        estado                      bajo   moderado   alto
        Sin afectacion              0%     0%         0%
        Posible Dano Estructural    15%    20%        35%
        Dano Moderado               5%     7,5%       10%
        Evidente Dano Estructural   45%    55%        60%
        Colapso                     100%   100%       100%

    Por eso en la hoja va UNA columna de estado y tres de valor.
    """
    if (esc, grupo) in _escenarios:
        return _escenarios[(esc, grupo)]
    patron = PATRON_ESCENARIO_POR_GRUPO[grupo].format(esc=esc)
    rutas = sorted(glob.glob(patron), reverse=True)
    if not rutas:
        print(f"No hay archivo del escenario '{esc}' para la familia {grupo} "
              f"({patron})")
        _escenarios[(esc, grupo)] = None
        return None
    e = pd.read_parquet(rutas[0], columns=['ID_PREDIO', 'PUNTCONS',
                                           'ACONCONS', 'Estado',
                                           'prc_Estado'])
    e['LLAVE'] = _llave_predio(e['ID_PREDIO'])
    for c in ('PUNTCONS', 'ACONCONS'):
        e[c] = pd.to_numeric(e[c], errors='coerce')
    e['prc_Estado'] = pd.to_numeric(e['prc_Estado'], errors='coerce').fillna(0)
    # El Estado llega bien, en UTF-8 y con sus tildes. Se pasa tal cual.
    e['Estado'] = e['Estado'].astype(str).str.strip()
    # Un predial puede traer varias construcciones. Se ordena por area
    # descendente para quedarse con la principal, que es la que el modelo
    # liquida; sin esto mandaria el orden del archivo.
    e = (e.sort_values('ACONCONS', ascending=False)
          .drop_duplicates('LLAVE').set_index('LLAVE'))
    print(f"Escenario '{esc}' ({grupo}): {os.path.basename(rutas[0])}, "
          f"{len(e):,} prediales "
          f"({int(e['prc_Estado'].gt(0).sum()):,} castigados)")
    _escenarios[(esc, grupo)] = e
    return e


def _llave_predio(serie):
    """
    ID_PREDIO comparable entre archivos.

    Los parquet de escenario lo traen como float64 -919337.0- y el pipeline
    como texto -'919337'-. Sin normalizar, el cruce da 0% y parece que el
    identificador cambio entre vigencias, cuando lo que cambia es el tipo.
    Medido bien, ID_PREDIO cruza el 99,9%; el que si cambio de verdad es
    ID_CONSTRUCCION, que cruza 0,0%.
    """
    return (pd.to_numeric(serie, errors='coerce')
              .astype('Int64').astype(str).str.strip())


_construccion_vigencia = {}


def construccion_de_grupo(grupo):
    """
    Las variables de construccion de la vigencia de esa familia, por predial.

    Solo la familia 2024 cambia de tabla: sus escenarios de sismo estan
    calculados sobre export_construccion_2025, asi que su liquidacion base
    tiene que salir de ahi tambien. La 2025 se queda con el export de hoy.
    """
    if grupo != '2024':
        return None
    if grupo in _construccion_vigencia:
        return _construccion_vigencia[grupo]
    try:
        c = pd.read_csv(RUTA_CONSTRUCCION_2025, sep='|', decimal=',',
                        encoding='ISO-8859-1', low_memory=False,
                        usecols=['ID_PREDIO'] + COLUMNAS_CONSTRUCCION_2025)
    except Exception as e:
        print(f"No se pudo leer {RUTA_CONSTRUCCION_2025}: {e}")
        _construccion_vigencia[grupo] = None
        return None
    c['LLAVE'] = _llave_predio(c['ID_PREDIO'])
    for col in COLUMNAS_CONSTRUCCION_2025:
        c[col] = pd.to_numeric(c[col], errors='coerce')
    c = (c.sort_values('ACONCONS', ascending=False)
          .drop_duplicates('LLAVE').set_index('LLAVE'))
    print(f"Construcciones de la familia {grupo}: "
          f"{os.path.basename(RUTA_CONSTRUCCION_2025)}, {len(c):,} prediales")
    _construccion_vigencia[grupo] = c
    return c


COLUMNAS_IDENTIFICACION = [
    'GRUPO_MODELO', 'MODELO_USADO', 'COMUNA', 'ID_PREDIO',
    'NUMERO_PREDIAL_NACIONAL', 'ID_CONSTRUCCION', 'USO_LADM', 'DESTINOCONS',
    'CONDICION', 'ESTRPRED', 'NUM_CONST_PREDIO',
    # --- con que se predijo ---
    'ZHF_MODELO', 'ZHF', 'VALOR_M2_SUELO', 'PUNTCONS', 'ACONCONS',
    'AREA_CONST', 'ARECPRED', 'ANOCONST', 'TPISCONS', 'NUM_CONST_TERR',
    'LATITUDE', 'LONGITUDE',
    # --- lo que liquida, sin sismo ---
    'VM2_COM_LIQ', 'VM2_CAT_LIQ', 'VALORCONS_COM_LIQ', 'VALORCONS_CAT_LIQ',
    'COINCIDE',
    'VIGENCIA_REF', 'VM2_CAT_REF',
]

# ANALISIS 1 - la bandera de comuna. Solo 2024.
COLUMNAS_AFECTADOS_MODELOS = [
    'AFECTADOS_MODELOS', 'DEFECTO_VIGENTE_HOY', 'BANDERAS_DEL_MODELO',
    'VM2_CAT_CON_DEFECTO', 'VM2_CAT_CORRECTO', 'DIF_VM2_CAT_BANDERA',
    # --- como esta contra como debe ser ---
    'VM2_COM_REF', 'VM2_COM_CORRECTO', 'DIF_VM2_COM', 'SENTIDO_BANDERA',
    'DIF_VM2_CAT', 'DIF_VALORCONS', 'DIF_AVALUO', 'DIF_PCT',
    'RANGO_DIF_VM2', 'RANGO_DIF_VALORCONS', 'RANGO_DIF_AVALUO',
]

# ANALISIS 2 - el sismo. En las dos. Las columnas por escenario se agregan
# detras, en el orden bajo -> moderado -> alto.
COLUMNAS_AFECTADOS_SISMO = ['AFECTADOS_SISMO', 'ESTADO_SISMO']


def columnas_por_escenario(esc):
    E = esc.upper()
    return [f'PRC_{E}', f'PUNTCONS_{E}', f'VM2_COM_{E}',
            f'VALORCONS_COM_{E}', f'DIF_VALORCONS_{E}']


# El diccionario de la hoja: una linea por columna, en el mismo orden en que
# van en MODELOS. Corto a proposito - aqui va QUE ES cada columna, no por que
# se decidio asi; eso vive en los comentarios de este archivo.
DESCRIPCION_COLUMNA = {
    'GRUPO_MODELO': 'Actualizacion: 2024 o 2025.',
    'MODELO_USADO': 'Modelo que puso el valor.',
    'COMUNA': 'Comuna del predio.',
    'ID_PREDIO': 'Identificador del predio.',
    'NUMERO_PREDIAL_NACIONAL': 'Predial nacional.',
    'ID_CONSTRUCCION': 'Identificador de la construccion.',
    'USO_LADM': 'Uso homologado.',
    'DESTINOCONS': 'Destino de la construccion.',
    'CONDICION': 'Condicion de propiedad. 9 = propiedad horizontal.',
    'ESTRPRED': 'Estrato del predio.',
    'NUM_CONST_PREDIO': 'Construcciones del predio.',
    'ZHF_MODELO': 'Zona homogenea que leyo el modelo.',
    'ZHF': 'Zona homogenea de la vigencia 2027.',
    'VALOR_M2_SUELO': 'Valor del m2 de suelo.',
    'PUNTCONS': 'Puntaje de la construccion, sin sismo.',
    'ACONCONS': 'Area construida de la construccion.',
    'AREA_CONST': 'Area con la que se liquida.',
    'ARECPRED': 'Area construida del predio.',
    'ANOCONST': 'Ano de construccion.',
    'TPISCONS': 'Total de pisos.',
    'NUM_CONST_TERR': 'Construcciones del terreno matriz.',
    'LATITUDE': 'Latitud.',
    'LONGITUDE': 'Longitud.',
    'BANDERAS_DEL_MODELO': 'Banderas de comuna que lee el modelo.',
    'VM2_COM_LIQ': 'Valor comercial del m2 liquidado.',
    'VM2_CAT_LIQ': 'Valor catastral del m2 liquidado. Base de los escenarios.',
    'VALORCONS_COM_LIQ': 'Valor comercial de la construccion liquidado. Base de los escenarios.',
    'VALORCONS_CAT_LIQ': 'Valor catastral de la construccion liquidado.',
    'COINCIDE': 'Si lo liquidado reproduce el avaluo de referencia.',
    'VIGENCIA_REF': 'Vigencia de referencia.',
    'VM2_CAT_REF': 'Valor catastral del m2 registrado hoy.',
    'AFECTADOS_MODELOS': 'Si el avaluo registrado salio con la bandera de comuna mal.',
    'DEFECTO_VIGENTE_HOY': 'Si ese defecto sigue en el avaluo de hoy.',
    'VM2_CAT_CON_DEFECTO': 'Valor del m2 con la bandera mal.',
    'VM2_CAT_CORRECTO': 'Valor del m2 con la bandera bien.',
    'DIF_VM2_CAT_BANDERA': 'Cuanto mueve la bandera, por m2.',
    'VM2_COM_REF': 'Valor comercial del m2 como esta registrado.',
    'VM2_COM_CORRECTO': 'Valor comercial del m2 como debe ser.',
    'DIF_VM2_COM': 'Diferencia del m2 comercial: como esta menos como debe ser.',
    'SENTIDO_BANDERA': 'Si al corregir la bandera el valor BAJA o SUBE.',
    'DIF_VM2_CAT': 'Diferencia del m2 catastral.',
    'DIF_VALORCONS': 'Diferencia en el valor de la construccion.',
    'DIF_AVALUO': 'Diferencia en el avaluo del predio.',
    'DIF_PCT': 'El exceso en porcentaje, sobre lo que deberia valer.',
    'RANGO_DIF_VM2': 'Rango de la diferencia por m2.',
    'RANGO_DIF_VALORCONS': 'Rango de la diferencia en la construccion.',
    'RANGO_DIF_AVALUO': 'Rango de la diferencia en el avaluo.',
    'AFECTADOS_SISMO': 'Si el sismo le castiga el puntaje.',
    'ESTADO_SISMO': 'Estado de afectacion.',
}

DESCRIPCION_ESCENARIO = {
    'PRC': 'Castigo al puntaje en el escenario {esc}.',
    'PUNTCONS': 'Puntaje castigado del escenario {esc}.',
    'VM2_COM': 'Valor comercial del m2 en el escenario {esc}.',
    'VALORCONS_COM': 'Valor comercial de la construccion en el escenario {esc}.',
    'DIF_VALORCONS': 'Diferencia comercial del escenario {esc} contra la base.',
}


def diccionario_de(columnas):
    """Una fila por columna de la hoja, en su mismo orden."""
    filas = []
    for c in columnas:
        texto = DESCRIPCION_COLUMNA.get(c)
        if texto is None:
            for base, plantilla in DESCRIPCION_ESCENARIO.items():
                hallado = next((e for e in ESCENARIOS_INFORME
                                if c == f'{base}_{e.upper()}'), None)
                if hallado:
                    texto = plantilla.format(esc=hallado)
                    break
        filas.append((c, texto or ''))
    return pd.DataFrame(filas, columns=['VARIABLE', 'DESCRIPCION'])


def _universo_informe(df_const, comunas, num_const=None):
    """
    Las construcciones de esas comunas que van por modelo, en predios de UNA
    sola construccion.

    El corte de una construccion no es cosmetico: con dos o mas, el m2
    integral del predio -AVALPRED/ARECPRED, que es la referencia contra la que
    se compara- mezcla todas, y ni el exceso de la bandera ni el efecto del
    sismo se pueden atribuir a esta fila. Deja fuera 909 construcciones de
    2024 y 134 de 2025.
    """
    d = df_const.copy()
    d['COMUNA'] = d['COMUNA'].astype(str).str.zfill(2)
    d['DESTINOCONS'] = d['DESTINOCONS'].astype(str).str.strip().str.zfill(3)
    condicion = pd.to_numeric(d['CONDICION'], errors='coerce')
    especial = (pd.to_numeric(d['ESPECIAL'], errors='coerce').fillna(0)
                if 'ESPECIAL' in d.columns else pd.Series(0, index=d.index))
    m = (d['COMUNA'].isin(comunas)
         & d['DESTINOCONS'].isin(DESTINOS_MODELO_2025)
         & (condicion == 9)
         & (especial <= 0))
    if num_const is not None:
        npn = d['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
        una = npn.map(num_const) == 1
        print(f"🏠 predios de mas de una construccion fuera: "
              f"{int((m & ~una).sum()):,}")
        m = m & una
    d = d[m].copy()
    d['TABLA_ORIGEN'] = 'MODELO'
    return d


def _construccion_de_vigencia(sub, grupo):
    """
    Cambia las variables de construccion por las de la vigencia de la familia.

    Va aqui y no dentro de ejecutar_modelos porque despues, escenario por
    escenario, solo hay que volver a pisar PUNTCONS: la base ya quedo sobre la
    tabla correcta.
    """
    c = construccion_de_grupo(grupo)
    if c is None:
        print(f"Construcciones de la familia {grupo}: las del pipeline")
        return sub
    sub = sub.copy()
    npn = _llave_predio(sub['ID_PREDIO'])
    for col in COLUMNAS_CONSTRUCCION_2025:
        if col not in sub.columns:
            continue
        nuevo = pd.to_numeric(npn.map(c[col]), errors='coerce')
        viejo = pd.to_numeric(sub[col], errors='coerce')
        cambian = int((nuevo.notna() & viejo.notna()
                       & (nuevo.round(2) != viejo.round(2))).sum())
        sub[col] = nuevo.fillna(viejo)
        print(f"🏗️ {col} desde la tabla de construcciones de {grupo}: "
              f"{int(nuevo.notna().sum()):,} de {len(sub):,} "
              f"({cambian:,} cambian de valor, "
              f"{int(nuevo.isna().sum()):,} se quedan con la del pipeline)")
    # AREA_CONST sale del ACONCONS: hay que rehacerla o el valor liquidado
    # quedaria multiplicado por el area de otra vigencia.
    if 'AREA_CONST' in sub.columns:
        acon = pd.to_numeric(sub['ACONCONS'], errors='coerce')
        sub['AREA_CONST'] = acon.where(
            acon > 0, pd.to_numeric(sub['AREA_CONST'], errors='coerce'))
    return sub


def _corre_familia(sub, grupo):
    """ejecutar_modelos forzando la familia y su export."""
    global MODO_INFORME
    MODO_INFORME = grupo
    try:
        return ejecutar_modelos(sub)
    finally:
        MODO_INFORME = None


def _liquida_escenarios(sub, grupo):
    """
    La liquidacion de los tres escenarios de sismo, por ID_CONSTRUCCION.

    Se vuelve a correr el modelo entero con el PUNTCONS castigado de cada
    escenario. No hay atajo: PUNTCONS entra a los arboles, no multiplica al
    final, asi que castigar el valor liquidado en vez del puntaje daria otra
    cosa.

    Las de Colapso quedan con PUNTCONS = 0 y ejecutar_modelos las descarta -no
    predice sin puntaje-. Vuelven mas abajo con valor CERO, que es lo que vale
    una construccion colapsada, en vez de desaparecer de la hoja.
    """
    salida = {}
    for esc in ESCENARIOS_INFORME:
        marca = escenario_sismo(esc, grupo)
        if marca is None:
            continue
        s = sub.copy()
        npn = _llave_predio(s['ID_PREDIO'])
        castigado = pd.to_numeric(npn.map(marca['PUNTCONS']), errors='coerce')
        s['PUNTCONS'] = castigado.fillna(
            pd.to_numeric(s['PUNTCONS'], errors='coerce'))
        print("\n" + "-" * 70)
        print(f"ESCENARIO '{esc}' - familia {grupo} - "
              f"{int(pd.to_numeric(npn.map(marca['prc_Estado']), errors='coerce').gt(0).sum()):,} "
              f"construcciones con el puntaje castigado")
        print("-" * 70)
        r = _corre_familia(s, grupo)
        if r is None or r.empty:
            continue
        r = r.assign(_ID=r['ID_CONSTRUCCION'].astype(str).str.strip())
        salida[esc] = (r.drop_duplicates('_ID').set_index('_ID')['VM2_MOD'])
    return salida


def _arma_hoja(grupo, comunas, df_const, num_const):
    """El frame de una familia: liquidacion base, banderas y los escenarios."""
    sub = _universo_informe(df_const, comunas, num_const)
    print("\n" + "=" * 70)
    print(f"FAMILIA {grupo} - comunas {', '.join(comunas)} - "
          f"{len(sub):,} construcciones")
    print("=" * 70)
    if sub.empty:
        return None
    sub = _construccion_de_vigencia(sub, grupo)
    d = _corre_familia(sub, grupo)
    if d is None or d.empty:
        return None
    escenarios = _liquida_escenarios(sub, grupo)

    factor = 0.7                       # catastral = comercial x 0.7

    def num(c):
        return (pd.to_numeric(d[c], errors='coerce') if c in d.columns
                else pd.Series(np.nan, index=d.index))

    d['VM2_COM_LIQ'] = num('VM2_MOD')
    d['VM2_CAT_LIQ'] = d['VM2_COM_LIQ'] * factor
    area = num('AREA_CONST')
    d['VALORCONS_COM_LIQ'] = area * d['VM2_COM_LIQ']
    d['VALORCONS_CAT_LIQ'] = area * d['VM2_CAT_LIQ']

    # ---- la referencia: el avaluo que la vigencia de esa familia dejo -----
    es24 = grupo == '2024'
    npn = d['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
    d['VIGENCIA_REF'] = '2025' if es24 else '2026'
    d['VM2_CAT_REF'] = pd.to_numeric(
        npn.map(vigencia_2025() if es24 else vigencia_2026()), errors='coerce')
    d['NUM_CONST_PREDIO'] = npn.map(num_const)

    TOL = 1_000                        # mil pesos por m2 es ruido de redondeo
    d['COINCIDE'] = np.where(
        d['VM2_CAT_REF'].isna(), 'SIN REFERENCIA',
        np.where((d['VM2_CAT_LIQ'] - d['VM2_CAT_REF']).abs() <= TOL,
                 'SI', 'NO'))

    # ---- ANALISIS 1: la bandera de comuna (solo 2024) --------------------
    if es24:
        d['VM2_CAT_CON_DEFECTO'] = num('VM2_BANDERA_CERO') * factor
        d['VM2_CAT_CORRECTO'] = num('VM2_BANDERA_OK') * factor
        d['DIF_VM2_CAT_BANDERA'] = (d['VM2_CAT_CON_DEFECTO']
                                    - d['VM2_CAT_CORRECTO'])
        mueve = d['DIF_VM2_CAT_BANDERA'].abs() > 1
        rep_cero = (d['VM2_CAT_CON_DEFECTO'] - d['VM2_CAT_REF']).abs() <= TOL
        rep_ok = (d['VM2_CAT_CORRECTO'] - d['VM2_CAT_REF']).abs() <= TOL
        d['AFECTADOS_MODELOS'] = np.select(
            [d['VM2_CAT_CORRECTO'].isna(), ~mueve, d['VM2_CAT_REF'].isna(),
             rep_cero & ~rep_ok, rep_ok],
            ['sin prediccion',
             'no distingue (la bandera no le cambia el valor)',
             'sin referencia', 'SI - salio con el defecto', 'NO - salio bien'],
            default='no corresponde a ninguna')
        afectado = d['AFECTADOS_MODELOS'] == 'SI - salio con el defecto'
        # Las comunas que se REACTUALIZARON en 2025 entraron al ejercicio de
        # 2024 y por eso aparecen aqui, pero su avaluo de 2026 no salio de
        # indexar el de 2025 sino de una valoracion nueva: alli el defecto
        # quedo atras, reemplazado.
        d['DEFECTO_VIGENTE_HOY'] = np.where(
            ~afectado, '',
            np.where(d['COMUNA'].astype(str).isin(COMUNAS_ACTUALIZACION_2025),
                     'no - la comuna se reactualizo en 2025',
                     'si - sigue dentro del avaluo de hoy'))
        # Como esta contra como debe ser. Se calcula en TODAS las filas que
        # tengan avaluo registrado, no solo en los afectados: asi los rangos y
        # el sentido cubren la base entera y el corte se hace con el filtro de
        # AFECTADOS_MODELOS, que es para lo que esta esa columna.
        d['VM2_COM_REF'] = d['VM2_CAT_REF'] / factor
        d['VM2_COM_CORRECTO'] = d['VM2_CAT_CORRECTO'] / factor
        d['DIF_VM2_COM'] = d['VM2_COM_REF'] - d['VM2_COM_CORRECTO']
        d['DIF_VM2_CAT'] = d['VM2_CAT_REF'] - d['VM2_CAT_CORRECTO']
        d['DIF_VALORCONS'] = d['DIF_VM2_CAT'] * area
        # El avaluo del predio solo se puede atribuir a esta fila porque el
        # universo son predios de UNA construccion.
        d['DIF_AVALUO'] = d['DIF_VM2_CAT'] * num('ARECPRED')
        # El exceso en porcentaje, sobre lo que el predio DEBERIA valer. Sale
        # uno solo para los tres niveles: el m2, la construccion y el avaluo
        # se multiplican todos por la misma area, asi que la proporcion no
        # cambia. Positivo = esta por encima de lo correcto.
        d['DIF_PCT'] = (d['DIF_VM2_CAT']
                        / d['VM2_CAT_CORRECTO'].replace(0, np.nan) * 100)
        # En el sentido de la CORRECCION, que es como se lee el archivo:
        # BAJA = lo registrado esta por encima de lo correcto y al corregir
        # baja; SUBE = al reves. En una palabra, para poder filtrar.
        d['SENTIDO_BANDERA'] = np.select(
            [d['DIF_VM2_CAT'].isna(), d['DIF_VM2_CAT'].abs() <= 1,
             d['DIF_VM2_CAT'] > 0],
            ['SIN REFERENCIA', 'IGUAL', 'BAJA'], default='SUBE')
        for col, base, cortes, etiq in (
                ('RANGO_DIF_VM2', 'DIF_VM2_CAT', CORTES_M2, ETIQ_M2),
                ('RANGO_DIF_VALORCONS', 'DIF_VALORCONS', CORTES_VALOR, ETIQ_VALOR),
                ('RANGO_DIF_AVALUO', 'DIF_AVALUO', CORTES_VALOR, ETIQ_VALOR)):
            d[col] = pd.cut(d[base].abs(), bins=cortes, labels=etiq,
                            include_lowest=True).astype(str)
            d.loc[d[base].isna(), col] = ''

    # ---- ANALISIS 2: el sismo -------------------------------------------
    # Los archivos de escenario se cruzan por ID_PREDIO, como el resto del
    # proyecto. Ojo con normalizarlo: ver _llave_predio.
    npn_d = _llave_predio(d['ID_PREDIO'])
    # Esta si es interna: indexa lo que devolvio nuestra propia corrida.
    ids = d['ID_CONSTRUCCION'].astype(str).str.strip()
    marca = escenario_sismo(ESCENARIOS_INFORME[0], grupo)
    if marca is not None:
        d['ESTADO_SISMO'] = npn_d.map(marca['Estado'])
        prc_ref = pd.to_numeric(npn_d.map(marca['prc_Estado']),
                                errors='coerce')
        d['AFECTADOS_SISMO'] = np.where(
            prc_ref.isna(), 'sin dato del ejercicio',
            np.where(prc_ref > 0, 'SI - el sismo le castiga el puntaje',
                     'NO - sin afectacion'))
    for esc in ESCENARIOS_INFORME:
        marca = escenario_sismo(esc, grupo)
        E = esc.upper()
        if marca is None:
            continue
        prc = pd.to_numeric(npn_d.map(marca['prc_Estado']), errors='coerce')
        d[f'PRC_{E}'] = prc
        d[f'PUNTCONS_{E}'] = pd.to_numeric(npn_d.map(marca['PUNTCONS']),
                                           errors='coerce')
        # El bloque de escenarios va en COMERCIAL, que es lo que sale del
        # modelo tal cual. Nada de multiplicar por 0.7 y volver a dividir: ese
        # ida y vuelta dejaba los ceros exactos en +-1e-06 y 14.603
        # construcciones SIN dano salian contadas como que pierden valor.
        vm2 = pd.to_numeric(ids.map(escenarios.get(esc, pd.Series(dtype=float))),
                            errors='coerce')
        # Colapso: el modelo no predice sin puntaje y la fila se cae de esa
        # corrida. Vale cero, no vacio.
        vm2 = vm2.where(~(prc >= 1), 0.0)
        d[f'VM2_COM_{E}'] = vm2
        d[f'VALORCONS_COM_{E}'] = vm2 * area
        d[f'DIF_VALORCONS_{E}'] = (d[f'VALORCONS_COM_{E}']
                                   - d['VALORCONS_COM_LIQ'])
    return d


def _con_total(t):
    """
    Le agrega la fila TOTAL a una tabla del resumen.

    Solo se suman los conteos y los pesos. Las medianas y los porcentajes no se
    suman: el porcentaje se recalcula sobre los totales y la mediana queda
    vacia, que es lo honesto -la mediana de las medianas no es nada-.
    """
    fila = {}
    for c in t.columns:
        if t[c].dtype.kind in 'fi' and 'MEDIANA' not in c and 'PCT' not in c:
            fila[c] = t[c].sum()
        elif t[c].dtype.kind in 'fi':
            fila[c] = np.nan
        else:
            fila[c] = ''
    fila[t.columns[0]] = 'TOTAL'
    if {'AFECTADAS', 'CONSTRUCCIONES'} <= set(t.columns) and 'PCT_AFECTADAS' in t.columns:
        fila['PCT_AFECTADAS'] = (fila['AFECTADAS'] / fila['CONSTRUCCIONES'] * 100
                                 if fila['CONSTRUCCIONES'] else np.nan)
    if {'AFECTADAS_MODELO', 'CONSTRUCCIONES'} <= set(t.columns) and 'PCT_AFECTADAS' in t.columns:
        fila['PCT_AFECTADAS'] = (fila['AFECTADAS_MODELO'] / fila['CONSTRUCCIONES'] * 100
                                 if fila['CONSTRUCCIONES'] else np.nan)
    return pd.concat([t, pd.DataFrame([fila])], ignore_index=True)


def _escribe(d, grupo, ruta):
    """Un Excel: MODELOS, RESUMEN, CRUCE_MARCAS (solo 2024) y DICCIONARIO."""
    orden = list(COLUMNAS_IDENTIFICACION)
    if grupo == '2024':
        orden += COLUMNAS_AFECTADOS_MODELOS
    orden += COLUMNAS_AFECTADOS_SISMO
    for esc in ESCENARIOS_INFORME:
        orden += columnas_por_escenario(esc)
    cols = [c for c in orden if c in d.columns]
    faltan = [c for c in orden if c not in d.columns]
    if faltan:
        print(f"   (a la hoja {grupo} le faltan columnas: {faltan})")
    hoja = d[cols].sort_values(['MODELO_USADO', 'COMUNA', 'ID_PREDIO'],
                               kind='stable')

    agg = {'CONSTRUCCIONES': ('ID_PREDIO', 'size'),
           'PREDIOS': ('ID_PREDIO', 'nunique'),
           'VALORCONS_CAT_LIQ': ('VALORCONS_CAT_LIQ', 'sum')}
    if grupo == '2024':
        hoja = hoja.assign(_AFM=(hoja['AFECTADOS_MODELOS']
                                 == 'SI - salio con el defecto').astype(int))
        hoja['_DIF_AF'] = hoja['DIF_AVALUO'].where(hoja['_AFM'] == 1)
        agg['AFECTADAS_MODELO'] = ('_AFM', 'sum')
        agg['DIF_AVALUO_AFECTADOS'] = ('_DIF_AF', 'sum')
    hoja = hoja.assign(_AFS=(hoja['AFECTADOS_SISMO']
                             == 'SI - el sismo le castiga el puntaje').astype(int))
    agg['AFECTADAS_SISMO'] = ('_AFS', 'sum')
    for esc in ESCENARIOS_INFORME:
        agg[f'DIF_VALORCONS_{esc.upper()}'] = (f'DIF_VALORCONS_{esc.upper()}',
                                               'sum')
    resumen = hoja.groupby(['MODELO_USADO', 'COMUNA'], dropna=False).agg(
        **agg).reset_index()
    # El cruce de las dos marcas. Es lo que la hoja plana no deja ver: las que
    # estan en los DOS analisis son donde las correcciones se pisan, y van en
    # direcciones contrarias.
    cruce = None
    if grupo == '2024':
        c = hoja.copy()
        c['BANDERA'] = np.where(c['_AFM'] == 1, 'bandera SI', 'bandera no')
        c['SISMO'] = np.where(c['_AFS'] == 1, 'sismo SI', 'sismo no')
        agg_c = {'CONSTRUCCIONES': ('ID_PREDIO', 'size'),
                 'DIF_AVALUO_AFECTADOS': ('_DIF_AF', 'sum')}
        for esc in ESCENARIOS_INFORME:
            agg_c[f'DIF_VALORCONS_{esc.upper()}'] = (
                f'DIF_VALORCONS_{esc.upper()}', 'sum')
        cruce = (c.groupby(['BANDERA', 'SISMO'], dropna=False)
                  .agg(**agg_c).reset_index())
    # Cuantas suben y cuantas bajan. Va como bloque propio porque es la
    # primera pregunta que se hace al abrir el archivo, y dentro de las tablas
    # de rangos queda repartida en cinco filas.
    sentido = None
    if grupo == '2024':
        sentido = (hoja.groupby('SENTIDO_BANDERA', dropna=False)
                       .agg(CONSTRUCCIONES=('ID_PREDIO', 'size'),
                            AFECTADAS=('_AFM', 'sum'),
                            DIF_VM2_CAT_MEDIANA=('DIF_VM2_CAT', 'median'),
                            DIF_PCT_MEDIANA=('DIF_PCT', 'median'),
                            DIF_VALORCONS=('DIF_VALORCONS', 'sum'),
                            DIF_AVALUO=('DIF_AVALUO', 'sum'))
                       .reset_index()
                       .sort_values('CONSTRUCCIONES', ascending=False))

    # Rangos de la diferencia que deja la bandera, abiertos por sentido. Es la
    # lectura que la hoja plana no da: cuantas suben, cuantas bajan y de que
    # tamano es la diferencia en cada nivel.
    rangos = {}
    if grupo == '2024':
        for nombre, col, rcol, etiq in (
                ('RANGOS_VM2', 'DIF_VM2_CAT', 'RANGO_DIF_VM2', ETIQ_M2),
                ('RANGOS_VALORCONS', 'DIF_VALORCONS', 'RANGO_DIF_VALORCONS',
                 ETIQ_VALOR),
                ('RANGOS_AVALUO', 'DIF_AVALUO', 'RANGO_DIF_AVALUO',
                 ETIQ_VALOR)):
            g = hoja[hoja[rcol].astype(str) != ''].copy()
            # El rango tiene que ordenarse por su corte, no alfabeticamente, o
            # "100 a 150" sale antes que "50 a 100".
            g[rcol] = pd.Categorical(g[rcol], categories=etiq, ordered=True)
            agg_r = {'CONSTRUCCIONES': ('ID_PREDIO', 'size'),
                     'AFECTADAS': ('_AFM', 'sum'),
                     'MEDIANA': (col, 'median')}
            # Sumar pesos por m2 entre construcciones no significa nada; en
            # construccion y avaluo si, que son pesos.
            if nombre != 'RANGOS_VM2':
                agg_r['SUMA'] = (col, 'sum')
            t = (g.groupby([rcol, 'SENTIDO_BANDERA'], dropna=False,
                           observed=True)
                  .agg(**agg_r).reset_index()
                  .sort_values([rcol, 'SENTIDO_BANDERA']))
            rangos[nombre] = t
    hoja = hoja.drop(columns=[c for c in ('_AFM', '_AFS', '_DIF_AF')
                              if c in hoja.columns])

    os.makedirs(os.path.dirname(ruta) or '.', exist_ok=True)
    if os.path.exists(ruta):
        try:
            with open(ruta, 'a+b'):
                pass
        except PermissionError:
            print(f"No se pudo sobrescribir '{os.path.basename(ruta)}': "
                  f"esta abierto en Excel. Cierrelo y vuelva a correr.")
            return None

    # Todo lo agregado va en UNA hoja RESUMEN, un bloque debajo del otro con su
    # titulo. Antes eran cuatro hojas y obligaba a saltar entre pestanas para
    # leer un mismo analisis.
    bloques = [('POR MODELO Y COMUNA', resumen)]
    if cruce is not None:
        bloques.append(('LAS DOS MARCAS CRUZADAS', cruce))
    if sentido is not None:
        bloques.append(('CUANTAS SUBEN Y CUANTAS BAJAN', sentido))
    bloques += [('DIFERENCIA POR M2 - RANGOS', rangos[k]) if k == 'RANGOS_VM2'
                else ('DIFERENCIA EN LA CONSTRUCCION - RANGOS', rangos[k])
                if k == 'RANGOS_VALORCONS'
                else ('DIFERENCIA EN EL AVALUO - RANGOS', rangos[k])
                for k in rangos]

    with pd.ExcelWriter(ruta, engine='xlsxwriter') as xls:
        hoja.to_excel(xls, sheet_name='MODELOS', index=False)
        fila = 0
        posiciones = []
        for titulo, t in bloques:
            t = _con_total(t)
            t.to_excel(xls, sheet_name='RESUMEN', index=False,
                       startrow=fila + 1)
            posiciones.append((titulo, t, fila))
            fila += len(t) + 4
        diccionario_de(cols).to_excel(xls, sheet_name='DICCIONARIO',
                                      index=False)
        libro = xls.book
        miles = libro.add_format({'num_format': '#,##0'})
        pct = libro.add_format({'num_format': '0.0%'})
        cabecera = libro.add_format({'bold': True, 'bg_color': '#DDEBF7',
                                     'border': 1, 'text_wrap': True,
                                     'valign': 'vcenter'})
        titulo_fmt = libro.add_format({'bold': True, 'font_size': 12})
        # Las dos columnas de marca van resaltadas: son el punto de entrada de
        # cada analisis y con 60 columnas se pierden de vista.
        marca = libro.add_format({'bold': True, 'bg_color': '#FFF2CC',
                                  'border': 1, 'text_wrap': True,
                                  'valign': 'vcenter'})
        h = xls.sheets['MODELOS']
        h.freeze_panes(1, 0)
        h.autofilter(0, 0, len(hoja), len(hoja.columns) - 1)
        for i, c in enumerate(hoja.columns):
            h.write(0, i, c, marca if c.startswith('AFECTADOS_') else cabecera)
            if c.startswith('PRC_'):
                fmt, ancho = pct, 12
            elif hoja[c].dtype.kind in 'fi':
                fmt, ancho = miles, 16
            else:
                fmt, ancho = None, max(12, min(34, len(c) + 4))
            h.set_column(i, i, ancho, fmt)

        h = xls.sheets['RESUMEN']
        # El ancho se decide una sola vez por columna, mirando TODOS los
        # bloques: un mismo indice de columna lleva la etiqueta de una tabla y
        # los miles de millones de otra. Y el formato se fija en la misma
        # llamada que el ancho -si se vuelve a fijar el ancho despues, se
        # pierde el formato y Excel escribe 1,39468E+11-.
        anchos, numerica = {}, {}
        for titulo, t, r0 in posiciones:
            h.write(r0, 0, titulo, titulo_fmt)
            for i, c in enumerate(t.columns):
                h.write(r0 + 1, i, c, cabecera)
                es_num = t[c].dtype.kind in 'fi'
                numerica[i] = numerica.get(i, False) or es_num
                if es_num:
                    # Lo que ocupa el numero mas grande ya con separadores de
                    # miles, mas el signo.
                    v = pd.to_numeric(t[c], errors='coerce').abs().max()
                    largo = len(f"{v:,.0f}") + 3 if pd.notna(v) else 12
                else:
                    largo = max([len(str(x)) for x in t[c]] or [0]) + 2
                anchos[i] = max(anchos.get(i, 12), largo, len(str(c)) + 3)
        for i, a in anchos.items():
            h.set_column(i, i, min(a, 46), miles if numerica[i] else None)

        h = xls.sheets['DICCIONARIO']
        h.set_column(0, 0, 30)
        h.set_column(1, 1, 100)

    try:
        hoja.to_parquet(os.path.splitext(ruta)[0] + '.parquet', index=False)
    except Exception as e:
        print(f"   (no se pudo escribir el parquet de {grupo}: {e})")
    print(f"\n>>> {ruta}  ({len(hoja):,} construcciones, "
          f"{hoja['ID_PREDIO'].nunique():,} predios, {len(cols)} columnas)")
    return ruta


def hoja_modelos(fecha=None, df_const=None, carpeta='./results'):
    """
    Los dos Excel: uno por actualizacion, con sus analisis de afectados.
    """
    from datetime import datetime

    if df_const is None:
        print(f"Leyendo {RUTA_CONSTRUCCIONES}")
        df_const = pd.read_parquet(RUTA_CONSTRUCCIONES)
    if 'COMUNA' not in df_const.columns:
        df_const['COMUNA'] = (df_const['NUMERO_PREDIAL_NACIONAL']
                              .astype(str).str[9:11])
    # Cuantas construcciones tiene cada predio: sin eso el comparativo en pesos
    # del avaluo no se puede atribuir a una sola fila.
    num_const = (df_const['NUMERO_PREDIAL_NACIONAL'].astype(str).str.strip()
                 .value_counts())

    fecha = fecha or datetime.now().strftime('%Y%m%d')
    salidas = []
    for grupo, comunas in (('2024', COMUNAS_ACTUALIZACION_2024),
                           ('2025', COMUNAS_ACTUALIZACION_2025)):
        d = _arma_hoja(grupo, comunas, df_const, num_const)
        if d is None:
            continue
        print("\n" + "=" * 70)
        print(f"FAMILIA {grupo}: MARCAS")
        print("=" * 70)
        for col in ('AFECTADOS_MODELOS', 'AFECTADOS_SISMO'):
            if col not in d.columns:
                continue
            print(f" {col}")
            for k, v in d[col].value_counts().items():
                print(f"   {k}: {v:,} ({v / len(d) * 100:.1f}%)")
        if 'EXCESO_AVALUO' in d.columns:
            _a = d['AFECTADOS_MODELOS'] == 'SI - salio con el defecto'
            print(f"   de mas en avaluo por la bandera: "
                  f"{d.loc[_a, 'EXCESO_AVALUO'].sum():,.0f}")
        for esc in ESCENARIOS_INFORME:
            c = f'DIF_VALORCONS_{esc.upper()}'
            if c in d.columns:
                print(f"   sismo '{esc}': {d[c].sum():,.0f} en construccion "
                      f"({d[c].lt(0).sum():,} construcciones pierden valor)")
        salidas.append(_escribe(
            d, grupo, os.path.join(carpeta,
                                   f'MODELOS_{grupo}_{fecha}.xlsx')))
    return salidas


if __name__ == '__main__':
    hoja_modelos()
