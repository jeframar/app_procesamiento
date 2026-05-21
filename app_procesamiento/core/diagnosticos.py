from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from app_procesamiento.core.utils import normalizar_dni, normalizar_dni_para_merge


@dataclass(frozen=True)
class DuplicadosDNI:
    total_registros: int
    dni_duplicados: int
    filas_duplicadas: int


def _contar_duplicados(serie: pd.Series) -> DuplicadosDNI:
    dni = normalizar_dni_para_merge(serie)
    dni = dni[dni != ""]
    repetidos = dni[dni.duplicated(keep=False)]

    return DuplicadosDNI(
        total_registros=len(serie),
        dni_duplicados=int(repetidos.nunique()),
        filas_duplicadas=int(dni.duplicated(keep="first").sum()),
    )


def _reiniciar_fuente(fuente) -> None:
    if hasattr(fuente, "seek"):
        fuente.seek(0)


def _preparar_dni_para_validacion(serie: pd.Series) -> pd.Series:
    return (
        serie.fillna("")
        .astype(str)
        .str.replace(r"\.0$", "", regex=True)
        .str.replace(r"\s+", "", regex=True)
        .str.zfill(8)
    )


def _valor_visible(valor) -> str:
    if pd.isna(valor):
        return "<NA>"

    texto = str(valor)
    if texto == "":
        return "<vacio>"
    if texto.strip() == "":
        return "<espacios>"

    return texto


def _imprimir_resumen_valores_dni(
    titulo: str,
    serie: pd.Series,
    dni_prevalidado: pd.Series,
    mask: pd.Series,
) -> None:
    total = int(mask.sum())
    if total == 0:
        print(f"- {titulo}: ninguno")
        return

    resumen = (
        pd.DataFrame(
            {
                "valor_original": serie[mask].map(_valor_visible),
                "valor_prevalidado": dni_prevalidado[mask],
            }
        )
        .value_counts(["valor_original", "valor_prevalidado"])
        .reset_index(name="veces")
    )

    print(f"- {titulo}: {total} fila(s)")
    for fila in resumen.itertuples(index=False):
        print(
            "  "
            f"valor_original={fila.valor_original!r}; "
            f"valor_prevalidado={fila.valor_prevalidado!r}; "
            f"veces={fila.veces}"
        )


def _imprimir_grupos_duplicados(
    nombre: str,
    serie: pd.Series,
    max_grupos: int = 20,
    max_valores_por_grupo: int = 8,
) -> None:
    dni_normalizado = normalizar_dni_para_merge(serie)
    df = pd.DataFrame(
        {
            "dni_normalizado": dni_normalizado,
            "valor_original": serie.map(_valor_visible),
        }
    )
    df = df[df["dni_normalizado"] != ""]

    conteos = df.groupby("dni_normalizado", dropna=False).size()
    duplicados = conteos[conteos > 1].sort_values(ascending=False)

    if duplicados.empty:
        print(f"- {nombre}: sin grupos duplicados")
        return

    print(f"- {nombre}: {len(duplicados)} grupo(s) duplicado(s)")
    for dni, ocurrencias in duplicados.head(max_grupos).items():
        valores = (
            df.loc[df["dni_normalizado"] == dni, "valor_original"]
            .value_counts()
            .head(max_valores_por_grupo)
        )
        valores_texto = ", ".join(
            f"{valor!r} ({veces})" for valor, veces in valores.items()
        )
        print(
            "  "
            f"dni_normalizado={dni!r}; "
            f"ocurrencias={int(ocurrencias)}; "
            f"valores_originales={valores_texto}"
        )

    grupos_omitidos = len(duplicados) - max_grupos
    if grupos_omitidos > 0:
        print(f"  ... {grupos_omitidos} grupo(s) duplicado(s) adicional(es) omitido(s)")


def _imprimir_diagnostico_dni_calificaciones(serie: pd.Series) -> None:
    dni_prevalidado = _preparar_dni_para_validacion(serie)
    dni_normalizado = normalizar_dni(serie)
    mask_patron_invalido = ~dni_prevalidado.str.fullmatch(r"\d{8}")
    mask_a_cero = dni_normalizado == "00000000"
    mask_a_cero_sin_patron_invalido = mask_a_cero & ~mask_patron_invalido

    print("Valores DNI sospechosos en calificaciones")
    print(
        "(valor_prevalidado es el DNI despues de limpiar espacios/.0 y aplicar zfill; "
        "estos valores no se usan como llave de merge por DNI)"
    )
    _imprimir_resumen_valores_dni(
        "fallan patron \\d{8} y se convierten en 00000000",
        serie,
        dni_prevalidado,
        mask_patron_invalido,
    )
    _imprimir_resumen_valores_dni(
        "normalizan a 00000000 sin fallar patron",
        serie,
        dni_prevalidado,
        mask_a_cero_sin_patron_invalido,
    )


def _leer_dni_actividades(ruta_csv: str | Path) -> pd.Series:
    _reiniciar_fuente(ruta_csv)
    cols = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        nrows=0,
    ).columns
    col_dni = "DNI" if "DNI" in cols else cols[1]

    _reiniciar_fuente(ruta_csv)
    df = pd.read_csv(
        ruta_csv,
        encoding="utf-16",
        sep="\t",
        dtype={col_dni: "object"},
        usecols=[col_dni],
    )
    _reiniciar_fuente(ruta_csv)
    return df[col_dni]


def _leer_dni_calificados(ruta_excel: str | Path) -> pd.Series:
    _reiniciar_fuente(ruta_excel)
    df = pd.read_excel(ruta_excel, dtype={"dni": "object", "DNI": "object"})
    _reiniciar_fuente(ruta_excel)

    if "dni" in df.columns:
        return df["dni"]
    if "DNI" in df.columns:
        return df["DNI"]

    raise KeyError("El archivo de calificaciones no tiene columna 'dni' ni 'DNI'.")


def _leer_dni_examen(ruta_excel: str | Path) -> pd.Series:
    _reiniciar_fuente(ruta_excel)
    df = pd.read_excel(
        ruta_excel,
        dtype={"DNI": "object"},
        skipfooter=1,
        usecols=[2],
    )
    _reiniciar_fuente(ruta_excel)

    if "DNI" in df.columns:
        return df["DNI"]

    return df.iloc[:, 0]


def _formatear_linea(nombre: str, conteo: DuplicadosDNI | None) -> str:
    if conteo is None:
        return f"- {nombre}: no seleccionado"

    return (
        f"- {nombre}: {conteo.total_registros} registro(s); "
        f"{conteo.dni_duplicados} DNI duplicado(s); "
        f"{conteo.filas_duplicadas} fila(s) extra duplicada(s)"
    )


def imprimir_diagnostico_duplicados_dni(
    ruta_actividades: str | Path,
    ruta_calificacion: str | Path,
    ruta_examen_entrada: str | Path | None = None,
    ruta_examen_final: str | Path | None = None,
) -> None:
    print("Diagnostico previo de duplicados en DNI")
    print("(antes de depurar/eliminar duplicados; agrupado por DNI valido para merge)")

    dni_calificados = _leer_dni_calificados(ruta_calificacion)
    dni_actividades = _leer_dni_actividades(ruta_actividades)
    dni_examen_entrada = _leer_dni_examen(ruta_examen_entrada) if ruta_examen_entrada else None
    dni_examen_final = _leer_dni_examen(ruta_examen_final) if ruta_examen_final else None

    diagnosticos = [
        ("calificaciones", _contar_duplicados(dni_calificados)),
        ("actividades", _contar_duplicados(dni_actividades)),
        (
            "examen entrada",
            _contar_duplicados(dni_examen_entrada) if dni_examen_entrada is not None else None,
        ),
        (
            "examen final",
            _contar_duplicados(dni_examen_final) if dni_examen_final is not None else None,
        ),
    ]

    for nombre, conteo in diagnosticos:
        print(_formatear_linea(nombre, conteo))

    print("Detalle de grupos duplicados por DNI normalizado")
    _imprimir_grupos_duplicados("calificaciones", dni_calificados)
    _imprimir_grupos_duplicados("actividades", dni_actividades)
    if dni_examen_entrada is not None:
        _imprimir_grupos_duplicados("examen entrada", dni_examen_entrada)
    if dni_examen_final is not None:
        _imprimir_grupos_duplicados("examen final", dni_examen_final)

    _imprimir_diagnostico_dni_calificaciones(dni_calificados)
