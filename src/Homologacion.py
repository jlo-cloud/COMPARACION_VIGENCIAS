import pandas as pd
import numpy as np
from io import StringIO


def aplicar_homologacion(df):
    """
    Procesa construcciones de 2025 (comunas 01, 09, 10, 11, 12)
    Input: DESTINOCONS_2025, DESTANEX_2025
    Output: DESTINOCONS, DESTANEX, USO_LADM
    """

    # ✅ CONDICION llega como STRING desde tabla_construccion (.astype(str)). Las condiciones de
    #    abajo comparan contra enteros (== 9, isin([8,9])); sin esta conversión fallan en silencio
    #    y mandan a "sin homologar" a todos los códigos que dependen de la condición (PH 8/9).
    df['CONDICION'] = pd.to_numeric(df['CONDICION'], errors='coerce').fillna(0).astype(int)

    df_conv = df[df['DESTINOCONS_2025'] > 0].copy()
    df_no_conv = df[df['DESTANEX_2025'] > 0].copy()

    print(f"AL MOMENTO DE HOMOLOGAR {df_no_conv['DESTANEX_2025'].value_counts()}")

    print(f"AL MOMENTO DE HOMOLOGAR {df_conv['DESTINOCONS_2025'].value_counts()}")

    ########## Nombres usos modelo LADM - CONVENCIONALES
    conv = '''DESTINOCONS\tUSO_LADM
    1\tApartamentos_4_y_mas_pisos_en_PH
    3\tApartamentos_4_y_mas_pisos
    4\tBarracas
    5\tCasa_Elbas
    6\tDepositos_Lockers
    7\tGarajes_Cubiertos
    8\tGarajes_En_PH
    9\tSalon_Comunal
    10\tSecadero_Ropa
    11\tVivienda_Colonial
    2\tVivienda_Colonial_en_PH
    12\tVivienda_Hasta_3_Pisos
    13\tVivienda_Hasta_3_Pisos_En_PH
    14\tVivienda_Recreacional
    15\tVivienda_Recreacional_En_PH
    16\tBodegas_Comerciales_Grandes_Almacenes
    17\tBodegas_Comerciales
    18\tBodegas_Comerciales_en_PH
    19\tCentros_Comerciales_pequenios
    20\tCentros_Comerciales_grandes
    21\tEstacion_de_servicio
    22\tCentros_Comerciales_en_PH_pequenios
    23\tCentros_Comerciales_en_PH_grandes
    24\tClubes_Casinos
    25\tComercio
    26\tComercio_Colonial
    27\tComercio_Deposito_Almacenamiento
    28\tComercio_en_PH
    29\tHotel_Colonial
    30\tHoteles
    31\tHoteles_en_PH
    32\tOficinas_Consultorios
    33\tOficinas_Consultorios_Coloniales
    34\tOficinas_Consultorios_en_PH
    35\tParque_Diversiones
    36\tParqueaderos
    37\tParqueaderos_en_PH
    38\tPensiones_y_Residencias
    39\tPlaza_Mercado
    40\tRestaurante_Colonial
    41\tRestaurantes
    42\tRestaurantes_en_PH
    43\tTeatro_Cinemas
    44\tTeatro_Cinemas_en_PH
    45\tBodega_Casa_Bomba
    46\tBodegas_Casa_Bomba_en_PH
    47\tIndustrias
    48\tIndustrias_en_PH
    49\tTalleres
    50\tAulas_de_Clases
    51\tBiblioteca
    52\tCarceles
    53\tCasas_de_Culto
    54\tClinicas_Hospitales_Centros_Medicos
    55\tColegio_y_Universidades
    56\tColiseos
    57\tEntidad_Educativa_Colonial_Colegio_Colonial
    58\tEstadios
    59\tFuertes_y_Castillos
    60\tIglesia
    61\tIglesia_en_PH
    62\tInstalaciones_Militares
    63\tJardin_Infantil_en_Casa
    64\tParque_Cementerio
    65\tPlanetario
    66\tPlaza_de_Toros
    67\tPuestos_de_Salud
    68\tMuseos
    69\tSeminarios_Conventos
    70\tTeatro
    71\tUnidad_Deportiva
    72\tVelodromo_Patinodromo
    73\tAdministrativos
    74\tFundaciones_y_ONG
    75\tEntidades_del_Socorro
    76\tEstaciones_y_CAI
    '''

    conv = pd.read_csv(StringIO(conv), sep='\t')
    conv['DESTINOCONS'] = conv['DESTINOCONS'].round(0).astype(int)


    ################## Usos no convencionales modelo LADM 
    no_conv = '''DESTANEX\tUSO_LADM
    77\tCanchas
    78\tCanchas_de_Tenis
    79\tCarretera
    80\tCerramiento
    81\tCimientos_Estructura_Muros_y_Placa_Base
    82\tCocheras_Marraneras_Porquerizas
    83\tConstruccion_en_Membrana_Arquitectonica
    84\tContenedor
    85\tCorrales
    86\tEstablos_Pesebreras
    87\tEstacion_Bombeo
    88\tEstacion_Sistema_Transporte
    89\tGalpones_Gallineros
    90\tGampling
    91\tHangar
    92\tKioscos
    93\tLagunas_de_Oxidacion
    94\tMarquesinas_Patios_Cubiertos
    95\tMuelles
    96\tMurallas
    97\tPergolas
    98\tPiscinas
    99\tPista_Aeropuerto
    100\tPozos
    101\tRamadas_Cobertizos_Caneyes
    102\tSecaderos
    103\tSilos
    104\tTanques
    105\tToboganes
    106\tTorre_de_Control
    107\tTorres_de_Enfriamiento
    108\tVia_Ferrea
    109\tCampo_de_Golf
    110\tCanopy
    111\tPatio_Encementado
    112\tPistas_de_Bolos
    113\tCanchas_Sinteticas_de_Futbol
    114\tColiseos
    115\tSaunas_y_Banos_Turcos
    116\tPista_de_Patinaje
    117\tPista_de_Atletismo
    118\tAlbercas_Banaderas
    119\tBeneficiaderos
    120\tCamaroneras
    '''
    
    no_conv = pd.read_csv(StringIO(no_conv), sep='\t')
    no_conv['DESTANEX'] = no_conv['DESTANEX'].round(0).astype(int)

    # Lista de valores para CONVENCIONALES
    USO = [1, 3, 6, 7, 8, 12, 13, 16, 19, 20, 21, 22, 23, 24, 25, 27, 28, 30, 31, 32, 34, 36, 37, 38, 47, 48, 50, 51, 54, 55, 60, 61, 64, 67, 71, 73]
    
    # Definir condiciones para CONVENCIONALES
    CONDICIONES_CONV = [
        (df_conv["DESTINOCONS_2025"].isin([1, 2]) & df_conv["CONDICION"].isin([9])),   #1 - 1
        (df_conv["DESTINOCONS_2025"].isin([4]) & ~(df_conv["CONDICION"].isin([8,9]))),    #2 - 3
        (df_conv["DESTINOCONS_2025"].isin([415])),  #3- 6
        (df_conv["DESTINOCONS_2025"].isin([411, 412]) & (~df_conv["CONDICION"].isin([8,9]))), #4- 7
        (df_conv["DESTINOCONS_2025"].isin([411, 412]) & (df_conv["CONDICION"].isin([8,9]))), #5- 8
        (df_conv["DESTINOCONS_2025"].isin([3]) & ~(df_conv["CONDICION"].isin([8,9]))), #6 - 12                                
        (df_conv["DESTINOCONS_2025"].isin([5]) & (df_conv["CONDICION"].isin([8,9]))), #7 - 13
        (df_conv["DESTINOCONS_2025"].isin([125])), #8 - 16
        (df_conv["DESTINOCONS_2025"].isin([118])),  #9 - 19
        (df_conv["DESTINOCONS_2025"].isin([120])), #10 - 20
        (df_conv["DESTINOCONS_2025"].isin([126])), #11 - 21                            
        (df_conv["DESTINOCONS_2025"].isin([117]) & (df_conv["CONDICION"].isin([9]))), #12 - 22
        (df_conv["DESTINOCONS_2025"].isin([119]) & (df_conv["CONDICION"].isin([9]))), #13 - 23                           
        (df_conv["DESTINOCONS_2025"].isin([321])), #14 - 24
        (df_conv["DESTINOCONS_2025"].isin([112, 114, 712])), #15 - 25
        (df_conv["DESTINOCONS_2025"].isin([416])), #16 - 27
        (df_conv["DESTINOCONS_2025"].isin([111, 113]) & (df_conv["CONDICION"].isin([8,9]))), #17 - 28
        (df_conv["DESTINOCONS_2025"].isin([122]) & ~(df_conv["CONDICION"].isin([8,9]))), #18 - 30                            
        (df_conv["DESTINOCONS_2025"].isin([121]) & (df_conv["CONDICION"] == 9)), #19 - 31
        (df_conv["DESTINOCONS_2025"].isin([116]) & ~(df_conv["CONDICION"].isin([8,9]))),  #20 - 32                            
        (df_conv["DESTINOCONS_2025"].isin([115]) & (df_conv["CONDICION"] == 9)), #21 - 34
        (df_conv["DESTINOCONS_2025"].isin([511, 713]) & ~(df_conv["CONDICION"].isin([8,9]))), #22 - 36                        
        (df_conv["DESTINOCONS_2025"].isin([413, 414]) & (df_conv["CONDICION"].isin([8,9]))),  #23 - 37
        (df_conv["DESTINOCONS_2025"].isin([123, 124])), #24 - 38
        (df_conv["DESTINOCONS_2025"].isin([212, 214]) & ~(df_conv["CONDICION"].isin([8,9]))), #25 - 47
        (df_conv["DESTINOCONS_2025"].isin([211, 213]) & (df_conv["CONDICION"].isin([8,9]))),  #26 - 48
        (df_conv["DESTINOCONS_2025"].isin([313])), #27 - 50                              
        (df_conv["DESTINOCONS_2025"].isin([314])), #28 - 51                             
        (df_conv["DESTINOCONS_2025"].isin([317])), #29 - 54                             
        (df_conv["DESTINOCONS_2025"].isin([311, 312])), #30 - 55                   
        (df_conv["DESTINOCONS_2025"].isin([315]) & (df_conv["CONDICION"] != 9)),  #31 - 60    
        (df_conv["DESTINOCONS_2025"].isin([315]) & (df_conv["CONDICION"] == 9)),  #32 - 61   
        (df_conv["DESTINOCONS_2025"].isin([611])),  #33 - 64                           
        (df_conv["DESTINOCONS_2025"].isin([318])), #34 - 67                             
        (df_conv["DESTINOCONS_2025"].isin([319, 320])), #35 - 71                        
        (df_conv["DESTINOCONS_2025"].isin([316])), #36 - 73
    ]

    # Asignar homologación a DESTINOCONS
    df_conv["DESTINOCONS"] = np.select(CONDICIONES_CONV, USO, default=0)
    
    # ⚠️ SEPARAR las que SÍ homologaron de las que NO
    df_conv_homologadas = df_conv[df_conv["DESTINOCONS"] > 0].copy()
    df_conv_sin_homologar = df_conv[df_conv["DESTINOCONS"] == 0].copy()
    

    # 🔎 DIAGNÓSTICO: por qué quedan sin homologar (códigos y condición más frecuentes)
    if len(df_conv_sin_homologar) > 0:
        print("   🔎 SIN HOMOLOGAR [URBANO 2025] · top DESTINOCONS_2025:")
        print(df_conv_sin_homologar['DESTINOCONS_2025'].value_counts(dropna=False).head(20).to_string())
        print("   🔎 SIN HOMOLOGAR [URBANO 2025] · top (DESTINOCONS_2025, CONDICION):")
        print(
            df_conv_sin_homologar
            .groupby(['DESTINOCONS_2025', 'CONDICION'], dropna=False)
            .size().sort_values(ascending=False).head(20).to_string()
        )
    print(f"Urbano Convencionales: {len(df_conv)} total, {len(df_conv_homologadas)} homologadas, {len(df_conv_sin_homologar)} sin homologar")

    # Merge solo las homologadas
    df_conv_homologadas = pd.merge(df_conv_homologadas, conv, on="DESTINOCONS", how="left")
    
    # if len(df_conv_sin_homologar) > 0:
    #     df_conv_sin_homologar["DESTANEX"] = df_no_conv_sin_homologar["DESTANEX_2025"]
    #     df_conv_sin_homologar["USO_LADM"] = "SIN_HOMOLOGAR"
    
    # Unir homologadas y sin homologar
    df_conv = pd.concat([df_conv_homologadas, df_conv_sin_homologar], ignore_index=True)


    # ### Homologación usos NO CONVENCIONALES
    USO_ANEX = [101, 89, 86, 82, 103, 98, 104, 119, 102, 100, 92, 118, 85, 107, 95, 78, 105, 94, 109, 110, 111, 112, 80, 113, 77, 114, 115, 81]

    CONDICIONES_ANEX = [
        (df_no_conv["DESTANEX_2025"].isin([2])), #1 - 101
        (df_no_conv["DESTANEX_2025"].isin([3])),  #2 - 89
        (df_no_conv["DESTANEX_2025"].isin([4])),    #3 - 86
        (df_no_conv["DESTANEX_2025"].isin([5])),  #4 - 82
        (df_no_conv["DESTANEX_2025"].isin([8])), #5 - 103
        (df_no_conv["DESTANEX_2025"].isin([9])), #6 - 98
        (df_no_conv["DESTANEX_2025"].isin([10])), #7 - 104
        (df_no_conv["DESTANEX_2025"].isin([11])), #8 - 119
        (df_no_conv["DESTANEX_2025"].isin([18])), #9 - 102
        (df_no_conv["DESTANEX_2025"].isin([20])), #10 - 100
        (df_no_conv["DESTANEX_2025"].isin([21])), #11 - 92
        (df_no_conv["DESTANEX_2025"].isin([23])), #12 - 118
        (df_no_conv["DESTANEX_2025"].isin([26])), #13 - 85
        (df_no_conv["DESTANEX_2025"].isin([47])), #14 - 107
        (df_no_conv["DESTANEX_2025"].isin([48])), #15 - 95
        (df_no_conv["DESTANEX_2025"].isin([60])), #16 - 78
        (df_no_conv["DESTANEX_2025"].isin([62])), #17 - 105
        (df_no_conv["DESTANEX_2025"].isin([82])), #18 - 94
        (df_no_conv["DESTANEX_2025"].isin([83])), #19 - 109
        (df_no_conv["DESTANEX_2025"].isin([84])), #20 - 110
        (df_no_conv["DESTANEX_2025"].isin([85])), #21 - 111
        (df_no_conv["DESTANEX_2025"].isin([86])), #22 - 112
        (df_no_conv["DESTANEX_2025"].isin([87])), #23 - 80
        (df_no_conv["DESTANEX_2025"].isin([88])), #24 - 113
        (df_no_conv["DESTANEX_2025"].isin([89])), #25 - 77
        (df_no_conv["DESTANEX_2025"].isin([90])), #26 - 114
        (df_no_conv["DESTANEX_2025"].isin([91])), #27 - 115
        (df_no_conv["DESTANEX_2025"].isin([92])), #28 - 81
    ]

    # Asignar homologación a DESTANEX
    df_no_conv["DESTANEX"] = np.select(CONDICIONES_ANEX, USO_ANEX, default=0)
    
    # ⚠️ SEPARAR las que SÍ homologaron de las que NO
    df_no_conv_homologadas = df_no_conv[df_no_conv["DESTANEX"] > 0].copy()
    df_no_conv_sin_homologar = df_no_conv[df_no_conv["DESTANEX"] == 0].copy()
    
    print(f"Urbano No convencionales: {len(df_no_conv)} total, {len(df_no_conv_homologadas)} homologadas, {len(df_no_conv_sin_homologar)} sin homologar")
    
    # Merge solo las homologadas
    df_no_conv_homologadas = pd.merge(df_no_conv_homologadas, no_conv, on="DESTANEX", how="left")
    
    # Para las sin homologar: mantener DESTANEX_2025 como DESTANEX (sin transformar)
    # if len(df_no_conv_sin_homologar) > 0:
    #     df_no_conv_sin_homologar["DESTANEX"] = df_no_conv_sin_homologar["DESTANEX_2025"]
    #     df_no_conv_sin_homologar["USO_LADM"] = "SIN_HOMOLOGAR"
    
    # Unir homologadas y sin homologar
    df_no_conv = pd.concat([df_no_conv_homologadas, df_no_conv_sin_homologar], ignore_index=True)

    # Asegurar que ambos DataFrames tengan las columnas necesarias
    if 'DESTANEX' not in df_conv.columns:
        df_conv['DESTANEX'] = 0
    if 'DESTINOCONS' not in df_no_conv.columns:
        df_no_conv['DESTINOCONS'] = 0

    print(f"Convencionales 2025: {df_conv.shape}, No convencionales 2025: {df_no_conv.shape}")

    # Concatenar construcciones convencionales y no convencionales
    df = pd.concat([df_conv, df_no_conv], ignore_index=True)

    return df


def cruce_uso_ladm(df):
    """
    Procesa construcciones de 2024 (comunas 02, 03, 04, 08, 17, 19, 22)
    Input: DESTINOCONS_2025, DESTANEX_2025
    Output: DESTINOCONS, DESTANEX, USO_LADM
    
    Lógica: 
    - Si DESTINOCONS_2025 <= 76 → buscar nombre en tabla convencionales
    - Si DESTANEX_2025 > 76 → buscar nombre en tabla no convencionales
    - GENERA columnas DESTINOCONS y DESTANEX a partir de las _2025
    """
    
    # Separar construcciones convencionales y no convencionales
    df_conv = df[(df['DESTINOCONS_2025'] > 0) & (df['DESTINOCONS_2025'] <= 76)].copy()
    df_no_conv = df[df['DESTANEX_2025'] > 76].copy()
    n_in = len(df)  # 🔎 para diagnóstico de descartadas [URBANO 2024]

    ########## Tabla de usos convencionales (1-76)
    conv = '''DESTINOCONS_2025\tUSO_LADM
    1\tApartamentos_4_y_mas_pisos_en_PH
    2\tVivienda_Colonial_en_PH
    3\tApartamentos_4_y_mas_pisos
    4\tBarracas
    5\tCasa_Elbas
    6\tDepositos_Lockers
    7\tGarajes_Cubiertos
    8\tGarajes_En_PH
    9\tSalon_Comunal
    10\tSecadero_Ropa
    11\tVivienda_Colonial
    12\tVivienda_Hasta_3_Pisos
    13\tVivienda_Hasta_3_Pisos_En_PH
    14\tVivienda_Recreacional
    15\tVivienda_Recreacional_En_PH
    16\tBodegas_Comerciales_Grandes_Almacenes
    17\tBodegas_Comerciales
    18\tBodegas_Comerciales_en_PH
    19\tCentros_Comerciales_pequenios
    20\tCentros_Comerciales_grandes
    21\tEstacion_de_servicio
    22\tCentros_Comerciales_en_PH_pequenios
    23\tCentros_Comerciales_en_PH_grandes
    24\tClubes_Casinos
    25\tComercio
    26\tComercio_Colonial
    27\tComercio_Deposito_Almacenamiento
    28\tComercio_en_PH
    29\tHotel_Colonial
    30\tHoteles
    31\tHoteles_en_PH
    32\tOficinas_Consultorios
    33\tOficinas_Consultorios_Coloniales
    34\tOficinas_Consultorios_en_PH
    35\tParque_Diversiones
    36\tParqueaderos
    37\tParqueaderos_en_PH
    38\tPensiones_y_Residencias
    39\tPlaza_Mercado
    40\tRestaurante_Colonial
    41\tRestaurantes
    42\tRestaurantes_en_PH
    43\tTeatro_Cinemas
    44\tTeatro_Cinemas_en_PH
    45\tBodega_Casa_Bomba
    46\tBodegas_Casa_Bomba_en_PH
    47\tIndustrias
    48\tIndustrias_en_PH
    49\tTalleres
    50\tAulas_de_Clases
    51\tBiblioteca
    52\tCarceles
    53\tCasas_de_Culto
    54\tClinicas_Hospitales_Centros_Medicos
    55\tColegio_y_Universidades
    56\tColiseos
    57\tEntidad_Educativa_Colonial_Colegio_Colonial
    58\tEstadios
    59\tFuertes_y_Castillos
    60\tIglesia
    61\tIglesia_en_PH
    62\tInstalaciones_Militares
    63\tJardin_Infantil_en_Casa
    64\tParque_Cementerio
    65\tPlanetario
    66\tPlaza_de_Toros
    67\tPuestos_de_Salud
    68\tMuseos
    69\tSeminarios_Conventos
    70\tTeatro
    71\tUnidad_Deportiva
    72\tVelodromo_Patinodromo
    73\tAdministrativos
    74\tFundaciones_y_ONG
    75\tEntidades_del_Socorro
    76\tEstaciones_y_CAI
    '''
    conv = pd.read_csv(StringIO(conv), sep='\t')
    conv['DESTINOCONS_2025'] = conv['DESTINOCONS_2025'].round(0).astype(int)
    
    ########## Tabla de usos no convencionales (77-120)
    no_conv = '''DESTANEX_2025\tUSO_LADM
    77\tCanchas
    78\tCanchas_de_Tenis
    79\tCarretera
    80\tCerramiento
    81\tCimientos_Estructura_Muros_y_Placa_Base
    82\tCocheras_Marraneras_Porquerizas
    83\tConstruccion_en_Membrana_Arquitectonica
    84\tContenedor
    85\tCorrales
    86\tEstablos_Pesebreras
    87\tEstacion_Bombeo
    88\tEstacion_Sistema_Transporte
    89\tGalpones_Gallineros
    90\tGampling
    91\tHangar
    92\tKioscos
    93\tLagunas_de_Oxidacion
    94\tMarquesinas_Patios_Cubiertos
    95\tMuelles
    96\tMurallas
    97\tPergolas
    98\tPiscinas
    99\tPista_Aeropuerto
    100\tPozos
    101\tRamadas_Cobertizos_Caneyes
    102\tSecaderos
    103\tSilos
    104\tTanques
    105\tToboganes
    106\tTorre_de_Control
    107\tTorres_de_Enfriamiento
    108\tVia_Ferrea
    109\tCampo_de_Golf
    110\tCanopy
    111\tPatio_Encementado
    112\tPistas_de_Bolos
    113\tCanchas_Sinteticas_de_Futbol
    114\tColiseos
    115\tSaunas_y_Banos_Turcos
    116\tPista_de_Patinaje
    117\tPista_de_Atletismo
    118\tAlbercas_Banaderas
    119\tBeneficiaderos
    120\tCamaroneras
    '''
    no_conv = pd.read_csv(StringIO(no_conv), sep='\t')
    no_conv['DESTANEX_2025'] = no_conv['DESTANEX_2025'].round(0).astype(int)
    
    # CLAVE: Crear columnas DESTINOCONS y DESTANEX a partir de _2025
    # Para convencionales: DESTINOCONS = DESTINOCONS_2025, DESTANEX = 0
    df_conv['DESTINOCONS'] = df_conv['DESTINOCONS_2025'].round(0).astype(int)
    df_conv['DESTANEX'] = 0
    
    # Para no convencionales: DESTINOCONS = 0, DESTANEX = DESTANEX_2025
    df_no_conv['DESTINOCONS'] = 0
    df_no_conv['DESTANEX'] = df_no_conv['DESTANEX_2025'].round(0).astype(int)
    
    # Merge convencionales (usando DESTINOCONS_2025)
    df_conv = pd.merge(df_conv, conv, on="DESTINOCONS_2025", how="left")
    
    # Merge no convencionales (usando DESTANEX_2025)
    df_no_conv = pd.merge(df_no_conv, no_conv, on="DESTANEX_2025", how="left")
    
    # Concatenar resultados
    df = pd.concat([df_conv, df_no_conv], ignore_index=True)
    
    
    print(f"Construcciones 2025 procesadas: {df.shape}")
    print(f"  - Convencionales (DESTINOCONS_2025 ≤ 76): {len(df_conv)}")
    print(f"  - No convencionales (DESTANEX_2025 > 76): {len(df_no_conv)}")

    # 🔎 DIAGNÓSTICO [URBANO 2024]: mapea por merge (no np.select). Reporta descartadas y sin nombre.
    descartadas = n_in - len(df)
    sin_nombre = int(df['USO_LADM'].isna().sum())
    print(f"   🔎 SIN HOMOLOGAR [URBANO 2024]: entradas={n_in}, mapeadas={len(df)}, "
          f"descartadas(no 1-76 ni anexo>76)={descartadas}, sin USO_LADM={sin_nombre}")
    if sin_nombre > 0:
        print("   top DESTINOCONS_2025 sin USO_LADM:")
        print(df[df['USO_LADM'].isna()]['DESTINOCONS_2025'].value_counts(dropna=False).head(10).to_string())

    return df

def homologar_rural(df):
    """
    Homologación rural - lógica propia con condiciones simples
    Input: DataFrame rural con DESTINOCONS_2025, DESTANEX_2025, CONDICION
    Output: DataFrame con DESTINOCONS, DESTANEX, USO_LADM
    """
    from io import StringIO
    
    # Separar convencionales y no convencionales
    df_conv = df[df['DESTINOCONS_2025'] > 0].copy()
    df_no_conv = df[df['DESTANEX_2025'] > 0].copy()
    
    print(f"   Rural convencionales: {len(df_conv)}, no convencionales: {len(df_no_conv)}")
    
    # ========== TABLAS LADM ==========
    conv = '''DESTINOCONS\tUSO_LADM
    1\tApartamentos_4_y_mas_pisos_en_PH
    2\tVivienda_Colonial_en_PH
    3\tApartamentos_4_y_mas_pisos
    4\tBarracas
    5\tCasa_Elbas
    6\tDepositos_Lockers
    7\tGarajes_Cubiertos
    8\tGarajes_En_PH
    9\tSalon_Comunal
    10\tSecadero_Ropa
    11\tVivienda_Colonial
    12\tVivienda_Hasta_3_Pisos
    13\tVivienda_Hasta_3_Pisos_En_PH
    14\tVivienda_Recreacional
    15\tVivienda_Recreacional_En_PH
    16\tBodegas_Comerciales_Grandes_Almacenes
    17\tBodegas_Comerciales
    18\tBodegas_Comerciales_en_PH
    19\tCentros_Comerciales_pequenios
    20\tCentros_Comerciales_grandes
    21\tEstacion_de_servicio
    22\tCentros_Comerciales_en_PH_pequenios
    23\tCentros_Comerciales_en_PH_grandes
    24\tClubes_Casinos
    25\tComercio
    26\tComercio_Colonial
    27\tComercio_Deposito_Almacenamiento
    28\tComercio_en_PH
    29\tHotel_Colonial
    30\tHoteles
    31\tHoteles_en_PH
    32\tOficinas_Consultorios
    33\tOficinas_Consultorios_Coloniales
    34\tOficinas_Consultorios_en_PH
    35\tParque_Diversiones
    36\tParqueaderos
    37\tParqueaderos_en_PH
    38\tPensiones_y_Residencias
    39\tPlaza_Mercado
    40\tRestaurante_Colonial
    41\tRestaurantes
    42\tRestaurantes_en_PH
    43\tTeatro_Cinemas
    44\tTeatro_Cinemas_en_PH
    45\tBodega_Casa_Bomba
    46\tBodegas_Casa_Bomba_en_PH
    47\tIndustrias
    48\tIndustrias_en_PH
    49\tTalleres
    50\tAulas_de_Clases
    51\tBiblioteca
    52\tCarceles
    53\tCasas_de_Culto
    54\tClinicas_Hospitales_Centros_Medicos
    55\tColegio_y_Universidades
    56\tColiseos
    57\tEntidad_Educativa_Colonial_Colegio_Colonial
    58\tEstadios
    59\tFuertes_y_Castillos
    60\tIglesia
    61\tIglesia_en_PH
    62\tInstalaciones_Militares
    63\tJardin_Infantil_en_Casa
    64\tParque_Cementerio
    65\tPlanetario
    66\tPlaza_de_Toros
    67\tPuestos_de_Salud
    68\tMuseos
    69\tSeminarios_Conventos
    70\tTeatro
    71\tUnidad_Deportiva
    72\tVelodromo_Patinodromo
    73\tAdministrativos
    74\tFundaciones_y_ONG
    75\tEntidades_del_Socorro
    76\tEstaciones_y_CAI
    '''
    
    no_conv = '''DESTANEX\tUSO_LADM
    77\tCanchas
    78\tCanchas_de_Tenis
    79\tCarretera
    80\tCerramiento
    81\tCimientos_Estructura_Muros_y_Placa_Base
    82\tCocheras_Marraneras_Porquerizas
    83\tConstruccion_en_Membrana_Arquitectonica
    84\tContenedor
    85\tCorrales
    86\tEstablos_Pesebreras
    87\tEstacion_Bombeo
    88\tEstacion_Sistema_Transporte
    89\tGalpones_Gallineros
    90\tGampling
    91\tHangar
    92\tKioscos
    93\tLagunas_de_Oxidacion
    94\tMarquesinas_Patios_Cubiertos
    95\tMuelles
    96\tMurallas
    97\tPergolas
    98\tPiscinas
    99\tPista_Aeropuerto
    100\tPozos
    101\tRamadas_Cobertizos_Caneyes
    102\tSecaderos
    103\tSilos
    104\tTanques
    105\tToboganes
    106\tTorre_de_Control
    107\tTorres_de_Enfriamiento
    108\tVia_Ferrea
    109\tCampo_de_Golf
    110\tCanopy
    111\tPatio_Encementado
    112\tPistas_de_Bolos
    113\tCanchas_Sinteticas_de_Futbol
    114\tColiseos
    115\tSaunas_y_Banos_Turcos
    116\tPista_de_Patinaje
    117\tPista_de_Atletismo
    118\tAlbercas_Banaderas
    119\tBeneficiaderos
    120\tCamaroneras
    '''
    
    conv = pd.read_csv(StringIO(conv), sep='\t')
    conv['DESTINOCONS'] = conv['DESTINOCONS'].astype(int)
    
    no_conv = pd.read_csv(StringIO(no_conv), sep='\t')
    no_conv['DESTANEX'] = no_conv['DESTANEX'].astype(int)
    
    # ========== CONVENCIONALES RURAL ==========
    USO = [1, 1, 3, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 18, 19, 20, 
           22, 23, 24, 25, 26, 28, 29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 
           40, 41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54, 55, 56, 57, 
           58, 59, 60, 61, 62, 63, 64, 65, 66, 67, 68, 69, 70, 71, 72, 1, 21]
    
    # Asegurar numérico
    df_conv['DESTINOCONS_2025'] = pd.to_numeric(df_conv['DESTINOCONS_2025'], errors='coerce').round().astype(int)
    df_conv['CONDICION'] = pd.to_numeric(df_conv['CONDICION'], errors='coerce').fillna(0).astype(int)
    
    CONDICIONES_CONV = [
        (df_conv["DESTINOCONS_2025"].isin([1]) & df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([2]) & (df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([2]) & ~(df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([3])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([4])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([5])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([6])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([7])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([8]) & df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([9]) & ~(df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([10])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([11])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([12])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([13])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([14])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([15])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([16])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([17])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([18])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([18])) & ~(df_conv["CONDICION"].isin([8,9])) & (df_conv["AREA_CONST"] > 5000),
        (df_conv["DESTINOCONS_2025"].isin([19])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([19])) & (df_conv["CONDICION"].isin([8,9])) & (df_conv["AREA_CONST"] > 5000),
        (df_conv["DESTINOCONS_2025"].isin([20])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([21])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([22])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([23]) & df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([24]) & ~(df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([25]) & ~(df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([26])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([27])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([28])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([29])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([30])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([31]) & ~df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([32]) & (df_conv["CONDICION"].isin([8,9]))),
        (df_conv["DESTINOCONS_2025"].isin([33])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([34])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([35])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([36])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([37])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([38])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([39])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([40])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([41])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([42])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([43])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([44])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([45])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([46])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([47])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([48])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([49])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([50])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([51])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([52])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([53])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([54])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([55])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([56])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([57])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([58])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([59])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([60])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([61])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([62])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([63])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([64])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([65])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([66])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([67])) & ~(df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([1002])) & (df_conv["CONDICION"].isin([8,9])),
        (df_conv["DESTINOCONS_2025"].isin([110])) & ~(df_conv["CONDICION"].isin([8,9])),
    ]
    
    df_conv["DESTINOCONS"] = np.select(CONDICIONES_CONV, USO, default=0)
    
    # Separar homologadas y sin homologar
    df_conv_homologadas = df_conv[df_conv["DESTINOCONS"] > 0].copy()
    df_conv_sin_homologar = df_conv[df_conv["DESTINOCONS"] == 0].copy()
    
    print(f"   Rural conv: {len(df_conv)} total, {len(df_conv_homologadas)} homologadas, {len(df_conv_sin_homologar)} sin homologar")

    # 🔎 DIAGNÓSTICO [RURAL]: por qué quedan sin homologar
    if len(df_conv_sin_homologar) > 0:
        print("   🔎 SIN HOMOLOGAR [RURAL] · top DESTINOCONS_2025:")
        print(df_conv_sin_homologar['DESTINOCONS_2025'].value_counts(dropna=False).head(20).to_string())
        print("   🔎 SIN HOMOLOGAR [RURAL] · top (DESTINOCONS_2025, CONDICION):")
        print(
            df_conv_sin_homologar
            .groupby(['DESTINOCONS_2025', 'CONDICION'], dropna=False)
            .size().sort_values(ascending=False).head(20).to_string()
        )

    # Merge solo homologadas
    df_conv_homologadas = pd.merge(df_conv_homologadas, conv, on="DESTINOCONS", how="left")
    
    # Unir
    df_conv = pd.concat([df_conv_homologadas, df_conv_sin_homologar], ignore_index=True, join='outer')
    
    # ========== NO CONVENCIONALES RURAL ==========
    USO_ANEX = [77, 78, 79, 80, 81, 81, 82, 83, 84, 85, 86, 87, 88, 89, 91, 92, 
                93, 94, 95, 96, 97, 98, 99, 100, 101, 102, 103, 104, 105, 106, 
                107, 108, 118, 119, 120]
    
    df_no_conv['DESTANEX_2025'] = pd.to_numeric(df_no_conv['DESTANEX_2025'], errors='coerce').round().astype(int)
    
    CONDICIONES_ANEX = [
        (df_no_conv["DESTANEX_2025"].isin([71])),
        (df_no_conv["DESTANEX_2025"].isin([72])),
        (df_no_conv["DESTANEX_2025"].isin([73])),
        (df_no_conv["DESTANEX_2025"].isin([74])),
        (df_no_conv["DESTANEX_2025"].isin([75])),
        (df_no_conv["DESTANEX_2025"].isin([101])),
        (df_no_conv["DESTANEX_2025"].isin([76])),
        (df_no_conv["DESTANEX_2025"].isin([77])),
        (df_no_conv["DESTANEX_2025"].isin([78])),
        (df_no_conv["DESTANEX_2025"].isin([79])),
        (df_no_conv["DESTANEX_2025"].isin([80])),
        (df_no_conv["DESTANEX_2025"].isin([81])),
        (df_no_conv["DESTANEX_2025"].isin([82])),
        (df_no_conv["DESTANEX_2025"].isin([83])),
        (df_no_conv["DESTANEX_2025"].isin([84])),
        (df_no_conv["DESTANEX_2025"].isin([85])),
        (df_no_conv["DESTANEX_2025"].isin([86])),
        (df_no_conv["DESTANEX_2025"].isin([87])),
        (df_no_conv["DESTANEX_2025"].isin([88])),
        (df_no_conv["DESTANEX_2025"].isin([89])),
        (df_no_conv["DESTANEX_2025"].isin([90])),
        (df_no_conv["DESTANEX_2025"].isin([91])),
        (df_no_conv["DESTANEX_2025"].isin([92])),
        (df_no_conv["DESTANEX_2025"].isin([93])),
        (df_no_conv["DESTANEX_2025"].isin([94])),
        (df_no_conv["DESTANEX_2025"].isin([95])),
        (df_no_conv["DESTANEX_2025"].isin([96])),
        (df_no_conv["DESTANEX_2025"].isin([97])),
        (df_no_conv["DESTANEX_2025"].isin([98])),
        (df_no_conv["DESTANEX_2025"].isin([99])),
        (df_no_conv["DESTANEX_2025"].isin([100])),
        (df_no_conv["DESTANEX_2025"].isin([102])),
        (df_no_conv["DESTANEX_2025"].isin([68])),
        (df_no_conv["DESTANEX_2025"].isin([69])),
        (df_no_conv["DESTANEX_2025"].isin([70])),
    ]
    
    df_no_conv["DESTANEX"] = np.select(CONDICIONES_ANEX, USO_ANEX, default=0)
    
    df_no_conv_homologadas = df_no_conv[df_no_conv["DESTANEX"] > 0].copy()
    df_no_conv_sin_homologar = df_no_conv[df_no_conv["DESTANEX"] == 0].copy()
    
    print(f"   Rural no conv: {len(df_no_conv)} total, {len(df_no_conv_homologadas)} homologadas, {len(df_no_conv_sin_homologar)} sin homologar")

    # 🔎 DIAGNÓSTICO [RURAL NO CONV]: por qué quedan sin homologar (depende solo de DESTANEX_2025)
    if len(df_no_conv_sin_homologar) > 0:
        print("   🔎 SIN HOMOLOGAR [RURAL NO CONV] · top DESTANEX_2025:")
        print(df_no_conv_sin_homologar['DESTANEX_2025'].value_counts(dropna=False).head(20).to_string())

    df_no_conv_homologadas = pd.merge(df_no_conv_homologadas, no_conv, on="DESTANEX", how="left")
    
    df_no_conv = pd.concat([df_no_conv_homologadas, df_no_conv_sin_homologar], ignore_index=True, join='outer')
    
    # Asegurar columnas
    if 'DESTANEX' not in df_conv.columns:
        df_conv['DESTANEX'] = 0
    if 'DESTINOCONS' not in df_no_conv.columns:
        df_no_conv['DESTINOCONS'] = 0
    
    # Concatenar final rural
    df = pd.concat([df_conv, df_no_conv], ignore_index=True, join='outer')
    
    print(f"Rural Convencionales: {len(df_conv)} total, {len(df_conv_homologadas)} homologadas, {len(df_conv_sin_homologar)} sin homologar")

    print(f"Rural No convencionales: {len(df_no_conv)} total, {len(df_no_conv_homologadas)} homologadas, {len(df_no_conv_sin_homologar)} sin homologar")
        
    return df