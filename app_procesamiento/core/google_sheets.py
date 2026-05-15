from __future__ import annotations

import os
import re
import socket
import time
from pathlib import Path
from typing import Callable, TypeVar

import pandas as pd
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
MAX_REINTENTOS = 4
ESPERA_BASE_SEGUNDOS = 2
T = TypeVar("T")


def authenticate(
    credentials_path: Path,
    token_path: Path,
    scopes: list[str] | None = None,
):
    scopes = scopes or SCOPES
    creds = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and not creds.has_scopes(scopes):
        creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path),
                scopes,
            )
            creds = flow.run_local_server(port=0)

        token_path.parent.mkdir(parents=True, exist_ok=True)
        with open(token_path, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def build_sheets_service(credentials_path: Path, token_path: Path):
    creds = authenticate(credentials_path, token_path)
    return build("sheets", "v4", credentials=creds)


def extract_spreadsheet_id(url: str) -> str:
    match = re.search(r"/d/([a-zA-Z0-9_-]+)", url)
    if not match:
        raise ValueError(f"No se pudo extraer el spreadsheet id de: {url}")
    return match.group(1)


def is_retryable_error(error: Exception) -> bool:
    if isinstance(error, HttpError):
        return error.resp.status in {408, 429, 500, 502, 503, 504}
    return isinstance(error, (TimeoutError, socket.timeout, ConnectionError, OSError))


def execute_with_retry(
    operation_name: str,
    func: Callable[[], T],
    max_attempts: int = MAX_REINTENTOS,
) -> T:
    last_error = None

    for attempt in range(1, max_attempts + 1):
        try:
            return func()
        except Exception as error:
            last_error = error

            if not is_retryable_error(error) or attempt == max_attempts:
                raise RuntimeError(
                    f"{operation_name} fallo tras {attempt} intento(s): {error}"
                ) from error

            wait_seconds = ESPERA_BASE_SEGUNDOS * (2 ** (attempt - 1))
            print(
                f"Reintento {attempt}/{max_attempts - 1} para {operation_name} "
                f"en {wait_seconds}s por error transitorio: {error}"
            )
            time.sleep(wait_seconds)

    raise RuntimeError(f"{operation_name} fallo: {last_error}")


def get_spreadsheet_metadata(service, spreadsheet_id: str) -> dict:
    return execute_with_retry(
        f"obtener metadata del spreadsheet {spreadsheet_id}",
        lambda: service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute(),
    )


def ensure_sheet_exists(service, spreadsheet_id: str, sheet_name: str) -> None:
    meta = get_spreadsheet_metadata(service, spreadsheet_id)
    existing_names = {s["properties"]["title"] for s in meta["sheets"]}

    if sheet_name in existing_names:
        return

    execute_with_retry(
        f"crear hoja '{sheet_name}' en {spreadsheet_id}",
        lambda: service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute(),
    )


def download_sheet_as_raw_df(service, spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    result = execute_with_retry(
        f"descargar hoja '{sheet_name}' de {spreadsheet_id}",
        lambda: service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=f"'{sheet_name}'")
        .execute(),
    )

    values = result.get("values", [])
    if not values:
        return pd.DataFrame()

    max_cols = max(len(row) for row in values)
    padded = [row + [""] * (max_cols - len(row)) for row in values]
    return pd.DataFrame(padded)


def raw_sheet_to_table(raw: pd.DataFrame) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()

    headers = raw.iloc[0].astype(str).str.strip().tolist()
    df = raw.iloc[1:].copy()
    df.columns = headers
    return df.reset_index(drop=True)


def download_sheet_as_table(service, spreadsheet_id: str, sheet_name: str) -> pd.DataFrame:
    return raw_sheet_to_table(download_sheet_as_raw_df(service, spreadsheet_id, sheet_name))


def append_rows(service, spreadsheet_id: str, sheet_name: str, rows: list[list[str]]) -> None:
    if not rows:
        return

    execute_with_retry(
        f"agregar filas a '{sheet_name}'",
        lambda: service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute(),
    )


def write_rows(service, spreadsheet_id: str, sheet_name: str, rows: list[list[str]]) -> None:
    execute_with_retry(
        f"escribir filas en '{sheet_name}'",
        lambda: service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"'{sheet_name}'!A1",
            valueInputOption="RAW",
            body={"values": rows},
        ).execute(),
    )

