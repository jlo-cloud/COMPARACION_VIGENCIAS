import pandas as pd
import numpy as np
from datetime import datetime
import os

def generar_reporte_inconsistencias(
    df,
    validar_coordenadas=True,
    validar_zhf=True,
    validar_uso_ladm=True,
    validar_construcciones=True,
    output_path='./output/Pre_inconsistencias/'
):

    print("\n" + "="*80)
    print("📋 GENERANDO REPORTE DE INCONSISTENCIAS")
    print("="*80)

    inconsistencias = {}
    predios_con_inconsistencias = {}

    # ------------------------------------------------------------------
    # 1️⃣ VALIDAR ZHF
    # ------------------------------------------------------------------
    if validar_zhf:

        def es_zhf_invalido(zhf):
            if pd.isna(zhf):
                return True
            zhf_str = str(zhf).strip()
            if zhf_str in ['', 'nan', 'None']:
                return True
            return len(zhf_str) != 11

        sin_zhf = df[df['ZHF'].apply(es_zhf_invalido)].copy()
        sin_zhf['MOTIVO_INCONSISTENCIA'] = 'Sin ZHF o ZHF inválido'

        for predio in sin_zhf['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin ZHF')

        inconsistencias['SIN_ZHF'] = {
            'total': len(sin_zhf),
            'predios_unicos': sin_zhf['ID_PREDIO'].nunique(),
            'detalle': sin_zhf.drop_duplicates('ID_PREDIO')
        }

    # ------------------------------------------------------------------
    # 2️⃣ COORDENADAS
    # ------------------------------------------------------------------
    if validar_coordenadas:

        sin_long = df[
            df['LONGITUDE'].isna() &
            df['DESTINOCONS'].fillna(0).astype(int).isin([1, 28, 34])
        ].copy()
        sin_long['MOTIVO_INCONSISTENCIA'] = 'Sin LONGITUDE'

        for predio in sin_long['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin LONGITUDE')

        inconsistencias['SIN_LONGITUD'] = {
            'total': len(sin_long),
            'predios_unicos': sin_long['ID_PREDIO'].nunique(),
            'detalle': sin_long.drop_duplicates('ID_PREDIO')
        }

        sin_lat = df[df['LATITUDE'].isna()].copy()
        sin_lat['MOTIVO_INCONSISTENCIA'] = 'Sin LATITUDE'

        for predio in sin_lat['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin LATITUDE')

        inconsistencias['SIN_LATITUD'] = {
            'total': len(sin_lat),
            'predios_unicos': sin_lat['ID_PREDIO'].nunique(),
            'detalle': sin_lat.drop_duplicates('ID_PREDIO')
        }

    # ------------------------------------------------------------------
    # 3️⃣ USO_LADM
    # ------------------------------------------------------------------
    if validar_uso_ladm:

        # SIN USO_LADM
        sin_uso_ladm = df[
            df['USO_LADM'].isna() |
            (df['USO_LADM'].astype(str).str.strip() == '')
        ].copy()

        sin_uso_ladm['MOTIVO_INCONSISTENCIA'] = 'Sin USO_LADM'

        for predio in sin_uso_ladm['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin USO_LADM')

        inconsistencias['SIN_USO_LADM'] = {
            'total': len(sin_uso_ladm),
            'predios_unicos': sin_uso_ladm['ID_PREDIO'].nunique(),
            'detalle': sin_uso_ladm.drop_duplicates('ID_PREDIO')
        }

        # USO_LADM inconsistente
        uso_ph = df[
            df['USO_LADM'].notna() &
            df['USO_LADM'].astype(str).str.contains('_PH', na=False) &
            (~df['CONDICION'].isin([8, 9]))
        ].copy()

        uso_ph['MOTIVO_INCONSISTENCIA'] = 'USO _PH sin CONDICION 8 o 9'

        for predio in uso_ph['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('USO_LADM inconsistente')

        inconsistencias['USO_INCONSISTENTE'] = {
            'total': len(uso_ph),
            'predios_unicos': uso_ph['ID_PREDIO'].nunique(),
            'detalle': uso_ph
        }

    # ------------------------------------------------------------------
    # 4️⃣ CONSTRUCCIONES
    # ------------------------------------------------------------------
    if validar_construcciones:

        codigos_ok = [6, 7, 8, 27, 36, 37]

        # SIN PUNTAJE CONDICIONADO
        sin_puntaje_cond = df[
            (
                (
                    (df['DESTINOCONS'].fillna(0) > 0) &
                    (~df['DESTINOCONS'].fillna(0).isin(codigos_ok)) &
                    (df['PUNTCONS'].fillna(0) == 0)
                )
                |
                (
                    (df['DESTANEX'].fillna(0) > 0) &
                    (df['TIPOANEXO'].fillna(0) == 0)
                )
            )
        ].copy()

        sin_puntaje_cond['MOTIVO_INCONSISTENCIA'] = 'Sin puntaje condicionado'

        for predio in sin_puntaje_cond['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin puntaje')

        inconsistencias['SIN_PUNTAJE'] = {
            'total': len(sin_puntaje_cond),
            'predios_unicos': sin_puntaje_cond['ID_PREDIO'].nunique(),
            'detalle': sin_puntaje_cond.drop_duplicates('ID_PREDIO')
        }

        # SIN AREA CONSTRUIDA
        sin_area = df[
            df['AREA_CONST'].fillna(0) == 0
        ].copy()

        sin_area['MOTIVO_INCONSISTENCIA'] = 'Sin área construida'

        for predio in sin_area['ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('Sin área')

        inconsistencias['SIN_AREA_CONSTRUIDA'] = {
            'total': len(sin_area),
            'predios_unicos': sin_area['ID_PREDIO'].nunique(),
            'detalle': sin_area.drop_duplicates('ID_PREDIO')
        }

    # ------------------------------------------------------------------
    # 5️⃣ DATAFRAME LIMPIO
    # ------------------------------------------------------------------
    lista_predios = list(predios_con_inconsistencias.keys())
    df_limpio = df[~df['ID_PREDIO'].isin(lista_predios)].copy()

    # ------------------------------------------------------------------
    # 6️⃣ EXPORTAR EXCEL
    # ------------------------------------------------------------------
    os.makedirs(output_path, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d')
    archivo = f"{output_path}reporte_pre_inconsistencias_{timestamp}.xlsx"

    total_predios = df['ID_PREDIO'].nunique()

    with pd.ExcelWriter(archivo, engine='openpyxl') as writer:

        resumen = [{
            'Tipo': k,
            'Registros': v['total'],
            'Predios': v['predios_unicos'],
            '% Predios': round(v['predios_unicos'] / total_predios * 100, 2)
        } for k, v in inconsistencias.items()]

        pd.DataFrame(resumen).to_excel(writer, sheet_name='RESUMEN', index=False)

        for nombre, data in inconsistencias.items():
            if len(data['detalle']) > 0:
                data['detalle'].to_excel(
                    writer,
                    sheet_name=nombre[:31],
                    index=False
                )

    print(f"\n✅ Archivo generado: {archivo}")
    print(f"✅ Predios limpios: {df_limpio['ID_PREDIO'].nunique()}")

    return df_limpio