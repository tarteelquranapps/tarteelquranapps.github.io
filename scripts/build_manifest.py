#!/usr/bin/env python3
"""
Pixabay Portrait-Only Manifest Build Pipeline for Quran Clips Studio.

Queries the Pixabay API for curated, portrait-only (9:16) image and video presets,
enforces strict orientation checks (height > width), applies a whole-word tokenized
Islamic compliance blocklist, selects optimal media tiers (small 1080x1920 for videos,
webformat 1280px for images), deduplicates across queries, and outputs the manifest.
"""

import argparse
import datetime
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Set
import urllib.error
import urllib.parse
import urllib.request

# Canonical whole-word Islamic compliance blocklist per spec.md and ADR 0007
BLOCKLIST: Set[str] = {
    "woman",
    "women",
    "girl",
    "lady",
    "man",
    "men",
    "boy",
    "person",
    "people",
    "human",
    "face",
    "portrait",
    "dog",
    "bikini",
    "swimsuit",
    "church",
    "cathedral",
    "temple",
    "hindu",
    "buddha",
    "christian",
    "cross",
    "crucifix",
    "beer",
    "wine",
    "alcohol",
    "bar",
    "pub",
    "club",
    "party",
    "dance",
    "pig",
    "pork",
    "statue",
    "sculpture",
    "idol",
    "nude",
    "sexy",
    "tattoo",
    "halloween",
    "christmas",
    "easter",
}

THEMATIC_QUERIES = {
    "nature": [
        "waterfall",
        "forest trees",
        "rain water drops",
        "mountain landscape",
        "ocean waves",
        "green foliage leaf",
    ],
    "atmospheric": [
        "clouds sky",
        "sunset sky",
        "starry night sky",
        "fog mist mountains",
        "sunrise light",
    ],
    "sacred": [
        "mosque architecture",
        "islamic architecture",
        "mecca medina",
        "kaaba",
        "arabic calligraphy",
        "islamic geometric art",
    ],
}


def is_portrait(width: Optional[int], height: Optional[int]) -> bool:
    """Verifies that height strictly exceeds width."""
    if width is None or height is None:
        return False
    if width <= 0 or height <= 0:
        return False
    return height > width


def tokenize_text(text: str) -> Set[str]:
    """Extracts lowercase word tokens, splitting on punctuation and whitespace."""
    if not text:
        return set()
    # Extract contiguous words (letters and numbers)
    tokens = re.findall(r"[a-zA-Z0-9]+", text.lower())
    return set(tokens)


def is_islamic_compliant(tags: Any, title: str = "") -> bool:
    """
    Checks if tags and title contain any whole-word blocked tokens.
    Returns True if compliant (no blocked words), False otherwise.
    """
    tokens = tokenize_text(title)
    if isinstance(tags, str):
        tokens.update(tokenize_text(tags))
    elif isinstance(tags, (list, tuple, set)):
        for tag in tags:
            if isinstance(tag, str):
                tokens.update(tokenize_text(tag))

    # Reject if any token matches the blocklist
    for blocked_word in BLOCKLIST:
        if blocked_word in tokens:
            return False

    return True


def extract_tags_list(tags_field: Any) -> List[str]:
    """Normalizes tags into a list of clean lowercase strings."""
    if isinstance(tags_field, str):
        return [t.strip().lower() for t in tags_field.split(",") if t.strip()]
    elif isinstance(tags_field, list):
        return [t.strip().lower() for t in tags_field if isinstance(t, str) and t.strip()]
    return []


def process_image_item(item: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    """
    Processes a raw Pixabay image API item into a Preset dictionary.
    Returns None if item is not portrait or violates the compliance blocklist.
    """
    raw_width = item.get("imageWidth")
    raw_height = item.get("imageHeight")
    webformat_width = item.get("webformatWidth", raw_width)
    webformat_height = item.get("webformatHeight", raw_height)

    # Orientation check: raw and webformat must strictly be vertical portrait
    if not is_portrait(raw_width, raw_height) or not is_portrait(webformat_width, webformat_height):
        return None

    tags_str = item.get("tags", "")

    # Compliance check on content tags
    if not is_islamic_compliant(tags=tags_str):
        return None

    item_id = item.get("id")
    webformat_url = item.get("webformatURL", "")
    preview_url = item.get("previewURL", webformat_url)

    # Derive high-resolution permanent CDN 1280px URL per spec and ADR 0007
    media_url = webformat_url
    width = webformat_width
    height = webformat_height

    if preview_url and "cdn.pixabay.com" in preview_url:
        media_url = re.sub(r"_\d+\.(jpe?g|png)", r"_1280.\1", preview_url)
        if raw_width and raw_height and raw_height > raw_width:
            height = 1280
            width = int(round(raw_width * 1280 / raw_height))
    elif item.get("largeImageURL"):
        media_url = item.get("largeImageURL")

    # Name formatted from tags
    tags_list = extract_tags_list(tags_str)
    name = ", ".join(tags_list[:3]) if tags_list else f"{category} image"

    return {
        "id": f"{category}-image-{item_id}",
        "name": name,
        "category": category,
        "type": "image",
        "thumbnailUrl": preview_url,
        "mediaUrl": webformat_url,
        "width": webformat_width,
        "height": webformat_height,
        "tags": {
            "en": tags_list,
        },
    }


def process_video_item(item: Dict[str, Any], category: str) -> Optional[Dict[str, Any]]:
    """
    Processes a raw Pixabay video API item into a Preset dictionary.
    Strictly links the small 1080x1920 portrait stream per spec and ADR 0007.
    Returns None if small tier is not portrait or violates compliance blocklist.
    """
    videos_dict = item.get("videos", {})
    if not isinstance(videos_dict, dict) or not videos_dict:
        return None

    # Strictly inspect small tier (native full-HD vertical 1080x1920)
    small_tier = videos_dict.get("small")
    if not small_tier or not is_portrait(small_tier.get("width"), small_tier.get("height")):
        return None

    tags_str = item.get("tags", "")

    # Compliance check on content tags
    if not is_islamic_compliant(tags=tags_str):
        return None

    item_id = item.get("id")
    media_url = small_tier.get("url", "")
    width = small_tier.get("width")
    height = small_tier.get("height")
    duration = item.get("duration", 0)

    # Video thumbnail: check tiny stream thumbnail, small thumbnail, or picture_id
    thumb_url = ""
    tiny_tier = videos_dict.get("tiny", {})
    if isinstance(tiny_tier, dict) and tiny_tier.get("thumbnail"):
        thumb_url = tiny_tier.get("thumbnail")
    elif small_tier.get("thumbnail"):
        thumb_url = small_tier.get("thumbnail")
    elif item.get("picture_id"):
        thumb_url = f"https://i.vimeocdn.com/video/{item.get('picture_id')}_295x166.jpg"

    tags_list = extract_tags_list(tags_str)
    name = ", ".join(tags_list[:3]) if tags_list else f"{category} video"

    return {
        "id": f"{category}-video-{item_id}",
        "name": name,
        "category": category,
        "type": "video",
        "thumbnailUrl": thumb_url,
        "mediaUrl": media_url,
        "duration": duration,
        "width": width,
        "height": height,
        "tags": {
            "en": tags_list,
        },
    }


DEFAULT_API_KEY = "57948098-ae0bfb11360afded649a37361"


def build_manifest_data(raw_items_with_meta: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Processes and deduplicates raw items across categories and queries.
    Returns dictionary with version, updatedAt, and backgrounds list.
    """
    seen_media_ids: Set[Any] = set()
    backgrounds: List[Dict[str, Any]] = []

    for entry in raw_items_with_meta:
        category = entry.get("category", "nature")
        media_type = entry.get("type", "video")
        raw_item = entry.get("item", {})

        raw_id = raw_item.get("id")
        if raw_id in seen_media_ids:
            continue

        preset = None
        if media_type == "image":
            preset = process_image_item(raw_item, category)
        elif media_type == "video":
            preset = process_video_item(raw_item, category)

        if preset:
            seen_media_ids.add(raw_id)
            backgrounds.append(preset)

    return {
        "version": 1,
        "updatedAt": datetime.date.today().isoformat(),
        "backgrounds": backgrounds,
    }


def fetch_pixabay_api(
    endpoint: str,
    params: Dict[str, Any],
    api_key: str,
    max_retries: int = 3,
) -> Dict[str, Any]:
    """Helper to query Pixabay API with rate limit pacing and retries."""
    params["key"] = api_key
    query_string = urllib.parse.urlencode(params)
    url = f"{endpoint}?{query_string}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }

    for attempt in range(max_retries):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as response:
                remaining_header = response.headers.get("X-RateLimit-Remaining")
                reset_header = response.headers.get("X-RateLimit-Reset")
                remaining = int(remaining_header) if remaining_header and remaining_header.isdigit() else 100
                reset_sec = int(reset_header) if reset_header and reset_header.isdigit() else 10

                if response.status == 200:
                    data = json.loads(response.read().decode("utf-8"))
                    # If quota is getting tight, pause until reset window
                    if remaining < 10 and reset_sec > 0:
                        print(f"Rate limit remaining={remaining}, pausing {reset_sec + 1}s...")
                        time.sleep(reset_sec + 1)
                    else:
                        time.sleep(0.65)
                    return data
        except urllib.error.HTTPError as e:
            if e.code == 429:
                reset_header = e.headers.get("X-RateLimit-Reset") if e.headers else None
                reset_sec = int(reset_header) if reset_header and reset_header.isdigit() else 15
                print(f"Rate limited (429). Sleeping for {reset_sec + 2} seconds...", file=sys.stderr)
                time.sleep(reset_sec + 2)
                continue
            else:
                print(f"HTTP error {e.code} querying {url}: {e}", file=sys.stderr)
                break
        except Exception as e:
            print(f"Error querying {url} (attempt {attempt + 1}): {e}", file=sys.stderr)
            time.sleep(2)
            continue
    return {}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build portrait-only preset manifest from Pixabay")
    parser.add_argument("--api-key", default=os.environ.get("PIXABAY_API_KEY", DEFAULT_API_KEY), help="Pixabay API Key")
    parser.add_argument("--output", default="quran-clips-backgrounds.json", help="Output JSON manifest file")
    parser.add_argument("--per-page", type=int, default=200, help="Results per query")
    parser.add_argument("--max-pages", type=int, default=3, help="Max pages to fetch per query")
    args = parser.parse_args()

    if not args.api_key:
        print("Error: PIXABAY_API_KEY environment variable or --api-key argument required to query live API.")
        sys.exit(1)

    all_raw_items: List[Dict[str, Any]] = []

    endpoints = [
        ("image", "https://pixabay.com/api/", {"orientation": "vertical"}),
        ("video", "https://pixabay.com/api/videos/", {}),
    ]

    print("Querying Pixabay API for portrait assets...")
    for category, queries in THEMATIC_QUERIES.items():
        for query in queries:
            for media_type, endpoint, extra_params in endpoints:
                for page in range(1, args.max_pages + 1):
                    params = {
                        "q": query,
                        "safesearch": "true",
                        "per_page": args.per_page,
                        "page": page,
                        **extra_params,
                    }
                    try:
                        data = fetch_pixabay_api(endpoint, params, args.api_key)
                        hits = data.get("hits", [])
                        if not hits:
                            break
                        for hit in hits:
                            all_raw_items.append({"category": category, "type": media_type, "item": hit})
                        if len(hits) < args.per_page:
                            break
                    except Exception as e:
                        print(f"Failed to query {media_type}s for '{query}' (page {page}): {e}", file=sys.stderr)
                        break

    manifest = build_manifest_data(all_raw_items)
    print(f"Generated manifest with {len(manifest['backgrounds'])} portrait items.")

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(f"Saved to {args.output}")


if __name__ == "__main__":
    main()
