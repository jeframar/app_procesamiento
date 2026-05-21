from __future__ import annotations

from contextlib import redirect_stdout
from io import BytesIO
from io import StringIO
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from googleapiclient.discovery import build
from streamlit.errors import StreamlitSecretNotFoundError


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
from app_procesamiento.core.diagnosticos import imprimir_diagnostico_duplicados_dni
from app_procesamiento.core.entidades import (
    aplicar_match_por_nombre,
    aplicar_match_por_ruc,
    cargar_bd_entidades,
    cargar_etiquetas_entidad,
    registrar_pendientes_en_sheets,
    validar_ruc_para_match,
)
from app_procesamiento.core.google_sheets import (
    SCOPES,
    build_sheets_service,
    extract_spreadsheet_id,
)
from app_procesamiento.core.lectores import (
    leer_actividades,
    leer_calificados,
    leer_examen,
    leer_examen_final,
)
from app_procesamiento.core.limpieza_laboral import (
    aplicar_correcciones_post_match,
    aplicar_reglas_limpieza_inicial,
    normalizar_columnas_por_situacion_laboral,
)
from app_procesamiento.core.transformaciones import (
    eliminar_columnas_basura,
    eliminar_columnas_exportacion,
    limpiar_campos_generales,
    merge_por_dni_o_nombre,
    unir_fuentes,
)


st.set_page_config(
    page_title="Procesamiento de datos",
    layout="wide",
)


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False)
    return output.getvalue()


def leer_actividades_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_actividades(uploaded_file)


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


def streamlit_service_account_info() -> dict | None:
    try:
        if "gcp_service_account" not in st.secrets:
            return None
        return dict(st.secrets["gcp_service_account"])
    except StreamlitSecretNotFoundError:
        return None


@st.cache_resource(show_spinner=False)
def sheets_service_from_secrets():
    info = streamlit_service_account_info()
    if info is not None:
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")

        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    credentials_path = config.CREDENTIALS_PATH
    token_path = config.TOKEN_PATH
    if not credentials_path.is_absolute():
        credentials_path = ROOT / credentials_path
    if not token_path.is_absolute():
        token_path = ROOT / token_path

    if credentials_path.exists():
        return build_sheets_service(credentials_path, token_path)

    raise RuntimeError(
        "No hay credenciales de Google Sheets configuradas. "
        "Para ejecucion local, crea .streamlit/secrets.toml a partir de "
        ".streamlit/secrets.example.toml o coloca credentials.json en la raiz "
        "del proyecto. En Streamlit Cloud, configura [gcp_service_account] en "
        "App settings > Secrets."
    )


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
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
        examen_entrada_file,
        examen_final_file,
    )

    actividades = leer_actividades_upload(actividades_file)
    calificados = leer_calificados_upload(dataset_file)
    df = unir_fuentes(calificados, actividades)

    if examen_entrada_file is not None:
        df = merge_por_dni_o_nombre(
            df,
            leer_examen_upload(examen_entrada_file),
            "examen entrada",
        )

    if examen_final_file is not None:
        df = merge_por_dni_o_nombre(
            df,
            leer_examen_final_upload(examen_final_file),
            "examen final",
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
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
        examen_entrada_file,
        examen_final_file,
    )

    actividades = leer_actividades_upload(actividades_file)
    calificados = leer_calificados_upload(dataset_file)
    df = unir_fuentes(calificados, actividades)

    if examen_entrada_file is not None:
        df = merge_por_dni_o_nombre(
            df,
            leer_examen_upload(examen_entrada_file),
            "examen entrada",
        )

    df = merge_por_dni_o_nombre(
        df,
        leer_examen_final_upload(examen_final_file),
        "examen final",
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
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
    )

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


def mostrar_mensajes_procesamiento(mensajes: str) -> None:
    lineas = [linea.rstrip() for linea in mensajes.splitlines() if linea.strip()]
    if not lineas:
        return

    incidentes = [linea for linea in lineas if linea.startswith("INCIDENTE:")]

    for incidente in incidentes:
        st.warning(incidente)

    with st.expander("Mensajes del procesamiento", expanded=bool(incidentes)):
        st.text("\n".join(lineas))


def inject_css() -> None:
    st.markdown(
        """
<style>
:root {
    --oece-blue: #0D406B;
    --oece-blue-dark: #083455;
    --oece-yellow: #F5A802;
    --oece-gray: #575556;
    --oece-bg: #F3F7FB;
    --oece-card: #FFFFFF;
    --oece-border: #D9E4EF;
    --oece-upload-bg: #EAF2F8;
    --oece-text: #1F2933;
    --oece-success: #0F766E;
    --oece-error: #B42318;
}

.stApp { background-color: var(--oece-bg); }

.block-container {
    padding-top: 2rem;
    padding-bottom: 3rem;
    max-width: 1180px;
}

.block-container::before {
    content: "";
    display: block;
    height: 6px;
    width: 100%;
    background: linear-gradient(90deg, var(--oece-blue) 0%, var(--oece-blue) 72%, var(--oece-yellow) 72%, var(--oece-yellow) 100%);
    border-radius: 999px;
    margin-bottom: 1.75rem;
}

section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #FFFFFF 0%, #F3F7FB 100%);
    border-right: 1px solid var(--oece-border);
}

section[data-testid="stSidebar"] h1,
section[data-testid="stSidebar"] h2,
section[data-testid="stSidebar"] h3 { color: var(--oece-blue); }

section[data-testid="stSidebar"] h2 {
    font-size: 1.15rem;
    margin-top: 0.25rem;
    margin-bottom: 0.75rem;
    border-bottom: 2px solid var(--oece-yellow);
    display: inline-block;
    padding-bottom: 0.15rem;
}

section[data-testid="stSidebar"] h3 {
    font-size: 0.9rem;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    margin-top: 1.2rem;
    margin-bottom: 0.4rem;
    color: var(--oece-gray);
    font-weight: 700;
}

h1 { color: var(--oece-blue); font-weight: 800; letter-spacing: -0.6px; margin-bottom: 0.15rem; }
h2, h3 { color: var(--oece-blue); font-weight: 700; }
p, label, span { color: var(--oece-text); }

.oece-header { padding: 0.1rem 0 0.4rem 0; }
.oece-header h1 { margin-bottom: 0.2rem; }
.oece-subtitle {
    color: var(--oece-gray);
    font-size: 1rem;
    margin: 0;
    font-weight: 500;
}

.stTextInput input {
    border-radius: 10px;
    border: 1px solid var(--oece-border);
    background-color: #FFFFFF;
}
.stTextInput input:focus {
    border-color: var(--oece-blue);
    box-shadow: 0 0 0 1px var(--oece-blue);
}

.stButton > button {
    background-color: var(--oece-blue);
    color: #FFFFFF;
    border: 1px solid var(--oece-blue);
    border-radius: 10px;
    font-weight: 700;
    padding: 0.65rem 1.2rem;
    transition: all 0.15s ease-in-out;
}
.stButton > button:not(:disabled) * {
    color: #FFFFFF !important;
}
.stButton > button:hover:not(:disabled) {
    background-color: var(--oece-blue-dark);
    border-color: var(--oece-blue-dark);
    color: #FFFFFF;
}
.stButton > button:hover:not(:disabled) * {
    color: #FFFFFF !important;
}
.stButton > button:disabled {
    background-color: #E5EAF0;
    color: #8A94A3;
    border: 1px solid #D0D7E2;
    cursor: not-allowed;
}
.stButton > button:disabled * {
    color: #8A94A3 !important;
}

.stDownloadButton > button {
    background-color: var(--oece-yellow);
    color: var(--oece-blue);
    border: 1px solid var(--oece-yellow);
    border-radius: 10px;
    font-weight: 700;
}
.stDownloadButton > button:hover {
    background-color: #E69A02;
    border-color: #E69A02;
    color: var(--oece-blue);
}

section[data-testid="stFileUploader"] {
    background-color: var(--oece-upload-bg);
    border: 1.5px dashed #9BB7CE;
    border-radius: 14px;
    padding: 1rem;
}
section[data-testid="stFileUploader"]:hover {
    border-color: var(--oece-blue);
    background-color: #E3EEF7;
}
section[data-testid="stFileUploader"] label { color: var(--oece-blue); font-weight: 600; }

div[data-baseweb="tab-list"] {
    gap: 0.5rem;
    border-bottom: 1px solid var(--oece-border);
}
button[data-baseweb="tab"] {
    font-weight: 700;
    color: var(--oece-gray);
    background-color: transparent;
    padding-top: 0.75rem;
    padding-bottom: 0.75rem;
}
button[data-baseweb="tab"][aria-selected="true"] {
    color: var(--oece-blue);
    border-bottom: 3px solid var(--oece-yellow);
}
div[data-baseweb="tab-highlight"] { background-color: transparent !important; }

div[role="radiogroup"] label {
    background-color: #FFFFFF;
    border: 1px solid var(--oece-border);
    border-radius: 999px;
    padding: 0.35rem 0.9rem;
    margin-right: 0.35rem;
    color: var(--oece-text);
}
div[role="radiogroup"] label[data-checked="true"] {
    background-color: var(--oece-blue);
    border-color: var(--oece-blue);
    color: #FFFFFF;
}

div[data-testid="stHorizontalBlock"] { gap: 1.25rem; }

.oece-card {
    background-color: var(--oece-card);
    border: 1px solid var(--oece-border);
    border-radius: 18px;
    padding: 1.4rem 1.5rem;
    box-shadow: 0 8px 24px rgba(13, 64, 107, 0.06);
    margin-bottom: 1.25rem;
}

.oece-section-title {
    color: var(--oece-blue);
    font-size: 1.2rem;
    font-weight: 800;
    margin: 0 0 0.25rem 0;
}
.oece-section-description {
    color: var(--oece-gray);
    font-size: 0.95rem;
    margin: 0;
}

.oece-divider {
    height: 1px;
    background: var(--oece-border);
    margin: 1rem 0 1.25rem 0;
    border: 0;
}

div[data-testid="stAlert"] { border-radius: 12px; }

div[data-testid="stMetric"] {
    background-color: #FFFFFF;
    border: 1px solid var(--oece-border);
    border-radius: 14px;
    padding: 0.85rem 1rem;
    box-shadow: 0 4px 12px rgba(13, 64, 107, 0.04);
}
div[data-testid="stMetricLabel"] { color: var(--oece-gray); font-weight: 600; }
div[data-testid="stMetricValue"] { color: var(--oece-blue); font-weight: 800; }
</style>
        """,
        unsafe_allow_html=True,
    )


def _find_logo() -> Path | None:
    for ext in ("png", "jpg", "jpeg"):
        candidate = ROOT / f"logo_oece.{ext}"
        if candidate.exists():
            return candidate
    return None


def render_header() -> None:
    logo = _find_logo()
    subtitulo = "Sistema de depuración, consolidación y procesamiento de actividades"

    if logo is not None:
        col_logo, col_text = st.columns([1, 6])
        with col_logo:
            st.image(str(logo), width=110)
        with col_text:
            st.markdown(
                f'<div class="oece-header">'
                f'<h1>Procesamiento OECE</h1>'
                f'<p class="oece-subtitle">{subtitulo}</p>'
                f'</div>',
                unsafe_allow_html=True,
            )
    else:
        st.markdown(
            f'<div class="oece-header">'
            f'<h1>Procesamiento de datos</h1>'
            f'<p class="oece-subtitle">{subtitulo}</p>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_card_open(title: str, description: str) -> None:
    st.markdown(
        f'<div class="oece-card">'
        f'<p class="oece-section-title">{title}</p>'
        f'<p class="oece-section-description">{description}</p>'
        f'<hr class="oece-divider" />'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_card_close() -> None:
    st.markdown('<div style="margin-bottom: 1.25rem;"></div>', unsafe_allow_html=True)


def render_sidebar() -> dict:
    with st.sidebar:
        st.markdown("## Configuración")

        st.markdown("### Google Sheets")
        spreadsheet_url = st.text_input("URL bd_entidades", value=config.BD_ENTIDADES_URL)

        st.markdown("### Hojas de trabajo")
        hoja_bd = st.text_input("Hoja principal", value=config.BD_ENTIDADES_SHEET)
        hoja_aniadir = st.text_input("Hoja adicional", value=config.BD_ANIADIR_SHEET)
        hoja_etiquetas = st.text_input("Hoja etiquetas", value=config.BD_ETIQUETAS_SHEET)

        st.markdown("### Opciones")
        registrar_pendientes = st.checkbox("Registrar pendientes", value=False)

    return {
        "cfg": {
            "spreadsheet_url": spreadsheet_url,
            "hoja_bd": hoja_bd,
            "hoja_aniadir": hoja_aniadir,
            "hoja_etiquetas": hoja_etiquetas,
        },
        "registrar_pendientes": registrar_pendientes,
    }


def render_action_button_right(label: str, *, key: str, disabled: bool) -> bool:
    _, col_btn = st.columns([3, 2])
    with col_btn:
        return st.button(
            label,
            type="primary",
            disabled=disabled,
            use_container_width=True,
            key=key,
        )


inject_css()
render_header()

sidebar_state = render_sidebar()
cfg = sidebar_state["cfg"]
registrar_pendientes = sidebar_state["registrar_pendientes"]

tab_limpiar, tab_finalizar, tab_procesar = st.tabs(
    ["Limpiar calificaciones", "Finalizar dataset", "Procesar actividad"]
)

with tab_limpiar:
    render_card_open(
        "Limpiar calificaciones",
        "Carga el archivo original de calificaciones en formato XLSX para generar una versión depurada.",
    )

    archivo_calificaciones = st.file_uploader(
        "Calificaciones original",
        type=["xlsx"],
        key="calificaciones_original",
    )

    clic_limpiar = render_action_button_right(
        "Limpiar calificaciones",
        key="btn_limpiar",
        disabled=archivo_calificaciones is None,
    )

    if clic_limpiar:
        try:
            with st.spinner("Procesando..."):
                df_limpio, metricas = limpiar_calificaciones(
                    archivo_calificaciones,
                    registrar_pendientes,
                    cfg,
                )
            st.success("Calificaciones limpiadas correctamente.")
            mostrar_metricas(metricas)
            descargar_excel(df_limpio, "dataset_limpiado.xlsx", "Descargar dataset_limpiado.xlsx")
        except Exception as error:
            st.error(str(error))
            with st.expander("Detalle técnico"):
                st.exception(error)

    render_card_close()

with tab_finalizar:
    render_card_open(
        "Finalizar dataset",
        "Carga el archivo depurado para consolidarlo con la información configurada en Google Sheets.",
    )

    archivo_limpiado = st.file_uploader(
        "Dataset depurado",
        type=["xlsx"],
        key="dataset_limpiado",
    )

    clic_finalizar = render_action_button_right(
        "Finalizar dataset",
        key="btn_finalizar",
        disabled=archivo_limpiado is None,
    )

    if clic_finalizar:
        try:
            with st.spinner("Procesando..."):
                df_final, metricas = finalizar_calificaciones(archivo_limpiado, cfg)
            st.success("Dataset consolidado correctamente.")
            mostrar_metricas(metricas)
            descargar_excel(df_final, "dataset_final.xlsx", "Descargar dataset_final.xlsx")
        except Exception as error:
            st.error(str(error))
            with st.expander("Detalle técnico"):
                st.exception(error)

    render_card_close()

with tab_procesar:
    render_card_open(
        "Procesar actividad",
        "Selecciona el tipo de actividad y carga los archivos requeridos para procesar la información.",
    )

    tipo_actividad = st.radio(
        "Tipo de actividad",
        ["Videoconferencia", "Microlearning", "MOOC"],
        horizontal=True,
        index=0,
    )

    col1, col2 = st.columns(2)
    with col1:
        actividades = st.file_uploader(
            "Actividades CSV",
            type=["csv"],
            key=f"act_{tipo_actividad}",
        )
    with col2:
        dataset_final = st.file_uploader(
            "Dataset final XLSX",
            type=["xlsx"],
            key=f"final_{tipo_actividad}",
        )

    examen_entrada = None
    examen_final = None

    if tipo_actividad in {"Microlearning", "MOOC"}:
        col3, col4 = st.columns(2)
        with col3:
            examen_entrada = st.file_uploader(
                "Examen de entrada (XLSX)",
                type=["xlsx"],
                key=f"entrada_{tipo_actividad}",
            )
        with col4:
            examen_final = st.file_uploader(
                "Examen final (XLSX)",
                type=["xlsx"],
                key=f"final_exam_{tipo_actividad}",
            )

    requiere_examen_final = tipo_actividad == "MOOC"
    listo = (
        actividades is not None
        and dataset_final is not None
        and (not requiere_examen_final or examen_final is not None)
    )

    if not listo:
        faltantes = []
        if actividades is None:
            faltantes.append("Actividades CSV")
        if dataset_final is None:
            faltantes.append("Dataset final XLSX")
        if requiere_examen_final and examen_final is None:
            faltantes.append("Examen final (requerido para MOOC)")
        if faltantes:
            st.info("Faltan archivos: " + ", ".join(faltantes) + ".")

    clic_procesar = render_action_button_right(
        "Procesar actividad",
        key="btn_procesar",
        disabled=not listo,
    )

    if clic_procesar:
        mensajes_buffer = StringIO()
        try:
            with st.spinner("Procesando..."):
                with redirect_stdout(mensajes_buffer):
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

            st.success(f"{tipo_actividad} procesado correctamente.")
            mostrar_mensajes_procesamiento(mensajes_buffer.getvalue())
            mostrar_metricas({"Registros procesados": len(df_resultado)})
            descargar_excel(df_resultado, nombre_archivo, f"Descargar {nombre_archivo}")
        except Exception as error:
            mostrar_mensajes_procesamiento(mensajes_buffer.getvalue())
            st.error(str(error))
            with st.expander("Detalle técnico"):
                st.exception(error)

    render_card_close()
