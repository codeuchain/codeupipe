"""
AppRunnerAdapter: Deploy adapter for AWS App Runner (https://aws.amazon.com/apprunner/).

Generates apprunner.yaml for AWS App Runner deployment:
- Fully managed container service
- Auto-scales from source repo or ECR image
- Native AWS integration (IAM, VPC, Secrets Manager)
- Pay-per-use with automatic HTTPS

Zero external dependencies — pure string template generation.

Usage:
    cup deploy apprunner cup.toml
    cup deploy apprunner cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["AppRunnerAdapter"]


class AppRunnerAdapter(DeployAdapter):
    """Generates apprunner.yaml for AWS App Runner deployment."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="apprunner",
            description="AWS App Runner — fully managed containers, auto-scale, native AWS integration",
            requires=["aws"],
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
        port = options.get("port", 8080)
        python_version = options.get("python_version", "3.12")

        # 1. apprunner.yaml
        apprunner_yaml = self._render_apprunner_yaml(project_name, port, pipeline_config)
        apprunner_path = output_dir / "apprunner.yaml"
        apprunner_path.write_text(apprunner_yaml)
        generated.append(apprunner_path)

        # 2. Dockerfile
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
        if dry_run:
            return (
                f"[dry-run] Would deploy {output_dir} to AWS App Runner\n"
                f"Config: {output_dir}/apprunner.yaml\n"
                f"Steps:\n"
                f"  1. aws apprunner create-service\n"
                f"  2. Push image to ECR or connect GitHub repo\n"
                f"  3. Automatic HTTPS + auto-scaling"
            )

        return (
            f"AWS App Runner artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. Push Docker image to ECR:\n"
            f"       docker build -t <ecr-repo>:latest {output_dir}\n"
            f"       docker push <ecr-repo>:latest\n"
            f"  2. Create App Runner service via console or CLI:\n"
            f"       aws apprunner create-service --cli-input-yaml file://apprunner.yaml\n"
            f"\n"
            f"Or connect your GitHub repo in the App Runner console.\n"
            f"\n"
            f"Pricing: Auto-provisioned vCPU + memory. No charge when paused."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_apprunner_yaml(
        project_name: str,
        port: int,
        pipeline_config: dict,
    ) -> str:
        connectors = pipeline_config.get("connectors", {})

        lines = [
            "# Auto-generated AWS App Runner config by cup deploy",
            "# Docs: https://docs.aws.amazon.com/apprunner/latest/dg/",
            "version: 1.0",
            f"# Service: {project_name}",
            "",
            "runtime: python312",
            "",
            "build:",
            '  commands: "pip install -r requirements.txt"',
            "",
            "run:",
            '  command: "python entrypoint.py"',
            f"  network:",
            f"    port: {port}",
            "",
            "scaling:",
            "  min_size: 1",
            "  max_size: 10",
            "  max_concurrency: 100",
            "",
            "instance:",
            "  cpu: 1",
            "  memory: 2",
        ]

        # Environment variables from connectors
        env_lines = []
        for name, connector in connectors.items():
            for key in connector.get("env", {}):
                env_lines.append(f"    {key}: \"\"")

        if env_lines:
            lines.append("")
            lines.append("env:")
            lines.extend(env_lines)

        lines.append("")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _render_dockerfile(port: int, python_version: str) -> str:
        return (
            f"FROM python:{python_version}-slim\n"
            "\n"
            "WORKDIR /app\n"
            "\n"
            "COPY requirements.txt .\n"
            "RUN pip install --no-cache-dir -r requirements.txt\n"
            "\n"
            "COPY . .\n"
            "\n"
            f"EXPOSE {port}\n"
            'CMD ["python", "entrypoint.py"]\n'
        )

    @staticmethod
    def _render_entrypoint(port: int) -> str:
        return (
            '"""Auto-generated pipeline entrypoint by cup deploy (App Runner)."""\n'
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
