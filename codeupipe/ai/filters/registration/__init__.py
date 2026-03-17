"""Registration Links — capability embedding and storage pipeline.

Links:
    ScanServerLink        — Introspect MCP server for capabilities
    ScanSkillsLink        — Scan filesystem for SKILL.md files
    ScanInstructionsLink  — Scan filesystem for *.instructions.md files
    ScanPlansLink         — Scan filesystem for plan .md files
    SyncLocalSourcesLink  — Diff scanned capabilities against registry
    EmbedCapabilityLink   — Embed capability description for indexing
    InsertCapabilityLink  — Store capability + embedding in registry
"""
