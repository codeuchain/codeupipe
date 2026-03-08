"""
KoyebAdapter: Deploy adapter for Koyeb (https://koyeb.com).

Generates koyeb.yaml for Koyeb deployment:
- Free nano instance (always-on, no cold starts)
- Free managed Postgres (Neon-powered)
- Docker or buildpack-based deployment
- Global edge network

Zero external dependencies — pure string template generation.

Usage:
    cup deploy koyeb cup.toml
    cup deploy koyeb cup.toml --dry-run
"""

import json
from pathlib import Path
from typing import List

from .adapter import DeployAdapter, DeployTarget

__all__ = ["KoyebAdapter"]


class KoyebAdapter(DeployAdapter):
    """Generates koyeb.yaml for Koyeb deployment."""

    def target(self) -> DeployTarget:
        return DeployTarget(
            name="koyeb",
            description="Koyeb — free nano instance, always-on, free Postgres, global edge",
            requires=["koyeb"],
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
        region = options.get("region", "was")

        # 1. koyeb.yaml
        koyeb_yaml = self._render_koyeb_yaml(project_name, port, region, pipeline_config)
        koyeb_path = output_dir / "koyeb.yaml"
        koyeb_path.write_text(koyeb_yaml)
        generated.append(koyeb_path)

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
                f"[dry-run] Would deploy {output_dir} to Koyeb\n"
                f"Config: {output_dir}/koyeb.yaml\n"
                f"Steps:\n"
                f"  1. koyeb app init\n"
                f"  2. koyeb service create\n"
                f"  3. Free tier — 1 nano instance, always-on"
            )

        return (
            f"Koyeb artifacts generated in {output_dir}/\n"
            f"\n"
            f"Deploy steps:\n"
            f"  1. cd {output_dir}\n"
            f"  2. koyeb app init <app-name>\n"
            f"  3. koyeb service create <app-name>/<service> \\\n"
            f"       --docker . --port {options.get('port', 8080)} \\\n"
            f"       --instance-type free\n"
            f"\n"
            f"Or connect your GitHub repo in the Koyeb dashboard.\n"
            f"\n"
            f"Free tier: 1 nano instance (always-on) + 1 free Postgres DB."
        )

    # ── Internal ────────────────────────────────────────────────

    @staticmethod
    def _render_koyeb_yaml(
        project_name: str,
        port: int,
        region: str,
        pipeline_config: dict,
    ) -> str:
        connectors = pipeline_config.get("connectors", {})
        has_postgres = any(
            c.get("provider") == "postgres" for c in connectors.values()
        )

        lines = [
            "# Auto-generated Koyeb config by cup deploy",
            "# Docs: https://www.koyeb.com/docs/build-and-deploy/deploy-to-koyeb-button",
            f"name: {project_name}",
            "type: web",
            "",
            "build:",
            "  type: dockerfile",
            '  dockerfile: "Dockerfile"',
            "",
            "service:",
            "  instance_type: free",
            f"  regions:",
            f"    - {region}",
            "  ports:",
            f"    - port: {port}",
            "      protocol: http",
            "  routes:",
            "    - path: /",
            f"      port: {port}",
            "  health_checks:",
            "    - type: http",
            "      path: /",
            f"      port: {port}",
        ]

        env_vars = []
        for name, connector in connectors.items():
            if connector.get("provider") == "postgres" and has_postgres:
                env_vars.append(
                    f"    # Connect a Koyeb Postgres database in the dashboard"
                )
                env_vars.append(
                    f"    # DATABASE_URL will be auto-injected"
                )
            else:
                for key in connector.get("env", {}):
                    env_vars.append(f"    - key: {key}")
                    env_vars.append(f'      value: ""')

        if env_vars:
            lines.append("  env:")
            lines.extend(env_vars)

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
            '"""Auto-generated pipeline entrypoint by cup deploy (Koyeb)."""\n'
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
