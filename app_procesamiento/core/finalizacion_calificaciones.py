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
from app_procesamiento.core.limpieza_laboral import normalizar_columnas_por_situacion_laboral


def _es_vacio(serie: pd.Series) -> pd.Series:
    texto = serie.fillna("").astype(str).str.strip().str.lower()
    return texto.isin(["", "nan", "none"])


def aplicar_reglas_finales(df: pd.DataFrame) -> pd.DataFrame:
    if {"tipo_entidad", "nivel_gobierno", "nombre_entidad"}.issubset(df.columns):
        tipo_entidad = df["tipo_entidad"].fillna("").astype(str).str.strip()
        nombre_entidad = df["nombre_entidad"].fillna("").astype(str).str.strip()
        mask_nivel = (
            (tipo_entidad == "Entidad p\u00fablica")
            & _es_vacio(df["nivel_gobierno"])
            & (nombre_entidad == "INDEPENDIENTE Y OTROS")
        )
        df.loc[mask_nivel, "nivel_gobierno"] = "-"

    for columna in ["clasificacion_empresa", "rubro_organizacion"]:
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
    df = aplicar_reglas_finales(df)
    analisis_errores = analizar_errores_match_no(df)

    return df, matches_ruc, matches_nombre, analisis_errores
