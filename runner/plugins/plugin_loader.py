"""
Custom metric plugin loader.

Users can define custom metrics as Python classes and reference them in rageval.yaml:

    plugins:
      - module: my_app.custom_metrics
        class: DrugDosageHallucinationMetric

Each plugin class must implement:
    def evaluate(self, output: str, tool_calls: list, rule: dict) -> tuple[bool, str]:
        ...  # Returns (passed, reason)
"""
import importlib


def load_plugin_class(dotted_path: str):
    """
    Load a class from a dotted module path.

    Args:
        dotted_path: e.g. "my_app.custom_metrics.DrugDosageHallucinationMetric"

    Returns:
        The class object.
    """
    parts = dotted_path.rsplit(".", 1)
    if len(parts) != 2:
        raise ValueError(
            f"Invalid plugin class path: {dotted_path!r}. "
            "Must be 'module.path.ClassName'."
        )
    module_path, class_name = parts
    module = importlib.import_module(module_path)
    cls = getattr(module, class_name, None)
    if cls is None:
        raise AttributeError(f"Class {class_name!r} not found in module {module_path!r}")
    return cls


def load_plugins_from_config(plugin_configs: list[dict]) -> list:
    """
    Load all plugin instances from the rageval.yaml plugins list.

    Args:
        plugin_configs: [{"module": "...", "class": "..."}]

    Returns:
        List of instantiated plugin objects.
    """
    plugins = []
    for cfg in plugin_configs:
        module_path = cfg.get("module", "")
        class_name = cfg.get("class", "")
        dotted_path = f"{module_path}.{class_name}"
        cls = load_plugin_class(dotted_path)
        plugins.append(cls())
    return plugins
