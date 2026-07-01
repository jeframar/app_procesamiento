import unicodedata

import numpy as np
import pandas as pd

from app_procesamiento import config


def _fecha_emision_actual(fecha_emision: str | None) -> str:
    return fecha_emision or config.FECHA_EMISION_CERTIFICADO


def agregar_certificado_por_total(
    df: pd.DataFrame,
    crear_si_no_hay_total: bool = False,
    fecha_emision: str | None = None,
) -> pd.DataFrame:
    if "total_curso" not in df.columns:
        if crear_si_no_hay_total:
            df["certificado"] = "NO CORRESPONDE"
            df["emision_certificado"] = "-"
        return df

    fecha_emision = _fecha_emision_actual(fecha_emision)
    df["condicion"] = ""
    df["certificado"] = np.where(df["total_curso"] >= 14, "CERTIFICADO", "NO CORRESPONDE")
    df["emision_certificado"] = np.where(df["total_curso"] >= 14, fecha_emision, "-")

    return df


def _normalizar_texto(valor) -> str:
    if pd.isna(valor):
        return ""

    texto = str(valor).strip().lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(caracter for caracter in texto if not unicodedata.combining(caracter))


def _estado_finalizado(serie: pd.Series) -> pd.Series:
    return serie.map(_normalizar_texto).eq("finalizado")


def _es_columna_estado_actividad(serie: pd.Series) -> bool:
    valores = serie.map(_normalizar_texto)
    valores = valores[~valores.isin(["", "nan", "none"])]
    if valores.empty:
        return False

    estados_validos = {"finalizado", "no finalizado"}
    return bool(valores.isin(estados_validos).all())


def _es_columna_excluida_asistencia(columna) -> bool:
    nombre = _normalizar_texto(columna)
    fragmentos_excluidos = [
        "actualice sus datos",
        "grabacion",
        "encuesta",
        "constancia",
        "direccion de correo",
        "ciudad",
        "numero de id",
        "dni",
        "_dni",
        "_nombre",
    ]
    return any(fragmento in nombre for fragmento in fragmentos_excluidos)


def _columnas_asistencia_en_vivo(df: pd.DataFrame) -> list:
    return [
        columna
        for columna in df.columns
        if not _es_columna_excluida_asistencia(columna)
        and _es_columna_estado_actividad(df[columna])
    ]


def _buscar_columna_por_fragmento(df: pd.DataFrame, fragmento: str):
    fragmento = _normalizar_texto(fragmento)
    for columna in df.columns:
        if fragmento in _normalizar_texto(columna):
            return columna
    return None


def calcular_condicion_y_constancia(
    df: pd.DataFrame,
    fecha_emision: str | None = None,
) -> pd.DataFrame:
    columnas_asistencia_vivo = _columnas_asistencia_en_vivo(df)
    if columnas_asistencia_vivo:
        asistencia_principal = pd.Series(False, index=df.index)
        for columna in columnas_asistencia_vivo:
            asistencia_principal = asistencia_principal | _estado_finalizado(df[columna])
    else:
        cols = list(df.columns)
        if "region" not in cols:
            return df

        i_region = cols.index("region")
        if i_region + 1 >= len(cols):
            return df

        asistencia_principal = _estado_finalizado(df[cols[i_region + 1]])

    col_grabacion = _buscar_columna_por_fragmento(df, "grabacion")
    if col_grabacion is None:
        asistencia_grabacion = pd.Series(False, index=df.index)
    else:
        asistencia_grabacion = _estado_finalizado(df[col_grabacion])

    df["condicion"] = np.where(
        asistencia_principal | asistencia_grabacion,
        "ASISTENTE",
        "INASISTENTE",
    )

    col_constancia = _buscar_columna_por_fragmento(df, "constancia")
    if col_constancia is None:
        constancia_finalizada = pd.Series(False, index=df.index)
    else:
        constancia_finalizada = _estado_finalizado(df[col_constancia])

    fecha_emision = _fecha_emision_actual(fecha_emision)
    df["certificado"] = np.where(
        (df["condicion"] == "ASISTENTE") & constancia_finalizada,
        "CONSTANCIA",
        "NO CORRESPONDE",
    )
    df["emision_certificado"] = np.where(df["certificado"] == "CONSTANCIA", fecha_emision, "-")

    return df

