import subprocess
import sys
from pathlib import Path

TWO_LAYER_YAML = """\
layers:
  - id: L0
    name: Services
    description: Service layer
    sources:
      - path: __L0_SRC__
    aggregation:
      strategy: none
  - id: L1
    name: System
    description: System layer
    parent: L0
    sources:
      - path: __L1_SRC__
    aggregation:
      strategy: none
"""


def _setup_fixture(tmp_path: Path) -> Path:
    l0_dir = tmp_path / "services"
    l1_dir = tmp_path / "system"
    l0_dir.mkdir()
    l1_dir.mkdir()

    (l0_dir / "auth.py").write_text(
        "class AuthService:\n    def login(self): pass\n",
        encoding="utf-8",
    )
    (l1_dir / "app.py").write_text(
        "class Application:\n    def run(self): pass\n",
        encoding="utf-8",
    )

    yaml_content = TWO_LAYER_YAML.replace("__L0_SRC__", str(l0_dir)).replace(
        "__L1_SRC__", str(l1_dir)
    )
    config_path = tmp_path / "layers.yaml"
    config_path.write_text(yaml_content, encoding="utf-8")
    return config_path


def _run_graphify(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        capture_output=True,
        text=True,
        cwd=cwd,
    )


class TestCLIBuildWithLayers:
    def test_build_with_layers_flag(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Layer build complete" in result.stdout

        out_root = tmp_path / "graphify-out"
        assert (out_root / "layers" / "L0" / "graph.json").exists()
        assert (out_root / "layers" / "L1" / "graph.json").exists()

    def test_build_with_layer_flag(self, tmp_path):
        config_path = _setup_fixture(tmp_path)
        result = _run_graphify("build", "--layers", str(config_path), cwd=str(tmp_path))
        assert result.returncode == 0

        result2 = _run_graphify(
            "build", "--layers", str(config_path), "--layer", "L1", cwd=str(tmp_path)
        )
        assert result2.returncode == 0, f"stderr: {result2.stderr}"

    def test_build_without_layers_exits_error(self, tmp_path):
        result = _run_graphify("build", cwd=str(tmp_path))
        assert result.returncode != 0

    def test_build_layers_file_not_found(self, tmp_path):
        result = _run_graphify(
            "build", "--layers", str(tmp_path / "nonexistent.yaml"), cwd=str(tmp_path)
        )
        assert result.returncode != 0
        assert "not found" in result.stderr

    def test_layer_without_layers_exits_error(self, tmp_path):
        result = _run_graphify("build", "--layer", "L0", cwd=str(tmp_path))
        assert result.returncode != 0
        assert "--layer requires --layers" in result.stderr
