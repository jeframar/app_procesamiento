from __future__ import annotations

from contextlib import redirect_stdout
from datetime import datetime
from io import BytesIO
from io import StringIO
from pathlib import Path
import sys
from time import time_ns

import pandas as pd
import streamlit as st
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from streamlit.errors import StreamlitSecretNotFoundError


ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app_procesamiento import config
from app_procesamiento.core.diagnosticos import imprimir_diagnostico_duplicados_dni
from app_procesamiento.core.entidades import (
    cargar_bd_entidades,
    cargar_etiquetas_entidad,
)
from app_procesamiento.core.errores_match_no import (
    AnalisisErroresMatchNo,
)
from app_procesamiento.core.finalizacion_calificaciones import finalizar_dataset_calificaciones
from app_procesamiento.core.google_sheets import (
    SCOPES,
    extract_spreadsheet_id,
)
from app_procesamiento.core.lectores import (
    leer_actividades,
    leer_calificados,
    leer_evaluacion_intermedia,
    leer_examen,
    leer_examen_final,
)
from app_procesamiento.core.limpieza_calificaciones import limpiar_dataset_calificaciones
from app_procesamiento.core.procesamiento_actividades import (
    procesar_microlearning_dataset,
    procesar_mooc_dataset,
    procesar_videoconferencia_dataset,
)
from app_procesamiento.core.utils import normalizar_ruc_para_match


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
    return pd.read_excel(uploaded_file, dtype={"ruc": "string", "RUC": "string"})


def diagnosticar_ruc_match(df: pd.DataFrame, bd: pd.DataFrame) -> dict[str, int]:
    rucs_dataset = (
        normalizar_ruc_para_match(df["ruc"])
        if "ruc" in df.columns
        else pd.Series(dtype=str)
    )
    rucs_bd = (
        normalizar_ruc_para_match(bd["RUC"])
        if "RUC" in bd.columns
        else pd.Series(dtype=str)
    )

    rucs_dataset_validos = set(rucs_dataset[rucs_dataset != "0"])
    rucs_bd_validos = set(rucs_bd[rucs_bd != "0"])

    return {
        "ruc_validos_dataset": len(rucs_dataset_validos),
        "ruc_validos_bd": len(rucs_bd_validos),
        "ruc_comunes": len(rucs_dataset_validos & rucs_bd_validos),
    }


def leer_calificados_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_calificados(uploaded_file)


def leer_examen_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_examen(uploaded_file)


def leer_examen_final_upload(uploaded_file) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_examen_final(uploaded_file)


def leer_evaluacion_intermedia_upload(uploaded_file, numero: int) -> pd.DataFrame:
    uploaded_file.seek(0)
    return leer_evaluacion_intermedia(uploaded_file, numero)


def fecha_emision_por_defecto():
    return datetime.strptime(config.FECHA_EMISION_CERTIFICADO, "%d-%m-%Y").date()


def streamlit_secret_section(name: str) -> dict | None:
    try:
        if name not in st.secrets:
            return None
        return dict(st.secrets[name])
    except StreamlitSecretNotFoundError:
        return None


def streamlit_service_account_info() -> dict | None:
    return streamlit_secret_section("gcp_service_account")


def streamlit_auth_info() -> dict | None:
    return streamlit_secret_section("auth")


def has_legacy_oauth_web_config() -> bool:
    return streamlit_secret_section("google_oauth_web") is not None


def user_is_logged_in() -> bool:
    return bool(getattr(st.user, "is_logged_in", False))


def streamlit_access_token() -> str | None:
    try:
        return st.user.tokens.get("access")
    except Exception:
        return None


def streamlit_user_credentials() -> UserCredentials:
    access_token = streamlit_access_token()
    if not access_token:
        raise RuntimeError(
            "La autenticacion de Streamlit no expuso un access token. "
            "Configura expose_tokens = \"access\" y agrega el scope de Google Sheets "
            "en [auth].client_kwargs."
        )

    return UserCredentials(token=access_token, scopes=SCOPES)


def render_streamlit_login() -> None:
    st.markdown("### Iniciar sesión con Google")
    st.info(
        "Autenticate con tu cuenta institucional para acceder a Google Sheets. "
        "Luego podras usar la app completa durante esta sesión."
    )
    if st.button("Iniciar sesión con Google", type="primary"):
        st.login()


def ensure_google_auth_ready() -> None:
    if streamlit_service_account_info() is not None:
        return

    if streamlit_auth_info() is None:
        if has_legacy_oauth_web_config():
            st.error(
                "La configuracion [google_oauth_web] ya no se usa. "
                "Migra los secrets al bloque [auth] de Streamlit."
            )
            st.stop()
        return

    if not user_is_logged_in():
        render_streamlit_login()
        st.stop()

    if streamlit_access_token() is None:
        st.error(
            "Inicio de sesión correcto, pero falta el access token para Google Sheets. "
            "En [auth], configura expose_tokens = \"access\" y el scope "
            "https://www.googleapis.com/auth/spreadsheets."
        )
        st.stop()


def sheets_service_from_secrets():
    info = streamlit_service_account_info()
    if info is not None:
        if "private_key" in info:
            info["private_key"] = info["private_key"].replace("\\n", "\n")

        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    if streamlit_auth_info() is not None:
        creds = streamlit_user_credentials()
        return build("sheets", "v4", credentials=creds, cache_discovery=False)

    if has_legacy_oauth_web_config():
        raise RuntimeError(
            "La configuracion [google_oauth_web] ya no se usa. "
            "Migra los secrets al bloque [auth] de Streamlit."
        )

    raise RuntimeError(
        "No hay credenciales de Google Sheets configuradas. "
        "Configura [auth] o "
        "[gcp_service_account] en App settings > Secrets."
    )


def cargar_bd_y_etiquetas(
    _service,
    spreadsheet_id: str,
    hoja_bd: str,
    hoja_aniadir: str,
    hoja_etiquetas: str,
    recarga_id: int | None = None,
):
    del recarga_id
    bd = cargar_bd_entidades(
        _service,
        spreadsheet_id,
        hoja_consolidado=hoja_bd,
        hoja_aniadir=hoja_aniadir,
    )
    etiquetas = cargar_etiquetas_entidad(_service, spreadsheet_id, hoja_etiquetas)
    return bd, etiquetas


def contexto_google(
    spreadsheet_url: str,
    hoja_bd: str,
    hoja_aniadir: str,
    hoja_etiquetas: str,
    recarga_id: int | None = None,
):
    service = sheets_service_from_secrets()
    spreadsheet_id = extract_spreadsheet_id(spreadsheet_url)
    bd, etiquetas = cargar_bd_y_etiquetas(
        service,
        spreadsheet_id,
        hoja_bd,
        hoja_aniadir,
        hoja_etiquetas,
        recarga_id=recarga_id,
    )
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

    df, nombres_normalizados, matches_ruc, matches_nombre = limpiar_dataset_calificaciones(
        df,
        bd,
        etiquetas,
        registrar_pendientes=registrar_pendientes,
        service=service,
        spreadsheet_id=spreadsheet_id,
    )

    return df, {
        "Registros cargados": registros_cargados,
        "Registros procesados": len(df),
        "Nombres normalizados": nombres_normalizados,
        "Matches por RUC": matches_ruc,
        "Matches por nombre": matches_nombre,
    }


def finalizar_calificaciones(uploaded_file, cfg: dict):
    st.cache_data.clear()

    _, _, bd, _ = contexto_google(
        cfg["spreadsheet_url"],
        cfg["hoja_bd"],
        cfg["hoja_aniadir"],
        cfg["hoja_etiquetas"],
        recarga_id=time_ns(),
    )

    df = leer_excel(uploaded_file)
    registros_cargados = len(df)
    diagnostico_ruc = diagnosticar_ruc_match(df, bd)

    df, matches_ruc, matches_nombre, analisis_errores = finalizar_dataset_calificaciones(
        df,
        bd,
    )

    metricas = {
        "Registros cargados": registros_cargados,
        "Registros procesados": len(df),
        "Matches por RUC": matches_ruc,
        "Matches por nombre": matches_nombre,
        "Errores match_entidad = NO": analisis_errores.total_casos,
    }
    return df, metricas, analisis_errores, diagnostico_ruc


def procesar_microlearning(
    actividades_file,
    dataset_file,
    examen_entrada_file,
    examen_final_file,
    evaluaciones_intermedias_files=None,
    fecha_emision: str = config.FECHA_EMISION_CERTIFICADO,
):
    evaluaciones_intermedias_files = evaluaciones_intermedias_files or []
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
        examen_entrada_file,
        examen_final_file,
        evaluaciones_intermedias_files,
    )

    examen_entrada = (
        leer_examen_upload(examen_entrada_file) if examen_entrada_file is not None else None
    )
    examen_final = (
        leer_examen_final_upload(examen_final_file) if examen_final_file is not None else None
    )
    evaluaciones_intermedias = [
        leer_evaluacion_intermedia_upload(archivo, numero)
        for numero, archivo in enumerate(evaluaciones_intermedias_files, start=1)
    ]
    return procesar_microlearning_dataset(
        leer_actividades_upload(actividades_file),
        leer_calificados_upload(dataset_file),
        examen_entrada,
        examen_final,
        evaluaciones_intermedias,
        fecha_emision,
    )


def procesar_mooc(
    actividades_file,
    dataset_file,
    examen_entrada_file,
    examen_final_file,
    evaluaciones_intermedias_files=None,
    fecha_emision: str = config.FECHA_EMISION_CERTIFICADO,
):
    evaluaciones_intermedias_files = evaluaciones_intermedias_files or []
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
        examen_entrada_file,
        examen_final_file,
        evaluaciones_intermedias_files,
    )

    examen_entrada = (
        leer_examen_upload(examen_entrada_file) if examen_entrada_file is not None else None
    )
    evaluaciones_intermedias = [
        leer_evaluacion_intermedia_upload(archivo, numero)
        for numero, archivo in enumerate(evaluaciones_intermedias_files, start=1)
    ]
    return procesar_mooc_dataset(
        leer_actividades_upload(actividades_file),
        leer_calificados_upload(dataset_file),
        examen_entrada,
        leer_examen_final_upload(examen_final_file),
        evaluaciones_intermedias,
        fecha_emision,
    )


def procesar_videoconferencia(
    actividades_file,
    dataset_file,
    fecha_emision: str = config.FECHA_EMISION_CERTIFICADO,
):
    imprimir_diagnostico_duplicados_dni(
        actividades_file,
        dataset_file,
    )

    return procesar_videoconferencia_dataset(
        leer_actividades_upload(actividades_file),
        leer_calificados_upload(dataset_file),
        fecha_emision,
    )


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


def mostrar_errores_match_no(analisis: AnalisisErroresMatchNo) -> None:
    if not analisis.hay_errores:
        return

    lineas = [
        f"Errores de consistencia en match_entidad = NO: {analisis.total_casos} caso(s).",
        "",
        *analisis.lineas_detalle(),
        "",
        "Se sugiere revisar cuidadosamente estos casos antes de usar el dataset final.",
    ]
    st.error("\n".join(lineas))


def mostrar_diagnostico_ruc_match(metricas: dict, diagnostico: dict[str, int]) -> None:
    if metricas.get("Matches por RUC", 0) != 0 or metricas.get("Matches por nombre", 0) == 0:
        return

    st.warning(
        "No hubo matches por RUC, pero si por nombre. "
        "Diagnostico previo: "
        f"{diagnostico['ruc_validos_dataset']} RUC validos en el archivo, "
        f"{diagnostico['ruc_validos_bd']} RUC validos en la BD y "
        f"{diagnostico['ruc_comunes']} RUC comunes entre ambos."
    )


def mensaje_error_usuario(error: Exception) -> str:
    mensaje = str(error)
    mensaje_lower = mensaje.lower()

    if any(
        texto in mensaje_lower
        for texto in (
            "403",
            "forbidden",
            "permission",
            "permiso",
            "permission_denied",
        )
    ):
        return (
            "No tienes permiso para acceder al Google Sheet configurado. "
            "Verifica que el archivo este compartido con tu cuenta institucional."
        )

    if any(texto in mensaje_lower for texto in ("401", "invalid_grant", "unauthorized")):
        return "Tu sesión de Google expiro o fue revocada. Cierra sesión e inicia nuevamente."

    return mensaje


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


def render_auth_status_sidebar() -> None:
    if streamlit_service_account_info() is not None:
        return

    if streamlit_auth_info() is None or not user_is_logged_in():
        return

    st.markdown("### Acceso")
    email = st.user.get("email", "Sesión de Google activa")
    st.caption(str(email))
    if st.button("Cerrar sesión", key="btn_logout_google", use_container_width=True):
        st.logout()
    st.markdown("---")


def render_sidebar() -> dict:
    with st.sidebar:
        render_auth_status_sidebar()

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
ensure_google_auth_ready()

sidebar_state = render_sidebar()
cfg = sidebar_state["cfg"]
registrar_pendientes = sidebar_state["registrar_pendientes"]

tab_limpiar, tab_finalizar, tab_procesar = st.tabs(
    ["Limpiar calificaciones", "Finalizar limpieza", "Procesar actividad"]
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
            st.error(mensaje_error_usuario(error))
            with st.expander("Detalle técnico"):
                st.exception(error)

    render_card_close()

with tab_finalizar:
    render_card_open(
        "Finalizar limpieza",
        "Carga el archivo depurado para consolidarlo con la información configurada en Google Sheets.",
    )

    archivo_limpiado = st.file_uploader(
        "Dataset depurado",
        type=["xlsx"],
        key="dataset_limpiado",
    )

    clic_finalizar = render_action_button_right(
        "Finalizar limpieza",
        key="btn_finalizar",
        disabled=archivo_limpiado is None,
    )

    if clic_finalizar:
        try:
            with st.spinner("Procesando..."):
                df_final, metricas, analisis_errores, diagnostico_ruc = finalizar_calificaciones(
                    archivo_limpiado,
                    cfg,
                )
            st.success("Dataset consolidado correctamente.")
            mostrar_errores_match_no(analisis_errores)
            mostrar_diagnostico_ruc_match(metricas, diagnostico_ruc)
            mostrar_metricas(metricas)
            descargar_excel(df_final, "dataset_final.xlsx", "Descargar dataset_final.xlsx")
        except Exception as error:
            st.error(mensaje_error_usuario(error))
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

    fecha_emision_seleccionada = st.date_input(
        "Fecha de emisión",
        value=fecha_emision_por_defecto(),
        format="DD/MM/YYYY",
        key=f"fecha_emision_{tipo_actividad}",
    )
    fecha_emision_certificado = fecha_emision_seleccionada.strftime("%d-%m-%Y")

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
    evaluaciones_intermedias = []

    if tipo_actividad in {"Microlearning", "MOOC"}:
        examen_entrada = st.file_uploader(
            "Examen de entrada (XLSX)",
            type=["xlsx"],
            key=f"entrada_{tipo_actividad}",
        )

        contador_intermedias_key = f"notas_intermedias_count_{tipo_actividad}"
        if contador_intermedias_key not in st.session_state:
            st.session_state[contador_intermedias_key] = 0

        col_intermedia, _ = st.columns([1, 3])
        with col_intermedia:
            if st.button(
                "+ Nota intermedia",
                key=f"add_intermedia_{tipo_actividad}",
                use_container_width=True,
            ):
                st.session_state[contador_intermedias_key] += 1

        for numero in range(1, st.session_state[contador_intermedias_key] + 1):
            archivo_intermedio = st.file_uploader(
                f"Notas intermedias {numero} (XLSX)",
                type=["xlsx"],
                key=f"intermedia_{tipo_actividad}_{numero}",
            )
            if archivo_intermedio is not None:
                evaluaciones_intermedias.append(archivo_intermedio)

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
                        df_resultado = procesar_videoconferencia(
                            actividades,
                            dataset_final,
                            fecha_emision_certificado,
                        )
                        nombre_archivo = "videoconferencia_procesado.xlsx"
                    elif tipo_actividad == "Microlearning":
                        df_resultado = procesar_microlearning(
                            actividades,
                            dataset_final,
                            examen_entrada,
                            examen_final,
                            evaluaciones_intermedias,
                            fecha_emision_certificado,
                        )
                        nombre_archivo = "microlearning_procesado.xlsx"
                    else:
                        df_resultado = procesar_mooc(
                            actividades,
                            dataset_final,
                            examen_entrada,
                            examen_final,
                            evaluaciones_intermedias,
                            fecha_emision_certificado,
                        )
                        nombre_archivo = "mooc_procesado.xlsx"

            st.success(f"{tipo_actividad} procesado correctamente.")
            mostrar_mensajes_procesamiento(mensajes_buffer.getvalue())
            mostrar_metricas({"Registros procesados": len(df_resultado)})
            descargar_excel(df_resultado, nombre_archivo, f"Descargar {nombre_archivo}")
        except Exception as error:
            mostrar_mensajes_procesamiento(mensajes_buffer.getvalue())
            st.error(mensaje_error_usuario(error))
            with st.expander("Detalle técnico"):
                st.exception(error)

    render_card_close()
