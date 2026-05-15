from __future__ import annotations

from io import BytesIO
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_procesamiento import config
from app_procesamiento.core.certificados import (
    agregar_certificado_por_total,
    calcular_condicion_y_constancia,
)
from app_procesamiento.core.columnas import (
    convertir_columnas_calificacion,
    eliminar_columnas_actividad,
    mover_columna_despues_de_otra,
    ordenar_bloque_calificaciones,
    ordenar_columnas_intermedias,
    ordenar_por_calificaciones,
)
from app_procesamiento.core.entidades import (
    aplicar_match_por_nombre,
    aplicar_match_por_ruc,
    cargar_bd_entidades,
    cargar_etiquetas_entidad,
    registrar_pendientes_en_sheets,
    validar_ruc_para_match,
)
from app_procesamiento.core.google_sheets import SCOPES, extract_spreadsheet_id
from app_procesamiento.core.lectores import leer_calificados, leer_examen, leer_examen_final
from app_procesamiento.core.limpieza_laboral import (
    aplicar_correcciones_post_match,
    aplicar_reglas_limpieza_inicial,
    normalizar_columnas_por_situacion_laboral,
)
from app_procesamiento.core.transformaciones import (
    eliminar_columnas_basura,
    eliminar_columnas_exportacion,
    limpiar_campos_generales,
    unir_fuentes,
)
from app_procesamiento.core.utils import normalizar_dni


st.set_page_config(
    page_title="Procesamiento OECE",
    layout="wide",
)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def leer_actividades_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    cols = pd.read_csv(
        uploaded_file,
        encoding="utf-16",
        sep="\t",
        nrows=0,
    ).columns

    uploaded_file.seek(0)
    df = pd.read_csv(
        uploaded_file,
        encoding="utf-16",
        sep="\t",
        dtype={"DNI": "object"},
        usecols=[cols[1]] + list(cols[3:]),
    )

    df["DNI"] = normalizar_dni(df["DNI"])
    return df


def leer_excel(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return pd.read_excel(uploaded_file)


def leer_calificados_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_calificados(uploaded_file)


def leer_examen_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_examen(uploaded_file)


def leer_examen_final_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_examen_final(uploaded_file)


@st.cache_resource(show_spinner=False)
def sheets_service_from_secrets():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError("Falta configurar [gcp_service_account] en los secrets de Streamlit.")

    info = dict(st.secrets["gcp_service_account"])
    if "private_key" in info:
        info["private_key"] = info["private_key"].replace("\\n", "\n")

    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False)


@st.cache_data(ttl=600, show_spinner=False)
def cargar_bd_y_etiquetas(_service, spreadsheet_id: str, hoja_bd: str, hoja_aniadir: str, hoja_etiquetas: str):
    bd = cargar_bd_entidades(
        _service,
        spreadsheet_id,
        hoja_consolidado=hoja_bd,
        hoja_aniadir=hoja_aniadir,
    )
    etiquetas = cargar_etiquetas_entidad(_service, spreadsheet_id, hoja_etiquetas)
    return bd, etiquetas


def contexto_google(spreadsheet_url: str, hoja_bd: str, hoja_aniadir: str, hoja_etiquetas: str):
    service = sheets_service_from_secrets()
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url)
    bd, etiquetas = cargar_bd_y_etiquetas(service, spreadsheet_id, hoja_bd, hoja_aniadir, hoja_etiquetas)
    return service, spreadsheet_id, bd, etiquetas


def limpiar_calificaciones(uploaded_file, registrar_pendientes: bool, cfg: dict):
    service, spreadsheet_id, bd, etiquetas = contexto_google(
        cfg["spreadsheet_url"],
        cfg["hoja_bd"],
        cfg["hoja_aniadir"],
        cfg["hoja_etiquetas"],
    )

    df = leer_excel(uploaded_file)
    registros_cargados = len(df)

    df, nombres_normalizados = aplicar_reglas_limpieza_inicial(df, etiquetas)
    df = validar_ruc_para_match(df)
    df, matches_ruc = aplicar_match_por_ruc(df, bd, reset_match=True)
    df, matches_nombre = aplicar_match_por_nombre(df, bd)
    df = aplicar_correcciones_post_match(df)

    if registrar_pendientes:
        registrar_pendientes_en_sheets(service, spreadsheet_id, df)

    return df, {
        "Registros cargados": registros_cargados,
        "Registros procesados": len(df),
        "Nombres normalizados": nombres_normalizados,
        "Matches por RUC": matches_ruc,
        "Matches por nombre": matches_nombre,
    }


def finalizar_calificaciones(uploaded_file, cfg: dict):
    _, _, bd, _ = contexto_google(
        cfg["spreadsheet_url"],
        cfg["hoja_bd"],
        cfg["hoja_aniadir"],
        cfg["hoja_etiquetas"],
    )

    df = leer_excel(uploaded_file)
    registros_cargados = len(df)

    df = validar_ruc_para_match(df)
    df, matches_ruc = aplicar_match_por_ruc(df, bd, reset_match=True)
    df, matches_nombre = aplicar_match_por_nombre(df, bd)
    df = normalizar_columnas_por_situacion_laboral(df)

    return df, {
        "Registros cargados": registros_cargados,
        "Registros procesados": len(df),
        "Matches por RUC": matches_ruc,
        "Matches por nombre": matches_nombre,
    }


def procesar_microlearning(actividades_file, dataset_file, examen_entrada_file, examen_final_file):
    actividades = leer_actividades_upload(actividades_file)
    calificados = leer_calificados_upload(dataset_file)
    df = unir_fuentes(calificados, actividades)

    if examen_entrada_file is not None:
        df = df.merge(leer_examen_upload(examen_entrada_file), on="DNI", how="outer")

    if examen_final_file is not None:
        df = df.merge(
            leer_examen_final_upload(examen_final_file),
            on="DNI",
            how="outer",
            suffixes=("", "_final"),
        )

    df = eliminar_columnas_actividad(df, "microlearning")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = convertir_columnas_calificacion(df)
    df = ordenar_bloque_calificaciones(df)
    df = ordenar_columnas_intermedias(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")
    df = ordenar_por_calificaciones(df)
    df = agregar_certificado_por_total(df, crear_si_no_hay_total=False)
    return eliminar_columnas_exportacion(df)


def procesar_mooc(actividades_file, dataset_file, examen_entrada_file, examen_final_file):
    actividades = leer_actividades_upload(actividades_file)
    calificados = leer_calificados_upload(dataset_file)
    df = unir_fuentes(calificados, actividades)

    if examen_entrada_file is not None:
        df = df.merge(leer_examen_upload(examen_entrada_file), on="DNI", how="outer")

    df = df.merge(
        leer_examen_final_upload(examen_final_file),
        on="DNI",
        how="outer",
        suffixes=("", "_final"),
    )

    df = eliminar_columnas_actividad(df, "mooc")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = convertir_columnas_calificacion(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")
    df = mover_columna_despues_de_otra(df, "total_curso", "Calificación/20,00_final")
    df = ordenar_bloque_calificaciones(df)
    df = ordenar_por_calificaciones(df)
    df = agregar_certificado_por_total(df, crear_si_no_hay_total=True)
    return eliminar_columnas_exportacion(df)


def procesar_videoconferencia(actividades_file, dataset_file):
    actividades = leer_actividades_upload(actividades_file)
    calificados = leer_calificados_upload(dataset_file)

    df = unir_fuentes(calificados, actividades)
    df = eliminar_columnas_actividad(df, "videoconferencia")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = calcular_condicion_y_constancia(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")

    if {"condicion", "certificado"}.issubset(df.columns):
        df = df.sort_values(by=["condicion", "certificado"], ascending=[True, True])

    return eliminar_columnas_exportacion(df)


def mostrar_metricas(metricas: dict) -> None:
    columnas = st.columns(len(metricas))
    for columna, (label, value) in zip(columnas, metricas.items()):
        columna.metric(label, value)


def descargar_excel(df: pd.DataFrame, filename: str, label: str) -> None:
    st.download_button(
        label=label,
        data=to_excel_bytes(df),
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )


st.title("Procesamiento OECE")

with st.sidebar:
    st.header("Google Sheets")
    spreadsheet_url = st.text_input("URL bd_entidades", value=config.BD_ENTIDADES_URL)
    hoja_bd = st.text_input("Hoja principal", value=config.BD_ENTIDADES_SHEET)
    hoja_aniadir = st.text_input("Hoja adicional", value=config.BD_ANIADIR_SHEET)
    hoja_etiquetas = st.text_input("Hoja etiquetas", value=config.BD_ETIQUETAS_SHEET)
    registrar_pendientes = st.checkbox("Registrar pendientes", value=False)

cfg = {
    "spreadsheet_url": spreadsheet_url,
    "hoja_bd": hoja_bd,
    "hoja_aniadir": hoja_aniadir,
    "hoja_etiquetas": hoja_etiquetas,
}

tab_limpiar, tab_finalizar, tab_procesar = st.tabs(
    ["Limpiar calificaciones", "Finalizar dataset", "Procesar actividad"]
)

with tab_limpiar:
    archivo_calificaciones = st.file_uploader(
        "Calificaciones original",
        type=["xlsx"],
        key="calificaciones_original",
    )

    if st.button("Limpiar", type="primary", disabled=archivo_calificaciones is None, use_container_width=True):
        try:
            with st.spinner("Procesando..."):
                df_limpio, metricas = limpiar_calificaciones(
                    archivo_calificaciones,
                    registrar_pendientes,
                    cfg,
                )
            mostrar_metricas(metricas)
            descargar_excel(df_limpio, "dataset_limpiado.xlsx", "Descargar dataset_limpiado.xlsx")
        except Exception as error:
            st.error(str(error))
            with st.expander("Detalle tecnico"):
                st.exception(error)

with tab_finalizar:
    archivo_limpiado = st.file_uploader(
        "dataset_limpiado.xlsx depurado",
        type=["xlsx"],
        key="dataset_limpiado",
    )

    if st.button("Finalizar", type="primary", disabled=archivo_limpiado is None, use_container_width=True):
        try:
            with st.spinner("Procesando..."):
                df_final, metricas = finalizar_calificaciones(archivo_limpiado, cfg)
            mostrar_metricas(metricas)
            descargar_excel(df_final, "dataset_final.xlsx", "Descargar dataset_final.xlsx")
        except Exception as error:
            st.error(str(error))
            with st.expander("Detalle tecnico"):
                st.exception(error)

with tab_procesar:
    tipo_actividad = st.radio(
        "Tipo",
        ["Videoconferencia", "Microlearning", "MOOC"],
        horizontal=True,
        default="Videoconferencia",
    )

    col1, col2 = st.columns(2)
    with col1:
        actividades = st.file_uploader("Actividades CSV", type=["csv"], key=f"act_{tipo_actividad}")
    with col2:
        dataset_final = st.file_uploader("dataset_final.xlsx", type=["xlsx"], key=f"final_{tipo_actividad}")

    examen_entrada = None
    examen_final = None

    if tipo_actividad in {"Microlearning", "MOOC"}:
        col3, col4 = st.columns(2)
        with col3:
            examen_entrada = st.file_uploader(
                "Examen de entrada",
                type=["xlsx"],
                key=f"entrada_{tipo_actividad}",
            )
        with col4:
            examen_final = st.file_uploader(
                "Examen final",
                type=["xlsx"],
                key=f"final_exam_{tipo_actividad}",
            )

    requiere_examen_final = tipo_actividad == "MOOC"
    listo = actividades is not None and dataset_final is not None and (
        not requiere_examen_final or examen_final is not None
    )

    if st.button("Procesar actividad", type="primary", disabled=not listo, use_container_width=True):
        try:
            with st.spinner("Procesando..."):
                if tipo_actividad == "Videoconferencia":
                    df_resultado = procesar_videoconferencia(actividades, dataset_final)
                    nombre_archivo = "videoconferencia_procesado.xlsx"
                elif tipo_actividad == "Microlearning":
                    df_resultado = procesar_microlearning(
                        actividades,
                        dataset_final,
                        examen_entrada,
                        examen_final,
                    )
                    nombre_archivo = "microlearning_procesado.xlsx"
                else:
                    df_resultado = procesar_mooc(
                        actividades,
                        dataset_final,
                        examen_entrada,
                        examen_final,
                    )
                    nombre_archivo = "mooc_procesado.xlsx"

            mostrar_metricas({"Registros procesados": len(df_resultado)})
            descargar_excel(df_resultado, nombre_archivo, f"Descargar {nombre_archivo}")
        except Exception as error:
            st.error(str(error))
            with st.expander("Detalle tecnico"):
                st.exception(error)
