from pathlib import Path

from app_procesamiento.core.diagnosticos import imprimir_diagnostico_duplicados_dni
from app_procesamiento.core.dialogos import seleccionar_archivo, seleccionar_carpeta
from app_procesamiento.core.lectores import leer_actividades, leer_calificados
from app_procesamiento.core.procesamiento_actividades import procesar_videoconferencia_dataset


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
    df = procesar_videoconferencia_dataset(actividades, calificados)

    print("Guardando archivo...\n")
    df.to_excel(ruta_salida, index=False)

    print("Archivo generado correctamente:")
    print(ruta_salida)
    print("Total registros:", len(df))
    return ruta_salida


if __name__ == "__main__":
    procesar()

