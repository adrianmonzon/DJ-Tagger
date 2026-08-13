#!/usr/bin/env python3
"""
dj_tagger.py — Autoetiquetado de MP3 para DJs (macOS + Apple Music)

Dos modos de uso:

1) MODO CARPETA (automático):
   python3 dj_tagger.py --watch "/Users/tu_usuario/Downloads/DJ-nuevas"

   Vigila una carpeta. Cada vez que sueltas ahí un MP3 recién descargado,
   el script intenta adivinar artista/título a partir del nombre del
   archivo, busca los metadatos correctos en la API de iTunes, los escribe
   en el propio MP3 (título, artista, álbum, género, año, portada) y lo
   añade a tu biblioteca de Apple Music.

2) MODO MANUAL (tú le dices qué es):
   python3 dj_tagger.py --file "/ruta/a/cancion.mp3" --song "Josh Baker - My Place"

   Útil cuando el nombre del archivo no se parece en nada a la canción real,
   o cuando la búsqueda automática no encuentra el resultado correcto y
   quieres forzar tú los términos de búsqueda.

Requisitos (una vez):
   pip3 install mutagen requests --break-system-packages

Notas:
- La integración con Apple Music (añadir el archivo a la app) SOLO
  funciona en macOS, porque usa AppleScript vía `osascript`.
- El mapeo de género se puede editar abajo, en GENRE_MAP, para que
  encaje con las categorías de tus playlists inteligentes.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.parse
import unicodedata
from pathlib import Path

import requests
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3, APIC, ID3NoHeaderError
from mutagen.mp3 import MP3

ITUNES_SEARCH_URL = "https://itunes.apple.com/search"

# Ajusta esto a como quieras que se llamen los géneros en tus playlists
# inteligentes. La clave es lo que devuelve iTunes, el valor es lo que
# se escribe en el archivo.
GENRE_MAP = {
    "Dance": "House",
    "House": "House",
    "Electronic": "Electronica",
    "Hip-Hop/Rap": "Hip-Hop",
    "Reggaeton y flow": "Reggaeton",
    "Latin": "Latin",
    "Pop": "Pop",
}


def guess_artist_title_from_filename(filename: str):
    """Intenta extraer 'Artista - Título' de un nombre de archivo típico
    de descarga (quita numeración, extensión, guiones bajos, etc.)."""
    name = Path(filename).stem
    name = re.sub(r"^\d+[\.\-\s]*", "", name)  # quita "01 - " del principio
    name = name.replace("_", " ").strip()

    # Formato más común: "Artista - Título"
    if " - " in name:
        artist, title = name.split(" - ", 1)
        return artist.strip(), title.strip()

    # Si no hay separador claro, lo dejamos todo como término de búsqueda
    return None, name


def _norm_search_text(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ")
    value = re.sub(r"[\[\]{}()_\-–—,:;.!?]+", " ", value)
    value = re.sub(r"[^a-z0-9 ]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def _clean_filename_title(title: str) -> str:
    """Elimina etiquetas habituales de releases que perjudican la búsqueda."""
    title = re.sub(r"\[[^\]]*\]", " ", title or "")
    title = re.sub(r"\b(?:official\s+)?(?:visualizer|video|audio|lyrics?)\b", " ", title, flags=re.I)
    title = re.sub(r"\((?:extended|original|club|radio|instrumental|remix|edit|version|mix)[^)]*\)", " ", title, flags=re.I)
    return re.sub(r"\s+", " ", title).strip(" -_")


def _itunes_results(term: str):
    if not term.strip():
        return []
    params = {
        "term": term,
        "media": "music",
        "entity": "song",
        "limit": 25,
    }
    resp = requests.get(ITUNES_SEARCH_URL, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("results", [])


def search_itunes(query: str, artist: str | None = None, title: str | None = None):
    """Busca varias veces y puntúa los resultados para no depender del ranking de iTunes.

    Los nombres de descargas DJ suelen contener sellos, [LABEL], OFFICIAL VISUALIZER,
    EXTENDED MIX, etc. Un único término con todo eso puede hacer que iTunes no devuelva nada.
    """
    clean_artist = _clean_filename_title(artist or "")
    clean_title = _clean_filename_title(title or query)
    artist_parts = [p.strip() for p in re.split(r"\s+(?:x|and)\s+|\s*&\s*", clean_artist, flags=re.I) if p.strip()]

    queries = []
    for q in (
        f"{clean_artist} {clean_title}",
        f"{clean_title} {clean_artist}",
        clean_title,
        query,
    ):
        q = re.sub(r"\s+", " ", q).strip()
        if q and q not in queries:
            queries.append(q)
    for part in artist_parts:
        q = f"{part} {clean_title}".strip()
        if q not in queries:
            queries.append(q)

    candidates = {}
    for q in queries:
        for item in _itunes_results(q):
            track_id = item.get("trackId") or (item.get("artistName"), item.get("trackName"), item.get("collectionName"))
            candidates[track_id] = item

    if not candidates:
        return None

    wanted_title = set(_norm_search_text(clean_title).split())
    wanted_artist = set(_norm_search_text(clean_artist).split())

    def score(item):
        got_title = set(_norm_search_text(item.get("trackName", "")).split())
        got_artist = set(_norm_search_text(item.get("artistName", "")).split())
        title_overlap = len(wanted_title & got_title) / max(len(wanted_title), 1)
        artist_overlap = len(wanted_artist & got_artist) / max(len(wanted_artist), 1)
        exact_title = 1.0 if _norm_search_text(clean_title) == _norm_search_text(item.get("trackName", "")) else 0.0
        exact_artist = 1.0 if clean_artist and _norm_search_text(clean_artist) == _norm_search_text(item.get("artistName", "")) else 0.0
        return exact_title * 100 + exact_artist * 35 + title_overlap * 45 + artist_overlap * 35

    ranked = sorted(candidates.values(), key=score, reverse=True)
    best = ranked[0]
    if score(best) < 45:
        return None
    return best


def map_genre(itunes_genre: str) -> str:
    return GENRE_MAP.get(itunes_genre, itunes_genre or "Sin clasificar")


def download_artwork(url: str):
    if not url:
        return None
    # iTunes da la portada pequeña (100x100); pedimos una más grande
    big_url = re.sub(r"\d+x\d+bb", "1000x1000bb", url)
    try:
        r = requests.get(big_url, timeout=10)
        r.raise_for_status()
        return r.content
    except requests.RequestException:
        return None


def tag_mp3(filepath: str, meta: dict):
    """Escribe los metadatos en el MP3 usando mutagen."""
    try:
        tags = EasyID3(filepath)
    except ID3NoHeaderError:
        tags = EasyID3()
        tags.save(filepath)
        tags = EasyID3(filepath)

    tags["title"] = meta["title"]
    tags["artist"] = meta["artist"]
    tags["album"] = meta.get("album", "")
    tags["genre"] = meta["genre"]
    if meta.get("year"):
        tags["date"] = str(meta["year"])
    tags.save()

    # Portada (necesita ID3 "completo", no el EasyID3)
    artwork = meta.get("artwork_bytes")
    if artwork:
        id3 = ID3(filepath)
        id3.delall("APIC")
        id3.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=artwork))
        id3.save()


_SPANISH_MONTHS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6,
    "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9, "octubre": 10,
    "noviembre": 11, "diciembre": 12,
}
_ENGLISH_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
# "14 de febrero de 2025, 15:36:28" (puede llevar el día de la semana antes)
_DATE_RE_ES = re.compile(
    r"(\d{1,2})\s+de\s+(\w+)\s+de\s+(\d{4})[,]?\s+(\d{1,2}):(\d{2}):(\d{2})", re.IGNORECASE,
)
# "Friday, February 14, 2025 at 3:36:28 PM"
_DATE_RE_EN = re.compile(
    r"(\w+)\s+(\d{1,2}),\s+(\d{4})(?:\s+at)?\s+(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)?", re.IGNORECASE,
)


def _parse_music_date_string(date_str: str) -> int:
    """Convierte el texto de fecha que devuelve Music (en el idioma del
    sistema) en un número ordenable (año*1e8 + mes*1e6 + día*1e4 +
    minutos_del_día). Soporta español e inglés; si no reconoce el
    formato, devuelve 0 (se ordenará como la más antigua)."""
    if not date_str:
        return 0
    s = date_str.strip()

    m = _DATE_RE_ES.search(s)
    if m:
        day, month_name, year, hour, minute, _second = m.groups()
        month = _SPANISH_MONTHS.get(month_name.lower())
        if month:
            return int(year) * 100000000 + month * 1000000 + int(day) * 10000 + int(hour) * 60 + int(minute)

    m = _DATE_RE_EN.search(s)
    if m:
        month_name, day, year, hour, minute, _second, ampm = m.groups()
        month = _ENGLISH_MONTHS.get(month_name.lower())
        if month:
            hour_num = int(hour)
            if ampm and ampm.upper() == "PM" and hour_num != 12:
                hour_num += 12
            if ampm and ampm.upper() == "AM" and hour_num == 12:
                hour_num = 0
            return int(year) * 100000000 + month * 1000000 + int(day) * 10000 + hour_num * 60 + int(minute)

    return 0


def _fetch_apple_music_batch(start_index: int, end_index: int):
    """Lee un rango [start_index, end_index] (1-indexado) de canciones de la
    biblioteca. Devuelve (total_canciones, lista_de_tuplas)."""
    script = f'''
    set nameList to {{}}
    set artistList to {{}}
    set dateList to {{}}
    set totalCount to 0

    tell application "Music"
        set matchingTracks to (every track of library playlist 1 whose media kind is song)
        set totalCount to count of matchingTracks
        set startIdx to {start_index}
        set endIdx to {end_index}
        if endIdx > totalCount then set endIdx to totalCount
        if startIdx <= totalCount then
            repeat with i from startIdx to endIdx
                set t to item i of matchingTracks
                set trackName to ""
                set trackArtist to ""
                set trackDateStr to ""
                try
                    set trackName to (name of t)
                end try
                try
                    set trackArtist to (artist of t)
                end try
                try
                    set trackDateStr to ((date added of t) as string)
                end try
                set end of nameList to trackName
                set end of artistList to trackArtist
                set end of dateList to trackDateStr
            end repeat
        end if
    end tell

    set AppleScript's text item delimiters to "|||"
    set nameText to nameList as string
    set artistText to artistList as string
    set dateText to dateList as string
    set AppleScript's text item delimiters to ""

    return (totalCount as string) & "###SEP###" & nameText & "###SEP###" & artistText & "###SEP###" & dateText
    '''
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=120, check=True,
    )
    output = result.stdout.strip()
    parts = output.split("###SEP###")
    if len(parts) < 4:
        return 0, []
    total_raw, name_part, artist_part, date_part = parts[0], parts[1], parts[2], parts[3]
    try:
        total = int(total_raw.strip())
    except ValueError:
        total = 0

    names = name_part.split("|||") if name_part else []
    artists = artist_part.split("|||") if artist_part else []
    date_strs = date_part.split("|||") if date_part else []

    n = min(len(names), len(artists), len(date_strs))
    tracks = [(names[i], artists[i], _parse_music_date_string(date_strs[i])) for i in range(n)]
    return total, tracks


def get_apple_music_song_count():
    """Devuelve solo el número total de canciones (media kind 'song') en
    tu biblioteca, sin leer sus datos. Rápido: para comprobar si hay
    canciones nuevas sin tener que recargar toda la biblioteca."""
    if sys.platform != "darwin":
        return -1
    script = '''
    tell application "Music"
        return (count of (every track of library playlist 1 whose media kind is song)) as string
    end tell
    '''
    try:
        result = subprocess.run(
            ["osascript", "-e", script],
            capture_output=True, text=True, timeout=60, check=True,
        )
        return int(result.stdout.strip())
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        return -1


def get_apple_music_library(progress_callback=None, batch_size: int = 50, start_index: int = 1):
    """Devuelve una lista de (titulo, artista, clave_orden_fecha) leída
    directamente de tu biblioteca de Apple Music: incluye tanto archivos
    locales como canciones de streaming/nube añadidas a tu biblioteca.
    clave_orden_fecha es un número (año*1e8 + mes*1e6 + día*1e4 + minuto
    del día) que permite ordenar por fecha de inclusión sin necesitar
    restar dos fechas.

    Lee la biblioteca en lotes de `batch_size` canciones, empezando en
    `start_index` (1-indexado; súbelo para traer solo las canciones más
    allá de un punto ya cargado, en vez de traerlas todas de nuevo). Si se
    pasa progress_callback(hechas, total), se llama después de cada lote
    para poder mostrar una barra de progreso. Solo lectura, no modifica
    nada. macOS únicamente."""
    if sys.platform != "darwin":
        print("  (Aviso: no estás en macOS, no se puede leer Apple Music)")
        return []

    all_tracks = []
    start = start_index
    total = None

    while total is None or start <= total:
        end = start + batch_size - 1
        try:
            batch_total, batch_tracks = _fetch_apple_music_batch(start, end)
        except subprocess.CalledProcessError as e:
            print(f"  No se pudo leer el lote {start}-{end}: {e.stderr.strip()}")
            break
        except subprocess.TimeoutExpired:
            print(f"  El lote {start}-{end} ha tardado demasiado, se omite.")
            break

        if total is None:
            total = batch_total
            if total == 0 or start_index > total:
                return []

        all_tracks.extend(batch_tracks)
        if progress_callback:
            done = min(start - start_index + len(batch_tracks), total - start_index + 1)
            progress_callback(done, total - start_index + 1)

        start = end + 1

    return all_tracks


DEFAULT_SEARCH_BASE_URL = "https://www.roji.ca/"


def build_search_url(base_url: str, query: str) -> str:
    """Construye la URL de búsqueda respetando el formato que use el sitio.

    Soporta, entre otros:
      - Fragmentos con marcador: ``https://sitio/#q=``
      - Query params con marcador: ``https://sitio/search?q=``
      - Rutas dinámicas tipo slug: ``https://www.roji.ca/discover/etta-yellow-space/``
        -> ``https://www.roji.ca/discover/<slug>/``
      - Rutas que terminan en ``/``: ``https://sitio/search/``
        -> ``https://sitio/search/<slug>/``

    En una URL de ruta, si ya existe un último segmento, se considera que es
    el valor dinámico y se sustituye; esto evita acabar con ``.../tema/cancion``
    cuando la URL proporcionada ya representa una búsqueda concreta.
    """
    base_url = (base_url or DEFAULT_SEARCH_BASE_URL).strip() or DEFAULT_SEARCH_BASE_URL
    query = str(query or "").strip()

    # Si la URL ya contiene un marcador '=' al final (query param o fragmento),
    # conservar exactamente ese mecanismo.
    if base_url.endswith("="):
        return base_url + urllib.parse.quote(query, safe="")

    parsed = urllib.parse.urlsplit(base_url)
    slug = urllib.parse.quote(
        re.sub(r"[^\w\-\s]+", "", query, flags=re.UNICODE).strip().replace(" ", "-"),
        safe="-"
    ).lower()

    # Algunas webs tienen una URL raíz que actúa como base para una ruta de
    # descubrimiento. Roji, por ejemplo, usa /discover/<slug>/. Si el usuario
    # introduce únicamente https://www.roji.ca/ debemos conservar esa estructura
    # y no generar https://www.roji.ca/<slug>/.
    path = parsed.path or "/"
    trailing_slash = path.endswith("/")
    parts = [part for part in path.split("/") if part]

    if not parts and parsed.netloc.lower() in {"www.roji.ca", "roji.ca"}:
        return urllib.parse.urlunsplit((
            parsed.scheme, parsed.netloc, f"/discover/{slug}/", parsed.query, parsed.fragment
        ))

    if parts:
        # Si la ruta termina en '/', normalmente indica un directorio/base de
        # búsqueda y debemos añadir el slug. Algunas webs, como roji.ca, usan
        # /discover/<slug>/; en ese caso el último segmento ya es el valor
        # dinámico y debe sustituirse.
        dynamic_parent_paths = {"discover", "search", "find", "track", "song"}
        if trailing_slash and parts[-1].lower() not in dynamic_parent_paths and len(parts) >= 2 and parts[-2].lower() in dynamic_parent_paths:
            parts[-1] = slug
        elif trailing_slash:
            parts.append(slug)
        else:
            parts[-1] = slug
    else:
        parts.append(slug)

    new_path = "/" + "/".join(parts) + ("/" if trailing_slash else "")
    return urllib.parse.urlunsplit((parsed.scheme, parsed.netloc, new_path, parsed.query, parsed.fragment))


def open_search_tabs(queries, base_url=DEFAULT_SEARCH_BASE_URL):
    """Abre una o varias búsquedas en el navegador del sistema.

    La URL introducida en la GUI puede usar distintos formatos de búsqueda;
    :func:`build_search_url` detecta cómo insertar el texto en cada caso.
    """
    import webbrowser

    if isinstance(queries, str):
        queries = [queries]

    for q in queries:
        url = build_search_url(base_url, q)
        # new=2: pestaña nueva, reutilizando la ventana del navegador si ya hay una abierta
        webbrowser.open(url, new=2)


def add_to_apple_music(filepath: str):
    """Añade el archivo a la biblioteca de Apple Music (solo macOS)."""
    if sys.platform != "darwin":
        print("  (Aviso: no estás en macOS, me salto el paso de añadir a Apple Music)")
        return
    posix_path = os.path.abspath(filepath)
    script = f'''
    tell application "Music"
        add POSIX file "{posix_path}"
    end tell
    '''
    subprocess.run(["osascript", "-e", script], check=False)


def sanitize_filename_part(value: str) -> str:
    """Limpia un título/artista para poder usarlo como nombre de archivo."""
    value = re.sub(r'[\/:*?"<>|\x00-\x1f]', '', value or '')
    value = re.sub(r'\s+', ' ', value).strip().rstrip('.')
    return value


def rename_processed_file(filepath: str, title: str, artist: str) -> str:
    """Renombra el MP3 como 'Canción - Artista.mp3' y evita sobrescribir otro."""
    path = Path(filepath)
    title_part = sanitize_filename_part(title) or path.stem
    artist_part = sanitize_filename_part(artist)
    base_name = f"{title_part} - {artist_part}" if artist_part else title_part
    target = path.with_name(base_name + path.suffix.lower())

    if target.resolve() == path.resolve():
        return str(path)

    if target.exists():
        stem = target.stem
        counter = 2
        while True:
            candidate = target.with_name(f"{stem} ({counter}){target.suffix}")
            if not candidate.exists():
                target = candidate
                break
            counter += 1

    path.rename(target)
    return str(target)


def process_file(filepath: str, manual_query=None, rename_file: bool = False):
    filename = os.path.basename(filepath)
    print(f"\nProcesando: {filename}")

    artist, title = guess_artist_title_from_filename(filename)
    if manual_query:
        query = manual_query
        search_artist, search_title = None, manual_query
    else:
        search_artist, search_title = artist, title
        query = f"{artist} {title}" if artist else title
    print(f"  Buscando: '{query}'")

    result = search_itunes(query, artist=search_artist, title=search_title)
    if not result:
        print("  No se encontraron resultados. Se deja el archivo sin tocar.")
        return

    meta = {
        "title": result.get("trackName", ""),
        "artist": result.get("artistName", ""),
        "album": result.get("collectionName", ""),
        "genre": map_genre(result.get("primaryGenreName", "")),
        "year": (result.get("releaseDate") or "")[:4],
        "artwork_bytes": download_artwork(result.get("artworkUrl100")),
    }
    print(f"  Encontrado: {meta['artist']} - {meta['title']} [{meta['genre']}]")

    tag_mp3(filepath, meta)
    print("  Etiquetas escritas en el archivo.")

    if rename_file:
        filepath = rename_processed_file(filepath, meta["title"], meta["artist"])
        print(f"  Renombrado: {os.path.basename(filepath)}")

    add_to_apple_music(filepath)
    print("  Añadido a Apple Music.")


def process_folder_batch(folder: str):
    """Procesa de golpe todos los MP3 que ya existen en una carpeta."""
    mp3_files = [f for f in os.listdir(folder) if f.lower().endswith(".mp3")]
    if not mp3_files:
        print("No hay archivos .mp3 en esa carpeta.")
        return
    print(f"Encontrados {len(mp3_files)} MP3. Procesando en lote...")
    for f in mp3_files:
        process_file(os.path.join(folder, f))
    print(f"\nListo. {len(mp3_files)} archivos procesados.")


def watch_folder(folder: str, poll_seconds: int = 5):
    print(f"Vigilando carpeta: {folder}")
    print("Suelta ahí tus MP3 recién descargados. Ctrl+C para parar.\n")
    seen = set(os.listdir(folder))
    try:
        while True:
            time.sleep(poll_seconds)
            current = set(os.listdir(folder))
            new_files = current - seen
            for f in new_files:
                if f.lower().endswith(".mp3"):
                    full_path = os.path.join(folder, f)
                    # Pequeña espera para asegurar que la descarga terminó
                    time.sleep(2)
                    process_file(full_path)
            seen = current
    except KeyboardInterrupt:
        print("\nDetenido.")


def main():
    parser = argparse.ArgumentParser(description="Autoetiquetado de MP3 para DJs")
    parser.add_argument("--watch", metavar="CARPETA", help="Vigila una carpeta y procesa MP3 nuevos automáticamente")
    parser.add_argument("--batch", metavar="CARPETA", help="Procesa de golpe todos los MP3 que YA existen en una carpeta")
    parser.add_argument("--file", metavar="ARCHIVO", help="Ruta a un MP3 concreto a procesar (modo manual)")
    parser.add_argument("--song", metavar="TEXTO", help="Texto de búsqueda, ej: 'Josh Baker - My Place' (con --file)")
    args = parser.parse_args()

    if args.watch:
        watch_folder(args.watch)
    elif args.batch:
        process_folder_batch(args.batch)
    elif args.file:
        process_file(args.file, manual_query=args.song)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
