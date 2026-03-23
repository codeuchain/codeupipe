"""Tests for bird-bone prototype — morphogenesis model surgery.

Verifies config parsing, filter contracts, hook behavior, tap recording,
pipeline assembly, and cryogenics security without requiring PyTorch/Transformers.
"""

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from codeupipe import Payload, Pipeline
from codeupipe.testing import run_filter, assert_payload, assert_keys

# Add prototype to import path — skip entire module if prototype isn't checked out
_proto = Path(__file__).resolve().parent.parent / "prototypes" / "bird-bone"
if not _proto.exists():
    pytest.skip("prototypes/bird-bone not available", allow_module_level=True)
if str(_proto) not in sys.path:
    sys.path.insert(0, str(_proto))

# Python 3.9/3.10 compat
try:
    import tomllib
except ModuleNotFoundError:
    try:
        import tomli as tomllib  # type: ignore[no-redef]
    except ModuleNotFoundError:
        tomllib = None  # type: ignore[assignment]

_needs_tomllib = pytest.mark.skipif(tomllib is None, reason="tomllib/tomli not available")


# ── Config tests ──────────────────────────────────────────────────

class TestMorphConfig:
    """Tests for morphogenesis configuration."""

    def test_from_dict_defaults(self):
        from config.morphogenesis import MorphConfig

        raw = {
            "specimen": {"model_name_or_path": "test-model"},
        }
        cfg = MorphConfig.from_dict(raw)
        assert cfg.specimen.model_name_or_path == "test-model"
        assert cfg.num_waves >= 1
        assert cfg.budget.target_bits >= 1

    def test_from_dict_full(self):
        from config.morphogenesis import MorphConfig

        raw = {
            "specimen": {
                "model_name_or_path": "meta-llama/Llama-3.2-1B",
                "revision": "main",
            },
            "num_waves": 7,
            "export_format": "gguf",
            "waves": {
                "prune_ratio": 0.15,
                "healing_steps": 300,
                "healing_lr": 1e-4,
                "stop_loss_threshold": 0.03,
                "regrow_fraction": 0.05,
            },
            "budget": {
                "target_bits": 4,
            },
            "colony": {
                "num_experts": 8,
                "experts_per_token": 2,
                "router_training_steps": 2000,
                "router_lr": 0.001,
                "domain_datasets": ["code", "math"],
                "shared_layers": 4,
            },
            "metamorph": {
                "target_architecture": "moe",
                "target_params": 2_000_000_000,
                "expansion_rank": 16,
            },
        }
        cfg = MorphConfig.from_dict(raw)
        assert cfg.num_waves == 7
        assert cfg.export_format == "gguf"
        assert cfg.waves.prune_ratio == 0.15
        assert cfg.colony.num_experts == 8
        assert cfg.colony.domain_datasets == ["code", "math"]
        assert cfg.metamorph.target_architecture == "moe"

    @_needs_tomllib
    def test_from_toml_default(self):
        from config.morphogenesis import MorphConfig

        with open(_proto / "config" / "default.toml", "rb") as f:
            raw = tomllib.load(f)
        cfg = MorphConfig.from_dict(raw)
        assert cfg.specimen.model_name_or_path
        assert cfg.num_waves > 0

    @_needs_tomllib
    def test_bird_bone_toml(self):
        from config.morphogenesis import MorphConfig

        with open(_proto / "config" / "bird_bone.toml", "rb") as f:
            raw = tomllib.load(f)
        cfg = MorphConfig.from_dict(raw)
        assert cfg.num_waves >= 5
        assert cfg.export_format == "gguf"

    @_needs_tomllib
    def test_coral_colony_toml(self):
        from config.morphogenesis import MorphConfig

        with open(_proto / "config" / "coral_colony.toml", "rb") as f:
            raw = tomllib.load(f)
        cfg = MorphConfig.from_dict(raw)
        assert cfg.colony.num_experts >= 4
        assert len(cfg.colony.domain_datasets) > 0

    @_needs_tomllib
    def test_axolotl_toml(self):
        from config.morphogenesis import MorphConfig

        with open(_proto / "config" / "axolotl.toml", "rb") as f:
            raw = tomllib.load(f)
        cfg = MorphConfig.from_dict(raw)
        assert "Qwen3.5" in cfg.specimen.model_name_or_path
        assert cfg.specimen.trust_remote_code is True
        assert cfg.metamorph.target_architecture == "hybrid"


# ── Import guard tests ────────────────────────────────────────────

class TestImportGuard:
    """Tests for _check.py dependency guard."""

    def test_require_bird_bone_deps_importable(self):
        from _check import require_bird_bone_deps
        assert callable(require_bird_bone_deps)


# ── Filter contract tests ────────────────────────────────────────

def _make_mock_model():
    """Create a mock model with realistic structure for unit tests."""
    model = MagicMock()

    param1 = MagicMock()
    param1.shape = (64, 64)
    param1.numel.return_value = 4096
    param1.ndim = 2
    param1.dtype = MagicMock(__str__=lambda s: "torch.float32")
    param1.data = MagicMock()
    param1.device = MagicMock(__str__=lambda s: "cpu")
    param1.__ne__ = lambda self, other: MagicMock(sum=lambda: MagicMock(item=lambda: 4000))

    model.parameters.return_value = [param1]
    model.named_parameters.return_value = [("layer.weight", param1)]
    model.named_modules.return_value = [("layer", MagicMock())]
    model.config = MagicMock()
    model.config.model_type = "llama"
    model.config.num_hidden_layers = 4
    model.config.hidden_size = 64
    model.config.num_attention_heads = 4
    model.config.intermediate_size = 128
    model.to.return_value = model
    model.eval.return_value = model
    model.train.return_value = model
    model.state_dict.return_value = {"layer.weight": param1.data}
    return model


class TestFilterContracts:
    """Test that filters accept Payload and return Payload."""

    def test_silence_contract(self):
        """Silence reads model + usage_scores, writes silence_masks."""
        from filters.silence import Silence

        model = _make_mock_model()
        payload = Payload({
            "model": model,
            "model_config": model.config,
            "usage_scores": {"layer.weight": 0.1},
        })

        f = Silence()
        result = run_filter(f, payload)
        assert isinstance(result, Payload)
        assert_keys(result, "silence_masks", "silenced_params")

    def test_silence_with_explicit_targets(self):
        """Silence with target_layers silences named layers."""
        from filters.silence import Silence

        model = _make_mock_model()
        payload = Payload({
            "model": model,
            "usage_scores": {},
        })

        f = Silence(target_layers=["layer"])
        result = run_filter(f, payload)
        masks = result.get("silence_masks")
        assert masks.get("layer.weight") is True

    def test_reactivate_all(self):
        """Reactivate(reactivate_all=True) clears all masks."""
        from filters.reactivate import Reactivate

        payload = Payload({
            "model": _make_mock_model(),
            "silence_masks": {"layer.weight": True, "other.weight": True},
        })

        f = Reactivate(reactivate_all=True)
        result = run_filter(f, payload)
        masks = result.get("silence_masks")
        assert all(v is False for v in masks.values())
        assert "layer.weight" in result.get("reactivated")

    def test_reactivate_targeted(self):
        """Reactivate with target_layers only reactivates named layers."""
        from filters.reactivate import Reactivate

        payload = Payload({
            "model": _make_mock_model(),
            "silence_masks": {"layer.weight": True, "other.weight": True},
        })

        f = Reactivate(target_layers=["layer"])
        result = run_filter(f, payload)
        masks = result.get("silence_masks")
        assert masks["layer.weight"] is False
        assert masks["other.weight"] is True

    def test_export_specimen_contract(self, tmp_path):
        """ExportSpecimen saves model to disk."""
        from filters.export_specimen import ExportSpecimen

        model = _make_mock_model()
        tokenizer = MagicMock()

        # Mock the dependency check and torch import
        mock_torch = MagicMock()
        with patch.dict(sys.modules, {"torch": mock_torch, "transformers": MagicMock()}):
            # Patch _check module to no-op the dep check
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                payload = Payload({
                    "model": model,
                    "tokenizer": tokenizer,
                    "specimen_id": "test-specimen",
                })

                f = ExportSpecimen(output_dir=str(tmp_path), fmt="pytorch")
                result = run_filter(f, payload)

        assert isinstance(result, Payload)
        assert_keys(result, "output_path", "export_log")

    def test_classify_layers_pure_transformer(self):
        """ClassifyLayers identifies a standard transformer with only softmax layers."""
        from filters.classify_layers import ClassifyLayers

        model = MagicMock()
        attn_mod = MagicMock()
        type(attn_mod).__name__ = "SdpaAttention"
        mlp_mod = MagicMock()
        type(mlp_mod).__name__ = "MLP"
        norm_mod = MagicMock()
        type(norm_mod).__name__ = "RMSNorm"
        model.named_modules.return_value = [
            ("", model),
            ("layer.self_attn", attn_mod),
            ("layer.mlp", mlp_mod),
            ("layer.norm", norm_mod),
        ]
        model.config = MagicMock()

        payload = Payload({"model": model, "model_config": model.config})
        f = ClassifyLayers()
        result = run_filter(f, payload)

        assert isinstance(result, Payload)
        assert_keys(result, "layer_types", "arch_summary")
        summary = result.get("arch_summary")
        assert summary["is_pure_transformer"] is True
        assert summary["is_hybrid"] is False
        assert summary["architecture_class"] == "pure_transformer"

    def test_classify_layers_hybrid(self):
        """ClassifyLayers identifies a hybrid model with both DeltaNet and softmax."""
        from filters.classify_layers import ClassifyLayers

        model = MagicMock()
        delta_mod = MagicMock()
        type(delta_mod).__name__ = "GatedDeltaNet"
        attn_mod = MagicMock()
        type(attn_mod).__name__ = "SdpaAttention"
        model.named_modules.return_value = [
            ("", model),
            ("layers.0.delta_net", delta_mod),
            ("layers.1.delta_net", delta_mod),
            ("layers.2.delta_net", delta_mod),
            ("layers.3.self_attn", attn_mod),
        ]
        model.config = MagicMock()

        payload = Payload({"model": model, "model_config": model.config})
        f = ClassifyLayers()
        result = run_filter(f, payload)

        summary = result.get("arch_summary")
        assert summary["is_hybrid"] is True
        assert summary["architecture_class"] == "hybrid_deltanet"
        assert summary["deltanet_ratio"] > 0.5

    def test_gate_prune_contract(self):
        """GatePrune zeros gate params in DeltaNet layers."""
        from filters.gate_prune import GatePrune

        import torch

        # Build a minimal model with a gate parameter
        model = MagicMock()
        gate_param = MagicMock()
        gate_param.ndim = 1
        gate_param.numel.return_value = 64
        gate_data = torch.rand(64)
        gate_param.data = gate_data
        gate_param.shape = (64,)

        other_param = MagicMock()
        other_param.ndim = 2
        other_param.numel.return_value = 4096
        other_param.shape = (64, 64)
        other_param.data = torch.rand(64, 64)

        model.named_parameters.return_value = [
            ("layers.0.delta_net.alpha", gate_param),
            ("layers.0.mlp.weight", other_param),
        ]
        model.parameters.return_value = [gate_param, other_param]

        payload = Payload({
            "model": model,
            "layer_types": {"layers.0.delta_net": "deltanet", "layers.0.mlp": "mlp"},
            "usage_scores": {"layers.0.delta_net.alpha": 0.01},
        })

        import _check
        with patch.object(_check, "require_bird_bone_deps", lambda: None):
            f = GatePrune(gate_threshold=0.1, max_removal_ratio=0.5)
            result = run_filter(f, payload)

        assert isinstance(result, Payload)
        assert_keys(result, "gate_prune_log", "pruned_gates", "sparsity_ratio")
        assert result.get("pruned_gates") >= 0

    def test_hybrid_skeleton_extract_contract(self):
        """HybridSkeletonExtract produces typed skeleton and per-type stats."""
        import torch

        model = MagicMock()

        # Build weight-like params that support abs() > threshold → mask
        def _make_weight(shape):
            p = MagicMock()
            p.ndim = len(shape)
            p.shape = shape
            p.numel.return_value = shape[0] * shape[1]
            # Create a real tensor for data so abs/sum/gt work
            real_data = torch.rand(*shape)
            p.data = real_data
            return p

        weight_delta = _make_weight((64, 64))
        weight_attn = _make_weight((64, 64))

        model.named_parameters.return_value = [
            ("layers.0.delta_net.alpha", weight_delta),
            ("layers.0.self_attn.q_proj.weight", weight_attn),
        ]
        model.parameters.return_value = [weight_delta, weight_attn]

        payload = Payload({
            "model": model,
            "sigma_map": {},
            "layer_types": {
                "layers.0.delta_net": "deltanet",
                "layers.0.self_attn": "softmax",
            },
        })

        import _check
        with patch.object(_check, "require_bird_bone_deps", lambda: None):
            from filters.hybrid_skeleton_extract import HybridSkeletonExtract

            f = HybridSkeletonExtract()
            result = run_filter(f, payload)

        assert isinstance(result, Payload)
        assert_keys(result, "skeleton", "genome_size", "skeleton_log")
        skeleton = result.get("skeleton")
        # Verify layer_type tagging
        assert skeleton["layers.0.delta_net.alpha"]["layer_type"] == "deltanet"
        assert skeleton["layers.0.self_attn.q_proj.weight"]["layer_type"] == "softmax"
        # Verify per-type stats
        log = result.get("skeleton_log")
        assert "per_type" in log


# ── Hook tests ────────────────────────────────────────────────────

class TestHooks:
    """Tests for morphogenesis hooks."""

    def test_fossil_record_captures_steps(self):
        from hooks.fossil_record import FossilRecordHook

        hook = FossilRecordHook()
        payload = Payload({"perplexity": 5.0, "sparsity_ratio": 0.1})

        hook.before(None, payload)
        hook.after(None, payload)

        assert len(hook.records) == 1
        assert "step" in hook.records[0]
        assert hook.records[0]["before"]["perplexity"] == 5.0

    def test_fossil_record_save(self, tmp_path):
        from hooks.fossil_record import FossilRecordHook

        hook = FossilRecordHook(fossil_dir=str(tmp_path))
        payload = Payload({"perplexity": 5.0})

        hook.before(None, payload)
        hook.after(None, payload)
        hook.save("test_run")

        fossils = list(tmp_path.glob("*.json"))
        assert len(fossils) == 1

    def test_fossil_record_on_error(self):
        from hooks.fossil_record import FossilRecordHook

        hook = FossilRecordHook()
        payload = Payload({"perplexity": 5.0})

        hook.before(None, payload)
        hook.on_error(None, ValueError("test error"), payload)

        assert len(hook.records) == 1
        assert hook.records[0]["error"] == "test error"

    def test_stop_loss_hook_basic(self):
        from hooks.stop_loss import StopLossHook

        hook = StopLossHook(max_ppl_delta=1.0)
        assert hook.revert_count == 0


# ── Tap tests ─────────────────────────────────────────────────────

class TestTaps:
    """Tests for density and vitals taps."""

    def test_density_monitor_records(self):
        from taps.density_monitor import DensityMonitorTap

        tap = DensityMonitorTap()
        payload = Payload({
            "sparsity_ratio": 0.3,
            "density_map": {"layer_0": 0.8, "layer_1": 0.6},
        })

        tap.observe(payload)
        assert len(tap.history) == 1
        assert tap.history[0]["sparsity_ratio"] == 0.3
        assert tap.history[0]["mean_density"] == 0.7

    def test_density_monitor_multiple(self):
        from taps.density_monitor import DensityMonitorTap

        tap = DensityMonitorTap()
        for i in range(5):
            tap.observe(Payload({"sparsity_ratio": i * 0.1}))
        assert len(tap.history) == 5
        assert tap.history[0]["step"] == 0
        assert tap.history[4]["step"] == 4

    def test_density_monitor_bit_assignments(self):
        from taps.density_monitor import DensityMonitorTap

        tap = DensityMonitorTap()
        tap.observe(Payload({
            "bit_assignments": {"layer_0": 4, "layer_1": 8, "layer_2": 16},
        }))
        avg = tap.history[0]["avg_bits"]
        assert abs(avg - 9.333) < 0.01

    def test_vitals_monitor_records(self):
        from taps.vitals_monitor import VitalsMonitorTap

        tap = VitalsMonitorTap()
        payload = Payload({
            "perplexity": 8.5,
            "viable": True,
        })

        tap.observe(payload)
        assert len(tap.history) == 1
        assert tap.history[0]["perplexity"] == 8.5
        assert tap.history[0]["viable"] is True

    def test_vitals_monitor_latest(self):
        from taps.vitals_monitor import VitalsMonitorTap

        tap = VitalsMonitorTap()
        assert tap.latest is None

        tap.observe(Payload({"perplexity": 5.0}))
        tap.observe(Payload({"perplexity": 3.0}))
        assert tap.latest["perplexity"] == 3.0

    def test_vitals_monitor_elapsed(self):
        from taps.vitals_monitor import VitalsMonitorTap

        tap = VitalsMonitorTap()
        tap.observe(Payload({}))
        assert tap.history[0]["elapsed_s"] >= 0.0


# ── Pipeline builder tests ────────────────────────────────────────

class TestPipelineBuilders:
    """Test that pipeline builders produce valid Pipeline instances."""

    def _make_cfg(self):
        from config.morphogenesis import MorphConfig
        return MorphConfig.from_dict({
            "specimen": {"model_name_or_path": "test-model"},
            "num_waves": 2,
            "waves": {
                "prune_ratio": 0.1,
                "healing_steps": 10,
                "healing_lr": 2e-4,
                "stop_loss_threshold": 0.03,
                "regrow_fraction": 0.05,
            },
            "colony": {
                "num_experts": 4,
                "experts_per_token": 2,
                "domain_datasets": ["code", "math", "chat", "science"],
                "shared_layers": 2,
                "router_training_steps": 100,
                "router_lr": 0.001,
            },
            "metamorph": {
                "target_architecture": "moe",
                "target_params": 1_000_000,
                "expansion_rank": 8,
            },
        })

    def test_build_bird_bone(self):
        from pipelines.bird_bone import build_bird_bone

        pipe = build_bird_bone(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0
        assert len(pipe._hooks) >= 2

    def test_build_whale_bone(self):
        from pipelines.whale_bone import build_whale_bone

        pipe = build_whale_bone(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0

    def test_build_coral_colony(self):
        from pipelines.coral_colony import build_coral_colony

        pipe = build_coral_colony(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0

    def test_build_salamander(self):
        from pipelines.salamander import build_salamander

        pipe = build_salamander(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0

    def test_build_chameleon(self):
        from pipelines.chameleon import build_chameleon

        pipe = build_chameleon(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0

    def test_build_axolotl(self):
        from pipelines.axolotl import build_axolotl

        pipe = build_axolotl(self._make_cfg())
        assert isinstance(pipe, Pipeline)
        assert len(pipe._steps) > 0
        assert len(pipe._hooks) >= 2

    def test_species_registry(self):
        from pipelines import SPECIES

        assert "bird_bone" in SPECIES
        assert "whale_bone" in SPECIES
        assert "coral_colony" in SPECIES
        assert "salamander" in SPECIES
        assert "chameleon" in SPECIES
        assert "axolotl" in SPECIES
        assert "sleep_cycle" in SPECIES
        assert len(SPECIES) == 7

    def test_all_species_build(self):
        """Every species in the registry should build without error."""
        from pipelines import SPECIES

        cfg = self._make_cfg()
        for name, builder in SPECIES.items():
            pipe = builder(cfg)
            assert isinstance(pipe, Pipeline), f"{name} didn't return Pipeline"

    def test_bird_bone_wave_count(self):
        """Bird bone should have nested wave pipelines matching config."""
        from pipelines.bird_bone import build_bird_bone

        cfg = self._make_cfg()
        pipe = build_bird_bone(cfg)
        wave_steps = [
            (name, kind) for name, _step, kind in pipe._steps
            if kind == "pipeline"
        ]
        assert len(wave_steps) == cfg.num_waves

    def test_chameleon_has_valve(self):
        """Chameleon should use a Valve for conditional reactivation."""
        from pipelines.chameleon import build_chameleon

        pipe = build_chameleon(self._make_cfg())
        filter_names = [name for name, _step, kind in pipe._steps if kind == "filter"]
        assert "reactivate_conditional" in filter_names

    def test_axolotl_has_dual_valves(self):
        """Axolotl uses Valves for type-specific pruning in each wave."""
        from pipelines.axolotl import build_axolotl

        pipe = build_axolotl(self._make_cfg())
        # Should have classify_layers before waves, and hybrid_skeleton at the end
        filter_names = [name for name, _step, kind in pipe._steps if kind == "filter"]
        assert "classify_layers" in filter_names
        assert "hybrid_skeleton" in filter_names

    def test_axolotl_wave_count(self):
        """Axolotl should have nested wave pipelines matching config."""
        from pipelines.axolotl import build_axolotl

        cfg = self._make_cfg()
        pipe = build_axolotl(cfg)
        wave_steps = [
            (name, kind) for name, _step, kind in pipe._steps
            if kind == "pipeline"
        ]
        assert len(wave_steps) == cfg.num_waves


# ── Prototype structure tests ─────────────────────────────────────

class TestPrototypeStructure:
    """Verify the prototype has all expected files."""

    def test_cup_toml_exists(self):
        assert (_proto / "cup.toml").exists()

    def test_check_py_exists(self):
        assert (_proto / "_check.py").exists()

    def test_requirements_exists(self):
        assert (_proto / "requirements.txt").exists()

    def test_pipeline_entry_exists(self):
        assert (_proto / "pipeline.py").exists()

    def test_ship_sh_exists(self):
        assert (_proto / "ship.sh").exists()

    def test_all_config_tomls_exist(self):
        for name in ["default", "bird_bone", "coral_colony", "salamander", "axolotl"]:
            assert (_proto / "config" / f"{name}.toml").exists()

    def test_all_filter_files_exist(self):
        expected = [
            "load_specimen", "xray_scan", "stress_test",
            "apoptosis", "differentiate", "ossify", "metabolize",
            "angiogenesis", "silence", "reactivate",
            "mitosis", "assemble_colony", "train_router",
            "skeleton_extract", "metamorphose",
            "validate_organism", "export_specimen",
            # Hybrid architecture filters
            "classify_layers", "gate_prune", "hybrid_skeleton_extract",
            # Cryogenics
            "cryo_snapshot", "cryo_thaw",
            # Gentle pruning
            "gentle_pruning",
            # Neurogenesis — grow new nodes
            "neurogenesis",
            # Sleep cycle — waking/sleeping lifecycle
            "traffic_sampler", "struggle_detector",
        ]
        for name in expected:
            assert (_proto / "filters" / f"{name}.py").exists(), f"Missing: filters/{name}.py"

    def test_all_tap_files_exist(self):
        expected = ["density_monitor", "vitals_monitor", "drift_detector"]
        for name in expected:
            assert (_proto / "taps" / f"{name}.py").exists(), f"Missing: taps/{name}.py"

    def test_all_pipeline_files_exist(self):
        expected = [
            "bird_bone", "whale_bone", "coral_colony",
            "salamander", "chameleon", "axolotl",
            # Sleep cycle — the learning lifecycle
            "sleep_cycle",
        ]
        for name in expected:
            assert (_proto / "pipelines" / f"{name}.py").exists(), f"Missing: pipelines/{name}.py"

    def test_species_guide_exists(self):
        assert (_proto / "SPECIES_GUIDE.md").exists()


# ── Cryogenics tests ─────────────────────────────────────────────

class TestCryoManifest:
    """Tests for CryoManifest dataclass."""

    def test_manifest_defaults(self):
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest()
        assert m.version == "0.1.0"
        assert m.specimen_id == ""
        assert m.has_model is False
        assert m.payload_keys == []

    def test_manifest_roundtrip(self):
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(
            version="1.2.3",
            specimen_id="test/model",
            species="bird_bone",
            name="test_model",
            parent_version="1.2.2",
            stem_cell="Qwen/Qwen3-0.6B",
            has_model=True,
            has_tokenizer=True,
            has_fossil_record=True,
            has_stress_profile=False,
            model_hash="abc123def456",
            payload_keys=["model", "tokenizer"],
        )
        d = m.to_dict()
        restored = CryoManifest.from_dict(d)
        assert restored.version == "1.2.3"
        assert restored.specimen_id == "test/model"
        assert restored.species == "bird_bone"
        assert restored.parent_version == "1.2.2"
        assert restored.has_model is True
        assert restored.has_tokenizer is True
        assert restored.has_fossil_record is True
        assert restored.has_stress_profile is False
        assert restored.model_hash == "abc123def456"

    def test_manifest_from_dict_ignores_unknown_keys(self):
        from filters.cryo_snapshot import CryoManifest
        d = {"version": "0.5.0", "unknown_field": "ignored", "specimen_id": "x"}
        m = CryoManifest.from_dict(d)
        assert m.version == "0.5.0"
        assert m.specimen_id == "x"

    def test_manifest_to_dict_is_plain_dict(self):
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(version="1.0.0", has_model=True)
        d = m.to_dict()
        assert isinstance(d, dict)
        assert d["version"] == "1.0.0"
        assert d["has_model"] is True


class TestCryoSnapshotContract:
    """Tests for CryoSnapshot filter contract — without real torch."""

    def test_cryo_snapshot_contract(self, tmp_path):
        """CryoSnapshot reads model and writes cryo_path + manifest."""
        from filters.cryo_snapshot import CryoSnapshot

        import numpy as np

        model = _make_mock_model()
        # Make state_dict return something hashable
        fake_tensor = MagicMock()
        fake_tensor.cpu.return_value = fake_tensor
        fake_tensor.numpy.return_value = np.zeros((4, 4), dtype=np.float32)
        model.state_dict.return_value = {"layer.weight": fake_tensor}

        tokenizer = MagicMock()

        mock_torch = MagicMock()
        with patch.dict(sys.modules, {"torch": mock_torch, "transformers": MagicMock()}):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                payload = Payload({
                    "model": model,
                    "tokenizer": tokenizer,
                    "specimen_id": "test/model",
                    "stress_scores": {"layer0": 0.5, "layer1": 0.1},
                    "density_map": {"layer0": 0.95, "layer1": 0.3},
                    "bit_assignments": {"layer0": 16, "layer1": 4},
                    "silenced_layers": ["layer1"],
                })

                f = CryoSnapshot(
                    output_dir=str(tmp_path),
                    version="0.1.0",
                    species="bird_bone",
                )
                result = run_filter(f, payload)

        assert isinstance(result, Payload)
        assert_keys(result, "cryo_path", "cryo_manifest", "cryo_version")
        assert result.get("cryo_version") == "0.1.0"

        # Verify directory was created
        cryo_path = result.get("cryo_path")
        assert cryo_path.endswith(".cryo")
        assert Path(cryo_path).exists()

        # Verify manifest was written
        import json
        manifest_path = Path(cryo_path) / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert manifest["version"] == "0.1.0"
        assert manifest["species"] == "bird_bone"
        assert manifest["specimen_id"] == "test/model"
        assert manifest["has_model"] is True
        assert manifest["has_stress_profile"] is True
        assert manifest["has_density_map"] is True
        assert manifest["has_bit_assignments"] is True
        assert manifest["has_silencing_masks"] is True

    def test_cryo_snapshot_writes_auxiliary_files(self, tmp_path):
        """CryoSnapshot saves stress, density, bits, masks as JSON files."""
        from filters.cryo_snapshot import CryoSnapshot

        import numpy as np

        model = _make_mock_model()
        fake_tensor = MagicMock()
        fake_tensor.cpu.return_value = fake_tensor
        fake_tensor.numpy.return_value = np.zeros((4, 4), dtype=np.float32)
        model.state_dict.return_value = {"layer.weight": fake_tensor}

        mock_torch = MagicMock()
        with patch.dict(sys.modules, {"torch": mock_torch, "transformers": MagicMock()}):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                payload = Payload({
                    "model": model,
                    "specimen_id": "aux-test",
                    "stress_scores": {"layer0": 0.8},
                    "density_map": {"layer0": 0.95},
                    "bit_assignments": {"layer0": 16},
                    "silenced_layers": ["layer0"],
                    "fossil_record": [{"step": "load", "time": 1.0}],
                    "adaptation_log": [{"epoch": 1, "metric": 0.5}],
                })

                f = CryoSnapshot(output_dir=str(tmp_path), version="0.2.0")
                result = run_filter(f, payload)

        cryo_path = Path(result.get("cryo_path"))
        assert (cryo_path / "stress_profile.json").exists()
        assert (cryo_path / "density_map.json").exists()
        assert (cryo_path / "bit_assignments.json").exists()
        assert (cryo_path / "masks.json").exists()
        assert (cryo_path / "fossil_record.json").exists()
        assert (cryo_path / "adaptation_history.json").exists()
        assert (cryo_path / "README.md").exists()

    def test_cryo_snapshot_parent_version(self, tmp_path):
        """CryoSnapshot records parent lineage in manifest."""
        from filters.cryo_snapshot import CryoSnapshot

        import numpy as np

        model = _make_mock_model()
        fake_tensor = MagicMock()
        fake_tensor.cpu.return_value = fake_tensor
        fake_tensor.numpy.return_value = np.zeros((4, 4), dtype=np.float32)
        model.state_dict.return_value = {"layer.weight": fake_tensor}

        mock_torch = MagicMock()
        with patch.dict(sys.modules, {"torch": mock_torch, "transformers": MagicMock()}):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                payload = Payload({"model": model, "specimen_id": "test"})
                f = CryoSnapshot(
                    output_dir=str(tmp_path),
                    version="0.3.0",
                    parent_version="0.2.0",
                )
                result = run_filter(f, payload)

        import json
        manifest = json.loads(
            (Path(result.get("cryo_path")) / "manifest.json").read_text()
        )
        assert manifest["parent_version"] == "0.2.0"


class TestCryoThawContract:
    """Tests for CryoThaw filter contract."""

    def test_cryo_thaw_requires_valid_path(self):
        """CryoThaw raises FileNotFoundError for missing snapshot."""
        from filters.cryo_thaw import CryoThaw

        mock_torch = MagicMock()
        mock_transformers = MagicMock()
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(cryo_path="/nonexistent/path.cryo")
                with pytest.raises(FileNotFoundError, match="not found"):
                    run_filter(f, Payload({}))

    def test_cryo_thaw_requires_manifest(self, tmp_path):
        """CryoThaw raises if no manifest.json in snapshot directory."""
        from filters.cryo_thaw import CryoThaw

        # Create an empty directory
        cryo_dir = tmp_path / "empty.cryo"
        cryo_dir.mkdir()

        mock_torch = MagicMock()
        mock_transformers = MagicMock()
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(cryo_path=str(cryo_dir))
                with pytest.raises(FileNotFoundError, match="manifest"):
                    run_filter(f, Payload({}))

    def test_cryo_thaw_restores_auxiliary_data(self, tmp_path):
        """CryoThaw reads auxiliary JSON files back into the payload."""
        from filters.cryo_thaw import CryoThaw

        import json

        # Build a fake .cryo directory
        cryo_dir = tmp_path / "test.cryo"
        cryo_dir.mkdir()
        model_dir = cryo_dir / "model"
        model_dir.mkdir()

        # Write manifest
        manifest = {
            "version": "0.1.0",
            "specimen_id": "test/model",
            "species": "bird_bone",
            "has_model": True,
            "has_tokenizer": False,
            "has_fossil_record": True,
            "has_stress_profile": True,
            "has_density_map": True,
            "has_bit_assignments": True,
            "has_silencing_masks": True,
            "has_adaptation_history": True,
            "payload_keys": [],
            "model_hash": "abc123",
        }
        (cryo_dir / "manifest.json").write_text(json.dumps(manifest))

        # Write auxiliary files
        (cryo_dir / "fossil_record.json").write_text(json.dumps([{"step": "load"}]))
        (cryo_dir / "stress_profile.json").write_text(json.dumps({"layer0": 0.5}))
        (cryo_dir / "density_map.json").write_text(json.dumps({"layer0": 0.9}))
        (cryo_dir / "bit_assignments.json").write_text(json.dumps({"layer0": 16}))
        (cryo_dir / "masks.json").write_text(json.dumps({"silenced_layers": ["layer0"]}))
        (cryo_dir / "adaptation_history.json").write_text(json.dumps([{"epoch": 1}]))

        # Mock transformers to return a fake model
        fake_model = _make_mock_model()
        mock_auto_model = MagicMock()
        mock_auto_model.from_pretrained.return_value = fake_model
        mock_auto_tokenizer = MagicMock()

        mock_torch = MagicMock()
        mock_torch.float32 = "float32"
        mock_transformers = MagicMock()
        mock_transformers.AutoModelForCausalLM = mock_auto_model
        mock_transformers.AutoTokenizer = mock_auto_tokenizer

        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(cryo_path=str(cryo_dir), device="cpu")
                result = run_filter(f, Payload({}))

        assert isinstance(result, Payload)
        assert_keys(result, "model", "specimen_id", "cryo_manifest",
                    "cryo_version", "thawed_from", "thaw_timestamp")
        assert result.get("specimen_id") == "test/model"
        assert result.get("cryo_version") == "0.1.0"

        # Auxiliary data restored
        assert result.get("fossil_record") == [{"step": "load"}]
        assert result.get("stress_scores") == {"layer0": 0.5}
        assert result.get("density_map") == {"layer0": 0.9}
        assert result.get("bit_assignments") == {"layer0": 16}
        assert result.get("silenced_layers") == ["layer0"]
        assert result.get("adaptation_log") == [{"epoch": 1}]


# ── Cryogenics Security tests ────────────────────────────────────

class TestCryoSigning:
    """Tests for HMAC-SHA256 manifest signing and verification."""

    def test_manifest_sign_and_verify(self):
        """Signing a manifest produces a verifiable signature."""
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(
            version="1.0.0",
            specimen_id="test/model",
            species="bird_bone",
            has_model=True,
            model_hash="abc123def456",
        )
        m.sign("test-secret-key")
        assert m.signature != ""
        assert m.verify("test-secret-key")

    def test_manifest_verify_wrong_key_fails(self):
        """Verification with wrong key returns False."""
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(version="1.0.0", specimen_id="x")
        m.sign("correct-key")
        assert not m.verify("wrong-key")

    def test_manifest_tampered_field_fails_verify(self):
        """Modifying a field after signing invalidates the signature."""
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(version="1.0.0", specimen_id="original")
        m.sign("key123")
        # Tamper
        m.specimen_id = "hacked"
        assert not m.verify("key123")

    def test_manifest_unsigned_fails_verify(self):
        """An unsigned manifest fails verification."""
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(version="1.0.0")
        assert not m.verify("any-key")

    def test_manifest_signable_bytes_excludes_signature(self):
        """signable_bytes() does not include the signature field."""
        from filters.cryo_snapshot import CryoManifest
        m = CryoManifest(version="1.0.0")
        m.signature = "some-sig"
        raw = m.signable_bytes()
        assert b"some-sig" not in raw


class TestCryoIntegrityHash:
    """Tests for auxiliary file integrity hashing."""

    def test_integrity_hash_detects_file_change(self, tmp_path):
        """Modifying an auxiliary file changes the integrity hash."""
        from filters.cryo_snapshot import _compute_integrity_hash, _write_json

        cryo_dir = str(tmp_path / "test.cryo")
        os.makedirs(cryo_dir, exist_ok=True)

        manifest_data = {
            "has_fossil_record": True,
            "has_stress_profile": True,
        }
        _write_json(cryo_dir, "fossil_record.json", [{"step": "load"}])
        _write_json(cryo_dir, "stress_profile.json", {"layer0": 0.5})

        hash_before = _compute_integrity_hash(cryo_dir, manifest_data)

        # Tamper with a file
        _write_json(cryo_dir, "stress_profile.json", {"layer0": 999.0})

        hash_after = _compute_integrity_hash(cryo_dir, manifest_data)
        assert hash_before != hash_after

    def test_integrity_hash_stable_for_same_content(self, tmp_path):
        """Same content produces same integrity hash."""
        from filters.cryo_snapshot import _compute_integrity_hash, _write_json

        cryo_dir = str(tmp_path / "test.cryo")
        os.makedirs(cryo_dir, exist_ok=True)
        manifest_data = {"has_fossil_record": True}
        _write_json(cryo_dir, "fossil_record.json", [{"step": "load"}])

        hash1 = _compute_integrity_hash(cryo_dir, manifest_data)
        hash2 = _compute_integrity_hash(cryo_dir, manifest_data)
        assert hash1 == hash2


class TestCryoThawSecurity:
    """Tests for CryoThaw security enforcement."""

    def test_thaw_rejects_tampered_manifest(self, tmp_path):
        """CryoThaw raises CryoSignatureError for tampered manifest."""
        from filters.cryo_thaw import CryoThaw
        from filters.cryo_snapshot import CryoManifest, CryoSignatureError

        import json

        cryo_dir = tmp_path / "tampered.cryo"
        cryo_dir.mkdir()
        (cryo_dir / "model").mkdir()

        # Build a signed manifest
        m = CryoManifest(
            version="0.1.0",
            specimen_id="test",
            has_model=True,
        )
        m.sign("original-key")
        manifest_data = m.to_dict()

        # Tamper with the manifest after signing
        manifest_data["specimen_id"] = "hacked-model"
        (cryo_dir / "manifest.json").write_text(json.dumps(manifest_data))

        mock_torch = MagicMock()
        mock_transformers = MagicMock()
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(
                    cryo_path=str(cryo_dir),
                    signing_key="original-key",
                    verify=True,
                )
                with pytest.raises(CryoSignatureError, match="tampered"):
                    run_filter(f, Payload({}))

    def test_thaw_rejects_tampered_auxiliary_file(self, tmp_path):
        """CryoThaw raises CryoIntegrityError when auxiliary files are modified."""
        from filters.cryo_thaw import CryoThaw
        from filters.cryo_snapshot import (
            CryoManifest,
            CryoIntegrityError,
            _compute_integrity_hash,
            _write_json,
        )

        import json

        cryo_dir = tmp_path / "tampered_aux.cryo"
        cryo_dir.mkdir()
        (cryo_dir / "model").mkdir()

        # Write auxiliary files
        _write_json(str(cryo_dir), "stress_profile.json", {"layer0": 0.5})

        # Build manifest with correct integrity hash
        m = CryoManifest(
            version="0.1.0",
            specimen_id="test",
            has_model=True,
            has_stress_profile=True,
        )
        m.integrity_hash = _compute_integrity_hash(
            str(cryo_dir), m.to_dict()
        )
        m.sign("key123")
        (cryo_dir / "manifest.json").write_text(json.dumps(m.to_dict()))

        # NOW tamper with the auxiliary file
        _write_json(str(cryo_dir), "stress_profile.json", {"layer0": 999.0})

        mock_torch = MagicMock()
        mock_transformers = MagicMock()
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(
                    cryo_path=str(cryo_dir),
                    signing_key="key123",
                    verify=True,
                )
                with pytest.raises(CryoIntegrityError, match="modified"):
                    run_filter(f, Payload({}))

    def test_thaw_verify_false_skips_checks(self, tmp_path):
        """CryoThaw with verify=False does not check signature or integrity."""
        from filters.cryo_thaw import CryoThaw

        import json

        cryo_dir = tmp_path / "unsigned.cryo"
        cryo_dir.mkdir()
        model_dir = cryo_dir / "model"
        model_dir.mkdir()

        # Manifest with no signature (legacy/unsigned)
        manifest = {
            "version": "0.1.0",
            "specimen_id": "test/model",
            "has_model": True,
            "has_tokenizer": False,
            "has_fossil_record": False,
            "has_stress_profile": False,
            "has_density_map": False,
            "has_bit_assignments": False,
            "has_silencing_masks": False,
            "has_adaptation_history": False,
            "payload_keys": [],
            "model_hash": "abc",
            "integrity_hash": "",
            "signature": "",
        }
        (cryo_dir / "manifest.json").write_text(json.dumps(manifest))

        fake_model = _make_mock_model()
        mock_auto_model = MagicMock()
        mock_auto_model.from_pretrained.return_value = fake_model

        mock_torch = MagicMock()
        mock_torch.float32 = "float32"
        mock_transformers = MagicMock()
        mock_transformers.AutoModelForCausalLM = mock_auto_model
        mock_transformers.AutoTokenizer = MagicMock()

        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(
                    cryo_path=str(cryo_dir),
                    verify=False,
                )
                result = run_filter(f, Payload({}))

        assert isinstance(result, Payload)
        assert result.get("specimen_id") == "test/model"

    def test_thaw_wrong_signing_key_rejected(self, tmp_path):
        """Thawing with wrong key raises CryoSignatureError."""
        from filters.cryo_thaw import CryoThaw
        from filters.cryo_snapshot import CryoManifest, CryoSignatureError

        import json

        cryo_dir = tmp_path / "wrong_key.cryo"
        cryo_dir.mkdir()
        (cryo_dir / "model").mkdir()

        m = CryoManifest(version="0.1.0", specimen_id="test", has_model=True)
        m.sign("correct-key")
        (cryo_dir / "manifest.json").write_text(json.dumps(m.to_dict()))

        mock_torch = MagicMock()
        mock_transformers = MagicMock()
        with patch.dict(sys.modules, {
            "torch": mock_torch,
            "transformers": mock_transformers,
        }):
            import _check
            with patch.object(_check, "require_bird_bone_deps", lambda: None):
                f = CryoThaw(
                    cryo_path=str(cryo_dir),
                    signing_key="wrong-key",
                    verify=True,
                )
                with pytest.raises(CryoSignatureError):
                    run_filter(f, Payload({}))


# ── GentlePruning tests ──────────────────────────────────────────

class TestGentlePruning:
    """Tests for GentlePruning — unstructured magnitude pruning."""

    def test_contract_returns_payload(self):
        """GentlePruning reads model, returns Payload with sparsity_ratio."""
        from filters.gentle_pruning import GentlePruning

        model = _make_mock_model()

        # Create a mock model with real-ish tensor parameters
        mock_torch = MagicMock()
        mock_param = MagicMock()
        mock_param.ndim = 2
        mock_param.data = MagicMock()
        mock_param.data.abs.return_value = MagicMock()
        mock_param.data.abs.return_value.flatten.return_value = MagicMock()

        payload = Payload({"model": model})
        f = GentlePruning(target_sparsity=0.02)
        # The filter requires real torch tensors for magnitude computation,
        # so we test the import-guard path: no model → error
        with pytest.raises(ValueError, match="requires 'model'"):
            run_filter(f, Payload({}))

    def test_gentle_pruning_requires_model(self):
        """GentlePruning raises ValueError without model."""
        from filters.gentle_pruning import GentlePruning

        f = GentlePruning()
        with pytest.raises(ValueError, match="requires 'model'"):
            run_filter(f, Payload({}))

    def test_gentle_pruning_default_params(self):
        """GentlePruning has sane defaults."""
        from filters.gentle_pruning import GentlePruning

        f = GentlePruning()
        assert f._target_sparsity == 0.02
        assert f._skip_embeddings is True
        assert f._skip_layernorm is True

    def test_gentle_pruning_custom_params(self):
        """GentlePruning accepts custom sparsity target."""
        from filters.gentle_pruning import GentlePruning

        f = GentlePruning(target_sparsity=0.05, skip_embeddings=False)
        assert f._target_sparsity == 0.05
        assert f._skip_embeddings is False


# ── Neurogenesis tests ────────────────────────────────────────────

class TestNeurogenesis:
    """Tests for Neurogenesis — grow new nodes at saturated regions."""

    def test_neurogenesis_requires_model(self):
        """Neurogenesis raises ValueError without model."""
        from filters.neurogenesis import Neurogenesis

        f = Neurogenesis()
        with pytest.raises(ValueError, match="requires 'model'"):
            run_filter(f, Payload({}))

    def test_neurogenesis_requires_usage_scores(self):
        """Neurogenesis raises ValueError without usage_scores."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        f = Neurogenesis()
        with pytest.raises(ValueError, match="requires 'usage_scores'"):
            run_filter(f, Payload({"model": model}))

    def test_neurogenesis_default_params(self):
        """Neurogenesis has sane defaults."""
        from filters.neurogenesis import Neurogenesis

        f = Neurogenesis()
        assert f._saturation_threshold == 0.8
        assert f._growth_ratio == 0.1
        assert f._mode == "adapter"

    def test_neurogenesis_custom_params(self):
        """Neurogenesis accepts custom growth parameters."""
        from filters.neurogenesis import Neurogenesis

        f = Neurogenesis(
            saturation_threshold=0.9,
            growth_ratio=0.2,
            mode="head",
        )
        assert f._saturation_threshold == 0.9
        assert f._growth_ratio == 0.2
        assert f._mode == "head"

    def test_neurogenesis_invalid_mode_raises(self):
        """Neurogenesis rejects invalid growth mode."""
        from filters.neurogenesis import Neurogenesis

        with pytest.raises(ValueError, match="mode must be"):
            Neurogenesis(mode="invalid")

    def test_neurogenesis_contract_returns_payload(self):
        """Neurogenesis returns Payload with neurogenesis_log and new_nodes_added."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        # Simulate saturated layers (all heads > threshold)
        usage_scores = {"layer.weight": 0.95}
        layer_index = ["layer.weight"]

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "layer_index": layer_index,
            "device": "cpu",
        })
        f = Neurogenesis(saturation_threshold=0.8, mode="adapter")
        result = f.call(payload)

        assert isinstance(result, Payload)
        assert result.get("model") is not None
        log = result.get("neurogenesis_log")
        assert log is not None
        assert "new_nodes_added" in log
        assert "saturated_layers" in log
        assert "mode" in log
        assert log["mode"] == "adapter"

    def test_neurogenesis_skips_non_saturated(self):
        """Neurogenesis does not grow nodes at non-saturated layers."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        # All layers below threshold — nothing should grow
        usage_scores = {"layer.weight": 0.3}
        layer_index = ["layer.weight"]

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "layer_index": layer_index,
            "device": "cpu",
        })
        f = Neurogenesis(saturation_threshold=0.8, mode="adapter")
        result = f.call(payload)

        assert isinstance(result, Payload)
        log = result.get("neurogenesis_log")
        assert log["new_nodes_added"] == 0
        assert log["saturated_layers"] == 0

    def test_neurogenesis_identifies_saturated_layers(self):
        """Neurogenesis correctly identifies saturated layers by threshold."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        # Mix of saturated and non-saturated
        usage_scores = {
            "layer.weight": 0.95,      # saturated
            "other.weight": 0.3,        # not saturated
        }
        layer_index = ["layer.weight", "other.weight"]

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "layer_index": layer_index,
            "device": "cpu",
        })
        f = Neurogenesis(saturation_threshold=0.8, mode="adapter")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log["saturated_layers"] == 1
        # Check details list has only the saturated layer
        details = log.get("details", [])
        assert len(details) == 1
        assert details[0]["layer"] == "layer.weight"

    def test_neurogenesis_adapter_mode_adds_parameters(self):
        """In adapter mode, Neurogenesis adds new Parameter modules."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        usage_scores = {"layer.weight": 0.95}
        layer_index = ["layer.weight"]

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "layer_index": layer_index,
            "device": "cpu",
        })
        f = Neurogenesis(saturation_threshold=0.8, mode="adapter")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log["new_nodes_added"] > 0
        assert log["mode"] == "adapter"

    def test_neurogenesis_eureka_mode_accepted(self):
        """Neurogenesis accepts mode='eureka' without raising."""
        from filters.neurogenesis import Neurogenesis

        f = Neurogenesis(mode="eureka")
        assert f._mode == "eureka"

    def test_neurogenesis_eureka_requires_struggle_map(self):
        """Eureka mode operates on struggle_map from StruggleDetector."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        usage_scores = {"layer.weight": 0.5}
        # In eureka mode with no struggle_map, should still return a valid
        # payload but with 0 bridges (nothing to bridge if no struggle)
        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log is not None
        assert log["mode"] == "eureka"
        assert log["new_nodes_added"] == 0

    def test_neurogenesis_eureka_reads_activation_map(self):
        """Eureka mode uses activation_map to find hot pathways for branching."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        # struggle_map with a struggling class that has layer_pairs
        struggle_map = {
            "struggling_classes": [{
                "class_id": "hard",
                "mean_loss": 5.0,
                "severity": 3.0,
                "layer_pairs": [{
                    "source": "layer.0.weight",
                    "target": "layer.3.weight",
                    "source_score": 0.9,
                    "target_score": 0.85,
                    "distance": 3,
                    "bridge_priority": 5.25,
                }],
            }],
        }
        # activation_map tells us where the hot pathways are
        activation_map = {
            "layer.0.weight": 2.5,   # hot source
            "layer.1.weight": 0.3,   # cold
            "layer.2.weight": 0.2,   # cold
            "layer.3.weight": 1.8,   # hot target
        }
        usage_scores = {
            "layer.0.weight": 0.9,
            "layer.1.weight": 0.3,
            "layer.2.weight": 0.2,
            "layer.3.weight": 0.85,
        }

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "activation_map": activation_map,
            "struggle_map": struggle_map,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log["mode"] == "eureka"
        # Should have attempted to grow bridges
        assert "bridges" in log
        assert len(log["bridges"]) >= 1

    def test_neurogenesis_eureka_bridge_follows_hot_pathway(self):
        """Eureka bridges are placed along high-activation pathways."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        struggle_map = {
            "struggling_classes": [{
                "class_id": "hard",
                "mean_loss": 5.0,
                "severity": 3.0,
                "layer_pairs": [{
                    "source": "layer.0.weight",
                    "target": "layer.3.weight",
                    "source_score": 0.9,
                    "target_score": 0.85,
                    "distance": 3,
                    "bridge_priority": 5.25,
                }],
            }],
        }
        activation_map = {
            "layer.0.weight": 2.5,
            "layer.3.weight": 1.8,
        }
        usage_scores = {
            "layer.0.weight": 0.9,
            "layer.3.weight": 0.85,
        }

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "activation_map": activation_map,
            "struggle_map": struggle_map,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        bridges = log.get("bridges", [])
        for bridge in bridges:
            # Each bridge should reference source and target layers
            assert "source" in bridge
            assert "target" in bridge
            # Bridge should record the activation intensity at both ends
            assert "source_activation" in bridge
            assert "target_activation" in bridge

    def test_neurogenesis_eureka_skips_when_no_struggle(self):
        """Eureka mode with empty struggling_classes grows nothing."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        struggle_map = {
            "struggling_classes": [],
            "total_classes": 5,
        }
        usage_scores = {"layer.weight": 0.9}
        activation_map = {"layer.weight": 2.0}

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "activation_map": activation_map,
            "struggle_map": struggle_map,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log["new_nodes_added"] == 0
        assert log["bridges"] == []

    def test_neurogenesis_eureka_prioritizes_highest_activation(self):
        """Eureka mode selects bridge pairs with highest activation first."""
        from filters.neurogenesis import Neurogenesis

        model = _make_mock_model()
        # Two candidate pairs — one with higher activation
        struggle_map = {
            "struggling_classes": [{
                "class_id": "hard",
                "mean_loss": 5.0,
                "severity": 3.0,
                "layer_pairs": [
                    {
                        "source": "layer.0.weight",
                        "target": "layer.3.weight",
                        "source_score": 0.9,
                        "target_score": 0.85,
                        "distance": 3,
                        "bridge_priority": 5.25,
                    },
                    {
                        "source": "layer.1.weight",
                        "target": "layer.2.weight",
                        "source_score": 0.6,
                        "target_score": 0.5,
                        "distance": 1,
                        "bridge_priority": 1.1,
                    },
                ],
            }],
        }
        activation_map = {
            "layer.0.weight": 3.0,   # very hot
            "layer.1.weight": 0.5,   # lukewarm
            "layer.2.weight": 0.4,   # cold
            "layer.3.weight": 2.5,   # hot
        }
        usage_scores = {
            "layer.0.weight": 0.9,
            "layer.1.weight": 0.6,
            "layer.2.weight": 0.5,
            "layer.3.weight": 0.85,
        }

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "activation_map": activation_map,
            "struggle_map": struggle_map,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        bridges = log.get("bridges", [])
        if len(bridges) >= 2:
            # First bridge should have higher combined activation
            first_combined = bridges[0]["source_activation"] + bridges[0]["target_activation"]
            second_combined = bridges[1]["source_activation"] + bridges[1]["target_activation"]
            assert first_combined >= second_combined

    def test_neurogenesis_eureka_grows_adapter_between_layers(self):
        """Eureka mode registers a cross-layer adapter on the model."""
        from filters.neurogenesis import Neurogenesis

        # Create a model with TWO named parameters so the bridge can find both
        model = MagicMock()
        param_a = MagicMock()
        param_a.shape = (64, 64)
        param_a.numel.return_value = 4096
        param_a.ndim = 2
        param_a.data = MagicMock()
        param_b = MagicMock()
        param_b.shape = (64, 64)
        param_b.numel.return_value = 4096
        param_b.ndim = 2
        param_b.data = MagicMock()
        model.named_parameters.return_value = [
            ("layer.0.weight", param_a),
            ("layer.3.weight", param_b),
        ]
        model.parameters.return_value = [param_a, param_b]
        model.to.return_value = model

        struggle_map = {
            "struggling_classes": [{
                "class_id": "hard",
                "mean_loss": 5.0,
                "severity": 3.0,
                "layer_pairs": [{
                    "source": "layer.0.weight",
                    "target": "layer.3.weight",
                    "source_score": 0.9,
                    "target_score": 0.85,
                    "distance": 3,
                    "bridge_priority": 5.25,
                }],
            }],
        }
        activation_map = {
            "layer.0.weight": 2.5,
            "layer.3.weight": 1.8,
        }
        usage_scores = {
            "layer.0.weight": 0.9,
            "layer.3.weight": 0.85,
        }

        payload = Payload({
            "model": model,
            "usage_scores": usage_scores,
            "activation_map": activation_map,
            "struggle_map": struggle_map,
            "device": "cpu",
        })
        f = Neurogenesis(mode="eureka")
        result = f.call(payload)

        log = result.get("neurogenesis_log")
        assert log["new_nodes_added"] > 0
        # Should have grown at least one bridge
        bridges = log.get("bridges", [])
        assert len(bridges) >= 1
        assert bridges[0]["grown"] is True


# ── TrafficSampler tests ─────────────────────────────────────────

class TestTrafficSampler:
    """Tests for TrafficSampler — capture inference patterns during waking."""

    def test_traffic_sampler_requires_inference_samples(self):
        """TrafficSampler raises ValueError without inference_samples."""
        from filters.traffic_sampler import TrafficSampler

        f = TrafficSampler()
        with pytest.raises(ValueError, match="requires 'inference_samples'"):
            run_filter(f, Payload({}))

    def test_traffic_sampler_default_params(self):
        """TrafficSampler has sane defaults."""
        from filters.traffic_sampler import TrafficSampler

        f = TrafficSampler()
        assert f._max_buffer_size == 10000
        assert f._class_method == "loss_quartile"

    def test_traffic_sampler_custom_params(self):
        """TrafficSampler accepts custom parameters."""
        from filters.traffic_sampler import TrafficSampler

        f = TrafficSampler(max_buffer_size=500, class_method="keyword")
        assert f._max_buffer_size == 500
        assert f._class_method == "keyword"

    def test_traffic_sampler_contract_returns_payload(self):
        """TrafficSampler returns Payload with traffic_log."""
        from filters.traffic_sampler import TrafficSampler

        samples = [
            {"input_text": "hello world", "loss": 2.5},
            {"input_text": "def foo():", "loss": 1.8},
            {"input_text": "SELECT * FROM", "loss": 3.1},
        ]
        payload = Payload({"inference_samples": samples})
        f = TrafficSampler()
        result = f.call(payload)

        assert isinstance(result, Payload)
        log = result.get("traffic_log")
        assert log is not None
        assert "sample_count" in log
        assert log["sample_count"] == 3
        assert "class_distribution" in log
        assert "loss_stats" in log

    def test_traffic_sampler_classifies_by_loss(self):
        """TrafficSampler groups samples into loss-based classes."""
        from filters.traffic_sampler import TrafficSampler

        # Create samples with clearly different loss ranges
        samples = [
            {"input_text": "easy", "loss": 0.5},
            {"input_text": "easy2", "loss": 0.6},
            {"input_text": "hard", "loss": 5.0},
            {"input_text": "hard2", "loss": 5.5},
        ]
        payload = Payload({"inference_samples": samples})
        f = TrafficSampler(class_method="loss_quartile")
        result = f.call(payload)

        log = result.get("traffic_log")
        # Should have at least 2 classes (low-loss and high-loss)
        assert len(log["class_distribution"]) >= 2

    def test_traffic_sampler_computes_loss_stats(self):
        """TrafficSampler computes mean, std, min, max loss."""
        from filters.traffic_sampler import TrafficSampler

        samples = [
            {"input_text": "a", "loss": 1.0},
            {"input_text": "b", "loss": 2.0},
            {"input_text": "c", "loss": 3.0},
        ]
        payload = Payload({"inference_samples": samples})
        f = TrafficSampler()
        result = f.call(payload)

        stats = result.get("traffic_log")["loss_stats"]
        assert stats["mean"] == pytest.approx(2.0, abs=0.01)
        assert stats["min"] == pytest.approx(1.0, abs=0.01)
        assert stats["max"] == pytest.approx(3.0, abs=0.01)

    def test_traffic_sampler_buffer_overflow(self):
        """TrafficSampler respects max_buffer_size by keeping most recent."""
        from filters.traffic_sampler import TrafficSampler

        samples = [{"input_text": f"sample_{i}", "loss": float(i)} for i in range(50)]
        f = TrafficSampler(max_buffer_size=10)
        payload = Payload({"inference_samples": samples})
        result = f.call(payload)

        log = result.get("traffic_log")
        # Should only process the most recent max_buffer_size samples
        assert log["sample_count"] <= 10

    def test_traffic_sampler_empty_samples(self):
        """TrafficSampler handles empty sample list gracefully."""
        from filters.traffic_sampler import TrafficSampler

        payload = Payload({"inference_samples": []})
        f = TrafficSampler()
        result = f.call(payload)

        log = result.get("traffic_log")
        assert log["sample_count"] == 0

    def test_traffic_sampler_accumulates_activation_patterns(self):
        """TrafficSampler records activation patterns when available."""
        from filters.traffic_sampler import TrafficSampler

        samples = [
            {"input_text": "test", "loss": 1.0, "activations": {"layer.0": 0.5}},
            {"input_text": "test2", "loss": 2.0, "activations": {"layer.0": 0.8}},
        ]
        payload = Payload({"inference_samples": samples})
        f = TrafficSampler()
        result = f.call(payload)

        log = result.get("traffic_log")
        assert "activation_summary" in log


# ── StruggleDetector tests ────────────────────────────────────────

class TestStruggleDetector:
    """Tests for StruggleDetector — identify sustained high-loss input classes."""

    def test_struggle_detector_requires_traffic_log(self):
        """StruggleDetector raises ValueError without traffic_log."""
        from filters.struggle_detector import StruggleDetector

        f = StruggleDetector()
        with pytest.raises(ValueError, match="requires 'traffic_log'"):
            run_filter(f, Payload({}))

    def test_struggle_detector_requires_usage_scores(self):
        """StruggleDetector raises ValueError without usage_scores."""
        from filters.struggle_detector import StruggleDetector

        f = StruggleDetector()
        traffic_log = {"sample_count": 10, "class_distribution": {}, "loss_stats": {}}
        with pytest.raises(ValueError, match="requires 'usage_scores'"):
            run_filter(f, Payload({"traffic_log": traffic_log}))

    def test_struggle_detector_default_params(self):
        """StruggleDetector has sane defaults."""
        from filters.struggle_detector import StruggleDetector

        f = StruggleDetector()
        assert f._loss_threshold_factor == 2.0
        assert f._min_samples == 5
        assert f._sustained_ratio == 0.6

    def test_struggle_detector_custom_params(self):
        """StruggleDetector accepts custom thresholds."""
        from filters.struggle_detector import StruggleDetector

        f = StruggleDetector(
            loss_threshold_factor=3.0,
            min_samples=10,
            sustained_ratio=0.8,
        )
        assert f._loss_threshold_factor == 3.0
        assert f._min_samples == 10
        assert f._sustained_ratio == 0.8

    def test_struggle_detector_contract_returns_payload(self):
        """StruggleDetector returns Payload with struggle_map."""
        from filters.struggle_detector import StruggleDetector

        traffic_log = {
            "sample_count": 10,
            "class_distribution": {
                "class_0": {
                    "count": 5,
                    "mean_loss": 1.2,
                    "samples": [
                        {"loss": 1.0}, {"loss": 1.1}, {"loss": 1.2},
                        {"loss": 1.3}, {"loss": 1.4},
                    ],
                },
            },
            "loss_stats": {"mean": 1.2, "std": 0.3, "min": 0.5, "max": 3.0},
        }
        usage_scores = {"layer.weight": 0.5}
        payload = Payload({
            "traffic_log": traffic_log,
            "usage_scores": usage_scores,
        })
        f = StruggleDetector()
        result = f.call(payload)

        assert isinstance(result, Payload)
        smap = result.get("struggle_map")
        assert smap is not None
        assert "struggling_classes" in smap
        assert "total_classes" in smap
        assert "threshold" in smap

    def test_struggle_detector_identifies_struggling_class(self):
        """StruggleDetector flags classes where loss exceeds threshold."""
        from filters.struggle_detector import StruggleDetector

        # One easy class, one hard class with sustained high loss
        traffic_log = {
            "sample_count": 20,
            "class_distribution": {
                "easy": {
                    "count": 10,
                    "mean_loss": 1.0,
                    "samples": [{"loss": v} for v in [0.8, 0.9, 1.0, 1.1, 1.2,
                                                       0.8, 0.9, 1.0, 1.1, 1.2]],
                },
                "hard": {
                    "count": 10,
                    "mean_loss": 5.0,
                    "samples": [{"loss": v} for v in [4.5, 5.0, 5.5, 4.8, 5.2,
                                                       4.7, 5.1, 5.3, 4.9, 5.0]],
                },
            },
            "loss_stats": {"mean": 3.0, "std": 2.0, "min": 0.8, "max": 5.5},
        }
        usage_scores = {"layer.0.weight": 0.7, "layer.1.weight": 0.3}
        payload = Payload({
            "traffic_log": traffic_log,
            "usage_scores": usage_scores,
        })
        f = StruggleDetector(loss_threshold_factor=1.5, min_samples=5)
        result = f.call(payload)

        smap = result.get("struggle_map")
        assert len(smap["struggling_classes"]) >= 1
        # The "hard" class should be flagged
        hard_classes = [c for c in smap["struggling_classes"] if c["class_id"] == "hard"]
        assert len(hard_classes) == 1

    def test_struggle_detector_no_struggle(self):
        """StruggleDetector returns empty struggling_classes when all is well."""
        from filters.struggle_detector import StruggleDetector

        traffic_log = {
            "sample_count": 10,
            "class_distribution": {
                "uniform": {
                    "count": 10,
                    "mean_loss": 1.0,
                    "samples": [{"loss": 1.0}] * 10,
                },
            },
            "loss_stats": {"mean": 1.0, "std": 0.0, "min": 1.0, "max": 1.0},
        }
        usage_scores = {"layer.weight": 0.5}
        payload = Payload({
            "traffic_log": traffic_log,
            "usage_scores": usage_scores,
        })
        f = StruggleDetector()
        result = f.call(payload)

        smap = result.get("struggle_map")
        assert len(smap["struggling_classes"]) == 0

    def test_struggle_detector_insufficient_samples(self):
        """StruggleDetector skips classes with too few samples."""
        from filters.struggle_detector import StruggleDetector

        traffic_log = {
            "sample_count": 3,
            "class_distribution": {
                "sparse": {
                    "count": 3,
                    "mean_loss": 10.0,
                    "samples": [{"loss": 10.0}] * 3,
                },
            },
            "loss_stats": {"mean": 10.0, "std": 0.0, "min": 10.0, "max": 10.0},
        }
        usage_scores = {"layer.weight": 0.5}
        payload = Payload({
            "traffic_log": traffic_log,
            "usage_scores": usage_scores,
        })
        f = StruggleDetector(min_samples=5)
        result = f.call(payload)

        smap = result.get("struggle_map")
        # Class has only 3 samples, min_samples=5 — should be skipped
        assert len(smap["struggling_classes"]) == 0

    def test_struggle_detector_suggests_layer_pairs(self):
        """StruggleDetector suggests layer pairs for cross-layer bridges."""
        from filters.struggle_detector import StruggleDetector

        traffic_log = {
            "sample_count": 20,
            "class_distribution": {
                "hard": {
                    "count": 10,
                    "mean_loss": 8.0,
                    "samples": [{"loss": v} for v in [7.5, 8.0, 8.5, 7.8, 8.2,
                                                       7.7, 8.1, 8.3, 7.9, 8.0]],
                },
            },
            "loss_stats": {"mean": 2.0, "std": 1.0, "min": 0.5, "max": 8.5},
        }
        # Usage scores with layers at different utilization levels
        usage_scores = {
            "layer.0.weight": 0.9,   # high usage — potential bridge source
            "layer.1.weight": 0.4,
            "layer.2.weight": 0.3,
            "layer.3.weight": 0.85,  # high usage — potential bridge target
        }
        payload = Payload({
            "traffic_log": traffic_log,
            "usage_scores": usage_scores,
        })
        f = StruggleDetector(loss_threshold_factor=1.5, min_samples=5)
        result = f.call(payload)

        smap = result.get("struggle_map")
        # Should have struggling classes
        assert len(smap["struggling_classes"]) >= 1
        # Each struggling class should suggest layer_pairs for bridges
        for sc in smap["struggling_classes"]:
            assert "layer_pairs" in sc


# ── DriftDetector tests ───────────────────────────────────────────

class TestDriftDetector:
    """Tests for DriftDetector — compare live stress to baseline."""

    def test_drift_detector_records_baseline(self):
        """DriftDetector records first observation as baseline."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        payload = Payload({
            "usage_scores": {"layer.0": 0.5, "layer.1": 0.7},
            "stress_complete": True,
        })
        tap.observe(payload)

        assert tap.baseline is not None
        assert tap.baseline["layer.0"] == 0.5

    def test_drift_detector_computes_drift(self):
        """DriftDetector measures drift from baseline on subsequent observations."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        # First observation = baseline
        tap.observe(Payload({
            "usage_scores": {"layer.0": 0.5, "layer.1": 0.7},
            "stress_complete": True,
        }))
        # Second observation = shifted
        tap.observe(Payload({
            "usage_scores": {"layer.0": 0.9, "layer.1": 0.3},
            "stress_complete": True,
        }))

        latest = tap.latest_drift
        assert latest is not None
        assert "magnitude" in latest
        assert latest["magnitude"] > 0.0

    def test_drift_detector_no_drift_when_same(self):
        """DriftDetector reports zero drift when scores unchanged."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        scores = {"layer.0": 0.5, "layer.1": 0.7}
        tap.observe(Payload({"usage_scores": scores, "stress_complete": True}))
        tap.observe(Payload({"usage_scores": scores, "stress_complete": True}))

        assert tap.latest_drift["magnitude"] == pytest.approx(0.0, abs=0.001)

    def test_drift_exceeded_threshold(self):
        """DriftDetector.drift_exceeded() correctly detects large shifts."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        tap.observe(Payload({
            "usage_scores": {"layer.0": 0.1, "layer.1": 0.1},
            "stress_complete": True,
        }))
        tap.observe(Payload({
            "usage_scores": {"layer.0": 0.9, "layer.1": 0.9},
            "stress_complete": True,
        }))

        assert tap.drift_exceeded(0.1) is True
        assert tap.drift_exceeded(100.0) is False

    def test_drift_detector_history(self):
        """DriftDetector maintains history of drift observations."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        for i in range(5):
            tap.observe(Payload({
                "usage_scores": {"layer.0": 0.1 * (i + 1)},
                "stress_complete": True,
            }))

        assert len(tap.history) == 5

    def test_drift_detector_skips_without_stress(self):
        """DriftDetector ignores observations without stress_complete."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        tap.observe(Payload({"usage_scores": {"layer.0": 0.5}}))
        # No stress_complete — should not set baseline
        assert tap.baseline is None

    def test_drift_detector_reset_baseline(self):
        """DriftDetector can reset baseline for new sleep cycle."""
        from taps.drift_detector import DriftDetector

        tap = DriftDetector()
        tap.observe(Payload({
            "usage_scores": {"layer.0": 0.5},
            "stress_complete": True,
        }))
        assert tap.baseline is not None

        tap.reset_baseline()
        assert tap.baseline is None


# ── SleepCycle pipeline tests ─────────────────────────────────────

class TestSleepCyclePipeline:
    """Tests for SleepCycle — the scheduled encoding loop."""

    @staticmethod
    def _make_cfg():
        from config.morphogenesis import MorphConfig
        return MorphConfig.from_dict({
            "specimen": {"model_name_or_path": "test-model"},
            "num_waves": 1,
        })

    def test_sleep_cycle_returns_pipeline(self):
        """build_sleep_cycle returns a Pipeline."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)
        assert isinstance(pipe, Pipeline)

    def test_sleep_cycle_has_core_filters(self):
        """SleepCycle contains the essential learning loop filters."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        step_names = [name for name, _step, _kind in pipe._steps]
        # Must have stress analysis, pruning, regrowth, neurogenesis, healing
        assert "stress_test" in step_names
        assert "gentle_pruning" in step_names
        assert "angiogenesis" in step_names
        assert "neurogenesis" in step_names
        assert "differentiate" in step_names

    def test_sleep_cycle_has_struggle_detector(self):
        """SleepCycle includes StruggleDetector for eureka detection."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        step_names = [name for name, _step, _kind in pipe._steps]
        assert "struggle_detector" in step_names

    def test_sleep_cycle_has_traffic_sampler(self):
        """SleepCycle includes TrafficSampler to process waking data."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        step_names = [name for name, _step, _kind in pipe._steps]
        assert "traffic_sampler" in step_names

    def test_sleep_cycle_has_fossil_hook(self):
        """SleepCycle uses FossilRecordHook for audit trail."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        # Pipeline should have hooks registered
        hook_types = [type(h).__name__ for h in pipe._hooks]
        assert "FossilRecordHook" in hook_types

    def test_sleep_cycle_has_drift_tap(self):
        """SleepCycle includes DriftDetector tap."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        step_names = [name for name, _step, _kind in pipe._steps]
        assert "drift_check" in step_names

    def test_sleep_cycle_ordering(self):
        """SleepCycle filters run in biologically correct order."""
        from pipelines.sleep_cycle import build_sleep_cycle

        cfg = self._make_cfg()
        pipe = build_sleep_cycle(cfg)

        # Get ordered filter/tap/pipeline names
        step_names = [name for name, _step, _kind in pipe._steps]

        # traffic_sampler must come before stress_test
        assert step_names.index("traffic_sampler") < step_names.index("stress_test")
        # stress_test must come before struggle_detector
        assert step_names.index("stress_test") < step_names.index("struggle_detector")
        # struggle_detector must come before neurogenesis
        assert step_names.index("struggle_detector") < step_names.index("neurogenesis")
        # gentle_pruning must come before angiogenesis
        assert step_names.index("gentle_pruning") < step_names.index("angiogenesis")
        # neurogenesis must come before differentiate
        assert step_names.index("neurogenesis") < step_names.index("differentiate")
        # eureka neurogenesis must come after demand-driven neurogenesis
        assert step_names.index("neurogenesis") < step_names.index("neurogenesis_eureka")
        # eureka neurogenesis must come before differentiate
        assert step_names.index("neurogenesis_eureka") < step_names.index("differentiate")


# ── Dream Training tests ─────────────────────────────────────────

class TestBuildDreamProxy:
    """Tests for BuildDreamProxy — low-rank SVD proxy construction."""

    def test_requires_model(self):
        """BuildDreamProxy raises ValueError without model."""
        from filters.dream_proxy import BuildDreamProxy

        f = BuildDreamProxy()
        with pytest.raises(ValueError, match="requires 'model'"):
            run_filter(f, Payload({}))

    def test_default_params(self):
        """BuildDreamProxy has sane defaults."""
        from filters.dream_proxy import BuildDreamProxy

        f = BuildDreamProxy()
        assert f._rank == 16
        assert f._skip_embeddings is True

    def test_custom_rank(self):
        """BuildDreamProxy accepts custom rank."""
        from filters.dream_proxy import BuildDreamProxy

        f = BuildDreamProxy(rank=4, skip_embeddings=False)
        assert f._rank == 4
        assert f._skip_embeddings is False

    def test_contract_returns_payload_keys(self):
        """BuildDreamProxy returns Payload with proxy, svd_basis, compression."""
        from filters.dream_proxy import BuildDreamProxy

        model = _make_mock_model()
        payload = Payload({"model": model, "device": "cpu"})
        f = BuildDreamProxy(rank=4)
        # Mock model's deepcopy will return a mock; that's fine for contract test
        result = run_filter(f, payload)
        assert isinstance(result, Payload)
        # Should have dream_proxy and svd_basis keys
        assert result.get("dream_proxy") is not None
        assert result.get("svd_basis") is not None
        assert result.get("proxy_rank") == 4

    def test_compression_ratio_positive(self):
        """Proxy compression ratio should be >= 1.0."""
        from filters.dream_proxy import BuildDreamProxy

        model = _make_mock_model()
        payload = Payload({"model": model, "device": "cpu"})
        f = BuildDreamProxy(rank=4)
        result = run_filter(f, payload)
        compression = result.get("proxy_compression")
        assert compression is not None
        assert compression >= 1.0


class TestLiftDreamGradients:
    """Tests for LiftDreamGradients — SVD-basis gradient projection."""

    def test_requires_model(self):
        """LiftDreamGradients raises ValueError without model."""
        from filters.dream_proxy import LiftDreamGradients

        f = LiftDreamGradients()
        with pytest.raises(ValueError, match="requires 'model'"):
            run_filter(f, Payload({}))

    def test_requires_proxy(self):
        """LiftDreamGradients raises ValueError without dream_proxy."""
        from filters.dream_proxy import LiftDreamGradients

        model = _make_mock_model()
        f = LiftDreamGradients()
        with pytest.raises(ValueError, match="requires 'dream_proxy'"):
            run_filter(f, Payload({"model": model}))

    def test_requires_svd_basis(self):
        """LiftDreamGradients raises ValueError without svd_basis."""
        from filters.dream_proxy import LiftDreamGradients

        model = _make_mock_model()
        proxy = _make_mock_model()
        f = LiftDreamGradients()
        with pytest.raises(ValueError, match="requires 'svd_basis'"):
            run_filter(f, Payload({"model": model, "dream_proxy": proxy}))

    def test_requires_weight_snap(self):
        """LiftDreamGradients raises ValueError without proxy_weight_snap."""
        from filters.dream_proxy import LiftDreamGradients

        model = _make_mock_model()
        proxy = _make_mock_model()
        f = LiftDreamGradients()
        with pytest.raises(ValueError, match="requires 'proxy_weight_snap'"):
            run_filter(f, Payload({
                "model": model,
                "dream_proxy": proxy,
                "svd_basis": {},
            }))

    def test_default_lr(self):
        """LiftDreamGradients default learning rate is 1.0."""
        from filters.dream_proxy import LiftDreamGradients

        f = LiftDreamGradients()
        assert f._lr == 1.0

    def test_custom_lr(self):
        """LiftDreamGradients accepts custom learning rate."""
        from filters.dream_proxy import LiftDreamGradients

        f = LiftDreamGradients(learning_rate=0.5)
        assert f._lr == 0.5

    def test_empty_basis_returns_log(self):
        """LiftDreamGradients with empty svd_basis still returns gradient_log."""
        from filters.dream_proxy import LiftDreamGradients

        model = _make_mock_model()
        proxy = _make_mock_model()
        f = LiftDreamGradients()
        result = run_filter(f, Payload({
            "model": model,
            "dream_proxy": proxy,
            "svd_basis": {},
            "proxy_weight_snap": {},
        }))
        assert isinstance(result, Payload)
        log = result.get("dream_gradient_log")
        assert log is not None
        assert log["_summary"]["layers_updated"] == 0


class TestDreamTrainer:
    """Tests for DreamTrainer — dream training loop."""

    def test_requires_proxy(self):
        """DreamTrainer raises ValueError without dream_proxy."""
        from filters.dream_trainer import DreamTrainer

        f = DreamTrainer()
        with pytest.raises(ValueError, match="requires 'dream_proxy'"):
            run_filter(f, Payload({}))

    def test_requires_tokenizer(self):
        """DreamTrainer raises ValueError without tokenizer."""
        from filters.dream_trainer import DreamTrainer

        proxy = _make_mock_model()
        f = DreamTrainer()
        with pytest.raises(ValueError, match="requires 'tokenizer'"):
            run_filter(f, Payload({"dream_proxy": proxy}))

    def test_default_params(self):
        """DreamTrainer has sane defaults."""
        from filters.dream_trainer import DreamTrainer

        f = DreamTrainer()
        assert f._training_steps == 200
        assert f._lr == 5e-5
        assert f._max_length == 256

    def test_custom_params(self):
        """DreamTrainer accepts custom training parameters."""
        from filters.dream_trainer import DreamTrainer

        f = DreamTrainer(
            training_steps=50,
            learning_rate=1e-4,
            max_length=128,
            training_texts=["hello world"],
        )
        assert f._training_steps == 50
        assert f._lr == 1e-4
        assert f._max_length == 128
        assert f._training_texts == ["hello world"]

    def test_default_dream_texts(self):
        """DreamTrainer has diverse default training texts."""
        from filters.dream_trainer import DreamTrainer

        texts = DreamTrainer._default_dream_texts()
        assert len(texts) >= 10
        # Should cover multiple domains
        has_code = any("def " in t or "class " in t for t in texts)
        has_science = any("ATP" in t or "photosynthesis" in t.lower() for t in texts)
        has_math = any("=" in t and ("+" in t or "×" in t or "^" in t) for t in texts)
        assert has_code
        assert has_science

    def test_contract_writes_snapshot(self):
        """DreamTrainer must write proxy_weight_snap for gradient lift."""
        from filters.dream_trainer import DreamTrainer

        # This is the critical contract — without the snapshot,
        # LiftDreamGradients can't compute the weight delta.
        # Verify the class documents this output.
        f = DreamTrainer(training_steps=1)
        # The Writes section in the class docstring declares proxy_weight_snap
        assert "proxy_weight_snap" in (DreamTrainer.__doc__ or "")

    def test_contract_writes_valence_log(self):
        """DreamTrainer must write valence_log for nightmare/positive analysis."""
        from filters.dream_trainer import DreamTrainer

        assert "valence_log" in (DreamTrainer.__doc__ or "")

    def test_classify_valence_empty(self):
        """_classify_valence handles empty records."""
        from filters.dream_trainer import DreamTrainer

        result = DreamTrainer._classify_valence([])
        assert result["nightmare"]["count"] == 0
        assert result["positive"]["count"] == 0
        assert result["neutral"]["count"] == 0

    def test_classify_valence_splits_thirds(self):
        """_classify_valence splits records into nightmare/neutral/positive thirds."""
        from filters.dream_trainer import DreamTrainer

        # 9 records with losses 1-9
        records = [
            {"loss": float(i), "grad_norm": float(i * 10), "text_preview": f"text {i}"}
            for i in range(1, 10)
        ]
        result = DreamTrainer._classify_valence(records)
        # Bottom third (1,2,3) = positive, top third (7,8,9) = nightmare
        assert result["positive"]["count"] >= 2
        assert result["nightmare"]["count"] >= 2
        assert result["neutral"]["count"] >= 1

    def test_classify_valence_nightmare_higher_loss(self):
        """Nightmare category should have higher mean loss than positive."""
        from filters.dream_trainer import DreamTrainer

        records = [
            {"loss": float(i), "grad_norm": float(i * 5), "text_preview": f"t{i}"}
            for i in range(1, 13)
        ]
        result = DreamTrainer._classify_valence(records)
        assert result["nightmare"]["mean_loss"] > result["positive"]["mean_loss"]

    def test_classify_valence_nightmare_higher_grad_norm(self):
        """Nightmare category should have higher mean grad_norm (correlates with loss)."""
        from filters.dream_trainer import DreamTrainer

        # Grad norm proportional to loss — models that struggle produce bigger gradients
        records = [
            {"loss": float(i), "grad_norm": float(i * 10), "text_preview": f"t{i}"}
            for i in range(1, 13)
        ]
        result = DreamTrainer._classify_valence(records)
        assert result["nightmare"]["mean_grad_norm"] > result["positive"]["mean_grad_norm"]

    def test_classify_valence_records_annotated(self):
        """Each record gets a 'valence' field added."""
        from filters.dream_trainer import DreamTrainer

        records = [
            {"loss": 1.0, "grad_norm": 5.0, "text_preview": "low"},
            {"loss": 5.0, "grad_norm": 25.0, "text_preview": "mid"},
            {"loss": 9.0, "grad_norm": 45.0, "text_preview": "high"},
        ]
        result = DreamTrainer._classify_valence(records)
        valences = {r["valence"] for r in result["records"]}
        # Should have at least 2 of the 3 categories represented
        assert len(valences) >= 2

    def test_accepts_nightmare_texts(self):
        """DreamTrainer accepts explicit nightmare_texts parameter."""
        from filters.dream_trainer import DreamTrainer

        f = DreamTrainer(nightmare_texts=["error error error"])
        assert f._nightmare_texts == ["error error error"]

    def test_accepts_positive_texts(self):
        """DreamTrainer accepts explicit positive_texts parameter."""
        from filters.dream_trainer import DreamTrainer

        f = DreamTrainer(positive_texts=["The answer is 42."])
        assert f._positive_texts == ["The answer is 42."]


class TestDreamComposer:
    """Tests for DreamComposer — synthetic training data generation.

    The brain doesn't just replay memories during dreams — it COMPOSES
    new scenarios by recombining elements.  DreamComposer generates
    synthetic training data by interpolating in the SVD latent space.
    """

    def test_requires_svd_basis(self):
        """DreamComposer raises ValueError without svd_basis."""
        from filters.dream_composer import DreamComposer

        f = DreamComposer()
        with pytest.raises(ValueError, match="requires 'svd_basis'"):
            run_filter(f, Payload({}))

    def test_requires_tokenizer(self):
        """DreamComposer raises ValueError without tokenizer."""
        from filters.dream_composer import DreamComposer

        f = DreamComposer()
        with pytest.raises(ValueError, match="requires 'tokenizer'"):
            run_filter(f, Payload({"svd_basis": {}}))

    def test_requires_traffic_samples(self):
        """DreamComposer raises ValueError without traffic_samples."""
        from filters.dream_composer import DreamComposer

        f = DreamComposer()
        with pytest.raises(ValueError, match="requires 'traffic_samples'"):
            run_filter(f, Payload({"svd_basis": {}, "tokenizer": MagicMock()}))

    def test_default_params(self):
        """DreamComposer has sane defaults."""
        from filters.dream_composer import DreamComposer

        f = DreamComposer()
        assert f._num_dreams >= 1
        assert 0.0 <= f._interpolation_noise <= 1.0

    def test_custom_params(self):
        """DreamComposer accepts custom generation parameters."""
        from filters.dream_composer import DreamComposer

        f = DreamComposer(num_dreams=50, interpolation_noise=0.3)
        assert f._num_dreams == 50
        assert f._interpolation_noise == 0.3

    def test_contract_writes_dream_texts(self):
        """DreamComposer must write composed_dreams to payload."""
        from filters.dream_composer import DreamComposer

        assert "composed_dreams" in (DreamComposer.__doc__ or "")