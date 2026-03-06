---
applyTo: 'codeupipe/cli.py'
description: 'Pattern for adding new cup CLI subcommands — wrapper function, argparse setup, handler block'
---

# Adding a `cup` Subcommand

## Three-Step Pattern

Every `cup` subcommand follows the same structure in `codeupipe/cli.py`:

### 1. Wrapper Function (above `main()`)

Thin function that builds a pipeline, runs it, and returns the result dict. This is the programmatic API — usable without the CLI.

```python
def my_command(directory: str) -> dict:
    """One-sentence description.

    Internally delegates to the CUP pipeline (dogfooding).
    """
    import asyncio
    from .linter.my_pipeline import build_my_pipeline

    pipeline = build_my_pipeline()
    payload = Payload({"directory": directory})
    result = asyncio.run(pipeline.run(payload))
    return result.get("my_report", {})
```

### 2. Argparse Setup (inside `main()`, after other subparsers)

```python
# cup my-command <path> [--json]
my_parser = sub.add_parser(
    "my-command",
    help="Short description for --help",
)
my_parser.add_argument("path", help="Directory to analyze")
my_parser.add_argument("--json", action="store_true", dest="json_output")
```

### 3. Handler Block (inside `main()`, before `parser.print_help()`)

```python
if args.command == "my-command":
    try:
        rpt = my_command(args.path)
        # Format and print output
        # return 0 for success, 1 for issues found
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
```

## Conventions

- **CLI name**: kebab-case (`doc-check`, not `doc_check`)
- **Wrapper function**: snake_case (`doc_check`)
- **Exit codes**: 0 = clean/success, 1 = issues found or error
- **JSON flag**: `--json` with `dest="json_output"` for CI piping
- **Update docstring**: Add the new command to the Usage block at the top of `cli.py`

## Existing Commands

| Command | Wrapper | Pipeline |
|---------|---------|----------|
| `cup lint <path>` | `lint()` | `build_lint_pipeline()` |
| `cup coverage <path>` | `coverage()` | `build_coverage_pipeline()` |
| `cup report <path>` | `report()` | `build_report_pipeline()` |
| `cup doc-check [path]` | `doc_check()` | `build_doc_check_pipeline()` |
