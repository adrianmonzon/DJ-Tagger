#!/bin/bash
# Doble clic en este archivo para abrir la app DJ Tagger.
cd "$(dirname "$0")"
python3 -m pip install --quiet tkinterdnd2 mutagen requests 2>/dev/null || true
python3 dj_tagger_gui.py
