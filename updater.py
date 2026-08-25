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

    current_app_path = os.path.abspath(
        os.path.join(
            os.path.dirname(__file__),
            "DJ Tagger.app",
        )
    )

    if ".app/Contents/" in current_app_path:
        current_app_path = current_app_path.split(
            ".app/Contents/"
        )[0] + ".app"

    updater_script = os.path.join(
        tempfile.gettempdir(),
        "dj_tagger_apply_update.py",
    )

    script = f'''import os
import shutil
import subprocess
import time

old_app = {current_app_path!r}
new_app = {new_app_path!r}
updater_script = {updater_script!r}

time.sleep(2)

try:
    if os.path.exists(old_app):
        shutil.rmtree(old_app)

    shutil.copytree(
        new_app,
        old_app,
    )

    subprocess.Popen(
        ["open", old_app],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

finally:
    try:
        os.remove(updater_script)
    except Exception:
        pass
'''

    with open(
        updater_script,
        "w",
        encoding="utf-8",
    ) as file:
        file.write(script)

    subprocess.Popen(
        [
            "python3",
            updater_script,
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )

    return True
