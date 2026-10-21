# -*- coding: utf-8 -*-
"""Liquidacion por TABLAS de la vigencia 2024.

Los valores de 2024 viven AQUI, incrustados en el codigo, como se hizo aquel
anio. No se leen de ningun Excel: este archivo es la evidencia de con que se
liquido en 2024.

Dos formas de usarlo:

  - IMPORTADO: tablas_liquidacion_2024(df_const) aplica las reglas y los
    valores de 2024 a la base que se le pase. Es lo que usa escenarios.py para
    responder que habria dado la base de hoy con las reglas de entonces.

  - COMO SCRIPT: reconstruye la base de 2024 desde ./data/*.txt y liquida,
    que es lo que hacia originalmente. Esos archivos ya no estan en el
    proyecto, asi que hoy no corre asi; se conserva para documentar de donde
    salia cada columna.

Lo unico que se le agrego a la logica original es la traduccion de la base de
hoy a lo que 2024 esperaba de la suya -ver el comienzo de la funcion-: nombres
de columna y tipos. Las condiciones y los valores estan intactos.
"""
import pandas as pd
import numpy as np
import re
import pyarrow.feather as feather
import os
from io import StringIO
import warnings
warnings.filterwarnings("ignore")


def tablas_liquidacion_2024(df_const):
    """El VM2 que las reglas de 2024 le darian a la base que se le pase."""
    df_const = df_const.copy()

    # --- Lo que 2024 esperaba de su propia base -----------------------------
    # COD_HOM_02 era UNA SOLA columna que cubria construcciones y anexos: para
    # una construccion traia su destino y para un anexo el codigo del anexo
    # (077, 078, 094, 101...). Hoy eso esta partido en DESTINOCONS y DESTANEX,
    # asi que se vuelve a juntar. Sin esto los 114.001 anexos se quedan con
    # '000', no cruzan ninguna condicion y salen sin tabla.
    _dc = df_const['DESTINOCONS'].astype(str).str.strip().str.zfill(3)
    _da = df_const['DESTANEX'].astype(str).str.strip().str.zfill(3)
    df_const['COD_HOM_02'] = _dc.where(_dc != '000', _da)

    # La tipologia: TRES ULTIMAS del ZHF, sin importar el largo. Menos de 11
    # caracteres no es un ZHF (filas en '0' y codigos rurales con otra
    # estructura), y esas quedan vacias.
    _zhf = df_const['ZHF'].astype(str).str.strip()
    _tip = _zhf.str[-3:].where(_zhf.str.len() >= 11, '')
    df_const['TIPOLOGIA_ZHF'] = _tip
    df_const['ACT_ECON'] = _tip.str[:2]
    df_const['TIPO_SEGUN_ACT'] = _tip.str[2:]
    df_const['ACTIVIDAD'] = _tip.str[1:]

    # CONDICION: 2024 la sacaba del predial nacional y no de la columna, asi
    # que se hace igual. Si el predial no sirve, se cae a la columna.
    _npn = df_const['NUMERO_PREDIAL_NACIONAL'].astype(str)
    _cond = _npn.str[21:22]
    df_const['CONDICION'] = _cond.where(_cond.str.strip() != '',
                                        df_const['CONDICION'].astype(str))





    # Transformar valores
    # Primero aseguramos que los valores sean numéricos
    df_const['COD_HOM_02'] = pd.to_numeric(df_const['COD_HOM_02'], errors='coerce')
    df_const['COD_HOM_02'] = df_const['COD_HOM_02'].apply(lambda x: f"{int(x):03d}" if pd.notnull(x) else 'NA')
    df_const['COD_HOM_02'] = df_const['COD_HOM_02'].astype(str)
    # Luego aplicamos el formato con ceros a la izquierda, ignorando valores nulos

    #df_const['ESTRATO_PARQ'] = df_const['ESTRATO_PARQ'].astype(str).str.replace('.0', '')

    df_const['PUNTCONS'] = df_const['PUNTCONS'].fillna(0).astype('int64')
    df_const['TIPOANEXO'] = df_const['TIPOANEXO'].fillna(0).astype('int64')
    df_const['CONDICION'] = df_const['NUMERO_PREDIAL_NACIONAL'].str[21:22]
    df_const['ESTRPRED'] = df_const['ESTRPRED'].fillna(0).astype('int64').astype('string')


    ### APLICAR LA CONDICION DEL PREDIO
    df_const['TIPO_PARQ'] = np.where(
        df_const['COD_HOM_02'].isin(["007", "008", "036", "037"]),  # Solo para estos códigos
        np.where(df_const['ACONCONS']  <= 50, "Sencillo", "Doble"),  # Sencillo si ACONCONS < 17, Doble en caso contrario
        pd.NA  # Dejar vacío para los demás códigos
    )


    condiciones_tabla = [
        (df_const['COD_HOM_02'].isin(["004", "012", "013", "063"])),
        (df_const['COD_HOM_02'].isin(["016", "021", "024", "025", "039", "041", "049"])),
        (df_const['COD_HOM_02'].isin(["009", "018", "047", "048"])),
        (df_const['COD_HOM_02'].isin(["050", "051", "055", "068", "070","071"])),
        (df_const['COD_HOM_02'].isin(["054", "067"])),
        (df_const['COD_HOM_02'].isin(["032", "033", "052", "073", "074", "075", "076"])),
        (df_const['COD_HOM_02'].isin(["053", "060", "061"])),
        (df_const['COD_HOM_02'].isin(["003"])),
        (df_const['COD_HOM_02'].isin(["030", "031", "038"])),
        (df_const['COD_HOM_02'].isin([
            "077", "078", "113", "110", "080", "081", "082", "114", "085", "086", "089",
            "092", "094", "111", "098", "100", "101", "102", "103", "104", "105", "109",
            "112", "115", "079", "083", "084", "091", "097", "118", "056"
        ])),
        (df_const['COD_HOM_02'].isin(["019", "022", "043"])),
        (df_const['COD_HOM_02'].isin(["006", "007", "008", "027","036", "037"])),
        (df_const['COD_HOM_02'].isin(["001","034","028"])) & (df_const['CONDICION']=="9"), # 
        (df_const['COD_HOM_02'].isin(["020","023"]))
    ]

    valores_tipomode = [
        'T1_RESIDENCIAL', 
        'T2_COMERCIAL', 
        'T3_INDUSTRIAL', 
        'T4_INSTITUCIONAL_ED',
        'T5_INSTITUCIONAL_SA', 
        'T6_INSTITUCIONAL_SER', 
        'T7_INSTITUCIONAL_IG',
        'T8_EDIFICIOS', 
        'T9_HOTELES', 
        'T10_ANEXOS', 
        'T11_CCOMERCIALES', 
        'T12_PARQUEADEROS',
        'MODELO',
        'ESPECIAL'
    ]

    # Asignar valores a la nueva columna
    df_const['TABLA_ORIGEN'] = np.select(condiciones_tabla, valores_tipomode, default='')


    condiciones_construccion=[ 
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T1_RESIDENCIAL") & (df_const['PUNTCONS'] == 100),

    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T2_COMERCIAL") & (df_const['PUNTCONS'] == 100),

    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T3_INDUSTRIAL") & (df_const['PUNTCONS'] == 100),

      (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T4_INSTITUCIONAL_ED") & (df_const['PUNTCONS'] == 100),

     (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T5_INSTITUCIONAL_SA") & (df_const['PUNTCONS'] == 100),

     (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T6_INSTITUCIONAL_SER") & (df_const['PUNTCONS'] == 100),

    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T7_INSTITUCIONAL_IG") & (df_const['PUNTCONS'] == 100),

     (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T8_EDIFICIOS") & (df_const['PUNTCONS'] == 100),

    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T9_HOTELES") & (df_const['PUNTCONS'] == 100),


    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '077') & (df_const['TIPOANEXO'].isin([1,10,20,40,50,60])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '077') & (df_const['TIPOANEXO'].isin([80,90])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '078') & (df_const['TIPOANEXO'] == 10),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '078') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '113') & (df_const['TIPOANEXO'].isin([20,40,50])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '110') & (df_const['TIPOANEXO'].isin([40,50,60])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '080') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '080') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '080') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '080') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '081') & (df_const['TIPOANEXO'].isin([20,40])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '081') & (df_const['TIPOANEXO'].isin([50,60])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '081') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '082') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '082') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '082') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '082') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '114') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '114') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '085') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '085') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '085') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '086') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '086') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '086') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '089') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '089') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '089') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '089') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '092') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '092') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '092') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '092') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '094') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '094') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '094') & (df_const['TIPOANEXO'].isin([50,60])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '094') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '111') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '111') & (df_const['TIPOANEXO'].isin([40,50])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '111') & (df_const['TIPOANEXO'].isin([60,80])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '098') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '098') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '098') & (df_const['TIPOANEXO'] == 50),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '098') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '098') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '100') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '100') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '101') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '101') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '101') & (df_const['TIPOANEXO'].isin([50,60])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '101') & (df_const['TIPOANEXO'].isin([70,80])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '101') & (df_const['TIPOANEXO'] == 90),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '102') & (df_const['TIPOANEXO'].isin([40,50])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '103') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '103') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '104') & (df_const['TIPOANEXO'] == 20),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '104') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '104') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '104') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '105') & (df_const['TIPOANEXO'] == 40),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '105') & (df_const['TIPOANEXO'] == 50),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '105') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '079') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '083') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '084') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '091') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '097') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '118') ,
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '109') & (df_const['TIPOANEXO'] == 30),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '109') & (df_const['TIPOANEXO'] == 50),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '109') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '112') & (df_const['TIPOANEXO'] == 30),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '112') & (df_const['TIPOANEXO'] == 50),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '112') & (df_const['TIPOANEXO'] == 80),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '115') & (df_const['TIPOANEXO'] == 30),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '115') & (df_const['TIPOANEXO'] == 50),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '115') & (df_const['TIPOANEXO'].isin([60,80])),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '056') & (df_const['TIPOANEXO'] == 60),
    (df_const['TABLA_ORIGEN'] == "T10_ANEXOS") & (df_const['COD_HOM_02'] == '056') & (df_const['PUNTCONS'] == 77),


    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 1),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 2),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 3),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 4),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 5),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 6),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 7),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 8),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 9),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 10),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 11),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 12),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 13),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 14),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 15),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 16),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 17),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 18),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 19),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 20),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 21),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 22),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 23),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 24),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 25),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 26),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 27),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 28),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 29),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 30),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 31),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 32),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 33),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 34),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 35),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 36),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 37),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 38),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 39),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 40),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 41),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 42),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 43),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 44),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 45),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 46),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 47),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 48),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 49),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 50),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 51),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 52),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 53),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 54),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 55),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 56),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 57),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 58),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 59),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 60),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 61),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 62),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 63),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 64),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 65),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 66),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 67),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 68),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 69),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 70),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 71),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 72),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 73),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 74),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 75),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 76),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 77),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 78),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 79),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 80),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 81),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 82),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 83),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 84),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 85),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 86),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 87),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 88),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 89),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 90),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 91),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 92),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 93),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 94),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 95),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 96),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 97),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 98),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 99),
    (df_const['TABLA_ORIGEN'] == "T11_CCOMERCIALES") & (df_const['PUNTCONS'] == 100),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '1') | (df_const['ACTIVIDAD'] == '11')) & 
        (df_const['TIPO_PARQ'].isin(['Sencillo', 'Doble']))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '2') | (df_const['ACTIVIDAD'] == '12')) & 
        (df_const['TIPO_PARQ'].isin(['Sencillo', 'Doble']))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '3') | (df_const['ACTIVIDAD'] == '13')) & 
        (df_const['TIPO_PARQ'].isin(['Sencillo', 'Doble']))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '4') | (df_const['ACTIVIDAD'] == '14')) & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '5') | (df_const['ACTIVIDAD'] == '15')) & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '6') | (df_const['ACTIVIDAD'] == '16')) & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (df_const['ACTIVIDAD'].isin(['21', '22'])) & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (df_const['ACTIVIDAD'] == '23') & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '4') | (df_const['ACTIVIDAD'] == '14')) & 
        (df_const['TIPO_PARQ'] == 'Doble')    
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '5') | (df_const['ACTIVIDAD'] == '15')) &
        (df_const['TIPO_PARQ'] == 'Doble') 
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        ((df_const['ESTRPRED'] == '6') | (df_const['ACTIVIDAD'] == '16')) &
        (df_const['TIPO_PARQ'] == 'Doble')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (df_const['ACTIVIDAD'].isin(['21', '22'])) & 
        (df_const['TIPO_PARQ'] == 'Doble')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (df_const['ACTIVIDAD'] == '23') & 
        (df_const['TIPO_PARQ'] == 'Doble')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (~df_const['ACTIVIDAD'].isin(['21', '22', '23'])) & 
        (df_const['TIPO_PARQ'] == 'Sencillo')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['036', '037'])) & 
        (~df_const['ACTIVIDAD'].isin(['21', '22', '23'])) & 
        (df_const['TIPO_PARQ'] == 'Doble')
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '1') | (df_const['ACTIVIDAD'] == '11'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '2') | (df_const['ACTIVIDAD'] == '12'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '3') | (df_const['ACTIVIDAD'] == '13'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '4') | (df_const['ACTIVIDAD'] == '14'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '5') | (df_const['ACTIVIDAD'] == '15'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '006') & 
        ((df_const['ESTRPRED'] == '6') | (df_const['ACTIVIDAD'] == '16'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['006', '027'])) & 
        ((df_const['ESTRPRED'] == '0') | (df_const['ACTIVIDAD'] == '21'))
    ),

    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'] == '027') & 
        (df_const['ESTRPRED'] != '0')
    ),
    ##
    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        (df_const['ESTRPRED'] == '0') & 
        (df_const['ACTIVIDAD'].isin(['21', '22'])) & 
        (df_const['TIPO_PARQ'] == 'Sencillo') 
    ),
    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        (df_const['ESTRPRED'] == '0') & 
        (df_const['ACTIVIDAD'].isin(['21', '22'])) & 
        (df_const['TIPO_PARQ'] == 'Doble') 
    ),
    (
        (df_const['TABLA_ORIGEN'] == "T12_PARQUEADEROS") & 
        (df_const['COD_HOM_02'].isin(['007', '008'])) & 
        (df_const['ESTRPRED'] == '0') & 
        (~df_const['ACTIVIDAD'].isin(['21', '22'])) & 
        (df_const['TIPO_PARQ'] == 'Doble') 
    )




    ]


    valores_construccion =[

    ###T1_RESIDENCIAL
    200114,	206696,	213496,	220518,	227772,	235265,	243004,	250997,	259254,	267782,	276590,	285688,	295086,	304793,	314819,	325174,	335871,	346919,	358331,	370118,	382293,	394868,	407857,	421274,	435131,	449445,	464229,	479499,	495272,	511564,	528392,	545773,	563726,	582269,	601423,	621206,	641640,	662747,	684548,	707065,	730324,	754348,	779162,	804792,	831265,	858609,	886852,	916025,	946157,	977281,	1009428,	1042632,	1076929,	1112354,	1148945,	1186739,	1225776,	1266097,	1307745,	1350762,	1395195,	1441089,	1488493,	1537456,	1588030,	1640268,	1694223,	1749954,	1807518,	1866975,	1928389,	1991822,	2057342,	2125017,	2194919,	2267119,	2341695,	2418724,	2498287,	2580467,	2665350,	2753025,	2843584,	2937123,	3033738,	3133531,	3236607,	3343074,	3453042,	3566629,	3683951,	3805133,	3930301,	4059586,	4193124,	4331055,	4473523,	4620677,	4772672,	4929666,

    ###T2_COMERCIAL
    28299,	67620,	106941,	146263,	185584,	224905,	264227,	303548,	342869,	382191,	421512,	460833,	500155,	539476,	578797,	618119,	657440,	696761,	736083,	775404,	814725,	854047,	893368,	932689,	972011,	1011332,	1050653,	1089975,	1129296,	1168617,	1207939,	1247260,	1286581,	1325903,	1365224,	1404546,	1443867,	1483188,	1522510,	1561831,	1601152,	1640474,	1679795,	1719116,	1758438,	1797759,	1837080,	1876402,	1915723,	1955044,	1994366,	2033687,	2073008,	2112330,	2151651,	2190972,	2230294,	2269615,	2308936,	2348258,	2387579,	2426900,	2466222,	2505543,	2544864,	2584186,	2623507,	2662828,	2702150,	2741471,	2780792,	2820114,	2859435,	2898757,	2938078,	2977399,	3016721,	3056042,	3095363,	3134685,	3174006,	3213327,	3252649,	3291970,	3331291,	3370613,	3409934,	3449255,	3488577,	3527898,	3567219,	3606541,	3645862,	3685183,	3724505,	3763826,	3803147,	3842469,	3881790,	3921111,

    #T3_INDUSTRIAL
    60923,	98406,	135889,	173373,	210856,	248339,	285822,	323305,	360788,	398271,	435755,	473238,	510721,	548204,	585687,	623170,	660653,	698137,	735620,	773103,	810586,	848069,	885552,	923035,	960519,	998002,	1035485,	1072968,	1110451,	1147934,	1185417,	1222900,	1260384,	1297867,	1335350,	1372833,	1410316,	1447799,	1485282,	1522766,	1560249,	1597732,	1635215,	1672698,	1710181,	1747664,	1785148,	1822631,	1860114,	1897597,	1935080,	1972563,	2010046,	2047530,	2085013,	2122496,	2159979,	2197462,	2234945,	2272428,	2309911,	2347395,	2384878,	2422361,	2459844,	2497327,	2534810,	2572293,	2609777,	2647260,	2684743,	2722226,	2759709,	2797192,	2834675,	2872159,	2909642,	2947125,	2984608,	3022091,	3059574,	3097057,	3134541,	3172024,	3209507,	3246990,	3284473,	3321956,	3359439,	3396922,	3434406,	3471889,	3509372,	3546855,	3584338,	3621821,	3659304,	3696788,	3734271,	3771754,

    #T4_INSTITUCIONAL_ED
    20491,	46695,	75599,	106409,	138719,	172277,	206909,	242488,	278916,	316116,	354024,	392588,	431762,	471508,	511792,	552586,	593863,	635600,	677776,	720372,	763371,	806758,	850517,	894637,	939104,	983907,	1029036,	1074481,	1120232,	1166282,	1212621,	1259243,	1306141,	1353306,	1400733,	1448417,	1496350,	1544528,	1592945,	1641597,	1690478,	1739584,	1788911,	1838454,	1888210,	1938175,	1988344,	2038715,	2089284,	2140047,	2191002,	2242146,	2293475,	2344986,	2396678,	2448547,	2500591,	2552806,	2605192,	2657745,	2710463,	2763345,	2816387,	2869588,	2922945,	2976458,	3030123,	3083939,	3137905,	3192018,	3246276,	3300679,	3355224,	3409911,	3464736,	3519699,	3574799,	3630034,	3685402,	3740902,	3796533,	3852293,	3908182,	3964197,	4020339,	4076604,	4132993,	4189505,	4246137,	4302889,	4359760,	4416749,	4473855,	4531076,	4588412,	4645862,	4703424,	4761099,	4818884,	4876780,

    #T5_INSTITUCIONAL_SA

    27640,	61146,	97294,	135271,	174669,	215238,	256808,	299253,	342480,	386412,	430989,	476161,	521885,	568123,	614845,	662023,	709633,	757651,	806060,	854841,	903978,	953457,	1003265,	1053389,	1103818,	1154541,	1205549,	1256832,	1308383,	1360193,	1412256,	1464563,	1517109,	1569887,	1622891,	1676116,	1729557,	1783208,	1837065,	1891124,	1945380,	1999828,	2054466,	2109289,	2164293,	2219476,	2274833,	2330362,	2386060,	2441923,	2497950,	2554136,	2610480,	2666978,	2723629,	2780431,	2837380,	2894474,	2951712,	3009092,	3066610,	3124267,	3182058,	3239983,	3298040,	3356228,	3414543,	3472986,	3531553,	3590245,	3649058,	3707992,	3767046,	3826217,	3885504,	3944907,	4004424,	4064053,	4123794,	4183644,	4243604,	4303672,	4363846,	4424126,	4484510,	4544998,	4605588,	4666280,	4727072,	4787963,	4848953,	4910041,	4971226,	5032506,	5093881,	5155350,	5216913,	5278568,	5340314,	5402152,

    #T6_INSTITUCIONAL_SER
    270598,	305846,	341095,	376343,	411591,	446839,	482087,	517336,	552584,	587832,	623080,	658328,	693576,	728825,	764073,	799321,	834569,	869817,	905066,	940314,	975562,	1010810,	1046058,	1081306,	1116555,	1151803,	1187051,	1222299,	1257547,	1292796,	1328044,	1363292,	1398540,	1433788,	1469036,	1504285,	1539533,	1574781,	1610029,	1645277,	1680526,	1715774,	1751022,	1786270,	1821518,	1856766,	1892015,	1927263,	1962511,	1997759,	2033007,	2068256,	2103504,	2138752,	2174000,	2209248,	2244496,	2279745,	2314993,	2350241,	2385489,	2420737,	2455985,	2491234,	2526482,	2561730,	2596978,	2632226,	2667475,	2702723,	2737971,	2773219,	2808467,	2843715,	2878964,	2914212,	2949460,	2984708,	3019956,	3055205,	3090453,	3125701,	3160949,	3196197,	3231445,	3266694,	3301942,	3337190,	3372438,	3407686,	3442935,	3478183,	3513431,	3548679,	3583927,	3619175,	3654424,	3689672,	3724920,	3760168,

    #T7_INSTITUCIONAL_IG
    28321,	63845,	102714,	143927,	186977,	231549,	277429,	324458,	372516,	421506,	471352,	521987,	573356,	625414,	678118,	731432,	785326,	839770,	894739,	950210,	1006163,	1062578,	1119437,	1176725,	1234427,	1292529,	1351018,	1409883,	1469112,	1528694,	1588621,	1648883,	1709470,	1770376,	1831592,	1893110,	1954925,	2017029,	2079415,	2142079,	2205013,	2268213,	2331674,	2395390,	2459357,	2523570,	2588024,	2652715,	2717640,	2782794,	2881577,	2929712,	2978650,	3028406,	3078993,	3130424,	3182715,	3235880,	3289933,	3344888,	3400761,	3457568,	3515324,	3574044,	3633746,	3694444,	3756157,	3818900,	3882691,	3947548,	4013489,	4080531,	4148692,	4217993,	4288451,	4360085,	4432917,	4506965,	4582250,	4658792,	4736613,	4815734,	4896177,	4977964,	5061116,	5145658,	5231611,	5319001,	5407850,	5498184,	5590026,	5683403,	5778339,	5874861,	5972996,	6072769,	6174210,	6277344,	6382202,	6488811,

    #T8_EDIFICIOS 
    28442,	59985,	92815,	126510,	160862,	195748,	231085,	266811,	302882,	339261,	375921,	412837,	449989,	487361,	524939,	562709,	600660,	638782,	677067,	715507,	754094,	792823,	831686,	870679,	909797,	949035,	988388,	1027853,	1067427,	1107105,	1146884,	1186762,	1226735,	1266801,	1306958,	1347202,	1387532,	1427946,	1468442,	1509016,	1549669,	1590398,	1631201,	1672076,	1713023,	1754040,	1795125,	1836277,	1877494,	1918777,	1960122,	2001530,	2042998,	2084527,	2126114,	2167759,	2209462,	2251220,	2293034,	2334902,	2376823,	2418797,	2460823,	2502900,	2545027,	2587204,	2629430,	2671705,	2714027,	2756395,	2798811,	2841272,	2883778,	2926329,	2968924,	3011562,	3054244,	3096967,	3139733,	3182540,	3225389,	3268278,	3311206,	3354175,	3397183,	3440229,	3483314,	3526437,	3569597,	3612794,	3656028,	3699299,	3742606,	3785948,	3829325,	3872738,	3916185,	3959667,	4003182,	4046731,

    #T9_HOTELES 
    52309,	105085,	158039,	211108,	264263,	317487,	370769,	424099,	477472,	530884,	584330,	637807,	691313,	744845,	798402,	851981,	905582,	959204,	1012845,	1066503,	1120179,	1173872,	1227580,	1281303,	1335040,	1388792,	1442556,	1496333,	1550123,	1603925,	1657738,	1711562,	1765397,	1819243,	1873098,	1926964,	1980839,	2034723,	2088617,	2142520,	2196431,	2250350,	2304278,	2358214,	2412158,	2466109,	2520068,	2574035,	2628008,	2681989,	2735977,	2789971,	2843972,	2897980,	2951994,	3006014,	3060040,	3114073,	3168112,	3222156,	3276206,	3330262,	3384324,	3438391,	3492463,	3546541,	3600624,	3654712,	3708806,	3762904,	3817008,	3871116,	3925229,	3979347,	4033469,	4087596,	4141728,	4195864,	4250005,	4304150,	4358300,	4412453,	4466611,	4520773,	4574940,	4629110,	4683285,	4737463,	4791645,	4845832,	4900022,	4954216,	5008414,	5062615,	5116820,	5171029,	5225242,	5279458,	5333678,	5387901,

    #T10_ANEXOS
    322359,	264772,	227205,	169255,	184409,	1894559,	403959,	582989,	605120,	1124194,	313340,	567339,	736096,	358589,	656246,	823887,	965363,	1118735,	1736860,	87998,	196916,	658524,	373286,	639143,	1104999,	306067,	515746,	613393,	861409,	442090,	567383,	645197,	1109845,	276086,	435638,	540028,	764118,	124355,	160276,	270241,	1062896,	1259182,	1547400,	1741858,	2108509,	798215,	1770636,	230083,	455681,	520195,	767402,	1049951,	262937,	1466809,	3523696,	596827,	782898,	1293343,	3256335,	971469,	2279142,	3911668,	280371,	765761,	3142651,	1148137,	821433,	758266,	167448,	213116,	270274,	2620691,	3335438,	4230005,	1572620,	2001525,	2538335,	1118735,	1736860,


    #T11_CCOMERCIALES   
    70254,	128911,	183865,	236544,	287594,	337381,	386143,	434044,	481204,	527717,	573654,	619074,	664026,	708549,	752679,	796444,	839871,	882981,	925794,	968328,	1010599,	1052620,	1094404,	1135963,	1177307,	1218446,	1259390,	1300144,	1340719,	1381120,	1421354,	1461427,	1501344,	1541112,	1580734,	1620216,	1659562,	1698776,	1737862,	1776823,	1815664,	1854387,	1892996,	1931493,	1969882,	2008165,	2046344,	2084423,	2122403,	2160287,	2198077,	2235775,	2273383,	2310903,	2348337,	2385686,	2422952,	2460138,	2497243,	2534271,	2571222,	2608098,	2644900,	2681629,	2718287,	2754875,	2791395,	2827846,	2864231,	2900551,	2936806,	2972998,	3009127,	3045195,	3081203,	3117151,	3153040,	3188871,	3224645,	3260363,	3296025,	3331633,	3367187,	3402688,	3438136,	3473532,	3508878,	3544172,	3579417,	3614613,	3649761,	3684860,	3719912,	3754917,	3789876,	3824789,	3859657,	3894481,	3929260,	3963995,

    #T12_PARQUEADEROS
    4800000,	12000000,	18000000,	27000000,	37000000,	48000000,	46000000,	48000000,	30590000,	42624000,	57790000,	70299000,	77275000,	48000000,	57790000,	750000,	750000,	850000,	1300000,	1600000,	1800000,	1450000,	1800000,	46000000,	70299000,	77275000


    ]
    df_const['LIQUIDACION_CONSTRUCCION'] = np.select(condiciones_construccion, valores_construccion, default=np.nan)


    # Cambiar el nombre de la columna 'LIQUIDACION_CONSTRUCCION' por 'VM2'
    df_const.rename(columns={'LIQUIDACION_CONSTRUCCION': 'VM2'}, inplace=True)
    return df_const

# ---------------------------------------------------------------------------
# Como se corria en 2024: armaba su propia base y liquidaba. Va bajo __main__
# para que importar el modulo NO intente leer archivos que ya no estan.
# ---------------------------------------------------------------------------
def _base_original_2024():
    """La base que 2024 construia desde ./data/*.txt."""
    ### Cargar archivos
    # 1. Tabla predio
    ruta_predio: str = './data/20241229_TABLA_PREDIO_NOVEDAD.txt'

    predio = pd.read_csv(
        ruta_predio,
        delimiter=r'\|\*\|',               # El delimitador es un tabulador
        encoding='ISO-8859-1',           # Codificación del archivo
        skipinitialspace=True,       # Elimina espacios después del delimitador
        #on_bad_lines='skip',         # Saltar líneas con problemas de formato
        dtype={'NUMERO_PREDIAL_NACIONAL': 'string', 'ID_PREDIO': 'string'}  # Tipos de datos
    )



    # 2. Tabla construcción
    ruta_const: str = './data/20241229_BASE_CONSTRUCCIONES_HOMOLOGADA.txt'


    predio_CONST = pd.read_csv(
        ruta_const,
        delimiter=r'\|\*\|',
        encoding='ISO-8859-1',
        skipinitialspace=True,
        #on_bad_lines='skip',
        dtype={
            'NUMERO_PREDIAL_NACIONAL': 'string',
            'ZHF': 'string',
            'ID_PREDIO': 'string',
            'ID_CONSTRUCCION': 'string'
        }
    )

    # Cargar el archivo 'zhf'
    ruta_zhf: str = './data/20241229_ASIGNACION_ZHF_TOTAL.csv'

    df_zhf = pd.read_csv(
        ruta_zhf,
        delimiter=';',             # El delimitador es punto y coma ';'
        encoding='ISO-8859-1',     # Codificación compatible con caracteres especiales
        skipinitialspace=True,     # Eliminar espacios después del delimitador
        #on_bad_lines='skip',       # Saltar líneas con problemas de formato
        dtype=str                 # Tratar todas las columnas como cadenas inicialmente
    )

    print(predio.shape)
    print(predio_CONST.shape)
    print(df_zhf.shape)

    ##############TOMAR LA PRIMERA ZONA ###########
    df_zhf = df_zhf.sort_values(['ID_PREDIO',  'PORCENTAJE'], ascending=[True, False]).copy()

    # Crear columnas 'NoUsos' y 'No_piso_max'
    df_zhf['NoZHF'] = df_zhf.groupby('ID_PREDIO').cumcount() + 1
    df_zhf = df_zhf[df_zhf['NoZHF']==1]

    ############ CRUZAR TABLAS
    predio['COMUNA'] = predio['NUMERO_PREDIAL_NACIONAL'].apply(lambda x : str(x[9:11]))

    # Filtra las comunas de la actualización
    predio = predio[predio['COMUNA'].isin(['02', '03', '04', '08', '17', '19', '22'])]


    #####
    predio_CONST1 = pd.merge(predio_CONST, predio[['ID_PREDIO','AREAPRED', 'ESTRPRED','AVALPRED','DIREPRED']],  on='ID_PREDIO', how='left')  
    predio_CONST2= pd.merge(predio_CONST1, df_zhf[['ID_PREDIO','ZHF']],  on='ID_PREDIO', how='left')

    print(predio_CONST.shape)
    print( predio_CONST1.shape)
    print( predio_CONST2.shape)


    ####
    return predio_CONST2


if __name__ == "__main__":
    df = tablas_liquidacion_2024(_base_original_2024())
    df[['ID_PREDIO', 'ID_CONSTRUCCION', 'ACONANEX', 'CONSANEX',
        'DESTANEX', 'VM2']].to_csv('./output/TABLAS.txt', index=False, sep=';')
    print("Liquidacion tablas 2024: OK")
