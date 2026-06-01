from pathlib import Path

from app_procesamiento.core.diagnosticos import imprimir_diagnostico_duplicados_dni
from app_procesamiento.core.dialogos import (
    seleccionar_archivo,
    seleccionar_archivo_opcional,
    seleccionar_carpeta,
)
from app_procesamiento.core.lectores import (
    leer_actividades,
    leer_calificados,
    leer_examen,
    leer_examen_final,
)
from app_procesamiento.core.procesamiento_actividades import procesar_microlearning_dataset


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
    ruta_examen_entrada = seleccionar_archivo_opcional(
        "Seleccione el examen de entrada (opcional)",
        [("Excel", "*.xlsx")],
    )
    ruta_examen_final = seleccionar_archivo_opcional(
        "Seleccione el examen final (opcional)",
        [("Excel", "*.xlsx")],
    )
    carpeta_salida = seleccionar_carpeta("Seleccione la carpeta donde guardar el resultado")
    ruta_salida = Path(carpeta_salida) / "microlearning_procesado.xlsx"

    print("\nRevisando duplicados antes del procesamiento...\n")
    imprimir_diagnostico_duplicados_dni(
        ruta_actividades,
        ruta_calificacion,
        ruta_examen_entrada,
        ruta_examen_final,
    )

    print("\nLeyendo archivos...\n")
    actividades = leer_actividades(ruta_actividades)
    calificados = leer_calificados(ruta_calificacion)
    examen_entrada = leer_examen(ruta_examen_entrada) if ruta_examen_entrada else None
    examen_final = leer_examen_final(ruta_examen_final) if ruta_examen_final else None

    print("Procesando datos...\n")
    df = procesar_microlearning_dataset(
        actividades,
        calificados,
        examen_entrada,
        examen_final,
    )

    print("Guardando archivo...\n")
    df.to_excel(ruta_salida, index=False)

    print("Archivo generado correctamente:")
    print(ruta_salida)
    print("Total registros:", len(df))
    return ruta_salida


if __name__ == "__main__":
    procesar()

