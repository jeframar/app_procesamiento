import unicodedata

import pandas as pd


MAP_GRADO = {
    "Bachiller": "Bachiller Universitario",
    "BACHILLER UNIVERSITARIO": "Bachiller Universitario",
    "Titulo profesional": "Titulado Universitario",
    "TITULO UNIVERSITARIO": "Titulado Universitario",
    "TITULADO UNIVERSITARIO": "Titulado Universitario",
    "SECUNDARIA COMPLETA": "Secundaria completa",
    "MAESTRIA": "Maestría",
    "MAESTRÍA": "Maestría",
    "MAESTRÍA ": "Maestría",
    "DOCTORADO": "Doctorado",
    "-": "No indica",
    "ESCUELA FFAA Y PNP": "Escuela FFAA y PNP",
    "TITULADO TÉCNICO SUPERIOR": "Titulado Técnico Superior",
    "TITULADO TECNICO SUPERIOR": "Titulado Técnico Superior",
    "EGRESADO EDUCACIÓN TÉCNICA SUPERIOR": "Egresado Educación Técnica Superior",
    "EGRESADO EDUCACION TECNICA SUPERIOR": "Egresado Educación Técnica Superior",
    "EGRESADO EDUCACIÓN UNIVERSITARIA": "Egresado Educación Universitaria",
    "EGRESADO EDUCACION UNIVERSITARIA": "Egresado Educación Universitaria",
}


MAP_PERFIL = {
    "Órgano Encargado de las Contrataciones - OEC": "DEC",
    "Órgano encargado de las contrataciones (OEC)": "DEC",
    "Dependencia Encargada de las Contrataciones - DEC": "DEC",
    "Área usuaria - AU": "AU",
    "Área usuaria": "AU",
    "Asesoría Jurídica": "ARBITRAJE/JPRD",
    "Procuraduría": "PROCURADURIA",
    "Órgano de control institucional": "OCI",
    "Órgano de Control Institucional - OCI": "OCI",
    "Planeamiento o presupuesto": "PLANEAMIENTO/PRESUPUESTO",
    "Planeamiento institucional": "PLANEAMIENTO/PRESUPUESTO",
    "Planeamiento/Presupuesto": "PLANEAMIENTO/PRESUPUESTO",
    "Supervisor de Obras": "PROVEEDOR",
    "Supervisión de Obras": "PROVEEDOR",
    "Inspector de obras": "PROVEEDOR",
    "Proveedor del Estado": "PROVEEDOR",
    "Docencia en contrataciones públicas": "PROFESIONAL INDEPENDIENTE",
    "Público en general": "PROFESIONAL INDEPENDIENTE",
    "Ciudadano": "PROFESIONAL INDEPENDIENTE",
    "Otros": "PROFESIONAL INDEPENDIENTE",
    "Otro": "PROFESIONAL INDEPENDIENTE",
    "":"PROFESIONAL INDEPENDIENTE"
}


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


def normalizar_ruc(serie: pd.Series) -> pd.Series:
    serie = (
        serie.fillna("")
        .astype(str)
        .str.replace(r"\s+", "", regex=True)
        .str.strip()
    )
    serie.loc[~serie.str.fullmatch(r"\d{11}")] = "0"
    return serie


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

