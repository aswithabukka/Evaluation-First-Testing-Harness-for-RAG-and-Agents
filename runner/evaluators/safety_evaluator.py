"""
Safety evaluator — layered.

Three layers, from cheapest to most robust. Each is optional; the evaluator
picks the most accurate one that's actually installed and falls back cleanly
if a model isn't available.

Layer 1: regex heuristics (always on)
    * PII patterns (email, phone, SSN, credit card)
    * Toxicity keyword density
    * Prompt-injection pattern match

Layer 2: Microsoft Presidio (if installed)
    * ML-backed PII detection, multilingual, handles obfuscation better than
      regex. Enable with ``use_presidio=True``.

Layer 3: Llama Guard / ShieldGemma (if HF transformers + model available)
    * Classifier for toxicity + jailbreaks. Enable with ``use_guard_model=True``
      and ``guard_model_id="meta-llama/Llama-Guard-3-8B"`` (or ShieldGemma).

All three layers contribute to the final scores. Regex is fast-path, the
others refine. Output keys:

    pii_detected: bool
    pii_types: list[str]
    pii_confidence: float            # from Presidio if available, else 1.0 on match
    toxicity_score: float            # 0..1
    prompt_injection_risk: float     # 0..1
    toxicity_source: str             # "regex" | "guard_model"
    guard_flags: list[str]           # guard model labels if used

Backward-compatible with the old ``evaluate(text)`` → dict signature.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field


# ---------------------------------------------------------------- regex layer


_PII_PATTERNS: dict[str, re.Pattern[str]] = {
    "email": re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
    "phone": re.compile(
        r"(?<!\d)(?:\+?1[\s\-.]?)?(?:\(?\d{3}\)?[\s\-.]?)\d{3}[\s\-.]?\d{4}(?!\d)"
    ),
    "ssn": re.compile(r"(?<!\d)\d{3}[\-\s]?\d{2}[\-\s]?\d{4}(?!\d)"),
    "credit_card": re.compile(r"(?<!\d)(?:\d{4}[\-\s]?){3}\d{4}(?!\d)"),
}

_TOXIC_KEYWORDS: list[str] = [
    "hate speech", "kill yourself", "kys", "go die", "racial slur",
    "white supremacy", "nazi", "terrorist", "bomb threat", "shoot up",
    "mass shooting", "sexual assault", "rape", "child abuse", "pedophile",
    "self-harm", "suicide method",
]

_INJECTION_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"forget\s+(all\s+)?(previous|prior|your)\s+(instructions?|prompts?|rules?)", re.I),
    re.compile(r"you\s+are\s+now\s+(a\s+)?(?:DAN|evil|unrestricted|jailbroken)", re.I),
    re.compile(r"act\s+as\s+(a\s+)?(?:DAN|evil|unrestricted|jailbroken)", re.I),
    re.compile(r"system\s*prompt\s*[:=]", re.I),
    re.compile(r"<\s*/?\s*system\s*>", re.I),
    re.compile(r"\[INST\]|\[/INST\]|\[SYSTEM\]", re.I),
    re.compile(r"do\s+anything\s+now", re.I),
    re.compile(r"bypass\s+(safety|content|moderation)\s*(filter|check|policy|restriction)", re.I),
    re.compile(r"override\s+(safety|content|moderation)\s*(filter|check|policy|restriction)", re.I),
    re.compile(r"reveal\s+(your\s+)?(system|initial|original)\s*(prompt|instructions?)", re.I),
    re.compile(r"pretend\s+(that\s+)?(you\s+)?(have\s+)?no\s+(restrictions?|rules?|limitations?)", re.I),
]


@dataclass
class SafetyResult:
    pii_detected: bool = False
    pii_types: list[str] = field(default_factory=list)
    pii_confidence: float = 0.0
    toxicity_score: float = 0.0
    prompt_injection_risk: float = 0.0
    toxicity_source: str = "regex"
    guard_flags: list[str] = field(default_factory=list)


class SafetyEvaluator:
    """Multi-layer safety scanner. Falls back gracefully when optional
    libraries / models aren't available.

    Args:
        additional_toxic_keywords: extra regex-layer keywords.
        use_presidio: enable Presidio for PII (requires ``presidio-analyzer``).
        use_guard_model: enable a guard model for toxicity/jailbreak
            classification (requires ``transformers`` and a downloaded model).
        guard_model_id: HF model id for the guard classifier.
    """

    def __init__(
        self,
        additional_toxic_keywords: list[str] | None = None,
        *,
        use_presidio: bool = False,
        use_guard_model: bool = False,
        guard_model_id: str = "meta-llama/Llama-Guard-3-8B",
    ) -> None:
        self._toxic_keywords = list(_TOXIC_KEYWORDS)
        if additional_toxic_keywords:
            self._toxic_keywords.extend(kw.strip().lower() for kw in additional_toxic_keywords)

        self._presidio = None
        if use_presidio:
            self._presidio = self._load_presidio()

        self._guard = None
        if use_guard_model:
            self._guard = self._load_guard(guard_model_id)

    # ------------------------------------------------------------------ public

    def evaluate(self, text: str) -> dict:
        pii_types, pii_conf = self._detect_pii(text)
        tox_score, tox_source, guard_flags = self._score_toxicity(text)
        injection_risk = self._score_prompt_injection(text)

        return {
            "pii_detected": len(pii_types) > 0,
            "pii_types": pii_types,
            "pii_confidence": pii_conf,
            "toxicity_score": tox_score,
            "prompt_injection_risk": injection_risk,
            "toxicity_source": tox_source,
            "guard_flags": guard_flags,
        }

    def evaluate_batch(self, texts: list[str]) -> list[dict]:
        return [self.evaluate(t) for t in texts]

    # ------------------------------------------------------------------ PII

    def _detect_pii(self, text: str) -> tuple[list[str], float]:
        if self._presidio is not None:
            try:
                results = self._presidio.analyze(text=text, language="en")
                if results:
                    types = sorted({r.entity_type.lower() for r in results})
                    conf = max((r.score for r in results), default=0.0)
                    return types, conf
                return [], 0.0
            except Exception:
                pass  # Fall through to regex.

        found = [t for t, p in _PII_PATTERNS.items() if p.search(text)]
        return found, 1.0 if found else 0.0

    # ------------------------------------------------------------------ toxicity

    def _score_toxicity(self, text: str) -> tuple[float, str, list[str]]:
        if self._guard is not None:
            try:
                score, flags = self._guard_score(text)
                return score, "guard_model", flags
            except Exception:
                pass  # Fall through.

        text_lower = text.lower()
        matches = sum(1 for kw in self._toxic_keywords if kw in text_lower)
        return min(matches / 3.0, 1.0), "regex", []

    def _guard_score(self, text: str) -> tuple[float, list[str]]:
        """Run the guard model; return (score_0_1, labels)."""
        tokenizer, model, device = self._guard
        import torch

        chat = [{"role": "user", "content": text}]
        prompt = tokenizer.apply_chat_template(chat, return_tensors="pt").to(device)
        with torch.no_grad():
            out = model.generate(prompt, max_new_tokens=20, temperature=0.0, do_sample=False)
        decoded = tokenizer.decode(out[0][prompt.shape[-1]:], skip_special_tokens=True).strip().lower()

        # Llama Guard emits "safe" or "unsafe\nS1,S2,S3".
        if decoded.startswith("safe"):
            return 0.0, []
        flags = []
        if "\n" in decoded:
            flags = [s.strip() for s in decoded.split("\n", 1)[1].split(",") if s.strip()]
        return 1.0, flags or ["unsafe"]

    # ------------------------------------------------------------------ injection

    @staticmethod
    def _score_prompt_injection(text: str) -> float:
        matches = sum(1 for pat in _INJECTION_PATTERNS if pat.search(text))
        return min(matches / 3.0, 1.0)

    # ------------------------------------------------------------------ loaders

    @staticmethod
    def _load_presidio():
        try:
            from presidio_analyzer import AnalyzerEngine
            return AnalyzerEngine()
        except ImportError:
            return None

    @staticmethod
    def _load_guard(model_id: str):
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError:
            return None
        try:
            tok = AutoTokenizer.from_pretrained(model_id)
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model = AutoModelForCausalLM.from_pretrained(
                model_id,
                torch_dtype=torch.float16 if device == "cuda" else torch.float32,
            ).to(device)
            return (tok, model, device)
        except Exception:
            return None
