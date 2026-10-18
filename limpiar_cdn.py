"""
Mantiene pequeño el repo de alojamiento de videos para Buffer (FR-19.12).

Uso:  python limpiar_cdn.py [días]            -> solo muestra qué haría (por defecto 14 días)
      python limpiar_cdn.py [días] --aplicar  -> lo hace

Borrar archivos con commits normales no reduce el repo (siguen en el historial). Por eso la rama main se
rehace con un único commit sin historial que conserva solo los videos subidos en los últimos N días; GitHub
elimina después los videos viejos. Sus enlaces dejan de funcionar, pero Buffer ya los descargó al publicar.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

import requests
from dotenv import load_dotenv

load_dotenv()
REPO = os.getenv("GITHUB_CDN_REPO", "") or "simonbermudez480-prog/video-assets"
API = f"https://api.github.com/repos/{REPO}"
HEADERS = {"Authorization": f"Bearer {os.getenv('GITHUB_CDN_TOKEN', '')}", "Accept": "application/vnd.github+json",
           "X-GitHub-Api-Version": "2022-11-28"}
README = "# video-assets\n\nAlojamiento temporal de videos para Buffer. Solo se conservan los de las últimas semanas.\n"


def _get(endpoint: str, **params):
    resp = requests.get(f"{API}{endpoint}", headers=HEADERS, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def _post(path: str, payload: dict, method: str = "POST"):
    resp = requests.request(method, f"{API}{path}", headers=HEADERS, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()


def uploaded_at(name: str) -> datetime:
    """Fecha del último commit que tocó el archivo."""
    commit = _get("/commits", path=name, per_page=1)[0]
    return datetime.fromisoformat(commit["commit"]["committer"]["date"].replace("Z", "+00:00"))


def main() -> int:
    args = [a for a in sys.argv[1:] if a != "--aplicar"]
    days = int(args[0]) if args else 14
    apply = "--aplicar" in sys.argv
    if not os.getenv("GITHUB_CDN_TOKEN"):
        print("Falta GITHUB_CDN_TOKEN en el archivo .env.")
        return 1

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    videos = [f for f in _get("/contents/") if f["type"] == "file" and f["name"].endswith(".mp4")]
    keep, drop = [], []
    for f in videos:
        (keep if uploaded_at(f["name"]) >= cutoff else drop).append(f)
    size = _get("").get("size", 0) / 1024
    print(f"Repo {REPO}: {size:.0f} MB, {len(videos)} videos. Se conservan {len(keep)} (últimos {days} días) "
          f"y se quitan {len(drop)} ({sum(f['size'] for f in drop) / 1e6:.0f} MB).")
    if not drop:
        print("No hay nada que limpiar.")
        return 0
    if not apply:
        print("Simulación: no se cambió nada. Ejecuta con --aplicar para hacerlo.")
        return 0

    readme = _post("/git/blobs", {"content": README, "encoding": "utf-8"})["sha"]
    tree = [{"path": "README.md", "mode": "100644", "type": "blob", "sha": readme}]
    tree += [{"path": f["name"], "mode": "100644", "type": "blob", "sha": f["sha"]} for f in keep]
    tree_sha = _post("/git/trees", {"tree": tree})["sha"]
    commit = _post("/git/commits", {"message": f"Limpieza: solo videos de los últimos {days} días", "tree": tree_sha, "parents": []})
    _post("/git/refs/heads/main", {"sha": commit["sha"], "force": True}, method="PATCH")
    print(f"Listo: main tiene ahora {len(keep)} videos. GitHub liberará el espacio de los antiguos en los próximos días.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
