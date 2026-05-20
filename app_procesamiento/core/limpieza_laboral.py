from __future__ import annotations

import pandas as pd


VALORES_BASURA = ["-", "--", "5"]

NORMALIZACION_NOMBRE_ENTIDAD = {
    "electro sur este": "ELECTRO SUR ESTE S.A.A.",
    "inei": "INSTITUTO NACIONAL DE ESTADISTICA E INFORMATICA",
    "minedu": "MINISTERIO DE EDUCACION",
    "municipalidad provincial de angaraes": "MUNICIPALIDAD PROVINCIAL ANGARAES LIRCAY",
    "pescs": "PROYECTO ESPECIAL SIERRA CENTRO SUR",
    "provias nacional": "PROYECTO ESPECIAL DE INFRAESTRUCTURA DE TRANSPORTE NACIONAL",
    "ugel cotabambas": "UNIDAD DE GESTION EDUCATIVA LOCAL COTABAMBAS",
    "universidad nacional del altiplano": "UNIVERSIDAD NACIONAL DEL ALTIPLANO PUNO",
    "gerencia regional de educación cusco": "GERENCIA REGIONAL DE EDUCACION CUSCO",
    "municipalidad de la esperanza": "MUNICIPALIDAD DISTRITAL DE LA ESPERANZA",
    "municipalidad distrital de ollachea": "MUNICIPALIDAD DISTRITAL OLLACHEA",
}


def es_vacio(serie: pd.Series) -> pd.Series:
    texto = serie.astype(str).str.strip()
    return serie.isna() | texto.isin(["", "-"]) | texto.str.lower().isin(["nan", "none"])


def sit(df: pd.DataFrame) -> pd.Series:
    return df["situacion_laboral"].astype(str).str.strip()


def tipo(df: pd.DataFrame) -> pd.Series:
    return df["tipo_entidad"].astype(str).str.strip()


def asegurar_columnas(df: pd.DataFrame, columnas: list[str]) -> pd.DataFrame:
    for columna in columnas:
        if columna not in df.columns:
            df[columna] = ""
    return df


def asignar_texto(df: pd.DataFrame, mask: pd.Series, columna: str, valor: str) -> None:
    if columna not in df.columns:
        return

    df[columna] = df[columna].astype("object")
    df.loc[mask, columna] = valor


def normalizar_nombre_entidad(
    df: pd.DataFrame,
    normalizacion_extra: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, int]:
    if "nombre_entidad" not in df.columns:
        return df, 0

    normalizacion = {**NORMALIZACION_NOMBRE_ENTIDAD, **(normalizacion_extra or {})}
    nombre_lower = df["nombre_entidad"].astype(str).str.strip().str.lower()
    mask_norm = nombre_lower.isin(normalizacion)

    df.loc[mask_norm, "nombre_entidad"] = nombre_lower[mask_norm].map(normalizacion)
    df["nombre_entidad"] = df["nombre_entidad"].astype(str).str.strip().str.upper()

    return df, int(mask_norm.sum())


def aplicar_reglas_limpieza_inicial(
    df: pd.DataFrame,
    normalizacion_nombres: dict[str, str] | None = None,
) -> tuple[pd.DataFrame, int]:
    df = asegurar_columnas(
        df,
        ["nombre_entidad", "ruc", "tipo_entidad", "situacion_laboral", "tipo_actividad"],
    )

    df, nombres_normalizados = normalizar_nombre_entidad(df, normalizacion_nombres)

    df.loc[sit(df) == "Estudiante", "situacion_laboral"] = "No labora actualmente"

    for col in ["nombre_entidad", "ruc"]:
        df[col] = (
            df[col]
            .astype(str)
            .str.strip()
            .replace(VALORES_BASURA, "")
            .replace(["nan", "NAN", "None"], "")
        )

    mask_3 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Independiente y otros")
        & es_vacio(df["situacion_laboral"])
    )
    df.loc[mask_3, "situacion_laboral"] = "Trabajador independiente"

    mask_4 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Independiente y otros")
        & (sit(df) == "Trabajador del sector privado")
    )
    df.loc[mask_4, "situacion_laboral"] = "Trabajador independiente"

    df.loc[sit(df) == "No labora actualmente", "tipo_entidad"] = "No labora actualmente"

    mask_6 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "-")
        & (sit(df) == "Trabajador independiente")
    )
    df.loc[mask_6, "tipo_entidad"] = "Independiente y otros"

    mask_7 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & tipo(df).isin(["Empresa u organización privada", "Entidad privada"])
        & ~sit(df).isin(["Trabajador del sector público", "No labora actualmente"])
    )
    df.loc[mask_7, "tipo_entidad"] = "Independiente y otros"
    df.loc[mask_7, "situacion_laboral"] = "Trabajador independiente"

    mask_8 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & es_vacio(df["tipo_entidad"])
        & (sit(df) == "Trabajador independiente")
    )
    df.loc[mask_8, "tipo_entidad"] = "Independiente y otros"

    mask_9 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & es_vacio(df["tipo_entidad"])
        & (sit(df) == "Trabajador dependiente")
    )
    df.loc[mask_9, "tipo_entidad"] = "Independiente y otros"
    df.loc[mask_9, "situacion_laboral"] = "Trabajador independiente"

    mask_10 = sit(df) == "Emprendedor / negocio propio"
    df.loc[mask_10, "situacion_laboral"] = "Trabajador independiente"
    df.loc[mask_10, "tipo_entidad"] = "Independiente y otros"

    mask_11 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Entidad pública")
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_11, "situacion_laboral"] = "Trabajador dependiente"

    mask_12 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Independiente y otros")
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_12, "situacion_laboral"] = "Trabajador dependiente"

    mask_13 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & es_vacio(df["tipo_entidad"])
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_13, "situacion_laboral"] = "Trabajador dependiente"
    df.loc[mask_13, "tipo_entidad"] = "Independiente y otros"

    mask_14 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & es_vacio(df["tipo_entidad"])
        & es_vacio(df["situacion_laboral"])
    )
    df.loc[mask_14, "situacion_laboral"] = "No labora actualmente"
    df.loc[mask_14, "tipo_entidad"] = "No labora actualmente"

    df["tipo_entidad"] = df["tipo_entidad"].replace(
        {
            "Empresa u organización privada": "Entidad privada",
            "Empresa u organizaciÃ³n privada": "Entidad privada",
        }
    )

    mask_16 = (
        es_vacio(df["ruc"])
        & (tipo(df) == "Entidad pública")
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_16, "situacion_laboral"] = "Trabajador dependiente"

    mask_17 = (
        es_vacio(df["ruc"])
        & ~es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Entidad privada")
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_17, "situacion_laboral"] = "Trabajador dependiente"

    mask_18 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & (tipo(df) == "Entidad privada")
        & (sit(df) == "Trabajador del sector público")
    )
    df.loc[mask_18, "situacion_laboral"] = "Trabajador independiente"
    df.loc[mask_18, "tipo_entidad"] = "Independiente y otros"

    base_19 = (
        es_vacio(df["ruc"])
        & es_vacio(df["nombre_entidad"])
        & es_vacio(df["situacion_laboral"])
    )
    df.loc[base_19 & (tipo(df) == "Entidad pública"), "situacion_laboral"] = (
        "Trabajador dependiente"
    )

    mask_19b = base_19 & (tipo(df) == "Entidad privada")
    df.loc[mask_19b, "situacion_laboral"] = "Trabajador independiente"
    df.loc[mask_19b, "tipo_entidad"] = "Independiente y otros"

    df.loc[base_19 & (tipo(df) == "Independiente y otros"), "situacion_laboral"] = (
        "Trabajador independiente"
    )

    sit_vacia = es_vacio(df["situacion_laboral"])
    df.loc[sit_vacia & tipo(df).isin(["Entidad privada", "Entidad pública"]), "situacion_laboral"] = (
        "Trabajador dependiente"
    )
    df.loc[sit_vacia & (tipo(df) == "Independiente y otros"), "situacion_laboral"] = (
        "Trabajador independiente"
    )

    return df, nombres_normalizados


def aplicar_correcciones_post_match(df: pd.DataFrame) -> pd.DataFrame:
    df = asegurar_columnas(df, ["match_entidad", "ruc", "nombre_entidad", "tipo_entidad"])

    mask_sector_privado_ruc_personal = (
        (df["match_entidad"] == "NO")
        & (sit(df) == "Trabajador del sector privado")
        & (tipo(df) == "Entidad privada")
        & df["ruc"].astype(str).str.strip().str.startswith("10")
    )
    df.loc[mask_sector_privado_ruc_personal, "situacion_laboral"] = "Trabajador independiente"
    df.loc[mask_sector_privado_ruc_personal, "tipo_entidad"] = "Independiente y otros"
    df.loc[mask_sector_privado_ruc_personal, "tipo_actividad"] = "Otros"

    ruc_str = df["ruc"].astype(str).str.strip()
    ruc_cond = ruc_str.isin(["0", ""]) | ruc_str.str.startswith("10")
    base = (
        (df["match_entidad"] == "NO")
        & es_vacio(df["nombre_entidad"])
        & ruc_cond
    )

    mask_ind = base & (sit(df) == "Trabajador independiente")
    df.loc[mask_ind, "tipo_entidad"] = "Independiente y otros"

    mask_dep_no_publica = base & (sit(df) == "Trabajador dependiente") & (tipo(df) != "Entidad pública")
    df.loc[mask_dep_no_publica, "tipo_entidad"] = "Independiente y otros"
    df.loc[mask_dep_no_publica, "situacion_laboral"] = "Trabajador independiente"

    mask_dep_publica = base & (sit(df) == "Trabajador dependiente") & (tipo(df) == "Entidad pública")
    df.loc[mask_dep_publica, "nombre_entidad"] = "INDEPENDIENTE Y OTROS"

    return df


def normalizar_columnas_por_situacion_laboral(df: pd.DataFrame) -> pd.DataFrame:
    df = asegurar_columnas(
        df,
        ["situacion_laboral", "tipo_entidad", "ruc", "nombre_entidad", "nivel_gobierno"],
    )
    nc = "No corresponde"

    mask_dep_pub = (sit(df) == "Trabajador dependiente") & (tipo(df) == "Entidad pública")
    for col in [
        "clasificacion_empresa",
        "rubro_organizacion",
        "tipo_actividad",
        "cuenta_con_ruc",
        "numero_ruc_independiente",
        "rubro_organizacion_independiente",
        "ambito_desempeno",
        "otros_ambito",
    ]:
        asignar_texto(df, mask_dep_pub, col, nc)

    mask_dep_pub_indep = (
        mask_dep_pub
        & (df["ruc"].astype(str).str.strip() == "0")
        & (df["nombre_entidad"].astype(str).str.strip() == "INDEPENDIENTE Y OTROS")
        & es_vacio(df["nivel_gobierno"])
    )
    asignar_texto(df, mask_dep_pub_indep, "nivel_gobierno", "-")

    mask_dep_pri = (sit(df) == "Trabajador dependiente") & (tipo(df) == "Entidad privada")
    asignar_texto(df, mask_dep_pri, "nivel_gobierno", "-")
    for col in [
        "perfil",
        "regimen_laboral",
        "nombre_jefe_rrhh",
        "correo_jefe_rrhh",
        "telefono_jefe_rrhh",
        "tipo_actividad",
        "cuenta_con_ruc",
        "numero_ruc_independiente",
        "rubro_organizacion_independiente",
    ]:
        asignar_texto(df, mask_dep_pri, col, nc)

    mask_ind = sit(df) == "Trabajador independiente"
    asignar_texto(df, mask_ind, "nivel_gobierno", "-")
    asignar_texto(df, mask_ind, "nombre_entidad", "INDEPENDIENTE Y OTROS")
    for col in [
        "perfil",
        "regimen_laboral",
        "nombre_jefe_rrhh",
        "correo_jefe_rrhh",
        "telefono_jefe_rrhh",
        "clasificacion_empresa",
        "rubro_organizacion",
        "ambito_desempeno",
        "otros_ambito",
    ]:
        asignar_texto(df, mask_ind, col, nc)

    mask_no_lab = sit(df) == "No labora actualmente"
    for col in [
        "nivel_gobierno",
        "nombre_entidad",
        "ruc",
        "perfil",
        "regimen_laboral",
        "nombre_jefe_rrhh",
        "correo_jefe_rrhh",
        "telefono_jefe_rrhh",
        "clasificacion_empresa",
        "rubro_organizacion",
        "tipo_actividad",
        "cuenta_con_ruc",
        "numero_ruc_independiente",
        "rubro_organizacion_independiente",
        "ambito_desempeno",
        "otros_ambito",
    ]:
        asignar_texto(df, mask_no_lab, col, nc)

    return df
