"""
Mueve los trabajos y videos pesados fuera de la carpeta del programa (FR-19.2), p. ej. fuera de OneDrive.

Uso:  python mover_carpeta_trabajo.py [destino]
      (por defecto: %USERPROFILE%\\VideosEducativos_trabajo)

Mueve assets/jobs -> <destino>/jobs y output -> <destino>/output, borra los clips temporales de montaje,
corrige las rutas guardadas en los reportes y escribe WORK_DIR en el .env.
"""
import json
import os
import shutil
import sys
from pathlib import Path

from dotenv import dotenv_values

ROOT = Path(__file__).resolve().parent


def _size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) if path.exists() else 0


def _delete(path: Path) -> int:
    freed = _size(path) if path.is_dir() else (path.stat().st_size if path.exists() else 0)
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()
    return freed


def _merge_move(src: Path, dst: Path) -> None:
    """Mueve el contenido de src a dst (si dst ya existe, archivo por archivo)."""
    if not src.exists():
        return
    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return
    for item in src.iterdir():
        target = dst / item.name
        if item.is_dir() and target.is_dir():
            _merge_move(item, target)
        elif not target.exists():
            shutil.move(str(item), str(target))
    shutil.rmtree(src, ignore_errors=True)


def _rewrite_paths(folder: Path, old_new: list[tuple[str, str]]) -> int:
    """Cambia las rutas absolutas viejas por las nuevas en los .json (reportes, cola, publicación)."""
    changed = 0
    for path in folder.rglob("*.json"):
        if path.parent.name == "images" or path.stat().st_size > 2_000_000:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue

        def fix(value):
            if isinstance(value, str):
                for old, new in old_new:
                    if value.lower().startswith(old.lower()):
                        return new + value[len(old):]
                return value
            if isinstance(value, list):
                return [fix(v) for v in value]
            if isinstance(value, dict):
                return {k: fix(v) for k, v in value.items()}
            return value

        fixed = fix(data)
        if fixed != data:
            path.write_text(json.dumps(fixed, ensure_ascii=False, indent=2), encoding="utf-8")
            changed += 1
    return changed


def _set_env(key: str, value: str) -> None:
    env_path = ROOT / ".env"
    lines = env_path.read_text(encoding="utf-8").splitlines() if env_path.exists() else []
    lines = [ln for ln in lines if not ln.strip().startswith(f"{key}=")]
    lines.append(f"{key}={value}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else Path(os.environ["USERPROFILE"]) / "VideosEducativos_trabajo").resolve()
    current = (dotenv_values(ROOT / ".env").get("WORK_DIR") or "").strip()
    if current and Path(current).resolve() != dest:
        print(f"Ya hay una carpeta de trabajo configurada: {current}. Cambia WORK_DIR en .env a mano si quieres otra.")
        return 1
    if "onedrive" in str(dest).lower():
        print(f"El destino {dest} sigue dentro de OneDrive; elige otra carpeta.")
        return 1
    if dest == ROOT or ROOT in dest.parents:
        print("El destino no puede estar dentro de la carpeta del programa.")
        return 1

    freed = 0
    for clips in [*(ROOT / "assets" / "jobs").glob("*/temp"), ROOT / "assets" / "temp"]:
        freed += sum(_delete(f) for f in [*clips.glob("clip_*.mp4"), clips / "overlay_texts.ass"])
    freed += _delete(ROOT / "assets" / "temp" / "video_assets_cdn")  # clon antiguo del repo CDN (hoy se sube por API)
    print(f"Temporales borrados: {freed / 1024 ** 3:.2f} GB")

    dest.mkdir(parents=True, exist_ok=True)
    moves = [(ROOT / "assets" / "jobs", dest / "jobs"), (ROOT / "output", dest / "output"), (ROOT / "assets" / "temp", dest / "temp")]
    for src, dst in moves:
        print(f"Moviendo {src} -> {dst} ...")
        _merge_move(src, dst)

    old_new = [(str(src), str(dst)) for src, dst in moves]
    print(f"Rutas corregidas en {_rewrite_paths(dest, old_new)} archivos .json")
    _set_env("WORK_DIR", str(dest))
    print(f"Listo. WORK_DIR={dest} guardado en .env")
    return 0


if __name__ == "__main__":
    sys.exit(main())
