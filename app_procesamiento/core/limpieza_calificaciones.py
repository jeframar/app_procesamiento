from __future__ import annotations

from collections.abc import Callable

import pandas as pd

from app_procesamiento.core.entidades import (
    aplicar_match_por_nombre,
    aplicar_match_por_ruc,
    registrar_pendientes_en_sheets,
    validar_ruc_para_match,
)
from app_procesamiento.core.limpieza_laboral import (
    aplicar_correcciones_post_match,
    aplicar_reglas_limpieza_inicial,
)


def limpiar_dataset_calificaciones(
    df: pd.DataFrame,
    bd: pd.DataFrame,
    etiquetas: dict[str, str] | None = None,
    *,
    registrar_pendientes: bool = False,
    service=None,
    spreadsheet_id: str | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[pd.DataFrame, int, int, int]:
    def emitir(mensaje: str) -> None:
        if log is not None:
            log(mensaje)

    df, nombres_normalizados = aplicar_reglas_limpieza_inicial(df, etiquetas)
    emitir(f"Nombres de entidad normalizados: {nombres_normalizados}")

    df = validar_ruc_para_match(df)

    emitir("\nAplicando match por RUC...")
    df, matches_ruc = aplicar_match_por_ruc(df, bd, reset_match=True)
    emitir(f"  Matches por RUC: {matches_ruc}")

    emitir("\nAplicando match por nombre_entidad...")
    df, matches_nombre = aplicar_match_por_nombre(df, bd)
    emitir(f"  Matches por nombre: {matches_nombre}")

    df = aplicar_correcciones_post_match(df)

    if registrar_pendientes:
        if service is None or spreadsheet_id is None:
            raise ValueError("Se requiere service y spreadsheet_id para registrar pendientes.")
        registrar_pendientes_en_sheets(service, spreadsheet_id, df)

    return df, nombres_normalizados, matches_ruc, matches_nombre
