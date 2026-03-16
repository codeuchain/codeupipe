"""``cup deploy``, ``cup recipe``, ``cup init``, ``cup ci`` commands."""

import json
import sys
from pathlib import Path

from .._registry import registry


def setup(sub, reg):
    # cup deploy [target] [config] [--dry-run] [--mode MODE] [--port PORT] [--output-dir DIR]
    deploy_parser = sub.add_parser("deploy", help="Generate deployment artifacts for a pipeline")
    deploy_parser.add_argument("target", nargs="?", default="docker", help="Deployment target (default: docker)")
    deploy_parser.add_argument("config", nargs="?", default="cup.toml", help="Pipeline config or cup.toml manifest (default: cup.toml)")
    deploy_parser.add_argument("--dry-run", action="store_true", help="Validate only — do not generate or deploy")
    deploy_parser.add_argument("--mode", choices=["http", "worker", "cli"], help="Execution mode override")
    deploy_parser.add_argument("--port", type=int, default=8080, help="Port for HTTP mode (default: 8080)")
    deploy_parser.add_argument("--output-dir", default="deploy_output", help="Directory for generated artifacts (default: deploy_output)")
    reg.register("deploy", _handle_deploy)

    # cup recipe [name] [--list] [--dry-run] [--var ...] [--output-dir]
    recipe_parser = sub.add_parser("recipe", help="Apply a recipe template to generate pipeline configs")
    recipe_parser.add_argument("name", nargs="?", help="Recipe name (omit with --list)")
    recipe_parser.add_argument("--list", action="store_true", dest="list_recipes", help="List available recipes")
    recipe_parser.add_argument("--dry-run", action="store_true", help="Show resolved config without writing files")
    recipe_parser.add_argument("--var", action="append", metavar="KEY=VALUE", default=[], help="Set a recipe variable (repeatable)")
    recipe_parser.add_argument("--output-dir", default="pipelines", help="Directory for generated pipeline config (default: pipelines)")
    reg.register("recipe", _handle_recipe)

    # cup init [template] [name] [--list] [--deploy TARGET] [--ci PROVIDER] ...
    init_parser = sub.add_parser("init", help="Scaffold a new codeupipe project from a template")
    init_parser.add_argument("template", nargs="?", help="Project template (saas, api, etl, chatbot). Omit with --list.")
    init_parser.add_argument("name", nargs="?", help="Project name")
    init_parser.add_argument("--list", action="store_true", dest="list_templates", help="List available project templates")
    init_parser.add_argument("--deploy", default="docker", help="Deployment target (default: docker)")
    init_parser.add_argument("--auth", help="Auth provider (e.g. jwt, oauth)")
    init_parser.add_argument("--db", help="Database provider (e.g. postgres, sqlite)")
    init_parser.add_argument("--payments", help="Payment provider (e.g. stripe)")
    init_parser.add_argument("--ai", help="AI provider (e.g. openai)")
    init_parser.add_argument("--email", help="Email provider (e.g. sendgrid)")
    init_parser.add_argument(
        "--frontend", choices=["react", "next", "vite", "remix", "static"],
        help="Frontend framework to scaffold",
    )
    init_parser.add_argument(
        "--ci", default="github",
        help=(
            "CI platform (default: github). Comma-separated for multiple: "
            "github,gitlab. Options: github, gitlab, azure-devops, bitbucket, "
            "circleci, jenkins, forgejo, gitea, buildkite, drone, woodpecker, "
            "travis, aws-codebuild, cloud-build"
        ),
    )
    reg.register("init", _handle_init)

    # cup ci [--detect] [--regenerate] [--provider P] [--deploy T] [--frontend F]
    ci_parser = sub.add_parser("ci", help="Detect, regenerate, or switch CI platform")
    ci_parser.add_argument("--detect", action="store_true", help="Show detected CI configs in the project")
    ci_parser.add_argument("--regenerate", action="store_true", help="Regenerate the current CI config")
    ci_parser.add_argument("--provider", help="Switch to a different CI provider")
    ci_parser.add_argument("--deploy", default="docker", help="Deploy target for CD steps (default: docker)")
    ci_parser.add_argument("--frontend", help="Frontend framework")
    reg.register("ci", _handle_ci)

    # cup config validate <contract> [--env-file FILE] [--var KEY=VALUE...] [--json]
    config_parser = sub.add_parser(
        "config",
        help="Validate deployment config against a platform contract",
    )
    config_parser.add_argument(
        "contract", nargs="?",
        help="Platform contract ID (e.g. aws-lambda, kubernetes). Omit with --list.",
    )
    config_parser.add_argument(
        "--list", action="store_true", dest="list_contracts",
        help="List all available platform contracts",
    )
    config_parser.add_argument(
        "--env-file", metavar="FILE",
        help="Read env vars from a .env file",
    )
    config_parser.add_argument(
        "--var", action="append", metavar="KEY=VALUE", default=[],
        help="Set an env var (repeatable)",
    )
    config_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )
    reg.register("config", _handle_config)

    # cup obfuscate <src> <out> [--preset LEVEL] [--config-file PATH]
    #   [--html FILE...] [--static NAME...] [--dead-code DENSITY]
    #   [--disable-stage NAME...] [--strict] [--json]
    obf_parser = sub.add_parser(
        "obfuscate",
        help="Build an obfuscated SPA — minify HTML, obfuscate inline JS",
    )
    obf_parser.add_argument(
        "src", help="Source directory containing readable HTML/JS",
    )
    obf_parser.add_argument(
        "out", help="Output directory for built artifacts",
    )
    obf_parser.add_argument(
        "--preset", choices=["light", "medium", "heavy", "paranoid"],
        default=None, help="Protection level preset (default: medium)",
    )
    obf_parser.add_argument(
        "--config-file", dest="config_file", default=None,
        help="Load config from JSON or TOML file",
    )
    obf_parser.add_argument(
        "--html", nargs="*", metavar="FILE", default=None,
        help="Explicit HTML files to process (default: auto-detect *.html)",
    )
    obf_parser.add_argument(
        "--static", nargs="*", metavar="NAME", default=[],
        help="Static files/dirs to copy as-is (e.g. robots.txt, assets/)",
    )
    obf_parser.add_argument(
        "--dead-code", dest="dead_code", default=None,
        choices=["low", "medium", "high"],
        help="Enable dead code injection at specified density",
    )
    obf_parser.add_argument(
        "--disable-stage", dest="disable_stages", nargs="*",
        metavar="STAGE", default=[],
        help="Disable pipeline stages (scan, extract, transform, reassemble, minify, write)",
    )
    obf_parser.add_argument(
        "--strict", action="store_true",
        help="Fail if javascript-obfuscator or html-minifier-terser not installed",
    )
    obf_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Output as JSON",
    )
    reg.register("obfuscate", _handle_obfuscate)


# ── Handlers ────────────────────────────────────────────────────────

def _handle_deploy(args):
    try:
        from codeupipe.deploy.discovery import find_adapters
        from codeupipe.deploy.manifest import load_manifest

        adapters = find_adapters()
        target_name = args.target
        if target_name not in adapters:
            available = ", ".join(adapters.keys())
            print(f"Error: unknown target '{target_name}'. Available: {available}", file=sys.stderr)
            return 1

        adapter = adapters[target_name]
        config_path = args.config
        if config_path.endswith(".toml"):
            pipeline_config = load_manifest(config_path)
        else:
            config_text = Path(config_path).read_text()
            pipeline_config = json.loads(config_text)

        mode = getattr(args, "mode", None)
        port = getattr(args, "port", 8080)
        output_dir = Path(getattr(args, "output_dir", "deploy_output"))

        opts = {}
        if mode:
            opts["mode"] = mode
        opts["port"] = port

        issues = adapter.validate(pipeline_config, **opts)
        if issues:
            print("Validation failed:", file=sys.stderr)
            for issue in issues:
                print(f"  ✗ {issue}", file=sys.stderr)
            return 1

        if getattr(args, "dry_run", False):
            print(f"✓ {target_name}: validation passed (dry run)")
            return 0

        files = adapter.generate(pipeline_config, output_dir, **opts)
        print(f"Generated {target_name} artifacts in {output_dir}/:")
        for f in files:
            print(f"  {f}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_recipe(args):
    try:
        from codeupipe.deploy.recipe import list_recipes as _list_recipes, resolve_recipe

        if getattr(args, "list_recipes", False):
            recipes = _list_recipes()
            if not recipes:
                print("No recipes available.")
                return 0
            print("Available recipes:")
            for r in recipes:
                print(f"  {r['name']:20s} {r['description']}")
            return 0

        if not args.name:
            print("Error: recipe name required (or use --list)", file=sys.stderr)
            return 1

        variables = {}
        for v in getattr(args, "var", []):
            if "=" not in v:
                print(f"Error: --var must be KEY=VALUE, got '{v}'", file=sys.stderr)
                return 1
            key, value = v.split("=", 1)
            variables[key] = value

        resolved, deps = resolve_recipe(args.name, variables)

        if getattr(args, "dry_run", False):
            print(json.dumps(resolved, indent=2))
            if deps:
                print(f"\nDependencies: {', '.join(deps)}")
            return 0

        output_dir = Path(getattr(args, "output_dir", "pipelines"))
        output_dir.mkdir(parents=True, exist_ok=True)
        out_file = output_dir / f"{args.name}.json"
        out_file.write_text(json.dumps(resolved, indent=2) + "\n")
        print(f"Created {out_file}")
        if deps:
            print(f"  Dependencies: {', '.join(deps)}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_init(args):
    try:
        from codeupipe.deploy.init import init_project, list_templates as _list_templates

        if getattr(args, "list_templates", False):
            templates = _list_templates()
            print("Available project templates:")
            for t in templates:
                print(f"  {t['name']:12s} {t['description']}")
            return 0

        if not args.template or not args.name:
            print("Error: template and name required (or use --list)", file=sys.stderr)
            return 1

        options = {}
        for key in ("auth", "db", "payments", "ai", "email"):
            val = getattr(args, key, None)
            if val:
                options[key] = val

        result = init_project(
            args.template, args.name,
            deploy_target=getattr(args, "deploy", "docker"),
            ci_provider=getattr(args, "ci", "github"),
            frontend=getattr(args, "frontend", None),
            options=options,
        )

        print(f"Created project '{args.name}' ({args.template}):")
        for f in result["files"]:
            print(f"  {f}")
        for w in result.get("warnings", []):
            print(f"  Warning: {w}", file=sys.stderr)
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_ci(args):
    try:
        from codeupipe.deploy.init import detect_ci, regenerate_ci

        if getattr(args, "detect", False):
            found = detect_ci(".")
            if not found:
                print("No CI configs detected.")
            else:
                print("Detected CI configs:")
                for entry in found:
                    print(f"  {entry['provider']:20s} {entry['path']}")
            return 0

        provider = getattr(args, "provider", None)
        regenerate = getattr(args, "regenerate", False)

        if regenerate or provider:
            result = regenerate_ci(
                ".", ci_provider=provider,
                deploy_target=getattr(args, "deploy", "docker"),
                frontend=getattr(args, "frontend", None),
            )
            action = "Switched to" if provider else "Regenerated"
            print(f"{action} {result['provider']} CI config: {result['file']}")
            for removed in result.get("removed", []):
                print(f"  Removed old config: {removed}")
            for w in result.get("warnings", []):
                print(f"  Warning: {w}", file=sys.stderr)
            return 0

        found = detect_ci(".")
        if not found:
            print("No CI configs detected. Use --provider to add one.")
        else:
            print("Current CI configs:")
            for entry in found:
                print(f"  {entry['provider']:20s} {entry['path']}")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_config(args):
    try:
        from codeupipe.deploy.contract import (
            list_contracts, load_contract, validate_env, ContractError,
        )

        # --list: show available contracts
        if getattr(args, "list_contracts", False):
            contracts = list_contracts()
            if getattr(args, "json_output", False):
                print(json.dumps(contracts, indent=2))
            else:
                print(f"{'ID':<30s} {'Name':<30s} Category")
                print("-" * 75)
                for c in contracts:
                    print(f"{c['id']:<30s} {c['name']:<30s} {c.get('category', '')}")
            return 0

        contract_id = getattr(args, "contract", None)
        if not contract_id:
            print("Usage: cup config <contract> [--env-file FILE] [--var KEY=VALUE...]")
            print("       cup config --list")
            return 1

        # Build env vars from --env-file and --var
        env = {}
        env_file = getattr(args, "env_file", None)
        if env_file:
            p = Path(env_file)
            if not p.exists():
                print(f"Error: env file not found: {env_file}", file=sys.stderr)
                return 1
            for line in p.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip().strip('"').strip("'")

        for var_str in getattr(args, "var", []):
            if "=" not in var_str:
                print(f"Error: --var must be KEY=VALUE, got: {var_str}", file=sys.stderr)
                return 1
            k, v = var_str.split("=", 1)
            env[k] = v

        result = validate_env(env, contract_id)

        if getattr(args, "json_output", False):
            print(json.dumps({
                "contract": result.contract_id,
                "valid": result.valid,
                "errors": result.errors,
                "warnings": result.warnings,
                "env_count": len(env),
            }, indent=2))
        else:
            contract = load_contract(contract_id)
            print(f"Contract: {contract.get('name', contract_id)} ({contract_id})")
            print(f"Variables: {len(env)}")
            print()
            if result.valid:
                print("✅ Validation passed")
            else:
                print("❌ Validation failed")
                for e in result.errors:
                    print(f"  ERROR: {e}")
            if result.warnings:
                print()
                for w in result.warnings:
                    print(f"  WARN: {w}")

        return 0 if result.valid else 1

    except ContractError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_obfuscate(args):
    """Handler for ``cup obfuscate`` — source protection build pipeline."""
    import asyncio
    from codeupipe import Payload
    from codeupipe.deploy.obfuscate import ObfuscateConfig, build_obfuscate_pipeline

    try:
        # Support loading from config file
        config_file = getattr(args, "config_file", None)
        if config_file:
            config = ObfuscateConfig.from_file(config_file)
            # CLI args override file settings
            config.src_dir = args.src
            config.out_dir = args.out
        else:
            # Build dead code config from CLI flag
            dead_code = None
            dead_code_density = getattr(args, "dead_code", None)
            if dead_code_density:
                dead_code = {"enabled": True, "density": dead_code_density}

            # Build stages dict from disable flags
            stages = None
            disable_stages = getattr(args, "disable_stages", [])
            if disable_stages:
                stages = {s: False for s in disable_stages}

            config = ObfuscateConfig(
                src_dir=args.src,
                out_dir=args.out,
                preset=getattr(args, "preset", None),
                html_files=args.html,
                static_copy=args.static,
                dead_code=dead_code,
                stages=stages,
            )

        pipeline = build_obfuscate_pipeline(config=config, strict=args.strict)
        result = asyncio.run(pipeline.run(Payload({"config": config.to_dict()})))

        build_results = result.get("build_results") or []
        obf_stats = result.get("obfuscate_stats") or {}
        min_stats = result.get("minify_stats") or {}
        static_copied = result.get("static_copied") or []

        if getattr(args, "json_output", False):
            report = {
                "files": build_results,
                "static": static_copied,
                "obfuscation": obf_stats,
                "minification": min_stats,
            }
            print(json.dumps(report, indent=2))
        else:
            print("=" * 50)
            print(" SPA Obfuscation Build")
            print(f" {args.src} -> {args.out}")
            print("=" * 50)

            for f in build_results:
                print(f"\n  done {f['filename']} -> {f['size']} bytes")

            if obf_stats:
                print(f"\n  JS: {obf_stats.get('obfuscated', 0)} obfuscated, "
                      f"{obf_stats.get('skipped', 0)} skipped, "
                      f"{obf_stats.get('errors', 0)} errors")

            if min_stats and min_stats.get("total_original"):
                print(f"  HTML: {min_stats['total_original']} -> "
                      f"{min_stats['total_minified']} bytes "
                      f"({min_stats['ratio']}%)")

            if static_copied:
                print(f"\n  Static: {', '.join(static_copied)}")

            print(f"\nBuild complete")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
