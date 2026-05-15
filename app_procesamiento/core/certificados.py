import numpy as np
import pandas as pd

from app_procesamiento.config import FECHA_EMISION_CERTIFICADO


def agregar_certificado_por_total(
    df: pd.DataFrame,
    crear_si_no_hay_total: bool = False,
    fecha_emision: str = FECHA_EMISION_CERTIFICADO,
) -> pd.DataFrame:
    if "total_curso" not in df.columns:
        if crear_si_no_hay_total:
            df["certificado"] = "NO CORRESPONDE"
            df["emision_certificado"] = "-"
        return df

    df["condicion"] = ""
    df["certificado"] = np.where(df["total_curso"] >= 14, "CERTIFICADO", "NO CORRESPONDE")
    df["emision_certificado"] = np.where(df["total_curso"] >= 14, fecha_emision, "-")

    return df


def calcular_condicion_y_constancia(
    df: pd.DataFrame,
    fecha_emision: str = FECHA_EMISION_CERTIFICADO,
) -> pd.DataFrame:
    cols = list(df.columns)
    if "region" not in cols:
        return df

    i_region = cols.index("region")
    if i_region + 1 >= len(cols):
        return df

    col_siguiente = cols[i_region + 1]
    asistencia_principal = df[col_siguiente].eq("Finalizado")

    columnas_grabacion = [
        "Accede a la grabación de la videoconferencia",
        "Accede a la grabación del evento.",
    ]
    col_grabacion = next((c for c in columnas_grabacion if c in df.columns), None)
    if col_grabacion is None:
        asistencia_grabacion = pd.Series(False, index=df.index)
    else:
        asistencia_grabacion = df[col_grabacion].eq("Finalizado")

    df["condicion"] = np.where(
        asistencia_principal | asistencia_grabacion,
        "ASISTENTE",
        "INASISTENTE",
    )

    columnas_constancia = ["Constancia de asistencia", "Constancia"]
    col_constancia = next((c for c in columnas_constancia if c in df.columns), None)
    if col_constancia is None:
        constancia_finalizada = pd.Series(False, index=df.index)
    else:
        constancia_finalizada = df[col_constancia].eq("Finalizado")

    df["certificado"] = np.where(
        (df["condicion"] == "ASISTENTE") & constancia_finalizada,
        "CONSTANCIA",
        "NO CORRESPONDE",
    )
    df["emision_certificado"] = np.where(df["certificado"] == "CONSTANCIA", fecha_emision, "-")

    return df

