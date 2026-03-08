"""
HuggingFaceAdapter: Deploy adapter for Hugging Face Spaces (https://huggingface.co/spaces).

Generates Dockerfile + README.md for HF Spaces deployment:
- Free CPU tier for ML/AI demos
- Docker SDK runtime (port 7860)
- Git-based deployment via HF Hub
- Ideal for showcasing AI pipelines

Zero external dependencies — pure string template generation.

Usage:
    cup deploy hf-spaces cup.toml
    cup deploy hf-spaces cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["HuggingFaceAdapter"]


class HuggingFaceAdapter(DeployAdapter):
    """Generates Dockerfile + README.md for Hugging Face Spaces deployment."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="hf-spaces",
            description="Hugging Face Spaces — free CPU tier, Docker SDK, ideal for AI demos",
            requires=["git"],
        )

    def validate(self, pipeline_config: dict, **options) -> List[str]:
        issues = []
        has_pipeline = "pipeline" in pipeline_config
        has_frontend = "frontend" in pipeline_config
        if not has_pipeline and not has_frontend:
            issues.append("Config needs 'pipeline' and/or 'frontend' section")
        if has_pipeline and "steps" not in pipeline_config.get("pipeline", {}):
            issues.append("Config 'pipeline' missing 'steps'")
        return issues

    def generate(self, pipeline_config: dict, output_dir: Path, **options) -> List[Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        generated: List[Path] = []

        project_name = pipeline_config.get("project", {}).get("name", "my-app")
        port = 7860  # HF Spaces expects port 7860
        python_version = options.get("python_version", "3.12")

        # 1. README.md with HF Spaces metadata
        readme_path = output_dir / "README.md"
        readme_path.write_text(self._render_readme(project_name))
        generated.append(readme_path)

        # 2. Dockerfile (must expose 7860)
        dockerfile_path = output_dir / "Dockerfile"
        dockerfile_path.write_text(self._render_dockerfile(port, python_version))
        generated.append(dockerfile_path)

        # 3. Pipeline config
        config_path = output_dir / "pipeline.json"
        config_path.write_text(json.dumps(pipeline_config, indent=2))
        generated.append(config_path)

        # 4. Entrypoint
        entrypoint_path = output_dir / "entrypoint.py"
        entrypoint_path.write_text(self._render_entrypoint(port))
        generated.append(entrypoint_path)

        # 5. Requirements
        reqs_path = output_dir / "requirements.txt"
        reqs_path.write_text(self._render_requirements(pipeline_config))
        generated.append(reqs_path)

        return generated

    def deploy(self, output_dir: Path, *, dry_run: bool = False, **options) -> str:
        hf_user = options.get("hf_user", "YOUR_HF_USERNAME")
        space_name = options.get("space_name", "my-pipeline")

        if dry_run:
            return (
                f"[dry-run] Would deploy {output_dir} to Hugging Face Spaces\n"
                f"Space: {hf_user}/{space_name}\n"
                f"Steps:\n"
                f"  1. Create Space on huggingface.co\n"
                f"  2. git push to Space repo\n"
                f"  3. Free CPU tier available"
            )

        return (
            f"Hugging Face Spaces artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. Create a new Space on huggingface.co/new-space\n"
            f'     - SDK: "Docker"\n'
            f"     - Hardware: Free CPU\n"
            f"  2. Clone and push:\n"
            f"       git clone https://huggingface.co/spaces/{hf_user}/{space_name}\n"
            f"       cp -r {output_dir}/* {space_name}/\n"
            f"       cd {space_name} && git add . && git commit -m 'cup deploy' && git push\n"
            f"\n"
            f"Your Space will be live at:\n"
            f"  https://huggingface.co/spaces/{hf_user}/{space_name}\n"
            f"\n"
            f"Free CPU tier — 2 vCPU, 16 GB RAM. Upgrade for GPU."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_readme(project_name: str) -> str:
        return (
            "---\n"
            f"title: {project_name}\n"
            "emoji: \U0001f680\n"
            "colorFrom: blue\n"
            "colorTo: purple\n"
            "sdk: docker\n"
            "pinned: false\n"
            "---\n"
            "\n"
            f"# {project_name}\n"
            "\n"
            "A codeupipe pipeline deployed to Hugging Face Spaces.\n"
            "\n"
            "## Endpoints\n"
            "\n"
            "- `GET /` — Health check\n"
            "- `POST /` — Run pipeline with JSON body\n"
            "\n"
            "Built with [codeupipe](https://github.com/codeuchain/codeupipe).\n"
        )

    @staticmethod
    def _render_dockerfile(port: int, python_version: str) -> str:
        return (
            f"FROM python:{python_version}-slim\n"
            "\n"
            "# HF Spaces requires non-root user\n"
            "RUN useradd -m -u 1000 user\n"
            "\n"
            "WORKDIR /app\n"
            "\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "\n"
            "COPY . .\n"
            "\n"
            "RUN chown -R user:user /app\n"
            "USER user\n"
            "\n"
            f"EXPOSE {port}\n"
            'CMD ["python", "entrypoint.py"]\n'
        )

    @staticmethod
    def _render_entrypoint(port: int) -> str:
        return (
            '"""Auto-generated pipeline entrypoint by cup deploy (HF Spaces)."""\n'
            "import asyncio\n"
            "import json\n"
            "import os\n"
            "from http.server import HTTPServer, BaseHTTPRequestHandler\n"
            "from pathlib import Path\n"
            "\n"
            "from codeupipe import Pipeline, Payload\n"
            "from codeupipe.registry import default_registry\n"
            "\n"
            "\n"
            'CONFIG_PATH = Path(__file__).parent / "pipeline.json"\n'
            "\n"
            "\n"
            "def _load_pipeline():\n"
            '    return Pipeline.from_config(str(CONFIG_PATH), registry=default_registry)\n'
            "\n"
            "\n"
            "def main():\n"
            "    pipeline = _load_pipeline()\n"
            f"    port = int(os.environ.get('PORT', {port}))\n"
            "\n"
            "    class Handler(BaseHTTPRequestHandler):\n"
            "        def do_POST(self):\n"
            "            length = int(self.headers.get('Content-Length', 0))\n"
            "            body = self.rfile.read(length) if length else b'{}'\n"
            "            data = json.loads(body)\n"
            "            result = asyncio.run(pipeline.run(Payload(data)))\n"
            "            response = json.dumps(result.to_dict()).encode()\n"
            "            self.send_response(200)\n"
            "            self.send_header('Content-Type', 'application/json')\n"
            "            self.send_header('Content-Length', str(len(response)))\n"
            "            self.end_headers()\n"
            "            self.wfile.write(response)\n"
            "\n"
            "        def do_GET(self):\n"
            "            self.send_response(200)\n"
            "            self.send_header('Content-Type', 'application/json')\n"
            '            body = b\'{"status": "ok"}\'\n'
            "            self.send_header('Content-Length', str(len(body)))\n"
            "            self.end_headers()\n"
            "            self.wfile.write(body)\n"
            "\n"
            '    server = HTTPServer(("0.0.0.0", port), Handler)\n'
            '    print(f"Pipeline server listening on 0.0.0.0:{port}")\n'
            "    server.serve_forever()\n"
            "\n"
            "\n"
            'if __name__ == "__main__":\n'
            "    main()\n"
        )

    @staticmethod
    def _render_requirements(pipeline_config: dict) -> str:
        lines = ["codeupipe"]
        deps = pipeline_config.get("dependencies", {})
        for pkg in deps:
            if isinstance(deps[pkg], str):
                lines.append(f"{pkg}{deps[pkg]}")
            else:
                lines.append(pkg)
        return "\n".join(lines) + "\n"
