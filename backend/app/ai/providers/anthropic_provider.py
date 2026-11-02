"""Anthropic Messages API adapter (official `anthropic` SDK).

Notes for current models (Opus 5.5 / Sonnet 5.5 / Haiku 5.5):
 * thinking is adaptive by default -> we omit the `thinking` param and control depth via output_config.effort
 * sampling params (temperature) are rejected -> never sent
 * forced tool_choice is rejected -> tool_choice stays "auto"; tools use strict schemas
 * structured output -> output_config.format json_schema
 * prompt caching -> cache_control on the (stable) system prompt
 * refusals -> optional server-side fallback (beta) + explicit stop_reason handling
"""
import json
import anthropic
from app.ai.providers.base import LLMRequest, LLMResponse, ToolCall, ProviderError
from app.core.config import get_settings

FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}


class AnthropicProvider:
    name = "anthropic"

    def __init__(self):
        self._client = None

    def available(self) -> bool:
        return bool(get_settings().anthropic_api_key)

    def client(self) -> anthropic.Anthropic:
        if self._client is None:
            s = get_settings()
            self._client = anthropic.Anthropic(api_key=s.anthropic_api_key, max_retries=s.ai_max_retries)
        return self._client

    @staticmethod
    def _messages(req: LLMRequest) -> list[dict]:
        out: list[dict] = []
        for m in req.messages:
            if m.role == "user":
                out.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                if m.raw and m.raw.get("provider") == "anthropic":
                    out.append({"role": "assistant", "content": m.raw["content"]})  # replay unchanged (thinking blocks)
                else:
                    blocks = []
                    if m.content:
                        blocks.append({"type": "text", "text": m.content})
                    for tc in m.tool_calls:
                        blocks.append({"type": "tool_use", "id": tc.id, "name": tc.name, "input": tc.arguments})
                    out.append({"role": "assistant", "content": blocks or m.content})
            elif m.role == "tool":
                block = {"type": "tool_result", "tool_use_id": m.tool_call_id, "content": m.content}
                if m.is_error:
                    block["is_error"] = True
                # All tool results for one assistant turn go in ONE user message.
                if out and out[-1]["role"] == "user" and isinstance(out[-1]["content"], list) and \
                        out[-1]["content"] and out[-1]["content"][0].get("type") == "tool_result":
                    out[-1]["content"].append(block)
                else:
                    out.append({"role": "user", "content": [block]})
        return out

    def complete(self, model: str, req: LLMRequest, timeout_s: float) -> LLMResponse:
        s = get_settings()
        params: dict = {
            "model": model,
            "max_tokens": req.max_tokens,
            "messages": self._messages(req),
        }
        if req.system:
            params["system"] = [{"type": "text", "text": req.system, "cache_control": {"type": "ephemeral"}}]
        output_config: dict = {}
        if req.effort:
            output_config["effort"] = req.effort
        if req.json_schema:
            output_config["format"] = {"type": "json_schema", "schema": req.json_schema}
        if output_config:
            params["output_config"] = output_config
        if req.tools:
            params["tools"] = [{"name": t.name, "description": t.description, "input_schema": t.parameters, "strict": True} for t in req.tools]
        try:
            client = self.client().with_options(timeout=timeout_s)
            if s.anthropic_refusal_fallback and model in FALLBACK_MODELS:
                resp = client.beta.messages.create(betas=["server-side-fallback-2026-07-01"], fallbacks="default", **params)
            else:
                resp = client.messages.create(**params)
        except anthropic.RateLimitError as e:
            raise ProviderError(f"anthropic rate limited: {e.message}", retryable=True)
        except anthropic.APIConnectionError as e:
            raise ProviderError(f"anthropic connection error: {e}", retryable=True)
        except anthropic.BadRequestError as e:
            raise ProviderError(f"anthropic bad request: {e.message}", retryable=False)
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError, anthropic.NotFoundError) as e:
            raise ProviderError(f"anthropic auth/model error: {e.message}", retryable=True)  # try next provider
        except anthropic.APIStatusError as e:
            raise ProviderError(f"anthropic error {e.status_code}: {e.message}", retryable=e.status_code >= 500)

        text_parts, calls = [], []
        for b in resp.content:
            if b.type == "text":
                text_parts.append(b.text)
            elif b.type == "tool_use":
                calls.append(ToolCall(id=b.id, name=b.name, arguments=dict(b.input)))
        text = "".join(text_parts)
        refusal = resp.stop_reason == "refusal"
        if refusal:
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            text = text or f"I can't help with that request{f' ({cat})' if cat else ''}."
        parsed = None
        if req.json_schema and text and not refusal:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        u = resp.usage
        cached = (getattr(u, "cache_read_input_tokens", 0) or 0)
        input_total = (u.input_tokens or 0) + cached + (getattr(u, "cache_creation_input_tokens", 0) or 0)
        return LLMResponse(
            text=text, model=resp.model, provider="anthropic", tool_calls=calls, parsed=parsed,
            input_tokens=input_total, output_tokens=u.output_tokens or 0, cached_tokens=cached,
            stop_reason=resp.stop_reason or "end_turn", refusal=refusal,
            raw_assistant={"provider": "anthropic", "content": [b.model_dump(exclude_none=True) for b in resp.content
                                                                 if b.type in ("text", "tool_use", "thinking", "redacted_thinking")]},
        )
