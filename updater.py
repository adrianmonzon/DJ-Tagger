import json
import os
import re
import shutil
import ssl
import subprocess
import tempfile
import urllib.request

import certifi

from version import APP_VERSION


GITHUB_API_URL = "https://api.github.com/repos/adrianmonzon/DJ-Tagger/releases/latest"

# Nombre del bundle .app tal y como lo genera el build (PyInstaller/py2app).
APP_BUNDLE_NAME = "DJ Tagger.app"

# Archivo donde el script de instalación deja constancia de a qué versión
# se actualizó con éxito. La GUI lo lee al arrancar para mostrar el aviso
# de "Actualización completada" una sola vez, y luego lo borra.
UPDATE_FLAG_PATH = os.path.join(
    os.path.expanduser("~"),
    "Library",
    "Application Support",
    "DJ Tagger",
    "last_update.json",
)

# El nombre del asset del ZIP en el Release de GitHub puede variar un poco
# entre publicaciones (espacios, guiones, mayúsculas...). Para no depender
# de un match exacto, exigimos solo que contenga "dj" y "tagger" y termine
# en .zip.
_ASSET_NAME_RE = re.compile(r"dj[\s_-]*tagger.*\.zip$", re.IGNORECASE)


def read_and_clear_update_flag():
    """Si la última actualización se completó con éxito, devuelve la
    versión instalada y borra la marca (para no volver a avisar). Si no
    hay marca pendiente, devuelve None.
    """
    try:
        with open(UPDATE_FLAG_PATH, "r", encoding="utf-8") as file:
            data = json.load(file)
        version = data.get("version")
    except (OSError, ValueError, json.JSONDecodeError):
        return None

    try:
        os.remove(UPDATE_FLAG_PATH)
    except OSError:
        pass

    return version


def version_tuple(version):
    """Convierte un string de versión (p.ej. 'v1.0.21' o '1.0.21-beta') en
    una tupla de enteros comparable. Cualquier sufijo no numérico en un
    segmento se ignora en vez de hacer que todo el parseo falle.
    """
    version = (version or "").strip()

    if version.lower().startswith("v"):
        version = version[1:]

    parts = re.split(r"[.\-+]", version)
    result = []

    for part in parts:
        match = re.match(r"\d+", part)
        if match:
            result.append(int(match.group()))

    return tuple(result) if result else (0,)


def _find_update_asset(assets):
    for asset in assets or []:
        name = asset.get("name", "")
        if _ASSET_NAME_RE.search(name):
            return asset.get("browser_download_url")
    return None


def _create_ssl_context():
    return ssl.create_default_context(cafile=certifi.where())


def _get_latest_release():
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DJ-Tagger",
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=10,
        context=_create_ssl_context(),
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def check_for_update():
    try:
        data = _get_latest_release()
        latest_version = data["tag_name"].lstrip("vV")

        if version_tuple(latest_version) > version_tuple(APP_VERSION):
            download_url = _find_update_asset(data.get("assets"))

            return {
                "available": True,
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "download_url": download_url,
                "release_url": data.get("html_url"),
            }

        return {
            "available": False,
            "current_version": APP_VERSION,
            "latest_version": latest_version,
            "download_url": None,
            "release_url": data.get("html_url"),
        }

    except Exception as error:
        return {
            "available": False,
            "current_version": APP_VERSION,
            "latest_version": None,
            "download_url": None,
            "release_url": None,
            "error": str(error),
        }


def download_update(download_url):
    if not download_url:
        raise RuntimeError("No se encontró el ZIP de la nueva versión.")

    temp_dir = tempfile.mkdtemp(prefix="dj_tagger_update_")
    zip_path = os.path.join(temp_dir, "DJ Tagger-macOS.zip")

    request = urllib.request.Request(
        download_url,
        headers={"User-Agent": "DJ-Tagger"},
    )

    with urllib.request.urlopen(
        request,
        timeout=60,
        context=_create_ssl_context(),
    ) as response, open(zip_path, "wb") as output_file:
        shutil.copyfileobj(response, output_file)

    if not os.path.isfile(zip_path):
        raise RuntimeError("La descarga terminó pero no se encontró el ZIP.")

    if os.path.getsize(zip_path) == 0:
        raise RuntimeError("El ZIP descargado está vacío.")

    return zip_path


def _resolve_current_app_path():
    current_file = os.path.abspath(__file__)

    if ".app/Contents/" in current_file:
        return current_file.split(".app/Contents/")[0] + ".app"

    return os.path.join("/Applications", APP_BUNDLE_NAME)


def install_update(zip_path, new_version=None):
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(
            f"No se encontró el archivo descargado: {zip_path}"
        )

    extract_dir = tempfile.mkdtemp(prefix="dj_tagger_extract_")

    result = subprocess.run(
        [
            "/usr/bin/ditto",
            "-x",
            "-k",
            zip_path,
            extract_dir,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "No se pudo extraer la actualización: "
            + (result.stderr.strip() or "error desconocido")
        )

    # El ZIP puede traer el .app directamente en la raíz, o dentro de una
    # única carpeta contenedora. Buscamos en ambos sitios.
    candidate_paths = [os.path.join(extract_dir, APP_BUNDLE_NAME)]

    for entry in os.listdir(extract_dir):
        nested = os.path.join(extract_dir, entry, APP_BUNDLE_NAME)
        if os.path.isdir(nested):
            candidate_paths.append(nested)

    new_app_path = next(
        (path for path in candidate_paths if os.path.isdir(path)),
        None,
    )

    if new_app_path is None:
        raise RuntimeError(
            f"El ZIP descargado no contiene '{APP_BUNDLE_NAME}'."
        )

    current_app_path = _resolve_current_app_path()
    backup_app_path = current_app_path + ".update-backup"

    updater_script = os.path.join(
        tempfile.gettempdir(),
        "dj_tagger_apply_update.sh",
    )

    log_file = os.path.join(
        tempfile.gettempdir(),
        "dj_tagger_update.log",
    )

    def shell_quote(value):
        return "'" + value.replace("'", "'\\''") + "'"

    old_app = shell_quote(current_app_path)
    backup_app = shell_quote(backup_app_path)
    new_app = shell_quote(new_app_path)
    updater = shell_quote(updater_script)
    log = shell_quote(log_file)
    executable_name = os.path.splitext(APP_BUNDLE_NAME)[0]

    flag_dir = shell_quote(os.path.dirname(UPDATE_FLAG_PATH))
    flag_path = shell_quote(UPDATE_FLAG_PATH)
    flag_version = (new_version or "").replace('"', '\\"')

    # Instalación atómica: la app vieja se renombra a un backup (no se
    # borra), se copia la nueva y solo si todo va bien se elimina el
    # backup. Si algo falla a mitad, se restaura el backup, así el usuario
    # nunca se queda sin una app funcional instalada.
    script = f"""#!/bin/sh

LOG_FILE={log}

exec >>"$LOG_FILE" 2>&1

echo "========================================"
echo "DJ Tagger update started"
echo "$(date)"
echo "OLD_APP={old_app}"
echo "NEW_APP={new_app}"
echo "========================================"

echo "Esperando a que DJ Tagger cierre..."
sleep 3

for i in 1 2 3 4 5 6 7 8 9 10; do
    if /usr/bin/pgrep -f "{os.path.basename(current_app_path)}/Contents/MacOS/" >/dev/null 2>&1; then
        echo "DJ Tagger sigue ejecutándose. Esperando..."
        sleep 1
    else
        echo "DJ Tagger ya está cerrado."
        break
    fi
done

echo "Comprobando nueva aplicación..."

if [ ! -d {new_app} ]; then
    echo "ERROR: No existe la nueva aplicación."
    exit 1
fi

# Nos aseguramos de no arrastrar un backup de un intento anterior fallido.
if [ -d {backup_app} ]; then
    /bin/rm -rf {backup_app}
fi

BACKUP_MADE=0

if [ -d {old_app} ]; then
    echo "Guardando copia de seguridad de la app actual..."
    /bin/mv {old_app} {backup_app}
    if [ $? -ne 0 ]; then
        echo "ERROR: No se pudo hacer copia de seguridad de la app actual."
        exit 1
    fi
    BACKUP_MADE=1
fi

echo "Copiando nueva aplicación..."

/usr/bin/ditto {new_app} {old_app}
DITTO_RESULT=$?

if [ $DITTO_RESULT -ne 0 ] || [ ! -d {old_app} ] || [ ! -x "{current_app_path}/Contents/MacOS/{executable_name}" ]; then
    echo "ERROR: la copia de la nueva app falló o quedó incompleta."

    if [ $BACKUP_MADE -eq 1 ]; then
        echo "Restaurando la versión anterior..."
        /bin/rm -rf {old_app}
        /bin/mv {backup_app} {old_app}
    fi

    exit 1
fi

echo "Nueva aplicación instalada correctamente."

if [ $BACKUP_MADE -eq 1 ]; then
    /bin/rm -rf {backup_app}
fi

echo "Dejando constancia de la actualización completada..."

/bin/mkdir -p {flag_dir}
/bin/cat > {flag_path} << FLAGEOF
{{"version": "{flag_version}"}}
FLAGEOF

echo "Abriendo nueva aplicación..."

/usr/bin/open -a {old_app}

OPEN_RESULT=$?

echo "Resultado de open: $OPEN_RESULT"

if [ $OPEN_RESULT -ne 0 ]; then
    echo "ERROR: No se pudo abrir la nueva aplicación (pero la instalación se completó)."
    exit 1
fi

echo "Actualización completada correctamente."

sleep 5

/bin/rm -rf "$(dirname {new_app})"
/bin/rm -f {updater}

echo "Archivos temporales eliminados."

exit 0
"""

    with open(
        updater_script,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(script)

    os.chmod(
        updater_script,
        0o755,
    )

    subprocess.Popen(
        [
            "/bin/sh",
            updater_script,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return True
