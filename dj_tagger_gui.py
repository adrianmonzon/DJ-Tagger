#!/usr/bin/env python3
"""
dj_tagger_gui.py — Interfaz gráfica para DJ Tagger

Ventana para gestionar tu biblioteca de Apple Music y procesar MP3 mediante arrastrar y soltar.

No requiere Terminal ni comandos una vez abierta. Para abrirla, haz doble
clic en "Iniciar DJ Tagger.command" (ver README.md).
"""

import os
import queue
import threading
import time
import tkinter as tk
import webbrowser
from version import APP_VERSION
from tkinter import filedialog, messagebox, ttk

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    DND_FILES = None
    TkinterDnD = None

import dj_tagger as core
from updater import check_for_update


class TextRedirector:
    """Redirige print() hacia la caja de texto de la interfaz."""

    def __init__(self, out_queue: queue.Queue):
        self.out_queue = out_queue

    def write(self, message):
        if message.strip():
            self.out_queue.put(message)

    def flush(self):
        pass


class DJTaggerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("DJ Tagger")
        self.root.geometry("720x880")
        self.root.minsize(680, 700)

        self.log_queue = queue.Queue()
        self.watching = False
        self.watch_thread = None
        self.watch_folder_path = None

        # URL base de búsqueda: editable desde la GUI y usada inmediatamente
        # en las búsquedas nuevas. Se mantiene la URL actual como valor por defecto.
        self.search_base_url_var = tk.StringVar(value=core.DEFAULT_SEARCH_BASE_URL)
        self.search_base_url_options = [
            core.DEFAULT_SEARCH_BASE_URL,
            "https://superceramika.pl/#q=",
        ]

        self._build_ui()
        self._poll_log_queue()

        # Comprobar actualizaciones en segundo plano para no bloquear la interfaz.
        threading.Thread(
            target=self._check_for_updates,
            daemon=True,
        ).start()

    # ---------- Construcción de la interfaz ----------

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        title = ttk.Label(self.root, text="DJ Tagger", font=("Helvetica", 18, "bold"))
        title.pack(anchor="w", **pad)

        subtitle = ttk.Label(
            self.root,
            text="Etiqueta MP3 automáticamente y los añade a Apple Music",
            foreground="#666",
        )
        subtitle.pack(anchor="w", padx=10, pady=(0, 6))

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="x", padx=10, pady=(0, 10))

        # --- Pestaña: Mi biblioteca ---
        tab_library = ttk.Frame(notebook, padding=10)
        notebook.add(tab_library, text="Mi biblioteca")

        lib_header = ttk.Frame(tab_library)
        lib_header.pack(fill="x", pady=(0, 6))
        ttk.Label(
            lib_header,
            text="Mi biblioteca",
            font=("Helvetica", 11, "bold"),
        ).pack(side="left")

        lib_controls = ttk.Frame(tab_library)
        lib_controls.pack(fill="x", pady=(0, 6))
        self.load_lib_btn = ttk.Button(
            lib_controls,
            text="Cargar mi biblioteca",
            command=self._load_library,
        )
        self.load_lib_btn.pack(side="left")

        self.lib_status_var = tk.StringVar(
            value="Biblioteca no cargada todavía"
        )
        ttk.Label(
            lib_controls,
            textvariable=self.lib_status_var,
            foreground="#888",
        ).pack(side="left", padx=(10, 0))

        self.lib_progressbar = ttk.Progressbar(
            tab_library,
            orient="horizontal",
            mode="determinate",
            maximum=100,
        )
        self.lib_progressbar.pack(fill="x", pady=(0, 6))

        self.lib_progress_text_var = tk.StringVar(value="")
        ttk.Label(
            tab_library,
            textvariable=self.lib_progress_text_var,
            foreground="#888",
        ).pack(anchor="w", pady=(0, 6))

        self.sort_by_date_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            tab_library,
            text="Ordenar por orden de inclusión (más reciente primero)",
            variable=self.sort_by_date_var,
            command=self._apply_library_filter,
        ).pack(anchor="w", pady=(4, 0))

        filter_label_row = ttk.Frame(tab_library)
        filter_label_row.pack(fill="x", pady=(6, 0))

        ttk.Label(
            filter_label_row,
            text="Filtrar:",
        ).pack(side="left")

        self.filter_scope_var = tk.StringVar(value="ambos")

        ttk.Radiobutton(
            filter_label_row,
            text="Canción",
            variable=self.filter_scope_var,
            value="cancion",
            command=self._apply_library_filter,
        ).pack(side="left", padx=(10, 0))

        ttk.Radiobutton(
            filter_label_row,
            text="Artista",
            variable=self.filter_scope_var,
            value="artista",
            command=self._apply_library_filter,
        ).pack(side="left", padx=(6, 0))

        ttk.Radiobutton(
            filter_label_row,
            text="Ambos",
            variable=self.filter_scope_var,
            value="ambos",
            command=self._apply_library_filter,
        ).pack(side="left", padx=(6, 0))

        self.library_filter_var = tk.StringVar()
        self.library_filter_var.trace_add(
            "write",
            self._apply_library_filter,
        )

        ttk.Entry(
            tab_library,
            textvariable=self.library_filter_var,
        ).pack(fill="x", pady=(4, 6))

        select_row = ttk.Frame(tab_library)
        select_row.pack(fill="x", pady=(0, 4))

        ttk.Button(
            select_row,
            text="Marcar todas las visibles",
            command=self._check_all_visible,
        ).pack(side="left")

        ttk.Button(
            select_row,
            text="Desmarcar todas",
            command=self._uncheck_all,
        ).pack(side="left", padx=(6, 0))

        list_frame = ttk.Frame(tab_library)
        list_frame.pack(fill="both", expand=True)

        lib_scroll = ttk.Scrollbar(
            list_frame,
            orient="vertical",
        )

        self.library_tree = ttk.Treeview(
            list_frame,
            columns=("check", "song", "artist"),
            show="headings",
            yscrollcommand=lib_scroll.set,
            height=10,
            selectmode="none",
        )

        self.library_tree.heading("check", text="✓")
        self.library_tree.heading("song", text="Canción")
        self.library_tree.heading("artist", text="Artista")

        self.library_tree.column(
            "check",
            width=34,
            anchor="center",
            stretch=False,
        )
        self.library_tree.column(
            "song",
            width=290,
            anchor="w",
        )
        self.library_tree.column(
            "artist",
            width=190,
            anchor="w",
        )

        lib_scroll.configure(
            command=self.library_tree.yview,
        )

        self.library_tree.pack(
            side="left",
            fill="both",
            expand=True,
        )

        lib_scroll.pack(
            side="right",
            fill="y",
        )

        self.library_tree.bind(
            "<Button-1>",
            self._on_library_tree_click,
        )

        bottom_row = ttk.Frame(tab_library)
        bottom_row.pack(
            side="bottom",
            fill="x",
            pady=(8, 0),
        )

        self.extended_var = tk.BooleanVar(value=False)

        ttk.Checkbutton(
            bottom_row,
            text='Añadir "Extended" a cada búsqueda',
            variable=self.extended_var,
        ).pack(side="left")

        # URL de búsqueda: configurable desde Mi biblioteca.
        # Se aplica inmediatamente en las siguientes búsquedas.
        url_frame = ttk.LabelFrame(
            tab_library,
            text="URL de búsqueda",
        )
        url_frame.pack(
            fill="x",
            pady=(8, 0),
        )

        url_inner = ttk.Frame(
            url_frame,
            padding=8,
        )
        url_inner.pack(fill="x")

        ttk.Label(
            url_inner,
            text="URL:",
        ).pack(side="left")

        self.search_base_url_combo = ttk.Combobox(
            url_inner,
            textvariable=self.search_base_url_var,
            values=self.search_base_url_options,
            state="normal",
        )

        self.search_base_url_combo.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(8, 0),
        )

        ttk.Label(
            url_frame,
            text="Selecciona una URL o escribe otra. Se aplicará inmediatamente en la siguiente búsqueda.",
            foreground="#666",
        ).pack(
            anchor="w",
            padx=8,
            pady=(0, 8),
        )

        ttk.Button(
            bottom_row,
            text="Buscar seleccionadas en convertidor",
            command=self._search_selected_in_convertidor,
        ).pack(
            side="left",
            padx=(10, 0),
        )

        self.library_tracks = []
        self.filtered_tracks = {}
        self.checked_tracks = set()

        # --- Pestaña: Renombrar y añadir canciones ---

        tab_rename = ttk.Frame(
            notebook,
            padding=10,
        )
        notebook.add(
            tab_rename,
            text="Renombrar y añadir canciones",
        )

        ttk.Label(
            tab_rename,
            text="Arrastra uno o varios MP3 aquí",
            font=("Helvetica", 16, "bold"),
        ).pack(pady=(30, 8))

        ttk.Label(
            tab_rename,
            text=(
                "Buscaré el título y artista correctos, escribiré los metadatos,\n"
                "renombraré cada archivo como «Canción - Artista.mp3» y lo añadiré a Apple Music."
            ),
            justify="center",
            foreground="#666",
        ).pack(pady=(0, 18))

        self.drop_frame = tk.Frame(
            tab_rename,
            bd=2,
            relief="groove",
            height=180,
        )
        self.drop_frame.pack(
            fill="both",
            expand=True,
            padx=30,
            pady=10,
        )
        self.drop_frame.pack_propagate(False)

        self.drop_label = ttk.Label(
            self.drop_frame,
            text="SUELTA LOS MP3 AQUÍ",
            anchor="center",
            justify="center",
            font=("Helvetica", 14, "bold"),
        )
        self.drop_label.pack(
            fill="both",
            expand=True,
        )

        ttk.Button(
            tab_rename,
            text="O elegir MP3...",
            command=self._choose_and_process_mp3s,
        ).pack(pady=(8, 4))

        ttk.Label(
            tab_rename,
            text="Puedes seleccionar varios archivos a la vez.",
            foreground="#888",
        ).pack(pady=(0, 10))

        if DND_FILES is not None:
            for widget in (
                self.drop_frame,
                self.drop_label,
            ):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind(
                    "<<Drop>>",
                    self._on_mp3_drop,
                )
        else:
            ttk.Label(
                tab_rename,
                text=(
                    "Para activar el arrastre desde Finder instala tkinterdnd2 "
                    "(el instalador lo hace automáticamente)."
                ),
                foreground="#aa6600",
            ).pack(pady=(0, 8))

        # Seleccionar Mi biblioteca por defecto al abrir.
        notebook.select(tab_library)

        # --- Log ---

        log_frame = ttk.LabelFrame(
            self.root,
            text="Actividad",
        )
        log_frame.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        self.log_text = tk.Text(
            log_frame,
            height=14,
            state="disabled",
            wrap="word",
        )
        self.log_text.pack(
            fill="both",
            expand=True,
            padx=6,
            pady=6,
        )

    # ---------- Utilidades de log ----------

    def _log(self, message: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(
            "end",
            message if message.endswith("\n") else message + "\n",
        )
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()
                self._log(message)
        except queue.Empty:
            pass

        self.root.after(
            150,
            self._poll_log_queue,
        )

    def _run_in_thread(self, target, *args):
        import sys

        def wrapper():
            old_stdout = sys.stdout
            sys.stdout = TextRedirector(self.log_queue)

            try:
                target(*args)
            except Exception as e:
                self.log_queue.put(f"ERROR: {e}")
            finally:
                sys.stdout = old_stdout

        t = threading.Thread(
            target=wrapper,
            daemon=True,
        )
        t.start()

        return t

    # ---------- Actualizaciones ----------

    def _check_for_updates(self):
        """Comprueba en segundo plano si existe una versión más reciente."""

        result = check_for_update()

        if not result.get("available"):
            return

        latest_version = result.get("latest_version")
        download_url = result.get("download_url")

        if not latest_version or not download_url:
            return

        self.root.after(
            0,
            lambda: self._show_update_available(
                latest_version,
                download_url,
            ),
        )

    def _show_update_available(
        self,
        latest_version,
        download_url,
    ):
        """Muestra el aviso de actualización en el hilo de la interfaz."""

        update = messagebox.askyesno(
            "Actualización disponible",
            (
                f"Hay una nueva versión de DJ Tagger.\n\n"
                f"Versión actual: {APP_VERSION}\n"
                f"Nueva versión: {latest_version}\n\n"
                "¿Quieres abrir la página de descarga?"
            ),
        )

        if update:
            webbrowser.open(download_url)

    # ---------- Acciones: vigilar carpeta ----------

    def _choose_watch_folder(self):
        folder = filedialog.askdirectory(
            title="Elige la carpeta a vigilar",
        )

        if folder:
            self.watch_folder_path = folder
            self.watch_path_var.set(folder)
            self.watch_toggle_btn.configure(
                state="normal",
            )

    def _toggle_watch(self):
        if not self.watching:
            self.watching = True
            self.watch_toggle_btn.configure(
                text="Parar de vigilar",
            )
            self._log(
                f"Vigilando: {self.watch_folder_path}"
            )
            self.watch_thread = self._run_in_thread(
                self._watch_loop,
                self.watch_folder_path,
            )
        else:
            self.watching = False
            self.watch_toggle_btn.configure(
                text="Empezar a vigilar",
            )
            self._log(
                "Vigilancia detenida."
            )

    def _watch_loop(self, folder):
        seen = set(os.listdir(folder))

        while self.watching:
            time.sleep(3)

            if not self.watching:
                break

            current = set(os.listdir(folder))
            new_files = current - seen

            for f in new_files:
                if f.lower().endswith(".mp3"):
                    time.sleep(2)
                    core.process_file(
                        os.path.join(folder, f)
                    )

            seen = current

    # ---------- Acciones: lote ----------

    def _run_batch(self):
        folder = filedialog.askdirectory(
            title="Elige la carpeta a procesar",
        )

        if not folder:
            return

        self._run_in_thread(
            core.process_folder_batch,
            folder,
        )

    # ---------- Acciones: manual ----------

    def _choose_and_process_mp3s(self):
        files = filedialog.askopenfilenames(
            title="Selecciona los MP3",
            filetypes=[
                ("Archivos MP3", "*.mp3"),
                ("Todos los archivos", "*"),
            ],
        )

        self._process_dropped_files(files)

    def _on_mp3_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]

        self._process_dropped_files(files)

    def _process_dropped_files(self, files):
        mp3_files = [
            os.path.abspath(f)
            for f in files
            if str(f).lower().endswith(".mp3")
            and os.path.isfile(f)
        ]

        if not mp3_files:
            messagebox.showwarning(
                "DJ Tagger",
                "No se han encontrado archivos MP3 válidos.",
            )
            return

        self._log(
            f"\nProcesando {len(mp3_files)} MP3...\n"
        )

        self._run_in_thread(
            self._process_mp3_files_worker,
            mp3_files,
        )

    def _process_mp3_files_worker(self, files):
        for filepath in files:
            try:
                core.process_file(
                    filepath,
                    rename_file=True,
                )
            except Exception as exc:
                print(
                    f"  ERROR procesando {os.path.basename(filepath)}: {exc}"
                )

        print("\nProceso terminado.")

    def _load_library(self):
        if self.library_tracks:
            self._update_library()
            return

        self.load_lib_btn.configure(
            state="disabled",
        )

        self.lib_status_var.set(
            "Cargando biblioteca... (puede tardar un poco)"
        )

        self.lib_progressbar.configure(
            mode="determinate",
            maximum=100,
            value=0,
        )

        self.lib_progress_text_var.set(
            "Empezando..."
        )

        self._run_in_thread(
            self._load_library_worker
        )

    def _load_library_worker(self):
        print(
            "Leyendo tu biblioteca de Apple Music..."
        )

        def on_progress(done, total):
            self.root.after(
                0,
                lambda: self._update_library_progress(
                    done,
                    total,
                ),
            )

        tracks = core.get_apple_music_library(
            progress_callback=on_progress,
        )

        self.root.after(
            0,
            lambda: self._on_library_loaded(tracks),
        )

    def _update_library(self):
        self.load_lib_btn.configure(
            state="disabled",
        )

        self.lib_status_var.set(
            "Buscando canciones nuevas..."
        )

        self._run_in_thread(
            self._update_library_worker
        )

    def _update_library_worker(self):
        current_count = len(self.library_tracks)
        new_total = core.get_apple_music_song_count()

        if new_total < 0:
            self.root.after(
                0,
                lambda: self._on_library_update_done(
                    None,
                    "No se pudo comprobar tu biblioteca (revisa Actividad).",
                ),
            )
            return

        if new_total <= current_count:
            self.root.after(
                0,
                lambda: self._on_library_update_done(
                    [],
                    f"Sin novedades: sigues teniendo {current_count} canciones.",
                ),
            )
            return

        print(
            f"Buscando canciones nuevas ({new_total - current_count})..."
        )

        def on_progress(done, total):
            self.root.after(
                0,
                lambda: self._update_library_progress(
                    done,
                    total,
                ),
            )

        new_tracks = core.get_apple_music_library(
            progress_callback=on_progress,
            start_index=current_count + 1,
        )

        self.root.after(
            0,
            lambda: self._on_library_update_done(
                new_tracks,
                None,
            ),
        )

    def _on_library_update_done(
        self,
        new_tracks,
        error_message,
    ):
        self.load_lib_btn.configure(
            state="normal",
        )

        if error_message:
            self.lib_status_var.set(
                error_message
            )
            self.lib_progress_text_var.set("")
            return

        if new_tracks:
            self.library_tracks.extend(
                new_tracks
            )

            self.lib_status_var.set(
                f"{len(new_tracks)} canciones nuevas añadidas "
                f"({len(self.library_tracks)} en total)"
            )

            self.lib_progress_text_var.set("")
            self._apply_library_filter()

        else:
            self.lib_status_var.set(
                f"Sin novedades: sigues teniendo "
                f"{len(self.library_tracks)} canciones."
            )

            self.lib_progress_text_var.set("")

    def _update_library_progress(
        self,
        done,
        total,
    ):
        if total > 0:
            self.lib_progressbar.configure(
                maximum=total,
                value=done,
            )

            self.lib_progress_text_var.set(
                f"{done} / {total} canciones leídas"
            )

    def _on_library_loaded(self, tracks):
        self.library_tracks = tracks
        self.checked_tracks = set()

        self.load_lib_btn.configure(
            state="normal",
        )

        if tracks:
            self.lib_status_var.set(
                f"{len(tracks)} canciones cargadas"
            )

            self.lib_progressbar.configure(
                value=self.lib_progressbar["maximum"]
            )

            self.lib_progress_text_var.set(
                f"Completado: {len(tracks)} canciones"
            )

            self.load_lib_btn.configure(
                text="Actualizar"
            )

        else:
            self.lib_status_var.set(
                "No se pudo cargar (revisa la ventana de Actividad)"
            )

            self.lib_progress_text_var.set("")

        self._apply_library_filter()

    def _apply_library_filter(self, *args):
        query = self.library_filter_var.get().lower().strip()
        scope = self.filter_scope_var.get()

        self.library_tree.delete(
            *self.library_tree.get_children()
        )

        self.filtered_tracks = {}

        rows = list(
            enumerate(self.library_tracks)
        )

        if self.sort_by_date_var.get():
            rows.sort(
                key=lambda r: r[1][2],
                reverse=True,
            )

        for original_idx, (
            title,
            artist,
            _seconds,
        ) in rows:

            if scope == "cancion":
                haystack = title.lower()
            elif scope == "artista":
                haystack = artist.lower()
            else:
                haystack = f"{title} {artist}".lower()

            if query in haystack:
                iid = str(original_idx)

                mark = (
                    "☑"
                    if iid in self.checked_tracks
                    else "☐"
                )

                self.library_tree.insert(
                    "",
                    "end",
                    iid=iid,
                    values=(
                        mark,
                        title,
                        artist,
                    ),
                )

                self.filtered_tracks[iid] = (
                    title,
                    artist,
                )

    def _on_library_tree_click(self, event):
        region = self.library_tree.identify_region(
            event.x,
            event.y,
        )

        if region != "cell":
            return

        row_iid = self.library_tree.identify_row(
            event.y
        )

        if not row_iid:
            return

        self._toggle_check(row_iid)

    def _toggle_check(self, iid):
        if iid in self.checked_tracks:
            self.checked_tracks.discard(iid)
            mark = "☐"
        else:
            self.checked_tracks.add(iid)
            mark = "☑"

        values = self.library_tree.item(
            iid,
            "values",
        )

        self.library_tree.item(
            iid,
            values=(
                mark,
                values[1],
                values[2],
            ),
        )

    def _check_all_visible(self):
        for iid in self.library_tree.get_children():
            self.checked_tracks.add(iid)

            values = self.library_tree.item(
                iid,
                "values",
            )

            self.library_tree.item(
                iid,
                values=(
                    "☑",
                    values[1],
                    values[2],
                ),
            )

    def _uncheck_all(self):
        for iid in self.library_tree.get_children():
            values = self.library_tree.item(
                iid,
                "values",
            )

            self.library_tree.item(
                iid,
                values=(
                    "☐",
                    values[1],
                    values[2],
                ),
            )

        self.checked_tracks = set()

    def _apply_extended(self, query: str) -> str:
        if (
            self.extended_var.get()
            and "extended" not in query.lower()
        ):
            return f"{query} Extended"

        return query

    def _search_selected_in_convertidor(self):
        if not self.checked_tracks:
            messagebox.showwarning(
                "Nada seleccionado",
                "Selecciona primero el check de una o varias canciones de la lista.",
            )
            return

        if len(self.checked_tracks) > 8:
            if not messagebox.askyesno(
                "Confirmar",
                f"Vas a abrir {len(self.checked_tracks)} pestañas de búsqueda, una por canción. ¿Continuar?",
            ):
                return

        queries = []

        # Recorremos en el orden en que aparecen actualmente en la lista
        # respetando el orden/filtro elegido.
        for iid in self.library_tree.get_children():
            if (
                iid in self.checked_tracks
                and iid in self.filtered_tracks
            ):
                title, artist = self.filtered_tracks[iid]

                query = self._apply_extended(
                    f"{artist} - {title}"
                )

                queries.append(query)

                self._log(
                    f"Abriendo búsqueda en el navegador para: '{query}'"
                )

        if not queries:
            messagebox.showwarning(
                "Nada visible seleccionado",
                "Las canciones seleccionadas no están en la vista actual (puede que el filtro las oculte).",
            )
            return

        self._open_search_tabs(queries)

    def _run_convertidor_search(self):
        query = self.search_query_var.get().strip()

        if not query:
            messagebox.showwarning(
                "Falta el texto",
                "Escribe primero el nombre de la canción.",
            )
            return

        query = self._apply_extended(query)

        self._log(
            f"Abriendo búsqueda en el navegador para: '{query}'"
        )

        self._open_search_tabs([query])

    def _open_search_tabs(self, queries):
        """Abre cada búsqueda como una pestaña nueva en el navegador del
        sistema, reutilizando la misma ventana en vez de abrir varias."""

        try:
            core.open_search_tabs(
                queries,
                base_url=self.search_base_url_var.get(),
            )
        except Exception as e:
            messagebox.showerror(
                "No se pudo abrir la búsqueda",
                str(e),
            )

    def _choose_manual_file(self):
        path = filedialog.askopenfilename(
            title="Elige un MP3",
            filetypes=[
                ("MP3", "*.mp3"),
            ],
        )

        if path:
            self.manual_file_var.set(path)

    def _run_manual(self):
        path = self.manual_file_var.get().strip()
        song = self.manual_song_var.get().strip() or None

        if not path:
            messagebox.showwarning(
                "Falta el archivo",
                "Elige primero un archivo MP3.",
            )
            return

        self._run_in_thread(
            core.process_file,
            path,
            song,
        )


def main():
    root = (
        TkinterDnD.Tk()
        if TkinterDnD is not None
        else tk.Tk()
    )

    try:
        style = ttk.Style()

        if "aqua" in style.theme_names():
            style.theme_use("aqua")

    except Exception:
        pass

    app = DJTaggerApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
