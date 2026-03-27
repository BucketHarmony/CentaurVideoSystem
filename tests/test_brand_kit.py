"""Tests for brand kit loading and validation."""

import json
import pytest
from pathlib import Path


class TestBrandKitSchema:
    def test_demo_brand_loads(self, brand_kit):
        assert brand_kit["name"] == "CVS Demo"

    def test_required_fields(self, brand_kit):
        assert "name" in brand_kit
        assert "brand" in brand_kit
        assert "rules" in brand_kit

    def test_colors_valid_hex(self, brand_kit):
        colors = brand_kit["brand"]["colors"]
        for name in ["primary", "secondary", "accent"]:
            color = colors[name]
            assert color.startswith("#"), f"{name} should be hex color"
            assert len(color) == 7, f"{name} should be #RRGGBB"
            int(color[1:], 16)  # Should not raise

    def test_tone_is_string(self, brand_kit):
        assert isinstance(brand_kit["brand"]["tone"], str)
        assert len(brand_kit["brand"]["tone"]) > 0

    def test_rules_are_list(self, brand_kit):
        assert isinstance(brand_kit["rules"], list)
        assert len(brand_kit["rules"]) > 0
        for rule in brand_kit["rules"]:
            assert isinstance(rule, str)

    def test_style_section(self, brand_kit):
        style = brand_kit.get("style", {})
        assert "aspect_ratio" in style
        assert "duration_target" in style


class TestBrandKitColorParsing:
    def test_hex_to_rgb(self, brand_kit):
        """Brand colors should convert to valid RGB tuples."""
        for color_hex in brand_kit["brand"]["colors"].values():
            r = int(color_hex[1:3], 16)
            g = int(color_hex[3:5], 16)
            b = int(color_hex[5:7], 16)
            assert 0 <= r <= 255
            assert 0 <= g <= 255
            assert 0 <= b <= 255

    def test_primary_is_crimson(self, brand_kit):
        """Demo brand primary should be crimson (#DC143C)."""
        assert brand_kit["brand"]["colors"]["primary"] == "#DC143C"


class TestAllBrandKitsValid:
    def test_all_json_brand_files(self, root_dir):
        """Every brand JSON in the repo should be valid."""
        brand_files = list(root_dir.rglob("*brand*.json"))
        assert len(brand_files) > 0, "No brand files found"
        for bf in brand_files:
            with open(bf) as f:
                data = json.load(f)
            assert "name" in data, f"{bf} missing 'name'"
            assert "brand" in data, f"{bf} missing 'brand'"
