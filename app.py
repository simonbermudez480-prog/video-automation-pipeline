"""
Interfaz de escritorio de Videos Educativos (Fases 18 y 21).
Permite crear, revisar, publicar y seguir videos sin usar comandos.
Se abre con doble clic en Abrir_Videos_Educativos.bat. Por debajo ejecuta main.py.
Diseño oscuro con CustomTkinter; tokens inspirados en el DESIGN.md de Linear (un solo acento, grises fríos).
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
from tkinter import messagebox

import customtkinter as ctk
from PIL import Image

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from src.config import JOBS_DIR, OUTPUT_DIR, WORK_DIR  # noqa: E402  (respeta WORK_DIR del .env)

QUEUE_DIR = OUTPUT_DIR / "queue"
PLATFORMS = ("youtube", "instagram", "tiktok")
PLATFORM_NAMES = {"youtube": "YouTube", "instagram": "Instagram", "tiktok": "TikTok"}
STEPS = ["Guion", "Voz", "Subtítulos", "Imágenes", "Montaje", "Listo"]
DURATIONS = {"1 min": "1.0", "1,5 min": "1.5", "2 min": "2.0", "2,5 min": "2.5", "3 min": "3.0"}
LOW_DISK_GB = 3.0
MIN_APPROVED_RATIO = 0.8  # por debajo, publicar pide una confirmación reforzada (FR-19.3)
ANSI = re.compile(r"\x1b\[[0-9;]*m")
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

# Tokens de diseño (contraste comprobado: texto 15,7:1, texto secundario 7,7:1, botón principal 7,0:1)
C = {
    "canvas": "#0B0C0E", "sidebar": "#101114", "surface": "#141518", "surface2": "#1B1D21", "surface3": "#22252A",
    "hairline": "#24262B", "hairline2": "#33363D",
    "ink": "#EDEEF0", "muted": "#A3A9B3",
    "accent": "#434EB5", "accent_hover": "#5560C9", "accent_text": "#A1A9FF",
    "ok": "#4ADE80", "warn": "#FBBF24", "error": "#FF8A8A",
    "ok_bg": "#13261A", "warn_bg": "#2A2210", "error_bg": "#2C1517", "accent_bg": "#1C1F3A",
}
FONT = "Segoe UI"
FONT_SEMI = "Segoe UI Semibold"
ICONS_FONT = "Segoe MDL2 Assets"
ICON = {
    "create": "", "review": "", "history": "", "status": "", "play": "",
    "send": "", "copy": "", "refresh": "", "folder": "", "check": "",
    "error": "", "warn": "", "close": "", "link": "", "dot": "",
}

STATUS = {  # estado: (texto, color de texto, fondo de la píldora)
    "passed": ("Listo para publicar", C["ok"], C["ok_bg"]),
    "needs_review": ("No superó el control", C["warn"], C["warn_bg"]),
    "queued": ("En cola", C["accent_text"], C["accent_bg"]),
    "published": ("Publicado", C["ok"], C["ok_bg"]),
    "partial": ("Publicado con errores", C["warn"], C["warn_bg"]),
    "publish_failed": ("Error al publicar", C["error"], C["error_bg"]),
    "discarded": ("Descartado", C["muted"], C["surface2"]),
    "": ("Sin revisar", C["muted"], C["surface2"]),
}


# ---------------------------------------------------------------------------
# Datos: trabajos, cola y estado
# ---------------------------------------------------------------------------

def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def publication_status(publication: dict) -> str:
    """'published' si todas las plataformas salieron, 'partial' si alguna falló, 'publish_failed' si ninguna, '' si no hay datos."""
    states = [i.get("status") == "success" for i in publication.get("platforms", {}).values()]
    if not states:
        return ""
    return "published" if all(states) else ("partial" if any(states) else "publish_failed")


def load_jobs() -> list[dict]:
    """Trabajos producidos (carpetas de jobs con reporte de calidad o publicación), del más nuevo al más viejo."""
    jobs = []
    for d in JOBS_DIR.glob("*/"):
        report = _read_json(d / "quality_report.json")
        publication = _read_json(d / "publication.json")
        if not report and not publication:
            continue
        script = _read_json(d / "script.json")
        title = report.get("title") or script.get("metadata", {}).get("title") or d.name
        title = re.sub(r"\s*\|?\s*#\w+", "", title)
        title = "".join(ch for ch in title if ord(ch) <= 0xFFFF and not 0x2600 <= ord(ch) <= 0x27BF and ord(ch) != 0xFE0F).strip()
        status = report.get("status", "")
        pub_status = publication_status(publication)
        if status != "discarded" and pub_status:
            status = pub_status
        created = report.get("created_at") or datetime.fromtimestamp(d.stat().st_mtime).isoformat(timespec="seconds")
        jobs.append({"dir": d, "title": title, "status": status, "created": created, "report": report, "publication": publication})
    return sorted(jobs, key=lambda j: j["created"], reverse=True)


def _gate_passed(report: dict) -> bool:
    """True si el control de calidad aprobó el video (sin motivos de bloqueo)."""
    return not report.get("reasons") and report.get("status") in ("passed", "published")


def approved_images(job: dict) -> tuple[int, int]:
    """(imágenes aprobadas por la revisión visual, total de escenas) según el manifiesto del trabajo."""
    scenes = _read_json(job["dir"] / "images" / "image_manifest.json").get("scenes", {})
    return sum(1 for e in scenes.values() if e.get("audit") == "approved"), len(scenes)


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
        ("Videos guardados fuera de OneDrive", "onedrive" not in str(WORK_DIR or ROOT).lower(), False,
         "Recomendado: ejecuta 'python mover_carpeta_trabajo.py' para no llenar OneDrive."),
    ]


def free_disk_gb() -> float:
    return shutil.disk_usage(WORK_DIR or ROOT).free / 1024 ** 3


def disk_usage_ratio() -> float:
    usage = shutil.disk_usage(WORK_DIR or ROOT)
    return usage.used / usage.total


def fetch_pollen_balance() -> tuple[float, str]:
    import requests
    from src.config import settings
    key = getattr(settings, "POLLINATIONS_API_KEY", "") or (
        settings.IMAGE_API_KEY if settings.IMAGE_API_KEY and not settings.IMAGE_API_KEY.startswith("tu_clave") else ""
    )
    if not key:
        return -1.0, "Sin clave configurada"
    data = requests.get("https://gen.pollinations.ai/account/balance", headers={"Authorization": f"Bearer {key}"}, timeout=20).json()
    balance = float(data.get("balance", 0))
    paid = data.get("accountBalance", {}).get("paid", 0)
    return balance, f"≈ {int(balance / 0.002)} imágenes" + (f" · pagado {paid}" if paid else " · saldo gratuito")


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


def friendly_error(message: str) -> str:
    """Explica en español los errores frecuentes de publicación."""
    m = (message or "").lower()
    if "first comment requires a paid plan" in m:
        return "Buffer no permite el primer comentario en el plan gratuito. Ya está corregido: reintenta para publicarlo."
    if "could not be read from its url" in m:
        return "Buffer no pudo leer el video. Revisa tu conexión y el espacio en disco, y reintenta."
    if "not_connected" in m or "no conectad" in m:
        return "La cuenta no está conectada en Buffer."
    if "no fue posible alojar" in m:
        return "No se pudo subir el video a internet para Buffer. Revisa la conexión y el token de GitHub, y reintenta."
    if "redactar los textos" in m:
        return "No se pudieron redactar los textos ni publicar. Revisa la conexión y la clave de Gemini, y reintenta."
    if "limit" in m and ("reach" in m or "límite" in m):
        return "Buffer alcanzó el límite de publicaciones del plan gratuito. Espera o libera la cola de Buffer."
    if "unauthorized" in m or "401" in m:
        return "Buffer rechazó el token. Revisa BUFFER_ACCESS_TOKEN en el archivo .env."
    return message or "Error desconocido."


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
# Componentes visuales
# ---------------------------------------------------------------------------

def font(size: int = 13, semibold: bool = False) -> tuple:
    return (FONT_SEMI if semibold else FONT, size)


def card(parent, **kw) -> ctk.CTkFrame:
    return ctk.CTkFrame(parent, fg_color=C["surface"], border_color=C["hairline"], border_width=1, corner_radius=12, **kw)


def pill(parent, status: str) -> ctk.CTkLabel:
    text, color, bg = STATUS.get(status, STATUS[""])
    return ctk.CTkLabel(parent, text=f"  {text}  ", font=font(12, True), text_color=color, fg_color=bg, corner_radius=6, height=24)


def button(parent, text: str, command, kind: str = "secondary", icon: str = "", **kw) -> ctk.CTkButton:
    styles = {
        "primary": dict(fg_color=C["accent"], hover_color=C["accent_hover"], text_color="#FFFFFF", border_width=0),
        "secondary": dict(fg_color=C["surface2"], hover_color=C["surface3"], text_color=C["ink"], border_width=1, border_color=C["hairline2"]),
        "ghost": dict(fg_color="transparent", hover_color=C["surface2"], text_color=C["muted"], border_width=0),
        "danger": dict(fg_color="transparent", hover_color=C["error_bg"], text_color=C["error"], border_width=0),
    }
    label = f"{icon}  {text}" if icon else text
    return ctk.CTkButton(parent, text=label, command=command, corner_radius=8, height=kw.pop("height", 38),
                         font=kw.pop("font", font(13, kind == "primary")), **styles[kind], **kw)


def icon_text(icon: str, text: str) -> str:
    return f"{icon}  {text}"


# ---------------------------------------------------------------------------
# Ventana
# ---------------------------------------------------------------------------

class App(ctk.CTk):
    PAGES = (("create", "Crear video"), ("review", "Revisar y publicar"), ("history", "Historial"), ("status", "Estado"))

    def __init__(self):
        ctk.set_appearance_mode("dark")
        super().__init__(fg_color=C["canvas"])
        self.title("Videos Educativos")
        self.geometry("1280x840")
        self.minsize(1120, 740)
        self.runner = PipelineRunner()
        self.current_task = None  # "create" | "publish" | "queue"
        self.current_page = "create"
        self.selected_review = None
        self.review_jobs: dict[str, dict] = {}
        self._sheet_image = None
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self.main = ctk.CTkFrame(self, fg_color=C["canvas"], corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(0, weight=1)
        self.pages = {
            "create": self._build_create_page(),
            "review": self._build_review_page(),
            "history": self._build_history_page(),
            "status": self._build_status_page(),
        }
        self.show_page("create")
        self.after(200, self._poll_runner)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ---------------- Menú lateral ----------------
    def _build_sidebar(self):
        side = ctk.CTkFrame(self, fg_color=C["sidebar"], corner_radius=0, width=244)
        side.grid(row=0, column=0, sticky="nsw")
        side.grid_propagate(False)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=20, pady=(24, 28))
        ctk.CTkLabel(brand, text="", font=(ICONS_FONT, 18), text_color="#FFFFFF", fg_color=C["accent"],
                     corner_radius=8, width=36, height=36).pack(side="left")
        names = ctk.CTkFrame(brand, fg_color="transparent")
        names.pack(side="left", padx=12)
        ctk.CTkLabel(names, text="Videos Educativos", font=font(15, True), text_color=C["ink"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(names, text="Historia y cultura", font=font(12), text_color=C["muted"], anchor="w").pack(anchor="w")

        self.nav = {}
        for key, label in self.PAGES:
            row = ctk.CTkFrame(side, fg_color="transparent", corner_radius=8, height=42)
            row.pack(fill="x", padx=12, pady=2)
            row.pack_propagate(False)
            indicator = ctk.CTkFrame(row, fg_color="transparent", width=3, corner_radius=2)
            indicator.pack(side="left", fill="y", pady=8)
            btn = ctk.CTkButton(row, text=icon_text(ICON[key], label), anchor="w", command=lambda k=key: self.show_page(k),
                                fg_color="transparent", hover_color=C["surface2"], text_color=C["muted"],
                                font=font(13), corner_radius=8, height=40)
            btn.pack(side="left", fill="both", expand=True, padx=(4, 0))
            badge = ctk.CTkLabel(row, text="", font=font(11, True), text_color="#FFFFFF", fg_color="transparent",
                                 corner_radius=9, width=22, height=18)
            badge.place(relx=1.0, rely=0.5, x=-12, anchor="e")
            self.nav[key] = (row, indicator, btn, badge)

        task = ctk.CTkFrame(side, fg_color=C["surface"], border_color=C["hairline"], border_width=1, corner_radius=10)
        task.pack(side="bottom", fill="x", padx=12, pady=16)
        self.task_label = ctk.CTkLabel(task, text=icon_text(ICON["dot"], "Sin tareas en curso"), font=font(12),
                                       text_color=C["muted"], anchor="w", justify="left", wraplength=190)
        self.task_label.pack(fill="x", padx=12, pady=(10, 6))
        self.task_bar = ctk.CTkProgressBar(task, height=4, corner_radius=2, fg_color=C["surface2"], progress_color=C["accent_text"])
        self.task_bar.set(0)
        self.task_bar.pack(fill="x", padx=12, pady=(0, 12))

    def show_page(self, key: str):
        self.current_page = key
        for k, (row, indicator, btn, _) in self.nav.items():
            active = k == key
            row.configure(fg_color=C["surface2"] if active else "transparent")
            indicator.configure(fg_color=C["accent_text"] if active else "transparent")
            btn.configure(text_color=C["ink"] if active else C["muted"], font=font(13, active),
                          hover_color=C["surface2"] if not active else C["surface3"])
        for k, page in self.pages.items():
            if k == key:
                page.grid(row=0, column=0, sticky="nsew")
            else:
                page.grid_forget()
        {"review": self._refresh_review, "history": self._refresh_history, "status": self._refresh_status}.get(key, lambda: None)()
        self._refresh_badges()

    def _refresh_badges(self):
        jobs = load_jobs()
        pending = sum(1 for j in jobs if j["status"] in ("passed", "needs_review"))
        problems = sum(1 for j in jobs if j["status"] in ("partial", "publish_failed"))
        issues = sum(1 for _, ok, req, _ in run_diagnostics() if req and not ok) + (1 if free_disk_gb() < LOW_DISK_GB else 0)
        for key, count, color in (("review", pending, C["accent"]), ("history", problems, "#9A3B3B"), ("status", issues, "#9A3B3B")):
            badge = self.nav[key][3]
            badge.configure(text=str(count) if count else "", fg_color=color if count else "transparent")

    def _page(self, title: str, subtitle: str) -> tuple[ctk.CTkFrame, ctk.CTkFrame]:
        page = ctk.CTkFrame(self.main, fg_color=C["canvas"], corner_radius=0)
        page.grid_columnconfigure(0, weight=1)
        page.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(page, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=36, pady=(30, 18))
        ctk.CTkLabel(head, text=title, font=font(24, True), text_color=C["ink"], anchor="w").pack(anchor="w")
        ctk.CTkLabel(head, text=subtitle, font=font(13), text_color=C["muted"], anchor="w").pack(anchor="w", pady=(2, 0))
        body = ctk.CTkFrame(page, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=36, pady=(0, 30))
        return page, body

    # ---------------- Crear video ----------------
    def _build_create_page(self):
        page, body = self._page("Crear video", "Escribe un tema y el programa hace el guion, la voz, las imágenes y el montaje.")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)

        form = card(body)
        form.grid(row=0, column=0, sticky="ew")
        ctk.CTkLabel(form, text="Tema del video", font=font(14, True), text_color=C["ink"], anchor="w").pack(anchor="w", padx=24, pady=(22, 8))
        self.topic_entry = ctk.CTkEntry(form, height=48, font=font(15), fg_color=C["surface2"], border_color=C["hairline2"],
                                        border_width=1, corner_radius=8, text_color=C["ink"],
                                        placeholder_text="Ej.: La explosión de Chernóbil (1986)", placeholder_text_color="#7C828C")
        self.topic_entry.pack(fill="x", padx=24)
        self.topic_entry.bind("<Return>", lambda e: self.start_create())
        row = ctk.CTkFrame(form, fg_color="transparent")
        row.pack(fill="x", padx=24, pady=(16, 22))
        ctk.CTkLabel(row, text="Duración", font=font(13), text_color=C["muted"]).pack(side="left", padx=(0, 12))
        self.duration_seg = ctk.CTkSegmentedButton(row, values=list(DURATIONS), font=font(12, True), height=34,
                                                   fg_color=C["surface2"], selected_color=C["accent"],
                                                   selected_hover_color=C["accent_hover"], unselected_color=C["surface2"],
                                                   unselected_hover_color=C["surface3"], text_color=C["ink"], corner_radius=8)
        self.duration_seg.set("2,5 min")
        self.duration_seg.pack(side="left")
        self.create_btn = button(row, "Crear video", self.start_create, "primary", ICON["create"], width=170, height=42)
        self.create_btn.pack(side="right")
        self.cancel_btn = button(row, "Cancelar", self.cancel_task, "ghost", height=42, state="disabled")
        self.cancel_btn.pack(side="right", padx=8)

        prog = card(body)
        prog.grid(row=1, column=0, sticky="nsew", pady=(16, 0))
        top = ctk.CTkFrame(prog, fg_color="transparent")
        top.pack(fill="x", padx=24, pady=(20, 4))
        ctk.CTkLabel(top, text="Progreso", font=font(14, True), text_color=C["ink"]).pack(side="left")
        self.create_status = ctk.CTkLabel(top, text="Sin tareas", font=font(13), text_color=C["muted"])
        self.create_status.pack(side="right")
        steps = ctk.CTkFrame(prog, fg_color="transparent")
        steps.pack(fill="x", padx=24, pady=(14, 10))
        self.step_widgets = []
        for i, name in enumerate(STEPS):
            steps.grid_columnconfigure(i, weight=1)
            cell = ctk.CTkFrame(steps, fg_color=C["surface2"], corner_radius=8, height=56)
            cell.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 6, 0))
            icon = ctk.CTkLabel(cell, text=str(i + 1), font=font(12, True), text_color=C["muted"], width=24, height=24,
                                fg_color=C["surface3"], corner_radius=12)
            icon.pack(side="left", padx=(12, 8), pady=14)
            label = ctk.CTkLabel(cell, text=name, font=font(13), text_color=C["muted"], anchor="w")
            label.pack(side="left")
            self.step_widgets.append((cell, icon, label))
        self.progress = ctk.CTkProgressBar(prog, height=6, corner_radius=3, fg_color=C["surface2"], progress_color=C["accent_text"])
        self.progress.set(0)
        self.progress.pack(fill="x", padx=24, pady=(6, 10))
        self.create_msg = ctk.CTkLabel(prog, text="Tarda unos 15–20 minutos. Puedes usar las otras secciones mientras tanto.",
                                       font=font(13), text_color=C["muted"], anchor="w", justify="left", wraplength=820)
        self.create_msg.pack(fill="x", padx=24)
        self.log_toggle = button(prog, "Ver registro técnico", self._toggle_log, "ghost", height=32)
        self.log_toggle.pack(anchor="w", padx=16, pady=(8, 4))
        self.log = ctk.CTkTextbox(prog, font=("Consolas", 12), fg_color="#0E0F12", text_color="#C9CED6", corner_radius=8,
                                  border_color=C["hairline"], border_width=1, wrap="word")
        self.log.configure(state="disabled")
        self._log_visible = False
        return page

    def _toggle_log(self):
        self._log_visible = not self._log_visible
        if self._log_visible:
            self.log.pack(fill="both", expand=True, padx=24, pady=(0, 20))
            self.log_toggle.configure(text="Ocultar registro técnico")
        else:
            self.log.pack_forget()
            self.log_toggle.configure(text="Ver registro técnico")

    def _set_step(self, index: int, state: str):
        cell, icon, label = self.step_widgets[index]
        if state == "done":
            icon.configure(text=ICON["check"], font=(ICONS_FONT, 11), text_color=C["canvas"], fg_color=C["ok"])
            label.configure(text_color=C["ink"], font=font(13))
            cell.configure(fg_color=C["surface2"])
        elif state == "running":
            icon.configure(text=str(index + 1), font=font(12, True), text_color="#FFFFFF", fg_color=C["accent"])
            label.configure(text_color=C["ink"], font=font(13, True))
            cell.configure(fg_color=C["accent_bg"])
        elif state == "error":
            icon.configure(text=ICON["close"], font=(ICONS_FONT, 10), text_color=C["canvas"], fg_color=C["error"])
            label.configure(text_color=C["error"], font=font(13, True))
            cell.configure(fg_color=C["error_bg"])
        else:
            icon.configure(text=str(index + 1), font=font(12, True), text_color=C["muted"], fg_color=C["surface3"])
            label.configure(text_color=C["muted"], font=font(13))
            cell.configure(fg_color=C["surface2"])

    def _log(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_create(self):
        topic = self.topic_entry.get().strip()
        if not topic:
            self.create_msg.configure(text="Escribe el tema del video antes de crearlo.", text_color=C["warn"])
            self.topic_entry.focus_set()
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso. Espera a que termine o cancélala.")
            return
        if free_disk_gb() < LOW_DISK_GB and not messagebox.askyesno(
                "Poco espacio en disco", f"Quedan {free_disk_gb():.1f} GB libres y un video necesita unos 2 GB temporales. ¿Continuar?"):
            return
        for i in range(len(STEPS)):
            self._set_step(i, "pending")
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")
        self.progress.set(0)
        self._begin_task("create", ["--topic", topic, "--aspect-ratio", "9:16", "--duration-minutes",
                                    DURATIONS[self.duration_seg.get()], "--no-social-pack"])
        self.create_status.configure(text=f"Creando: {topic}", text_color=C["accent_text"])
        self.create_msg.configure(text="Tarda unos 15–20 minutos. Puedes usar las otras secciones mientras tanto.", text_color=C["muted"])

    # ---------------- Revisar y publicar ----------------
    def _build_review_page(self):
        page, body = self._page("Revisar y publicar", "Mira el resultado antes de publicarlo en YouTube, Instagram y TikTok.")
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)
        self.review_list = ctk.CTkScrollableFrame(body, width=330, fg_color=C["surface"], corner_radius=12, border_width=1,
                                                  border_color=C["hairline"], scrollbar_button_color=C["surface3"],
                                                  scrollbar_button_hover_color=C["hairline2"])
        self.review_list.grid(row=0, column=0, sticky="nsw")
        self.review_detail = card(body)
        self.review_detail.grid(row=0, column=1, sticky="nsew", padx=(16, 0))
        return page

    def _refresh_review(self):
        for child in self.review_list.winfo_children():
            child.destroy()
        self.review_jobs = {str(j["dir"]): j for j in load_jobs() if j["status"] in ("passed", "needs_review")}
        if self.selected_review not in self.review_jobs:
            self.selected_review = next(iter(self.review_jobs), None)
        ctk.CTkLabel(self.review_list, text=f"Pendientes · {len(self.review_jobs)}", font=font(12, True),
                     text_color=C["muted"], anchor="w").pack(fill="x", padx=12, pady=(10, 6))
        for key, job in self.review_jobs.items():
            selected = key == self.selected_review
            item = ctk.CTkFrame(self.review_list, fg_color=C["surface2"] if selected else "transparent", corner_radius=10,
                                border_width=1, border_color=C["accent"] if selected else C["surface"])
            item.pack(fill="x", padx=6, pady=3)
            title = ctk.CTkLabel(item, text=job["title"], font=font(13, True), text_color=C["ink"], anchor="w",
                                 justify="left", wraplength=270)
            title.pack(fill="x", padx=14, pady=(12, 6))
            meta = ctk.CTkFrame(item, fg_color="transparent")
            meta.pack(fill="x", padx=14, pady=(0, 12))
            pill(meta, job["status"]).pack(side="left")
            ctk.CTkLabel(meta, text=job["created"].replace("T", "  ")[:17], font=font(12), text_color=C["muted"]).pack(side="right")
            for w in (item, title, meta, *meta.winfo_children()):
                w.bind("<Button-1>", lambda e, k=key: self._select_review(k))
                w.configure(cursor="hand2")
        self._render_review_detail()

    def _select_review(self, key: str):
        self.selected_review = key
        self._refresh_review()

    def _render_review_detail(self):
        for child in self.review_detail.winfo_children():
            child.destroy()
        job = self.review_jobs.get(self.selected_review) if self.selected_review else None
        if not job:
            empty = ctk.CTkFrame(self.review_detail, fg_color="transparent")
            empty.place(relx=0.5, rely=0.45, anchor="center")
            ctk.CTkLabel(empty, text=ICON["check"], font=(ICONS_FONT, 30), text_color=C["ok"], fg_color=C["ok_bg"],
                         width=64, height=64, corner_radius=32).pack()
            ctk.CTkLabel(empty, text="Todo al día", font=font(18, True), text_color=C["ink"]).pack(pady=(14, 4))
            ctk.CTkLabel(empty, text="No hay videos esperando revisión.", font=font(13), text_color=C["muted"]).pack()
            button(empty, "Crear un video", lambda: self.show_page("create"), "primary", ICON["create"]).pack(pady=(16, 0))
            return
        report = job["report"]
        pad = dict(padx=24)
        ctk.CTkLabel(self.review_detail, text=job["title"], font=font(18, True), text_color=C["ink"], anchor="w",
                     justify="left", wraplength=640).pack(fill="x", pady=(22, 10), **pad)
        status_row = ctk.CTkFrame(self.review_detail, fg_color="transparent")
        status_row.pack(fill="x", **pad)
        if _gate_passed(report):
            pill(status_row, "passed").pack(side="left")
            merged = report.get("merged_scenes") or {}
            detail = f"Escenas unidas con la anterior: {', '.join(merged)}" if merged else "Todas las escenas tienen imagen aprobada."
        else:
            pill(status_row, "needs_review").pack(side="left")
            approved, total = approved_images(job)
            failing = ", ".join(str(s) for s in report.get("failing_scenes", []))
            detail = (f"Solo {approved} de {total} imágenes pasaron la revisión visual"
                      + (f" (fallan las escenas {failing})" if failing else "")
                      + ". Usa «Reparar escenas» para buscar imágenes nuevas solo para esas escenas.")
        ctk.CTkLabel(self.review_detail, text=detail, font=font(13), text_color=C["muted"], anchor="w", justify="left",
                     wraplength=500).pack(fill="x", pady=(8, 0), **pad)

        question = (report.get("closing_question") or "").strip()
        if question:
            box = ctk.CTkFrame(self.review_detail, fg_color=C["accent_bg"], corner_radius=10)
            box.pack(fill="x", pady=(16, 0), **pad)
            text = ctk.CTkFrame(box, fg_color="transparent")
            text.pack(side="left", fill="x", expand=True, padx=16, pady=12)
            ctk.CTkLabel(text, text="Comentario para fijar en TikTok y YouTube", font=font(12, True),
                         text_color=C["accent_text"], anchor="w").pack(anchor="w")
            ctk.CTkLabel(text, text=question, font=font(14), text_color=C["ink"], anchor="w", justify="left",
                         wraplength=480).pack(anchor="w", pady=(2, 0))
            button(box, "Copiar", lambda q=question: self._copy_comment(q), "secondary", ICON["copy"], width=110).pack(side="right", padx=14)

        sheet = Path(report.get("contact_sheet", ""))
        if sheet.exists():
            with Image.open(sheet) as im:
                im = im.convert("RGB")
            self.update_idletasks()
            window = self.winfo_width() if self.winfo_width() > 600 else 1280
            available = window - 244 - 36 * 2 - 346 - 16 - 56  # ventana - menú - márgenes - lista - separación - relleno
            width = max(420, min(720, available))
            height = int(im.height * width / im.width)
            self._sheet_image = ctk.CTkImage(light_image=im, dark_image=im, size=(width, height))
            ctk.CTkLabel(self.review_detail, image=self._sheet_image, text="").pack(anchor="w", pady=(16, 6), **pad)
            ctk.CTkLabel(self.review_detail, text="Verde: imagen aprobada · Naranja: se une con la escena anterior · Rojo: problema",
                         font=font(12), text_color=C["muted"], anchor="w").pack(anchor="w", **pad)

        actions = ctk.CTkFrame(self.review_detail, fg_color="transparent")
        actions.pack(fill="x", pady=(18, 6), **pad)
        self.repair_btn = None
        if _gate_passed(report):
            self.publish_btn = button(actions, "Publicar en YouTube, Instagram y TikTok", self._publish_selected, "primary",
                                      ICON["send"], height=42)
        else:
            # Sin control superado, lo recomendado es reparar; publicar queda como opción secundaria
            self.repair_btn = button(actions, "Reparar escenas", self._repair_selected, "primary", height=42)
            self.repair_btn.pack(side="left", padx=(0, 8))
            self.publish_btn = button(actions, "Publicar igualmente", self._publish_selected, "secondary", ICON["send"], height=42)
        self.publish_btn.pack(side="left")
        button(actions, "Ver video", self._play_selected, "secondary", ICON["play"], height=42).pack(side="left", padx=8)
        button(actions, "Descartar", self._discard_selected, "danger", height=42).pack(side="left")
        if self.runner.busy:
            self.publish_btn.configure(state="disabled")
            if self.repair_btn:
                self.repair_btn.configure(state="disabled")
        self.review_msg = ctk.CTkLabel(self.review_detail, text="", font=font(13), text_color=C["muted"], anchor="w",
                                       justify="left", wraplength=640)
        self.review_msg.pack(fill="x", pady=(4, 18), **pad)

    def _selected_job(self):
        return self.review_jobs.get(self.selected_review) if self.selected_review else None

    def _copy_comment(self, question: str):
        self.clipboard_clear()
        self.clipboard_append(question)
        self.review_msg.configure(text="Pregunta copiada. Pégala como comentario y fíjala en TikTok y YouTube.", text_color=C["ok"])

    def _play_selected(self):
        job = self._selected_job()
        video = Path(job["report"].get("video_path", "")) if job else None
        if video and video.exists():
            os.startfile(video)
        else:
            self.review_msg.configure(text="No se encontró el archivo de video de este trabajo.", text_color=C["error"])

    def _publish_selected(self):
        job = self._selected_job()
        if not job:
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso. Espera a que termine.")
            return
        warning = "" if _gate_passed(job["report"]) else "\n\nATENCIÓN: este video NO superó el control de calidad."
        if not messagebox.askyesno("Confirmar publicación",
                                   f"Se publicará AHORA y de forma pública en YouTube, Instagram y TikTok:\n\n«{job['title']}»{warning}\n\n¿Publicar?",
                                   icon="warning"):
            return
        approved, total = approved_images(job)
        if total and approved / total < MIN_APPROVED_RATIO and not messagebox.askyesno(
                "Pocas imágenes aprobadas",
                f"Solo {approved} de {total} imágenes pasaron la revisión visual. Las demás pueden mostrar cosas que no "
                "corresponden a la historia (objetos modernos, texto inventado…).\n\n"
                "Recomendado: pulsa «No» y usa «Reparar escenas».\n\n¿Publicar de todas formas?",
                icon="warning", default="no"):
            return
        self._begin_task("publish", ["--publish-job", str(job["dir"])])
        self.review_msg.configure(text="Publicando… puede tardar unos minutos (se sube el video y se redactan los textos).",
                                  text_color=C["accent_text"])

    def _repair_selected(self):
        job = self._selected_job()
        if not job:
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso. Espera a que termine.")
            return
        approved, total = approved_images(job)
        if not messagebox.askyesno("Reparar escenas",
                                   f"Se buscarán imágenes nuevas solo para las escenas rechazadas ({total - approved} de {total}) "
                                   "y se volverá a montar el video. Tarda unos 5–15 minutos y no publica nada.\n\n¿Reparar?"):
            return
        self._begin_task("repair", ["--repair-job", str(job["dir"])])
        self.review_msg.configure(text="Reparando escenas… al terminar verás la hoja de contacto actualizada.",
                                  text_color=C["accent_text"])

    def _discard_selected(self):
        job = self._selected_job()
        if not job or not messagebox.askyesno("Descartar video", f"¿Descartar «{job['title']}»? No se borra ningún archivo; solo deja de aparecer aquí."):
            return
        report = job["report"]
        report["status"] = "discarded"
        (job["dir"] / "quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        self.selected_review = None
        self._refresh_review()
        self._refresh_badges()

    # ---------------- Historial ----------------
    def _build_history_page(self):
        page, body = self._page("Historial", "Videos producidos y publicados. Pulsa una plataforma para abrir la publicación.")
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(2, weight=1)
        bar = ctk.CTkFrame(body, fg_color="transparent")
        bar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        button(bar, "Actualizar enlaces", self._refresh_links, "secondary", ICON["refresh"]).pack(side="left")
        self.history_msg = ctk.CTkLabel(bar, text="", font=font(13), text_color=C["muted"], anchor="w", justify="left",
                                        wraplength=760)
        self.history_msg.pack(side="left", fill="x", expand=True, padx=14)
        self.history_alert = ctk.CTkFrame(body, fg_color=C["error_bg"], corner_radius=10)
        self.history_list = ctk.CTkScrollableFrame(body, fg_color=C["surface"], corner_radius=12, border_width=1,
                                                   border_color=C["hairline"], scrollbar_button_color=C["surface3"],
                                                   scrollbar_button_hover_color=C["hairline2"])
        self.history_list.grid(row=2, column=0, sticky="nsew")
        return page

    def _refresh_history(self):
        for child in self.history_list.winfo_children():
            child.destroy()
        jobs = load_jobs()
        if not jobs:
            ctk.CTkLabel(self.history_list, text="Todavía no hay videos. Crea el primero en «Crear video».",
                         font=font(14), text_color=C["muted"]).pack(pady=40)
            return
        # Columnas fijas para que fecha, estado y publicaciones queden alineadas en todas las filas
        cols = ((0, 124, 0), (1, 220, 1), (2, 176, 0), (3, 312, 0), (4, 44, 0))

        def grid_cols(frame):
            for col, minsize, weight in cols:
                frame.grid_columnconfigure(col, minsize=minsize, weight=weight)

        head = ctk.CTkFrame(self.history_list, fg_color="transparent")
        head.pack(fill="x", padx=6, pady=(10, 4))
        grid_cols(head)
        for col, text in ((0, "Fecha"), (1, "Video"), (2, "Estado"), (3, "Publicaciones")):
            ctk.CTkLabel(head, text=text, font=font(12, True), text_color=C["muted"], anchor="w").grid(
                row=0, column=col, sticky="w", padx=(12 if col == 0 else 6, 6))
        for job in jobs:
            row = ctk.CTkFrame(self.history_list, fg_color=C["surface2"], corner_radius=10)
            row.pack(fill="x", padx=6, pady=3)
            grid_cols(row)
            ctk.CTkLabel(row, text=job["created"].replace("T", " ")[:16], font=("Consolas", 12), text_color=C["muted"],
                         anchor="w").grid(row=0, column=0, sticky="w", padx=(12, 6), pady=12)
            ctk.CTkLabel(row, text=job["title"], font=font(13, True), text_color=C["ink"], anchor="w", justify="left",
                         wraplength=232).grid(row=0, column=1, sticky="w", padx=6, pady=8)
            pill(row, job["status"]).grid(row=0, column=2, sticky="w", padx=6)
            chips = ctk.CTkFrame(row, fg_color="transparent")
            chips.grid(row=0, column=3, sticky="w", padx=6)
            for p in PLATFORMS:
                info = job["publication"].get("platforms", {}).get(p, {})
                self._platform_chip(chips, job, p, info).pack(side="left", padx=3)
            button(row, "", lambda j=job: self._open_folder(j), "ghost", ICON["folder"], width=36,
                   height=32, font=(ICONS_FONT, 13)).grid(row=0, column=4, padx=(0, 6))

    def _platform_chip(self, parent, job: dict, platform: str, info: dict) -> ctk.CTkButton:
        name = PLATFORM_NAMES[platform]
        status = info.get("status")
        if status == "success":
            text, color, bg = icon_text(ICON["link"] if info.get("link") else ICON["check"], name), C["ok"], C["ok_bg"]
        elif status:
            text, color, bg = icon_text(ICON["warn"], name), C["error"], C["error_bg"]
        else:
            text, color, bg = name, C["muted"], C["surface3"]
        return ctk.CTkButton(parent, text=text, width=96, height=30, corner_radius=6, font=font(12, True),
                             fg_color=bg, hover_color=C["surface3"], text_color=color,
                             command=lambda: self._chip_clicked(job, platform, info))

    def _chip_clicked(self, job: dict, platform: str, info: dict):
        if info.get("link"):
            webbrowser.open(info["link"])
        elif info.get("status") == "success":
            self.history_msg.configure(text="Publicado; el enlace aparece al pulsar «Actualizar enlaces» en unos minutos.", text_color=C["muted"])
        elif info.get("status"):
            self._show_history_alert(job, platform, info)
        else:
            self.history_msg.configure(text=f"Este video no se envió a {PLATFORM_NAMES[platform]}.", text_color=C["muted"])

    def _show_history_alert(self, job: dict, platform: str, info: dict):
        for child in self.history_alert.winfo_children():
            child.destroy()
        self.history_alert.grid(row=1, column=0, sticky="ew", pady=(0, 12))
        text = ctk.CTkFrame(self.history_alert, fg_color="transparent")
        text.pack(side="left", fill="x", expand=True, padx=16, pady=12)
        ctk.CTkLabel(text, text=icon_text(ICON["warn"], f"No se publicó en {PLATFORM_NAMES[platform]}: {job['title']}"),
                     font=font(13, True), text_color=C["error"], anchor="w", justify="left", wraplength=700).pack(anchor="w")
        ctk.CTkLabel(text, text=friendly_error(info.get("message", "")), font=font(13), text_color=C["ink"], anchor="w",
                     justify="left", wraplength=700).pack(anchor="w", pady=(2, 0))
        button(self.history_alert, "", self.history_alert.grid_forget, "ghost", ICON["close"], width=36,
               font=(ICONS_FONT, 12)).pack(side="right", padx=(0, 8))
        button(self.history_alert, f"Reintentar en {PLATFORM_NAMES[platform]}",
               lambda: self._retry_platform(job, platform), "primary", ICON["refresh"]).pack(side="right", padx=8)

    def _retry_platform(self, job: dict, platform: str):
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso.")
            return
        if not messagebox.askyesno("Reintentar publicación",
                                   f"Se publicará AHORA en {PLATFORM_NAMES[platform]}:\n\n«{job['title']}»\n\n¿Continuar?", icon="warning"):
            return
        self.history_alert.grid_forget()
        self.history_msg.configure(text=f"Publicando en {PLATFORM_NAMES[platform]}…", text_color=C["accent_text"])
        self._begin_task("publish", ["--publish-job", str(job["dir"]), "--publish-platforms", platform])

    def _open_folder(self, job: dict):
        video = Path(job["report"].get("video_path", ""))
        os.startfile(video.parent if video.exists() else job["dir"])

    def _refresh_links(self):
        self.history_msg.configure(text="Consultando enlaces en Buffer…", text_color=C["accent_text"])

        def work():
            try:
                found = refresh_links(load_jobs())
                msg, color = f"Enlaces actualizados ({found} nuevos).", C["ok"]
            except Exception as e:
                msg, color = f"No se pudieron consultar los enlaces: {e}", C["error"]
            self.after(0, lambda: (self.history_msg.configure(text=msg, text_color=color), self._refresh_history()))

        threading.Thread(target=work, daemon=True).start()

    # ---------------- Estado ----------------
    def _build_status_page(self):
        page, body = self._page("Estado", "Espacio, saldo de imágenes, claves y cola de publicación.")
        body.grid_columnconfigure((0, 1), weight=1, uniform="cols")
        body.grid_rowconfigure(2, weight=1)

        disk = card(body)
        disk.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ctk.CTkLabel(disk, text="Espacio libre en disco", font=font(13), text_color=C["muted"], anchor="w").pack(anchor="w", padx=22, pady=(18, 0))
        self.disk_value = ctk.CTkLabel(disk, text="—", font=font(28, True), text_color=C["ink"], anchor="w")
        self.disk_value.pack(anchor="w", padx=22)
        self.disk_bar = ctk.CTkProgressBar(disk, height=6, corner_radius=3, fg_color=C["surface2"])
        self.disk_bar.pack(fill="x", padx=22, pady=(8, 6))
        self.disk_note = ctk.CTkLabel(disk, text="", font=font(12), text_color=C["muted"], anchor="w")
        self.disk_note.pack(anchor="w", padx=22, pady=(0, 18))

        pollen = card(body)
        pollen.grid(row=0, column=1, sticky="nsew", padx=(8, 0))
        top = ctk.CTkFrame(pollen, fg_color="transparent")
        top.pack(fill="x", padx=22, pady=(18, 0))
        ctk.CTkLabel(top, text="Saldo de imágenes con IA (Pollinations)", font=font(13), text_color=C["muted"]).pack(side="left")
        button(top, "Consultar", self._refresh_pollen, "secondary", ICON["refresh"], height=30, width=110).pack(side="right")
        self.pollen_value = ctk.CTkLabel(pollen, text="—", font=font(28, True), text_color=C["ink"], anchor="w")
        self.pollen_value.pack(anchor="w", padx=22)
        self.pollen_note = ctk.CTkLabel(pollen, text="Pulsa «Consultar» para ver el saldo.", font=font(12), text_color=C["muted"], anchor="w")
        self.pollen_note.pack(anchor="w", padx=22, pady=(4, 18))

        self.diag_card = card(body)
        self.diag_card.grid(row=1, column=0, columnspan=2, sticky="ew", pady=16)

        queue_card = card(body)
        queue_card.grid(row=2, column=0, columnspan=2, sticky="nsew")
        qtop = ctk.CTkFrame(queue_card, fg_color="transparent")
        qtop.pack(fill="x", padx=22, pady=(18, 4))
        ctk.CTkLabel(qtop, text="Cola de publicación", font=font(14, True), text_color=C["ink"]).pack(side="left")
        self.queue_btn = button(qtop, "Procesar cola ahora", self._process_queue, "primary", ICON["send"])
        self.queue_btn.pack(side="right")
        ctk.CTkLabel(queue_card, text="Videos que esperan cuota de revisión visual. Al procesar la cola se revisan y se publican los que pasan el control.",
                     font=font(12), text_color=C["muted"], anchor="w", justify="left", wraplength=900).pack(anchor="w", padx=22)
        self.queue_rows = ctk.CTkFrame(queue_card, fg_color="transparent")
        self.queue_rows.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        return page

    def _refresh_status(self):
        free = free_disk_gb()
        low = free < LOW_DISK_GB
        self.disk_value.configure(text=f"{free:.1f} GB".replace(".", ","), text_color=C["error"] if low else C["ink"])
        used = disk_usage_ratio()
        self.disk_bar.configure(progress_color=C["error"] if low else (C["warn"] if used > 0.9 else C["accent_text"]))
        self.disk_bar.set(min(1.0, used))
        note = "Poco espacio: libera disco antes de crear más videos." if low else "Suficiente para crear videos."
        self.disk_note.configure(text=f"Disco usado al {used:.0%}".replace("%", " %") + f" · {note}",
                                 text_color=C["error"] if low else C["muted"])

        for child in self.diag_card.winfo_children():
            child.destroy()
        ctk.CTkLabel(self.diag_card, text="Comprobaciones", font=font(14, True), text_color=C["ink"], anchor="w").pack(anchor="w", padx=22, pady=(18, 8))
        grid = ctk.CTkFrame(self.diag_card, fg_color="transparent")
        grid.pack(fill="x", padx=16, pady=(0, 16))
        grid.grid_columnconfigure((0, 1), weight=1, uniform="d")
        for n, (name, ok, required, hint) in enumerate(run_diagnostics()):
            if ok:
                glyph, color, bg = ICON["check"], C["ok"], C["ok_bg"]
            elif required:
                glyph, color, bg = ICON["close"], C["error"], C["error_bg"]
            else:
                glyph, color, bg = ICON["warn"], C["warn"], C["warn_bg"]
            item = ctk.CTkFrame(grid, fg_color=C["surface2"], corner_radius=8)
            item.grid(row=n // 2, column=n % 2, sticky="ew", padx=6, pady=4)
            ctk.CTkLabel(item, text=glyph, font=(ICONS_FONT, 11), text_color=color, fg_color=bg, width=26, height=26,
                         corner_radius=13).pack(side="left", padx=(10, 10), pady=10)
            texts = ctk.CTkFrame(item, fg_color="transparent")
            texts.pack(side="left", fill="x", expand=True, pady=6)
            ctk.CTkLabel(texts, text=name, font=font(13), text_color=C["ink"], anchor="w").pack(anchor="w")
            if not ok:
                ctk.CTkLabel(texts, text=hint, font=font(12), text_color=color, anchor="w", justify="left", wraplength=380).pack(anchor="w")

        for child in self.queue_rows.winfo_children():
            child.destroy()
        entries = load_queue()
        if not entries:
            ctk.CTkLabel(self.queue_rows, text=icon_text(ICON["check"], "La cola está vacía."), font=font(13),
                         text_color=C["muted"], anchor="w").pack(anchor="w", padx=6, pady=6)
        for e in entries:
            row = ctk.CTkFrame(self.queue_rows, fg_color=C["surface2"], corner_radius=8)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=e.get("topic", e["file"].stem), font=font(13, True), text_color=C["ink"], anchor="w").pack(side="left", padx=12, pady=10)
            ctk.CTkLabel(row, text=f"En cola desde {(e.get('queued_at') or '').replace('T', ' ')[:16]} · intentos: {e.get('attempts', 0)}",
                         font=font(12), text_color=C["muted"]).pack(side="right", padx=12)

    def _refresh_pollen(self):
        self.pollen_note.configure(text="Consultando…", text_color=C["accent_text"])

        def work():
            try:
                balance, note = fetch_pollen_balance()
                value = "—" if balance < 0 else f"{balance:.3f} Pollen".replace(".", ",")
                color = C["muted"]
            except Exception as e:
                value, note, color = "—", f"No disponible ({e.__class__.__name__})", C["error"]
            self.after(0, lambda: (self.pollen_value.configure(text=value), self.pollen_note.configure(text=note, text_color=color)))

        threading.Thread(target=work, daemon=True).start()

    def _process_queue(self):
        if not load_queue():
            messagebox.showinfo("Cola vacía", "No hay videos en la cola.")
            return
        if self.runner.busy:
            messagebox.showinfo("Espera un momento", "Ya hay una tarea en curso.")
            return
        if not messagebox.askyesno("Procesar cola", "Los videos de la cola que superen el control de calidad se publicarán AHORA en las 3 cuentas. ¿Continuar?",
                                   icon="warning"):
            return
        self._begin_task("queue", ["--process-queue", "--no-approval"])

    # ---------------- Tareas en segundo plano ----------------
    def _begin_task(self, kind: str, args: list[str]):
        self.current_task = kind
        self.last_error = ""
        self.task_job = Path(args[args.index("--publish-job") + 1]) if "--publish-job" in args else None
        self.runner.start(args)
        self.create_btn.configure(state="disabled")
        self.queue_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        labels = {"create": "Creando video…", "publish": "Publicando…", "queue": "Procesando la cola…", "repair": "Reparando escenas…"}
        self.task_label.configure(text=icon_text(ICON["dot"], labels[kind]), text_color=C["accent_text"])
        self.task_bar.configure(mode="indeterminate")
        self.task_bar.start()

    def _end_task(self, code: int):
        kind, self.current_task = self.current_task, None
        self.create_btn.configure(state="normal")
        self.queue_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")
        self.task_bar.stop()
        self.task_bar.configure(mode="determinate")
        self.task_bar.set(0)
        self.task_label.configure(text=icon_text(ICON["dot"], "Sin tareas en curso"), text_color=C["muted"])
        if kind == "create":
            if code == 0:
                for i in range(len(STEPS)):
                    self._set_step(i, "done")
                self.progress.set(1)
                self.create_status.configure(text="Video listo", text_color=C["ok"])
                self.create_msg.configure(text="El video está listo. Revísalo en «Revisar y publicar».", text_color=C["ok"])
                self.show_page("review")
            else:
                running = [i for i, (cell, _, _) in enumerate(self.step_widgets) if cell.cget("fg_color") == C["accent_bg"]]
                if running:
                    self._set_step(running[0], "error")
                self.create_status.configure(text="Detenido", text_color=C["error"])
                reason = f" Motivo: {self.last_error}" if self.last_error else " Abre el registro técnico para ver el motivo."
                self.create_msg.configure(text="La creación se detuvo." + reason, text_color=C["error"])
        elif kind == "publish":
            ok = code == 0
            publication = _read_json(self.task_job / "publication.json") if self.task_job else {}
            failed = [(PLATFORM_NAMES.get(p, p), i.get("message")) for p, i in publication.get("platforms", {}).items()
                      if i.get("status") != "success"]
            text = ("Publicado. Los enlaces aparecen en «Historial» en unos minutos." if ok
                    else "La publicación tuvo errores. " + (f"{failed[0][0]}: {friendly_error(failed[0][1])}" if failed
                                                             else "Mira el detalle en «Historial»."))
            if publication.get("copy_source") == "plantilla":
                text += " Ojo: la IA no respondió y los textos salieron de la plantilla automática."
            if self.current_page == "review" and hasattr(self, "review_msg") and self.review_msg.winfo_exists():
                self.review_msg.configure(text=text, text_color=C["ok"] if ok else C["error"])
            self.history_msg.configure(text=text, text_color=C["ok"] if ok else C["error"])
            self.show_page(self.current_page)
        elif kind == "repair":
            text = {0: "Reparado: ahora supera el control de calidad. Revísalo y publícalo.",
                    2: "Reparado en parte: sigue sin superar el control. Mira la hoja de contacto antes de decidir."}.get(
                code, f"La reparación se detuvo. {self.last_error or 'Abre el registro técnico en «Crear video» para ver el motivo.'}")
            self.show_page("review")
            if hasattr(self, "review_msg") and self.review_msg.winfo_exists():
                self.review_msg.configure(text=text, text_color=C["ok"] if code == 0 else C["warn"] if code == 2 else C["error"])
        elif kind == "queue":
            self.show_page("status")
        self._refresh_badges()

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
                        self.progress.set(n / len(STEPS))
                        self.create_msg.configure(text=f"Paso {n + 1} de 6: {STEPS[n]}…", text_color=C["muted"])
                if self.current_task in ("create", "repair"):
                    self._log(friendly(value))
                if re.search(r"\| (ERROR|CRITICAL) ", value):  # el último error se muestra si la tarea falla (FR-19.6)
                    self.last_error = friendly(value).split("  ", 1)[-1][:220]
        except queue.Empty:
            pass
        self.after(200, self._poll_runner)

    def cancel_task(self):
        if self.runner.busy and messagebox.askyesno("Cancelar", "¿Detener la tarea en curso?"):
            self.runner.cancel()

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
