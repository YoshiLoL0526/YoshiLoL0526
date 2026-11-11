"""Actualiza las secciones dinámicas del README del perfil de GitHub.

Sin dependencias externas: solo stdlib. Reescribe el contenido entre los
marcadores `<!-- SECCION:START -->` y `<!-- SECCION:END -->`, y solo toca el
archivo si algo cambió (así el workflow no genera commits vacíos).
"""

from __future__ import annotations

import json
import os
import re
import urllib.request
from collections.abc import Callable, Iterable
from pathlib import Path

API = "https://api.github.com"
README = Path(__file__).resolve().parent.parent / "README.md"
USER = os.environ.get("GITHUB_USER") or os.environ["GITHUB_REPOSITORY_OWNER"]
TOKEN = os.environ.get("GITHUB_TOKEN")
MAX_ITEMS = 5

Event = dict
Formatter = Callable[[Event], "str | None"]


# ── GitHub API ────────────────────────────────────────────────────────────────

def gh(path: str) -> list[dict]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": f"{USER}-profile-readme",
    }
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    req = urllib.request.Request(f"{API}{path}", headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.load(resp)


# ── Formateo de eventos ───────────────────────────────────────────────────────

def _repo(e: Event) -> str:
    name = e["repo"]["name"]
    return f"[{name}](https://github.com/{name})"


def _item(e: Event, key: str) -> tuple[int | None, str]:
    """Devuelve (número, url) de un PR o issue, tolerando payloads recortados."""
    p = e["payload"]
    obj = p.get(key) or {}
    num = obj.get("number") or p.get("number")
    kind = "pull" if key == "pull_request" else "issues"
    url = obj.get("html_url") or f"https://github.com/{e['repo']['name']}/{kind}/{num}"
    return num, url


def _pull_request(e: Event) -> str | None:
    p = e["payload"]
    num, url = _item(e, "pull_request")
    if p.get("action") == "opened":
        return f"🎯 Abrió el PR [#{num}]({url}) en {_repo(e)}"
    if p.get("action") == "closed" and (p.get("pull_request") or {}).get("merged"):
        return f"🟣 Fusionó el PR [#{num}]({url}) en {_repo(e)}"
    return None


def _issue(e: Event) -> str | None:
    if e["payload"].get("action") != "opened":
        return None
    num, url = _item(e, "issue")
    return f"🐛 Abrió el issue [#{num}]({url}) en {_repo(e)}"


def _create(e: Event) -> str | None:
    if e["payload"].get("ref_type") != "repository":
        return None
    return f"✨ Creó el repositorio {_repo(e)}"


def _release(e: Event) -> str | None:
    rel = e["payload"].get("release") or {}
    tag = rel.get("tag_name", "nueva versión")
    return f"🚀 Publicó [{tag}]({rel.get('html_url', '#')}) en {_repo(e)}"


FORMATTERS: dict[str, Formatter] = {
    "PushEvent": lambda e: f"🔨 Hizo push a {_repo(e)}",
    "PullRequestEvent": _pull_request,
    "IssuesEvent": _issue,
    "CreateEvent": _create,
    "ReleaseEvent": _release,
}


def unique(lines: Iterable[str | None]) -> list[str]:
    """Filtra vacíos y duplicados preservando el orden (dict mantiene inserción)."""
    return list(dict.fromkeys(line for line in lines if line))


# ── Secciones ────────────────────────────────────────────────────────────────

def recent_activity() -> list[str]:
    events = gh(f"/users/{USER}/events/public?per_page=100")
    lines = unique(
        (fmt(e) if (fmt := FORMATTERS.get(e["type"])) else None) for e in events
    )
    return [f"- {line}" for line in lines[:MAX_ITEMS]]


def active_repos() -> list[str]:
    repos = gh(f"/users/{USER}/repos?sort=pushed&per_page=30")
    picks = (
        r for r in repos
        if not r["fork"] and not r["archived"] and r["name"].lower() != USER.lower()
    )
    lines = []
    for r in list(picks)[:MAX_ITEMS]:
        meta = " · ".join(filter(None, [r.get("language"), f"⭐ {r['stargazers_count']}"]))
        desc = f" — {r['description']}" if r.get("description") else ""
        lines.append(f"- **[{r['name']}]({r['html_url']})** `{meta}`{desc}")
    return lines


SECTIONS: dict[str, Callable[[], list[str]]] = {
    "REPOS": active_repos,
    "ACTIVITY": recent_activity,
}


# ── Inyección en el README ────────────────────────────────────────────────────

def inject(text: str, section: str, lines: list[str]) -> str:
    pattern = re.compile(rf"(<!-- {section}:START -->).*?(<!-- {section}:END -->)", re.S)
    body = "\n".join(lines) or "_Nada por aquí todavía._"
    new, count = pattern.subn(lambda m: f"{m[1]}\n{body}\n{m[2]}", text)
    if not count:
        raise SystemExit(f"❌ No se encontró el marcador {section} en {README.name}")
    return new


def main() -> None:
    original = README.read_text(encoding="utf-8")
    updated = original
    for section, build in SECTIONS.items():
        updated = inject(updated, section, build())

    if updated == original:
        print("Sin cambios.")
        return
    README.write_text(updated, encoding="utf-8")
    print("README actualizado.")


if __name__ == "__main__":
    main()
