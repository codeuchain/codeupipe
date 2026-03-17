"""
agent_docs_pipeline: Build the agent documentation pipeline.

Scans for skill domains, generates the skill index and domain docs,
and validates completeness.  Dogfooded as a CUP pipeline.

Usage::

    pipeline = build_agent_docs_pipeline()
    result = pipeline.run(Payload({
        "directory": ".",
        "docs_dir": "docs",
        "site_url": "https://example.github.io/project",
        "project_name": "myproject",
        "agent_docs_mode": "validate",   # or "init" or "update"
    }))
"""

from codeupipe import Pipeline

from .scan_skill_domains import ScanSkillDomains
from .generate_skill_index import GenerateSkillIndex
from .generate_domain_doc import GenerateDomainDocs
from .validate_agent_docs import ValidateAgentDocs


def build_agent_docs_pipeline() -> Pipeline:
    """Build and return the agent docs pipeline."""
    pipeline = Pipeline()
    pipeline.add_filter(ScanSkillDomains(), "scan_skill_domains")
    pipeline.add_filter(GenerateSkillIndex(), "generate_skill_index")
    pipeline.add_filter(GenerateDomainDocs(), "generate_domain_docs")
    pipeline.add_filter(ValidateAgentDocs(), "validate_agent_docs")
    return pipeline
