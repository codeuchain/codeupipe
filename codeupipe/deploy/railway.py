"""
RailwayAdapter: Deploy adapter for Railway (https://railway.app).

Generates railway.json for Railway deployment:
- Docker or Nixpacks-based build
- Optional Railway Postgres plugin
- No cold starts — always-on
- One-click deploy from GitHub

Zero external dependencies — pure string template generation.

Usage:
    cup deploy railway cup.toml
    cup deploy railway cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["RailwayAdapter"]


class RailwayAdapter(DeployAdapter):
    """Generates railway.json for Railway deployment."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="railway",
            description="Railway — zero-config deploys, no cold starts, Postgres plugin",
            requires=["railway"],
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

        # 1. railway.json
        railway_json = self._render_railway_json(project_name, port, pipeline_config)
        railway_path = output_dir / "railway.json"
        railway_path.write_text(json.dumps(railway_json, indent=2))
        generated.append(railway_path)

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
                f"[dry-run] Would deploy {output_dir} to Railway\n"
                f"Config: {output_dir}/railway.json\n"
                f"Steps:\n"
                f"  1. railway init\n"
                f"  2. railway up\n"
                f"  3. Starter plan — $5/mo with $5 free credit"
            )

        return (
            f"Railway artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. cd {output_dir}\n"
            f"  2. railway init\n"
            f"  3. railway up\n"
            f"  4. railway open\n"
            f"\n"
            f"Starter plan includes $5/mo free usage credit.\n"
            f"No cold starts — your service stays warm."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_railway_json(
        project_name: str,
        port: int,
        pipeline_config: dict,
    ) -> dict:
        connectors = pipeline_config.get("connectors", {})
        has_postgres = any(
            c.get("provider") == "postgres" for c in connectors.values()
        )

        config: dict = {
            "$schema": "https://railway.app/railway.schema.json",
            "build": {"builder": "DOCKERFILE", "dockerfilePath": "Dockerfile"},
            "deploy": {
                "startCommand": "python entrypoint.py",
                "restartPolicyType": "ON_FAILURE",
                "restartPolicyMaxRetries": 10,
            },
        }

        if has_postgres:
            config["deploy"]["healthcheckPath"] = "/"
            config["_comment"] = (
                "Add a Postgres plugin in the Railway dashboard. "
                "DATABASE_URL will be auto-injected."
            )

        return config

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
            '"""Auto-generated pipeline entrypoint by cup deploy (Railway)."""\n'
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
