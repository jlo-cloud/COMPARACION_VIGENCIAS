"""
Cambios fisicos de predios: el archivo caracteristicas_unidad_<fecha>.

Trae, para cada predio que tuvo un cambio fisico, TODAS sus construcciones y
anexos como quedaron despues del cambio. Por eso el proceso borra lo que la base
tenia de esos predios y pone en su lugar estas filas (ver
aplicar_cambios_fisicos en tabla_construccion.py).

Las filas vienen con el NOMBRE del uso LADM (uso_ladm), no con el codigo, y a
veces con el codigo pegado ("025-Comercio"). Aqui se traduce a DESTINOCONS
(001-076, convencional) o DESTANEX (077-120, anexo). Ya son codigos LADM: no
pasan por la homologacion, que es para los destinos viejos de la base.

Viene del procesamiento_cambios.py de la liquidacion 2025.
"""
import re
from io import StringIO

import numpy as np
import pandas as pd

# Catalogo de usos LADM: codigo -> nombre.
USOS_LADM = '''COD\tUSO
001\tApartamentos_4_y_mas_pisos_en_PH
002\tVivienda_Colonial_en_PH
003\tApartamentos_4_y_mas_pisos
004\tBarracas
005\tCasa_Elbas
006\tDepositos_Lockers
007\tGarajes_Cubiertos
008\tGarajes_En_PH
009\tSalon_Comunal
010\tSecadero_Ropa
011\tVivienda_Colonial
012\tVivienda_Hasta_3_Pisos
013\tVivienda_Hasta_3_Pisos_En_PH
014\tVivienda_Recreacional
015\tVivienda_Recreacional_En_PH
016\tBodegas_Comerciales_Grandes_Almacenes
017\tBodegas_Comerciales
018\tBodegas_Comerciales_en_PH
019\tCentros_Comerciales_pequenios
020\tCentros_Comerciales_grandes
021\tEstacion_de_servicio
022\tCentros_Comerciales_en_PH_pequenios
023\tCentros_Comerciales_en_PH_grandes
024\tClubes_Casinos
025\tComercio
026\tComercio_Colonial
027\tComercio_Deposito_Almacenamiento
028\tComercio_en_PH
029\tHotel_Colonial
030\tHoteles
031\tHoteles_en_PH
032\tOficinas_Consultorios
033\tOficinas_Consultorios_Coloniales
034\tOficinas_Consultorios_en_PH
035\tParque_Diversiones
036\tParqueaderos
037\tParqueaderos_en_PH
038\tPensiones_y_Residencias
039\tPlaza_Mercado
040\tRestaurante_Colonial
041\tRestaurantes
042\tRestaurantes_en_PH
043\tTeatro_Cinemas
044\tTeatro_Cinemas_en_PH
045\tBodega_Casa_Bomba
046\tBodegas_Casa_Bomba_en_PH
047\tIndustrias
048\tIndustrias_en_PH
049\tTalleres
050\tAulas_de_Clases
051\tBiblioteca
052\tCarceles
053\tCasas_de_Culto
054\tClinicas_Hospitales_Centros_Medicos
055\tColegio_y_Universidades
056\tColiseos
057\tEntidad_Educativa_Colonial_Colegio_Colonial
058\tEstadios
059\tFuertes_y_Castillos
060\tIglesia
061\tIglesia_en_PH
062\tInstalaciones_Militares
063\tJardin_Infantil_en_Casa
064\tParque_Cementerio
065\tPlanetario
066\tPlaza_de_Toros
067\tPuestos_de_Salud
068\tMuseos
069\tSeminarios_Conventos
070\tTeatro
071\tUnidad_Deportiva
072\tVelodromo_Patinodromo
073\tAdministrativos
074\tFundaciones_y_ONG
075\tEntidades_del_Socorro
076\tEstaciones_y_CAI
077\tCanchas
078\tCanchas_de_Tenis
079\tCarretera
080\tCerramiento
081\tCimientos_Estructura_Muros_y_Placa_Base
082\tCocheras_Marraneras_Porquerizas
083\tConstruccion_en_Membrana_Arquitectonica
084\tContenedor
085\tCorrales
086\tEstablos_Pesebreras
087\tEstacion_Bombeo
088\tEstacion_Sistema_Transporte
089\tGalpones_Gallineros
090\tGampling
091\tHangar
092\tKioscos
093\tLagunas_de_Oxidacion
094\tMarquesinas_Patios_Cubiertos
095\tMuelles
096\tMurallas
097\tPergolas
098\tPiscinas
099\tPista_Aeropuerto
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
120\tCamaroneras'''

_cat = pd.read_csv(StringIO(USOS_LADM), sep="\t", dtype={"COD": str})
# 056 y 114 se llaman igual (Coliseos): por nombre queda el 114 y
# procesar_cambios lo pasa a 056 si la fila no trae informacion de anexo.
POR_NOMBRE = {u.lower(): int(c) for c, u in zip(_cat["COD"], _cat["USO"])}
POR_CODIGO = {int(c): u for c, u in zip(_cat["COD"], _cat["USO"])}
COLISEO_CONV, COLISEO_ANEXO = 56, 114


def codigo_uso(uso):
    """(USO_LADM, codigo) del nombre que trae el archivo; (None, None) si no
    se reconoce."""
    if uso is None or pd.isna(uso) or not str(uso).strip():
        return None, None
    texto = str(uso).strip()
    # "025-Comercio": manda el codigo.
    m = re.match(r"^(\d{1,3})\s*-", texto)
    if m and int(m.group(1)) in POR_CODIGO:
        cod = int(m.group(1))
        return POR_CODIGO[cod], cod
    clave = texto.lower()
    if clave in POR_NOMBRE:
        return POR_CODIGO[POR_NOMBRE[clave]], POR_NOMBRE[clave]
    # Nombre recortado: que termine igual, con al menos 5 letras.
    if len(clave) >= 5:
        for nombre, cod in POR_NOMBRE.items():
            if nombre.endswith(clave):
                return POR_CODIGO[cod], cod
    return None, None


def procesar_cambios(df):
    """Limpia el archivo de cambios y le pone el codigo LADM a cada fila.

    Devuelve las columnas en mayuscula, con DESTINOCONS (convencional) o
    DESTANEX (anexo) y el otro en 0. Las filas sin uso reconocido se
    conservan con los dos en 0 y USO_LADM vacio: el predio ya cambio y su base
    vieja no sirve, asi que entra igual y lo reporta pre_inconsistencias."""
    d = df.copy()
    d.columns = d.columns.str.upper().str.strip()
    vacias = d["ID_PREDIO"].isna() | (d["ID_PREDIO"].astype(str).str.strip() == "")
    d = d[~vacias].copy()
    d["ID_PREDIO"] = (pd.to_numeric(d["ID_PREDIO"], errors="coerce")
                        .astype("Int64").astype(str))

    traducido = d["USO_LADM"].map(codigo_uso)
    d["USO_ORIGEN"] = d["USO_LADM"]
    d["USO_LADM"] = traducido.str[0]
    cod = pd.to_numeric(traducido.str[1], errors="coerce").fillna(0).astype(int)
    # Coliseos: es anexo (114) si la fila trae informacion de anexo; si no,
    # convencional (056).
    info_anexo = (d["TIPO_UNIDAD_CONSTRUCCION"].astype(str).str.strip().eq("Anexo")
                  | (pd.to_numeric(d["TIPOANEXO"], errors="coerce").fillna(0) > 0)
                  | (pd.to_numeric(d["ACONANEX"], errors="coerce").fillna(0) > 0))
    coliseo_conv = (cod == COLISEO_ANEXO) & ~info_anexo
    cod = cod.where(~coliseo_conv, COLISEO_CONV)
    d.loc[coliseo_conv, "USO_LADM"] = POR_CODIGO[COLISEO_CONV]
    d["DESTINOCONS"] = np.where((cod > 0) & (cod <= 76), cod, 0)
    d["DESTANEX"] = np.where(cod > 76, cod, 0)

    for c in ("PUNTCONS", "TIPOANEXO", "TPISCONS", "ANOCONST"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).round().astype(int)
    for c in ("ACONCONS", "ACONANEX"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0.0)
    # El area de un anexo viene en ACONANEX y la de una construccion en
    # ACONCONS; si llega en la otra columna se pasa a la suya.
    anexo = d["DESTANEX"] > 0
    d["ACONANEX"] = d["ACONANEX"].mask(anexo & (d["ACONANEX"] == 0), d["ACONCONS"])
    d.loc[anexo, "ACONCONS"] = 0.0
    d["ACONCONS"] = d["ACONCONS"].mask(
        ~anexo & (d["ACONCONS"] == 0) & (d["DESTINOCONS"] > 0), d["ACONANEX"])
    d.loc[d["DESTINOCONS"] > 0, "ACONANEX"] = 0.0

    print(f"   Cambios fisicos: {len(d):,} filas de {d['ID_PREDIO'].nunique():,} "
          f"predios ({int(vacias.sum()):,} filas vacias descartadas)")
    sin = d["USO_LADM"].isna()
    print(f"   Con uso reconocido: {int((~sin).sum()):,} | sin uso: {int(sin.sum()):,}"
          + (f" {d.loc[sin, 'USO_ORIGEN'].value_counts(dropna=False).head(5).to_dict()}"
             if sin.any() else ""))
    return d
