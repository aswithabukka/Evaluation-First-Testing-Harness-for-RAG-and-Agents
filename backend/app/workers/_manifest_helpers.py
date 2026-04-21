"""
Manifest recording helpers used by the Celery evaluation worker.

Kept in their own module so unit tests can import them without pulling in
Celery / Redis. The worker (``evaluation_tasks.py``) re-exports
``record_evaluator`` for backwards compatibility.
"""
from __future__ import annotations

import importlib


def record_evaluator(manifest, module_path: str, class_name: str) -> None:
    """Register an evaluator class in the run manifest, idempotently.

    Imports the class lazily so we can capture its ``name`` / ``version``
    class attributes. Swallows errors — manifest recording must never take
    down a run. If the class is missing (e.g. Ragas not installed) we fall
    back to a stub row with version ``"unknown"``.
    """
    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name, None)
        if cls is None:
            raise AttributeError(class_name)
        stub_name = getattr(cls, "name", class_name)
        stub_version = getattr(cls, "version", "unknown")

        class _EvalStub:
            pass

        _EvalStub.__name__ = class_name
        _EvalStub.__qualname__ = class_name
        instance = _EvalStub()
        instance.name = stub_name  # type: ignore[attr-defined]
        instance.version = stub_version  # type: ignore[attr-defined]
        try:
            instance.__class__ = cls  # show real class name in manifest entry
        except TypeError:
            pass
        manifest.record_evaluator(instance)
    except Exception:
        try:
            class _EvalStub:
                pass

            _EvalStub.__name__ = class_name
            _EvalStub.__qualname__ = class_name
            fallback = _EvalStub()
            fallback.name = class_name  # type: ignore[attr-defined]
            fallback.version = "unknown"  # type: ignore[attr-defined]
            manifest.record_evaluator(fallback)
        except Exception:
            pass
