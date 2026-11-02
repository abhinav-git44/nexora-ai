"""OpenAI Responses API adapter (official `openai` SDK): function tools, strict JSON-schema output, prompt caching key."""
import json
import openai
from app.ai.providers.base import LLMRequest, LLMResponse, ToolCall, ProviderError
from app.core.config import get_settings

REASONING_PREFIXES = ("gpt-5", "o3", "o4")


class OpenAIProvider:
    name = "openai"

    def __init__(self):
        self._client = None

    def available(self) -> bool:
        return bool(get_settings().openai_api_key)

    def client(self) -> openai.OpenAI:
        if self._client is None:
            s = get_settings()
            self._client = openai.OpenAI(api_key=s.openai_api_key, max_retries=s.ai_max_retries)
        return self._client

    @staticmethod
    def _input(req: LLMRequest) -> list[dict]:
        items: list[dict] = []
        for m in req.messages:
            if m.role == "user":
                items.append({"role": "user", "content": m.content})
            elif m.role == "assistant":
                if m.raw and m.raw.get("provider") == "openai":
                    items.extend(m.raw["output"])
                else:
                    if m.content:
                        items.append({"role": "assistant", "content": m.content})
                    for tc in m.tool_calls:
                        items.append({"type": "function_call", "call_id": tc.id, "name": tc.name, "arguments": json.dumps(tc.arguments)})
            elif m.role == "tool":
                items.append({"type": "function_call_output", "call_id": m.tool_call_id, "output": m.content})
        return items

    def complete(self, model: str, req: LLMRequest, timeout_s: float) -> LLMResponse:
        params: dict = {"model": model, "input": self._input(req), "max_output_tokens": req.max_tokens, "store": False}
        if req.system:
            params["instructions"] = req.system
            params["prompt_cache_key"] = f"nexora:{req.task_type}"
        is_reasoning = model.startswith(REASONING_PREFIXES)
        if is_reasoning and req.effort:
            params["reasoning"] = {"effort": {"low": "low", "medium": "medium", "high": "high"}.get(req.effort, "medium")}
        if req.temperature is not None and not is_reasoning:
            params["temperature"] = req.temperature
        if req.tools:
            params["tools"] = [{"type": "function", "name": t.name, "description": t.description,
                                "parameters": t.parameters, "strict": True} for t in req.tools]
        if req.json_schema:
            params["text"] = {"format": {"type": "json_schema", "name": "output", "schema": req.json_schema, "strict": True}}
        try:
            resp = self.client().with_options(timeout=timeout_s).responses.create(**params)
        except openai.RateLimitError as e:
            raise ProviderError(f"openai rate limited: {e}", retryable=True)
        except openai.APIConnectionError as e:
            raise ProviderError(f"openai connection error: {e}", retryable=True)
        except openai.BadRequestError as e:
            raise ProviderError(f"openai bad request: {e}", retryable=False)
        except (openai.AuthenticationError, openai.PermissionDeniedError, openai.NotFoundError) as e:
            raise ProviderError(f"openai auth/model error: {e}", retryable=True)
        except openai.APIStatusError as e:
            raise ProviderError(f"openai error {e.status_code}: {e}", retryable=e.status_code >= 500)

        calls, raw_out = [], []
        for item in resp.output:
            d = item.model_dump(exclude_none=True)
            if item.type == "function_call":
                try:
                    args = json.loads(item.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}
                calls.append(ToolCall(id=item.call_id, name=item.name, arguments=args))
                raw_out.append({"type": "function_call", "call_id": item.call_id, "name": item.name, "arguments": item.arguments})
            elif item.type == "message":
                raw_out.append({"role": "assistant", "content": resp.output_text})
            elif item.type == "reasoning":
                raw_out.append(d)
        text = resp.output_text or ""
        parsed = None
        if req.json_schema and text:
            try:
                parsed = json.loads(text)
            except json.JSONDecodeError:
                parsed = None
        u = resp.usage
        cached = getattr(getattr(u, "input_tokens_details", None), "cached_tokens", 0) or 0
        return LLMResponse(text=text, model=resp.model, provider="openai", tool_calls=calls, parsed=parsed,
                           input_tokens=u.input_tokens if u else 0, output_tokens=u.output_tokens if u else 0, cached_tokens=cached,
                           stop_reason="tool_use" if calls else "end_turn", raw_assistant={"provider": "openai", "output": raw_out})
