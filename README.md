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
5. En `App settings > Secrets`, configura OAuth Web o una service account.

## Credenciales Google Sheets

No subas `credentials.json`, `token.json`, `.streamlit/secrets.toml` ni claves
JSON al repositorio, aunque sea privado.

### Opcion recomendada: OAuth Web por usuario

Usa esta opcion cuando cada usuario debe acceder con su cuenta institucional.
La app pedira iniciar sesion con Google al entrar y guardara las credenciales
solo en la sesion de Streamlit.

1. En Google Cloud Console crea un OAuth Client ID de tipo `Web application`.
2. Agrega como `Authorized redirect URI` la URL de la app, por ejemplo
   `https://tu-app.streamlit.app/`.
3. Para pruebas locales, agrega tambien `http://localhost:8501/`.
4. En Streamlit Cloud, pega este bloque en `App settings > Secrets`:

```toml
[google_oauth_web]
client_id = "tu-client-id.apps.googleusercontent.com"
client_secret = "tu-client-secret"
redirect_uri = "https://tu-app.streamlit.app/"
```

Cada usuario debe tener acceso directo al Google Sheet con su cuenta
institucional.

### Opcion alternativa: service account

Usa esta opcion solo si tu organizacion permite compartir el Google Sheet con el
correo `client_email` de una service account.

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

Para mantener el flujo local existente, coloca `credentials.json` en la raiz
del proyecto. Se obtiene descargando la clave del cliente OAuth desde
Google Cloud Console (tipo "Aplicacion de escritorio").

La primera vez que se conecte a Google Sheets se abrira el navegador para
autorizar el acceso. Tras eso se crea `token.json` automaticamente y no vuelve
a pedirse autorizacion.

Para probar el mismo flujo que Streamlit Cloud, copia
`.streamlit/secrets.example.toml` como `.streamlit/secrets.toml`, configura
`[google_oauth_web]` y usa `redirect_uri = "http://localhost:8501/"`.

`credentials.json`, `token.json` y `.streamlit/secrets.toml` estan en
`.gitignore` y nunca se suben al repositorio. Al clonar en un dispositivo nuevo
hay que configurarlos manualmente.

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

