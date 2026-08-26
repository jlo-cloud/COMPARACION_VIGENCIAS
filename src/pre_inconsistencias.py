import pandas as pd
import numpy as np
from datetime import datetime
import os

# Motivos que ADEMAS de reportarse descuentan el predio de la liquidacion.
#
# "Sin ZHF" reporta y NO descuenta: las tres familias tienen camino alterno
# cuando la ZHF no sirve -residencial y edificios deciden por ESTRPRED,
# comercial cae a T3_COMERCIAL_022 e industrial a T4_INDUSTRIAL_032-, y de
# hecho las 31.282 construcciones sin ZHF que hay en el reporte se liquidaron
# todas, ninguna quedo sin valor. Se reportan para pedir la correccion del
# dato, no para sacar el predio. Las coordenadas, igual: no participan en la
# asignacion de tabla.
#
# Los otros cuatro si impiden liquidar: sin uso no hay tabla que asignar, sin
# puntaje no hay fila que consultar, sin area el valor sale en cero, y el
# conflicto de uso contra condicion es un dato que hay que corregir en la base
# antes de poder valorar el predio.
MOTIVOS_QUE_DESCUENTAN = {
    'Sin ZHF comercial/industrial',
    'Sin USO_LADM',
    'USO_LADM inconsistente',
    'Sin puntaje',
    'Sin área',
}


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
            """
            Sin ZHF utilizable: nulo, cero, o menos de 6 digitos.

            Antes se exigian 11 caracteres exactos, y no funcionaba: el ZHF
            llega como ENTERO, asi que los que empiezan por cero pierden esas
            posiciones -08634801 se guarda como 8634801- y quedaban marcados
            sin tener nada malo. Ademas hay 299.388 filas de 13 digitos, que
            tampoco median 11. Con la regla vieja caian 329.774 predios; sin
            ZHF de verdad son 46.609, los que traen 0.
            """
            if pd.isna(zhf):
                return True
            zhf_str = str(zhf).strip()
            if zhf_str.endswith('.0'):          # por si llega como flotante
                zhf_str = zhf_str[:-2]
            if zhf_str in ['', 'nan', 'None']:
                return True
            if not zhf_str.isdigit():
                return True
            return int(zhf_str) == 0 or len(zhf_str) < 6

        sin_zhf = df[df['ZHF'].apply(es_zhf_invalido)].copy()

        # Sin ZHF NO pesa igual segun la familia:
        #
        # - Residencial y edificios tienen con que suplirla: cuando la ZHF no
        #   sirve, la tabla la decide el ESTRPRED del predio. Se liquidan bien,
        #   asi que solo se reportan para pedir la correccion del dato.
        # - Comercial e industrial NO tienen con que suplirla. Su respaldo era
        #   caer a una tabla fija -T3_COMERCIAL_022, T4_INDUSTRIAL_032-, que da
        #   el mismo VM2 sin importar donde este el predio ni su estrato. Sin
        #   zona no hay como valorarlos, asi que el predio se descuenta.
        #
        # Los destinos son los mismos que usa Liquidacion_tablas.py para armar
        # TABLA_ORIGEN, ya homologados y como entero.
        DESTINOS_COMERCIAL = [16, 21, 24, 25, 28, 39, 41, 49]
        DESTINOS_INDUSTRIAL = [9, 18, 47, 48]
        _dest = pd.to_numeric(sin_zhf['DESTINOCONS'], errors='coerce').fillna(0)
        es_com_ind = _dest.isin(DESTINOS_COMERCIAL + DESTINOS_INDUSTRIAL)

        sin_zhf['MOTIVO_INCONSISTENCIA'] = np.where(
            es_com_ind,
            'Sin ZHF en comercial o industrial: no hay con que suplirla',
            'Sin ZHF o ZHF inválido')

        for predio in sin_zhf.loc[es_com_ind, 'ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append(
                'Sin ZHF comercial/industrial')
        for predio in sin_zhf.loc[~es_com_ind, 'ID_PREDIO'].unique():
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

        # USO_LADM inconsistente, en las DOS direcciones. Antes solo se miraba
        # la primera, que son 12 casos; la segunda son miles y nadie la veia.
        #
        # Los ANEXOS quedan fuera de esta validacion: el anexo no trae uso
        # propio, asi que su USO_LADM no dice nada sobre que condicion deberia
        # tener y compararlos solo produce ruido.
        es_anexo = pd.to_numeric(df['DESTANEX'], errors='coerce').fillna(0) > 0
        uso_txt = df['USO_LADM'].astype(str)
        tiene_ph = uso_txt.str.contains('_PH', case=False, na=False)
        cond_num = pd.to_numeric(df['CONDICION'], errors='coerce').fillna(0)

        # En las 7 comunas el residencial NO se separa por condicion: el
        # consolidado trae T1_RESIDENCIAL_7C_011..016 y ninguna columna
        # COND_9. Alli una condicion 9 mal puesta no desvia el valor a ningun
        # lado -las 20.605 construcciones de PH de ese grupo se valoran con la
        # misma tabla que las demas-, asi que se reporta pero NO se descuenta
        # el predio. En las 10 comunas si hay COND_9 y la condicion equivocada
        # manda la construccion a la tabla de PH: eso si impide liquidar bien.
        try:
            from tabla_construccion import COMUNAS_7
        except Exception:                                    # pragma: no cover
            COMUNAS_7 = ['02', '03', '04', '08', '17', '19', '22']
        es_7c = (df['COMUNA'].astype(str).str.strip().str.zfill(2)
                 .isin(COMUNAS_7))

        # a) el uso dice PH pero la condicion no es de PH
        falla_a = tiene_ph & ~cond_num.isin([8, 9])
        # b) el uso NO dice PH pero viene con condicion 9, donde eso cambia
        #    la tabla que le toca
        falla_b = ~tiene_ph & (cond_num == 9) & ~es_7c
        # c) lo mismo en las 7 comunas, donde no cambia nada: solo se reporta
        falla_c = ~tiene_ph & (cond_num == 9) & es_7c

        uso_ph = df[df['USO_LADM'].notna() & ~es_anexo &
                    (falla_a | falla_b | falla_c)].copy()

        uso_ph['MOTIVO_INCONSISTENCIA'] = np.select(
            [falla_a[uso_ph.index], falla_b[uso_ph.index]],
            ['USO _PH sin CONDICION 8 o 9', 'USO sin _PH con CONDICION 9'],
            default='USO sin _PH con CONDICION 9 (7 comunas, no afecta el valor)')

        # El predio se descuenta solo si su inconsistencia cambia la tabla.
        pesa = uso_ph['MOTIVO_INCONSISTENCIA'] != (
            'USO sin _PH con CONDICION 9 (7 comunas, no afecta el valor)')
        for predio in uso_ph.loc[pesa, 'ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append('USO_LADM inconsistente')
        for predio in uso_ph.loc[~pesa, 'ID_PREDIO'].unique():
            predios_con_inconsistencias.setdefault(predio, []).append(
                'USO_LADM inconsistente sin efecto')

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
    a_descontar = [pid for pid, motivos in predios_con_inconsistencias.items()
                   if any(m in MOTIVOS_QUE_DESCUENTAN for m in motivos)]
    solo_reporte = len(predios_con_inconsistencias) - len(a_descontar)
    df_limpio = df[~df['ID_PREDIO'].isin(a_descontar)].copy()
    print("")
    print(f"   Predios con alguna inconsistencia : {len(predios_con_inconsistencias):,}")
    print(f"   De esos, se descuentan            : {len(a_descontar):,}")
    print(f"   Solo se reportan (siguen)         : {solo_reporte:,}")

    # ------------------------------------------------------------------
    # 6️⃣ EXPORTAR EXCEL
    # ------------------------------------------------------------------
    os.makedirs(output_path, exist_ok=True)
    timestamp = datetime.now().strftime('%Y%m%d')
    archivo = f"{output_path}reporte_pre_inconsistencias_{timestamp}.xlsx"

    total_predios = df['ID_PREDIO'].nunique()

    # xlsxwriter y no openpyxl: openpyxl escribe celda por celda y con
    # decenas de miles de filas por ~70 columnas la corrida se cuelga.
    motor = 'xlsxwriter'
    try:
        import xlsxwriter  # noqa: F401
    except ImportError:
        motor = 'openpyxl'

    with pd.ExcelWriter(archivo, engine=motor) as writer:

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