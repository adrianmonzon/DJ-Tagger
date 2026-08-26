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

    return zip_path


def install_update(zip_path):
    if not os.path.isfile(zip_path):
        raise FileNotFoundError(
            f"No se encontró el archivo descargado: {zip_path}"
        )

    extract_dir = tempfile.mkdtemp(
        prefix="dj_tagger_extract_"
    )

    with zipfile.ZipFile(
        zip_path,
        "r",
    ) as archive:
        archive.extractall(extract_dir)

    new_app_path = os.path.join(
        extract_dir,
        "DJ Tagger.app",
    )

    if not os.path.isdir(new_app_path):
        raise RuntimeError(
            "El ZIP descargado no contiene 'DJ Tagger.app'."
        )

    # Determinar la aplicación que está ejecutándose.
    # En una app empaquetada, __file__ está dentro de:
    # DJ Tagger.app/Contents/...
    current_file = os.path.abspath(__file__)

    if ".app/Contents/" in current_file:
        current_app_path = current_file.split(
            ".app/Contents/"
        )[0] + ".app"
    else:
        # Si se ejecuta desde el proyecto, actualizar la app instalada.
        current_app_path = "/Applications/DJ Tagger.app"

    # No usamos "python3" para el actualizador porque una instalación
    # normal de macOS no tiene por qué tener Python disponible.
    # /bin/sh y /usr/bin/ditto sí forman parte de macOS.
    updater_script = os.path.join(
        tempfile.gettempdir(),
        "dj_tagger_apply_update.sh",
    )

    shell_quote = lambda value: "'" + value.replace("'", "'\\''") + "'"

    old_app = shell_quote(current_app_path)
    new_app = shell_quote(new_app_path)
    script_path = shell_quote(updater_script)

    script = f"""#!/bin/sh

OLD_APP={old_app}
NEW_APP={new_app}
UPDATER_SCRIPT={script_path}

# Dar tiempo a DJ Tagger para cerrar completamente.
sleep 2

# Esperar un poco más si el proceso todavía mantiene abierta la app.
for i in 1 2 3 4 5; do
    if /usr/bin/pgrep -f "$OLD_APP/Contents/MacOS/" >/dev/null 2>&1; then
        sleep 1
    else
        break
    fi
done

# Eliminar la versión instalada y copiar la nueva.
if [ -d "$OLD_APP" ]; then
    /bin/rm -rf "$OLD_APP"
fi

/usr/bin/ditto "$NEW_APP" "$OLD_APP"

# Abrir la nueva versión.
 /usr/bin/open "$OLD_APP" >/dev/null 2>&1 &

# Limpiar los archivos temporales después de abrir la app.
(
    sleep 3
    /bin/rm -rf "$(dirname "$NEW_APP")"
    /bin/rm -f "$UPDATER_SCRIPT"
) >/dev/null 2>&1 &

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

    # Ejecutar el script con /bin/sh, disponible en cualquier macOS.
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
