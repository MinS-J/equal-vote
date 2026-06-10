from __future__ import annotations

import argparse
import re
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    {
        "path": "",
        "priority": "1.0",
        "changefreq": "weekly",
    }
]


def normalize_base_url(value: str) -> str:
    url = value.strip().rstrip("/")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("base URL must be an absolute http(s) URL, for example https://example.vercel.app")
    return url


def upsert_head_tag(html: str, tag_pattern: str, tag: str) -> str:
    if re.search(tag_pattern, html):
        return re.sub(tag_pattern, tag, html, count=1)
    return html.replace("    <link rel=\"manifest\"", f"    {tag}\n    <link rel=\"manifest\"", 1)


def configure_index(base_url: str) -> None:
    index_path = ROOT / "index.html"
    html = index_path.read_text(encoding="utf-8")
    html = upsert_head_tag(
        html,
        r'<link rel="canonical" href="[^"]+"\s*/>',
        f'<link rel="canonical" href="{base_url}" />',
    )
    html = upsert_head_tag(
        html,
        r'<meta property="og:url" content="[^"]+"\s*/>',
        f'<meta property="og:url" content="{base_url}" />',
    )
    html = upsert_head_tag(
        html,
        r'<meta property="og:image" content="[^"]+"\s*/>',
        f'<meta property="og:image" content="{base_url}/assets/chart1_scope.png" />',
    )
    html = upsert_head_tag(
        html,
        r'<meta name="twitter:image" content="[^"]+"\s*/>',
        f'<meta name="twitter:image" content="{base_url}/assets/chart1_scope.png" />',
    )
    index_path.write_text(html, encoding="utf-8")


def write_sitemap(base_url: str) -> None:
    urls = "\n".join(
        f"""  <url>
    <loc>{base_url}/{page["path"]}</loc>
    <changefreq>{page["changefreq"]}</changefreq>
    <priority>{page["priority"]}</priority>
  </url>"""
        for page in PAGES
    )
    (ROOT / "sitemap.xml").write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>
""",
        encoding="utf-8",
    )


def configure_robots(base_url: str) -> None:
    (ROOT / "robots.txt").write_text(
        f"""User-agent: *
Allow: /
Sitemap: {base_url}/sitemap.xml
""",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Configure canonical URL and sitemap after Vercel deploy.")
    parser.add_argument("--base-url", required=True, help="Production site URL, e.g. https://example.vercel.app")
    args = parser.parse_args()

    base_url = normalize_base_url(args.base_url)
    configure_index(base_url)
    write_sitemap(base_url)
    configure_robots(base_url)
    print(f"configured public URL: {base_url}")


if __name__ == "__main__":
    main()
