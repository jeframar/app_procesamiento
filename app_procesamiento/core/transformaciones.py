import re
import unicodedata

import pandas as pd

from app_procesamiento.core.columnas import renumerar_id_por_apellidos_nombres
from app_procesamiento.core.mapeos import (
    MAP_CLASIFICACION_EMPRESA,
    MAP_GRADO,
    MAP_PERFIL,
    MAP_RUBRO_ORGANIZACION,
    VALORES_MYPE_NO,
    VALORES_MYPE_SI,
)
from app_procesamiento.core.limpieza_laboral import (
    normalizar_columna_rnp,
    normalizar_perfil_entidad_publica_por_rnp,
    normalizar_perfil_independiente_por_rnp,
    normalizar_perfil_proveedor_por_tipo_entidad_rnp,
)
from app_procesamiento.core.utils import (
    completar_nulos,
    formatear_fecha,
    normalizar_dni_para_merge,
    normalizar_nombre_persona,
    normalizar_celular,
    normalizar_region,
    normalizar_ruc,
)


PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _normalizar_clave_clasificacion(valor) -> str:
    if pd.isna(valor):
        return ""

    texto = str(valor).strip().upper()
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    texto = re.sub(r"[^A-Z0-9]+", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def _asegurar_claves_merge(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if "_dni_merge" not in df.columns:
        if "DNI" in df.columns:
            df["_dni_merge"] = normalizar_dni_para_merge(df["DNI"])
        else:
            df["_dni_merge"] = ""

    if "_nombre_merge" not in df.columns:
        if "nombres_apellidos" in df.columns:
            df["_nombre_merge"] = normalizar_nombre_persona(df["nombres_apellidos"])
        else:
            df["_nombre_merge"] = ""

    return df


def _mapear_ids_unicos(df: pd.DataFrame, columna_clave: str, columna_id: str) -> dict:
    claves = df[columna_clave].fillna("").astype(str)
    mask = claves != ""
    conteos = claves[mask].value_counts()
    claves_unicas = set(conteos[conteos == 1].index)

    if not claves_unicas:
        return {}

    candidatos = df.loc[mask & claves.isin(claves_unicas), [columna_clave, columna_id]]
    return candidatos.set_index(columna_clave)[columna_id].to_dict()


def _contar_claves_ambiguas(df: pd.DataFrame, columna_clave: str) -> int:
    claves = df[columna_clave].fillna("").astype(str)
    conteos = claves[claves != ""].value_counts()
    return int((conteos > 1).sum())


def _fusionar_columnas_llave(
    df: pd.DataFrame,
    columnas: list[str],
    sufijo_derecha: str,
) -> pd.DataFrame:
    for columna in columnas:
        columna_derecha = f"{columna}{sufijo_derecha}"
        if columna in df.columns and columna_derecha in df.columns:
            df[columna] = df[columna].combine_first(df[columna_derecha])
            df = df.drop(columns=[columna_derecha])
        elif columna_derecha in df.columns:
            df = df.rename(columns={columna_derecha: columna})

    return df


def merge_por_dni_o_nombre(
    izquierda: pd.DataFrame,
    derecha: pd.DataFrame,
    nombre_derecha: str,
    suffixes=("", "_der"),
) -> pd.DataFrame:
    izquierda = _asegurar_claves_merge(izquierda).reset_index(drop=True)
    derecha = _asegurar_claves_merge(derecha).reset_index(drop=True)
    izquierda["__left_id"] = range(len(izquierda))
    derecha["__right_id"] = range(len(derecha))

    pares: list[dict] = []
    left_matched: set[int] = set()
    right_matched: set[int] = set()

    left_dni = _mapear_ids_unicos(izquierda, "_dni_merge", "__left_id")
    right_dni = _mapear_ids_unicos(derecha, "_dni_merge", "__right_id")
    for clave in sorted(set(left_dni) & set(right_dni)):
        left_id = int(left_dni[clave])
        right_id = int(right_dni[clave])
        pares.append({"__left_id": left_id, "__right_id": right_id, "__merge_metodo": "DNI"})
        left_matched.add(left_id)
        right_matched.add(right_id)

    izquierda_restante = izquierda.loc[~izquierda["__left_id"].isin(left_matched)]
    derecha_restante = derecha.loc[~derecha["__right_id"].isin(right_matched)]
    left_nombre = _mapear_ids_unicos(izquierda_restante, "_nombre_merge", "__left_id")
    right_nombre = _mapear_ids_unicos(derecha_restante, "_nombre_merge", "__right_id")
    for clave in sorted(set(left_nombre) & set(right_nombre)):
        left_id = int(left_nombre[clave])
        right_id = int(right_nombre[clave])
        pares.append(
            {"__left_id": left_id, "__right_id": right_id, "__merge_metodo": "nombre"}
        )
        left_matched.add(left_id)
        right_matched.add(right_id)

    for left_id in izquierda.loc[
        ~izquierda["__left_id"].isin(left_matched), "__left_id"
    ]:
        pares.append({"__left_id": int(left_id), "__right_id": pd.NA, "__merge_metodo": "solo_izquierda"})

    for right_id in derecha.loc[
        ~derecha["__right_id"].isin(right_matched), "__right_id"
    ]:
        pares.append({"__left_id": pd.NA, "__right_id": int(right_id), "__merge_metodo": "solo_derecha"})

    puente = pd.DataFrame(pares)
    df = (
        puente.merge(izquierda, on="__left_id", how="left")
        .merge(derecha, on="__right_id", how="left", suffixes=suffixes)
    )

    df = _fusionar_columnas_llave(
        df,
        ["DNI", "_dni_original", "_dni_merge", "_nombre_merge"],
        suffixes[1],
    )

    total_dni = sum(1 for par in pares if par["__merge_metodo"] == "DNI")
    total_nombre = sum(1 for par in pares if par["__merge_metodo"] == "nombre")
    total_solo_izquierda = sum(1 for par in pares if par["__merge_metodo"] == "solo_izquierda")
    total_solo_derecha = sum(1 for par in pares if par["__merge_metodo"] == "solo_derecha")
    ambiguos_dni_izq = _contar_claves_ambiguas(izquierda, "_dni_merge")
    ambiguos_dni_der = _contar_claves_ambiguas(derecha, "_dni_merge")
    ambiguos_nombre_izq = _contar_claves_ambiguas(izquierda_restante, "_nombre_merge")
    ambiguos_nombre_der = _contar_claves_ambiguas(derecha_restante, "_nombre_merge")

    print(
        f"Merge con {nombre_derecha}: "
        f"{total_dni} por DNI, "
        f"{total_nombre} por nombre, "
        f"{total_solo_izquierda} solo base, "
        f"{total_solo_derecha} solo {nombre_derecha}."
    )

    if any([ambiguos_dni_izq, ambiguos_dni_der, ambiguos_nombre_izq, ambiguos_nombre_der]):
        print(
            f"INCIDENTE: merge con {nombre_derecha} omitio llaves ambiguas "
            f"(DNI base={ambiguos_dni_izq}, DNI {nombre_derecha}={ambiguos_dni_der}, "
            f"nombre base={ambiguos_nombre_izq}, nombre {nombre_derecha}={ambiguos_nombre_der})."
        )

    return df.drop(columns=["__left_id", "__right_id", "__merge_metodo"], errors="ignore")


def unir_fuentes(calificados: pd.DataFrame, actividades: pd.DataFrame) -> pd.DataFrame:
    total_calificados = len(calificados)
    total_actividades = len(actividades)

    if total_calificados != total_actividades:
        print(
            "INCIDENTE: calificaciones y actividades tienen distinto numero "
            "de registros antes del merge. "
            "Conteo despues de leer/normalizar los archivos "
            f"(calificaciones_procesadas={total_calificados}, "
            f"actividades_procesadas={total_actividades}, "
            f"diferencia={abs(total_calificados - total_actividades)})."
        )

    return merge_por_dni_o_nombre(
        calificados,
        actividades,
        "actividades",
        suffixes=("", "_act"),
    )


def eliminar_columnas_basura(df: pd.DataFrame) -> pd.DataFrame:
    def es_fecha(columna) -> bool:
        if isinstance(columna, pd.Timestamp):
            return True
        return isinstance(columna, str) and bool(PATRON_FECHA.match(columna))

    cols_fecha = [c for c in df.columns if es_fecha(c)]
    if cols_fecha:
        df = df.drop(columns=cols_fecha)

    columnas = df.columns.astype(str)
    return df.loc[:, ~(columnas.str.startswith("Unnamed") | (columnas == ""))]


def normalizar_nivel_certificacion(df: pd.DataFrame) -> pd.DataFrame:
    if not {"certificacion", "nivel_certificacion"}.issubset(df.columns):
        return df

    cert = df["certificacion"].fillna("").astype(str).str.strip().str.upper()
    nivel = df["nivel_certificacion"].fillna("").astype(str).str.strip()

    mask_si = cert == "SI"
    df.loc[mask_si & (nivel == "No cuento con certificación"), "nivel_certificacion"] = "No indica"
    df.loc[cert == "", "nivel_certificacion"] = "No indica"

    nivel_actual = df["nivel_certificacion"].fillna("").astype(str).str.strip()
    df.loc[(cert == "NO") & (nivel_actual == ""), "nivel_certificacion"] = (
        "No cuento con certificación"
    )

    return df


def normalizar_clasificacion_empresa(df: pd.DataFrame) -> pd.DataFrame:
    if "clasificacion_empresa" not in df.columns:
        return df

    clasificacion = df["clasificacion_empresa"].fillna("").astype(str).str.strip()
    if "tipo_entidad" in df.columns:
        tipo_entidad = df["tipo_entidad"].fillna("").astype(str).str.strip()
        mask_privada = tipo_entidad == "Entidad privada"
    else:
        mask_privada = pd.Series(False, index=df.index)

    if mask_privada.any():
        clasificacion_privada = clasificacion[mask_privada]
        claves = clasificacion_privada.map(_normalizar_clave_clasificacion)
        df.loc[mask_privada, "clasificacion_empresa"] = (
            claves.map(MAP_CLASIFICACION_EMPRESA)
            .fillna(clasificacion_privada)
            .mask(clasificacion_privada.isin(["", "-"]), "No indica")
        )

    clasificacion_mype = df["clasificacion_empresa"].fillna("").astype(str).str.strip()
    mype = df["clasificacion_empresa"].copy().astype("object")
    mype.loc[mask_privada] = "No determinado"
    mype.loc[mask_privada & clasificacion_mype.isin(VALORES_MYPE_SI)] = "S\u00ed"
    mype.loc[mask_privada & clasificacion_mype.isin(VALORES_MYPE_NO)] = "No"
    mype.loc[mask_privada & (clasificacion_mype == "No indica")] = "No indica"
    df["MYPE"] = mype

    return df


def normalizar_rubro_organizacion(df: pd.DataFrame) -> pd.DataFrame:
    if "rubro_organizacion" not in df.columns:
        return df

    mask_con_valor = df["rubro_organizacion"].notna()
    rubro = df.loc[mask_con_valor, "rubro_organizacion"].astype(str).str.strip()
    df.loc[mask_con_valor, "rubro_organizacion"] = rubro.replace(MAP_RUBRO_ORGANIZACION)

    return df


def normalizar_carrera_tecnica(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_columna_rnp(df)

    if "grado_instruccion" not in df.columns:
        return df

    grado = df["grado_instruccion"].astype(str).str.strip()
    mask_carrera = grado == "Carrera técnica"

    if not mask_carrera.any():
        return df

    mask_independiente = pd.Series(False, index=df.index)
    if {"rnp", "tipo_entidad"}.issubset(df.columns):
        rnp = df["rnp"].astype(str).str.strip()
        tipo_entidad = df["tipo_entidad"].astype(str).str.strip()
        mask_independiente = (rnp == "No") & (tipo_entidad == "Independiente y otros")

    df.loc[mask_carrera & mask_independiente, "grado_instruccion"] = (
        "Egresado Educación Técnica Superior"
    )
    df.loc[mask_carrera & ~mask_independiente, "grado_instruccion"] = (
        "Titulado Técnico Superior"
    )

    return df


def limpiar_campos_generales(df: pd.DataFrame) -> pd.DataFrame:
    df = normalizar_columna_rnp(df)

    if "fecha_nacimiento" in df.columns:
        df["fecha_nacimiento"] = formatear_fecha(df["fecha_nacimiento"])

    if "celular" in df.columns:
        df["celular"] = normalizar_celular(df["celular"])

    if "ruc" in df.columns:
        df["ruc"] = normalizar_ruc(df["ruc"])

    if "grado_instruccion" in df.columns:
        df["grado_instruccion"] = (
            df["grado_instruccion"].astype(str).str.strip().replace(MAP_GRADO)
        )
        df = normalizar_carrera_tecnica(df)

    if "perfil" in df.columns:
        df["perfil"] = df["perfil"].fillna("").astype(str).str.strip().replace(MAP_PERFIL)

    if "region" in df.columns:
        df["region"] = normalizar_region(df["region"])

    df = normalizar_nivel_certificacion(df)
    df = normalizar_clasificacion_empresa(df)
    df = completar_nulos(df, ["rnp"], "No indica")
    df = normalizar_perfil_entidad_publica_por_rnp(df)
    df = normalizar_perfil_independiente_por_rnp(df)
    df = normalizar_perfil_proveedor_por_tipo_entidad_rnp(df)
    df = completar_nulos(df, ["rubro_organizacion"], "-")
    df = normalizar_rubro_organizacion(df)

    return df


def eliminar_columnas_exportacion(df: pd.DataFrame) -> pd.DataFrame:
    cols_eliminar = [
        "carrera_profesional",
        "certificacion",
        "situacion_laboral",
        "regimen_laboral",
        "nombre_jefe_rrhh",
        "correo_jefe_rrhh",
        "telefono_jefe_rrhh",
        "rubro_organizacion_independiente",
        "tipo_actividad",
        "cuenta_con_ruc",
        "numero_ruc_independiente",
        "tipo_proveedor",
        "ambito_desempeno",
        "Dirección de correo",
        "Ciudad",
        "_dni_original",
        "_dni_merge",
        "_nombre_merge"
    ]
    df = df.drop(columns=cols_eliminar, errors="ignore")

    orden_bloque = [
        "rnp",
        "perfil",
        "clasificacion_empresa",
        "MYPE",
        "rubro_organizacion",
        "nivel_gobierno",
        "tipo_entidad",
        "ruc",
        "nombre_entidad",
    ]

    cols = list(df.columns)
    bloque_presente = [c for c in orden_bloque if c in cols]

    if bloque_presente:
        pos_insercion = min(cols.index(c) for c in bloque_presente)
        cols_restantes = [c for c in cols if c not in bloque_presente]
        pos_ajustada = sum(1 for c in cols[:pos_insercion] if c not in bloque_presente)
        df = df[cols_restantes[:pos_ajustada] + bloque_presente + cols_restantes[pos_ajustada:]]

    if "Ver ficha técnica" in df.columns and "region" in df.columns:
        cols = list(df.columns)
        cols.remove("Ver ficha técnica")
        cols.insert(cols.index("region") + 1, "Ver ficha técnica")
        df = df[cols]

    df = renumerar_id_por_apellidos_nombres(df)

    return df

