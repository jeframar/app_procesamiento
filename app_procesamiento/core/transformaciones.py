import re

import pandas as pd

from app_procesamiento.core.utils import (
    MAP_GRADO,
    MAP_PERFIL,
    completar_nulos,
    formatear_fecha,
    normalizar_celular,
    normalizar_region,
    normalizar_ruc,
)


PATRON_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}")


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

    return calificados.merge(
        actividades,
        on="DNI",
        how="outer",
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

    return df.loc[:, ~df.columns.astype(str).str.startswith("Unnamed")]


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
    df["clasificacion_empresa"] = clasificacion.mask(clasificacion.isin(["", "-"]), "No indica")

    return df


def normalizar_carrera_tecnica(df: pd.DataFrame) -> pd.DataFrame:
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
    df = completar_nulos(df, ["rubro_org"], "-")

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
        "match_entidad"
    ]
    df = df.drop(columns=cols_eliminar, errors="ignore")

    orden_bloque = [
        "rnp",
        "perfil",
        "clasificacion_empresa",
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

    return df

