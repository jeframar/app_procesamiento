from __future__ import annotations

import pandas as pd

from app_procesamiento.core.certificados import (
    agregar_certificado_por_total,
    calcular_condicion_y_constancia,
)
from app_procesamiento.core.columnas import (
    actualizar_total_curso_desde_notas,
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


COLUMNA_CALIFICACION = "Calificación/20,00"


def _tiene_evaluaciones_intermedias(
    evaluaciones_intermedias: list[pd.DataFrame] | None,
) -> bool:
    return any(evaluacion is not None for evaluacion in evaluaciones_intermedias or [])


def _renombrar_examen_final_si_hay_intermedias(
    examen_final: pd.DataFrame,
    evaluaciones_intermedias: list[pd.DataFrame] | None,
) -> pd.DataFrame:
    columna_final = f"{COLUMNA_CALIFICACION}_final"
    if (
        _tiene_evaluaciones_intermedias(evaluaciones_intermedias)
        and COLUMNA_CALIFICACION in examen_final.columns
        and columna_final not in examen_final.columns
    ):
        return examen_final.rename(columns={COLUMNA_CALIFICACION: columna_final})
    return examen_final


def _mergear_evaluaciones_intermedias(
    df: pd.DataFrame,
    evaluaciones_intermedias: list[pd.DataFrame] | None,
) -> pd.DataFrame:
    if not evaluaciones_intermedias:
        return df

    for numero, evaluacion in enumerate(evaluaciones_intermedias, start=1):
        if evaluacion is None:
            continue
        df = merge_por_dni_o_nombre(
            df,
            evaluacion,
            f"evaluacion intermedia {numero}",
        )
    return df


def procesar_microlearning_dataset(
    actividades: pd.DataFrame,
    calificados: pd.DataFrame,
    examen_entrada: pd.DataFrame | None = None,
    examen_final: pd.DataFrame | None = None,
    evaluaciones_intermedias: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    df = unir_fuentes(calificados, actividades)

    if examen_entrada is not None:
        df = merge_por_dni_o_nombre(df, examen_entrada, "examen entrada")

    df = _mergear_evaluaciones_intermedias(df, evaluaciones_intermedias)

    if examen_final is not None:
        examen_final = _renombrar_examen_final_si_hay_intermedias(
            examen_final,
            evaluaciones_intermedias,
        )
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
    df = actualizar_total_curso_desde_notas(
        df,
        tiene_examen_entrada=examen_entrada is not None,
        tiene_examen_final=examen_final is not None,
    )
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
    evaluaciones_intermedias: list[pd.DataFrame] | None = None,
) -> pd.DataFrame:
    df = unir_fuentes(calificados, actividades)

    if examen_entrada is not None:
        df = merge_por_dni_o_nombre(df, examen_entrada, "examen entrada")

    df = _mergear_evaluaciones_intermedias(df, evaluaciones_intermedias)

    examen_final = _renombrar_examen_final_si_hay_intermedias(
        examen_final,
        evaluaciones_intermedias,
    )
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
    df = actualizar_total_curso_desde_notas(
        df,
        tiene_examen_entrada=examen_entrada is not None,
        tiene_examen_final=examen_final is not None,
    )
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
