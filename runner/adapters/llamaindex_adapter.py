"""
Pre-built adapter for LlamaIndex query engines.

Usage in rageval.yaml:
    adapter:
      module: runner.adapters.llamaindex_adapter
      class: LlamaIndexAdapter
      config:
        engine_module: my_app.engine
        engine_factory: build_query_engine
        engine_kwargs:
          index_dir: ./storage
"""
from runner.adapters.base import PipelineOutput, RAGAdapter


class LlamaIndexAdapter(RAGAdapter):
    """
    Wraps any LlamaIndex query engine. The engine must implement .query(str).
    Source nodes are extracted from the response for faithfulness evaluation.
    """

    def __init__(
        self,
        engine_module: str,
        engine_factory: str,
        engine_kwargs: dict | None = None,
    ):
        self._engine_module = engine_module
        self._engine_factory = engine_factory
        self._engine_kwargs = engine_kwargs or {}
        self._engine = None

    def setup(self) -> None:
        import importlib

        module = importlib.import_module(self._engine_module)
        factory = getattr(module, self._engine_factory)
        self._engine = factory(**self._engine_kwargs)

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._engine is None:
            raise RuntimeError("LlamaIndexAdapter.setup() was not called before run()")

        response = self._engine.query(query)
        answer = str(response)
        retrieved_contexts = [
            node.get_content() for node in getattr(response, "source_nodes", [])
        ]

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=retrieved_contexts,
            metadata={"response_type": type(response).__name__},
        )
