# DJ Tagger — Autoetiquetado de MP3 para Apple Music / Rekordbox

Automatiza la parte pesada de añadir música nueva: busca los metadatos
correctos (título, artista, álbum, género, año, portada) usando la API
pública de iTunes, los escribe en el propio archivo MP3, y lo añade a tu
biblioteca de Apple Music ya etiquetado — para que tus playlists
inteligentes lo clasifiquen solas.

**Importante:** este script NO descarga música. Solo etiqueta archivos
MP3 que tú ya tienes (comprados/descargados legalmente) y los mete en tu
biblioteca. La búsqueda de música en sí (comprarla, conseguirla) sigue
siendo manual, como hasta ahora.

## Instalación (una sola vez, esto sí necesita Terminal)

Abre la Terminal en tu Mac (Aplicaciones → Utilidades → Terminal) y
ejecuta una sola vez:

```bash
pip3 install mutagen requests --break-system-packages
```

Si tu Mac tiene una versión de `pip3` que no reconoce `--break-system-packages` (te dará el error "no such option"), usa esta versión sin esa opción:

```bash
python3 -m pip install mutagen requests
```

Guarda estos 3 archivos juntos en una carpeta cómoda, por ejemplo
`~/Aplicaciones/DJ Tagger/`:
- `dj_tagger.py`
- `dj_tagger_gui.py`
- `Iniciar DJ Tagger.command`

## Uso normal: la app con interfaz (sin comandos)

A partir de aquí, ya no necesitas Terminal para trabajar con la app:

1. Haz **doble clic en `Iniciar DJ Tagger.command`**.
2. La aplicación tiene solo dos pestañas:
   - **Mi biblioteca**: carga y consulta tu biblioteca de Apple Music y permite seleccionar canciones para abrir sus búsquedas en el navegador. La URL de búsqueda se puede elegir o escribir manualmente y se aplica inmediatamente.
   - **Renombrar y añadir canciones**: arrastra uno o varios MP3 desde Finder al área indicada. Para cada archivo, la app busca el título y artista correctos, escribe los metadatos, renombra el archivo con el formato **`Canción - Artista.mp3`** y finalmente lo añade a Apple Music. Si ya existe un archivo con ese nombre, añade `(2)`, `(3)`, etc. para no sobrescribirlo.
3. También hay un botón **O elegir MP3...** como alternativa al arrastre.

La integración con Apple Music para añadir archivos requiere macOS. El arrastre desde Finder utiliza `tkinterdnd2`; el archivo `.command` intenta instalarlo automáticamente junto con `mutagen` y `requests` al abrir la aplicación.

## Modo Terminal (alternativa, si prefieres comandos)

Si en algún momento prefieres usarlo por Terminal en vez de la ventana,
sigue funcionando igual que antes:


1. Crea una carpeta donde vas a soltar tus descargas nuevas, por ejemplo
   `~/Downloads/DJ-nuevas`.
2. Abre Terminal y ejecuta:

```bash
python3 ~/Scripts/dj_tagger.py --watch ~/Downloads/DJ-nuevas
```

3. Deja esa ventana de Terminal abierta. Cada vez que descargues un MP3
   nuevo y lo muevas/guardes en esa carpeta, el script:
   - Adivina artista y título a partir del nombre del archivo
   - Busca los metadatos correctos en iTunes
   - Etiqueta el archivo (título, artista, álbum, género, año, portada)
   - Lo añade automáticamente a tu biblioteca de Apple Music

Para pararlo, pulsa `Ctrl + C` en la Terminal.

### Truco: que se abra solo al encender el Mac

Si quieres que esto se ejecute siempre en segundo plano sin tener que
abrir Terminal manualmente, dímelo y te preparo un servicio de `launchd`
(el equivalente en Mac a "que arranque solo").

## Modo 2: Manual (cuando el nombre del archivo no ayuda o quieres forzar la búsqueda)

```bash
python3 ~/Scripts/dj_tagger.py --file "/ruta/a/cancion.mp3" --song "Josh Baker - My Place"
```

Esto busca exactamente ese texto en iTunes, ignorando el nombre del
archivo, y etiqueta/añade ese MP3 concreto.

## Ajustar los géneros a tus playlists inteligentes

Abre `dj_tagger.py` y busca el diccionario `GENRE_MAP` cerca del principio
del archivo:

```python
GENRE_MAP = {
    "Dance": "House",
    "House": "House",
    "Electronic": "Electronica",
    "Hip-Hop/Rap": "Hip-Hop",
    ...
}
```

La clave (izquierda) es el género tal como lo devuelve iTunes. El valor
(derecha) es el texto exacto que se escribirá en el campo "Género" del
MP3 — ese es el que tiene que coincidir con la condición de tu smart
playlist en Apple Music. Añade o cambia las líneas que necesites.

## Limitaciones a tener en cuenta

- Solo funciona con archivos **MP3** (para WAV/AIFF/M4A el sistema de
  etiquetas es distinto; si los usas, avísame y adapto el script).
- La búsqueda automática depende de que el nombre del archivo se parezca
  al título real. Si la descarga viene con un nombre raro, mejor usa el
  Modo 2 (manual).
- La API de iTunes no siempre tiene el remix/edit exacto que buscas
  (versiones de club, extended mixes, etc.) — en esos casos revisa el
  resultado antes de fiarte a ciegas, o usa el modo manual con el nombre
  más preciso posible.
- Añadir a Apple Music solo funciona en macOS.
