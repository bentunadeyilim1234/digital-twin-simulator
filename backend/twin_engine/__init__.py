"""School Safety & Resilience Digital Twin — deterministic institutional simulation engine.

The unit of analysis is the school as an institution. The engine contains no
individual-level inputs or outputs and produces no risk, dangerousness or attack
probabilities. Outputs are institutional readiness and process-performance indicators.
"""

from .config import ENGINE_VERSION, config_hash, default_config, templates, validate_config
from .model import compile_model, linear_stability
from .simulator import simulate

__all__ = ["ENGINE_VERSION", "config_hash", "default_config", "templates", "validate_config",
           "compile_model", "linear_stability", "simulate"]
