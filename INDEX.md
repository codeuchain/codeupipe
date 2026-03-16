# codeupipe — Index

Quick-reference map of the project. Every path listed here is verified by `cup doc-check`.

---

## Docs

| Document | Purpose |
|----------|---------|
| [README.md](README.md) | Quick-start, install, examples |
| [CONCEPTS.md](CONCEPTS.md) | Full API reference with runnable examples |
| [BEST_PRACTICES.md](BEST_PRACTICES.md) | Project structure, naming, testing strategy |
| [SKILL.md](SKILL.md) | Agent skill reference (types, patterns, conversion) |
| [INDEX.md](INDEX.md) | This file — project map |
| [ring10-secure-config-blueprint.md](docs/ring10-secure-config-blueprint.md) | Ring 10 — Secure Config design blueprint |
| [docs/archive/](docs/archive/) | Archived blueprints (rings 7-9, shipping exploration) |

---

## Package Structure

<!-- cup:ref file=codeupipe/__init__.py hash=2dc77bf -->
```
codeupipe/
├── __init__.py              # Public API re-exports
├── py.typed                 # PEP 561 typed marker
│
├── core/                    # Primitives
│   ├── payload.py           # Payload, MutablePayload
│   ├── filter.py            # Filter Protocol
│   ├── stream_filter.py     # StreamFilter Protocol
│   ├── pipeline.py          # Pipeline orchestrator + from_config()
│   ├── valve.py             # Valve — conditional gate
│   ├── tap.py               # Tap Protocol — observation
│   ├── state.py             # State — execution metadata
│   ├── hook.py              # Hook ABC — lifecycle
│   ├── event.py             # PipelineEvent, EventEmitter
│   ├── govern.py            # Schemas, contracts, audit, dead-letter
│   ├── secure.py            # Sign, verify, encrypt, decrypt — functional helpers
│   ├── sign_filter.py       # SignFilter — HMAC-SHA256 signing
│   ├── verify_filter.py     # VerifyFilter — signature verification
│   ├── encrypt_filter.py    # EncryptFilter — symmetric encryption
│   └── decrypt_filter.py    # DecryptFilter — symmetric decryption
│
├── connect/                 # Service connectors (Ring 8)
│   ├── config.py            # ConnectorConfig, load_connector_configs
│   ├── discovery.py         # discover_connectors, check_health
│   └── http.py              # HttpConnector — built-in REST connector
│
├── deploy/                  # Deployment adapters (Ring 7)
│   ├── adapter.py           # DeployTarget, DeployAdapter ABC
│   ├── contract.py          # Platform contracts — load, list, validate
│   ├── contracts/           # 25 platform constraint JSON schemas
│   ├── discovery.py         # find_adapters
│   ├── docker.py            # DockerAdapter
│   ├── handlers.py          # Serverless handler renderers
│   ├── init.py              # cup init scaffolding
│   ├── manifest.py          # cup.toml manifest — load & validate
│   ├── netlify.py           # NetlifyAdapter
│   ├── obfuscate/           # SPA obfuscation build pipeline
│   │   ├── obfuscate_config.py     # ObfuscateConfig — tool options
│   │   ├── scan_html_files.py      # ScanHtmlFiles filter
│   │   ├── extract_inline_scripts.py # ExtractInlineScripts filter
│   │   ├── obfuscate_scripts.py    # ObfuscateScripts — JS obfuscation
│   │   ├── reassemble_html.py      # ReassembleHtml — re-inject scripts
│   │   ├── minify_html.py          # MinifyHtml — HTML+CSS minification
│   │   ├── write_output.py         # WriteOutput — write files + copy static
│   │   └── obfuscate_pipeline.py   # build_obfuscate_pipeline() builder
│   ├── recipe.py            # Recipes — list, resolve, dependencies
│   └── vercel.py            # VercelAdapter
│
├── distribute/              # Distributed execution (Ring 7a)
│   ├── checkpoint.py        # Checkpoint, CheckpointHook
│   ├── remote.py            # RemoteFilter
│   ├── source.py            # IterableSource, FileSource
│   └── worker.py            # WorkerPool
│
├── runtime.py               # TapSwitch, HotSwap — zero-downtime production control
│
├── auth/                    # OAuth2 integration (browser-based login, credential persistence)
│   ├── credential.py        # Credential, CredentialStore
│   ├── provider.py          # AuthProvider, GoogleOAuth, GitHubOAuth
│   ├── hook.py              # AuthHook
│   └── _server.py           # Local OAuth callback server
│
├── registry.py              # Registry, cup_component, default_registry
│
├── utils/
│   └── error_handling.py    # ErrorHandlingMixin, RetryFilter
│
├── converter/               # CodeUChain ↔ codeupipe migration
│   ├── config.py            # Pattern config (mvc/clean/hexagonal/flat)
│   ├── filters/             # 7 conversion filters
│   ├── taps/                # ConversionLogTap
│   └── pipelines/           # build_export_pipeline, build_import_pipeline
│
├── linter/                  # Analysis pipelines (dogfooded as CUP)
│   ├── lint_pipeline.py     # build_lint_pipeline()
│   ├── coverage_pipeline.py # build_coverage_pipeline()
│   ├── report_pipeline.py   # build_report_pipeline()
│   ├── doc_check_pipeline.py# build_doc_check_pipeline()
│   └── (18 filter files)    # ScanDirectory, CheckNaming, etc.
│
├── testing.py               # Test helpers — run_filter, assert_payload, etc.
└── cli/                     # CLI package — registry-routed command dispatch
    ├── __init__.py          # Thin main() + backward-compat re-exports
    ├── __main__.py          # python -m codeupipe.cli entry
    ├── _registry.py         # CommandRegistry — routes command name → handler
    ├── _templates.py        # 9 component template strings
    ├── _scaffold.py         # scaffold engine, name utils, composed builder
    ├── _bundle.py           # bundle engine
    └── commands/            # One module per command group
        ├── scaffold_cmds.py # new, list
        ├── analysis_cmds.py # lint, coverage, report, doc-check
        ├── run_cmds.py      # run, describe, graph, runs
        ├── deploy_cmds.py   # deploy, recipe, init, ci, config, obfuscate
        ├── connect_cmds.py  # connect, marketplace
        ├── project_cmds.py  # test, doctor, upgrade, publish, version, bundle
        ├── distribute_cmds.py # distribute checkpoint/remote/worker
        └── auth_cmds.py     # auth login/status/revoke/list
```
<!-- /cup:ref -->

---

## Core Types

<!-- cup:ref file=codeupipe/core/__init__.py hash=af8905e -->
| Type | Source | Role |
|------|--------|------|
| `Payload` | core/payload.py | Immutable data container |
| `MutablePayload` | core/payload.py | Mutable sibling for bulk edits |
| `Filter` | core/filter.py | Processing unit — `.call(payload) → Payload` |
| `StreamFilter` | core/stream_filter.py | Streaming — `.stream(chunk)` yields 0..N |
| `Pipeline` | core/pipeline.py | Orchestrator — `.run()` / `.stream()` |
| `Valve` | core/valve.py | Conditional gate — filter + predicate |
| `Tap` | core/tap.py | Read-only observer — `.observe(payload)` |
| `State` | core/state.py | Execution metadata |
| `Hook` | core/hook.py | Lifecycle — before / after / on_error |
<!-- /cup:ref -->

---

## Govern (Ring 6)

<!-- cup:ref file=codeupipe/core/event.py symbols=PipelineEvent,EventEmitter hash=d106174 -->
<!-- cup:ref file=codeupipe/core/govern.py symbols=SchemaViolation,ContractViolation,PipelineTimeoutError,PayloadSchema,AuditEntry,AuditTrail,AuditHook,DeadLetterHandler,LogDeadLetterHandler hash=f98fbce -->
| Type | Source | Role |
|------|--------|------|
| `PipelineEvent` | core/event.py | Typed event emitted by pipelines |
| `EventEmitter` | core/event.py | Pub/sub event bus |
| `PayloadSchema` | core/govern.py | Declarative payload validation |
| `SchemaViolation` | core/govern.py | Schema check failure |
| `ContractViolation` | core/govern.py | Pre/post-condition failure |
| `PipelineTimeoutError` | core/govern.py | Timeout exceeded |
| `AuditEntry` / `AuditTrail` | core/govern.py | Immutable audit log |
| `AuditHook` | core/govern.py | Hook that records audit entries |
| `DeadLetterHandler` | core/govern.py | Failed-payload routing ABC |
| `LogDeadLetterHandler` | core/govern.py | Dead-letter → logger |
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Deploy (Ring 7)

<!-- cup:ref file=codeupipe/deploy/__init__.py hash=5cd158c -->
<!-- cup:ref file=codeupipe/deploy/adapter.py symbols=DeployTarget,DeployAdapter hash=fb707c9 -->
<!-- cup:ref file=codeupipe/deploy/discovery.py symbols=find_adapters hash=2057718 -->
<!-- cup:ref file=codeupipe/deploy/docker.py symbols=DockerAdapter hash=bb3410f -->
<!-- cup:ref file=codeupipe/deploy/handlers.py symbols=render_vercel_handler,render_netlify_handler,render_lambda_handler hash=33fb03d -->
<!-- cup:ref file=codeupipe/deploy/init.py symbols=init_project,list_templates hash=381c944 -->
<!-- cup:ref file=codeupipe/deploy/manifest.py symbols=ManifestError,load_manifest hash=717235e -->
<!-- cup:ref file=codeupipe/deploy/netlify.py symbols=NetlifyAdapter hash=5659642 -->
<!-- cup:ref file=codeupipe/deploy/render.py symbols=RenderAdapter hash=c94da8d -->
<!-- cup:ref file=codeupipe/deploy/recipe.py symbols=RecipeError,list_recipes,resolve_recipe hash=6e84b7a -->
<!-- cup:ref file=codeupipe/deploy/vercel.py symbols=VercelAdapter hash=33ddeb5 -->
<!-- cup:ref file=codeupipe/deploy/fly.py symbols=FlyAdapter -->
<!-- cup:ref file=codeupipe/deploy/railway.py symbols=RailwayAdapter -->
<!-- cup:ref file=codeupipe/deploy/cloudrun.py symbols=CloudRunAdapter -->
<!-- cup:ref file=codeupipe/deploy/koyeb.py symbols=KoyebAdapter -->
<!-- cup:ref file=codeupipe/deploy/apprunner.py symbols=AppRunnerAdapter -->
<!-- cup:ref file=codeupipe/deploy/oracle.py symbols=OracleAdapter -->
<!-- cup:ref file=codeupipe/deploy/azure_container_apps.py symbols=AzureContainerAppsAdapter -->
<!-- cup:ref file=codeupipe/deploy/huggingface.py symbols=HuggingFaceAdapter -->
| Type | Source | Role |
|------|--------|------|
| `DeployTarget` | deploy/adapter.py | Enum — docker, vercel, netlify, lambda |
| `DeployAdapter` | deploy/adapter.py | ABC — `prepare()`, `deploy()` |
| `find_adapters` | deploy/discovery.py | Auto-discover platform adapters |
| `DockerAdapter` | deploy/docker.py | Docker build + push |
| `VercelAdapter` | deploy/vercel.py | Vercel deployment |
| `NetlifyAdapter` | deploy/netlify.py | Netlify deployment |
| `RenderAdapter` | deploy/render.py | Render free-tier deployment |
| `FlyAdapter` | deploy/fly.py | Fly.io edge deployment |
| `RailwayAdapter` | deploy/railway.py | Railway deployment |
| `CloudRunAdapter` | deploy/cloudrun.py | Google Cloud Run |
| `KoyebAdapter` | deploy/koyeb.py | Koyeb free-tier deployment |
| `AppRunnerAdapter` | deploy/apprunner.py | AWS App Runner |
| `OracleAdapter` | deploy/oracle.py | Oracle Cloud Always Free VM |
| `AzureContainerAppsAdapter` | deploy/azure_container_apps.py | Azure Container Apps |
| `HuggingFaceAdapter` | deploy/huggingface.py | Hugging Face Spaces |
| `render_*_handler` | deploy/handlers.py | Serverless entry-point renderers |
| `init_project` | deploy/init.py | `cup init` scaffolding |
| `load_manifest` | deploy/manifest.py | Parse & validate cup.toml |
| `list_recipes` / `resolve_recipe` | deploy/recipe.py | Recipe system |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Distribute (Ring 7a)

<!-- cup:ref file=codeupipe/distribute/__init__.py hash=59ccacc -->
<!-- cup:ref file=codeupipe/distribute/checkpoint.py symbols=Checkpoint,CheckpointHook hash=c982735 -->
<!-- cup:ref file=codeupipe/distribute/remote.py symbols=RemoteFilter hash=b17b607 -->
<!-- cup:ref file=codeupipe/distribute/source.py symbols=IterableSource,FileSource hash=192a21a -->
<!-- cup:ref file=codeupipe/distribute/worker.py symbols=WorkerPool hash=362b51b -->
| Type | Source | Role |
|------|--------|------|
| `Checkpoint` / `CheckpointHook` | distribute/checkpoint.py | Save/resume pipeline progress |
| `RemoteFilter` | distribute/remote.py | Execute a filter on a remote worker |
| `IterableSource` / `FileSource` | distribute/source.py | Stream data into pipelines |
| `WorkerPool` | distribute/worker.py | Multi-process execution pool |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Connect (Ring 8)

<!-- cup:ref file=codeupipe/connect/__init__.py hash=5c80122 -->
<!-- cup:ref file=codeupipe/connect/config.py symbols=ConfigError,ConnectorConfig,load_connector_configs hash=693d3be -->
<!-- cup:ref file=codeupipe/connect/discovery.py symbols=discover_connectors,check_health hash=e9fe17c -->
<!-- cup:ref file=codeupipe/connect/http.py symbols=HttpConnector hash=2bf804b -->
| Type | Source | Role |
|------|--------|------|
| `ConnectorConfig` | connect/config.py | Parse `[connectors.*]` from cup.toml |
| `load_connector_configs` | connect/config.py | Load all connector configs |
| `discover_connectors` | connect/discovery.py | Entry-point discovery + registration |
| `check_health` | connect/discovery.py | Pre-flight health checks |
| `HttpConnector` | connect/http.py | Built-in REST connector (urllib, zero deps) |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Marketplace (Ring 9)

The marketplace index is community-managed in a standalone repo:
**[codeuchain/codeupipe-marketplace](https://github.com/codeuchain/codeupipe-marketplace)**

Contributors fork that repo, add a `manifest.json` for their component, and open a PR.
CI validates the manifest; on merge the index is rebuilt automatically.

The CLI client code below fetches the index and provides search/info/install commands:

<!-- cup:ref file=codeupipe/marketplace/__init__.py hash=4dc7675 -->
<!-- cup:ref file=codeupipe/marketplace/index.py symbols=fetch_index,search,info,MarketplaceError hash=c05c5ff -->
| Type | Source | Role |
|------|--------|------|
| `fetch_index` | marketplace/index.py | Fetch & cache marketplace JSON index |
| `search` | marketplace/index.py | Keyword + category/provider search |
| `info` | marketplace/index.py | Package detail lookup by name or provider |
| `MarketplaceError` | marketplace/index.py | Marketplace-specific error |

### CLI Commands

```bash
cup marketplace search "payments"          # Search by keyword
cup marketplace info codeupipe-stripe      # Detailed package info
cup marketplace install codeupipe-stripe   # Install from PyPI
```

### Trust Tiers

| Tier | Badge | Meaning |
|------|-------|---------|
| **verified** | ✅ | Published by codeuchain org |
| **community** | 🔷 | Community-submitted, CI-validated |
| **unindexed** | — | Works via entry points, not in index |

All tiers work with `cup connect --list`. The marketplace only affects discoverability.
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Secure Config (Ring 10)

<!-- cup:ref file=codeupipe/core/secure.py symbols=seal_payload,verify_payload,encrypt_data,decrypt_data,SecurePayloadError -->
<!-- cup:ref file=codeupipe/core/sign_filter.py symbols=SignFilter -->
<!-- cup:ref file=codeupipe/core/verify_filter.py symbols=VerifyFilter -->
<!-- cup:ref file=codeupipe/core/encrypt_filter.py symbols=EncryptFilter -->
<!-- cup:ref file=codeupipe/core/decrypt_filter.py symbols=DecryptFilter -->
<!-- cup:ref file=codeupipe/deploy/contract.py symbols=load_contract,list_contracts,validate_env,ContractError,ValidationResult -->
| Type | Source | Role |
|------|--------|------|
| `SignFilter` | core/sign_filter.py | HMAC-SHA256 sign payloads at pipeline boundary |
| `VerifyFilter` | core/verify_filter.py | Verify signature + optional expiry check |
| `EncryptFilter` | core/encrypt_filter.py | Encrypt payload data (PBKDF2 + authenticated) |
| `DecryptFilter` | core/decrypt_filter.py | Decrypt payload data |
| `seal_payload` / `verify_payload` | core/secure.py | Functional sign/verify helpers |
| `encrypt_data` / `decrypt_data` | core/secure.py | Functional encrypt/decrypt helpers |
| `SecurePayloadError` | core/secure.py | Tamper, wrong key, or expiry error |
| `load_contract` | deploy/contract.py | Load a platform contract JSON by ID |
| `list_contracts` | deploy/contract.py | List all available platform contracts |
| `validate_env` | deploy/contract.py | Validate env vars against a contract |
| `ContractError` | deploy/contract.py | Contract not found / malformed |
| `ValidationResult` | deploy/contract.py | Validation result with `.valid`, `.errors`, `.warnings` |

### Platform Contracts (25 JSON schemas)

Located in `codeupipe/deploy/contracts/`. Each JSON defines:
- Required / optional env vars
- Naming rules (regex pattern, forbidden prefixes)
- Size limits (key, value, total, max vars)
- Secret backends and export formats

```bash
cup config --list                        # Show all 23 platforms
cup config aws-lambda --var MY_KEY=val   # Validate against AWS Lambda contract
cup config kubernetes --env-file .env    # Validate .env against Kubernetes
```

### Source Protection Pipeline

<!-- cup:ref file=codeupipe/deploy/obfuscate/__init__.py -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/obfuscate_config.py symbols=ObfuscateConfig -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/obfuscate_pipeline.py symbols=build_obfuscate_pipeline -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/scan_source_files.py symbols=ScanSourceFiles -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/extract_embedded_code.py symbols=ExtractEmbeddedCode -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/inject_dead_code.py symbols=InjectDeadCode -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/transform_code.py symbols=TransformCode -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/reassemble_content.py symbols=ReassembleContent -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/minify_content.py symbols=MinifyContent -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/write_output.py symbols=WriteOutput -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/scan_html_files.py symbols=ScanHtmlFiles -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/extract_inline_scripts.py symbols=ExtractInlineScripts -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/obfuscate_scripts.py symbols=ObfuscateScripts -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/reassemble_html.py symbols=ReassembleHtml -->
<!-- cup:ref file=codeupipe/deploy/obfuscate/minify_html.py symbols=MinifyHtml -->

Configurable source protection pipeline with preset profiles, per-stage toggling,
dead code injection, and file type extensibility. A dynamic CUP pipeline:

| Stage | Filter (New) | Alias (Old) | Purpose |
|-------|-------------|-------------|---------|
| 1 | `ScanSourceFiles` | `ScanHtmlFiles` | Discover files by configured extensions |
| 2 | `ExtractEmbeddedCode` | `ExtractInlineScripts` | Regex-extract inline code, replace with placeholders |
| 2½ | `InjectDeadCode` | — | Insert non-functional code (optional, density-controlled) |
| 3 | `TransformCode` | `ObfuscateScripts` | Shell out to tool (graceful fallback) |
| 4 | `ReassembleContent` | `ReassembleHtml` | Inject processed code back into templates |
| 5 | `MinifyContent` | `MinifyHtml` | Shell out to minifier (graceful fallback) |
| 6 | `WriteOutput` | `WriteOutput` | Write files + copy static assets to output directory |

Presets: `light`, `medium` (default), `heavy`, `paranoid`.

```bash
cup obfuscate src/ dist/                                    # Auto-detect, medium preset
cup obfuscate src/ dist/ --preset heavy                     # Aggressive protection
cup obfuscate src/ dist/ --preset paranoid --dead-code high # Max protection + dead code
cup obfuscate src/ dist/ --config-file obfuscate.toml       # Load from config file
cup obfuscate src/ dist/ --disable-stage minify             # Skip minification
cup obfuscate src/ dist/ --strict                           # Fail if Node tools missing
cup obfuscate src/ dist/ --html index.html --static robots.txt assets/
cup obfuscate src/ dist/ --json                             # Machine-readable output
```
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Utils

<!-- cup:ref file=codeupipe/utils/__init__.py hash=9c3f862 -->
<!-- cup:ref file=codeupipe/utils/error_handling.py symbols=ErrorHandlingMixin,RetryFilter hash=dc0f5ec -->
| Type | Role |
|------|------|
| `ErrorHandlingMixin` | Error routing for pipelines |
| `RetryFilter` | Resilience wrapper — retries N times |
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Converter

<!-- cup:ref file=codeupipe/converter/__init__.py hash=117430e -->
| Export | Role |
|--------|------|
| `load_config` | Parse `.cup.json` or pattern defaults |
| `DEFAULT_CONFIG` | Default config dict |
| `PATTERN_DEFAULTS` | Pattern configs (mvc/clean/hexagonal/flat) |
| `build_export_pipeline` | CUP → standard Python |
| `build_import_pipeline` | Standard Python → CUP |
<!-- /cup:ref -->

---

## Linter Pipelines

<!-- cup:ref file=codeupipe/linter/__init__.py hash=84e6f07 -->
<!-- cup:ref file=codeupipe/linter/lint_pipeline.py symbols=build_lint_pipeline hash=ccff493 -->
<!-- cup:ref file=codeupipe/linter/coverage_pipeline.py symbols=build_coverage_pipeline hash=004f7b8 -->
<!-- cup:ref file=codeupipe/linter/report_pipeline.py symbols=build_report_pipeline hash=15f61c5 -->
<!-- cup:ref file=codeupipe/linter/doc_check_pipeline.py symbols=build_doc_check_pipeline hash=00e62dc -->
| Pipeline | Command | Purpose |
|----------|---------|---------|
| `build_lint_pipeline()` | `cup lint` | Standards violations (CUP000–CUP008) |
| `build_coverage_pipeline()` | `cup coverage` | Component↔test coverage gaps |
| `build_report_pipeline()` | `cup report` | Health report with scores |
| `build_doc_check_pipeline()` | `cup doc-check` | Doc freshness verification |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Testing Utilities

<!-- cup:ref file=codeupipe/testing.py symbols=run_filter,run_pipeline,assert_payload,assert_keys,assert_state,mock_filter hash=65f0296 -->
| Helper | Purpose |
|--------|---------|
| `run_filter(filter, data)` | Run one filter, returns Payload |
| `run_pipeline(pipeline, data)` | Run full pipeline |
| `assert_payload(payload, **kv)` | Assert key=value pairs |
| `assert_keys(payload, *keys)` | Assert keys exist |
| `assert_state(payload, ...)` | Assert State tracking |
| `mock_filter(**sets)` | Mock filter that sets keys |
| `mock_tap()` / `mock_hook()` | Recording mocks |
<!-- /cup:ref -->

---

## CLI

<!-- cup:ref file=codeupipe/cli/__init__.py symbols=main hash=4691a2f -->
<!-- cup:ref file=codeupipe/cli/__main__.py hash=eec6b5b -->
<!-- cup:ref file=codeupipe/cli/_registry.py symbols=CommandRegistry hash=8e82ece -->
<!-- cup:ref file=codeupipe/cli/_templates.py hash=c43b99a -->
<!-- cup:ref file=codeupipe/cli/_scaffold.py symbols=scaffold,COMPONENT_TYPES hash=1f62e60 -->
<!-- cup:ref file=codeupipe/cli/_bundle.py symbols=bundle hash=9a1b776 -->
<!-- cup:ref file=codeupipe/cli/commands/__init__.py symbols=setup_all hash=1f2d6ed -->
<!-- cup:ref file=codeupipe/cli/commands/scaffold_cmds.py hash=f410919 -->
<!-- cup:ref file=codeupipe/cli/commands/analysis_cmds.py symbols=lint,coverage,report,doc_check hash=9d54f93 -->
<!-- cup:ref file=codeupipe/cli/commands/run_cmds.py hash=1dbf404 -->
<!-- cup:ref file=codeupipe/cli/commands/deploy_cmds.py hash=9c59563 -->
<!-- cup:ref file=codeupipe/cli/commands/connect_cmds.py hash=eb63c26 -->
<!-- cup:ref file=codeupipe/cli/commands/project_cmds.py hash=6bad64b -->
<!-- cup:ref file=codeupipe/cli/commands/distribute_cmds.py hash=8cb53eb -->
<!-- cup:ref file=codeupipe/cli/commands/auth_cmds.py hash=a0df015 -->
<!-- cup:ref file=codeupipe/cli/commands/vault_cmds.py hash=d2fb81a -->
| Command | Purpose |
|---------|---------||
| `cup new <type> <name> [path]` | Scaffold component + test |
| `cup list` | Show component types |
| `cup bundle <path>` | Generate `__init__.py` re-exports |
| `cup lint <path>` | Check CUP conventions |
| `cup coverage <path>` | Map test coverage |
| `cup report <path>` | Health report |
| `cup doc-check [path]` | Doc freshness check |
| `cup run <config>` | Execute a pipeline from config (TOML/JSON) |
| `cup run --record <config>` | Execute + persist run record |
| `cup connect --list/--health` | List connectors / run health checks |
| `cup describe <config>` | Inspect pipeline inputs, outputs, steps |
| `cup test [path]` | Smart test runner (markers, coverage) |
| `cup doctor [path]` | Project health diagnostics |
| `cup runs` | Show recent pipeline run history |
| `cup upgrade [path]` | Regenerate scaffolded files to latest templates |
| `cup publish <dir>` | Validate & build for publishing |
| `cup graph <config>` | Mermaid pipeline visualization |
| `cup version [--bump]` | Show/bump semver from pyproject.toml |
| `cup auth login <provider>` | Browser-based OAuth2 login |
| `cup auth status <provider>` | Show credential status |
| `cup auth revoke <provider>` | Remove stored credentials |
| `cup auth list` | List all stored providers |
| `cup vault issue <provider>` | Issue a proxy token for a provider |
| `cup vault resolve <token>` | Verify proxy token validity |
| `cup vault revoke <token>` | Revoke a single proxy token |
| `cup vault revoke-all` | Revoke all active proxy tokens |
| `cup vault list` | List active proxy tokens |
| `cup vault status <token>` | Detailed proxy token inspection |
| `cup config --list` | List available platform contracts |
| `cup config <id> --var K=V` | Validate env vars against a platform contract |
| `cup config <id> --env-file .env` | Validate .env file against a contract |
| `cup obfuscate <src> <out>` | Build obfuscated SPA — minify HTML, obfuscate JS |
| `cup obfuscate <src> <out> --strict` | Fail if Node.js tools not installed |
| `--json` (global) | Machine-readable JSON output |
| `--auto-fix` (doc-check) | Non-interactive hash fix (AI/CI friendly) |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Observability

<!-- cup:ref file=codeupipe/observe.py symbols=CaptureTap,InsightTap,MetricsTap,RunRecord,save_run_record,load_run_records,export_captures_for_testing hash=cee4130 -->
| Export | Role |
|--------|------|
| `CaptureTap` | Tap that records payload snapshots for replay |
| `MetricsTap` | Tap that counts invocations and timestamps |
| `RunRecord` | Serializable pipeline run summary |
| `save_run_record` | Persist run record to `.cup/runs/` |
| `load_run_records` | Load recent run records |
| `export_captures_for_testing` | Generate pytest fixtures from captures |
<!-- /cup:ref -->

---

## Doctor

<!-- cup:ref file=codeupipe/doctor.py symbols=diagnose hash=36b8d51 -->
| Export | Role |
|--------|------|
| `diagnose` | Run 6 project health checks (manifest, CI, tests, lint, connectors, docs) |
<!-- /cup:ref -->

---

## Upgrade

<!-- cup:ref file=codeupipe/upgrade.py symbols=upgrade_project hash=681ba08 -->
| Export | Role |
|--------|------|
| `upgrade_project` | Regenerate CI/README to latest templates |
<!-- /cup:ref -->

---

## Graph

<!-- cup:ref file=codeupipe/graph.py symbols=pipeline_to_mermaid,render_graph hash=0b11399 -->
| Export | Role |
|--------|------|
| `pipeline_to_mermaid` | Convert pipeline config to Mermaid flowchart |
| `render_graph` | Load config file and generate diagram |
<!-- /cup:ref -->

---

## Runtime (Zero-Downtime Control)

<!-- cup:ref file=codeupipe/runtime.py symbols=TapSwitch,HotSwap,PipelineAccessor -->
| Export | Role |
|--------|------|
| `TapSwitch` | Toggle observation taps on/off at runtime without restarting |
| `HotSwap` | Atomically replace the active Pipeline from a new config file |
<!-- /cup:ref -->

---

## Auth (OAuth2 Integration)

<!-- cup:ref file=codeupipe/auth/__init__.py hash=85c76a2 -->
<!-- cup:ref file=codeupipe/auth/credential.py symbols=Credential,CredentialStore hash=c430594 -->
<!-- cup:ref file=codeupipe/auth/provider.py symbols=AuthProvider,GoogleOAuth,GitHubOAuth hash=88a42c5 -->
<!-- cup:ref file=codeupipe/auth/hook.py symbols=AuthHook hash=f2144d0 -->
<!-- cup:ref file=codeupipe/auth/_server.py symbols=run_oauth_flow hash=ae07f5c -->
<!-- cup:ref file=codeupipe/auth/proxy_token.py symbols=ProxyToken hash=686c997 -->
<!-- cup:ref file=codeupipe/auth/token_ledger.py symbols=LedgerEvent,TokenLedger hash=f6cd6dd -->
<!-- cup:ref file=codeupipe/auth/token_vault.py symbols=TokenVault hash=dfd347f -->
<!-- cup:ref file=codeupipe/auth/vault_hook.py symbols=VaultHook hash=899f08a -->
| Export | Role |
|--------|------|
| `Credential` | Token container with expiry tracking and serialization |
| `CredentialStore` | File-backed JSON persistence with auto-refresh |
| `AuthProvider` | ABC for OAuth2 flows (authorize, exchange, refresh) |
| `GoogleOAuth` | Google OAuth2 provider (all Google API scopes) |
| `GitHubOAuth` | GitHub OAuth2 provider |
| `AuthHook` | Pipeline hook that injects credentials before execution |
| `run_oauth_flow` | Browser-based OAuth2 callback server |
| `ProxyToken` | Opaque `cup_tok_*` reference token with TTL, scopes, usage limits |
| `TokenLedger` | Audit trail for proxy token lifecycle events |
| `TokenVault` | Central authority — issues, resolves, revokes proxy tokens |
| `VaultHook` | Pipeline hook — injects proxy tokens instead of real credentials |
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->
<!-- /cup:ref -->

---

## Registry (Composability Layer)

<!-- cup:ref file=codeupipe/registry.py symbols=Registry,cup_component,default_registry hash=5af5cbd -->
| Export | Role |
|--------|------|
| `Registry` | Name → component catalog with `register()`, `get()`, `discover()` |
| `cup_component` | Decorator — register a class with auto-name and auto-kind detection |
| `default_registry` | Module-level singleton Registry |
| `Pipeline.from_config()` | Build a Pipeline from a `.toml` or `.json` config file |
<!-- /cup:ref -->

---

## Tests

2015 tests across 60+ files. Full suite: `pytest`

---

*Maintained via `cup doc-check` — if a referenced file changes, the marker hash drifts and CI catches it.*
