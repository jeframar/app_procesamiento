from pathlib import Path

import pandas as pd

from app_procesamiento.core.utils import convertir_a_numerico, normalizar_dni


def leer_actividades(ruta_csv: str | Path) -> pd.DataFrame:
    ruta_csv = Path(ruta_csv)

    cols = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        nrows=0,
    ).columns

    df = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        dtype={"DNI": "object"},
        usecols=[cols[1]] + list(cols[3:]),
    )

    df["DNI"] = normalizar_dni(df["DNI"])
    return df


def leer_calificados(ruta_excel: str | Path) -> pd.DataFrame:
    df = pd.read_excel(ruta_excel, dtype={"dni": "object", "DNI": "object"})

    if "dni" in df.columns:
        col_dni = "dni"
    elif "DNI" in df.columns:
        col_dni = "DNI"
    else:
        raise KeyError("El archivo de calificaciones no tiene columna 'dni' ni 'DNI'.")

    df[col_dni] = normalizar_dni(df[col_dni])
    df = df.drop_duplicates(subset=[col_dni], keep="first")

    if col_dni != "DNI":
        df = df.rename(columns={col_dni: "DNI"})

    return df


def leer_examen(ruta_excel: str | Path) -> pd.DataFrame:
    df = pd.read_excel(
        ruta_excel,
        dtype={"DNI": "object"},
        skipfooter=1,
        usecols=[2, 10],
    )

    df["DNI"] = normalizar_dni(df["DNI"])
    return df


def leer_examen_final(ruta_excel: str | Path) -> pd.DataFrame:
    df = leer_examen(ruta_excel)

    df["Calificación/20,00"] = convertir_a_numerico(df["Calificación/20,00"])

    df = (
        df.sort_values(
            by=["DNI", "Calificación/20,00"],
            ascending=[True, False],
        )
        .drop_duplicates(subset=["DNI"], keep="first")
    )

    return df

