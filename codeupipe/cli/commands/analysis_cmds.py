"""``cup lint``, ``cup coverage``, ``cup report``, ``cup doc-check`` commands.

All four delegate to linter pipelines (dogfooding).
"""

import json
import os
import sys

from codeupipe import Payload

from .._registry import registry


# ── Programmatic API (importable without CLI) ───────────────────────

def lint(directory: str) -> list:
    """Lint a codeupipe component directory for standards violations."""
    import asyncio
    from codeupipe.linter import build_lint_pipeline

    pipeline = build_lint_pipeline()
    payload = Payload({"directory": directory})
    result = asyncio.run(pipeline.run(payload))
    return result.get("issues", [])


def coverage(directory: str, tests_dir: str = "tests") -> dict:
    """Map test coverage for a codeupipe component directory."""
    import asyncio
    from codeupipe.linter.coverage_pipeline import build_coverage_pipeline

    pipeline = build_coverage_pipeline()
    payload = Payload({"directory": directory, "tests_dir": tests_dir})
    result = asyncio.run(pipeline.run(payload))
    return {
        "coverage": result.get("coverage", []),
        "summary": result.get("summary", {}),
        "gaps": result.get("gaps", []),
    }


def report(directory: str, tests_dir: str = "tests") -> dict:
    """Generate a full codebase health report."""
    import asyncio
    from codeupipe.linter.report_pipeline import build_report_pipeline

    pipeline = build_report_pipeline()
    payload = Payload({"directory": directory, "tests_dir": tests_dir})
    result = asyncio.run(pipeline.run(payload))
    return result.get("report", {})


def doc_check(directory: str) -> dict:
    """Check documentation freshness against source code."""
    import asyncio
    from codeupipe.linter.doc_check_pipeline import build_doc_check_pipeline

    pipeline = build_doc_check_pipeline()
    payload = Payload({"directory": directory})
    result = asyncio.run(pipeline.run(payload))
    return result.get("doc_report", {})


def agent_docs(
    directory: str,
    mode: str = "validate",
    site_url: str = "",
    project_name: str = "",
    docs_dir: str = "docs",
    nav_file: str = "mkdocs.yml",
) -> dict:
    """Generate or validate agent-optimized documentation.

    Modes:
        ``init``      — Scaffold agent docs structure from scratch.
        ``update``    — Regenerate docs (preserves hand-maintained files).
        ``validate``  — Check completeness and freshness (default).

    Returns a dict with ``agent_docs_report`` and, for init/update,
    ``skill_index_path`` and ``domain_docs_written``.
    """
    import asyncio
    from codeupipe.linter.agent_docs_pipeline import build_agent_docs_pipeline

    # Try to read config from cup.toml
    config = _load_agent_docs_config(directory)

    pipeline = build_agent_docs_pipeline()
    payload = Payload({
        "directory": directory,
        "agent_docs_mode": mode,
        "site_url": site_url or config.get("site_url", ""),
        "project_name": project_name or config.get("project_name", ""),
        "docs_dir": docs_dir,
        "nav_file": nav_file,
        "agent_docs_config": config,
    })
    result = asyncio.run(pipeline.run(payload))
    return {
        "report": result.get("agent_docs_report", {}),
        "skill_index_path": result.get("skill_index_path", ""),
        "domain_docs_written": result.get("domain_docs_written", []),
        "skill_domains": result.get("skill_domains", []),
    }


def _load_agent_docs_config(directory: str) -> dict:
    """Try to load [agent-docs] from cup.toml."""
    from pathlib import Path
    cup_toml = Path(directory) / "cup.toml"
    if not cup_toml.exists():
        return {}
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            # Fall back to basic parsing
            return {}
    try:
        data = tomllib.loads(cup_toml.read_text(encoding="utf-8"))
        return data.get("agent-docs", {})
    except Exception:
        return {}


# ── Parser Setup ────────────────────────────────────────────────────

def setup(sub, reg):
    # cup lint <path>
    lint_parser = sub.add_parser(
        "lint", help="Check a component directory for codeupipe standards violations",
    )
    lint_parser.add_argument("path", help="Directory to lint")
    reg.register("lint", _handle_lint)

    # cup coverage <path> [--tests-dir]
    cov_parser = sub.add_parser("coverage", help="Map test coverage for a component directory")
    cov_parser.add_argument("path", help="Directory to analyze")
    cov_parser.add_argument("--tests-dir", default="tests", help="Path to tests directory (default: tests)")
    reg.register("coverage", _handle_coverage)

    # cup report <path> [--tests-dir] [--json] [--detail] [--verbose]
    report_parser = sub.add_parser("report", help="Generate a full codebase health report")
    report_parser.add_argument("path", help="Directory to analyze")
    report_parser.add_argument("--tests-dir", default="tests", help="Path to tests directory (default: tests)")
    report_parser.add_argument("--json", action="store_true", dest="json_output", help="Output raw JSON for piping to web/CI")
    report_parser.add_argument("--detail", action="store_true", help="Show per-component detail table")
    report_parser.add_argument("--verbose", action="store_true", help="Show full detail with source info")
    reg.register("report", _handle_report)

    # cup doc-check [path] [--json] [--fix] [--all] [--auto-fix]
    doc_parser = sub.add_parser("doc-check", help="Check documentation freshness against source code")
    doc_parser.add_argument("path", nargs="?", default=".", help="Directory to scan (default: current dir)")
    doc_parser.add_argument("--json", action="store_true", dest="json_output", help="Output raw JSON for piping to CI")
    doc_parser.add_argument("--fix", action="store_true", help="Interactively approve and update drifted hashes")
    doc_parser.add_argument("--all", action="store_true", dest="fix_all", help="With --fix, auto-approve all drifted hashes without prompting")
    doc_parser.add_argument("--auto-fix", action="store_true", dest="auto_fix", help="Non-interactive: auto-approve and fix all drifted hashes (shorthand for --fix --all)")
    reg.register("doc-check", _handle_doc_check)

    # cup agent-docs [init|update|validate] [path] [--site-url] [--project-name] [--json]
    ad_parser = sub.add_parser(
        "agent-docs",
        help="Generate or validate agent-optimized documentation",
    )
    ad_parser.add_argument(
        "mode", nargs="?", default="validate",
        choices=["init", "update", "validate"],
        help="init: scaffold from scratch, update: regenerate, validate: check (default)",
    )
    ad_parser.add_argument(
        "path", nargs="?", default=".",
        help="Project directory (default: current dir)",
    )
    ad_parser.add_argument(
        "--site-url", default="", dest="site_url",
        help="Site URL for curl endpoints (e.g. https://example.github.io/project)",
    )
    ad_parser.add_argument(
        "--project-name", default="", dest="project_name",
        help="Project name for doc titles",
    )
    ad_parser.add_argument(
        "--docs-dir", default="docs", dest="docs_dir",
        help="Docs directory (default: docs)",
    )
    ad_parser.add_argument(
        "--nav-file", default="mkdocs.yml", dest="nav_file",
        help="Nav config file (default: mkdocs.yml)",
    )
    ad_parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Machine-readable JSON output",
    )
    reg.register("agent-docs", _handle_agent_docs)


# ── Handlers ────────────────────────────────────────────────────────

def _handle_lint(args):
    try:
        issues = lint(args.path)
        if not issues:
            print(f"✓ {args.path}: all checks passed")
            return 0

        errors = [i for i in issues if i[1] == "error"]
        warnings = [i for i in issues if i[1] == "warning"]

        for rule_id, severity, filepath, message in issues:
            marker = "✗" if severity == "error" else "!"
            print(f"  {marker} {rule_id} [{severity}] {filepath}: {message}")

        print()
        summary_parts = []
        if errors:
            summary_parts.append(f"{len(errors)} error(s)")
        if warnings:
            summary_parts.append(f"{len(warnings)} warning(s)")
        print(f"  {', '.join(summary_parts)}")
        return 1 if errors else 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_coverage(args):
    try:
        tests_dir = getattr(args, "tests_dir", "tests")
        result = coverage(args.path, tests_dir=tests_dir)
        summary = result["summary"]
        cov_list = result["coverage"]

        if not cov_list:
            print(f"✓ {args.path}: no components found")
            return 0

        for entry in cov_list:
            pct = entry["coverage_pct"]
            icon = "✓" if pct == 100.0 else ("!" if pct > 0 else "✗")
            test_tag = f"{entry['test_count']} tests" if entry["has_test_file"] else "no tests"
            print(f"  {icon} {entry['name']} ({entry['kind']}) — {pct}% [{test_tag}]")
            if entry["untested_methods"]:
                for m in entry["untested_methods"]:
                    print(f"      missing: {m}()")

        print()
        print(
            f"  {summary['overall_pct']}% method coverage "
            f"({summary['tested_methods']}/{summary['total_methods']} methods, "
            f"{summary['tested_components']}/{summary['total_components']} components tested)"
        )
        gaps = result["gaps"]
        if gaps:
            print(f"  {len(gaps)} component(s) with gaps")
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_report(args):
    try:
        tests_dir = getattr(args, "tests_dir", "tests")
        rpt = report(args.path, tests_dir=tests_dir)

        if getattr(args, "json_output", False):
            print(json.dumps(rpt, indent=2))
            return 0

        summary = rpt.get("summary", {})
        components = rpt.get("components", [])
        orphaned_comps = rpt.get("orphaned_components", [])
        orphaned_tests = rpt.get("orphaned_tests", [])
        stale_files = rpt.get("stale_files", [])
        show_detail = getattr(args, "detail", False) or getattr(args, "verbose", False)
        show_verbose = getattr(args, "verbose", False)

        score = summary.get("health_score", "?")
        score_icon = {"A": "✓", "B": "✓", "C": "!", "D": "✗", "F": "✗"}.get(score, "?")
        print(f"\n  {score_icon} Health Score: {score}")
        print(f"    generated: {rpt.get('generated_at', 'unknown')}")
        print(f"    directory: {rpt.get('directory', '')}")
        print()

        cov_pct = summary.get("overall_pct", 0)
        total = summary.get("total_components", 0)
        tested = summary.get("tested_components", 0)
        print(f"  Coverage:  {cov_pct}% ({tested}/{total} components)")
        print(f"  Orphans:   {len(orphaned_comps)} component(s), {len(orphaned_tests)} test(s)")
        print(f"  Stale:     {len(stale_files)} file(s) (>90d)")

        if show_detail:
            print()
            print("  Components:")
            for comp in components:
                pct = comp["coverage_pct"]
                icon = "✓" if pct == 100.0 else ("!" if pct > 0 else "✗")
                orphan_tag = " [ORPHAN]" if comp.get("orphaned") else ""
                git = comp.get("git", {})
                age = git.get("days_since_change")
                age_tag = f" ({age}d ago)" if age is not None else ""
                author = git.get("last_author", "")
                author_tag = f" by {author}" if author else ""
                print(f"    {icon} {comp['name']} ({comp['kind']}) — {pct}%{orphan_tag}{age_tag}{author_tag}")
                if show_verbose and comp.get("untested_methods"):
                    for m in comp["untested_methods"]:
                        print(f"        missing: {m}()")
                if show_verbose and comp.get("imported_by"):
                    print(f"        imported by: {', '.join(comp['imported_by'])}")

        if orphaned_comps:
            print()
            print("  Orphaned Components:")
            for o in orphaned_comps:
                print(f"    ✗ {o['name']} ({o['kind']}) — {o['file']}")
        if orphaned_tests:
            print()
            print("  Orphaned Tests:")
            for o in orphaned_tests:
                print(f"    ✗ {o['file']}")
        if stale_files:
            print()
            print("  Stale Files:")
            for s in stale_files:
                print(f"    ! {s['file']} — {s['days_since_change']}d since change")
        print()
        return 0
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _handle_doc_check(args):
    try:
        rpt = doc_check(args.path)

        if getattr(args, "json_output", False):
            print(json.dumps(rpt, indent=2))
            return 0 if rpt.get("status") == "ok" else 1

        total = rpt.get("total_refs", 0)
        status = rpt.get("status", "ok")
        details = rpt.get("details", [])

        if status == "ok":
            print(f"✓ docs: {total} ref(s) checked, all current")
            return 0

        drifted = rpt.get("drifted", 0)
        missing_sym = rpt.get("missing_symbols", 0)
        missing_files = rpt.get("missing_files", 0)

        print(f"✗ docs: {total} ref(s) checked, issues found")
        print()
        if drifted:
            print(f"  Drifted: {drifted} ref(s)")
        if missing_sym:
            print(f"  Missing symbols: {missing_sym}")
        if missing_files:
            print(f"  Missing files: {missing_files}")

        want_fix = getattr(args, "fix", False) or getattr(args, "auto_fix", False)
        fix_all = getattr(args, "fix_all", False) or getattr(args, "auto_fix", False)

        if details:
            print()
            for d in details:
                kind = d.get("type", "unknown")
                icon = "!" if kind == "drift" else "✗"
                doc = d.get("doc_file", d.get("doc_path", "?"))
                src = d.get("source_file", d.get("file", "?"))
                msg = d.get("message", d.get("symbol", ""))
                print(f"  {icon} {doc} → {src}: {msg}")

                # Show the content inside the ref so the user can review it
                ref_content = d.get("content", "")
                if ref_content:
                    preview_lines = ref_content.splitlines()
                    max_lines = 6
                    for cline in preview_lines[:max_lines]:
                        print(f"    │ {cline}")
                    if len(preview_lines) > max_lines:
                        print(f"    │ ... ({len(preview_lines) - max_lines} more lines)")
                    print()

                # Interactive fix for drift issues
                if want_fix and kind == "drift":
                    _apply_hash_fix(d, fix_all)

        print()
        return 1
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


def _apply_hash_fix(detail, auto_approve):
    """Prompt the user (or auto-approve) and rewrite the hash in the markdown file."""
    import re

    doc_path = detail.get("doc_path", detail.get("doc_file"))
    line_num = detail.get("line")
    stored = detail.get("stored_hash")
    current = detail.get("current_hash")
    src_file = detail.get("file", "?")

    if not (doc_path and line_num and stored and current):
        return

    # Extract hashes from the message if not top-level keys
    if not stored or not current:
        m = re.search(r"stored=(\w+), current=(\w+)", detail.get("message", ""))
        if m:
            stored, current = m.group(1), m.group(2)
        else:
            return

    if auto_approve:
        approved = True
    else:
        try:
            answer = input(
                f"    ▸ Update hash in {doc_path} line {line_num}? "
                f"({stored} → {current}) [y/n/q] "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n    ▸ Aborted.")
            return
        if answer == "q":
            print("    ▸ Quitting fix mode.")
            raise SystemExit(1)
        approved = answer in ("y", "yes")

    if not approved:
        print(f"    ▸ Skipped {src_file}")
        return

    try:
        from pathlib import Path
        path = Path(doc_path)
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        idx = line_num - 1  # 0-based
        if 0 <= idx < len(lines):
            old_line = lines[idx]
            new_line = old_line.replace(f"hash={stored}", f"hash={current}", 1)
            if new_line != old_line:
                lines[idx] = new_line
                path.write_text("".join(lines), encoding="utf-8")
                print(f"    ✓ Fixed {doc_path}:{line_num} ({stored} → {current})")
            else:
                print(f"    ! Could not locate hash={stored} on line {line_num} of {doc_path}")
        else:
            print(f"    ! Line {line_num} out of range in {doc_path}")
    except Exception as e:
        print(f"    ✗ Failed to fix {doc_path}: {e}", file=sys.stderr)


def _handle_agent_docs(args):
    """Handler for ``cup agent-docs [init|update|validate] [path]``."""
    import json as _json

    mode = getattr(args, "mode", "validate")
    directory = os.path.abspath(getattr(args, "path", "."))
    json_out = getattr(args, "json_output", False)
    site_url = getattr(args, "site_url", "")
    project_name = getattr(args, "project_name", "")
    docs_dir = getattr(args, "docs_dir", "docs")
    nav_file = getattr(args, "nav_file", "mkdocs.yml")

    result = agent_docs(
        directory=directory,
        mode=mode,
        site_url=site_url or None,
        project_name=project_name or None,
        docs_dir=docs_dir,
        nav_file=nav_file,
    )

    report = result.get("report", {})
    status = report.get("status", "unknown")
    issues = report.get("issues", [])

    if json_out:
        print(_json.dumps(result, indent=2))
        raise SystemExit(0 if status == "ok" else 1)

    # Human-readable output
    domains = result.get("skill_domains", [])
    written = result.get("domain_docs_written", [])

    if mode == "init":
        print(f"  Agent docs initialised — {len(domains)} domains discovered")
        if written:
            for p in written:
                print(f"    + {p}")
        print(f"  Index → {result.get('skill_index_path', 'docs/agents.md')}")

    elif mode == "update":
        print(f"  Agent docs updated — {len(domains)} domains")
        for p in written:
            print(f"    ↻ {p}")
        if not written:
            print("    (no generated files to update)")

    else:  # validate
        total = report.get("total_domains", 0)
        documented = report.get("documented", 0)
        missing = report.get("missing", [])
        orphaned = report.get("orphaned", [])

        icon = "✓" if status == "ok" else "✗"
        print(f"  {icon} Agent docs: {documented}/{total} domains documented")

        if missing:
            print(f"  Missing docs:")
            for m in missing:
                print(f"    - {m}")
        if orphaned:
            print(f"  Orphaned docs:")
            for o in orphaned:
                print(f"    - {o}")
        if issues:
            print(f"  Issues:")
            for issue in issues:
                print(f"    ! {issue}")

    if issues and mode != "validate":
        print(f"\n  ⚠ {len(issues)} issue(s):")
        for issue in issues:
            print(f"    ! {issue}")

    raise SystemExit(0 if status == "ok" or mode in ("init", "update") else 1)