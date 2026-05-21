from pathlib import Path

import pandas as pd

from app_procesamiento.core.utils import (
    convertir_a_numerico,
    normalizar_dni,
    normalizar_dni_para_merge,
    normalizar_nombre_persona,
)


COLUMNA_CALIFICACION = "Calificación/20,00"


def _reiniciar_fuente(fuente) -> None:
    if hasattr(fuente, "seek"):
        fuente.seek(0)


def _columnas_unicas(columnas) -> list:
    resultado = []
    for columna in columnas:
        if columna not in resultado:
            resultado.append(columna)
    return resultado


def _buscar_columna(columnas, candidatos: list[str], contiene: list[str] | None = None):
    columnas_lista = list(columnas)
    columnas_lower = {str(c).strip().lower(): c for c in columnas_lista}

    for candidato in candidatos:
        encontrado = columnas_lower.get(candidato.strip().lower())
        if encontrado is not None:
            return encontrado

    if contiene:
        for columna in columnas_lista:
            texto = str(columna).strip().lower()
            if all(fragmento.lower() in texto for fragmento in contiene):
                return columna

    return None


def _dni_para_salida(serie: pd.Series) -> pd.Series:
    dni_merge = normalizar_dni_para_merge(serie)
    dni_legacy = normalizar_dni(serie)
    return dni_merge.where(dni_merge != "", dni_legacy)


def _agregar_claves_persona(
    df: pd.DataFrame,
    columna_dni: str,
    columna_nombre: str | None = None,
) -> pd.DataFrame:
    df["_dni_original"] = df[columna_dni]
    df["_dni_merge"] = normalizar_dni_para_merge(df[columna_dni])
    df[columna_dni] = _dni_para_salida(df[columna_dni])

    if columna_nombre and columna_nombre in df.columns:
        df["_nombre_merge"] = normalizar_nombre_persona(df[columna_nombre])
    elif "_nombre_merge" in df.columns:
        df["_nombre_merge"] = df["_nombre_merge"].fillna("").astype(str)
    else:
        df["_nombre_merge"] = ""

    return df


def _deduplicar_validos_por_dni(df: pd.DataFrame) -> pd.DataFrame:
    if "_dni_merge" not in df.columns:
        return df

    mask_valido = df["_dni_merge"] != ""
    df_validos = df.loc[mask_valido].drop_duplicates(subset=["_dni_merge"], keep="first")
    df_invalidos = df.loc[~mask_valido]

    return pd.concat([df_validos, df_invalidos]).sort_index()


def _deduplicar_examen_final(df: pd.DataFrame) -> pd.DataFrame:
    df = df.sort_values(by=[COLUMNA_CALIFICACION], ascending=[False])

    mask_dni = df["_dni_merge"] != ""
    por_dni = df.loc[mask_dni].drop_duplicates(subset=["_dni_merge"], keep="first")

    restantes = df.loc[~mask_dni]
    mask_nombre = restantes["_nombre_merge"] != ""
    por_nombre = restantes.loc[mask_nombre].drop_duplicates(
        subset=["_nombre_merge"],
        keep="first",
    )
    sin_llave = restantes.loc[~mask_nombre]

    return pd.concat([por_dni, por_nombre, sin_llave]).sort_index()


def leer_actividades(ruta_csv: str | Path) -> pd.DataFrame:
    if isinstance(ruta_csv, (str, Path)):
        ruta_csv = Path(ruta_csv)

    _reiniciar_fuente(ruta_csv)
    cols = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        nrows=0,
    ).columns

    col_nombre = cols[0]
    col_dni = "DNI" if "DNI" in cols else cols[1]
    usecols = _columnas_unicas([col_nombre, col_dni] + list(cols[3:]))

    _reiniciar_fuente(ruta_csv)
    df = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        dtype={col_dni: "object"},
        usecols=usecols,
    )
    _reiniciar_fuente(ruta_csv)

    df = _agregar_claves_persona(df, col_dni, col_nombre)
    if col_dni != "DNI":
        df = df.rename(columns={col_dni: "DNI"})
    return df


def leer_calificados(ruta_excel: str | Path) -> pd.DataFrame:
    df = pd.read_excel(ruta_excel, dtype={"dni": "object", "DNI": "object"})

    if "dni" in df.columns:
        col_dni = "dni"
    elif "DNI" in df.columns:
        col_dni = "DNI"
    else:
        raise KeyError("El archivo de calificaciones no tiene columna 'dni' ni 'DNI'.")

    col_nombre = _buscar_columna(df.columns, ["nombres_apellidos"])
    df = _agregar_claves_persona(df, col_dni, col_nombre)
    df = _deduplicar_validos_por_dni(df)

    if col_dni != "DNI":
        df = df.rename(columns={col_dni: "DNI"})

    return df


def leer_examen(ruta_excel: str | Path) -> pd.DataFrame:
    df_completo = pd.read_excel(
        ruta_excel,
        dtype={"DNI": "object"},
        skipfooter=1,
    )

    col_apellidos = _buscar_columna(
        df_completo.columns,
        ["Apellido(s) (Como aparece en su DNI)"],
        contiene=["apellido"],
    )
    col_nombres = _buscar_columna(
        df_completo.columns,
        ["Nombre (Como aparece en su DNI)"],
        contiene=["nombre", "dni"],
    )
    col_dni = _buscar_columna(df_completo.columns, ["DNI"])
    col_calificacion = _buscar_columna(
        df_completo.columns,
        [COLUMNA_CALIFICACION],
        contiene=["calificaci", "20,00"],
    )

    if col_dni is None:
        col_dni = df_completo.columns[2]
    if col_calificacion is None:
        col_calificacion = df_completo.columns[10]

    df = df_completo[[col_dni, col_calificacion]].copy()
    if col_calificacion != COLUMNA_CALIFICACION:
        df = df.rename(columns={col_calificacion: COLUMNA_CALIFICACION})

    if col_apellidos is not None and col_nombres is not None:
        nombre_completo = (
            df_completo[col_nombres].fillna("").astype(str)
            + " "
            + df_completo[col_apellidos].fillna("").astype(str)
        )
        df["_nombre_merge"] = normalizar_nombre_persona(nombre_completo)
    else:
        df["_nombre_merge"] = ""

    df = _agregar_claves_persona(df, col_dni)
    if col_dni != "DNI":
        df = df.rename(columns={col_dni: "DNI"})
    return df


def leer_examen_final(ruta_excel: str | Path) -> pd.DataFrame:
    df = leer_examen(ruta_excel)

    df[COLUMNA_CALIFICACION] = convertir_a_numerico(df[COLUMNA_CALIFICACION])
    df = _deduplicar_examen_final(df)

    return df
