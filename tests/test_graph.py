"""
Tests for codeupipe.graph — Mermaid pipeline visualization.

Verifies pipeline_to_mermaid generates correct Mermaid syntax
for all step types (filter, tap, valve, parallel) and render_graph
handles file I/O.
"""

import json

import pytest

from codeupipe.graph import pipeline_to_mermaid, render_graph


# ── pipeline_to_mermaid ─────────────────────────────────────────────


class TestPipelineToMermaid:
    """Test Mermaid flowchart generation from pipeline configs."""

    @pytest.mark.unit
    def test_simple_linear_pipeline(self):
        config = {
            "pipeline": {
                "name": "etl",
                "steps": [
                    {"name": "Extract", "type": "filter"},
                    {"name": "Transform", "type": "filter"},
                    {"name": "Load", "type": "filter"},
                ],
            }
        }
        result = pipeline_to_mermaid(config)

        assert "graph TD" in result
        assert "Extract" in result
        assert "Transform" in result
        assert "Load" in result
        assert "START" in result
        assert "END" in result

    @pytest.mark.unit
    def test_tap_node_shape(self):
        config = {
            "pipeline": {
                "name": "with_tap",
                "steps": [
                    {"name": "Process", "type": "filter"},
                    {"name": "Logger", "type": "tap"},
                ],
            }
        }
        result = pipeline_to_mermaid(config)
        # Taps use parallelogram shape /"/
        assert '/\"Logger\"/' in result

    @pytest.mark.unit
    def test_valve_node_shape(self):
        config = {
            "pipeline": {
                "name": "gated",
                "steps": [
                    {"name": "AuthGate", "type": "valve"},
                    {"name": "DoWork", "type": "filter"},
                ],
            }
        }
        result = pipeline_to_mermaid(config)
        assert "AuthGate" in result

    @pytest.mark.unit
    def test_parallel_node_shape(self):
        config = {
            "pipeline": {
                "name": "fan_out",
                "steps": [
                    {"name": "Scatter", "type": "parallel"},
                ],
            }
        }
        result = pipeline_to_mermaid(config)
        # Parallel uses hexagon {{}}
        assert "Scatter" in result

    @pytest.mark.unit
    def test_empty_pipeline(self):
        config = {"pipeline": {"name": "empty", "steps": []}}
        result = pipeline_to_mermaid(config)
        assert "graph TD" in result

    @pytest.mark.unit
    def test_style_classes_present(self):
        config = {
            "pipeline": {
                "name": "styled",
                "steps": [{"name": "A", "type": "filter"}],
            }
        }
        result = pipeline_to_mermaid(config)
        assert "classDef filter" in result
        assert "classDef tap" in result
        assert "classDef valve" in result
        assert "classDef parallel" in result

    @pytest.mark.unit
    def test_flat_config_without_pipeline_key(self):
        """Config can be a flat dict without wrapping 'pipeline' key."""
        config = {
            "name": "flat",
            "steps": [
                {"name": "StepOne", "type": "filter"},
            ],
        }
        result = pipeline_to_mermaid(config)
        assert "StepOne" in result

    @pytest.mark.unit
    def test_default_type_is_filter(self):
        config = {
            "pipeline": {
                "name": "defaults",
                "steps": [{"name": "NoType"}],
            }
        }
        result = pipeline_to_mermaid(config)
        # Default type = filter → rectangle shape
        assert '["NoType"]' in result

    @pytest.mark.unit
    def test_edges_connect_sequential_steps(self):
        config = {
            "pipeline": {
                "name": "chain",
                "steps": [
                    {"name": "A", "type": "filter"},
                    {"name": "B", "type": "filter"},
                    {"name": "C", "type": "filter"},
                ],
            }
        }
        result = pipeline_to_mermaid(config)
        # A → B and B → C edges should exist
        assert " --> S1_B" in result
        assert " --> S2_C" in result
        # Last step → END
        assert " --> END" in result


# ── render_graph ────────────────────────────────────────────────────


class TestRenderGraph:
    """Test render_graph file I/O."""

    @pytest.mark.unit
    def test_render_from_file(self, tmp_path):
        config = {
            "pipeline": {
                "name": "file_test",
                "steps": [
                    {"name": "Read", "type": "filter"},
                    {"name": "Write", "type": "filter"},
                ],
            }
        }
        config_file = tmp_path / "pipeline.json"
        config_file.write_text(json.dumps(config))

        result = render_graph(str(config_file))
        assert "graph TD" in result
        assert "Read" in result
        assert "Write" in result

    @pytest.mark.unit
    def test_render_missing_file(self):
        with pytest.raises(FileNotFoundError):
            render_graph("/nonexistent/pipeline.json")
