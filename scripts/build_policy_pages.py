"""Renders the policy markdown files into styled pages on the website, so
visitors read them on pokerforge.app rather than being sent to raw
markdown on GitHub.

The markdown files stay the single source of truth — re-run this after
editing one. Two things it does deliberately:

- Strips the leading "DRAFT — not legal advice" blockquote. That note is
  addressed to whoever maintains the document, not to users, and a
  published policy announcing itself as an unreviewed draft undermines
  the thing it's trying to do.
- REFUSES to publish a document still carrying bracketed editorial notes
  (e.g. "[A lawyer should confirm...]"). Those mark decisions that
  haven't been made yet, and shipping them verbatim would be worse than
  not publishing the page at all.

Usage:  python scripts/build_policy_pages.py
"""
import re
import sys
from pathlib import Path

import markdown

REPO = Path(__file__).resolve().parent.parent
DOCS = REPO / "docs"

PAGES = [
    ("PRIVACY_POLICY.md", "privacy", "Privacy Policy",
     "How PokerForge handles your data: everything stays on your own computer."),
    ("TERMS_OF_USE.md", "terms", "Terms of Use",
     "The terms covering your use of PokerForge."),
]

# A markdown link is [text](url); an editorial note is a bracketed
# sentence with no URL after it.
_EDITORIAL_NOTE = re.compile(r"\[[^\]]{15,}\](?!\()")

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — PokerForge</title>
<meta name="description" content="{description}">
<meta property="og:title" content="PokerForge — {title}">
<meta property="og:description" content="{description}">
<meta property="og:type" content="website">
<meta property="og:url" content="https://pokerforge.app/{slug}/">
<link rel="icon" href="/favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="/favicon-32.png">
<link rel="icon" type="image/png" sizes="192x192" href="/favicon-192.png">
<link rel="apple-touch-icon" href="/apple-touch-icon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700;800&family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="/styles.css">
</head>
<body>

<header class="nav">
  <div class="wrap nav-row">
    <a class="brand" href="/" style="text-decoration:none;">
      <img src="/logo.png" width="42" height="42" alt="" decoding="async">
      <span>Poker<span class="fg">Forge</span></span>
    </a>
    <nav class="nav-links">
      <a href="/#features">Features</a>
      <a href="/#faq">FAQ</a>
    </nav>
    <a href="https://github.com/PokerForge/pokerforge/releases" class="btn btn-primary js-download">Download Free</a>
  </div>
</header>

<section>
  <div class="wrap">
    <article class="prose">
{content}
    </article>
  </div>
</section>

<footer>
  <div class="wrap">
    <div class="foot-grid">
      <div>
        <div class="brand" style="font-size:20px;">
          <img src="/logo.png" width="22" height="22" alt="" decoding="async">
          <span>Poker<span class="fg">Forge</span></span>
        </div>
        <p class="foot-tag">Play. Analyse. Improve. A stats engine that stays on your machine.</p>
      </div>
      <div>
        <h4>Product</h4>
        <a href="/#features">Features</a>
        <a href="/#faq">FAQ</a>
        <a href="https://github.com/PokerForge/pokerforge/releases">All releases</a>
      </div>
      <div>
        <h4>Project</h4>
        <a href="mailto:support@pokerforge.app">Support</a>
        <a href="https://github.com/PokerForge/pokerforge">GitHub</a>
        <a href="https://github.com/PokerForge/pokerforge/issues/new">Report an issue</a>
        <a href="https://github.com/PokerForge/pokerforge/blob/main/CHANGELOG.md">Changelog</a>
      </div>
      <div>
        <h4>Legal</h4>
        <a href="/privacy/">Privacy Policy</a>
        <a href="/terms/">Terms of Use</a>
      </div>
    </div>
    <div class="foot-bottom">
      <span>&copy; 2026 PokerForge</span>
      <span>Not affiliated with PokerStars, GGPoker, Winning Poker Network or iPoker.</span>
    </div>
  </div>
</footer>

<script src="/download-link.js"></script>
</body>
</html>
"""


def strip_draft_banner(text: str) -> str:
    lines = text.splitlines()
    out, skipping = [], False
    for line in lines:
        if line.startswith("> ") and "DRAFT" in line:
            skipping = True
            continue
        if skipping:
            if line.startswith(">") or not line.strip():
                continue
            skipping = False
        out.append(line)
    return "\n".join(out)


def build(md_name: str, slug: str, title: str, description: str) -> str:
    raw = (REPO / md_name).read_text(encoding="utf-8")
    body = strip_draft_banner(raw)

    notes = _EDITORIAL_NOTE.findall(body)
    if notes:
        raise SystemExit(
            f"REFUSING to publish {md_name}: it still contains "
            f"{len(notes)} unresolved editorial note(s).\n"
            + "\n".join(f"   - {n[:90]}" for n in notes)
            + "\n\nResolve these in the markdown first — publishing them "
              "verbatim would be worse than not publishing the page."
        )

    html = markdown.markdown(body, extensions=["extra", "sane_lists"])
    indented = "\n".join("      " + l for l in html.splitlines())
    page = TEMPLATE.format(title=title, description=description, slug=slug, content=indented)

    out_dir = DOCS / slug
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "index.html").write_text(page, encoding="utf-8")
    return f"docs/{slug}/index.html"


def main():
    built, blocked = [], []
    for md_name, slug, title, description in PAGES:
        try:
            built.append(build(md_name, slug, title, description))
        except SystemExit as e:
            blocked.append(str(e))

    for path in built:
        print(f"built   {path}")
    for msg in blocked:
        print(f"\nSKIPPED {msg}")
    if blocked and not built:
        sys.exit(1)


if __name__ == "__main__":
    main()
