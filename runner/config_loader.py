"""
Loads rageval.yaml from the user's project and dynamically imports their RAGAdapter.

Example rageval.yaml:

    adapter:
      module: my_rag_app.pipeline
      class: MyRAGPipeline
      config:
        index_url: "http://localhost:6333"
        collection: "docs_v2"
        model: "gpt-4o"

    test_set:
      id: "550e8400-e29b-41d4-a716-446655440000"

    thresholds:
      faithfulness: 0.75
      answer_relevancy: 0.70
      context_precision: 0.65
      context_recall: 0.60
      pass_rate: 0.90

    metrics:
      - faithfulness
      - answer_relevancy
      - context_precision
      - context_recall
      - rule_evaluation

    api:
      url: "http://localhost:8000"

    plugins:
      - module: my_rag_app.custom_metrics
        class: DrugDosageHallucinationMetric
"""
import importlib
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class AdapterConfig:
    module: str
    class_name: str
    config: dict = field(default_factory=dict)


@dataclass
class APIConfig:
    url: str = "http://localhost:8000"
    api_key: str | None = None


@dataclass
class HarnessConfig:
    adapter: AdapterConfig
    test_set_id: str | None = None
    test_set_name: str | None = None
    thresholds: dict = field(default_factory=dict)
    metrics: list[str] = field(
        default_factory=lambda: [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "rule_evaluation",
        ]
    )
    api: APIConfig = field(default_factory=APIConfig)
    plugins: list[dict] = field(default_factory=list)


class ConfigLoader:
    def load(self, path: str = "rageval.yaml") -> HarnessConfig:
        config_path = Path(path)
        if not config_path.exists():
            raise FileNotFoundError(
                f"rageval.yaml not found at {config_path.absolute()}. "
                "Copy rageval.yaml.example to rageval.yaml and fill in your settings."
            )

        with config_path.open() as f:
            raw = yaml.safe_load(f)

        adapter_raw = raw.get("adapter", {})
        adapter = AdapterConfig(
            module=adapter_raw.get("module", ""),
            class_name=adapter_raw.get("class", ""),
            config=adapter_raw.get("config", {}),
        )

        test_set_raw = raw.get("test_set", {})
        test_set_id = test_set_raw.get("id") if isinstance(test_set_raw, dict) else None
        test_set_name = test_set_raw.get("name") if isinstance(test_set_raw, dict) else None

        api_raw = raw.get("api", {})
        api = APIConfig(
            url=api_raw.get("url", "http://localhost:8000"),
            api_key=api_raw.get("api_key"),
        )

        return HarnessConfig(
            adapter=adapter,
            test_set_id=test_set_id,
            test_set_name=test_set_name,
            thresholds=raw.get("thresholds", {}),
            metrics=raw.get("metrics", [
                "faithfulness",
                "answer_relevancy",
                "context_precision",
                "context_recall",
                "rule_evaluation",
            ]),
            api=api,
            plugins=raw.get("plugins", []),
        )

    def load_adapter(self, config: HarnessConfig):
        """Dynamically import and instantiate the user's RAGAdapter."""
        from runner.adapters.base import RAGAdapter

        if not config.adapter.module:
            raise ValueError("adapter.module is not set in rageval.yaml")
        if not config.adapter.class_name:
            raise ValueError("adapter.class is not set in rageval.yaml")

        module = importlib.import_module(config.adapter.module)
        cls = getattr(module, config.adapter.class_name, None)
        if cls is None:
            raise AttributeError(
                f"Class {config.adapter.class_name!r} not found in module {config.adapter.module!r}"
            )
        if not issubclass(cls, RAGAdapter):
            raise TypeError(
                f"{config.adapter.class_name} must subclass runner.adapters.base.RAGAdapter"
            )
        return cls(**config.adapter.config)
