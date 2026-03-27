"""Tests for workflow JSON files — structure, validity, and schema."""

import json
import pytest
from pathlib import Path


class TestWorkflowJsonValidity:
    def test_all_json_files_parse(self, root_dir):
        """Every tracked JSON file should be valid JSON."""
        json_files = (
            list((root_dir / "scripts").glob("*.json"))
            + list((root_dir / "ComfyUI_Workflows").glob("*.json"))
            + list((root_dir / "comfyui-config" / "kombucha-pipeline").glob("*.json"))
        )
        assert len(json_files) > 0
        for jf in json_files:
            with open(jf) as f:
                data = json.load(f)
            assert isinstance(data, dict), f"{jf.name} should be a dict"


class TestComfyUIWorkflowStructure:
    """ComfyUI API workflows should have the right shape."""

    @pytest.fixture
    def api_workflows(self, root_dir):
        """Collect workflows that look like API-format (node dicts, not UI)."""
        workflows = {}
        for jf in (root_dir / "scripts").glob("workflow_*.json"):
            with open(jf) as f:
                data = json.load(f)
            # API format: keys are node IDs (strings of numbers)
            if any(k.isdigit() for k in data.keys()):
                workflows[jf.name] = data
        return workflows

    def test_api_workflows_have_class_type(self, api_workflows):
        """Each node in an API workflow should have class_type."""
        for name, wf in api_workflows.items():
            for node_id, node in wf.items():
                if not node_id.isdigit():
                    continue
                assert "class_type" in node, \
                    f"{name} node {node_id} missing class_type"

    def test_api_workflows_have_inputs(self, api_workflows):
        """Each node should have an inputs dict."""
        for name, wf in api_workflows.items():
            for node_id, node in wf.items():
                if not node_id.isdigit():
                    continue
                assert "inputs" in node, \
                    f"{name} node {node_id} missing inputs"
                assert isinstance(node["inputs"], dict)


class TestImageToTextWorkflow:
    def test_image_to_text_loads(self, root_dir):
        wf_path = root_dir / "ComfyUI_Workflows" / "image_to_text.json"
        with open(wf_path) as f:
            wf = json.load(f)
        assert "nodes" in wf
        assert "links" in wf

    def test_image_to_text_has_required_nodes(self, root_dir):
        wf_path = root_dir / "ComfyUI_Workflows" / "image_to_text.json"
        with open(wf_path) as f:
            wf = json.load(f)
        node_types = {n["type"] for n in wf["nodes"]}
        assert "LoadImage" in node_types
        assert "CLIPLoader" in node_types
        assert "TextGenerate" in node_types
        assert "PreviewAny" in node_types


class TestEpisodeConfigs:
    def test_episode_configs_valid(self, root_dir):
        """Episode JSON configs should have required fields."""
        config_dir = root_dir / "comfyui-config" / "kombucha-pipeline"
        configs = list(config_dir.glob("episode_*.json"))
        assert len(configs) > 0
        for cf in configs:
            with open(cf) as f:
                data = json.load(f)
            assert "number" in data or "title" in data, \
                f"{cf.name} missing number or title"
