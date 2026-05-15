from __future__ import annotations

import pandas as pd

from app_procesamiento.core.utils import convertir_a_numerico


COLUMNAS_ELIMINAR_ACTIVIDAD = {
    "mooc": [
        "ambito_desempeño",
        "otros_ambito",
        "grupos",
        "accion",
        "Resuelve la encuesta del curso",
        "Descarga el certificado del curso",
        "Actualice sus datos para participar en el MOOC",
        "",
    ],
    "microlearning": [
        "ambito_desempeño",
        "otros_ambito",
        "grupos",
        "accion",
        "Resuelve la encuesta del curso",
        "Descarga el certificado del curso",
        "Actualice sus datos para participar en el Microlearning",
    ],
    "videoconferencia": [
        "ambito_desempeño",
        "otros_ambito",
        "grupos",
        "total_curso",
        "accion",
        "Actualice sus datos para participar en la videoconferencia",
        "Actualice sus datos para participar en el taller",
    ],
}


def eliminar_columnas_actividad(df: pd.DataFrame, tipo_actividad: str) -> pd.DataFrame:
    return df.drop(
        columns=COLUMNAS_ELIMINAR_ACTIVIDAD.get(tipo_actividad, []),
        errors="ignore",
    )


def mover_columna_antes_de_otra(
    df: pd.DataFrame,
    columna_mover: str,
    columna_referencia: str,
) -> pd.DataFrame:
    if columna_mover not in df.columns or columna_referencia not in df.columns:
        return df

    columnas = list(df.columns)
    columnas.remove(columna_mover)
    columnas.insert(columnas.index(columna_referencia), columna_mover)

    return df[columnas]


def mover_columna_despues_de_otra(
    df: pd.DataFrame,
    columna_mover: str,
    columna_referencia: str,
) -> pd.DataFrame:
    if columna_mover not in df.columns or columna_referencia not in df.columns:
        return df

    columnas = list(df.columns)
    columnas.remove(columna_mover)
    columnas.insert(columnas.index(columna_referencia) + 1, columna_mover)

    return df[columnas]


def convertir_columnas_calificacion(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["Calificación/20,00", "Calificación/20,00_final", "total_curso"]:
        if col in df.columns:
            df[col] = convertir_a_numerico(df[col])
    return df


def ordenar_bloque_calificaciones(df: pd.DataFrame) -> pd.DataFrame:
    col_entrada = next(
        (c for c in df.columns if str(c).startswith("Examen de entrada")),
        None,
    )
    bloque = [
        col_entrada,
        "Examen final",
        "Calificación/20,00",
        "Calificación/20,00_final",
        "total_curso",
    ]
    bloque = [c for c in bloque if c and c in df.columns]

    if not bloque:
        return df

    cols_originales = list(df.columns)
    primera_posicion = min(cols_originales.index(c) for c in bloque)
    cols_restantes = [c for c in cols_originales if c not in bloque]
    posicion_ajustada = sum(1 for c in cols_originales[:primera_posicion] if c not in bloque)

    return df[cols_restantes[:posicion_ajustada] + bloque + cols_restantes[posicion_ajustada:]]


def ordenar_columnas_intermedias(df: pd.DataFrame) -> pd.DataFrame:
    if "region" not in df.columns or "Calificación/20,00" not in df.columns:
        return df

    cols = list(df.columns)
    i_region = cols.index("region")
    i_calif = cols.index("Calificación/20,00")

    if i_region >= i_calif:
        return df

    middle = cols[i_region + 1 : i_calif]
    return df[cols[: i_region + 1] + sorted(middle) + cols[i_calif:]]


def ordenar_por_calificaciones(df: pd.DataFrame) -> pd.DataFrame:
    columnas_orden = [
        c
        for c in ["total_curso", "Calificación/20,00", "Calificación/20,00_final"]
        if c in df.columns
    ]
    if columnas_orden:
        df = df.sort_values(by=columnas_orden, ascending=[False] * len(columnas_orden))
    return df

