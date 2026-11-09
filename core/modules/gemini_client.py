import json
import os
from pathlib import Path
import random
import time
from typing import Any, Dict, List, Optional, Tuple
import urllib.error
import urllib.request

MODEL_FALLBACK_CHAIN = [
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
    "gemini-3.1-flash-lite",
    "gemini-3.5-flash-lite",
]


def _get_api_key() -> str:
    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if api_key:
        return api_key.strip()

    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                if k.strip() in ("GEMINI_API_KEY", "GOOGLE_API_KEY"):
                    return v.strip().strip("'").strip('"')

    raise RuntimeError("GEMINI_API_KEY is not configured in environment or .env file.")


def call_gemini_resilient(
    payload: Dict[str, Any],
    timeout_per_call: int = 12,
    max_rounds: int = 1,
) -> Tuple[Dict[str, Any], str, int]:
    """
    Executes a POST request against the Gemini generateContent REST API with:
    - Multi-model fallback across MODEL_FALLBACK_CHAIN
    - Fast failover when any model returns 503 or times out
    Returns (candidate_content_dict, model_used, latency_ms).
    """
    api_key = _get_api_key()
    start_time = time.time()
    encoded_payload = json.dumps(payload).encode("utf-8")
    errors: List[str] = []

    for round_idx in range(max_rounds):
        if round_idx > 0:
            time.sleep(0.5 + random.uniform(0.1, 0.4))

        for model_name in MODEL_FALLBACK_CHAIN:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models/"
                f"{model_name}:generateContent?key={api_key}"
            )
            req = urllib.request.Request(
                url,
                data=encoded_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            model_timeout = min(14, timeout_per_call)
            try:
                with urllib.request.urlopen(req, timeout=model_timeout) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    candidates = body.get("candidates") or []
                    if not candidates:
                        raise RuntimeError(f"No candidates returned from {model_name}")
                    content = candidates[0].get("content") or {}
                    latency_ms = int((time.time() - start_time) * 1000)
                    return content, model_name, latency_ms
            except urllib.error.HTTPError as http_err:
                err_body = http_err.read().decode("utf-8", errors="replace")[:160]
                errors.append(f"{model_name} (HTTP {http_err.code}): {err_body}")
            except Exception as exc:
                errors.append(f"{model_name}: {exc}")

    raise RuntimeError(f"All Gemini models failed: {' | '.join(errors[-4:])}")


def generate_structured_with_gemini(
    system_instruction: str,
    user_prompt: str,
    response_schema: Dict[str, Any],
    temperature: float = 0.1,
) -> Tuple[Dict[str, Any], str, int]:
    """
    Calls Gemini with a structured JSON responseSchema and resilient fallback.
    """
    payload = {
        "systemInstruction": {"parts": [{"text": system_instruction}]},
        "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
            "responseSchema": response_schema,
        },
    }
    content, model_used, latency_ms = call_gemini_resilient(
        payload=payload, timeout_per_call=18, max_rounds=1
    )
    parts = content.get("parts") or []
    raw_text = "".join(p.get("text", "") for p in parts).strip()
    if not raw_text:
        raise RuntimeError(f"Empty JSON text from {model_used}")
    return json.loads(raw_text), model_used, latency_ms
