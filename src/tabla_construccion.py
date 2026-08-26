
import pandas as pd
import numpy as np
import os
import glob
import re
from io import StringIO
import gc
from datetime import datetime

from Homologacion import aplicar_homologacion, cruce_uso_ladm, homologar_rural
from pre_inconsistencias import generar_reporte_inconsistencias
from uso_principal import uso_principal_const


# =====================================================================
# ALCANCE URBANO: que comunas entran a la liquidacion
# =====================================================================
# Cali tiene 22 comunas urbanas y hasta ahora se liquidan 17. Las cinco que
# faltan -05, 06, 13, 16 y 18- se descartan aqui mismo, antes de armar las
# construcciones, asi que no llegan a ninguna etapa posterior: en el parquet
# de salida no hay ni una sola fila de ellas.
#
# Para incluirlas hay que hacer DOS cosas, y este interruptor hace las dos:
#   1. dejar de filtrarlas en este archivo, y
#   2. meterlas en un grupo de las tablas de valor, porque si entran pero no
#      pertenecen a ningun grupo el merge no les encuentra valor y se quedan
#      con VM2 = 0, que es como no haber entrado.
#
#     INCLUIR_COMUNAS_FALTANTES = True   -> entran, y se liquidan leyendo las
#                                           columnas *_10C_* de las tablas
#     INCLUIR_COMUNAS_FALTANTES = False  -> como estaba: quedan fuera
#
# Es una sola linea para prender y apagar. Liquidacion_tablas.py lee de aqui
# los dos grupos, asi que no hay una segunda lista que se pueda desincronizar.
#
# OJO: meterlas en el grupo de 10 es una DECISION, no algo que salga de los
# datos. Significa cobrarles con los valores que se calcularon para las otras
# diez comunas. Si mas adelante les hacen tabla propia, se agrega una columna
# *_5C_* al Excel de tablas y estas cinco pasan a un grupo nuevo.
INCLUIR_COMUNAS_FALTANTES = True

COMUNAS_FALTANTES = ["05", "06", "13", "16", "18"]

# Las que NO entran al proceso (se usa en los dos filtros de este archivo).
COMUNAS_EXCLUIDAS = [] if INCLUIR_COMUNAS_FALTANTES else list(COMUNAS_FALTANTES)

# Grupos con que se leen las tablas de valor (los usa Liquidacion_tablas.py).
COMUNAS_7 = ['02', '03', '04', '08', '17', '19', '22']
COMUNAS_10 = (['01', '07', '09', '10', '11', '12', '14', '15', '20', '21']
              + (COMUNAS_FALTANTES if INCLUIR_COMUNAS_FALTANTES else []))

def convertir_a_float(df, columnas):
    for col in columnas:
        if col in df.columns:
            df[col] = (
                df[col]
                  .astype(str)
                  .astype(float)
            )
        else:
            print(f"⚠️ La columna '{col}' no existe en el DataFrame")
    return df


def convertir_a_int(df, columnas):
    for columna in columnas:

        print(f"\n--- {columna} ---")
        print("dtype:", df[columna].dtype)

        valores_no_numericos = df[
            pd.to_numeric(df[columna], errors='coerce').isna()
        ][columna].unique()

        print("Cantidad no numéricos:", len(valores_no_numericos))
        print("Ejemplos:", valores_no_numericos[:20])

        df[columna] = (
            pd.to_numeric(df[columna], errors='coerce')
            .fillna(0)
            .round(0)
            .astype(int)
        )

    return df

def convertir_a_string(df, columnas):
    for columna in columnas:
        try:
            df[columna] = df[columna].astype(str)
        except ValueError as e:
            print(f"Error al convertir la columna '{columna}' a string: {e}")
    return df

def convertir_a_cero(df, columnas):
    for columna in columnas:
        try:
            df[columna] = df[columna].fillna(0)
        except Exception as e:
            print(f"Error en la columna '{columna}': {e}")
    return df


import glob
import re
import pandas as pd


def leer_archivo(path, sep="|", decimal="."):
    extension = os.path.splitext(path)[1].lower()

    if extension == ".parquet":
        return pd.read_parquet(path)

    elif extension in [".txt", ".csv"]:
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
            f"No se pudo leer el archivo {path} con las codificaciones probadas."
        )

    else:
        raise ValueError(f"Formato no soportado: {extension}")
import glob
import re
from pathlib import Path
import glob
import os
import re

def procesar_construcciones(base_path=None):
    """
    Carga los archivos de predios y construcciones desde la carpeta input.
    Si no se especifica base_path, utiliza automáticamente la carpeta
    input ubicada en la raíz del proyecto.
    """

    if base_path is None:
        base_path = Path(__file__).resolve().parent.parent / "input" / "export_liq"
    else:
        base_path = Path(base_path)

    # Los nombres cambian de una entrega a otra: unas traen
    # "export_construccion_homologado" y "export_anexos_homologado", otras
    # "construccion_convencional" y "construccion_no_convencional". Los
    # patrones cubren las dos formas.
    #
    # ORDEN IMPORTANTE: no_conv va primero y su archivo se descarta de los
    # candidatos a conv. "convencional" tambien casa con "no_convencional" y
    # "construccion" casa con los dos, asi que sin esto 'conv' se quedaba con
    # el archivo equivocado -y ordenando por nombre descendente le tocaba
    # justamente el no convencional- sin que nada avisara.
    file_patterns = {
        "predio": r"export_predio_zhf",
        "no_conv": r"no.?convencional|anexo",
        "conv": r"convencional|construccion",
    }

    dataframes = {k: None for k in file_patterns}

    print(f"📂 Buscando archivos en: {base_path}")

    files = (
        glob.glob(str(base_path / "*.txt")) +
        glob.glob(str(base_path / "*.parquet")) +
        glob.glob(str(base_path / "*.csv"))
    )

    print("📂 Archivos encontrados:")
    if files:
        for f in files:
            print(" -", os.path.basename(f))
    else:
        print("⚠️ No se encontraron archivos en la carpeta.")

    usados = set()
    for name, pattern in file_patterns.items():
        # Ordenado por nombre DESCENDENTE: los export de predio empiezan por la
        # fecha (20260804_, 20260728_), asi que el primero es el mas reciente.
        # Antes se tomaba matched_files[0] del glob, que iba en orden
        # ascendente y se habria quedado con la entrega vieja.
        matched_files = sorted(
            (f for f in files
             if re.search(pattern, os.path.basename(f), re.IGNORECASE)
             and f not in usados),
            key=lambda f: os.path.basename(f), reverse=True)
        if matched_files:
            usados.add(matched_files[0])

        if matched_files:
            try:
                dataframes[name] = leer_archivo(matched_files[0])
                print(f"✅ {name}: {os.path.basename(matched_files[0])}")
            except Exception as e:
                print(f"⚠️ Error leyendo {matched_files[0]}: {e}")
        else:
            print(f"⚠️ No se encontró archivo para '{name}'")

    # --- ZHF de la entrega anterior, pegada como ZHF_ANTERIOR ---------------
    # Sirve para ver que predios cambiaron de zona homogenea. Viene de
    # export_predio_<fecha>, que es OTRO archivo: el patron pide la fecha
    # pegada a "export_predio_" y por eso no casa con los
    # <fecha>_export_predio_zhf_<vigencia>, que son el predio principal.
    predios = sorted(
        (f for f in files
         if re.search(r"export_predio_\d{8}", os.path.basename(f), re.IGNORECASE)),
        key=lambda f: os.path.basename(f), reverse=True)
    if dataframes["predio"] is not None and predios:
        anterior = predios[0]
        try:
            prev = leer_archivo(anterior)[["ID_PREDIO", "ZHF"]].copy()
            prev = (prev.rename(columns={"ZHF": "ZHF_ANTERIOR"})
                        .drop_duplicates("ID_PREDIO"))
            dataframes["predio"] = dataframes["predio"].merge(
                prev, on="ID_PREDIO", how="left", validate="many_to_one")
            hay = dataframes["predio"]["ZHF_ANTERIOR"].notna().sum()
            print(f"✅ ZHF_ANTERIOR desde {os.path.basename(anterior)}: "
                  f"{hay:,} de {len(dataframes['predio']):,} predios la traen")
        except Exception as e:
            print(f"⚠️ No se pudo agregar ZHF_ANTERIOR desde "
                  f"{os.path.basename(anterior)}: {e}")
    elif dataframes["predio"] is not None:
        print("⚠️ No hay export_predio_<fecha>: no se agrega ZHF_ANTERIOR")

    for k, v in dataframes.items():
        print(f"📊 {k}: {'OK' if v is not None else 'None'}")

    return (
        dataframes["predio"],
        dataframes["conv"],
        dataframes["no_conv"]
    )
def renombrar_destinos(d):
    """
    Renombra el destino crudo a las columnas que espera Homologacion.

    DESTINOCONS -> DESTINOCONS_2025 y DESTANEX -> DESTANEX_2025. Las entregas
    llegan CRUDAS, sin homologar, porque la homologacion la hace
    Homologacion.py; USO_LADM tampoco viene, lo pone ese modulo al cruzar con
    su tabla de nombres.

    Existe como funcion y no como tres renames sueltos porque el reparto la
    llama tres veces: urbano_24, urbano_25 y rural.
    """
    return d.rename(columns={"DESTINOCONS": "DESTINOCONS_2025",
                             "DESTANEX": "DESTANEX_2025"})


def cruces_const_predio(df_predio, df_conv, df_noconv):


    print(f"Filas: {len(df_predio)}")
    print(f"Predios únicos: {df_predio['ID_PREDIO'].nunique()}")

    # Ver duplicados
    print(df_predio[df_predio.duplicated('ID_PREDIO', keep=False)].sort_values('ID_PREDIO'))

    # Eliminar duplicados (conserva el primero)
    df_predio = df_predio.drop_duplicates(subset='ID_PREDIO')

    # Contar nuevamente
    print(f"Filas: {len(df_predio)}")
    print(f"Predios únicos: {df_predio['ID_PREDIO'].nunique()}")

    df_conv.columns = df_conv.columns.str.strip()
    df_noconv.columns = df_noconv.columns.str.strip()
    df_predio.columns = df_predio.columns.str.strip()
    ### Transformar las variables 

    df_predio = convertir_a_cero(df_predio, ['AREAPRED','ACONANEX', 'ARECPRED','VTER','AVALPRED','VCONST','VANEXO','ESTRPRED','LATITUDE','LONGITUDE'])
    df_predio = convertir_a_float(df_predio, ['AREAPRED', 'ARECPRED','ACONANEX','VTER','AVALPRED','VCONST','VANEXO','LATITUDE','LONGITUDE'])
    df_predio = convertir_a_int(df_predio,['ESTRPRED','ZHF'])
    df_predio = convertir_a_string(df_predio,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL'])
    df_conv = convertir_a_string(df_conv,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL'])

    df_predio['ZHF'] = (
        pd.to_numeric(df_predio['ZHF'], errors='coerce')
        .fillna(0)
        .astype(int)
    )
    
    df_predio['CONDICION'] = df_predio['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(int)
    df_predio['COMUNA'] = df_predio['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
    df_predio = df_predio[~df_predio['COMUNA'].isin(COMUNAS_EXCLUIDAS)]
    print("Total de predios:", df_predio.shape)

           
    df_conv = df_conv[df_conv['ID_PREDIO'].notna()]
    df_noconv = df_noconv[df_noconv['ID_PREDIO'].notna()]


    df_conv['ID_TERR'] = df_conv['NUMERO_PREDIAL_NACIONAL'].astype(str).str[1:21]
    df_predio['ID_TERR'] = df_predio['NUMERO_PREDIAL_NACIONAL'].astype(str).str[1:21]
    
    df_conv['NUM_CONST_TERR'] = df_conv.groupby('ID_TERR')['ID_TERR'].transform('count')

    df_num_const = (
    df_conv[['ID_PREDIO','NUM_CONST_TERR']]
    .drop_duplicates(subset='ID_PREDIO', keep='first'))
    
    print(f"Convencionales: {df_conv.shape}, No convencionales: {df_noconv.shape}")
    
    df_predio['AREA_TERR'] = df_predio.groupby('ID_TERR')['ID_TERR'].transform('count')
    
    df_predio = pd.merge(df_predio,df_num_const, on='ID_PREDIO',how='left')
    df_predio = df_predio.rename(columns={'ACONANEX': 'ACONANEXT'})

    ####### 

    

    print("🚀 INICIO USO PRINCIPAL")
    df_conv['DESTINOCONS'] = (
    df_conv['DESTINOCONS']
    .astype(str)
    .str.strip()
    )

    df_conv['DESTINOCONS'] = pd.to_numeric(
        df_conv['DESTINOCONS'],
        errors='coerce'
    )

    df_predio_usop = uso_principal_const(df_predio, df_conv)
    

    print("✅ TERMINÓ USO PRINCIPAL")
    print(f'✅ LAS VARIABLES CON USO P {df_predio_usop.dtypes}')
    print("➡️ SIGUE DESPUÉS DE USO PRINCIPAL")
    print(f'✅ CAMBIAN DE TIPOUSO {df_predio_usop['CAMBIA_TIPOUSO'].value_counts()}')
    print(f'✅ CAMBIAN DE TIPOPRED {df_predio_usop['CAMBIA_TIPOPRED'].value_counts()}')


####


    # # Columnas que quieres revisar
    # cols = [
    #     'ID_PREDIO',
    #     'CAT_USO',
    #     'IPU',
    #     'DESTINOCONS',
    #     'CONDICION',
    #     'TIPOPRED',
    #     'TIPOUSO',
    #     'TIPOUSO_AJUSTADO',
    #     'CAMBIA_TIPOUSO'
    # ]

    # # Cantidad de categorías
    # n_cat = df_predio_usop['TIPOUSO_AJUSTADO'].nunique(dropna=False)
    # print(f"Categorías de TIPOUSO_AJUSTADO: {n_cat}")

    # # Aproximadamente 1000 registros repartidos entre las categorías
    # n_por_grupo = max(1, 1000 // n_cat)

    # muestra = (
    #     df_predio_usop
    #     .groupby('TIPOUSO_AJUSTADO', dropna=False, group_keys=False)
    #     .apply(lambda x: x.sample(min(len(x), n_por_grupo), random_state=42))
    # )

    # print(muestra['TIPOUSO_AJUSTADO'].value_counts())

    # muestra[cols].to_excel(
    #     r"C:\Users\USUARIO\Desktop\CATASTRO 2026\TRABAJO\LIQUIDACION\LIQUIDACION\muestra_tipouso_ajustado.xlsx",
    #     index=False
    # )

    # print(f"Registros exportados: {len(muestra)}")


####
    ##Borrar destinocons
    df_predio_usop.drop(columns='DESTINOCONS', inplace=True)

    ## Unifica las construcciones convencionaales y  no convencionales
    df_const = pd.concat([df_conv, df_noconv], ignore_index=True)
    

    
    if 'NUMERO_PREDIAL_NACIONAL' in df_const.columns:
        df_const.drop(columns=['NUMERO_PREDIAL_NACIONAL'], inplace=True)
        print("✅ NUMERO_PREDIAL_NACIONAL eliminada")
    else:
        print("ℹ️ NUMERO_PREDIAL_NACIONAL no existe en df_const")
        
    df_const = df_const.merge(
        df_predio[['ID_PREDIO', 'VIGEPRED','NUMERO_PREDIAL_NACIONAL']],
        on='ID_PREDIO',
        how='left'
    )
    print("Antes:", len(df_const))

    df_const = df_const.dropna(subset=['NUMERO_PREDIAL_NACIONAL']).copy()

    print("Después filtro comunas:", len(df_const))
   
    print("NPN nulos construcciones :", df_const['NUMERO_PREDIAL_NACIONAL'].isna().sum())
    df_const.drop(columns=['COMUNA'], errors='ignore', inplace=True)
    df_const['COMUNA'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
    
    print("Antes:", len(df_const))

  

    df_const = df_const[
        df_const['COMUNA'].notna() &
        ~df_const['COMUNA'].isin(COMUNAS_EXCLUIDAS)
    ]

    print("Después:", len(df_const))
    print(f"Convencionales: {df_conv.shape}, No convencionales: {df_noconv.shape}")


    print("Total de construcciones:", df_const.shape)
    
   
    if 'COMUNA' not in df_const.columns:
        df_const['COMUNA'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
    if 'CONDICION' not in df_const.columns:
        df_const['CONDICION'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(str)
        
    #Asegurar COMUNA como numérico para filtrar
   
    aconcons = pd.to_numeric(df_const['ACONCONS'], errors='coerce').fillna(0)
    aconanex = pd.to_numeric(df_const['ACONANEX'], errors='coerce').fillna(0)
    df_const['AREA_CONST'] = np.where(aconcons == 0, aconanex, aconcons)
    

    # ============================================================
    # SEPARAR URBANO Y RURAL
    # ============================================================
    df_const['COMUNA'] = pd.to_numeric(df_const['COMUNA'], errors='coerce')
    urbano = df_const[df_const['COMUNA'] <= 22].copy()
    rural = df_const[df_const['COMUNA'] > 22].copy()
    

    print(f'✅ Construcciones zona urbana: {urbano.shape}')
    print(f'✅ Construcciones zona rural: {rural.shape}')

    # ============================================================
    # HOMOLOGACIÓN URBANO - SEPARAR POR AÑO DE ACTUALIZACIÓN
    # ============================================================
    urbano['COMUNA'] = (
    urbano['COMUNA']
    .astype('Int64')   # conserva los NaN
    .astype(str)
    .str.zfill(2)
    )
    
    # Las comunas de la actualizacion 2024 son COMUNAS_7, arriba en este mismo
    # archivo. Antes habia una segunda lista identica declarada aqui: dos copias
    # del mismo dato es como se desincronizan.
    actualizacion_2025 = ['01','03','09','10','11','12','22']

    # EL CORTE ES SOLO POR COMUNA:
    #   comuna actualizada    -> ya viene homologada, solo se le pone USO_LADM
    #   comuna sin actualizar -> hay que traducirle el destino
    #
    # Antes se exigia ademas VIGEPRED == '2026-01-01 00:00:00'. Esa igualdad
    # exacta sobre texto excluia a los predios de vigencia 2027 -los MAS
    # actualizados, no los menos- y les traducia un destino que ya estaba en la
    # codificacion nueva: aplicar_homologacion mapea 3->12 y 5->13, asi que
    # salian con el destino equivocado. Y siendo texto, bastaba con que un
    # export trajera la fecha sin la hora para que la condicion fuera falsa en
    # todas las filas y se retradujeran las 436.000 construcciones de estas
    # comunas sin que nada avisara.
    #
    # Cortar solo por comuna cuesta 3 predios: el 121852 y el 122303 de la
    # comuna 09, que traen destino 114 de la codificacion vieja, y el 305368 de
    # la 12. No se liquidan mal, se descartan: cruce_uso_ladm solo procesa
    # convencionales de destino 1 a 76 y anexos por encima de 76, asi que lo que
    # no encaja se cae y queda contado en "descartadas (no 1-76 ni anexo>76)",
    # que pasa de 6 a 10 construcciones.
    #
    # Las comunas 03 y 22 estan en las dos actualizaciones; la union las deja
    # una sola vez.
    COMUNAS_ACTUALIZADAS = sorted(set(COMUNAS_7) | set(actualizacion_2025))

    urbano_24 = urbano[urbano['COMUNA'].isin(COMUNAS_ACTUALIZADAS)].copy()
    urbano_25 = urbano.drop(urbano_24.index).copy()

    print("Total urbano:", len(urbano))
    print("Urbano 2024:", len(urbano_24))
    print("Urbano 2025:", len(urbano_25))
    print("Suma:", len(urbano_24) + len(urbano_25))
    # ============================================================
    # PREPARAR COLUMNAS PARA HOMOLOGACIÓN
    # ============================================================
    
    # Extraer CONDICION del predial nacional (para 2025 y rural)
    urbano_25['CONDICION'] = urbano_25['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(str)
    
    # Renombrar para las funciones de homologación
    urbano_24 = renombrar_destinos(urbano_24)
    urbano_25 = renombrar_destinos(urbano_25)
    
    cols = ['DESTANEX_2025', 'DESTINOCONS_2025']

    for df in [urbano_24, urbano_25]:
        df[cols] = (
            df[cols]
            .apply(pd.to_numeric, errors='coerce')
            .astype('Int64')
        )
    
    # Convertir a numérico
    urbano_24['DESTINOCONS_2025'] = pd.to_numeric(urbano_24['DESTINOCONS_2025'], errors='coerce')
    urbano_24['DESTANEX_2025'] = pd.to_numeric(urbano_24['DESTANEX_2025'], errors='coerce')
    urbano_25['DESTINOCONS_2025'] = pd.to_numeric(urbano_25['DESTINOCONS_2025'], errors='coerce')
    urbano_25['DESTANEX_2025'] = pd.to_numeric(urbano_25['DESTANEX_2025'], errors='coerce')

    # ============================================================
    # PREPARAR COLUMNAS PARA HOMOLOGACIÓN
    # ============================================================

    # Extraer CONDICION del predial nacional (para 2025 y rural)
    urbano_25['CONDICION'] = urbano_25['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(str)

    # Renombrar para las funciones de homologación
    urbano_24 = renombrar_destinos(urbano_24)
    urbano_25 = renombrar_destinos(urbano_25)


    # Convertir a numérico
    urbano_24['DESTINOCONS_2025'] = pd.to_numeric(urbano_24['DESTINOCONS_2025'], errors='coerce')
    urbano_24['DESTANEX_2025'] = pd.to_numeric(urbano_24['DESTANEX_2025'], errors='coerce')
    urbano_25['DESTINOCONS_2025'] = pd.to_numeric(urbano_25['DESTINOCONS_2025'], errors='coerce')
    urbano_25['DESTANEX_2025'] = pd.to_numeric(urbano_25['DESTANEX_2025'], errors='coerce')
    

    # ============================================================
    # APLICAR HOMOLOGACIÓN URBANO
    # ============================================================

    # 2025: usa aplicar_homologacion() con np.select y condiciones complejas
    if len(urbano_25) > 0:
        urbano_25 = aplicar_homologacion(urbano_25)
        print(f"✅ Homologación 2025 aplicada: {len(urbano_25)} registros")

    # 2024: usa cruce_uso_ladm() con merge directo a tablas LADM
    if len(urbano_24) > 0:
        urbano_24 = cruce_uso_ladm(urbano_24)
        print(f"✅ Homologación 2024 aplicada: {len(urbano_24)} registros")

    # Unir urbano homologado
    urbano = pd.concat([urbano_25, urbano_24], ignore_index=True, join='outer')

    # ============================================================
    # RURAL: HOMOLOGACIÓN LADM
    # ============================================================

    if len(rural) > 0:
        # Preparar columnas rural igual que urbano
        rural = renombrar_destinos(rural)
        rural['DESTINOCONS_2025'] = pd.to_numeric(rural['DESTINOCONS_2025'], errors='coerce')
        rural['DESTANEX_2025'] = pd.to_numeric(rural['DESTANEX_2025'], errors='coerce')
        rural['CONDICION'] = rural['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(str)
            

        
        # Aplicar homologación rural
        rural = homologar_rural(rural)
        print(f"✅ Homologación rural aplicada: {len(rural)} registros")

    # ============================================================
    # UNIR URBANO Y RURAL
    # ============================================================

    # Asegurar mismas columnas antes del concat
    all_cols = set(urbano.columns) | set(rural.columns)
    for col in all_cols:
        if col not in urbano.columns:
            urbano[col] = np.nan
        if col not in rural.columns:
            rural[col] = np.nan

    # Alinear tipos de columnas comunes
    for col in urbano.columns:
        if col in rural.columns and urbano[col].dtype != rural[col].dtype:
            if urbano[col].dtype == 'object' or rural[col].dtype == 'object':
                urbano[col] = urbano[col].astype(str).replace('nan', np.nan)
                rural[col] = rural[col].astype(str).replace('nan', np.nan)
            elif urbano[col].dtype in ['int64', 'float64'] and rural[col].dtype in ['int64', 'float64']:
                urbano[col] = urbano[col].astype(float)
                rural[col] = rural[col].astype(float)

    df_const = pd.concat([urbano, rural], ignore_index=True)

    print(f"✅ Total después de homologación: {len(df_const)}")
    print(f"✅ Columnas disponibles: {list(df_const.columns)}")

    # Asegurar COMUNA y CONDICION existan y sean string limpio
    if 'COMUNA' not in df_const.columns:
        df_const['COMUNA'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[9:11]
    df_const['COMUNA'] = df_const['COMUNA'].fillna('00').astype(str)

    if 'CONDICION' not in df_const.columns:
        df_const['CONDICION'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[21:22]
    df_const['CONDICION'] = df_const['CONDICION'].fillna('0').astype(str)

    df_const = df_const.drop(columns='NUM_CONST_TERR') ### Aqui se elimina para luego cruzarla

    df_const = convertir_a_cero(df_const,['PUNTCONS', 'ACONCONS', 'TPISCONS', 'ANOCONST', 'ACONANEX', 'TIPOANEXO'])
    df_const = convertir_a_float(df_const, ['ACONCONS', 'ACONANEX'])
    df_const = convertir_a_int(df_const, ['PUNTCONS', 'TIPOANEXO','ANOCONST','TPISCONS'])
    df_predio_usop = convertir_a_string(df_predio_usop,['ID_PREDIO'])

   
    df_predio_usop = convertir_a_cero(df_predio_usop, ['AREAPRED','ACONANEXT', 'ARECPRED','VTER','AVALPRED','VCONST','VANEXO','ESTRPRED','LATITUDE','LONGITUDE'])
    df_predio_usop = convertir_a_float(df_predio_usop, ['AREAPRED', 'ARECPRED','ACONANEXT','VTER','AVALPRED','VCONST','VANEXO','LATITUDE','LONGITUDE'])
    df_predio_usop = convertir_a_int(df_predio_usop,['ESTRPRED','NUM_CONST_TERR','CONDICION'])
    df_predio_usop = convertir_a_string(df_predio_usop,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL','COMUNA'])

    df_predio_usop['INFORMALIDAD'] = np.where(
        ((df_predio_usop['CONDICION'] == 5) & 
         (df_predio_usop["NUMERO_PREDIAL_NACIONAL"].astype(str).str[-1] != "1")) | 
        (df_predio_usop['CONDICION'] == 2),
        1, 0
    ).astype(int)

    df_const['AREA_CONST'] = np.where(df_const['ACONCONS']==0, df_const['ACONANEX'], df_const['ACONCONS'])


    df_const = convertir_a_cero(df_const,['PUNTCONS', 'ACONCONS', 'VALORCONS', 'TPISCONS', 'ANOCONST','DESTINOCONS','DESTANEX', 'TIPOANEXO','ACONANEX', 'VALOANEX','AREA_CONST'])
    df_const = convertir_a_float(df_const, ['ACONCONS', 'VALORCONS', 'VALOANEX','AREA_CONST'])
    df_const = convertir_a_int(df_const, ['PUNTCONS', 'ANOCONST','TPISCONS','DESTINOCONS','TIPOANEXO','DESTANEX'])
    df_const = convertir_a_string(df_const,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL'])
    df_const.drop(columns='NUMERO_PREDIAL_NACIONAL', inplace=True)
    
    # Merge construccion y predio
    df_const_predio = pd.merge(df_const, df_predio_usop, on='ID_PREDIO', how='left')

    print(f'✅ REVISION CRUCE ENTRE CONSTRUCCION Y PREDIO {len(df_const)-len(df_const_predio)}')

    # 🔎 DIAGNÓSTICO DEL CRUCE (por qué -2 y por qué se recrea COMUNA)
    _dups = df_predio_usop['ID_PREDIO'].duplicated(keep=False)
    print(f"🔎 ID_PREDIO duplicados en df_predio_usop: {int(_dups.sum())} filas "
          f"/ {df_predio_usop.loc[_dups, 'ID_PREDIO'].nunique()} predios")
    if _dups.any():
        print(df_predio_usop.loc[_dups, ['ID_PREDIO', 'NUMERO_PREDIAL_NACIONAL', 'COMUNA']]
              .sort_values('ID_PREDIO').head(20).to_string())
    # ¿Colisionaron las COMUNA en el merge?
    print(f"🔎 Columnas COMUNA tras merge: {[c for c in df_const_predio.columns if c.startswith('COMUNA')]}")
    # Construcciones que NO cruzaron con predio (NPN del lado predio queda NaN)
    if 'NUMERO_PREDIAL_NACIONAL' in df_const_predio.columns:
        _sin_predio = df_const_predio['NUMERO_PREDIAL_NACIONAL'].isna().sum()
        print(f"🔎 Construcciones sin predio en el cruce (NPN NaN → COMUNA='nan'): {int(_sin_predio)}")

    # ⚠️ RECREAR COMUNA SI SE PERDIÓ EN EL MERGE
    if 'COMUNA' not in df_const_predio.columns:
        df_const_predio['COMUNA'] = df_const_predio['NUMERO_PREDIAL_NACIONAL'].str[9:11].astype(str)
        print("⚠️ COMUNA recreada en df_const_predio después del merge")
    
    # Asegurar que CONDICION también exista
    if 'CONDICION' not in df_const_predio.columns:
        df_const_predio['CONDICION'] = df_const_predio['NUMERO_PREDIAL_NACIONAL'].str[21:22].astype(str)


    #### Aplicar formatos

    df_const_predio = convertir_a_cero(df_const_predio,['PUNTCONS', 'ACONCONS', 'VALORCONS', 'TPISCONS', 'ANOCONST','DESTINOCONS','DESTANEX', 'TIPOANEXO', 'VALOANEX','AREA_CONST','VTER','VCONST','VANEXO','AVALPRED','AREAPRED','ARECPRED','ACONANEXT'])
    df_const_predio = convertir_a_float(df_const_predio, ['ACONCONS', 'VALORCONS', 'VALOANEX','AREA_CONST','ACONANEX','AREAPRED','ARECPRED','ACONANEXT'])
    df_const_predio = convertir_a_int(df_const_predio, ['ANOCONST'])
    df_const_predio = convertir_a_string(df_const_predio,['ID_PREDIO','NUMERO_PREDIAL_NACIONAL','COMUNA'])

    
    

    # print(df_predio_final['ESPECIAL'].unique())
    # ============================================================
    # CONTINUAR CON EL PROCESAMIENTO (AHORA CON DATOS LIMPIOS)
    # ============================================================
    
    ### Ordenar los convencionales
    df_conv_ord = df_const_predio[df_const_predio['DESTINOCONS'] > 0].copy()

    print(f'✅construcciones convencionales {df_conv_ord.shape}')

    df_conv_ord = df_conv_ord.sort_values(
        ['DESTINOCONS', 'AREA_CONST', 'PUNTCONS'],
        ascending=[True, False, False]
    )

    df_conv_ord['CONSECUTIVO'] = df_conv_ord.groupby('ID_PREDIO').cumcount() + 1

    ### Ordenar los no convecionales

    df_noconv_ord = df_const_predio[df_const_predio['DESTINOCONS'] == 0].copy()
    print(f'✅construcciones  NO convencionales {df_noconv_ord.shape}')

    df_noconv_ord = df_noconv_ord.sort_values(
        ['DESTANEX', 'AREA_CONST', 'TIPOANEXO'],
        ascending=[True, False, False]
    )

    df_noconv_ord['CONSECUTIVO'] = df_noconv_ord.groupby('ID_PREDIO').cumcount() + 1

    del df_const_predio
    gc.collect()

    df_const_predio = pd.concat([df_conv_ord, df_noconv_ord], ignore_index=True)

    
    df_const_predio['CONSTRUCCION_ID'] = (
    df_const_predio['ID_PREDIO'].astype(str) +
    df_const_predio['CONSECUTIVO'].astype(str) +
    df_const_predio.apply(
        lambda x: (
            str(int(x['DESTINOCONS'])) if pd.notna(x['DESTINOCONS']) and x['DESTINOCONS'] > 0
            else str(int(x['DESTANEX'])) if pd.notna(x['DESTANEX']) and x['DESTANEX'] > 0
            else ""
        ),
        axis=1
    )
    )

   
    df_const_predio.to_parquet("./output/todas_las_construcciones.parquet")
    del df_predio_usop, df_const, df_conv, df_noconv
    gc.collect()

    # Activado: genera el reporte y devuelve la base SIN los predios
    # inconsistentes, que es lo pedido -no se liquidan hasta que los ajusten-.
    # Con los criterios de hoy son ~64.000 predios, el 8.8%. Para volver a
    # correr sin descontar, comente la primera linea y descomente la segunda.
    df_const_predio_clean = generar_reporte_inconsistencias(df_const_predio)
    # df_const_predio_clean = df_const_predio.copy()

    print(f'PREDIOS DESCONTADOS POR INCONSISTENCIAS {df_const_predio['ID_PREDIO'].nunique()-df_const_predio_clean['ID_PREDIO'].nunique()}')


    return df_const_predio_clean

    