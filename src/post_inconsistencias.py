import os
import pandas as pd
from datetime import datetime

def validar_vm2_cero(df_const_salida, exportar=True, output_path='./output/'):

    print("\n" + "="*80)
    print("🔎 VALIDACIÓN: VM2_2026_COM = 0 (incluye SIN TABLA)")
    print("="*80)

    inconsistencias = {}
    predios_con_inconsistencias = {}

    # ----------------------------------------------------------------------
    # 1️⃣ CONSTRUCCIONES CON VM2_2026_COM = 0
    # ----------------------------------------------------------------------
    mask_vm2_cero = df_const_salida['VM2_2026_COM'] == 0

    sin_vm2 = df_const_salida[mask_vm2_cero].copy()

    # Motivo base
    sin_vm2['MOTIVO_INCONSISTENCIA'] = 'VM2_2026_COM = 0'

    # Marcar SIN TABLA como motivo adicional
    mask_sin_tabla = sin_vm2['TABLA_ORIGEN'] == 'SIN TABLA'
    sin_vm2.loc[mask_sin_tabla, 'MOTIVO_INCONSISTENCIA'] = (
        sin_vm2.loc[mask_sin_tabla, 'MOTIVO_INCONSISTENCIA'] + ' | SIN TABLA'
    )

    sin_vm2['CATEGORIA'] = 'VM2_CERO'

    print(
        f"\n1️⃣ CONSTRUCCIONES con VM2_2026_COM = 0: {len(sin_vm2)} "
        f"({sin_vm2['ID_PREDIO'].nunique()} predios)"
    )
    print(
        f"    └─ de los cuales SIN TABLA: {mask_sin_tabla.sum()}"
    )

    # Registrar motivos por predio
    for _, row in sin_vm2[['ID_PREDIO', 'MOTIVO_INCONSISTENCIA']].drop_duplicates().iterrows():
        pid = row['ID_PREDIO']
        motivos = row['MOTIVO_INCONSISTENCIA'].split(' | ')
        for m in motivos:
            predios_con_inconsistencias.setdefault(pid, []).append(m)

    inconsistencias['sin_vm2_detalle'] = sin_vm2.copy()

    # ----------------------------------------------------------------------
    # 2️⃣ CONSOLIDADO DE PREDIOS
    # ----------------------------------------------------------------------
    lista_predios = []

    for pid, motivos in predios_con_inconsistencias.items():

        if 'CRUCE_CAMBIOS' in df_const_salida.columns:
            cruce = (
                df_const_salida.loc[df_const_salida['ID_PREDIO'] == pid, 'CRUCE_CAMBIOS']
                .fillna(0)
                .astype(int)
                .max()
            )
        else:
            cruce = 0

        lista_predios.append({
            'ID_PREDIO': pid,
            'MOTIVOS_INCONSISTENCIA': ' | '.join(sorted(set(motivos))),
            'CANTIDAD_MOTIVOS': len(set(motivos)),
            'CRUCE_CAMBIOS': cruce
        })

    df_predios = pd.DataFrame(lista_predios)

    inconsistencias['predios'] = df_predios
    inconsistencias['total_predios'] = len(df_predios)

    # ----------------------------------------------------------------------
    # 3️⃣ RESUMEN GENERAL
    # ----------------------------------------------------------------------
    resumen = pd.DataFrame([
        ['VM2_CERO', len(sin_vm2), sin_vm2['ID_PREDIO'].nunique()],
        ['VM2_CERO + SIN TABLA', mask_sin_tabla.sum(),
         sin_vm2.loc[mask_sin_tabla, 'ID_PREDIO'].nunique()]
    ], columns=['TIPO_INCONSISTENCIA', 'CONSTRUCCIONES', 'PREDIOS'])

    print("\n" + "="*80)
    print("📊 RESUMEN GENERAL:")
    print("="*80)
    print(resumen.to_string(index=False))

    # ----------------------------------------------------------------------
    # 4️⃣ EXPORTAR
    # ----------------------------------------------------------------------
    if exportar:
        carpeta = os.path.join(output_path, "post_inconsistencias/")
        os.makedirs(carpeta, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d")
        file_xlsx = f"{carpeta}reporte_post_inconsistencias_{timestamp}.xlsx"

        with pd.ExcelWriter(file_xlsx, engine='openpyxl') as writer:
            resumen.to_excel(writer, sheet_name='RESUMEN', index=False)
            df_predios.to_excel(writer, sheet_name='PREDIOS', index=False)
            sin_vm2.to_excel(writer, sheet_name='VM2_CERO', index=False)

        print(f"\n💾 Archivo exportado en: {file_xlsx}")

    print("\n" + "="*80)
    print("✅ VALIDACIÓN COMPLETADA")
    print("="*80 + "\n")

    return inconsistencias
