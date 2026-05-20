# Procesamiento OECE en Streamlit

App Streamlit para limpiar calificaciones, finalizar el dataset y procesar
videoconferencias, microlearning o MOOC.

## Estructura

```text
streamlit_procesamiento/
├─ app.py
├─ requirements.txt
├─ runtime.txt
├─ .streamlit/
│  ├─ config.toml
│  └─ secrets.example.toml
└─ app_procesamiento/
   └─ ...
```

La carpeta incluye una copia de `app_procesamiento`, por lo que puede subirse
como repositorio independiente a GitHub.

## Despliegue en Streamlit Community Cloud

1. Crea un repositorio en GitHub.
2. Sube el contenido de `streamlit_procesamiento/` como contenido del repo.
3. En Streamlit Community Cloud crea una app nueva.
4. Selecciona el repo y usa `app.py` como main file.
5. En `App settings > Secrets`, pega tus credenciales de service account.

## Credenciales Google Sheets

La app usa una service account de Google Cloud. No uses `credentials.json` ni
`token.json` en Streamlit Cloud.

1. Crea o usa una service account en Google Cloud.
2. Genera una clave JSON.
3. Copia los campos del JSON al formato de `.streamlit/secrets.example.toml`.
4. Comparte el Google Sheet de `bd_entidades` con el correo `client_email`.
5. Dale permiso de editor si quieres registrar pendientes en `añadir_bd` y
   `entidades_sin_ruc`.

Ejemplo de secrets:

```toml
[gcp_service_account]
type = "service_account"
project_id = "tu-proyecto"
private_key_id = "tu-private-key-id"
private_key = """-----BEGIN PRIVATE KEY-----
TU_PRIVATE_KEY
-----END PRIVATE KEY-----"""
client_email = "tu-service-account@tu-proyecto.iam.gserviceaccount.com"
client_id = "tu-client-id"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/tu-service-account%40tu-proyecto.iam.gserviceaccount.com"
universe_domain = "googleapis.com"
```

## Ejecucion local

### 1. Instalar dependencias

```powershell
uv sync
```

### 2. Iniciar la app

```powershell
uv run streamlit run app.py
```

Usar siempre `uv run` para que el comando se ejecute dentro del entorno virtual
`.venv/` creado por uv. Ejecutar `streamlit run app.py` directamente usa el
Python del sistema y produce `ModuleNotFoundError` aunque `uv sync` haya
terminado sin errores.

### 3. Credenciales para ejecucion local

La app usa el flujo OAuth de escritorio: coloca `credentials.json` en la raiz
del proyecto. Se obtiene descargando la clave del cliente OAuth desde
Google Cloud Console (proyecto `drive1-491915`, tipo "Aplicacion de escritorio").

La primera vez que se conecte a Google Sheets se abrira el navegador para
autorizar el acceso. Tras eso se crea `token.json` automaticamente y no vuelve
a pedirse autorizacion.

Ambos archivos estan en `.gitignore` y nunca se suben al repositorio. Al clonar
en un dispositivo nuevo hay que copiarlos manualmente.

## Flujo de uso

1. `Limpiar calificaciones`: sube el archivo original de calificaciones y
   descarga `dataset_limpiado.xlsx`.
2. Depura manualmente `dataset_limpiado.xlsx`.
3. `Finalizar dataset`: sube el archivo depurado y descarga `dataset_final.xlsx`.
4. `Procesar actividad`: sube `dataset_final.xlsx` y los archivos de la actividad.

## Notas

- `Registrar pendientes` esta apagado por defecto para evitar escrituras
  accidentales en Google Sheets.
- MOOC requiere examen final. Microlearning permite examenes opcionales.
- Videoconferencia solo requiere actividades y `dataset_final.xlsx`.

