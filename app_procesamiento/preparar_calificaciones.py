from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from app_procesamiento import config
from app_procesamiento.core.dialogos import seleccionar_archivo
from app_procesamiento.core.entidades import (
    cargar_bd_entidades,
    cargar_etiquetas_entidad,
)
from app_procesamiento.core.errores_match_no import (
    imprimir_analisis_errores_match_no,
)
from app_procesamiento.core.finalizacion_calificaciones import finalizar_dataset_calificaciones
from app_procesamiento.core.google_sheets import build_sheets_service, extract_spreadsheet_id
from app_procesamiento.core.limpieza_calificaciones import limpiar_dataset_calificaciones


DTYPE_EXCEL = {"ruc": "string", "RUC": "string"}


def _ruta_input(args, titulo: str) -> Path:
    if args.input:
        return Path(args.input)
    return Path(seleccionar_archivo(titulo, [("Excel", "*.xlsx")]))


def _ruta_output(args, ruta_input: Path, nombre_default: str) -> Path:
    if args.output:
        return Path(args.output)
    return ruta_input.parent / nombre_default


def _cargar_bd(args):
    service = build_sheets_service(Path(args.credentials), Path(args.token))
    spreadsheet_id = extract_spreadsheet_id(args.bd_url)

    print(f"Descargando bd_entidades desde '{args.hoja_bd}'...")
    bd = cargar_bd_entidades(
        service,
        spreadsheet_id,
        hoja_consolidado=args.hoja_bd,
        hoja_aniadir=args.hoja_aniadir,
    )

    return service, spreadsheet_id, bd


def _leer_excel_dataset(ruta_input: Path) -> pd.DataFrame:
    return pd.read_excel(ruta_input, dtype=DTYPE_EXCEL)


def ejecutar_limpieza(args) -> Path:
    ruta_input = _ruta_input(args, "Seleccione el archivo Calificaciones original")
    ruta_output = _ruta_output(args, ruta_input, "dataset_limpiado.xlsx")

    service, spreadsheet_id, bd = _cargar_bd(args)

    print(f"Descargando etiquetas desde '{args.hoja_etiquetas}'...")
    etiquetas = cargar_etiquetas_entidad(service, spreadsheet_id, args.hoja_etiquetas)

    print(f"\nCargando dataset desde: {ruta_input}")
    df = _leer_excel_dataset(ruta_input)
    print(f"Registros cargados: {len(df)}")

    df, _nombres_normalizados, _matches_ruc, _matches_nombre = limpiar_dataset_calificaciones(
        df,
        bd,
        etiquetas,
        registrar_pendientes=not args.no_registrar_pendientes,
        service=service,
        spreadsheet_id=spreadsheet_id,
        log=print,
    )

    df.to_excel(ruta_output, index=False)

    print(f"\nRegistros procesados: {len(df)}")
    print(f"Archivo guardado en: {ruta_output}")
    return ruta_output


def ejecutar_finalizacion(args) -> Path:
    ruta_input = _ruta_input(args, "Seleccione dataset_limpiado.xlsx ya depurado")
    ruta_output = _ruta_output(args, ruta_input, "dataset_final.xlsx")

    _, _, bd = _cargar_bd(args)

    print(f"\nCargando dataset desde: {ruta_input}")
    df = _leer_excel_dataset(ruta_input)
    print(f"Registros cargados: {len(df)}")

    df, _matches_ruc, _matches_nombre, analisis_errores = finalizar_dataset_calificaciones(
        df,
        bd,
        log=print,
    )

    df.to_excel(ruta_output, index=False)

    print(f"\nRegistros procesados: {len(df)}")
    print(f"Archivo guardado en: {ruta_output}")
    imprimir_analisis_errores_match_no(analisis_errores)
    return ruta_output


def crear_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepara archivos de calificaciones para los procesadores finales.",
    )
    subparsers = parser.add_subparsers(dest="modo", required=True)

    def add_common_args(subparser):
        subparser.add_argument("--input", help="Ruta del Excel de entrada.")
        subparser.add_argument("--output", help="Ruta del Excel de salida.")
        subparser.add_argument("--bd-url", default=config.BD_ENTIDADES_URL)
        subparser.add_argument("--hoja-bd", default=config.BD_ENTIDADES_SHEET)
        subparser.add_argument("--hoja-aniadir", default=config.BD_ANIADIR_SHEET)
        subparser.add_argument("--credentials", default=str(config.CREDENTIALS_PATH))
        subparser.add_argument("--token", default=str(config.TOKEN_PATH))

    limpiar = subparsers.add_parser("limpiar", help="Genera dataset_limpiado.xlsx.")
    add_common_args(limpiar)
    limpiar.add_argument("--hoja-etiquetas", default=config.BD_ETIQUETAS_SHEET)
    limpiar.add_argument(
        "--no-registrar-pendientes",
        action="store_true",
        help="No escribe candidatos en las hojas auxiliares de Google Sheets.",
    )
    limpiar.set_defaults(func=ejecutar_limpieza)

    finalizar = subparsers.add_parser("finalizar", help="Genera dataset_final.xlsx.")
    add_common_args(finalizar)
    finalizar.set_defaults(func=ejecutar_finalizacion)

    return parser


def main() -> None:
    parser = crear_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
