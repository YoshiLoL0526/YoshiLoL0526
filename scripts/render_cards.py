"""Genera las tarjetas SVG de estadísticas y lenguajes del perfil.

Sustituye a github-readme-stats (cuyo servicio público dejó de funcionar):
consulta la API GraphQL de GitHub y escribe, en el directorio indicado,
una versión clara y otra oscura de cada tarjeta. El workflow las publica en
la rama `output` junto con la serpiente de contribuciones.

Sin dependencias externas: solo stdlib.

Uso: python scripts/render_cards.py [directorio_salida]   (por defecto: dist)
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

USER = os.environ.get("GITHUB_USER") or os.environ["GITHUB_REPOSITORY_OWNER"]
TOKEN = os.environ["GITHUB_TOKEN"]  # GraphQL exige autenticación
TOP_LANGS = 6
WIDTH, HEIGHT = 420, 180
FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"

QUERY = """
query($login: String!) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection { contributionCalendar { totalContributions } }
    repositories(ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false, first: 100) {
      totalCount
      nodes {
        name
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Theme:
    bg: str
    border: str
    title: str
    text: str
    muted: str
    accent: str
    track: str


THEMES = {
    "": Theme("#ffffff", "#d0d7de", "#0f6e74", "#1f2328", "#59636e", "#2c9c9a", "#eaeef2"),
    "-dark": Theme("#0f2027", "#203a43", "#4fd1c5", "#e6edf3", "#8b9ba5", "#4fd1c5", "#203a43"),
}


# ── Datos ─────────────────────────────────────────────────────────────────────

def fetch() -> dict:
    body = json.dumps({"query": QUERY, "variables": {"login": USER}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": f"{USER}-profile-readme",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise SystemExit(f"❌ GraphQL: {data['errors']}")
    return data["data"]["user"]


def stats(user: dict) -> list[tuple[str, int]]:
    repos = user["repositories"]
    return [
        ("Estrellas recibidas", sum(r["stargazerCount"] for r in repos["nodes"])),
        ("Contribuciones (12 meses)",
         user["contributionsCollection"]["contributionCalendar"]["totalContributions"]),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Issues", user["issues"]["totalCount"]),
        ("Repos públicos", repos["totalCount"]),
    ]


def languages(user: dict) -> list[tuple[str, str, float]]:
    """(nombre, color, porcentaje) de los lenguajes más usados por bytes."""
    sizes: Counter[str] = Counter()
    colors: dict[str, str] = {}
    for repo in user["repositories"]["nodes"]:
        if repo["name"].lower() == USER.lower():  # el repo del perfil no cuenta
            continue
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] += edge["size"]
            colors[name] = edge["node"]["color"] or "#8b949e"
    total = sum(sizes.values()) or 1
    return [(n, colors[n], s * 100 / total) for n, s in sizes.most_common(TOP_LANGS)]


# ── SVG ───────────────────────────────────────────────────────────────────────

def card(title: str, body: str, t: Theme) -> str:
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label="{escape(title)}">
  <title>{escape(title)}</title>
  <style>
    text {{ font-family: {FONT}; }}
    .title {{ font-size: 17px; font-weight: 600; fill: {t.title}; }}
    .label {{ font-size: 13.5px; fill: {t.muted}; }}
    .value {{ font-size: 14px; font-weight: 600; fill: {t.text}; }}
    .fade {{ opacity: 0; animation: fade .5s ease-out forwards; }}
    @keyframes fade {{ to {{ opacity: 1; }} }}
    @media (prefers-reduced-motion: reduce) {{ .fade {{ animation: none; opacity: 1; }} }}
  </style>
  <rect x="0.5" y="0.5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="10" fill="{t.bg}" stroke="{t.border}"/>
  <text x="24" y="36" class="title">{escape(title)}</text>
{body}
</svg>
"""


def stats_card(rows: list[tuple[str, int]], t: Theme) -> str:
    lines = []
    for i, (label, value) in enumerate(rows):
        y = 66 + i * 24
        lines.append(
            f'  <g class="fade" style="animation-delay:{i * 80}ms">'
            f'<circle cx="28" cy="{y - 4.5}" r="3.5" fill="{t.accent}"/>'
            f'<text x="42" y="{y}" class="label">{escape(label)}</text>'
            f'<text x="{WIDTH - 24}" y="{y}" class="value" text-anchor="end">{value:,}</text></g>'
        )
    return card("Estadísticas de GitHub", "\n".join(lines), t)


def langs_card(langs: list[tuple[str, str, float]], t: Theme) -> str:
    bar_x, bar_y, bar_w, bar_h = 24, 54, WIDTH - 48, 10
    parts = [
        f'  <clipPath id="bar"><rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5"/></clipPath>',
        f'  <rect x="{bar_x}" y="{bar_y}" width="{bar_w}" height="{bar_h}" rx="5" fill="{t.track}"/>',
        '  <g clip-path="url(#bar)">',
    ]
    shown = sum(p for _, _, p in langs) or 1
    x = float(bar_x)
    for _, color, pct in langs:
        w = bar_w * pct / shown
        parts.append(f'    <rect x="{x:.2f}" y="{bar_y}" width="{w + 0.5:.2f}" height="{bar_h}" fill="{color}"/>')
        x += w
    parts.append("  </g>")

    col_w = (WIDTH - 48) / 2
    for i, (name, color, pct) in enumerate(langs):
        cx = 24 + (i % 2) * col_w
        y = 96 + (i // 2) * 26
        parts.append(
            f'  <g class="fade" style="animation-delay:{i * 70}ms">'
            f'<circle cx="{cx + 5}" cy="{y - 4.5}" r="5" fill="{color}"/>'
            f'<text x="{cx + 18}" y="{y}" class="label">{escape(name)}</text>'
            f'<text x="{cx + col_w - 16}" y="{y}" class="value" text-anchor="end">{pct:.1f}%</text></g>'
        )
    if not langs:
        parts.append(f'  <text x="24" y="100" class="label">Sin datos todavía.</text>')
    return card("Lenguajes más usados", "\n".join(parts), t)


def main() -> None:
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
    out.mkdir(parents=True, exist_ok=True)
    user = fetch()
    rows, langs = stats(user), languages(user)
    for suffix, theme in THEMES.items():
        (out / f"stats{suffix}.svg").write_text(stats_card(rows, theme), encoding="utf-8")
        (out / f"top-langs{suffix}.svg").write_text(langs_card(langs, theme), encoding="utf-8")
    print(f"Tarjetas generadas en {out}/")


if __name__ == "__main__":
    main()
