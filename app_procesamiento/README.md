# app_procesamiento

Version depurada del flujo de procesamiento de bases.

## Flujo recomendado

1. Limpiar el archivo original de Calificaciones:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.preparar_calificaciones limpiar
```

Esto genera `dataset_limpiado.xlsx` en la misma carpeta del archivo de entrada.
Tambien registra candidatos pendientes en las hojas auxiliares de Google Sheets.

2. Depurar manualmente `dataset_limpiado.xlsx`.

3. Finalizar el dataset depurado:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.preparar_calificaciones finalizar
```

Esto genera `dataset_final.xlsx`.

4. Procesar la actividad final:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.procesar_videoconferencia
.\.venv\Scripts\python.exe -m app_procesamiento.procesar_microlearning
.\.venv\Scripts\python.exe -m app_procesamiento.procesar_mooc
```

Los tres procesadores piden `dataset_final.xlsx` como archivo de calificaciones.
Ya no piden base de entidades porque el enriquecimiento ocurre antes.

## Atajos

Tambien existen estos wrappers interactivos:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.limpiar_calificaciones
.\.venv\Scripts\python.exe -m app_procesamiento.finalizar_calificaciones
```

## Archivos que pide cada procesador

| Script | Archivos de entrada |
|---|---|
| `procesar_videoconferencia.py` | Actividades + `dataset_final.xlsx` |
| `procesar_microlearning.py` | Actividades + `dataset_final.xlsx` + examenes opcionales |
| `procesar_mooc.py` | Actividades + `dataset_final.xlsx` + examen final + examen de entrada opcional |

## Configuracion

La URL y nombres de hojas estan en `config.py`. Por defecto se usan
`credentials.json` y `token.json` desde la raiz del proyecto.

Puedes pasar rutas por CLI para evitar ventanas:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.preparar_calificaciones limpiar --input C:\ruta\calificaciones.xlsx --output C:\ruta\dataset_limpiado.xlsx
.\.venv\Scripts\python.exe -m app_procesamiento.preparar_calificaciones finalizar --input C:\ruta\dataset_limpiado.xlsx --output C:\ruta\dataset_final.xlsx
```

Para no escribir candidatos en Google Sheets durante la limpieza:

```powershell
.\.venv\Scripts\python.exe -m app_procesamiento.preparar_calificaciones limpiar --no-registrar-pendientes
```
