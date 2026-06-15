from decimal import Decimal, InvalidOperation
import re
import unicodedata

import pandas as pd


PREFIJOS_RUC_VALIDOS = ("10", "15", "17", "20")


def normalizar_dni(serie: pd.Series) -> pd.Series:
    serie = (
        serie.fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.zfill(8)
    )
    serie.loc[~serie.str.fullmatch(r"\d{8}")] = "00000000"
    return serie


def normalizar_dni_para_merge(serie: pd.Series) -> pd.Series:
    dni = (
        serie.fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
    )

    solo_digitos = dni.str.fullmatch(r"\d+")
    dni_sin_ceros = dni.where(~solo_digitos, dni.str.lstrip("0"))
    dni_sin_ceros = dni_sin_ceros.mask(dni_sin_ceros == "", "0")

    normalizado = dni.copy()
    mask_ocho_o_menos = solo_digitos & (dni.str.len() <= 8)
    mask_ceros_extra = solo_digitos & (dni.str.len() > 8) & (dni_sin_ceros.str.len() <= 8)
    normalizado.loc[mask_ocho_o_menos | mask_ceros_extra] = (
        dni_sin_ceros.loc[mask_ocho_o_menos | mask_ceros_extra].str.zfill(8)
    )

    valido = normalizado.str.fullmatch(r"\d{8}") & (normalizado != "00000000")
    normalizado.loc[~valido] = ""
    return normalizado


def normalizar_nombre_persona(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.upper()
        .apply(
            lambda x: unicodedata.normalize("NFKD", x)
            .encode("ascii", "ignore")
            .decode("utf-8")
        )
        .str.replace(r"[^A-Z0-9]+", " ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
    )


def normalizar_celular(serie: pd.Series) -> pd.Series:
    serie = (
        serie.fillna("")
        .astype(str)
        .str.replace(r"\D", "", regex=True)
    )

    # quitar código país Perú
    serie = serie.str.replace(r"^51", "", regex=True)

    # validar celular peruano
    mask = serie.str.fullmatch(r"9\d{8}")

    serie.loc[~mask] = "000000000"

    return serie


def _texto_decimal_entero(valor: str) -> str | None:
    texto = valor.replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None

    if numero != numero.to_integral_value():
        return None

    return format(numero.quantize(Decimal(1)), "f")


def _normalizar_ruc_valor(valor) -> str:
    try:
        if pd.isna(valor):
            return "0"
    except (TypeError, ValueError):
        pass

    texto = (
        str(valor)
        .strip()
        .replace("\u00a0", "")
        .replace("\u200b", "")
        .removeprefix("'")
        .strip()
    )
    if texto.lower() in {"", "nan", "none", "<na>"}:
        return "0"

    texto_sin_espacios = re.sub(r"\s+", "", texto)
    if re.fullmatch(r"[+-]?\d+(?:[\.,]\d+)?[eE][+-]?\d+", texto_sin_espacios):
        decimal_entero = _texto_decimal_entero(texto_sin_espacios)
        if decimal_entero is not None:
            texto_sin_espacios = decimal_entero
    else:
        texto_sin_espacios = re.sub(r"[\.,]0+$", "", texto_sin_espacios)

    return re.sub(r"\D", "", texto_sin_espacios)


def normalizar_ruc(serie: pd.Series) -> pd.Series:
    ruc = serie.map(_normalizar_ruc_valor).astype(str)
    ruc.loc[~ruc.str.fullmatch(r"\d{11}")] = "0"
    return ruc


def normalizar_ruc_para_match(serie: pd.Series) -> pd.Series:
    ruc = normalizar_ruc(serie)
    ruc.loc[~ruc.str[:2].isin(PREFIJOS_RUC_VALIDOS)] = "0"
    return ruc


def normalizar_region(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.upper()
        .apply(
            lambda x: unicodedata.normalize("NFKD", x)
            .encode("ascii", "ignore")
            .decode("utf-8")
        )
    )


def formatear_fecha(serie: pd.Series) -> pd.Series:
    return pd.to_datetime(serie, dayfirst=True, errors="coerce").dt.strftime("%d-%m-%Y")


def convertir_a_numerico(serie: pd.Series) -> pd.Series:
    return (
        serie.astype(str)
        .str.strip()
        .replace({"-": None, "": None, "nan": None, "None": None})
        .str.replace(",", ".", regex=False)
        .pipe(pd.to_numeric, errors="coerce")
        .fillna(0)
        .astype(float)
    )


def completar_nulos(df: pd.DataFrame, columnas: list[str], valor: str) -> pd.DataFrame:
    columnas = [c for c in columnas if c in df.columns]
    if columnas:
        df[columnas] = df[columnas].fillna(valor)
    return df

