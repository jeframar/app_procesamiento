from __future__ import annotations

import pandas as pd

from app_procesamiento import config
from app_procesamiento.core.google_sheets import (
    append_rows,
    download_sheet_as_raw_df,
    download_sheet_as_table,
    ensure_sheet_exists,
    write_rows,
)
from app_procesamiento.core.limpieza_laboral import es_vacio, sit, tipo


COLUMNAS_ENTIDAD = ["RUC", "Nivel de Gobierno", "Tipo de entidad", "Nombre de entidad"]
ALIAS_NOMBRE_ENTIDAD = "Nombre de la entidad"


def normalizar_columnas_entidad(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()

    if ALIAS_NOMBRE_ENTIDAD in df.columns and "Nombre de entidad" not in df.columns:
        df = df.rename(columns={ALIAS_NOMBRE_ENTIDAD: "Nombre de entidad"})
    elif ALIAS_NOMBRE_ENTIDAD in df.columns and "Nombre de entidad" in df.columns:
        nombre_canonico = df["Nombre de entidad"].astype(str).str.strip()
        nombre_alias = df[ALIAS_NOMBRE_ENTIDAD].astype(str).str.strip()
        df["Nombre de entidad"] = nombre_canonico.where(nombre_canonico != "", nombre_alias)
        df = df.drop(columns=[ALIAS_NOMBRE_ENTIDAD])

    faltantes = [c for c in COLUMNAS_ENTIDAD if c not in df.columns]
    if faltantes:
        raise KeyError(f"Faltan columnas de entidad: {faltantes}")

    df = df[COLUMNAS_ENTIDAD].copy()
    for col in COLUMNAS_ENTIDAD:
        df[col] = df[col].astype(str).str.strip()

    return df


def cargar_bd_entidades(
    service,
    spreadsheet_id: str,
    hoja_consolidado: str = config.BD_ENTIDADES_SHEET,
    hoja_aniadir: str = config.BD_ANIADIR_SHEET,
) -> pd.DataFrame:
    bd = download_sheet_as_table(service, spreadsheet_id, hoja_consolidado)
    if bd.empty:
        raise RuntimeError("La hoja bd_entidades esta vacia. Abortando.")

    bd = normalizar_columnas_entidad(bd)
    print(f"  Consolidado: {len(bd)} entidades")

    bd_aniadir = download_sheet_as_table(service, spreadsheet_id, hoja_aniadir)
    if not bd_aniadir.empty:
        bd_aniadir = normalizar_columnas_entidad(bd_aniadir)
        bd = pd.concat([bd, bd_aniadir], ignore_index=True)
        print(f"  '{hoja_aniadir}': {len(bd_aniadir)} entidades adicionales")
    else:
        print(f"  '{hoja_aniadir}' vacia o sin datos, se omite.")

    bd["RUC"] = bd["RUC"].astype(str).str.strip()
    print(f"  Total bd para match: {len(bd)}")
    return bd


def cargar_etiquetas_entidad(
    service,
    spreadsheet_id: str,
    hoja_etiquetas: str = config.BD_ETIQUETAS_SHEET,
) -> dict[str, str]:
    raw = download_sheet_as_raw_df(service, spreadsheet_id, hoja_etiquetas)

    etiquetas: dict[str, str] = {}
    if raw.empty or len(raw) <= 1:
        print(f"  Hoja '{hoja_etiquetas}' vacia, se omite.")
        return etiquetas

    for _, row in raw.iloc[1:].iterrows():
        etiqueta = str(row.iloc[0]).strip().lower()
        entidad = str(row.iloc[2]).strip() if len(row) > 2 else ""
        if etiqueta and etiqueta != "nan" and entidad and entidad != "nan":
            etiquetas[etiqueta] = entidad

    print(f"  Etiquetas cargadas: {len(etiquetas)}")
    return etiquetas


def validar_ruc_para_match(df: pd.DataFrame) -> pd.DataFrame:
    if "ruc" not in df.columns:
        return df

    ruc_str = df["ruc"].astype(str).str.strip().str.replace(r"\D", "", regex=True)
    ruc_valido = ruc_str.str.fullmatch(r"\d{11}") & ruc_str.str[:2].isin(["10", "15", "17", "20"])
    df["ruc"] = ruc_str.where(ruc_valido, "0")
    return df


def preparar_bd_para_match_por_ruc(bd: pd.DataFrame) -> pd.DataFrame:
    bd = normalizar_columnas_entidad(bd)
    ruc_limpio = bd["RUC"].astype(str).str.strip()
    bd = bd[~ruc_limpio.str.lower().isin(["", "0", "nan", "none"])].copy()

    rucs_duplicados = bd.loc[bd["RUC"].duplicated(keep=False), "RUC"].nunique()
    filas_duplicadas = int(bd["RUC"].duplicated(keep="first").sum())

    if filas_duplicadas:
        print(
            "  Aviso: bd_entidades tiene "
            f"{filas_duplicadas} fila(s) duplicada(s) en {rucs_duplicados} RUC(s); "
            "se usara la primera aparicion para no duplicar participantes."
        )

    return bd.drop_duplicates(subset=["RUC"], keep="first")


def _actualizar_situacion_laboral_por_tipo(df: pd.DataFrame, mask: pd.Series) -> pd.DataFrame:
    mask_pub_pri = mask & tipo(df).isin(["Entidad pública", "Entidad privada"])
    mask_ind = mask & (tipo(df) == "Independiente y otros")

    df.loc[mask_pub_pri, "situacion_laboral"] = "Trabajador dependiente"
    df.loc[mask_ind, "situacion_laboral"] = "Trabajador independiente"

    return df


def aplicar_match_por_ruc(
    df: pd.DataFrame,
    bd: pd.DataFrame,
    reset_match: bool = False,
) -> tuple[pd.DataFrame, int]:
    filas_antes = len(df)
    bd_match = preparar_bd_para_match_por_ruc(bd)

    if reset_match or "match_entidad" not in df.columns:
        df["match_entidad"] = "NO"

    df = df.merge(
        bd_match,
        left_on="ruc",
        right_on="RUC",
        how="left",
        validate="many_to_one",
    )

    if len(df) != filas_antes:
        raise RuntimeError(
            "El match por RUC cambio la cantidad de filas "
            f"({filas_antes} -> {len(df)}). Revise duplicados en bd_entidades."
        )

    mask_match = df["Tipo de entidad"].notna() & (df["Tipo de entidad"].astype(str).str.strip() != "")
    df["match_entidad"] = mask_match.map({True: "SI", False: "NO"})
    df.loc[mask_match, "tipo_entidad"] = df.loc[mask_match, "Tipo de entidad"]
    df.loc[mask_match, "nivel_gobierno"] = df.loc[mask_match, "Nivel de Gobierno"]
    df.loc[mask_match, "nombre_entidad"] = df.loc[mask_match, "Nombre de entidad"]

    df = _actualizar_situacion_laboral_por_tipo(df, mask_match)
    df = df.drop(columns=COLUMNAS_ENTIDAD, errors="ignore")

    return df, int(mask_match.sum())


def aplicar_match_por_nombre(df: pd.DataFrame, bd: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    bd = normalizar_columnas_entidad(bd)

    if "match_entidad" not in df.columns:
        df["match_entidad"] = "NO"

    mask_candidatos = (
        (df["match_entidad"] == "NO")
        & df["ruc"].astype(str).str.strip().isin(["", "0"])
        & ~es_vacio(df["nombre_entidad"])
    )

    bd_norm = bd.copy()
    bd_norm["_nombre_norm"] = bd_norm["Nombre de entidad"].astype(str).str.strip().str.upper()
    bd_norm = bd_norm[bd_norm["_nombre_norm"] != ""]

    rucs_por_nombre = bd_norm.groupby("_nombre_norm")["RUC"].nunique()
    nombres_unicos = rucs_por_nombre[rucs_por_nombre == 1].index
    bd_unicos = (
        bd_norm[bd_norm["_nombre_norm"].isin(nombres_unicos)]
        .drop_duplicates("_nombre_norm")
        .set_index("_nombre_norm")
    )

    nombre_a_ruc = bd_unicos["RUC"].astype(str).str.strip().to_dict()
    nombre_a_tipo = bd_unicos["Tipo de entidad"].astype(str).str.strip().to_dict()
    nombre_a_nivel = bd_unicos["Nivel de Gobierno"].astype(str).str.strip().to_dict()

    df_nombre_norm = df["nombre_entidad"].astype(str).str.strip().str.upper()
    mask_match = mask_candidatos & df_nombre_norm.isin(nombre_a_ruc)

    if mask_match.any():
        df.loc[mask_match, "ruc"] = df_nombre_norm[mask_match].map(nombre_a_ruc)
        df.loc[mask_match, "tipo_entidad"] = df_nombre_norm[mask_match].map(nombre_a_tipo)
        df.loc[mask_match, "nivel_gobierno"] = df_nombre_norm[mask_match].map(nombre_a_nivel)
        df.loc[mask_match, "match_entidad"] = "SI_NOMBRE"
        df = _actualizar_situacion_laboral_por_tipo(df, mask_match)

    return df, int(mask_match.sum())


def _leer_existentes_por_columna(
    service,
    spreadsheet_id: str,
    sheet_name: str,
    columna: str,
) -> tuple[set[str], bool]:
    raw = download_sheet_as_raw_df(service, spreadsheet_id, sheet_name)

    if raw.empty:
        return set(), False

    headers = raw.iloc[0].astype(str).str.strip().tolist()
    tiene_encabezado = columna in headers
    if not tiene_encabezado or len(raw) <= 1:
        return set(), tiene_encabezado

    data = raw.iloc[1:].copy()
    data.columns = headers
    existentes = set(data[columna].astype(str).str.strip().tolist())
    return existentes, True


def registrar_pendientes_en_sheets(service, spreadsheet_id: str, df: pd.DataFrame) -> None:
    mask_aniadir = (
        (df["match_entidad"] == "NO")
        & ~df["ruc"].astype(str).str.strip().isin(["", "0"])
    )

    candidatos_aniadir = (
        df.loc[mask_aniadir, ["ruc", "nombre_entidad"]]
        .astype(str)
        .apply(lambda serie: serie.str.strip())
        .drop_duplicates(subset="ruc")
        .sort_values("ruc")
    )

    print(f"\nCandidatos para {config.ANIADIR_BD_SHEET}: {len(candidatos_aniadir)}")

    if not candidatos_aniadir.empty:
        ensure_sheet_exists(service, spreadsheet_id, config.ANIADIR_BD_SHEET)
        rucs_existentes, hay_encabezado = _leer_existentes_por_columna(
            service,
            spreadsheet_id,
            config.ANIADIR_BD_SHEET,
            "RUC",
        )

        filas_nuevas = [
            [ruc, "", "", "" if pd.isna(nombre) else str(nombre)]
            for ruc, nombre in zip(candidatos_aniadir["ruc"], candidatos_aniadir["nombre_entidad"])
            if ruc not in rucs_existentes
        ]

        if filas_nuevas:
            if hay_encabezado:
                append_rows(service, spreadsheet_id, config.ANIADIR_BD_SHEET, filas_nuevas)
            else:
                write_rows(service, spreadsheet_id, config.ANIADIR_BD_SHEET, [COLUMNAS_ENTIDAD] + filas_nuevas)
            print(f"Nuevos registros agregados a '{config.ANIADIR_BD_SHEET}': {len(filas_nuevas)}")
        else:
            print(f"Sin registros nuevos para '{config.ANIADIR_BD_SHEET}'.")

    mask_sin_ruc = (
        df["ruc"].astype(str).str.strip().isin(["", "0"])
        & ~es_vacio(df["nombre_entidad"])
        & (df["match_entidad"] == "NO")
    )

    nombres_candidatos = (
        df.loc[mask_sin_ruc, "nombre_entidad"]
        .astype(str)
        .str.strip()
        .drop_duplicates()
        .tolist()
    )

    print(f"\nCandidatos para {config.ENTIDADES_SIN_RUC_SHEET}: {len(nombres_candidatos)}")

    if nombres_candidatos:
        ensure_sheet_exists(service, spreadsheet_id, config.ENTIDADES_SIN_RUC_SHEET)
        nombres_existentes, hay_encabezado = _leer_existentes_por_columna(
            service,
            spreadsheet_id,
            config.ENTIDADES_SIN_RUC_SHEET,
            "Nombre de entidad",
        )

        nombres_nuevos = [n for n in nombres_candidatos if n not in nombres_existentes]
        if nombres_nuevos:
            filas_nuevas = [["", "", "", nombre] for nombre in sorted(nombres_nuevos)]
            if hay_encabezado:
                append_rows(service, spreadsheet_id, config.ENTIDADES_SIN_RUC_SHEET, filas_nuevas)
            else:
                write_rows(
                    service,
                    spreadsheet_id,
                    config.ENTIDADES_SIN_RUC_SHEET,
                    [COLUMNAS_ENTIDAD] + filas_nuevas,
                )
            print(
                f"Nuevas entidades agregadas a '{config.ENTIDADES_SIN_RUC_SHEET}': "
                f"{len(nombres_nuevos)}"
            )
        else:
            print(f"Sin entidades nuevas para '{config.ENTIDADES_SIN_RUC_SHEET}'.")
