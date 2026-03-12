#!/usr/bin/env python3
"""Generate LLM-friendly dataset indexes from data.bs.ch using public Explore API."""

from __future__ import annotations

import json
import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
import unicodedata
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT / "llms" / "datasets"
BY_THEME_DIR = DATASETS_DIR / "by-theme"
LOG = logging.getLogger("generate_dataset_docs")
API_BASE = "https://data.bs.ch/api/explore/v2.1"
CATALOG_ENDPOINT = f"{API_BASE}/catalog/datasets"

CANONICAL_THEME_NAMES = [
    "Arbeit, Erwerb",
    "Bau- und Wohnungswesen",
    "Bevölkerung",
    "Bildung, Wissenschaft",
    "Energie",
    "Finanzen",
    "Gebäude",
    "Geographie",
    "Gesetzgebung",
    "Gesundheit",
    "Handel",
    "Industrie, Dienstleistungen",
    "Kriminalität, Strafrecht",
    "Kultur, Medien, Informationsgesellschaft, Sport",
    "Land- und Forstwirtschaft",
    "Mobilität und Verkehr",
    "Politik",
    "Preise",
    "Raum und Umwelt",
    "Soziale Sicherheit",
    "Statistische Grundlagen",
    "Tourismus",
    "Verwaltung",
    "Volkswirtschaft",
    "Öffentliche Ordnung und Sicherheit",
]

THEME_ALIASES = {
    "Bildung": "Bildung, Wissenschaft",
    "Wissenschaft": "Bildung, Wissenschaft",
    "Kultur": "Kultur, Medien, Informationsgesellschaft, Sport",
}

CANONICAL_THEME_SET = set(CANONICAL_THEME_NAMES)


def configure_logging() -> None:
    """Configure script logging."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def fetch_json(url: str) -> dict:
    """Fetch and decode JSON from a URL.

    Args:
        url: Absolute URL to fetch.

    Returns:
        Decoded JSON payload.

    Raises:
        RuntimeError: If the request fails.
    """
    try:
        with urlopen(url, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError) as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def slugify(value: str) -> str:
    """Convert theme labels into stable ASCII slugs.

    Args:
        value: Raw theme label.

    Returns:
        URL/file-safe slug.
    """
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def iter_datasets() -> list[dict]:
    """Fetch all public datasets using Explore API pagination."""
    datasets: list[dict] = []
    limit = 100
    offset = 0
    total_count: int | None = None

    while True:
        url = f"{CATALOG_ENDPOINT}?limit={limit}&offset={offset}"
        payload = fetch_json(url)
        results = payload.get("results", [])
        if total_count is None:
            total_count = int(payload.get("total_count", 0))
            LOG.info("Explore API total datasets reported: %s", total_count)
        datasets.extend(results)
        offset += len(results)
        LOG.info("Fetched %s/%s datasets", offset, total_count)
        if not results or offset >= total_count:
            break

    return datasets


def get_default_meta(dataset: dict) -> dict:
    """Return default metadata block from a dataset record."""
    metas = dataset.get("metas", {})
    return metas.get("default", {}) if isinstance(metas, dict) else {}


def extract_theme_names(dataset: dict) -> list[str]:
    """Extract and normalize theme names from a dataset record.

    Args:
        dataset: Explore API dataset record.

    Returns:
        Normalized theme names.
    """
    metas = dataset.get("metas", {})
    default_meta = metas.get("default", {})
    themes = default_meta.get("theme")
    if not isinstance(themes, list):
        return ["Uncategorized"]

    normalized: list[str] = []
    seen: set[str] = set()
    for raw_theme in themes:
        theme = str(raw_theme).strip()
        if not theme:
            continue

        canonical = THEME_ALIASES.get(theme, theme)
        if canonical not in CANONICAL_THEME_SET:
            LOG.warning("Unknown theme label encountered: %s", theme)
        if canonical not in seen:
            normalized.append(canonical)
            seen.add(canonical)

    return normalized or ["Uncategorized"]


def extract_title(dataset: dict) -> str:
    """Extract dataset title with fallback to dataset identifier."""
    default_meta = get_default_meta(dataset)
    title = default_meta.get("title")
    if title:
        return str(title).strip()
    return dataset.get("dataset_id", "unknown-dataset")


def extract_modified(dataset: dict) -> str:
    """Extract modified timestamp or return n/a."""
    default_meta = get_default_meta(dataset)
    value = default_meta.get("modified")
    return str(value).strip() if value else "n/a"


def extract_records_count(dataset: dict) -> str:
    """Extract records count or return n/a."""
    default_meta = get_default_meta(dataset)
    value = default_meta.get("records_count")
    return str(value) if value is not None else "n/a"


def write_text(path: Path, content: str) -> None:
    """Write text content to file, creating directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_dataset_link(dataset_id: str) -> str:
    """Build the public dataset information URL."""
    return f"https://data.bs.ch/explore/dataset/{dataset_id}/information/"


def build_main_index(datasets: list[dict], generated_at: str) -> str:
    """Build the global dataset index markdown page."""
    lines = [
        "# data.bs.ch dataset index",
        "",
        f"_Generated: {generated_at}_",
        "",
        "This index is generated from the Explore API and grouped by themes in dedicated pages.",
        "",
        f"- Total datasets: **{len(datasets)}**",
        "- Theme index: [by-theme/index.md](./by-theme/index.md)",
        "",
        "## Datasets",
        "",
        "| dataset_id | title | records_count | modified | themes |",
        "|---|---|---:|---|---|",
    ]

    for ds in sorted(datasets, key=lambda item: item.get("dataset_id", "")):
        dataset_id = ds.get("dataset_id", "")
        title = extract_title(ds).replace("|", "\\|")
        records = extract_records_count(ds)
        modified = extract_modified(ds)
        themes = ", ".join(extract_theme_names(ds)).replace("|", "\\|")
        dataset_link = render_dataset_link(dataset_id)
        lines.append(
            f"| [{dataset_id}]({dataset_link}) | {title} | {records} | {modified} | {themes} |"
        )

    lines.append("")
    return "\n".join(lines)


def build_theme_index(theme_map: dict[str, list[dict]], generated_at: str) -> str:
    """Build the by-theme index markdown page."""
    lines = [
        "# data.bs.ch datasets by theme",
        "",
        f"_Generated: {generated_at}_",
        "",
        "## Theme pages",
        "",
        "| theme | datasets | page |",
        "|---|---:|---|",
    ]

    for theme in sorted(theme_map.keys(), key=lambda x: x.lower()):
        datasets = theme_map[theme]
        slug = slugify(theme)
        page = f"./{slug}.md"
        lines.append(f"| {theme.replace('|', '\\|')} | {len(datasets)} | [open]({page}) |")

    lines.append("")
    return "\n".join(lines)


def build_theme_page(theme: str, datasets: list[dict], generated_at: str) -> str:
    """Build a single theme markdown page."""
    lines = [
        f"# Theme: {theme}",
        "",
        f"_Generated: {generated_at}_",
        "",
        f"- Dataset count: **{len(datasets)}**",
        "- Back to: [theme index](./index.md)",
        "",
        "| dataset_id | title | records_count | modified |",
        "|---|---|---:|---|",
    ]

    for ds in sorted(datasets, key=lambda item: item.get("dataset_id", "")):
        dataset_id = ds.get("dataset_id", "")
        title = extract_title(ds).replace("|", "\\|")
        records = extract_records_count(ds)
        modified = extract_modified(ds)
        dataset_link = render_dataset_link(dataset_id)
        lines.append(f"| [{dataset_id}]({dataset_link}) | {title} | {records} | {modified} |")

    lines.append("")
    return "\n".join(lines)


def generate() -> None:
    """Generate all dataset and theme markdown pages."""
    LOG.info("Starting dataset doc generation")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    datasets = iter_datasets()
    if not datasets:
        raise RuntimeError("No datasets returned from API; aborting generation.")
    LOG.info("Datasets normalized: %s", len(datasets))

    theme_map: dict[str, list[dict]] = defaultdict(list)
    for ds in datasets:
        for theme in extract_theme_names(ds):
            theme_map[theme].append(ds)
    LOG.info("Themes aggregated: %s", len(theme_map))

    write_text(DATASETS_DIR / "index.md", build_main_index(datasets, generated_at))
    write_text(BY_THEME_DIR / "index.md", build_theme_index(theme_map, generated_at))
    LOG.info("Main index files written")

    # Remove stale theme files from previous generations.
    if BY_THEME_DIR.exists():
        for old_file in BY_THEME_DIR.glob("*.md"):
            if old_file.name != "index.md":
                old_file.unlink()

    for theme, themed_datasets in theme_map.items():
        slug = slugify(theme)
        write_text(BY_THEME_DIR / f"{slug}.md", build_theme_page(theme, themed_datasets, generated_at))
    LOG.info("Theme pages written: %s", len(theme_map))
    LOG.info("Generation completed successfully: datasets=%s themes=%s", len(datasets), len(theme_map))
    print(f"Generated dataset docs for {len(datasets)} datasets across {len(theme_map)} themes.")


if __name__ == "__main__":
    try:
        configure_logging()
        generate()
    except Exception:  # pragma: no cover
        LOG.exception("Dataset doc generation failed")
        sys.exit(1)
