from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from app_procesamiento.core.entidades import (
    aplicar_match_por_nombre,
    aplicar_match_por_ruc,
    validar_ruc_para_match,
)
from app_procesamiento.core.errores_match_no import (
    AnalisisErroresMatchNo,
    analizar_errores_match_no,
)
from app_procesamiento.core.columnas import renumerar_id_por_apellidos_nombres
from app_procesamiento.core.limpieza_laboral import normalizar_columnas_por_situacion_laboral


def _es_vacio(serie: pd.Series) -> pd.Series:
    texto = serie.fillna("").astype(str).str.strip().str.lower()
    return texto.isin(["", "nan", "none"])


def _es_rubro_privado_sin_valor(serie: pd.Series) -> pd.Series:
    texto = serie.fillna("").astype(str).str.strip().str.lower()
    return texto.isin(["", "-", "nan", "none", "no corresponde"])


def normalizar_rubro_organizacion_calificaciones(df: pd.DataFrame) -> pd.DataFrame:
    if not {"situacion_laboral", "tipo_entidad", "rubro_organizacion"}.issubset(df.columns):
        return df

    situacion = df["situacion_laboral"].fillna("").astype(str).str.strip()
    tipo_entidad = df["tipo_entidad"].fillna("").astype(str).str.strip()

    mask_no_corresponde = (
        ((situacion == "Trabajador dependiente") & (tipo_entidad == "Entidad pública"))
        | (situacion == "Trabajador independiente")
        | (tipo_entidad == "Independiente y otros")
        | (situacion == "No labora actualmente")
        | (tipo_entidad == "No labora actualmente")
    )
    df.loc[mask_no_corresponde, "rubro_organizacion"] = "No corresponde"

    mask_privado_sin_rubro = (
        (situacion == "Trabajador dependiente")
        & (tipo_entidad == "Entidad privada")
        & _es_rubro_privado_sin_valor(df["rubro_organizacion"])
    )
    df.loc[mask_privado_sin_rubro, "rubro_organizacion"] = "No indica"

    return df


def aplicar_reglas_finales(df: pd.DataFrame) -> pd.DataFrame:
    for columna in ["clasificacion_empresa"]:
        if columna in df.columns:
            df.loc[_es_vacio(df[columna]), columna] = "-"

    valores_por_defecto = {
        "tipo_actividad": "No indica",
        "cuenta_con_ruc": "No indica",
        "numero_ruc_independiente": "0",
        "rubro_organizacion_independiente": "-",
        "rnp": "No indica",
        "tipo_proveedor": "-",
        "ambito_desempeno": "Otros",
        "otros_ambito": "No indica",
    }
    for columna, valor in valores_por_defecto.items():
        if columna in df.columns:
            df.loc[_es_vacio(df[columna]), columna] = valor

    return df


def finalizar_dataset_calificaciones(
    df: pd.DataFrame,
    bd: pd.DataFrame,
    log: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, int, int, AnalisisErroresMatchNo]:
    def emitir(mensaje: str) -> None:
        if log is not None:
            log(mensaje)

    df = validar_ruc_para_match(df)

    emitir("\nRecalculando match por RUC...")
    df, matches_ruc = aplicar_match_por_ruc(df, bd, reset_match=True)
    emitir(f"  Matches por RUC: {matches_ruc}")

    emitir("\nRecalculando match por nombre_entidad...")
    df, matches_nombre = aplicar_match_por_nombre(df, bd)
    emitir(f"  Matches por nombre: {matches_nombre}")

    emitir("\nNormalizando columnas por situacion_laboral...")
    df = normalizar_columnas_por_situacion_laboral(df)
    df = normalizar_rubro_organizacion_calificaciones(df)
    df = aplicar_reglas_finales(df)
    analisis_errores = analizar_errores_match_no(df)
    df = renumerar_id_por_apellidos_nombres(df)

    return df, matches_ruc, matches_nombre, analisis_errores
