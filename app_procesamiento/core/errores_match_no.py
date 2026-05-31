from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any
import unicodedata

import pandas as pd


VALID_SITUACION = {
    "NO LABORA ACTUALMENTE",
    "TRABAJADOR DEPENDIENTE",
    "TRABAJADOR INDEPENDIENTE",
}
VALID_TIPO_DEPENDIENTE = {"ENTIDAD PUBLICA", "ENTIDAD PRIVADA"}

ERROR_SITUACION_INVALIDA = "categoria_no_valida"
ERROR_INDEPENDIENTE = "inconsistencia_independiente"
ERROR_DEPENDIENTE = "inconsistencia_dependiente"
ERROR_NIVEL_GOBIERNO = "ausencia_nivel_gobierno"
ERROR_ORDER = (
    ERROR_SITUACION_INVALIDA,
    ERROR_INDEPENDIENTE,
    ERROR_DEPENDIENTE,
    ERROR_NIVEL_GOBIERNO,
)


def canonical_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""

    text = str(value).strip()
    text = " ".join(text.split())
    text = unicodedata.normalize("NFD", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.upper()


def is_empty_value(value: Any) -> bool:
    return canonical_text(value) in {"", "NAN", "NONE"}


def error_code_for_row(row: Mapping[str, Any]) -> str | None:
    situacion = canonical_text(row.get("situacion_laboral"))
    tipo = canonical_text(row.get("tipo_entidad"))

    if situacion not in VALID_SITUACION:
        return ERROR_SITUACION_INVALIDA
    if situacion == "TRABAJADOR INDEPENDIENTE" and tipo != "INDEPENDIENTE Y OTROS":
        return ERROR_INDEPENDIENTE
    if situacion == "TRABAJADOR DEPENDIENTE" and tipo not in VALID_TIPO_DEPENDIENTE:
        return ERROR_DEPENDIENTE
    if (
        situacion == "TRABAJADOR DEPENDIENTE"
        and tipo == "ENTIDAD PUBLICA"
        and is_empty_value(row.get("nivel_gobierno"))
    ):
        return ERROR_NIVEL_GOBIERNO
    return None


def format_rows(rows: Sequence[int]) -> str:
    return ", ".join(str(row) for row in sorted(rows))


def format_rows_with_y(rows: Sequence[int]) -> str:
    sorted_rows = [str(row) for row in sorted(rows)]
    if len(sorted_rows) <= 1:
        return "".join(sorted_rows)
    if len(sorted_rows) == 2:
        return " y ".join(sorted_rows)
    return f"{', '.join(sorted_rows[:-1])} y {sorted_rows[-1]}"


@dataclass(frozen=True)
class AnalisisErroresMatchNo:
    total_filas: int
    total_match_no: int
    filas_por_error: dict[str, tuple[int, ...]]

    @property
    def total_casos(self) -> int:
        return len({row for rows in self.filas_por_error.values() for row in rows})

    @property
    def hay_errores(self) -> bool:
        return self.total_casos > 0

    def filas(self, codigo_error: str) -> tuple[int, ...]:
        return self.filas_por_error.get(codigo_error, ())

    def lineas_detalle(self) -> list[str]:
        if not self.hay_errores:
            return ["No se encontraron errores de consistencia."]

        lineas = []
        item_number = 1

        rows_situacion = self.filas(ERROR_SITUACION_INVALIDA)
        if rows_situacion:
            label = "fila" if len(rows_situacion) == 1 else "filas"
            lineas.append(
                f"{item_number}. Categoria no valida en columna situacion_laboral "
                f"({label} {format_rows(rows_situacion)})."
            )
            item_number += 1

        rows_independiente = self.filas(ERROR_INDEPENDIENTE)
        if rows_independiente:
            lineas.append(
                f"{item_number}. Inconsistencia en filas "
                f"{format_rows(rows_independiente)}. "
                "Trabajador independiente solo tiene como tipo_entidad "
                "Independiente y otros."
            )
            item_number += 1

        rows_dependiente = self.filas(ERROR_DEPENDIENTE)
        if rows_dependiente:
            lineas.append(
                f"{item_number}. Inconsistencia en filas "
                f"{format_rows(rows_dependiente)}: "
                "Trabajador dependiente solo tiene como tipo_entidad: "
                "Entidad publica o Entidad privada."
            )
            item_number += 1

        rows_nivel_gobierno = self.filas(ERROR_NIVEL_GOBIERNO)
        if rows_nivel_gobierno:
            label = "fila" if len(rows_nivel_gobierno) == 1 else "filas"
            lineas.append(
                f"{item_number}. Ausencia de valor en nivel_gobierno, "
                "por error en procesamiento de "
                f"{label} {format_rows_with_y(rows_nivel_gobierno)}."
            )

        return lineas

    def lineas_reporte(self) -> list[str]:
        lineas = [
            f"Total de filas: {self.total_filas}",
            f"Total match_entidad = NO: {self.total_match_no}",
            f"Total de casos con error: {self.total_casos}",
            "",
            *self.lineas_detalle(),
        ]
        if self.hay_errores:
            lineas.extend(
                ["", f"Se sugiere revisar cuidadosamente estos {self.total_casos} casos."]
            )
        return lineas


def analizar_errores_match_no(df: pd.DataFrame) -> AnalisisErroresMatchNo:
    rows_by_error = {codigo: [] for codigo in ERROR_ORDER}
    total_match_no = 0

    for excel_row, row in enumerate(df.to_dict(orient="records"), start=2):
        if canonical_text(row.get("match_entidad")) != "NO":
            continue

        total_match_no += 1
        error_code = error_code_for_row(row)
        if error_code:
            rows_by_error[error_code].append(excel_row)

    return AnalisisErroresMatchNo(
        total_filas=len(df),
        total_match_no=total_match_no,
        filas_por_error={codigo: tuple(rows) for codigo, rows in rows_by_error.items()},
    )


def imprimir_analisis_errores_match_no(analisis: AnalisisErroresMatchNo) -> None:
    print()
    print("Analisis de errores match_entidad = NO:")
    for linea in analisis.lineas_reporte():
        print(linea)
