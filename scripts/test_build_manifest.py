#!/usr/bin/env python3
"""
Unit tests for the Pixabay Portrait-Only Manifest Build Pipeline.
Tests dimension validation, Islamic compliance whole-word blocklist filtering,
media tier selection, and deduplication.
"""

import unittest
from build_manifest import (
    BLOCKLIST,
    is_portrait,
    is_islamic_compliant,
    tokenize_text,
    process_image_item,
    process_video_item,
    build_manifest_data,
)


class TestPortraitValidation(unittest.TestCase):
    def test_portrait_dimensions(self):
        # Strictly height > width
        self.assertTrue(is_portrait(1080, 1920))
        self.assertTrue(is_portrait(720, 1280))
        self.assertTrue(is_portrait(1000, 1500))

    def test_reject_landscape_and_square(self):
        # Landscape
        self.assertFalse(is_portrait(1920, 1080))
        self.assertFalse(is_portrait(1280, 720))
        # Square
        self.assertFalse(is_portrait(1080, 1080))
        self.assertFalse(is_portrait(500, 500))
        # Zero or invalid
        self.assertFalse(is_portrait(0, 1920))
        self.assertFalse(is_portrait(1080, 0))
        self.assertFalse(is_portrait(None, 1920))


class TestIslamicComplianceBlocklist(unittest.TestCase):
    def test_tokenize_text(self):
        tokens = tokenize_text("Waterfall, misty morning! Beautiful Nature.")
        self.assertIn("waterfall", tokens)
        self.assertIn("misty", tokens)
        self.assertIn("morning", tokens)
        self.assertIn("beautiful", tokens)
        self.assertIn("nature", tokens)

    def test_blocks_explicit_tokens(self):
        blocked_samples = [
            ("woman smiling in park", ["nature", "woman", "park"]),
            ("portrait of a young girl", ["girl", "face"]),
            ("men walking on mountain", ["men", "hiking"]),
            ("temple in ancient valley", ["valley", "temple"]),
            ("church at sunset", ["architecture", "church"]),
            ("wine glass at dinner", ["wine", "drink"]),
            ("dog running in field", ["dog", "pet"]),
            ("ancient sculpture of warrior", ["statue", "sculpture"]),
            ("celebration and party", ["party", "dance"]),
            ("cross on top of hill", ["cross", "hill"]),
        ]
        for title, tags in blocked_samples:
            self.assertFalse(
                is_islamic_compliant(tags=tags, title=title),
                f"Expected '{title}' / {tags} to be blocked"
            )

    def test_avoids_false_positives_on_substrings(self):
        # Words containing substrings of blocked words should NOT be blocked:
        # 'manifest' contains 'man'
        # 'demanding' contains 'man'
        # 'management' contains 'man'
        # 'command' contains 'man'
        # 'peacock' should not match
        # 'crossroad' or 'crossroads' vs 'cross'
        allowed_samples = [
            ("Manifestation of morning light", ["mist", "manifest", "light"]),
            ("Permanent mountain range", ["mountain", "range", "permanent"]),
            ("Commanding waterfall view", ["commanding", "waterfall"]),
            ("Historic architecture arch", ["arch", "mosaic", "historic"]),
            ("Emerald forest canopy", ["forest", "trees", "green"]),
        ]
        for title, tags in allowed_samples:
            self.assertTrue(
                is_islamic_compliant(tags=tags, title=title),
                f"Expected '{title}' / {tags} to be compliant"
            )


class TestMediaItemProcessing(unittest.TestCase):
    def test_process_valid_portrait_image(self):
        item = {
            "id": 12345,
            "tags": "waterfall, forest, peaceful",
            "imageWidth": 3000,
            "imageHeight": 4500,
            "webformatURL": "https://cdn.pixabay.com/photo/12345_1280.jpg",
            "webformatWidth": 853,
            "webformatHeight": 1280,
            "previewURL": "https://cdn.pixabay.com/photo/12345_150.jpg",
        }
        preset = process_image_item(item, category="nature")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["id"], "nature-image-12345")
        self.assertEqual(preset["type"], "image")
        self.assertEqual(preset["category"], "nature")
        self.assertEqual(preset["width"], 853)
        self.assertEqual(preset["height"], 1280)
        self.assertEqual(preset["mediaUrl"], "https://cdn.pixabay.com/photo/12345_1280.jpg")
        self.assertEqual(preset["thumbnailUrl"], "https://cdn.pixabay.com/photo/12345_150.jpg")
        self.assertIn("waterfall", preset["tags"]["en"])
        self.assertIn("forest", preset["tags"]["en"])
        self.assertIn("peaceful", preset["tags"]["en"])

    def test_reject_landscape_image(self):
        item = {
            "id": 67890,
            "tags": "desert, sunset",
            "imageWidth": 4500,
            "imageHeight": 3000,
            "webformatURL": "https://cdn.pixabay.com/photo/67890_1280.jpg",
            "webformatWidth": 1280,
            "webformatHeight": 853,
            "previewURL": "https://cdn.pixabay.com/photo/67890_150.jpg",
        }
        preset = process_image_item(item, category="desert")
        self.assertIsNone(preset)

    def test_reject_image_when_webformat_is_not_portrait(self):
        # Raw dimensions vertical, but webformat scaled to landscape
        item = {
            "id": 67891,
            "tags": "desert, sunset",
            "imageWidth": 3000,
            "imageHeight": 4500,
            "webformatURL": "https://cdn.pixabay.com/photo/67891_1280.jpg",
            "webformatWidth": 1280,
            "webformatHeight": 853,
            "previewURL": "https://cdn.pixabay.com/photo/67891_150.jpg",
        }
        preset = process_image_item(item, category="desert")
        self.assertIsNone(preset)

    def test_reject_image_with_blocked_keywords(self):
        item = {
            "id": 11111,
            "tags": "woman, forest, trees",
            "imageWidth": 3000,
            "imageHeight": 4500,
            "webformatURL": "https://cdn.pixabay.com/photo/11111_1280.jpg",
            "webformatWidth": 853,
            "webformatHeight": 1280,
            "previewURL": "https://cdn.pixabay.com/photo/11111_150.jpg",
        }
        preset = process_image_item(item, category="nature")
        self.assertIsNone(preset)

    def test_user_handle_does_not_falsely_block_compliant_item(self):
        # Photographer username contains a word like "dance_studio", but tags are clean
        item = {
            "id": 22222,
            "user": "dance_studio_films",
            "tags": "waterfall, mist, foliage",
            "imageWidth": 3000,
            "imageHeight": 4500,
            "webformatURL": "https://cdn.pixabay.com/photo/22222_1280.jpg",
            "webformatWidth": 853,
            "webformatHeight": 1280,
            "previewURL": "https://cdn.pixabay.com/photo/22222_150.jpg",
        }
        preset = process_image_item(item, category="nature")
        self.assertIsNotNone(preset)

    def test_process_valid_portrait_video_with_small_tier(self):
        item = {
            "id": 88888,
            "tags": "clouds, sky, sunset",
            "duration": 18,
            "picture_id": "99999",
            "videos": {
                "large": {
                    "url": "https://cdn.pixabay.com/video/88888_large.mp4",
                    "width": 2160,
                    "height": 3840,
                    "size": 15000000,
                },
                "small": {
                    "url": "https://cdn.pixabay.com/video/88888_small.mp4",
                    "width": 1080,
                    "height": 1920,
                    "size": 2500000,
                },
                "tiny": {
                    "url": "https://cdn.pixabay.com/video/88888_tiny.mp4",
                    "width": 540,
                    "height": 960,
                    "size": 800000,
                },
            },
        }
        preset = process_video_item(item, category="atmospheric")
        self.assertIsNotNone(preset)
        self.assertEqual(preset["id"], "atmospheric-video-88888")
        self.assertEqual(preset["type"], "video")
        self.assertEqual(preset["category"], "atmospheric")
        self.assertEqual(preset["mediaUrl"], "https://cdn.pixabay.com/video/88888_small.mp4")
        self.assertEqual(preset["width"], 1080)
        self.assertEqual(preset["height"], 1920)
        self.assertEqual(preset["duration"], 18)
        self.assertIn("clouds", preset["tags"]["en"])

    def test_reject_video_without_portrait_small_tier(self):
        # Even if large is portrait, missing or landscape small tier rejects video
        item = {
            "id": 88889,
            "tags": "clouds, sky",
            "duration": 15,
            "videos": {
                "large": {
                    "url": "https://cdn.pixabay.com/video/88889_large.mp4",
                    "width": 2160,
                    "height": 3840,
                },
                "small": {
                    "url": "https://cdn.pixabay.com/video/88889_small.mp4",
                    "width": 1920,
                    "height": 1080,
                },
            },
        }
        preset = process_video_item(item, category="atmospheric")
        self.assertIsNone(preset)

    def test_reject_landscape_video(self):
        item = {
            "id": 77777,
            "tags": "ocean, waves",
            "duration": 12,
            "videos": {
                "large": {
                    "url": "https://cdn.pixabay.com/video/77777_large.mp4",
                    "width": 3840,
                    "height": 2160,
                },
                "small": {
                    "url": "https://cdn.pixabay.com/video/77777_small.mp4",
                    "width": 1920,
                    "height": 1080,
                },
            },
        }
        preset = process_video_item(item, category="nature")
        self.assertIsNone(preset)


class TestManifestDeduplicationAndAggregation(unittest.TestCase):
    def test_deduplication_by_id(self):
        raw_items_batch_1 = [
            {
                "category": "nature",
                "type": "image",
                "item": {
                    "id": 100,
                    "tags": "rain, leaves",
                    "imageWidth": 2000,
                    "imageHeight": 3000,
                    "webformatURL": "https://cdn.pixabay.com/100_1280.jpg",
                    "webformatWidth": 800,
                    "webformatHeight": 1200,
                    "previewURL": "https://cdn.pixabay.com/100_thumb.jpg",
                },
            },
            {
                "category": "atmospheric",
                "type": "image",
                "item": {
                    "id": 200,
                    "tags": "fog, mountains",
                    "imageWidth": 2000,
                    "imageHeight": 3000,
                    "webformatURL": "https://cdn.pixabay.com/200_1280.jpg",
                    "webformatWidth": 800,
                    "webformatHeight": 1200,
                    "previewURL": "https://cdn.pixabay.com/200_thumb.jpg",
                },
            },
        ]
        # Duplicate of id 100 in another category query
        raw_items_batch_2 = [
            {
                "category": "sacred",
                "type": "image",
                "item": {
                    "id": 100,
                    "tags": "rain, leaves, quiet",
                    "imageWidth": 2000,
                    "imageHeight": 3000,
                    "webformatURL": "https://cdn.pixabay.com/100_1280.jpg",
                    "webformatWidth": 800,
                    "webformatHeight": 1200,
                    "previewURL": "https://cdn.pixabay.com/100_thumb.jpg",
                },
            },
        ]

        manifest = build_manifest_data(raw_items_batch_1 + raw_items_batch_2)
        backgrounds = manifest["backgrounds"]
        self.assertEqual(len(backgrounds), 2)
        ids = [b["id"] for b in backgrounds]
        self.assertIn("nature-image-100", ids)
        self.assertIn("atmospheric-image-200", ids)


if __name__ == "__main__":
    unittest.main()
