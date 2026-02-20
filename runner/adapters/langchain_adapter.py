"""
Pre-built adapter for LangChain RAG chains.

Usage in rageval.yaml:
    adapter:
      module: runner.adapters.langchain_adapter
      class: LangChainAdapter
      config:
        chain_module: my_app.chains
        chain_factory: build_rag_chain
        chain_kwargs:
          index_path: ./data/index
"""
from runner.adapters.base import PipelineOutput, RAGAdapter


class LangChainAdapter(RAGAdapter):
    """
    Wraps any LangChain chain that accepts a string query and returns a dict
    with at least an "answer" key. The chain should also return "source_documents"
    (a list of Document objects) to enable faithfulness evaluation.
    """

    def __init__(
        self,
        chain_module: str,
        chain_factory: str,
        chain_kwargs: dict | None = None,
    ):
        self._chain_module = chain_module
        self._chain_factory = chain_factory
        self._chain_kwargs = chain_kwargs or {}
        self._chain = None

    def setup(self) -> None:
        import importlib

        module = importlib.import_module(self._chain_module)
        factory = getattr(module, self._chain_factory)
        self._chain = factory(**self._chain_kwargs)

    def run(self, query: str, context: dict) -> PipelineOutput:
        if self._chain is None:
            raise RuntimeError("LangChainAdapter.setup() was not called before run()")

        result = self._chain.invoke({"query": query})

        answer = result.get("answer") or result.get("result") or str(result)
        source_docs = result.get("source_documents", [])
        retrieved_contexts = [doc.page_content for doc in source_docs]

        return PipelineOutput(
            answer=answer,
            retrieved_contexts=retrieved_contexts,
            metadata={"raw_result": str(result)},
        )
