from pathlib import Path
import re
from html import escape

from PIL import Image


ROOT = Path(__file__).resolve().parent
SOURCE_HTML = ROOT / "index.html"
OUTPUT_HTML = ROOT / "index-optimized.html"
ART_DIR = ROOT / "art"
WEB_DIR = ROOT / "art-web"
SIZES = (480, 900, 1200, 1600)
QUALITY = {480: 74, 900: 78, 1200: 78, 1600: 82}


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def image_size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        return img.size


def generate_webp() -> dict[str, dict[int, tuple[str, int, int, int]]]:
    manifest: dict[str, dict[int, tuple[str, int, int, int]]] = {}
    for src in sorted(ART_DIR.glob("*.jpg")):
        src_rel = rel(src)
        manifest[src_rel] = {}
        with Image.open(src) as img:
            img = img.convert("RGB")
            original_w, original_h = img.size
            for width in SIZES:
                out_dir = WEB_DIR / str(width)
                out_dir.mkdir(parents=True, exist_ok=True)
                out = out_dir / f"{src.stem}.webp"
                target_w = min(width, original_w)
                target_h = round(original_h * (target_w / original_w))
                if not out.exists():
                    resized = img if target_w == original_w else img.resize((target_w, target_h), Image.Resampling.LANCZOS)
                    resized.save(out, "WEBP", quality=QUALITY[width], method=6)
                manifest[src_rel][width] = (rel(out), target_w, target_h, out.stat().st_size)
    return manifest


def nearest_title(html: str, index: int) -> str:
    prefix = html[max(0, index - 320):index]
    matches = list(re.finditer(r'data-title="([^"]+)"', prefix))
    return matches[-1].group(1) if matches else "OCWE artwork"


def optimize_html(manifest: dict[str, dict[int, tuple[str, int, int, int]]]) -> None:
    html = SOURCE_HTML.read_text(encoding="utf-8")

    html = html.replace(
        ".thumb { position: relative; min-width: 0; cursor: pointer; transition: transform .24s ease, filter .24s ease, box-shadow .24s ease; }",
        ".thumb { position: relative; min-width: 0; aspect-ratio: 1 / 1; overflow: hidden; cursor: pointer; transition: transform .24s ease, filter .24s ease, box-shadow .24s ease; }",
    )
    html = html.replace(
        ".thumb[hidden] { display: none !important; }\n.thumb img",
        ".thumb[hidden] { display: none !important; }\n.thumb picture { display: block; width: 100%; height: 100%; }\n.thumb img",
    )
    html = html.replace(
        '<link rel="preconnect" href="https://fonts.googleapis.com">\n'
        '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n'
        '<link href="https://fonts.googleapis.com/css2?family=Archivo+Black&family=Space+Grotesk:wght@500;700;900&display=swap" rel="stylesheet">',
        '<link rel="preload" href="fonts/space-grotesk-latin.woff2" as="font" type="font/woff2" crossorigin>\n'
        '<link rel="preload" href="fonts/space-grotesk-latin-ext.woff2" as="font" type="font/woff2" crossorigin>',
    )
    html = html.replace(
        "* { box-sizing: border-box; }\n:root",
        "* { box-sizing: border-box; }\n"
        "@font-face { font-family: 'Space Grotesk'; font-style: normal; font-weight: 500 900; font-display: swap; src: url('fonts/space-grotesk-latin.woff2') format('woff2'); unicode-range: U+0000-00FF, U+0131, U+0152-0153, U+02BB-02BC, U+02C6, U+02DA, U+02DC, U+0304, U+0308, U+0329, U+2000-206F, U+20AC, U+2122, U+2191, U+2193, U+2212, U+2215, U+FEFF, U+FFFD; }\n"
        "@font-face { font-family: 'Space Grotesk'; font-style: normal; font-weight: 500 900; font-display: swap; src: url('fonts/space-grotesk-latin-ext.woff2') format('woff2'); unicode-range: U+0100-02BA, U+02BD-02C5, U+02C7-02CC, U+02CE-02D7, U+02DD-02FF, U+0304, U+0308, U+0329, U+1D00-1DBF, U+1E00-1E9F, U+1EF2-1EFF, U+2020, U+20A0-20AB, U+20AD-20C0, U+2113, U+2C60-2C7F, U+A720-A7FF; }\n"
        ":root",
    )

    html = re.sub(
        r'<a\b([^>]*target="_blank"(?![^>]*\brel=)[^>]*)>',
        r'<a\1 rel="noopener noreferrer">',
        html,
    )

    # Prioritize the visible brand mark and reserve its layout space.
    html = re.sub(
        r'<img(\s+src="logo/ocwe_h_t\.png"[^>]*)>',
        lambda m: enrich_static_img(m.group(1), ROOT / "logo" / "ocwe_h_t.png", fetchpriority=True),
        html,
        count=1,
    )

    def replace_art_img(match: re.Match[str]) -> str:
        src = match.group("src")
        attrs = match.group("attrs")
        if src not in manifest:
            return match.group(0)

        title = nearest_title(html, match.start())
        original_w, original_h = image_size(ROOT / src)
        srcset = ",\n            ".join(
            f"{manifest[src][size][0]} {manifest[src][size][1]}w" for size in SIZES
        )
        fallback = manifest[src][900][0]
        full = manifest[src][1600][0]

        if "alt=" not in attrs:
            attrs += f' alt="{escape(title, quote=True)}"'
        if "loading=" not in attrs:
            attrs += ' loading="lazy"'
        if "decoding=" not in attrs:
            attrs += ' decoding="async"'
        if "width=" not in attrs:
            attrs += f' width="{original_w}"'
        if "height=" not in attrs:
            attrs += f' height="{original_h}"'
        if "data-full-image=" not in attrs:
            attrs += f' data-full-image="{full}"'

        return (
            '<picture>\n'
            f'  <source type="image/webp" srcset="{srcset}" '
            'sizes="(max-width: 520px) calc(100vw - 22px), '
            '(max-width: 900px) 50vw, 340px">\n'
            f'  <img src="{fallback}"{attrs}>\n'
            '</picture>'
        )

    html = re.sub(
        r'<img\s+src="(?P<src>art/[^"]+\.jpg)"(?P<attrs>[^>]*)>',
        replace_art_img,
        html,
    )

    for src, variants in manifest.items():
        stem = Path(src).stem
        html = html.replace(
            f"art-web/900/{stem}.webp 900w,\n            art-web/1600/{stem}.webp 1600w",
            f"art-web/900/{stem}.webp 900w,\n            art-web/1200/{stem}.webp 1200w,\n            art-web/1600/{stem}.webp 1600w",
        )

    # Size and async-decode the small icon assets.
    html = re.sub(
        r'<img(\s+src="social/([^"]+)"[^>]*)>',
        lambda m: enrich_static_img(m.group(1), ROOT / "social" / m.group(2)),
        html,
    )

    html = html.replace(
        "document.getElementById('modal-img').src = el.querySelector('img').src;",
        "const thumbImg = el.querySelector('img');\n"
        "  document.getElementById('modal-img').src = thumbImg.dataset.fullImage || thumbImg.currentSrc || thumbImg.src;",
    )
    html = html.replace(
        "let modalItems = [];\nlet modalIndex = -1;",
        "let modalItems = [];\nlet modalIndex = -1;\n\n"
        "thumbs.forEach(thumb => {\n"
        "  thumb.setAttribute('role', 'button');\n"
        "  thumb.setAttribute('tabindex', '0');\n"
        "  thumb.setAttribute('aria-label', `Open artwork ${thumb.dataset.title}`);\n"
        "  thumb.addEventListener('keydown', e => {\n"
        "    if (e.key === 'Enter' || e.key === ' ') {\n"
        "      e.preventDefault();\n"
        "      openModal(thumb);\n"
        "    }\n"
        "  });\n"
        "});",
    )

    OUTPUT_HTML.write_text(html, encoding="utf-8")


def enrich_static_img(attrs: str, path: Path, fetchpriority: bool = False) -> str:
    width, height = image_size(path)
    extra = attrs
    if "width=" not in extra:
        extra += f' width="{width}"'
    if "height=" not in extra:
        extra += f' height="{height}"'
    if "decoding=" not in extra:
        extra += ' decoding="async"'
    if fetchpriority and "fetchpriority=" not in extra:
        extra += ' fetchpriority="high"'
    return f"<img{extra}>"


def main() -> None:
    manifest = generate_webp()
    optimize_html(manifest)
    original_bytes = sum(p.stat().st_size for p in ART_DIR.glob("*.jpg"))
    webp_bytes = {
        size: sum(p.stat().st_size for p in (WEB_DIR / str(size)).glob("*.webp"))
        for size in SIZES
    }
    print(f"Generated {sum(len(v) for v in manifest.values())} WebP files")
    print(f"Original art bytes: {original_bytes}")
    for size, total in webp_bytes.items():
        print(f"WebP {size}px bytes: {total}")
    print(f"Wrote {OUTPUT_HTML.name}")


if __name__ == "__main__":
    main()
