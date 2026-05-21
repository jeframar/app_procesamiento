from pathlib import Path

from app_procesamiento.core.certificados import calcular_condicion_y_constancia
from app_procesamiento.core.columnas import (
    eliminar_columnas_actividad,
    mover_columna_despues_de_otra,
)
from app_procesamiento.core.diagnosticos import imprimir_diagnostico_duplicados_dni
from app_procesamiento.core.dialogos import seleccionar_archivo, seleccionar_carpeta
from app_procesamiento.core.lectores import leer_actividades, leer_calificados
from app_procesamiento.core.transformaciones import (
    eliminar_columnas_basura,
    eliminar_columnas_exportacion,
    limpiar_campos_generales,
    unir_fuentes,
)


def procesar() -> Path:
    print("\nSeleccione los archivos necesarios\n")

    ruta_actividades = seleccionar_archivo(
        "Seleccione el archivo de actividades",
        [("CSV", "*.csv")],
    )
    ruta_calificacion = seleccionar_archivo(
        "Seleccione dataset_final.xlsx",
        [("Excel", "*.xlsx")],
    )
    carpeta_salida = seleccionar_carpeta("Seleccione la carpeta donde guardar el resultado")
    ruta_salida = Path(carpeta_salida) / "videoconferencia_procesado.xlsx"

    print("\nRevisando duplicados antes del procesamiento...\n")
    imprimir_diagnostico_duplicados_dni(
        ruta_actividades,
        ruta_calificacion,
    )

    print("\nLeyendo archivos...\n")
    actividades = leer_actividades(ruta_actividades)
    calificados = leer_calificados(ruta_calificacion)

    print("Procesando datos...\n")
    df = unir_fuentes(calificados, actividades)
    df = eliminar_columnas_actividad(df, "videoconferencia")
    df = eliminar_columnas_basura(df)
    df = limpiar_campos_generales(df)
    df = calcular_condicion_y_constancia(df)
    df = mover_columna_despues_de_otra(df, "clasificacion_empresa", "perfil")

    if {"condicion", "certificado"}.issubset(df.columns):
        df = df.sort_values(by=["condicion", "certificado"], ascending=[True, True])

    df = eliminar_columnas_exportacion(df)

    print("Guardando archivo...\n")
    df.to_excel(ruta_salida, index=False)

    print("Archivo generado correctamente:")
    print(ruta_salida)
    print("Total registros:", len(df))
    return ruta_salida


if __name__ == "__main__":
    procesar()

