"""
Interfaz de escritorio de Videos Educativos (Fase 18 / FR-15).
Permite crear, revisar, publicar y seguir videos sin usar comandos.
Se abre con doble clic en Abrir_Videos_Educativos.bat. Por debajo ejecuta main.py.
"""
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import webbrowser
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

from PIL import Image, ImageTk

ROOT = Path(__file__).resolve().parent
JOBS_DIR = ROOT / "assets" / "jobs"
QUEUE_DIR = ROOT / "output" / "queue"
PLATFORMS = ("youtube", "instagram", "tiktok")
PLATFORM_NAMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}
STEPS = ["Guion", "Voz", "Subtítulos", "Imágenes", "Montaje", "Listo"]
LOW_DISK_GB = 3.0

COLORS = {
    "bg": "#F4F6F8", "card": "#FFFFFF", "text": "#1A1A1A", "muted": "#4A5560",
    "primary": "#1F5FBF", "primary_dark": "#174A96", "ok": "#1E7D32", "warn": "#B45309", "error": "#B3261E",
}
ANSI = re.compile(r"\x1b\[[0-9;]*m")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

STATUS_LABELS = {
    "passed": "Listo para publicar", "needs_review": "No superó el control", "queued": "En cola",
    "published": "Publicado", "publish_failed": "Error al publicar", "discarded": "Descartado",
}


# ---------------------------------------------------------------------------
# Datos: trabajos, cola y estado
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def load_jobs() -> list[dict]:
    """Trabajos producidos (carpetas de assets/jobs con reporte de calidad o publicación), del más nuevo al más viejo."""
    jobs = []
    for d in JOBS_DIR.glob("*/"):
        report = _read_json(d / "quality_report.json")
        publication = _read_json(d / "publication.json")
        if not report and not publication:
            continue
        script = _read_json(d / "script.json")
        title = report.get("title") or script.get("metadata", {}).get("title") or d.name
        status = report.get("status", "")
        sent = [i.get("status") == "success" for i in publication.get("platforms", {}).values()]
        if status != "discarded" and sent:
            status = "published" if any(sent) else "publish_failed"
        created = report.get("created_at") or datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds")
        jobs.append({"dir": d, "title": title, "status": status, "created": created, "report": report, "publication": publication})
    return sorted(jobs, key=lambda j: j["created"], reverse=True)


def _gate_passed(report: dict) -> bool:
    """True si el control de calidad aprobó el video (sin motivos de bloqueo)."""
    return not report.get("reasons") and report.get("status") in ("passed", "published")


def load_queue() -> list[dict]:
    return [{"file": p, **_read_json(p)} for p in sorted(QUEUE_DIR.glob("*.json"))]


def run_diagnostics() -> list[tuple[str, bool, bool, str]]:
    """Comprueba lo necesario para funcionar: (nombre, correcto, obligatorio, qué hacer si falta)."""
    from dotenv import dotenv_values
    env_path = ROOT / ".env"
    env = dotenv_values(env_path) if env_path.exists() else {}

    def has(key: str) -> bool:
        value = (env.get(key) or "").strip()
        return bool(value) and not value.startswith("tu_")

    return [
        ("FFmpeg (montaje de video)", bool(shutil.which("ffmpeg")), True, "Vuelve a ejecutar instalar.bat."),
        ("Archivo de claves (.env)", env_path.exists(), True, "Copia el archivo .env en la carpeta del programa."),
        ("Clave de Gemini (guion, voz y revisión)", has("GEMINI_API_KEY"), True, "Falta GEMINI_API_KEY en el archivo .env."),
        ("Token de Buffer (publicar)", has("BUFFER_ACCESS_TOKEN"), True, "Falta BUFFER_ACCESS_TOKEN en el archivo .env."),
        ("Subida del video a GitHub (para Buffer)", has("GITHUB_CDN_TOKEN") or bool(shutil.which("gh")), True,
         "Falta GITHUB_CDN_TOKEN en el archivo .env (ver INSTALACION.md)."),
        ("Clave de Pollinations (imágenes con IA)", has("POLLINATIONS_API_KEY") or has("IMAGE_API_KEY"), False,
         "Opcional: sin ella no se generan imágenes con IA para los huecos."),
        ("Clave de Pexels (fotos de stock)", has("PEXELS_API_KEY"), False, "Opcional: sin ella no se usan fotos de stock."),
    ]


def free_disk_gb() -> float:
    return shutil.disk_usage(ROOT).free / 1024 ** 3


def fetch_pollen_balance() -> str:
    import requests
    from src.config import settings
    key = getattr(settings, "POLLINATIONS_API_KEY", "") or (
        settings.IMAGE_API_KEY if settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave") else ""
    )
    if not key:
        return "sin clave configurada"
    data = requests.get("https://gen.pollinations.ai/account/balance", headers={"Authorization": f"Bearer {key}"}, timeout=20).json()
    paid = data.get("accountBalance", {}).get("paid", 0)
    return f"{data.get('balance', 0):.3f} Pollen (≈{int(data.get('balance', 0) / 0.002)} imágenes)" + (f", pagado {paid}" if paid else "")


def refresh_links(jobs: list[dict]) -> int:
    """Consulta a Buffer los enlaces públicos de las publicaciones que aún no los tienen. Retorna cuántos encontró."""
    import requests
    from src.buffer_publisher import BUFFER_GRAPHQL_ENDPOINT, BufferPublisher
    headers = BufferPublisher().headers
    query = "query P($id: PostId!){ post(input:{id:$id}){ status externalLink } }"
    found = 0
    for job in jobs:
        pub = job["publication"]
        changed = False
        for info in pub.get("platforms", {}).values():
            if info.get("post_id") and not info.get("link"):
                resp = requests.post(BUFFER_GRAPHQL_ENDPOINT, headers=headers, timeout=30,
                                     json={"query": query, "variables": {"id": info["post_id"]}}).json()
                post = (resp.get("data") or {}).get("post") or {}
                info["buffer_status"] = post.get("status")
                if post.get("externalLink"):
                    info["link"] = post["externalLink"]
                    found += 1
                changed = True
        if changed:
            (job["dir"] / "publication.json").write_text(json.dumps(pub, ensure_ascii=False, indent=2), encoding="utf-8")
    return found


# ---------------------------------------------------------------------------
# Ejecución de main.py en segundo plano
# ---------------------------------------------------------------------------

class PipelineRunner:
    """Ejecuta main.py en un proceso aparte y entrega cada línea del registro por una cola."""

    def __init__(self):
        self.proc = None
        self.lines: "queue.Queue[tuple[str, object]]" = queue.Queue()

    @property
    def busy(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def start(self, args: list[str]) -> None:
        env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUNBUFFERED": "1"}
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":  # el proceso hijo necesita salida de texto
            python = python.with_name("python.exe")
        self.proc = subprocess.Popen(
            [str(python), "main.py", *args], cwd=ROOT, env=env, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
            creationflags=NO_WINDOW,
        )
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.proc.stdout:
            self.lines.put(("line", ANSI.sub("", line.rstrip())))
        self.lines.put(("exit", self.proc.wait()))

    def cancel(self) -> None:
        if self.busy:
            self.proc.terminate()


def friendly(line: str) -> str:
    """Convierte una línea del registro técnico en un mensaje corto: 'hora  mensaje'."""
    m = re.match(r"\d{4}-\d{2}-\d{2} (\d{2}:\d{2}:\d{2})\.?\d* \| \w+ +\| [^-]+- (.*)", line)
    return f"{m.group(1)}  {m.group(2)}" if m else line


# ---------------------------------------------------------------------------
# Ventana
# ---------------------------------------------------------------------------

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Videos Educativos")
        self.geometry("1180x800")
        self.minsize(1000, 700)
        self.configure(bg=COLORS["bg"])
        self.runner = PipelineRunner()
        self.current_task = None  # "create" | "publish" | "queue"
        self._photo = None
        self._setup_style()

        header = tk.Frame(self, bg=COLORS["primary"])
        header.pack(fill="x")
        tk.Label(header, text="Videos Educativos", font=("Segoe UI", 18, "bold"), fg="white", bg=COLORS["primary"]).pack(side="left", padx=20, pady=12)
        self.header_status = tk.Label(header, text="", font=("Segoe UI", 11), fg="white", bg=COLORS["primary"])
        self.header_status.pack(side="right", padx=20)

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=12, pady=12)
        self._build_create_tab()
        self._build_review_tab()
        self._build_history_tab()
        self._build_status_tab()
        self.tabs.bind("<<NotebookTabChanged>>", lambda e: self.refresh_all())
        self.refresh_all()
        self.after(200, self._poll_runner)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _setup_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        base = ("Segoe UI", 11)
        s.configure(".", font=base, background=COLORS["bg"], foreground=COLORS["text"])
        s.configure("TNotebook", background=COLORS["bg"], borderwidth=0)
        s.configure("TNotebook.Tab", font=("Segoe UI", 12, "bold"), padding=(18, 8), foreground=COLORS["text"])
        s.map("TNotebook.Tab", background=[("selected", COLORS["card"])], foreground=[("selected", COLORS["primary"])])
        s.configure("Card.TFrame", background=COLORS["card"])
        s.configure("Card.TLabel", background=COLORS["card"], foreground=COLORS["text"])
        s.configure("Muted.TLabel", background=COLORS["card"], foreground=COLORS["muted"])
        s.configure("Title.TLabel", background=COLORS["card"], foreground=COLORS["text"], font=("Segoe UI", 15, "bold"))
        s.configure("Primary.TButton", font=("Segoe UI", 12, "bold"), foreground="white", background=COLORS["primary"], padding=(16, 10))
        s.map("Primary.TButton", background=[("active", COLORS["primary_dark"]), ("disabled", "#9AA5B1")])
        s.configure("TButton", padding=(12, 8))
        s.configure("Horizontal.TProgressbar", background=COLORS["primary"], troughcolor="#E3E8EE", bordercolor="#E3E8EE",
                    lightcolor=COLORS["primary"], darkcolor=COLORS["primary"], thickness=14)
        s.configure("Treeview", font=("Segoe UI", 11), rowheight=30, background=COLORS["card"], fieldbackground=COLORS["card"])
        s.configure("Treeview.Heading", font=("Segoe UI", 11, "bold"))

    def _card(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, style="Card.TFrame", padding=20)
        frame.pack(fill="both", expand=True)
        return frame

    # ---------------- Pestaña 1: Crear video ----------------
    def _build_create_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="1. Crear video")
        card = self._card(tab)
        ttk.Label(card, text="¿Sobre qué tema quieres el video?", style="Title.TLabel").pack(anchor="w")
        ttk.Label(card, text="Escribe el tema con tus palabras, por ejemplo: La explosión de Chernóbil (1986)", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        self.topic_var = tk.StringVar()
        entry = ttk.Entry(card, textvariable=self.topic_var, font=("Segoe UI", 14))
        entry.pack(fill="x", ipady=6)
        entry.bind("<Return>", lambda e: self.start_create())

        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(fill="x", pady=12)
        ttk.Label(row, text="Duración aproximada:", style="Card.TLabel").pack(side="left")
        self.duration_var = tk.StringVar(value="2.5")
        ttk.Spinbox(row, from_=1.0, to=3.0, increment=0.5, textvariable=self.duration_var, width=5, font=("Segoe UI", 12)).pack(side="left", padx=8)
        ttk.Label(row, text="minutos", style="Card.TLabel").pack(side="left")
        self.cancel_btn = ttk.Button(row, text="Cancelar", command=self.cancel_task, state="disabled")
        self.cancel_btn.pack(side="right")
        self.create_btn = ttk.Button(row, text="Crear video", style="Primary.TButton", command=self.start_create)
        self.create_btn.pack(side="right", padx=8)

        steps = ttk.Frame(card, style="Card.TFrame")
        steps.pack(fill="x", pady=(8, 4))
        self.step_labels = []
        for name in STEPS:
            lbl = tk.Label(steps, text=f"○  {name}", font=("Segoe UI", 12), bg=COLORS["card"], fg=COLORS["muted"], padx=10)
            lbl.pack(side="left")
            self.step_labels.append(lbl)
        self.progress = ttk.Progressbar(card, mode="indeterminate")
        self.progress.pack(fill="x", pady=8)
        self.create_msg = ttk.Label(card, text="Tarda unos 15–20 minutos. Puedes seguir usando las otras pestañas mientras tanto.", style="Muted.TLabel")
        self.create_msg.pack(anchor="w")
        self.log = ScrolledText(card, height=14, font=("Consolas", 10), bg="#0F1720", fg="#E6EDF3", insertbackground="white", state="disabled", relief="flat")
        self.log.pack(fill="both", expand=True, pady=(8, 0))

    def _set_step(self, index: int, state: str):
        icons = {"pending": ("○", COLORS["muted"]), "running": ("●", COLORS["primary"]), "done": ("✓", COLORS["ok"]), "error": ("✗", COLORS["error"])}
        icon, color = icons[state]
        self.step_labels[index].configure(text=f"{icon}  {STEPS[index]}", fg=color, font=("Segoe UI", 12, "bold" if state == "running" else "normal"))

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_create(self):
        topic = self.topic_var.get().strip()
        if not topic:
            messagebox.showwarning("Falta el tema", "Escribe el tema del video antes de crearlo.")
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso. Espera a que termine o cancélala.")
            return
        if free_disk_gb() < LOW_DISK_GB:
            if not messagebox.askyesno("Poco espacio en disco", f"Quedan {free_disk_gb():.1f} GB libres. Un video necesita unos 2 GB temporales. ¿Continuar igualmente?"):
                return
        try:
            duration = float(self.duration_var.get().replace(",", "."))
        except ValueError:
            duration = 2.5
        for i in range(len(STEPS)):
            self._set_step(i, "pending")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self._begin_task("create", ["--topic", topic, "--aspect-ratio", "9:16", "--duration-minutes", str(duration), "--no-social-pack"])
        self.create_msg.configure(text=f"Creando: {topic}")

    # ---------------- Pestaña 2: Revisar y publicar ----------------
    def _build_review_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="2. Revisar y publicar")
        card = self._card(tab)
        ttk.Label(card, text="Videos listos para revisar", style="Title.TLabel").pack(anchor="w")
        body = ttk.Frame(card, style="Card.TFrame")
        body.pack(fill="both", expand=True, pady=(8, 0))

        left = ttk.Frame(body, style="Card.TFrame")
        left.pack(side="left", fill="y")
        self.review_list = ttk.Treeview(left, columns=("title", "control"), show="headings", height=14, selectmode="browse")
        self.review_list.heading("title", text="Video")
        self.review_list.heading("control", text="Control de calidad")
        self.review_list.column("title", width=300)
        self.review_list.column("control", width=170)
        self.review_list.pack(fill="y", expand=True)
        self.review_list.bind("<<TreeviewSelect>>", lambda e: self._show_review())

        right = ttk.Frame(body, style="Card.TFrame", padding=(16, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)
        self.review_title = ttk.Label(right, text="Selecciona un video de la lista", style="Title.TLabel", wraplength=560)
        self.review_title.pack(anchor="w")
        self.review_status = tk.Label(right, text="", font=("Segoe UI", 12, "bold"), bg=COLORS["card"], anchor="w", justify="left", wraplength=560)
        self.review_status.pack(anchor="w", pady=(4, 4), fill="x")
        self.review_detail = ttk.Label(right, text="", style="Muted.TLabel", wraplength=560, justify="left")
        self.review_detail.pack(anchor="w")
        self.sheet_label = tk.Label(right, bg=COLORS["card"])
        self.sheet_label.pack(anchor="w", pady=8)
        ttk.Label(right, text="Verde = imagen aprobada · Naranja = se une con la escena anterior · Rojo = problema", style="Muted.TLabel").pack(anchor="w")
        buttons = ttk.Frame(right, style="Card.TFrame")
        buttons.pack(anchor="w", pady=10)
        ttk.Button(buttons, text="▶  Ver video", command=self._play_selected).pack(side="left")
        self.publish_btn = ttk.Button(buttons, text="Publicar en YouTube, Instagram y TikTok", style="Primary.TButton", command=self._publish_selected)
        self.publish_btn.pack(side="left", padx=8)
        ttk.Button(buttons, text="Descartar", command=self._discard_selected).pack(side="left")
        self.publish_msg = ttk.Label(right, text="", style="Muted.TLabel", wraplength=560)
        self.publish_msg.pack(anchor="w")
        self.review_jobs: dict[str, dict] = {}

    def _refresh_review(self):
        selected = self.review_list.selection()
        self.review_list.delete(*self.review_list.get_children())
        self.review_jobs = {}
        for job in load_jobs():
            if job["status"] not in ("passed", "needs_review", "publish_failed"):
                continue
            key = str(job["dir"])
            self.review_jobs[key] = job
            control = "✓ Superado" if _gate_passed(job["report"]) else "⚠ No superado"
            self.review_list.insert("", "end", iid=key, values=(job["title"], control))
        if selected and selected[0] in self.review_jobs:
            self.review_list.selection_set(selected[0])
        elif self.review_jobs:
            self.review_list.selection_set(next(iter(self.review_jobs)))
        else:
            self.review_title.configure(text="No hay videos pendientes de revisión")
            self.review_status.configure(text="")
            self.review_detail.configure(text="Crea uno en la pestaña «1. Crear video».")
            self.sheet_label.configure(image="")
        self._show_review()

    def _selected_job(self):
        sel = self.review_list.selection()
        return self.review_jobs.get(sel[0]) if sel else None

    def _show_review(self):
        job = self._selected_job()
        if not job:
            return
        report = job["report"]
        self.review_title.configure(text=job["title"])
        if _gate_passed(report):
            merged = report.get("merged_scenes") or {}
            text = "✓ Superó el control de calidad"
            detail = f"Escenas unidas con la anterior: {', '.join(merged)}" if merged else "Todas las escenas tienen imagen aprobada."
            color = COLORS["ok"]
        else:
            text = "⚠ No superó el control de calidad. Revísalo con cuidado antes de publicar."
            detail = "\n".join(f"• {r}" for r in report.get("reasons", []))
            color = COLORS["warn"]
        if job["status"] == "publish_failed":
            text, color = "✗ El último intento de publicación falló. Puedes intentarlo de nuevo.", COLORS["error"]
        self.review_status.configure(text=text, fg=color)
        self.review_detail.configure(text=detail)
        sheet = Path(report.get("contact_sheet", ""))
        if sheet.exists():
            with Image.open(sheet) as im:
                im = im.convert("RGB")
                im.thumbnail((620, 340))
                self._photo = ImageTk.PhotoImage(im)
            self.sheet_label.configure(image=self._photo)
        else:
            self.sheet_label.configure(image="")

    def _play_selected(self):
        job = self._selected_job()
        video = Path(job["report"].get("video_path", "")) if job else None
        if video and video.exists():
            os.startfile(video)
        else:
            messagebox.showwarning("Video no encontrado", "No se encontró el archivo de video de este trabajo.")

    def _publish_selected(self):
        job = self._selected_job()
        if not job:
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso. Espera a que termine.")
            return
        warning = ""
        if not _gate_passed(job["report"]):
            warning = "\n\n⚠ ATENCIÓN: este video NO superó el control de calidad."
        if not messagebox.askyesno(
            "Confirmar publicación",
            f"Se publicará AHORA y de forma pública en YouTube, Instagram y TikTok:\n\n«{job['title']}»{warning}\n\n¿Publicar?",
            icon="warning",
        ):
            return
        self.publish_msg.configure(text="Publicando… puede tardar unos minutos (se sube el video y se redactan los textos).", foreground=COLORS["primary"])
        self._begin_task("publish", ["--publish-job", str(job["dir"])])

    def _discard_selected(self):
        job = self._selected_job()
        if not job or not messagebox.askyesno("Descartar video", f"¿Descartar «{job['title']}»? No se borra ningún archivo; solo deja de aparecer aquí."):
            return
        report = job["report"]
        report["status"] = "discarded"
        (job["dir"] / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self._refresh_review()

    # ---------------- Pestaña 3: Historial ----------------
    def _build_history_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="3. Historial")
        card = self._card(tab)
        top = ttk.Frame(card, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Videos producidos y publicados", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Abrir carpeta del video", command=self._open_history_folder).pack(side="right")
        ttk.Button(top, text="Actualizar enlaces", command=self._refresh_links).pack(side="right", padx=8)
        ttk.Label(card, text="Doble clic en YouTube, Instagram o TikTok para abrir la publicación.", style="Muted.TLabel").pack(anchor="w", pady=(2, 8))
        cols = ("date", "title", "status", *PLATFORMS)
        self.history = ttk.Treeview(card, columns=cols, show="headings", selectmode="browse")
        for col, text, width in (("date", "Fecha", 140), ("title", "Video", 380), ("status", "Estado", 170),
                                 ("youtube", "YouTube", 120), ("instagram", "Instagram", 120), ("tiktok", "TikTok", 120)):
            self.history.heading(col, text=text)
            self.history.column(col, width=width, anchor="w" if col in ("title", "status") else "center")
        self.history.pack(fill="both", expand=True)
        self.history.bind("<Double-1>", self._open_history_link)
        self.history_msg = ttk.Label(card, text="", style="Muted.TLabel")
        self.history_msg.pack(anchor="w", pady=(6, 0))
        self.history_jobs: dict[str, dict] = {}

    def _refresh_history(self):
        self.history.delete(*self.history.get_children())
        self.history_jobs = {}
        for job in load_jobs():
            key = str(job["dir"])
            self.history_jobs[key] = job
            links = []
            for p in PLATFORMS:
                info = job["publication"].get("platforms", {}).get(p, {})
                if info.get("link"):
                    links.append("Abrir ↗")
                elif info.get("status") == "success":
                    links.append("Enviado")
                elif info.get("status"):
                    links.append("Error")
                else:
                    links.append("—")
            date = job["created"].replace("T", " ")[:16]
            self.history.insert("", "end", iid=key, values=(date, job["title"], STATUS_LABELS.get(job["status"], "Sin revisar"), *links))

    def _open_history_link(self, event):
        row, col = self.history.identify_row(event.y), self.history.identify_column(event.x)
        if not row:
            return
        index = int(col.replace("#", "")) - 1
        cols = ("date", "title", "status", *PLATFORMS)
        if index < len(cols) and cols[index] in PLATFORMS:
            link = self.history_jobs[row]["publication"].get("platforms", {}).get(cols[index], {}).get("link")
            if link:
                webbrowser.open(link)
            else:
                messagebox.showinfo("Sin enlace", "Todavía no hay enlace. Pulsa «Actualizar enlaces» en unos minutos.")

    def _open_history_folder(self):
        sel = self.history.selection()
        if sel:
            video = Path(self.history_jobs[sel[0]]["report"].get("video_path", ""))
            os.startfile(video.parent if video.exists() else self.history_jobs[sel[0]]["dir"])

    def _refresh_links(self):
        self.history_msg.configure(text="Consultando enlaces en Buffer…")

        def work():
            try:
                found = refresh_links(load_jobs())
                msg = f"Enlaces actualizados ({found} nuevos)."
            except Exception as e:
                msg = f"No se pudieron consultar los enlaces: {e}"
            self.after(0, lambda: (self.history_msg.configure(text=msg), self._refresh_history()))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- Pestaña 4: Cola y estado ----------------
    def _build_status_tab(self):
        tab = ttk.Frame(self.tabs)
        self.tabs.add(tab, text="4. Cola y estado")
        card = self._card(tab)
        ttk.Label(card, text="Estado del sistema", style="Title.TLabel").pack(anchor="w")
        self.disk_label = tk.Label(card, text="", font=("Segoe UI", 12), bg=COLORS["card"], anchor="w")
        self.disk_label.pack(anchor="w", pady=(8, 2))
        row = ttk.Frame(card, style="Card.TFrame")
        row.pack(anchor="w", fill="x")
        self.pollen_label = tk.Label(row, text="Saldo de imágenes IA (Pollinations): —", font=("Segoe UI", 12), bg=COLORS["card"], fg=COLORS["text"])
        self.pollen_label.pack(side="left")
        ttk.Button(row, text="Consultar saldo", command=self._refresh_pollen).pack(side="left", padx=12)
        self.diag_frame = ttk.Frame(card, style="Card.TFrame")
        self.diag_frame.pack(anchor="w", fill="x", pady=(10, 0))

        ttk.Separator(card).pack(fill="x", pady=16)
        top = ttk.Frame(card, style="Card.TFrame")
        top.pack(fill="x")
        ttk.Label(top, text="Cola de publicación", style="Title.TLabel").pack(side="left")
        self.queue_btn = ttk.Button(top, text="Procesar cola ahora", style="Primary.TButton", command=self._process_queue)
        self.queue_btn.pack(side="right")
        ttk.Label(card, text="Videos que esperan a que haya cuota de revisión visual. Al procesar la cola se revisan y se publican los que pasen el control.",
                  style="Muted.TLabel", wraplength=1000).pack(anchor="w", pady=(2, 8))
        self.queue_list = ttk.Treeview(card, columns=("topic", "queued", "attempts"), show="headings", height=8)
        for col, text, width in (("topic", "Video", 600), ("queued", "En cola desde", 200), ("attempts", "Intentos", 100)):
            self.queue_list.heading(col, text=text)
            self.queue_list.column(col, width=width, anchor="w" if col == "topic" else "center")
        self.queue_list.pack(fill="both", expand=True)
        self.queue_msg = ttk.Label(card, text="", style="Muted.TLabel")
        self.queue_msg.pack(anchor="w", pady=(6, 0))

    def _refresh_status(self):
        free = free_disk_gb()
        low = free < LOW_DISK_GB
        self.disk_label.configure(
            text=f"Espacio libre en disco: {free:.1f} GB" + ("  ⚠ Poco espacio: libera disco antes de crear más videos." if low else "  ✓ Suficiente"),
            fg=COLORS["error"] if low else COLORS["ok"],
        )
        for child in self.diag_frame.winfo_children():
            child.destroy()
        for name, ok, required, hint in run_diagnostics():
            icon, color = ("✓", COLORS["ok"]) if ok else (("✗", COLORS["error"]) if required else ("!", COLORS["warn"]))
            text = f"{icon}  {name}" + ("" if ok else f" — {hint}")
            tk.Label(self.diag_frame, text=text, font=("Segoe UI", 11), bg=COLORS["card"], fg=color, anchor="w").pack(anchor="w")
        self.queue_list.delete(*self.queue_list.get_children())
        entries = load_queue()
        for e in entries:
            self.queue_list.insert("", "end", values=(e.get("topic", e["file"].stem), (e.get("queued_at") or "").replace("T", " ")[:16], e.get("attempts", 0)))
        if not self.runner.busy:
            self.queue_msg.configure(text="La cola está vacía." if not entries else f"{len(entries)} video(s) en cola.")

    def _refresh_pollen(self):
        self.pollen_label.configure(text="Saldo de imágenes IA (Pollinations): consultando…")

        def work():
            try:
                text = fetch_pollen_balance()
            except Exception as e:
                text = f"no disponible ({e.__class__.__name__})"
            self.after(0, lambda: self.pollen_label.configure(text=f"Saldo de imágenes IA (Pollinations): {text}"))

        threading.Thread(target=work, daemon=True).start()

    def _process_queue(self):
        if not load_queue():
            messagebox.showinfo("Cola vacía", "No hay videos en la cola.")
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso.")
            return
        if not messagebox.askyesno("Procesar cola", "Los videos de la cola que superen el control de calidad se publicarán AHORA en las 3 cuentas. ¿Continuar?", icon="warning"):
            return
        self.queue_msg.configure(text="Procesando la cola…")
        self._begin_task("queue", ["--process-queue", "--no-approval"])

    # ---------------- Tareas en segundo plano ----------------
    def _begin_task(self, kind: str, args: list[str]):
        self.current_task = kind
        self.runner.start(args)
        self.progress.start(12)
        self.create_btn.configure(state="disabled")
        self.publish_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        labels = {"create": "Creando video…", "publish": "Publicando…", "queue": "Procesando la cola…"}
        self.header_status.configure(text=labels[kind])

    def _end_task(self, code: int):
        kind, self.current_task = self.current_task, None
        self.progress.stop()
        self.create_btn.configure(state="normal")
        self.publish_btn.configure(state="normal")
        self.queue_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.header_status.configure(text="")
        if kind == "create":
            if code == 0:
                for i in range(len(STEPS)):
                    self._set_step(i, "done")
                self.create_msg.configure(text="✓ Video listo. Revísalo en la pestaña «2. Revisar y publicar».")
                self.refresh_all()
                self.tabs.select(1)
            else:
                running = [i for i, lbl in enumerate(self.step_labels) if lbl.cget("text").startswith("●")]
                if running:
                    self._set_step(running[0], "error")
                self.create_msg.configure(text="✗ La creación se detuvo. Mira el registro de abajo para ver el motivo.")
        elif kind == "publish":
            ok = code == 0
            self.publish_msg.configure(
                text="✓ Publicado en las 3 cuentas. Los enlaces aparecerán en «3. Historial» en unos minutos." if ok
                else "✗ La publicación falló. Revisa tu conexión y vuelve a intentarlo.",
                foreground=COLORS["ok"] if ok else COLORS["error"],
            )
            self.refresh_all()
        elif kind == "queue":
            self.refresh_all()
            self.queue_msg.configure(text="Cola procesada." if code == 0 else "Hubo un error al procesar la cola.")

    def _poll_runner(self):
        try:
            while True:
                kind, value = self.runner.lines.get_nowait()
                if kind == "exit":
                    self._end_task(value)
                    continue
                if self.current_task == "create":
                    step = re.search(r"\[PASO (\d)/6\]", value)
                    if step:
                        n = int(step.group(1)) - 1
                        for i in range(n):
                            self._set_step(i, "done")
                        self._set_step(n, "running")
                    self._log(friendly(value))
                elif self.current_task == "publish" and "publicado exitosamente" in value.lower():
                    self.publish_msg.configure(text=friendly(value))
        except queue.Empty:
            pass
        self.after(200, self._poll_runner)

    def cancel_task(self):
        if self.runner.busy and messagebox.askyesno("Cancelar", "¿Detener la tarea en curso?"):
            self.runner.cancel()

    def refresh_all(self):
        self._refresh_review()
        self._refresh_history()
        self._refresh_status()

    def _on_close(self):
        if self.runner.busy and not messagebox.askyesno("Hay una tarea en curso", "Si cierras la ventana se detendrá la tarea en curso. ¿Cerrar igualmente?"):
            return
        self.runner.cancel()
        self.destroy()


if __name__ == "__main__":
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    local_ffmpeg = ROOT / "tools" / "ffmpeg" / "bin"
    if (local_ffmpeg / "ffmpeg.exe").exists():  # FFmpeg instalado por instalar.bat dentro de la carpeta
        os.environ["PATH"] = f"{local_ffmpeg}{os.pathsep}{os.environ['PATH']}"
    App().mainloop()
