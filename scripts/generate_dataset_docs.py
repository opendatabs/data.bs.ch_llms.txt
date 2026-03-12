#!/usr/bin/env python3
"""Generate LLM-friendly dataset indexes from data.bs.ch using huwise-utils-py."""

from __future__ import annotations

import logging
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List
import unicodedata

from huwise_utils_py import bulk_get_dataset_ids, bulk_get_metadata

ROOT = Path(__file__).resolve().parents[1]
DATASETS_DIR = ROOT / "llms" / "datasets"
BY_THEME_DIR = DATASETS_DIR / "by-theme"
LOG = logging.getLogger("generate_dataset_docs")


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


def extract_huwise_value(field_value: object) -> object:
    """Normalize metadata field values from huwise-utils-py responses.

    Huwise metadata fields are usually dictionaries like {"value": ...}.
    """
    if isinstance(field_value, dict) and "value" in field_value:
        return field_value["value"]
    return field_value


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "unknown"


def normalize_theme_value(theme_value: object) -> List[str]:
    """Return a list of themes from mixed metadata formats."""
    if isinstance(theme_value, list):
        cleaned = [str(t).strip() for t in theme_value if str(t).strip()]
        return cleaned or ["Uncategorized"]
    if isinstance(theme_value, str) and theme_value.strip():
        # Handle either single theme or comma-separated label formats.
        if "," in theme_value:
            cleaned = [part.strip() for part in theme_value.split(",") if part.strip()]
            return cleaned or ["Uncategorized"]
        return [theme_value.strip()]
    return ["Uncategorized"]


def iter_datasets() -> Iterable[Dict]:
    """Fetch datasets via huwise-utils-py and map to existing output schema."""
    LOG.info("Fetching dataset IDs from Huwise Automation API")
    dataset_ids = bulk_get_dataset_ids(include_restricted=False)
    LOG.info("Fetched dataset IDs", extra={"count": len(dataset_ids)})

    LOG.info("Fetching dataset metadata in bulk")
    metadata_by_id = bulk_get_metadata(dataset_ids=dataset_ids)
    LOG.info("Bulk metadata response received", extra={"count": len(metadata_by_id)})

    failed_ids: list[str] = []

    for dataset_id in dataset_ids:
        metadata = metadata_by_id.get(dataset_id, {})
        if not isinstance(metadata, dict) or "error" in metadata:
            failed_ids.append(dataset_id)
            continue

        default_meta = metadata.get("default", {})
        title = extract_huwise_value(default_meta.get("title"))
        modified = extract_huwise_value(default_meta.get("modified"))
        records_count = extract_huwise_value(default_meta.get("records_count"))
        theme_val = extract_huwise_value(default_meta.get("theme"))
        if theme_val in (None, "", []):
            # Some portals store only theme IDs in metadata.
            theme_val = extract_huwise_value(default_meta.get("theme_id"))

        yield {
            "dataset_id": dataset_id,
            "metas": {
                "default": {
                    "title": title,
                    "modified": modified,
                    "records_count": records_count,
                    "theme": normalize_theme_value(theme_val),
                }
            },
        }

    if failed_ids:
        sample = ", ".join(failed_ids[:10])
        raise RuntimeError(
            f"Metadata fetch failed for {len(failed_ids)} datasets. Sample IDs: {sample}"
        )


def extract_theme_names(dataset: Dict) -> List[str]:
    metas = dataset.get("metas", {})
    default_meta = metas.get("default", {})
    themes = default_meta.get("theme")
    if isinstance(themes, list):
        cleaned = [str(t).strip() for t in themes if str(t).strip()]
        return cleaned or ["Uncategorized"]
    return ["Uncategorized"]


def extract_title(dataset: Dict) -> str:
    metas = dataset.get("metas", {})
    default_meta = metas.get("default", {})
    title = default_meta.get("title")
    if title:
        return str(title).strip()
    return dataset.get("dataset_id", "unknown-dataset")


def extract_modified(dataset: Dict) -> str:
    metas = dataset.get("metas", {})
    default_meta = metas.get("default", {})
    value = default_meta.get("modified")
    return str(value).strip() if value else "n/a"


def extract_records_count(dataset: Dict) -> str:
    metas = dataset.get("metas", {})
    default_meta = metas.get("default", {})
    value = default_meta.get("records_count")
    return str(value) if value is not None else "n/a"


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def render_dataset_link(dataset_id: str) -> str:
    return f"https://data.bs.ch/explore/dataset/{dataset_id}/information/"


def build_main_index(datasets: List[Dict], generated_at: str) -> str:
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


def build_theme_index(theme_map: Dict[str, List[Dict]], generated_at: str) -> str:
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


def build_theme_page(theme: str, datasets: List[Dict], generated_at: str) -> str:
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
    LOG.info("Starting dataset doc generation")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    datasets = list(iter_datasets())
    if not datasets:
        raise RuntimeError("No datasets returned from API; aborting generation.")
    LOG.info("Datasets normalized", extra={"count": len(datasets)})

    theme_map: Dict[str, List[Dict]] = defaultdict(list)
    for ds in datasets:
        for theme in extract_theme_names(ds):
            theme_map[theme].append(ds)
    LOG.info("Themes aggregated", extra={"theme_count": len(theme_map)})

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
    LOG.info("Theme pages written", extra={"theme_count": len(theme_map)})

    LOG.info(
        "Generation completed successfully",
        extra={"dataset_count": len(datasets), "theme_count": len(theme_map)},
    )
    print(f"Generated dataset docs for {len(datasets)} datasets across {len(theme_map)} themes.")


if __name__ == "__main__":
    try:
        configure_logging()
        generate()
    except Exception as exc:  # pragma: no cover
        LOG.exception("Dataset doc generation failed")
        print(str(exc), file=sys.stderr)
        sys.exit(1)
