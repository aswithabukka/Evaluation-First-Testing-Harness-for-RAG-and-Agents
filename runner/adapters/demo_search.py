"""
Demo Search Engine Adapter — hybrid local + web search system.

Searches a built-in document corpus first (OpenAI embeddings + cosine similarity).
Falls back to live Google search via Serper API when no local results are relevant.
Returns ranked results with relevance scores, suitable for NDCG/MRR/MAP evaluation.
"""
import os
import math

import httpx
from openai import OpenAI

from runner.adapters.base import PipelineOutput, RAGAdapter

# Document corpus — each doc has an ID, title, and content
DOCUMENTS = [
    {
        "id": "doc-001",
        "title": "Python List Sorting",
        "content": "Python lists can be sorted using the built-in sort() method for in-place sorting or the sorted() function which returns a new list. Both accept a key parameter for custom sorting and a reverse parameter for descending order. The Timsort algorithm is used, which has O(n log n) time complexity.",
        "tags": ["python", "programming", "sorting"],
    },
    {
        "id": "doc-002",
        "title": "JavaScript Async/Await",
        "content": "Async/await in JavaScript provides a cleaner syntax for working with promises. An async function always returns a promise. The await keyword pauses execution until the promise resolves. Error handling is done with try/catch blocks. This pattern is preferred over .then() chains for readability.",
        "tags": ["javascript", "programming", "async"],
    },
    {
        "id": "doc-003",
        "title": "Docker Container Basics",
        "content": "Docker containers are lightweight, standalone executable packages that include everything needed to run software. A Dockerfile defines the build steps. Key commands: docker build, docker run, docker ps, docker stop. Containers share the host OS kernel, making them more efficient than virtual machines.",
        "tags": ["docker", "devops", "containers"],
    },
    {
        "id": "doc-004",
        "title": "SQL JOIN Types",
        "content": "SQL supports several JOIN types: INNER JOIN returns matching rows from both tables. LEFT JOIN returns all rows from the left table plus matches. RIGHT JOIN returns all from the right table. FULL OUTER JOIN returns all rows from both tables. CROSS JOIN produces a Cartesian product.",
        "tags": ["sql", "database", "queries"],
    },
    {
        "id": "doc-005",
        "title": "Git Branching Strategy",
        "content": "Common Git branching strategies include Git Flow (feature/develop/release/hotfix branches), GitHub Flow (simple feature branches merged to main), and Trunk-Based Development (short-lived branches, frequent merges). Choose based on team size and release cadence.",
        "tags": ["git", "version-control", "workflow"],
    },
    {
        "id": "doc-006",
        "title": "REST API Design",
        "content": "REST API best practices: use nouns for endpoints (e.g., /users, /orders), HTTP methods for actions (GET, POST, PUT, DELETE), proper status codes (200, 201, 404, 500), pagination for collections, versioning in URL or headers, and HATEOAS for discoverability.",
        "tags": ["api", "rest", "web"],
    },
    {
        "id": "doc-007",
        "title": "Machine Learning Pipeline",
        "content": "A typical ML pipeline includes: data collection, data cleaning, feature engineering, model selection, training, validation, hyperparameter tuning, testing, deployment, and monitoring. Common tools include scikit-learn, TensorFlow, PyTorch, and MLflow for experiment tracking.",
        "tags": ["ml", "ai", "data-science"],
    },
    {
        "id": "doc-008",
        "title": "CSS Flexbox Layout",
        "content": "CSS Flexbox is a one-dimensional layout model. Key properties: display:flex on container, flex-direction (row/column), justify-content (main axis alignment), align-items (cross axis alignment), flex-wrap, and flex-grow/shrink/basis on items. Use for navigation bars, card layouts, and centering.",
        "tags": ["css", "frontend", "layout"],
    },
    {
        "id": "doc-009",
        "title": "Kubernetes Pods and Services",
        "content": "Kubernetes Pods are the smallest deployable units containing one or more containers. Services provide stable networking: ClusterIP (internal), NodePort (external via node), LoadBalancer (cloud LB), and Ingress (HTTP routing). Deployments manage Pod replicas and rolling updates.",
        "tags": ["kubernetes", "devops", "orchestration"],
    },
    {
        "id": "doc-010",
        "title": "React Hooks Overview",
        "content": "React Hooks let you use state and lifecycle features in functional components. useState for state management, useEffect for side effects, useContext for context, useRef for mutable refs, useMemo and useCallback for performance optimization. Custom hooks extract reusable logic.",
        "tags": ["react", "javascript", "frontend"],
    },
    {
        "id": "doc-011",
        "title": "PostgreSQL Performance Tuning",
        "content": "PostgreSQL performance tips: use EXPLAIN ANALYZE for query plans, create indexes on frequently queried columns, use connection pooling (PgBouncer), optimize shared_buffers and work_mem, vacuum regularly, use partitioning for large tables, and consider read replicas for scaling reads.",
        "tags": ["postgresql", "database", "performance"],
    },
    {
        "id": "doc-012",
        "title": "Python Virtual Environments",
        "content": "Python virtual environments isolate project dependencies. Create with python -m venv myenv, activate with source myenv/bin/activate (Unix) or myenv\\Scripts\\activate (Windows). Use pip freeze > requirements.txt to save and pip install -r requirements.txt to restore. Poetry and pipenv are modern alternatives.",
        "tags": ["python", "packaging", "environment"],
    },
    {
        "id": "doc-013",
        "title": "OAuth 2.0 Flow",
        "content": "OAuth 2.0 authorization flows: Authorization Code (web apps, most secure), Implicit (deprecated, was for SPAs), Client Credentials (machine-to-machine), Resource Owner Password (legacy apps). Use PKCE extension for public clients. Access tokens are short-lived; refresh tokens get new access tokens.",
        "tags": ["auth", "security", "oauth"],
    },
    {
        "id": "doc-014",
        "title": "Redis Caching Patterns",
        "content": "Redis caching patterns: Cache-Aside (app manages cache), Write-Through (write to cache and DB), Write-Behind (async DB writes), Read-Through (cache loads on miss). Set TTL for expiration. Use Redis for sessions, rate limiting, pub/sub messaging, and leaderboards. Supports data structures: strings, lists, sets, hashes, sorted sets.",
        "tags": ["redis", "caching", "performance"],
    },
    {
        "id": "doc-015",
        "title": "CI/CD with GitHub Actions",
        "content": "GitHub Actions automates CI/CD with YAML workflow files in .github/workflows/. Triggers include push, pull_request, schedule, and workflow_dispatch. Jobs run on runners (ubuntu-latest, windows, macOS). Use actions/checkout, actions/setup-node, etc. Matrix builds test multiple versions. Cache dependencies for speed.",
        "tags": ["ci-cd", "github", "automation"],
    },
    # ── AI / LLM Frameworks ──────────────────────────────────────────────
    {
        "id": "doc-016",
        "title": "LangChain Framework",
        "content": "LangChain is an open-source framework for building applications powered by large language models (LLMs). It provides abstractions for chains (sequential LLM calls), agents (LLMs that decide which tools to use), memory (conversation history), and retrieval (RAG pipelines). Key components include prompt templates, output parsers, document loaders, text splitters, vector stores, and retrievers. LangChain supports OpenAI, Anthropic, Hugging Face, and many other LLM providers.",
        "tags": ["langchain", "llm", "ai-framework"],
    },
    {
        "id": "doc-017",
        "title": "LlamaIndex (GPT Index)",
        "content": "LlamaIndex is a data framework for connecting custom data sources to large language models. It excels at building RAG (Retrieval-Augmented Generation) applications with features for data ingestion, indexing, and querying. Key concepts include nodes (data chunks), indices (vector store index, list index, tree index), query engines, and response synthesizers. It integrates with vector databases like Pinecone, Weaviate, and ChromaDB.",
        "tags": ["llamaindex", "rag", "ai-framework"],
    },
    {
        "id": "doc-018",
        "title": "Vector Databases for AI",
        "content": "Vector databases store and query high-dimensional embeddings for similarity search. Popular options: Pinecone (managed, scalable), Weaviate (open-source, hybrid search), ChromaDB (lightweight, Python-native), Milvus (open-source, high-performance), Qdrant (Rust-based, fast). Use cases include semantic search, recommendation systems, RAG pipelines, and image similarity. Key concepts: embeddings, approximate nearest neighbor (ANN) algorithms like HNSW, and distance metrics (cosine, euclidean, dot product).",
        "tags": ["vector-db", "embeddings", "ai"],
    },
    {
        "id": "doc-019",
        "title": "Prompt Engineering Techniques",
        "content": "Prompt engineering optimizes LLM inputs for better outputs. Techniques include: zero-shot (direct question), few-shot (examples in prompt), chain-of-thought (step-by-step reasoning), ReAct (reasoning + acting), tree-of-thought (exploring multiple paths), and role prompting (assign a persona). Best practices: be specific, provide context, use delimiters, specify output format, and include examples. Temperature controls randomness; lower values for factual tasks, higher for creative ones.",
        "tags": ["prompt-engineering", "llm", "ai"],
    },
    {
        "id": "doc-020",
        "title": "RAG Architecture Patterns",
        "content": "Retrieval-Augmented Generation (RAG) combines retrieval with LLM generation. Basic RAG: embed documents, store in vector DB, retrieve top-k chunks for each query, feed to LLM as context. Advanced patterns: HyDE (hypothetical document embeddings), multi-query retrieval, re-ranking (cross-encoder), recursive retrieval, sentence-window retrieval, and parent-document retrieval. Evaluation metrics include faithfulness, answer relevancy, context precision, and context recall.",
        "tags": ["rag", "llm", "architecture"],
    },
    # ── Additional Dev Topics ────────────────────────────────────────────
    {
        "id": "doc-021",
        "title": "TypeScript Generics",
        "content": "TypeScript generics enable writing reusable, type-safe code. Declare with angle brackets: function identity<T>(arg: T): T. Constrain with extends: <T extends HasLength>. Use with interfaces, classes, and type aliases. Common patterns: generic collections (Array<T>), utility types (Partial<T>, Required<T>, Pick<T, K>), and mapped types. Generics are resolved at compile time with zero runtime cost.",
        "tags": ["typescript", "programming", "types"],
    },
    {
        "id": "doc-022",
        "title": "GraphQL API Design",
        "content": "GraphQL is a query language for APIs that lets clients request exactly the data they need. Define schemas with types, queries, mutations, and subscriptions. Resolvers fetch data for each field. Benefits over REST: no over-fetching, single endpoint, strong typing, introspection. Tools include Apollo Server/Client, Relay, and GraphQL Code Generator. Use DataLoader for batching and caching to avoid the N+1 problem.",
        "tags": ["graphql", "api", "web"],
    },
    {
        "id": "doc-023",
        "title": "Microservices Architecture",
        "content": "Microservices decompose applications into small, independently deployable services. Each service owns its data and communicates via APIs (REST/gRPC) or async messaging (Kafka, RabbitMQ). Benefits: independent scaling, technology diversity, fault isolation. Challenges: distributed transactions (use sagas), service discovery, observability (tracing, logging, metrics). Patterns include API Gateway, Circuit Breaker, Event Sourcing, and CQRS.",
        "tags": ["architecture", "microservices", "distributed"],
    },
    {
        "id": "doc-024",
        "title": "Next.js App Router",
        "content": "Next.js App Router (v13+) uses a file-system based router with React Server Components by default. Key features: layouts (shared UI), loading.tsx (streaming), error.tsx (error boundaries), route groups, parallel routes, and intercepting routes. Server Actions handle form submissions. Data fetching uses async/await in Server Components. Use 'use client' directive for interactive components. Supports static and dynamic rendering, ISR, and edge runtime.",
        "tags": ["nextjs", "react", "frontend"],
    },
    {
        "id": "doc-025",
        "title": "FastAPI Web Framework",
        "content": "FastAPI is a modern Python web framework for building APIs. Key features: automatic OpenAPI/Swagger docs, type validation via Pydantic, async/await support, dependency injection, middleware, and WebSocket support. Use path/query parameters with type hints. Background tasks for async processing. Integrates with SQLAlchemy, databases, and ORMs. Performance comparable to Node.js and Go thanks to Starlette and uvicorn ASGI server.",
        "tags": ["fastapi", "python", "api"],
    },
]


class DemoSearchAdapter(RAGAdapter):
    """Self-contained search engine using OpenAI embeddings for document ranking."""

    # Minimum cosine similarity to consider a result relevant
    RELEVANCE_THRESHOLD = 0.25

    def __init__(self, model: str = "gpt-4o-mini", top_k: int = 5, **kwargs):
        self.model = model
        self.top_k = top_k
        self._embed_model = "text-embedding-3-small"
        self._client: OpenAI | None = None
        self._doc_embeddings: list[tuple[dict, list[float]]] = []

    def setup(self) -> None:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        self._client = OpenAI(api_key=api_key)

        # Embed all documents
        texts = [f"{d['title']}. {d['content']}" for d in DOCUMENTS]
        response = self._client.embeddings.create(input=texts, model=self._embed_model)
        self._doc_embeddings = [
            (DOCUMENTS[i], response.data[i].embedding)
            for i in range(len(DOCUMENTS))
        ]

    def run(self, query: str, context: dict | None = None) -> PipelineOutput:
        # 1. Local search — embed the query and rank against corpus
        q_response = self._client.embeddings.create(input=[query], model=self._embed_model)
        q_embedding = q_response.data[0].embedding

        scored = []
        for doc, doc_emb in self._doc_embeddings:
            sim = self._cosine_similarity(q_embedding, doc_emb)
            scored.append((sim, doc))
        scored.sort(key=lambda x: x[0], reverse=True)

        relevant = [(sim, doc) for sim, doc in scored if sim >= self.RELEVANCE_THRESHOLD]
        top_results = relevant[: self.top_k]

        # 2. If local results found, return them
        if top_results:
            best_doc = top_results[0][1]
            answer = f"{best_doc['title']}: {best_doc['content']}"
            retrieved_contexts = [
                f"[{doc['id']}] {doc['title']}: {doc['content']}"
                for _, doc in top_results
            ]
            return PipelineOutput(
                answer=answer,
                retrieved_contexts=retrieved_contexts,
                tool_calls=[],
                turn_history=[],
                metadata={
                    "source": "local",
                    "model": self._embed_model,
                    "top_k": self.top_k,
                    "result_count": len(top_results),
                    "relevance_threshold": self.RELEVANCE_THRESHOLD,
                    "top_doc_id": top_results[0][1]["id"],
                    "scores": {doc["id"]: round(sim, 4) for sim, doc in top_results},
                    "ranked_ids": [doc["id"] for _, doc in top_results],
                },
            )

        # 3. No local results — try web search via Serper API
        web_results = self._web_search(query)

        if web_results:
            # Build context from web results for GPT answer generation
            context_block = "\n\n".join(
                f"[Source {i + 1}] {r['title']}: {r['snippet']}"
                for i, r in enumerate(web_results)
            )
            completion = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a helpful search assistant. Answer the user's question "
                            "using ONLY the information in the provided web search results. "
                            "Be concise and cite which sources you used."
                        ),
                    },
                    {
                        "role": "user",
                        "content": f"Web search results:\n{context_block}\n\nQuestion: {query}",
                    },
                ],
                temperature=0,
                max_tokens=512,
            )
            answer = completion.choices[0].message.content or ""

            retrieved_contexts = [
                f"[WEB] {r['title']}: {r['snippet']} ({r['link']})"
                for r in web_results
            ]

            return PipelineOutput(
                answer=answer,
                retrieved_contexts=retrieved_contexts,
                tool_calls=[],
                turn_history=[],
                metadata={
                    "source": "web",
                    "model": self.model,
                    "top_k": self.top_k,
                    "result_count": len(web_results),
                    "web_results": [
                        {"title": r["title"], "link": r["link"], "snippet": r["snippet"]}
                        for r in web_results
                    ],
                },
            )

        # 4. No web search available or no results
        return PipelineOutput(
            answer=(
                "No relevant results found. The local knowledge base doesn't cover this topic, "
                "and web search is not configured. Add a SERPER_API_KEY to enable Google search fallback."
            ),
            retrieved_contexts=[],
            tool_calls=[],
            turn_history=[],
            metadata={
                "source": "none",
                "model": self._embed_model,
                "top_k": self.top_k,
                "result_count": 0,
            },
        )

    # ------------------------------------------------------------------
    def _web_search(self, query: str) -> list[dict]:
        """Search Google via Serper API. Returns list of {title, link, snippet}."""
        api_key = os.environ.get("SERPER_API_KEY", "").strip()
        if not api_key:
            return []

        try:
            resp = httpx.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": api_key, "Content-Type": "application/json"},
                json={"q": query, "num": self.top_k},
                timeout=10.0,
            )
            resp.raise_for_status()
            data = resp.json()

            results = []
            for item in data.get("organic", [])[:self.top_k]:
                results.append({
                    "title": item.get("title", ""),
                    "link": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                })
            return results
        except Exception:
            return []

    def teardown(self) -> None:
        self._doc_embeddings = []
        self._client = None

    @staticmethod
    def _cosine_similarity(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)
