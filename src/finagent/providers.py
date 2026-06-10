from __future__ import annotations

import json
import logging
import os
import re
import time
import urllib.request
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger("finagent.providers")


class LLMProvider(ABC):
    @abstractmethod
    def complete_structured(self, agent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        raise NotImplementedError


class MockLLMProvider(LLMProvider):
    """Deterministic provider used by tests and the offline demo.

    Roles differentiate on the feature names they care about: technical reads
    momentum features, macro reads regime features, fundamental reads
    valuation/growth features. Roles fall back to the blended feature_score
    when none of their features are present; critic stays contrarian on the
    blend.
    """

    ROLE_FEATURE_PREFIXES = {
        "technical": ("momentum_",),
        "macro": ("macro_",),
        "fundamental": ("valuation_", "growth_", "quality_", "fundamental_"),
    }

    def complete_structured(self, agent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        blend = float(payload.get("feature_score", 0.0))
        if agent == "critic":
            # Contrarian on the blend, plus an explicit bear case built from
            # risk_* features (e.g. drawdown from the 52-week high).
            score = -0.35 * blend - 0.5 * self._risk_penalty(payload)
        else:
            score = self._role_score(agent, payload, blend)
        score = max(-1.0, min(1.0, score))
        return {
            "score": score,
            "confidence": min(0.9, 0.55 + abs(score) * 0.25),
            "stance": "bullish" if score > 0.05 else "bearish" if score < -0.05 else "neutral",
            "thesis": f"{agent} view derived from verified structured evidence.",
            "risks": ["model uncertainty"],
        }

    @classmethod
    def _role_score(cls, agent: str, payload: Dict[str, Any], blend: float) -> float:
        features = payload.get("features") or {}
        prefixes = cls.ROLE_FEATURE_PREFIXES.get(agent)
        if prefixes and isinstance(features, dict):
            matched = [
                float(value)
                for name, value in features.items()
                if str(name).startswith(prefixes) and isinstance(value, (int, float))
            ]
            if matched:
                return sum(matched) / len(matched)
        return blend

    @staticmethod
    def _risk_penalty(payload: Dict[str, Any]) -> float:
        features = payload.get("features") or {}
        if not isinstance(features, dict):
            return 0.0
        matched = [
            float(value)
            for name, value in features.items()
            if str(name).startswith("risk_") and isinstance(value, (int, float))
        ]
        return sum(matched) / len(matched) if matched else 0.0


class DeepSeekProvider(LLMProvider):
    """DeepSeek chat-completions provider.

    Ported behaviors from maipf's DeepSeekClient: exponential-backoff retries,
    optional thinking mode, markdown-fence-tolerant JSON parsing, and token
    usage logging.
    """

    def __init__(self, max_retries: int = 3) -> None:
        self.api_key = os.environ.get("DEEPSEEK_API_KEY", "")
        self.base_url = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
        self.model = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
        self.thinking = os.environ.get("DEEPSEEK_THINKING_ENABLED", "false").lower() == "true"
        self.max_retries = max_retries

    def complete_structured(self, agent: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_key:
            raise RuntimeError("DEEPSEEK_API_KEY is required for live mode")
        request_body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": 2048,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"You are the {agent} analyst of a research team. "
                        "Given point-in-time evidence features, return JSON only with keys "
                        "score (float in [-1,1]), confidence (float in [0,1]), "
                        "stance (bullish|bearish|neutral), thesis (short string), "
                        "risks (list of strings). "
                        "Do not produce portfolio weights or orders."
                    ),
                },
                {"role": "user", "content": json.dumps({"agent": agent, **payload})},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.thinking:
            request_body["thinking"] = {"type": "enabled"}
        else:
            request_body["temperature"] = 0.1

        last_error: Optional[Exception] = None
        for attempt in range(self.max_retries):
            try:
                body = self._post(request_body)
                usage = body.get("usage", {})
                logger.info(
                    "deepseek ok agent=%s model=%s tokens=%s",
                    agent, self.model, usage.get("total_tokens", "?"),
                )
                return _parse_json_content(body["choices"][0]["message"]["content"])
            except Exception as error:  # noqa: BLE001 - retried, then surfaced
                last_error = error
                wait = 2**attempt
                logger.warning(
                    "deepseek attempt %d/%d failed: %s", attempt + 1, self.max_retries, error
                )
                if attempt < self.max_retries - 1:
                    time.sleep(wait)
        raise RuntimeError(f"DeepSeek call failed after {self.max_retries} attempts: {last_error}")

    def _post(self, request_body: Dict[str, Any]) -> Dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/chat/completions",
            data=json.dumps(request_body).encode(),
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.loads(response.read())


def _parse_json_content(content: str) -> Dict[str, Any]:
    """Tolerate markdown fences and surrounding prose around the JSON object."""
    text = content.strip()
    if text.startswith("```json"):
        text = text[7:]
    if text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group())
        raise


def select_provider(mode: Optional[str] = None) -> LLMProvider:
    """Pick the provider from an explicit mode or the FINAGENT_MODE env var."""
    resolved = (mode or os.environ.get("FINAGENT_MODE", "mock")).lower()
    if resolved == "live":
        return DeepSeekProvider()
    return MockLLMProvider()
