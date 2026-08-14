import json
import ssl
import urllib.request

import certifi

from version import APP_VERSION


GITHUB_API_URL = (
    "https://api.github.com/repos/adrianmonzon/DJ-Tagger/releases/latest"
)


def version_tuple(version):
    return tuple(int(part) for part in version.lstrip("v").split("."))


def check_for_update():
    try:
        request = urllib.request.Request(
            GITHUB_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "DJ-Tagger",
            },
        )

        context = ssl.create_default_context(
            cafile=certifi.where()
        )

        with urllib.request.urlopen(
            request,
            timeout=5,
            context=context,
        ) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )

        latest_version = data["tag_name"].lstrip("v")

        if version_tuple(latest_version) > version_tuple(APP_VERSION):
            return {
                "available": True,
                "current_version": APP_VERSION,
                "latest_version": latest_version,
                "download_url": data.get("html_url"),
            }

        return {
            "available": False,
            "current_version": APP_VERSION,
            "latest_version": latest_version,
            "download_url": None,
        }

    except Exception as error:
        return {
            "available": False,
            "current_version": APP_VERSION,
            "latest_version": None,
            "download_url": None,
            "error": str(error),
        }
