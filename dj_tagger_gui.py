#!/usr/bin/env python3
from pathlib import Path
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
from updater import check_for_update, download_update, install_update


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
        self._setup_modern_styles()

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
        self._apply_modern_appearance()
        self._poll_log_queue()
        self._appearance_check()

        # Comprobar actualizaciones en segundo plano para no bloquear la interfaz.
        threading.Thread(
            target=self._check_for_updates,
            daemon=True,
        ).start()

    # ---------- Estilos modernos ----------

    def _setup_modern_styles(self):
        style = ttk.Style(self.root)

        try:
            if "aqua" in style.theme_names():
                style.theme_use("aqua")
        except Exception:
            pass

        style.configure(
            "Modern.TFrame",
            borderwidth=0,
        )

        style.configure(
            "Modern.TLabel",
            font=("Helvetica", 11),
        )

        style.configure(
            "Title.TLabel",
            font=("Helvetica", 18, "bold"),
        )

        style.configure(
            "Subtitle.TLabel",
            font=("Helvetica", 10),
        )

        style.configure(
            "Modern.TButton",
            font=("Helvetica", 10, "bold"),
            padding=(16, 9),
        )

        style.configure(
            "Primary.TButton",
            font=("Helvetica", 10, "bold"),
            padding=(16, 9),
        )

        style.configure(
            "Treeview",
            rowheight=36,
            font=("Helvetica", 10),
            borderwidth=0,
        )

        style.configure(
            "Treeview.Heading",
            font=("Helvetica", 10, "bold"),
            padding=(10, 9),
        )

        style.configure(
            "Modern.TNotebook",
            borderwidth=0,
        )

        style.configure(
            "Modern.TNotebook.Tab",
            padding=(20, 10),
            font=("Helvetica", 10, "bold"),
        )

    def _is_dark_mode(self):
        """Detecta el modo claro/oscuro actual de macOS."""
        try:
            from AppKit import (
                NSAppearance,
                NSApp,
            )

            app = NSApp()
            if app is None:
                return False

            appearance = app.effectiveAppearance()

            if appearance is None:
                return False

            best = appearance.bestMatchFromAppearancesWithNames_(
                [
                    "NSAppearanceNameAqua",
                    "NSAppearanceNameDarkAqua",
                ]
            )

            return str(best) == "NSAppearanceNameDarkAqua"

        except Exception:
            return False

    def _apply_modern_appearance(self):
        dark = self._is_dark_mode()

        if dark:
            bg = "#1C1C1E"
            surface = "#2C2C2E"
            surface_alt = "#242426"
            text = "#F5F5F7"
            secondary = "#A1A1A6"
            border = "#3A3A3C"
            table_bg = "#242426"
            table_selected = "#315F9F"
            header_bg = "#323234"
            drop_bg = "#242426"
            accent = "#0A84FF"
        else:
            bg = "#F5F5F7"
            surface = "#FFFFFF"
            surface_alt = "#FAFAFC"
            text = "#1D1D1F"
            secondary = "#6E6E73"
            border = "#D2D2D7"
            table_bg = "#FFFFFF"
            table_selected = "#DCEBFF"
            header_bg = "#F2F2F7"
            drop_bg = "#FFFFFF"
            accent = "#007AFF"

        # -----------------------------------------------------
        # Root
        # -----------------------------------------------------

        try:
            self.root.configure(bg=bg)
        except Exception:
            pass

        # -----------------------------------------------------
        # Estilos ttk
        # -----------------------------------------------------

        style = ttk.Style(self.root)

        style.configure(
            "Modern.TFrame",
            background=bg,
        )

        style.configure(
            "Card.TFrame",
            background=surface,
        )

        style.configure(
            "Modern.TLabel",
            background=bg,
            foreground=text,
        )

        style.configure(
            "Title.TLabel",
            background=bg,
            foreground=text,
        )

        style.configure(
            "Subtitle.TLabel",
            background=bg,
            foreground=secondary,
        )

        style.configure(
            "Modern.TButton",
            foreground=text,
            padding=(16, 9),
        )

        style.configure(
            "Primary.TButton",
            foreground=text,
            padding=(16, 9),
        )

        style.configure(
            "Treeview",
            background=table_bg,
            fieldbackground=table_bg,
            foreground=text,
            rowheight=36,
        )

        style.configure(
            "Treeview.Heading",
            background=header_bg,
            foreground=text,
        )

        style.map(
            "Treeview",
            background=[
                ("selected", table_selected),
            ],
            foreground=[
                ("selected", text),
            ],
        )

        style.configure(
            "Modern.TNotebook",
            background=bg,
            borderwidth=0,
        )

        style.configure(
            "Modern.TNotebook.Tab",
            background=bg,
            foreground=secondary,
            padding=(20, 10),
        )

        style.map(
            "Modern.TNotebook.Tab",
            background=[
                ("selected", surface),
            ],
            foreground=[
                ("selected", text),
            ],
        )

        # -----------------------------------------------------
        # Recorrer widgets y adaptar los widgets Tk clásicos
        # -----------------------------------------------------

        def update_widget(widget):
            try:
                cls = widget.winfo_class()
            except Exception:
                return

            try:
                if cls in ("Frame", "Labelframe"):
                    widget.configure(
                        background=surface
                        if widget is getattr(self, "drop_frame", None)
                        else bg
                    )

                elif cls == "Label":
                    widget.configure(
                        background=surface
                        if widget is getattr(self, "drop_frame", None)
                        else bg,
                        foreground=text,
                    )

                elif cls == "Canvas":
                    widget.configure(
                        background=surface,
                        highlightbackground=border,
                    )

                elif cls == "Text":
                    widget.configure(
                        background=surface_alt,
                        foreground=text,
                        insertbackground=text,
                    )

                elif cls == "Entry":
                    widget.configure(
                        background=surface,
                        foreground=text,
                        insertbackground=text,
                    )

                elif cls == "Button":
                    widget.configure(
                        background=surface,
                        foreground=text,
                        activebackground=header_bg,
                        activeforeground=text,
                        highlightbackground=border,
                    )

            except Exception:
                pass

            for child in widget.winfo_children():
                update_widget(child)

        update_widget(self.root)

        # -----------------------------------------------------
        # Elementos específicos de la zona Drag & Drop
        # -----------------------------------------------------

        try:
            self.drop_frame.configure(
                background=drop_bg,
                highlightbackground=border,
                highlightcolor=accent,
            )
        except Exception:
            pass

        try:
            self.drop_label.configure(
                background=drop_bg,
                foreground=secondary,
            )
        except Exception:
            pass

        try:
            self.processing_header.configure(
                background=header_bg,
            )

            for child in self.processing_header.winfo_children():
                try:
                    child.configure(
                        background=header_bg,
                        foreground=text,
                    )
                except Exception:
                    pass
        except Exception:
            pass

        # -----------------------------------------------------
        # Guardar el estado para detectar cambios posteriores
        # -----------------------------------------------------

        self._last_dark_mode = dark

    def _appearance_check(self):
        """Actualiza el tema si el usuario cambia el modo de macOS."""
        try:
            current = self._is_dark_mode()

            if current != getattr(self, "_last_dark_mode", None):
                self._apply_modern_appearance()

        except Exception:
            pass

        self.root.after(1500, self._appearance_check)


    # ---------- Construcción de la interfaz ----------

    def _poll_log_queue(self):
        try:
            while True:
                message = self.log_queue.get_nowait()

                self.log_text.configure(state="normal")
                self.log_text.insert("end", str(message))
                self.log_text.see("end")
                self.log_text.configure(state="disabled")

        except queue.Empty:
            pass

        self.root.after(100, self._poll_log_queue)

    def _log(self, message):
        try:
            self.log_queue.put(str(message))
        except Exception:
            pass

    def _run_in_thread(self, target, *args):
        import threading

        thread = threading.Thread(
            target=target,
            args=args,
            daemon=True,
        )
        thread.start()
        return thread

    def _shorten_filename(self, filename, max_length=32):
        filename = str(filename)

        if len(filename) <= max_length:
            return filename

        path = Path(filename)
        suffix = path.suffix

        if suffix and len(suffix) < max_length:
            available = max_length - len(suffix) - 3
            if available < 1:
                return "..." + suffix
            return filename[:available] + "..." + suffix

        return filename[:max_length - 3] + "..."

    def _clear_processing_entries(self):
        entries = getattr(
            self,
            "_processing_entries",
            {},
        )

        for entry in list(entries.values()):
            try:
                entry.destroy()
            except tk.TclError:
                pass

        self._processing_entries = {}

    def _reset_processing_area(self):
        # ----------------------------------------------------
        # Eliminar campos editables.
        # ----------------------------------------------------

        entries = getattr(
            self,
            "_processing_entries",
            {},
        )

        for entry in list(entries.values()):
            try:
                entry.destroy()
            except Exception:
                pass

        self._processing_entries = {}

        # ----------------------------------------------------
        # ELIMINAR BOTONES
        # ----------------------------------------------------

        buttons = getattr(
            self,
            "processing_buttons_frame",
            None,
        )

        if buttons is not None:
            try:
                buttons.destroy()
            except Exception:
                pass

        self.processing_buttons_frame = None
        self.processing_confirm_button = None
        self.processing_cancel_button = None

        # ----------------------------------------------------
        # Vaciar tabla.
        # ----------------------------------------------------

        tree = getattr(
            self,
            "processing_tree",
            None,
        )

        if tree is not None:
            try:
                for item in tree.get_children():
                    tree.delete(item)
            except Exception:
                pass

        # ----------------------------------------------------
        # Ocultar procesamiento.
        # ----------------------------------------------------

        frame = getattr(
            self,
            "processing_frame",
            None,
        )

        if frame is not None:
            try:
                frame.pack_forget()
            except Exception:
                try:
                    frame.place_forget()
                except Exception:
                    pass

        # ----------------------------------------------------
        # VOLVER A LA CAJA INICIAL
        # ----------------------------------------------------

        drop_label = getattr(
            self,
            "drop_label",
            None,
        )

        if drop_label is not None:
            try:
                drop_label.pack(
                    fill="both",
                    expand=True,
                    padx=20,
                    pady=20,
                )
            except Exception:
                pass

        self._processing_paths = {}
        self._processing_results = []
        self._processing_edit = None
        self._processing_total = 0
        self._processing_done = 0

    def _update_processing_row(
        self,
        filepath,
        status,
        error="",
        title="",
        artist="",
    ):
        def update():
            target_item = None

            for item, path in self._processing_paths.items():
                if path == filepath:
                    target_item = item
                    break

            if target_item is None:
                return

            values = (
                self._shorten_filename(
                    Path(filepath).name
                ),
                title,
                artist,
                status,
            )

            self.processing_tree.item(
                target_item,
                values=values,
            )

        self.root.after(0, update)

    def _check_for_updates(self):
        try:
            from updater import check_for_update, download_update, install_update

            def worker():
                try:
                    result = check_for_update()

                    self.root.after(
                        0,
                        lambda r=result: self._on_update_check_done(r),
                    )

                except Exception as exc:
                    self.root.after(
                        0,
                        lambda e=exc: self._log(
                            f"Error comprobando actualizaciones: {e}\n"
                        ),
                    )

            self._run_in_thread(worker)

        except Exception as exc:
            self._log(
                f"Error comprobando actualizaciones: {exc}\n"
            )

    def _on_update_check_done(self, result):
        if not result:
            return

        if result.get("error"):
            self._log(
                f"Error comprobando actualizaciones: "
                f"{result['error']}\n"
            )
            return

        if not result.get("available"):
            return

        latest_version = result.get(
            "latest_version",
            "?",
        )

        current_version = result.get(
            "current_version",
            APP_VERSION,
        )

        download_url = result.get("download_url")

        answer = messagebox.askyesno(
            "Actualización disponible",
            f"Hay una nueva versión de DJ Tagger.\n\n"
            f"Versión actual: {current_version}\n"
            f"Nueva versión: {latest_version}\n\n"
            f"¿Quieres descargarla e instalarla ahora?",
        )

        if not answer:
            return

        if not download_url:
            messagebox.showerror(
                "Error de actualización",
                "No se encontró el archivo de actualización en GitHub.",
            )
            return

        self._log(
            f"Descargando DJ Tagger {latest_version}...\n"
        )

        def update_worker():
            try:
                zip_path = download_update(download_url)

                self.root.after(
                    0,
                    lambda: self._log(
                        "Descarga completada. Instalando actualización...\n"
                    ),
                )

                install_update(zip_path)

                self.root.after(
                    0,
                    lambda: self._log(
                        "Actualización preparada. DJ Tagger se cerrará para completar la instalación...\n",
                    ),
                )
                self.root.after(
                    1000,
                    self.root.destroy,
                )

            except Exception as exc:
                self.root.after(
                    0,
                    lambda e=exc: messagebox.showerror(
                        "Error de actualización",
                        f"No se pudo instalar la actualización.\n\n{e}",
                    ),
                )

        self._run_in_thread(update_worker)

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
            columns=("check", "song", "artist", "type"),
            show="headings",
            yscrollcommand=lib_scroll.set,
            height=10,
            selectmode="none",
        )

        self.library_tree.heading("check", text="✓")
        self.library_tree.heading("type", text="Tipo")
        self.library_tree.heading("song", text="Canción")
        self.library_tree.heading("artist", text="Artista")
        self.library_tree.heading("type", text="Tipo")

        self.library_tree.column(
            "check",
            width=34,
            anchor="center",
            stretch=False,
        )

        self.library_tree.column(
            "type",
            width=90,
            anchor="center",
            stretch=False,
        )

        self.library_tree.column(
            "song",
            width=270,
            anchor="w",
        )

        self.library_tree.column(
            "artist",
            width=190,
            anchor="w",
        )

        self.library_tree.column(
            "type",
            width=100,
            anchor="center",
            stretch=False,
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
        self.tab_rename = tab_rename
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

        # Lista de procesamiento dentro de la pestaña.
        self.processing_frame = ttk.Frame(self.drop_frame)

        self.processing_title = ttk.Label(
            self.processing_frame,
            text="Procesando canciones...",
            font=("Helvetica", 13, "bold"),
        )
        self.processing_title.pack(
            anchor="w",
            padx=12,
            pady=(10, 6),
        )

        # =========================================================
        # TABLA DE RESULTADOS
        # =========================================================

        self.processing_table_outer = ttk.Frame(
            self.processing_frame
        )
        self.processing_table_outer.pack(
            fill="both",
            expand=True,
            padx=10,
            pady=(0, 10),
        )

        # Canvas horizontal: cabecera + contenido se desplazan juntos.
        self.processing_horizontal_canvas = tk.Canvas(
            self.processing_table_outer,
            highlightthickness=0,
            bd=0,
        )

        self.processing_horizontal_canvas.pack(
            side="top",
            fill="both",
            expand=True,
        )

        self.processing_horizontal_inner = ttk.Frame(
            self.processing_horizontal_canvas
        )

        self.processing_horizontal_window = (
            self.processing_horizontal_canvas.create_window(
                (0, 0),
                window=self.processing_horizontal_inner,
                anchor="nw",
            )
        )

        # ---------------------------------------------------------
        # CABECERA REAL
        # ---------------------------------------------------------

        self.processing_header = tk.Frame(
            self.processing_horizontal_inner,
            bg="#e5e5e5",
            height=52,
            bd=1,
            relief="solid",
        )

        self.processing_header.pack(
            fill="x",
            side="top",
        )

        self.processing_header.pack_propagate(False)

        widths = [180, 240, 210, 90]

        for i, width in enumerate(widths):
            self.processing_header.grid_columnconfigure(
                i,
                minsize=width,
                weight=0,
            )

        header_font = (
            "Helvetica",
            10,
            "bold",
        )

        def header(text, row, column, rowspan=1, columnspan=1):
            label = tk.Label(
                self.processing_header,
                text=text,
                bg="#e5e5e5",
                font=header_font,
                relief="solid",
                bd=1,
                anchor="center",
            )
            label.grid(
                row=row,
                column=column,
                rowspan=rowspan,
                columnspan=columnspan,
                sticky="nsew",
            )
            return label

        self.processing_header_archivo = header(
            "Archivo",
            0,
            0,
            rowspan=2,
        )

        self.processing_header_resultado = header(
            "Resultado",
            0,
            1,
            columnspan=2,
        )

        self.processing_header_estado = header(
            "Estado",
            0,
            3,
            rowspan=2,
        )

        self.processing_header_cancion = header(
            "Canción",
            1,
            1,
        )

        self.processing_header_artista = header(
            "Artista",
            1,
            2,
        )

        # ---------------------------------------------------------
        # CUERPO
        # ---------------------------------------------------------

        self.processing_body_frame = ttk.Frame(
            self.processing_horizontal_inner
        )

        self.processing_body_frame.pack(
            fill="both",
            expand=True,
        )

        self.processing_tree = ttk.Treeview(
            self.processing_body_frame,
            columns=(
                "archivo",
                "cancion",
                "artista",
                "estado",
            ),
            show="",
            selectmode="browse",
            height=10,
        )

        for column in (
            "archivo",
            "cancion",
            "artista",
            "estado",
        ):
            self.processing_tree.heading(
                column,
                text="",
            )

        self.processing_tree.column(
            "archivo",
            width=180,
            minwidth=180,
            anchor="w",
            stretch=False,
        )

        self.processing_tree.column(
            "cancion",
            width=240,
            minwidth=200,
            anchor="w",
            stretch=False,
        )

        self.processing_tree.column(
            "artista",
            width=210,
            minwidth=180,
            anchor="w",
            stretch=False,
        )

        self.processing_tree.column(
            "estado",
            width=90,
            minwidth=90,
            anchor="center",
            stretch=False,
        )

        # Scroll vertical.
        self.processing_scrollbar_y = ttk.Scrollbar(
            self.processing_body_frame,
            orient="vertical",
            command=self.processing_tree.yview,
        )

        self.processing_tree.configure(
            yscrollcommand=self.processing_scrollbar_y.set,
        )

        self.processing_tree.pack(
            side="left",
            fill="both",
            expand=True,
        )

        self.processing_scrollbar_y.pack(
            side="right",
            fill="y",
        )

        # ---------------------------------------------------------
        # SCROLL HORIZONTAL REAL
        # ---------------------------------------------------------

        self.processing_scrollbar_x = ttk.Scrollbar(
            self.processing_table_outer,
            orient="horizontal",
            command=self.processing_horizontal_canvas.xview,
        )

        self.processing_scrollbar_x.pack(
            side="bottom",
            fill="x",
        )

        self.processing_horizontal_canvas.configure(
            xscrollcommand=self.processing_scrollbar_x.set,
        )

        # El contenido tiene una anchura fija superior a la ventana
        # cuando sea necesario, por lo que la barra aparece.
        total_width = sum(widths)

        self.processing_horizontal_inner.configure(
            width=total_width
        )

        self.processing_horizontal_canvas.configure(
            scrollregion=(0, 0, total_width, 500)
        )

        # Doble clic para editar Canción / Artista.
        self.processing_tree.bind(
            "<Double-1>",
            self._edit_processing_cell,
        )

        self._processing_paths = {}
        self._processing_results = []
        self._processing_edit = None

        self.processing_frame.pack_forget()

        # Botones de confirmación: fuera de la zona de la tabla,
        # justo entre la tabla y "O elegir MP3...".
        self.processing_buttons_frame = ttk.Frame(tab_rename)

        buttons_inner = ttk.Frame(self.processing_buttons_frame)
        buttons_inner.pack(anchor="center")

        self.processing_confirm_button = ttk.Button(
            buttons_inner,
            style="Primary.TButton",
            text="Confirmar y añadir",
            command=lambda: self._confirm_processing_preview(
                None,
                self._processing_results,
            ),
        )
        self.processing_confirm_button.pack(
            side="left",
            padx=(0, 6),
        )

        self.processing_cancel_button = ttk.Button(
            buttons_inner,
            style="Modern.TButton",
            text="Cancelar",
            command=self._cancel_processing_preview,
        )
        self.processing_cancel_button.pack(
            side="left",
            padx=(6, 0),
        )

        # Ocultos hasta que haya una tabla de resultados.
        self.processing_buttons_frame.pack_forget()

        self.choose_mp3_button = ttk.Button(
            tab_rename,
            style="Primary.TButton",
            text="O elegir MP3...",
            command=self._choose_and_process_mp3s,
        )
        self.choose_mp3_button.pack(pady=(8, 4))

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

    def _on_mp3_drop(self, event):
        try:
            files = self.root.tk.splitlist(event.data)
        except Exception:
            files = [event.data]

        mp3_files = [
            str(filepath)
            for filepath in files
            if str(filepath).lower().endswith(".mp3")
        ]

        if not mp3_files:
            messagebox.showwarning(
                "DJ Tagger",
                "No se han encontrado archivos MP3.",
            )
            return

        self._process_dropped_files(mp3_files)

    def _process_dropped_files(self, files):
        mp3_files = [
            str(filepath)
            for filepath in files
            if str(filepath).lower().endswith(".mp3")
        ]

        if not mp3_files:
            return

        self._show_processing_area(mp3_files)

        self._run_in_thread(
            self._process_files_worker,
            mp3_files,
        )

    def _process_files_worker(
        self,
        files,
    ):
        total = len(files)

        for index, filepath in enumerate(
            files,
            start=1,
        ):
            try:
                result = core.process_file(
                    filepath,
                    preview_only=True,
                )

            except Exception as exc:
                result = {
                    "success": False,
                    "filepath": filepath,
                    "original_filename": os.path.basename(filepath),
                    "error": str(exc),
                }

            self.root.after(
                0,
                lambda r=result, i=index, t=total:
                    self._append_processing_result_row(
                        r,
                        i,
                        t,
                    ),
            )

        # No mostrar botones de confirmación hasta
        # que TODAS las canciones hayan terminado.
        self.root.after(
            100,
            self._finish_processing_preview,
        )


    def _show_processing_area(self, files):
        self.drop_label.pack_forget()

        self.processing_frame.pack(
            fill="both",
            expand=True,
        )

        self.processing_title.configure(
            text=f"0 de {len(files)} canciones procesadas"
        )

        # Limpiar Entries anteriores.
        entries = getattr(
            self,
            "_processing_entries",
            {},
        )

        for entry in list(entries.values()):
            try:
                entry.destroy()
            except Exception:
                pass

        self._processing_entries = {}

        # Limpiar tabla.
        for item in self.processing_tree.get_children():
            self.processing_tree.delete(item)

        self._processing_paths = {}
        self._processing_results = []
        self._processing_total = len(files)
        self._processing_done = 0

        # Crear una fila fija para cada canción.
        for index, filepath in enumerate(files):
            item_id = f"processing_{index}"

            self.processing_tree.insert(
                "",
                "end",
                iid=item_id,
                values=(
                    self._shorten_filename(
                        os.path.basename(filepath)
                    ),
                    "",
                    "",
                    "Procesando...",
                ),
            )

            self._processing_paths[item_id] = filepath

        self.processing_tree.update_idletasks()

        # Todavía no mostrar botones.
        old = getattr(
            self,
            "processing_buttons_frame",
            None,
        )

        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass

        self.processing_buttons_frame = None

    def _scroll_processing_horizontal(self, *args):
        """Mueve horizontalmente el cuerpo y la cabecera al mismo tiempo."""
        self.processing_tree.xview(*args)
        if hasattr(self, "processing_header_canvas"):
            try:
                self.processing_header_canvas.xview(*args)
            except Exception:
                pass

    def _update_processing_header_width(self, event=None):
        """Mantiene la cabecera con el mismo ancho que la tabla."""
        if not hasattr(self, "processing_tree"):
            return
        if not hasattr(self, "processing_header_inner"):
            return

        try:
            total_width = sum(
                self.processing_tree.column(column, "width")
                for column in (
                    "archivo",
                    "cancion",
                    "artista",
                    "estado",
                )
            )

            self.processing_header_canvas.configure(
                scrollregion=(0, 0, total_width, 52)
            )

            self.processing_header_inner.configure(
                width=total_width
            )

            self.processing_header_canvas.itemconfigure(
                self.processing_header_window,
                width=total_width,
            )
        except Exception:
            pass

    def _edit_processing_cell(self, event):
        region = self.processing_tree.identify(
            "region",
            event.x,
            event.y,
        )

        if region != "cell":
            return

        row = self.processing_tree.identify_row(event.y)
        column = self.processing_tree.identify_column(event.x)

        # Solo Canción y Artista son editables.
        if not row or column not in ("#2", "#3"):
            return

        bbox = self.processing_tree.bbox(
            row,
            column,
        )

        if not bbox:
            return

        x, y, width, height = bbox

        values = list(
            self.processing_tree.item(
                row,
                "values",
            )
        )

        column_index = 1 if column == "#2" else 2

        if len(values) <= column_index:
            return

        old_value = values[column_index]

        if self._processing_edit is not None:
            try:
                self._processing_edit.destroy()
            except Exception:
                pass

        entry = tk.Entry(
            self.processing_tree,
            relief="solid",
            bd=1,
            highlightthickness=1,
            font=("Helvetica", 10),
        )

        entry.insert(
            0,
            old_value,
        )

        entry.select_range(
            0,
            "end",
        )

        entry.place(
            x=x,
            y=y,
            width=width,
            height=height,
        )

        self._processing_edit = entry

        def save(event=None):
            new_value = entry.get().strip()

            values[column_index] = new_value

            self.processing_tree.item(
                row,
                values=tuple(values),
            )

            filepath = self._processing_paths.get(row)

            if filepath:
                for result in self._processing_results:
                    if result.get("filepath") == filepath:
                        if column_index == 1:
                            result["title"] = new_value
                        elif column_index == 2:
                            result["artist"] = new_value
                        break

            try:
                entry.destroy()
            except Exception:
                pass

            self._processing_edit = None

        def cancel(event=None):
            try:
                entry.destroy()
            except Exception:
                pass

            self._processing_edit = None

        entry.bind(
            "<Return>",
            save,
        )

        entry.bind(
            "<Escape>",
            cancel,
        )

        entry.bind(
            "<FocusOut>",
            save,
        )

        entry.focus_set()

    def _confirm_processing_preview(
        self,
        event=None,
        results=None,
    ):
        """
        Confirma la previsualización y procesa definitivamente
        todas las canciones válidas.
        """

        source_results = (
            results
            if results is not None
            else getattr(
                self,
                "_processing_results",
                [],
            )
        )

        # Asegurarnos de trabajar con una lista real.
        source_results = list(
            source_results or []
        )

        valid_results = []

        for index, result in enumerate(
            source_results
        ):
            if not isinstance(result, dict):
                continue

            filepath = result.get(
                "filepath",
                "",
            )

            if not filepath:
                continue

            # La fila correspondiente.
            item_id = f"processing_{index}"

            # Recuperar los valores actualmente escritos
            # en los campos editables.
            title_entry = getattr(
                self,
                "_processing_entries",
                {},
            ).get(
                (item_id, "cancion")
            )

            artist_entry = getattr(
                self,
                "_processing_entries",
                {},
            ).get(
                (item_id, "artista")
            )

            if title_entry is not None:
                try:
                    title = title_entry.get().strip()
                except tk.TclError:
                    title = str(
                        result.get("title", "")
                    ).strip()
            else:
                title = str(
                    result.get("title", "")
                ).strip()

            if artist_entry is not None:
                try:
                    artist = artist_entry.get().strip()
                except tk.TclError:
                    artist = str(
                        result.get("artist", "")
                    ).strip()
            else:
                artist = str(
                    result.get("artist", "")
                ).strip()

            if not title or not artist:
                continue

            # Actualizar el propio resultado con los valores
            # definitivos editados por el usuario.
            result["title"] = title
            result["artist"] = artist

            valid_results.append(result)

        if not valid_results:
            messagebox.showwarning(
                "DJ Tagger",
                "No hay canciones válidas para procesar.",
            )
            return

        # Desactivar botones para evitar dobles clics.
        buttons = getattr(
            self,
            "processing_buttons_frame",
            None,
        )

        if buttons is not None:
            for child in buttons.winfo_children():
                try:
                    child.configure(
                        state="disabled"
                    )
                except tk.TclError:
                    pass

        self.processing_title.configure(
            text=(
                f"Procesando 0 de "
                f"{len(valid_results)} canciones..."
            )
        )

        # Procesamiento definitivo en segundo plano.
        self._run_in_thread(
            self._process_confirmed_files_worker,
            valid_results,
        )


    def _cancel_processing_preview(self):
        self._reset_processing_area()

    def _create_processing_editors(
        self,
        item_id,
        title,
        artist,
    ):
        self.processing_tree.update_idletasks()

        def create_editor(column, value):
            bbox = self.processing_tree.bbox(
                item_id,
                column,
            )

            if not bbox:
                self.root.after(
                    30,
                    lambda: self._create_processing_editors(
                        item_id,
                        title,
                        artist,
                    ),
                )
                return

            x, y, width, height = bbox

            entry = tk.Entry(
                self.processing_tree,
                relief="solid",
                bd=1,
                highlightthickness=0,
                font=("Helvetica", 10),
            )

            entry.insert(
                0,
                value,
            )

            entry.place(
                x=x + 1,
                y=y + 1,
                width=max(width - 2, 30),
                height=max(height - 2, 20),
            )

            self._processing_entries[
                (item_id, column)
            ] = entry

            def save(event=None):
                current_title = self._processing_entries.get(
                    (item_id, "cancion")
                )

                current_artist = self._processing_entries.get(
                    (item_id, "artista")
                )

                for result_item in self._processing_results:
                    if result_item.get("filepath") == self._processing_paths.get(item_id):
                        if current_title is not None:
                            result_item["title"] = (
                                current_title.get().strip()
                            )

                        if current_artist is not None:
                            result_item["artist"] = (
                                current_artist.get().strip()
                            )

                        break

            entry.bind(
                "<FocusOut>",
                save,
            )

            entry.bind(
                "<Return>",
                save,
            )

        create_editor(
            "cancion",
            title,
        )

        create_editor(
            "artista",
            artist,
        )


    def _finish_processing_preview(self):
        total = getattr(
            self,
            "_processing_total",
            0,
        )

        done = getattr(
            self,
            "_processing_done",
            0,
        )

        self.processing_title.configure(
            text=(
                f"{done} de {total} "
                f"canciones procesadas"
            )
        )

        self._show_processing_action_buttons()


    def _append_processing_result_row(
        self,
        result,
        index,
        total,
    ):
        filepath = str(
            result.get("filepath", "")
        )

        item_id = f"processing_{index - 1}"

        if not self.processing_tree.exists(item_id):
            return

        self._processing_paths[item_id] = filepath

        success = bool(result.get("success"))

        if success:
            title = str(
                result.get("title", "")
            ).strip()

            artist = str(
                result.get("artist", "")
            ).strip()

            status = "✓"
        else:
            title = ""
            artist = ""

            error = str(
                result.get("error", "")
            ).strip()

            status = "ERROR"

        # Actualizar únicamente ESTA fila.
        self.processing_tree.item(
            item_id,
            values=(
                self._shorten_filename(
                    os.path.basename(filepath)
                ),
                "",
                "",
                status,
            ),
        )

        # Eliminar Entry anteriores de esta fila si existen.
        for key in [
            (item_id, "cancion"),
            (item_id, "artista"),
        ]:
            entry = self._processing_entries.pop(
                key,
                None,
            )

            if entry is not None:
                try:
                    entry.destroy()
                except tk.TclError:
                    pass

        self._processing_results.append(result)

        # Guardamos los valores que se mostrarán en los Entry.
        self._create_processing_editors(
            item_id,
            title,
            artist,
        )

        self._processing_done = index

        self.processing_title.configure(
            text=(
                f"{index} de {total} "
                f"canciones procesadas"
            )
        )

        self.processing_tree.see(item_id)
        self.processing_tree.update_idletasks()


    def _show_processing_preview(self, results):
        """Compatibilidad: prepara la tabla con los resultados ya obtenidos."""

        self._processing_results = list(results or [])

        for item in self.processing_tree.get_children():
            self.processing_tree.delete(item)

        self._processing_paths = {}

        total = len(self._processing_results)

        for index, result in enumerate(
            self._processing_results,
            start=1,
        ):
            self._append_processing_result_row(
                result,
                index,
                total,
            )

        if total:
            self.processing_title.configure(
                text=f"{total} de {total} canciones procesadas"
            )

        self._show_processing_action_buttons()

    def _show_processing_action_buttons(self):
        old_buttons = getattr(
            self,
            "processing_buttons_frame",
            None,
        )

        if old_buttons is not None:
            try:
                old_buttons.destroy()
            except Exception:
                pass

        # Panel situado directamente en la pestaña,
        # fuera de la tabla y de su zona de scroll.
        buttons = ttk.Frame(self.tab_rename)
        self.processing_buttons_frame = buttons

        buttons.pack(
            fill="x",
            padx=10,
            pady=(4, 4),
            before=self.choose_mp3_button,
        )

        buttons_inner = ttk.Frame(buttons)
        buttons_inner.pack(anchor="center")

        # Confirmar
        confirm_button = ttk.Button(
            buttons_inner,
            text="Confirmar y añadir",
            command=lambda: self._confirm_processing_preview(
                None,
                self._processing_results,
            ),
        )
        confirm_button.pack(
            side="left",
            padx=(0, 6),
        )

        # Cancelar
        cancel_button = ttk.Button(
            buttons_inner,
            text="Cancelar",
            command=self._cancel_processing_preview,
        )
        cancel_button.pack(
            side="left",
            padx=(6, 0),
        )

        self.processing_confirm_button = confirm_button
        self.processing_cancel_button = cancel_button

    def _process_confirmed_files_worker(
        self,
        results,
    ):
        """
        Procesa definitivamente los resultados confirmados.

        Utiliza EXACTAMENTE el título y artista que aparecen
        en la previsualización, incluyendo las modificaciones
        realizadas por el usuario.
        """

        results = list(results or [])
        total = len(results)
        done = 0

        for result in results:
            if not isinstance(result, dict):
                continue

            filepath = str(
                result.get("filepath", "")
            ).strip()

            if not filepath:
                continue

            title = str(
                result.get("title", "")
            ).strip()

            artist = str(
                result.get("artist", "")
            ).strip()

            if not title or not artist:
                continue

            # Buscar la fila correspondiente.
            item_id = None

            for iid, path in getattr(
                self,
                "_processing_paths",
                {},
            ).items():
                if str(path) == filepath:
                    item_id = iid
                    break

            # Mostrar que esta canción se está procesando.
            if item_id is not None:
                try:
                    self.root.after(
                        0,
                        lambda iid=item_id, t=title, a=artist:
                            self.processing_tree.item(
                                iid,
                                values=(
                                    self._shorten_filename(
                                        os.path.basename(filepath)
                                    ),
                                    t,
                                    a,
                                    "Procesando...",
                                ),
                            ),
                    )
                except Exception:
                    pass

            try:
                final_result = core.process_edited_file(
                    filepath,
                    title,
                    artist,
                    result,
                )

                done += 1

                final_title = str(
                    final_result.get(
                        "title",
                        title,
                    )
                )

                final_artist = str(
                    final_result.get(
                        "artist",
                        artist,
                    )
                )

                if item_id is not None:
                    self.root.after(
                        0,
                        lambda iid=item_id, t=final_title, a=final_artist:
                            self.processing_tree.item(
                                iid,
                                values=(
                                    self._shorten_filename(
                                        os.path.basename(filepath)
                                    ),
                                    t,
                                    a,
                                    "✓",
                                ),
                            ),
                    )

            except Exception as exc:
                done += 1

                error_text = str(exc)

                if item_id is not None:
                    self.root.after(
                        0,
                        lambda iid=item_id, t=title, a=artist, e=error_text:
                            self.processing_tree.item(
                                iid,
                                values=(
                                    self._shorten_filename(
                                        os.path.basename(filepath)
                                    ),
                                    t,
                                    a,
                                    "ERROR",
                                ),
                            ),
                    )

                self.root.after(
                    0,
                    lambda e=error_text:
                        self._log(
                            f"Error procesando archivo: {e}\n"
                        ),
                )

            # Actualizar contador después de cada canción.
            self.root.after(
                0,
                lambda d=done, t=total:
                    self.processing_title.configure(
                        text=(
                            f"Procesando {d} de {t} "
                            f"canciones..."
                        )
                    ),
            )

        # Terminado TODO el procesamiento.
        self.root.after(
            0,
            self._finish_processing,
        )



    def _finish_processing(self):
        try:
            self.processing_title.configure(
                text="Proceso terminado"
            )
        except Exception:
            pass

        # Quitar botones.
        buttons = getattr(
            self,
            "processing_buttons_frame",
            None,
        )

        if buttons is not None:
            try:
                buttons.destroy()
            except Exception:
                pass

        self.processing_buttons_frame = None
        self.processing_confirm_button = None
        self.processing_cancel_button = None

        # Mostrar "Proceso terminado" durante 3 segundos.
        self.root.after(
            3000,
            self._reset_processing_area,
        )

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
        print("Leyendo tu biblioteca de Apple Music...")

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

        print(f"Biblioteca cargada: {len(tracks)} canciones.")

        self.root.after(
            0,
            lambda: self._on_library_loaded(tracks),
        )

    def _update_library(self):
        self.load_lib_btn.configure(
            state="disabled",
        )

        self.lib_status_var.set(
            "Comprobando cambios en la biblioteca..."
        )

        self.lib_progressbar.configure(mode="indeterminate")
        self.lib_progressbar.start(12)
        self.lib_progress_text_var.set("Comprobando cambios...")

        self._run_in_thread(
            self._update_library_worker
        )

    def _update_library_worker(self):
        print("Comprobando cambios en la biblioteca de Apple Music...")

        try:
            current_ids = core.get_apple_music_database_ids()

            if current_ids is None:
                self.root.after(
                    0,
                    lambda: self._on_library_update_done(
                        None,
                        "No se pudo comprobar tu biblioteca (revisa la ventana de Actividad).",
                    ),
                )
                return

            current_id_set = set(current_ids.keys())

            old_ids = {
                str(track[4])
                for track in self.library_tracks
                if len(track) >= 5 and track[4]
            }

            print(
                f"IDs locales: {len(old_ids)}, "
                f"IDs Apple Music: {len(current_id_set)}"
            )

            # Si por alguna razón la biblioteca actual no tiene IDs,
            # hacemos una carga completa para inicializarla correctamente.
            if not old_ids:
                print(
                    "La biblioteca local no tiene database IDs. "
                    "Realizando sincronización inicial..."
                )

                tracks = core.get_apple_music_library()

                self.root.after(
                    0,
                    lambda: self._on_library_update_done(
                        tracks,
                        None,
                        len(tracks),
                        0,
                    ),
                )
                return

            added_ids = current_id_set - old_ids
            removed_ids = old_ids - current_id_set

            print(
                f"Canciones nuevas: {len(added_ids)} | "
                f"Eliminadas: {len(removed_ids)}"
            )

            # No hay absolutamente ningún cambio.
            if not added_ids and not removed_ids:
                self.root.after(
                    0,
                    lambda: self._on_library_update_done(
                        [],
                        None,
                        0,
                        0,
                    ),
                )
                return

            # Obtener únicamente las canciones nuevas, todas en una sola
            # llamada a AppleScript (mucho más rápido que pedirlas una a
            # una cuando se añaden varias canciones de golpe).
            self.root.after(
                0,
                lambda total=len(added_ids): self._update_library_progress(
                    0, total, indeterminate=True
                ),
            )

            print(
                f"Obteniendo {len(added_ids)} canción(es) nueva(s) "
                f"en una sola consulta..."
            )

            added_tracks = core.get_apple_music_tracks_by_database_ids(
                sorted(added_ids)
            )

            self.root.after(
                0,
                lambda done=len(added_tracks), total=len(added_ids): (
                    self._update_library_progress(done, total)
                ),
            )

            # Mantener las canciones existentes y quitar únicamente
            # las que ya no están en Apple Music.
            removed_ids = {str(x) for x in removed_ids}

            updated_tracks = [
                track
                for track in self.library_tracks
                if len(track) >= 5
                and str(track[4]) not in removed_ids
            ]

            # Añadimos solamente las nuevas.
            updated_tracks.extend(added_tracks)

            self.root.after(
                0,
                lambda tracks=updated_tracks,
                       added=len(added_tracks),
                       removed=len(removed_ids): (
                    self._on_library_update_done(
                        tracks,
                        None,
                        added,
                        removed,
                    )
                ),
            )

        except Exception as exc:
            print(f"Error actualizando biblioteca: {exc}")

            self.root.after(
                0,
                lambda error=str(exc): self._on_library_update_done(
                    None,
                    f"No se pudo actualizar la biblioteca: {error}",
                    0,
                    0,
                ),
            )

    def _on_library_update_done(
        self,
        new_tracks,
        error_message,
        added_count=0,
        removed_count=0,
    ):
        self.load_lib_btn.configure(
            state="normal",
        )

        self.lib_progressbar.stop()
        self.lib_progressbar.configure(mode="determinate")

        if error_message:
            self.lib_status_var.set(
                error_message
            )
            self.lib_progress_text_var.set("")
            return

        # En una actualización incremental recibimos la biblioteca
        # completa ya actualizada. La reemplazamos en lugar de hacer
        # extend(), evitando duplicados.
        if new_tracks is not None:
            self.library_tracks = list(new_tracks)

        local_count = sum(
            1
            for track in self.library_tracks
            if len(track) < 4 or track[3] == "local"
        )

        total_count = len(self.library_tracks)

        if added_count or removed_count:
            changes = []

            if added_count:
                changes.append(
                    f"{added_count} añadida"
                    + ("s" if added_count != 1 else "")
                )

            if removed_count:
                changes.append(
                    f"{removed_count} eliminada"
                    + ("s" if removed_count != 1 else "")
                )

            self.lib_status_var.set(
                f"Biblioteca actualizada: {', '.join(changes)}. "
                f"{total_count} canciones."
            )
        else:
            self.lib_status_var.set(
                f"Sin cambios: {total_count} canciones."
            )

        self.lib_progress_text_var.set("")

        # Volvemos a mostrar la biblioteca actualizada.
        self._apply_library_filter()


    def _update_library_progress(
        self,
        done,
        total,
        indeterminate=False,
    ):
        if indeterminate:
            self.lib_progressbar.configure(mode="indeterminate")
            self.lib_progressbar.start(12)
            self.lib_progress_text_var.set(
                f"Obteniendo {total} canción(es) nueva(s)..."
                if total
                else "Obteniendo canciones nuevas..."
            )
            return

        self.lib_progressbar.stop()
        self.lib_progressbar.configure(mode="determinate")

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
            local_count = sum(
                1
                for track in tracks
                if len(track) >= 4 and track[3] == "local"
            )

            streaming_count = sum(
                1
                for track in tracks
                if len(track) >= 4 and track[3] == "streaming"
            )

            self.lib_status_var.set(
                f"{len(tracks)} canciones cargadas "
                f"({local_count} locales, "
                f"{streaming_count} de streaming)"
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

        for original_idx, track in rows:
            title = track[0]
            artist = track[1]
            date_added = track[2]

            # Compatibilidad con el formato antiguo
            # y con el nuevo formato que incluye el tipo.
            track_type = (
                track[3]
                if len(track) >= 4
                else "local"
            )

            if scope == "cancion":
                haystack = title.lower()

            elif scope == "artista":
                haystack = artist.lower()

            else:
                haystack = f"{title} {artist}".lower()

            if query not in haystack:
                continue

            iid = str(original_idx)

            mark = (
                "☑"
                if iid in self.checked_tracks
                else "☐"
            )

            tipo_texto = (
                "STREAMING"
                if track_type == "streaming"
                else "LOCAL"
            )

            self.library_tree.insert(
                "",
                "end",
                iid=iid,
                values=(
                    mark,
                    title,
                    artist,
                    tipo_texto,
                ),
            )

            self.filtered_tracks[iid] = (
                title,
                artist,
                track_type,
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
                values[3],
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
                    values[3],
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
                "DJ Tagger",
                "Selecciona al menos una canción.",
            )
            return

        queries = []

        for iid in self.checked_tracks:
            track = self.filtered_tracks.get(iid)

            if not track:
                continue

            title = track[0]
            artist = track[1]

            query = f"{title} {artist}".strip()

            if query:
                query = self._apply_extended(query)
                queries.append(query)

        if not queries:
            messagebox.showwarning(
                "DJ Tagger",
                "No hay canciones válidas seleccionadas.",
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

    def _choose_and_process_mp3s(self):
        files = filedialog.askopenfilenames(
            title="Selecciona canciones MP3",
            filetypes=[
                ("Archivos MP3", "*.mp3"),
                ("Todos los archivos", "*.*"),
            ],
        )

        if not files:
            return

        mp3_files = [
            str(filepath)
            for filepath in files
            if str(filepath).lower().endswith(".mp3")
        ]

        if not mp3_files:
            messagebox.showwarning(
                "DJ Tagger",
                "No se han seleccionado archivos MP3.",
            )
            return

        self._show_processing_area(mp3_files)

        self._run_in_thread(
            self._process_files_worker,
            mp3_files,
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
