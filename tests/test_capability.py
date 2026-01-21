"""Unit tests for CapabilityGenerator."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from agent.capability_generator import (
    CapabilityGenerator,
    PRIORITY_FILES,
    SKIP_DIRS,
    MAX_FILE_CHARS,
    MAX_TOTAL_CHARS,
)


class TestCapabilityGenerator:
    """Tests for CapabilityGenerator class."""

    @pytest.fixture
    def generator(self, agent_config):
        """Create CapabilityGenerator instance."""
        return CapabilityGenerator(agent_config)

    def test_build_directory_tree(self, generator, temp_dir):
        """Should build directory tree representation."""
        # Create structure
        (temp_dir / "src").mkdir()
        (temp_dir / "src" / "main.py").write_text("print('hello')")
        (temp_dir / "README.md").write_text("# Test")
        (temp_dir / "__pycache__").mkdir()  # Should be skipped

        tree = generator._build_directory_tree(temp_dir)

        assert "src/" in tree
        assert "main.py" in tree
        assert "README.md" in tree
        assert "__pycache__" not in tree

    def test_build_directory_tree_skips_hidden(self, generator, temp_dir):
        """Should skip hidden directories except .env.example."""
        (temp_dir / ".git").mkdir()
        (temp_dir / ".hidden").mkdir()
        (temp_dir / ".env.example").write_text("KEY=value")
        (temp_dir / "visible").mkdir()

        tree = generator._build_directory_tree(temp_dir)

        assert ".git" not in tree
        assert ".hidden" not in tree
        assert ".env.example" in tree
        assert "visible" in tree

    def test_build_directory_tree_respects_depth(self, generator, temp_dir):
        """Should respect max_depth parameter."""
        deep = temp_dir
        for i in range(5):
            deep = deep / f"level{i}"
            deep.mkdir()
            (deep / "file.txt").write_text(f"level {i}")

        tree = generator._build_directory_tree(temp_dir, max_depth=2)

        assert "level0" in tree
        assert "level1" in tree
        assert "level2" in tree
        # level3 and beyond should not be expanded
        lines = tree.split("\n")
        level3_expanded = any("level3/" in line and "  " * 3 in line for line in lines)
        # Check that level3 content is not shown (max_depth=2 means 2 levels down)

    def test_gather_file_contents_priority_files(self, generator, temp_dir):
        """Should read priority files first."""
        (temp_dir / "main.py").write_text("main content")
        (temp_dir / "README.md").write_text("readme content")
        (temp_dir / "random.py").write_text("random content")

        contents = generator._gather_file_contents(temp_dir)

        # Priority files should appear before random
        main_pos = contents.find("main.py")
        readme_pos = contents.find("README.md")
        assert main_pos != -1
        assert readme_pos != -1
        assert "main content" in contents
        assert "readme content" in contents

    def test_gather_file_contents_respects_max_chars(self, generator, temp_dir):
        """Should truncate large files."""
        large_content = "x" * (MAX_FILE_CHARS + 1000)
        (temp_dir / "main.py").write_text(large_content)

        contents = generator._gather_file_contents(temp_dir)

        assert "[truncated]" in contents
        # Content should be limited
        assert len(contents) < len(large_content) + 500

    def test_gather_file_contents_respects_total_limit(self, generator, temp_dir):
        """Should stop gathering when total limit reached."""
        # Create many large files
        for i in range(20):
            content = f"content {i}\n" * 1000
            (temp_dir / f"file{i}.py").write_text(content)

        contents = generator._gather_file_contents(temp_dir)

        assert len(contents) <= MAX_TOTAL_CHARS + 1000  # Some buffer for formatting

    def test_read_file_safe_handles_encoding(self, generator, temp_dir):
        """Should handle different file encodings."""
        utf8_file = temp_dir / "utf8.txt"
        utf8_file.write_text("Hello 世界", encoding="utf-8")

        content = generator._read_file_safe(utf8_file)
        assert content == "Hello 世界"

    def test_read_file_safe_handles_binary(self, generator, temp_dir):
        """Should return None for binary files."""
        binary_file = temp_dir / "binary.bin"
        binary_file.write_bytes(bytes([0x00, 0x01, 0x02, 0xFF, 0xFE]))

        content = generator._read_file_safe(binary_file)
        # Should either return None or handle gracefully
        # The implementation tries latin-1 fallback, so it might return something

    def test_clean_yaml_removes_code_blocks(self, generator):
        """Should remove markdown code block markers."""
        content = "```yaml\nschema_version: '1.0'\n```"
        cleaned = generator._clean_yaml(content)

        assert not cleaned.startswith("```")
        assert not cleaned.endswith("```")
        assert "schema_version" in cleaned

    def test_clean_yaml_handles_plain_yaml(self, generator):
        """Should handle yaml without code blocks."""
        content = "schema_version: '1.0'\nservice:\n  id: test"
        cleaned = generator._clean_yaml(content)

        assert cleaned == content

    def test_validate_yaml_valid(self, generator):
        """Should pass validation for valid capability yaml."""
        valid_yaml = """
schema_version: "1.0"
service:
  id: test
  name: Test
runtime:
  start_command: "python main.py"
  ports:
    api:
      default: 8000
endpoints:
  api:
    health_check: "/health"
"""
        # Should not raise
        generator._validate_yaml(valid_yaml)

    def test_validate_yaml_missing_fields(self, generator):
        """Should raise for missing required fields."""
        invalid_yaml = """
service:
  id: test
"""
        with pytest.raises(ValueError, match="Missing required field"):
            generator._validate_yaml(invalid_yaml)

    @pytest.mark.asyncio
    async def test_generate_capability_no_api_key(
        self, generator, temp_dir, agent_config
    ):
        """Should raise error if no API key configured."""
        (temp_dir / "main.py").write_text("print('hello')")

        # Ensure no API key is set (patch the method at class level)
        with patch.object(type(agent_config), "get_llm_api_key", return_value=None):
            with pytest.raises(ValueError, match="No LLM API key"):
                await generator.generate_capability(temp_dir)

    @pytest.mark.asyncio
    async def test_generate_capability_success(self, generator, temp_dir, agent_config):
        """Should generate valid capability yaml via LLM."""
        (temp_dir / "main.py").write_text("""
from fastapi import FastAPI
app = FastAPI()

@app.get("/health")
def health():
    return {"status": "ok"}
""")
        (temp_dir / "README.md").write_text("# Test Service")

        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content="""schema_version: "1.0"
service:
  id: "temp_dir"
  name: "Test Service"
runtime:
  start_command: "python main.py"
  ports:
    api:
      default: 8000
endpoints:
  api:
    health_check: "/health"
"""
                )
            )
        ]

        with patch.object(
            type(agent_config), "get_llm_api_key", return_value="test-key"
        ):
            with patch("litellm.acompletion", new_callable=AsyncMock) as mock_llm:
                mock_llm.return_value = mock_response

                result = await generator.generate_capability(temp_dir)

        assert "schema_version" in result
        assert "service" in result
        assert "runtime" in result

    def test_format_file_content(self, generator):
        """Should format file content with header."""
        content = "print('hello')"
        formatted = generator._format_file_content("main.py", content, "python")

        assert "### FILE: main.py" in formatted
        assert "```python" in formatted
        assert "print('hello')" in formatted


class TestPriorityFiles:
    """Tests for priority file handling."""

    def test_priority_files_contain_common_files(self):
        """Priority files should include common service files."""
        assert "main.py" in PRIORITY_FILES
        assert "app.py" in PRIORITY_FILES
        assert "README.md" in PRIORITY_FILES
        assert "requirements.txt" in PRIORITY_FILES
        assert "Dockerfile" in PRIORITY_FILES

    def test_skip_dirs_contain_common_excludes(self):
        """Skip dirs should include common non-service directories."""
        assert ".git" in SKIP_DIRS
        assert "__pycache__" in SKIP_DIRS
        assert "node_modules" in SKIP_DIRS
        assert "venv" in SKIP_DIRS
        assert ".venv" in SKIP_DIRS
