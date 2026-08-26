import json
import os
import shutil
import ssl
import subprocess
import tempfile
import urllib.request
import zipfile

import certifi

from version import APP_VERSION


GITHUB_API_URL = (
    "https://api.github.com/repos/adrianmonzon/DJ-Tagger/releases/latest"
)


def version_tuple(version):
    return tuple(
        int(part)
        for part in version.lstrip("v").split(".")
    )


def _create_ssl_context():
    return ssl.create_default_context(
        cafile=certifi.where()
    )


def _get_latest_release():
    request = urllib.request.Request(
        GITHUB_API_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DJ-Tagger",
        },
    )

    context = _create_ssl_context()

    with urllib.request.urlopen(
        request,
        timeout=10,
        context=context,
    ) as response:
        return json.loads(
            response.read().decode("utf-8")
        )


def check_for_update():
    try:
        data = _get_latest_release()

        latest_version = data["tag_name"].lstrip("v")

        if version_tuple(latest_version) > version_tuple(APP_VERSION):
            download_url = None

            for asset in data.get("assets", []):
                name = asset.get("name", "")

                if name.lower() == "dj.tagger-macos.zip":
                    download_url = asset.get(
                        "browser_download_url"
                    )
                    break

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
        raise RuntimeError(
            "No se encontró el ZIP de la nueva versión."
        )

    temp_dir = tempfile.mkdtemp(
        prefix="dj_tagger_update_"
    )

    zip_path = os.path.join(
        temp_dir,
        "DJ Tagger-macOS.zip",
    )

    request = urllib.request.Request(
        download_url,
        headers={
            "User-Agent": "DJ-Tagger",
        },
    )

    context = _create_ssl_context()

    with urllib.request.urlopen(
        request,
        timeout=60,
        context=context,
    ) as response, open(
        zip_path,
        "wb",
    ) as output_file:
        shutil.copyfileobj(
            response,
            output_file,
        )

    if not os.path.isfile(zip_path):
        raise RuntimeError(
            "La descarga terminó pero no se encontró el ZIP."
        )

    if os.path.getsize(zip_path) == 0:
        raise RuntimeError(
            "El ZIP descargado está vacío."
        )

    return zip_path


def install_update(zip_path):
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(
            f"No se encontró el archivo descargado: {zip_path}"
        )

    extract_dir = tempfile.mkdtemp(
        prefix="dj_tagger_extract_"
    )

    # Usar ditto para extraer el ZIP en macOS.
    # zipfile.extractall() puede perder permisos ejecutables
    # necesarios para el binario principal de la aplicación.
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

    new_app_path = os.path.join(
        extract_dir,
        "DJ Tagger.app",
    )

    if not os.path.isdir(new_app_path):
        raise RuntimeError(
            "El ZIP descargado no contiene 'DJ Tagger.app'."
        )

    current_file = os.path.abspath(__file__)

    if ".app/Contents/" in current_file:
        current_app_path = current_file.split(
            ".app/Contents/"
        )[0] + ".app"
    else:
        current_app_path = "/Applications/DJ Tagger.app"

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
    new_app = shell_quote(new_app_path)
    updater = shell_quote(updater_script)
    log = shell_quote(log_file)

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
    if /usr/bin/pgrep -f "{current_app_path}/Contents/MacOS/" >/dev/null 2>&1; then
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

echo "Eliminando aplicación antigua..."

if [ -d {old_app} ]; then
    /bin/rm -rf {old_app}

    if [ -d {old_app} ]; then
        echo "ERROR: No se pudo eliminar la aplicación antigua."
        exit 1
    fi
fi

echo "Copiando nueva aplicación..."

/usr/bin/ditto {new_app} {old_app}

if [ ! -d {old_app} ]; then
    echo "ERROR: ditto no creó la aplicación nueva."
    exit 1
fi

echo "Abriendo nueva aplicación..."

/usr/bin/open -a {old_app}

OPEN_RESULT=$?

echo "Resultado de open: $OPEN_RESULT"

if [ $OPEN_RESULT -ne 0 ]; then
    echo "ERROR: No se pudo abrir la nueva aplicación."
    exit 1
fi

echo "Actualización completada correctamente."

sleep 5

/bin/rm -rf "$(dirname {new_app})"

echo "Archivos temporales eliminados."

/bin/rm -f {updater}

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
