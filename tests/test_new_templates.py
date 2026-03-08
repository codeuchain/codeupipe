"""
Tests for new templates — cli, webhook, ml-pipeline, scheduled-job.

Verifies init_project scaffolds correctly for each of the 4 new templates.
"""

import pytest

from codeupipe.deploy.init import init_project, _TEMPLATES


class TestNewTemplates:
    """Verify the 4 new templates are registered and scaffold correctly."""

    @pytest.mark.unit
    @pytest.mark.parametrize("template", ["cli", "webhook", "ml-pipeline", "scheduled-job"])
    def test_template_registered(self, template):
        assert template in _TEMPLATES

    @pytest.mark.unit
    @pytest.mark.parametrize("template", ["cli", "webhook", "ml-pipeline", "scheduled-job"])
    def test_scaffold_new_template(self, tmp_path, template):
        result = init_project(
            template=template,
            name=f"test-{template}",
            output_dir=str(tmp_path / f"proj-{template}"),
        )
        proj_dir = tmp_path / f"proj-{template}"
        assert proj_dir.exists()

        # Should create cup.toml
        assert (proj_dir / "cup.toml").exists()
        manifest_text = (proj_dir / "cup.toml").read_text()
        assert f"test-{template}" in manifest_text

        # Should create pipeline recipe(s)
        recipes = _TEMPLATES[template]["recipes"]
        for recipe_name in recipes:
            assert (proj_dir / "pipelines" / f"{recipe_name}.json").exists()

    @pytest.mark.unit
    def test_all_eight_templates_present(self):
        expected = {"saas", "api", "etl", "chatbot", "cli", "webhook", "ml-pipeline", "scheduled-job"}
        assert set(_TEMPLATES.keys()) == expected
