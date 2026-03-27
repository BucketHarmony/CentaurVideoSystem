"""Security tests — ensure no secrets leak into tracked files."""

import re
import subprocess
import pytest
from pathlib import Path


class TestNoSecretsInRepo:
    @pytest.fixture
    def tracked_files(self, root_dir):
        """Get list of git-tracked files."""
        result = subprocess.run(
            ["git", "ls-files"],
            capture_output=True, text=True, cwd=root_dir
        )
        return [root_dir / f for f in result.stdout.strip().split("\n") if f]

    def test_no_api_keys(self, tracked_files):
        """No ElevenLabs or other API keys in tracked files."""
        pattern = re.compile(r"sk_[a-f0-9]{20,}")
        for f in tracked_files:
            if f.suffix in (".py", ".json", ".yaml", ".yml", ".md", ".bat"):
                content = f.read_text(encoding="utf-8", errors="ignore")
                matches = pattern.findall(content)
                assert not matches, f"API key found in {f.name}: {matches[0][:20]}..."

    def test_no_app_passwords(self, tracked_files):
        """No Bluesky/Gmail app passwords in tracked code files."""
        pw_pattern = re.compile(r"[a-z]{4}-[a-z]{4}-[a-z]{4}-[a-z]{4}")
        for f in tracked_files:
            if f.suffix in (".py", ".json", ".yaml"):
                content = f.read_text(encoding="utf-8", errors="ignore")
                matches = pw_pattern.findall(content)
                for m in matches:
                    # Allow "your-pass-word-here" style placeholders
                    if "your" in m or "example" in m or "pass" in m:
                        continue
                    assert False, f"Possible password in {f.name}: {m}"

    def test_env_file_gitignored(self, root_dir):
        """The .env file should be in .gitignore."""
        gitignore = (root_dir / ".gitignore").read_text()
        assert ".env" in gitignore

    def test_env_example_exists(self, root_dir):
        """There should be a .env.example with placeholders."""
        example = root_dir / ".env.example"
        assert example.exists()
        content = example.read_text()
        assert "your_" in content or "here" in content

    def test_no_hardcoded_local_paths_in_python(self, tracked_files):
        """No E:\\AI\\ or E:/AI/ paths in tracked Python files."""
        pattern = re.compile(r"[\"']E:[/\\]+AI[/\\]", re.IGNORECASE)
        for f in tracked_files:
            if f.suffix == ".py":
                content = f.read_text(encoding="utf-8", errors="ignore")
                matches = pattern.findall(content)
                assert not matches, \
                    f"Hardcoded local path in {f.name}: {matches[0]}"
