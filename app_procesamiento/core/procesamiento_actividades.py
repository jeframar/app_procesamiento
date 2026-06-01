from __future__ import annotations

import pandas as pd

from app_procesamiento.core.certificados import (
    agregar_certificado_por_total,
    calcular_condicion_y_constancia,
)
from app_procesamiento.core.columnas import (
    convertir_columnas_calificacion,
    eliminar_columnas_actividad,
    mover_columna_despues_de_otra,
    ordenar_bloque_calificaciones,
    ordenar_columnas_intermedias,
    ordenar_por_calificaciones,
)
from app_procesamiento.core.transformaciones import (
    eliminar_columnas_basura,
    eliminar_columnas_exportacion,
    limpiar_campos_generales,
    merge_por_dni_o_nombre,
    unir_fuentes,
)


def procesar_microlearning_dataset(
    actividades: pd.DataFrame,
    calificados: pd.DataFrame,
    examen_entrada: pd.DataFrame | None = None,
    examen_final: pd.DataFrame | None = None,
) -> pd.DataFrame:
    df = unir_fuentes(calificados, actividades)

    if examen_entrada is not None:
        df = merge_por_dni_o_nombre(df, examen_entrada, "examen entrada")

    if examen_final is not None:
        df = merge_por_dni_o_nombre(
            df,
            examen_final,
            "examen final",
            suffixes=("", "_final"),
        )

    df = eliminar_columnas_actividad(df, "microlearning")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = convertir_columnas_calificacion(df)
    df = ordenar_bloque_calificaciones(df)
    df = ordenar_columnas_intermedias(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")
    df = ordenar_por_calificaciones(df)
    df = agregar_certificado_por_total(df, crear_si_no_hay_total=False)
    return eliminar_columnas_exportacion(df)


def procesar_mooc_dataset(
    actividades: pd.DataFrame,
    calificados: pd.DataFrame,
    examen_entrada: pd.DataFrame | None,
    examen_final: pd.DataFrame,
) -> pd.DataFrame:
    df = unir_fuentes(calificados, actividades)

    if examen_entrada is not None:
        df = merge_por_dni_o_nombre(df, examen_entrada, "examen entrada")

    df = merge_por_dni_o_nombre(
        df,
        examen_final,
        "examen final",
        suffixes=("", "_final"),
    )

    df = eliminar_columnas_actividad(df, "mooc")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = convertir_columnas_calificacion(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")
    df = mover_columna_despues_de_otra(df, "total_curso", "Calificaci\u00f3n/20,00_final")
    df = ordenar_bloque_calificaciones(df)
    df = ordenar_por_calificaciones(df)
    df = agregar_certificado_por_total(df, crear_si_no_hay_total=True)
    return eliminar_columnas_exportacion(df)


def procesar_videoconferencia_dataset(
    actividades: pd.DataFrame,
    calificados: pd.DataFrame,
) -> pd.DataFrame:
    df = unir_fuentes(calificados, actividades)
    df = eliminar_columnas_actividad(df, "videoconferencia")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = calcular_condicion_y_constancia(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")

    if {"condicion", "certificado"}.issubset(df.columns):
        df = df.sort_values(by=["condicion", "certificado"], ascending=[True, True])

    return eliminar_columnas_exportacion(df)
