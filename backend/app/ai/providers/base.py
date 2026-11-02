"""Provider-neutral request/response types. New providers implement `LLMProvider.complete`."""
from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict  # JSON schema (object, additionalProperties: false)


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class ChatMessage:
    role: str  # user | assistant | tool
    content: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    tool_call_id: str | None = None
    tool_name: str | None = None
    is_error: bool = False
    # Opaque provider-native content (e.g. Anthropic thinking blocks) replayed unchanged to the same provider.
    raw: dict | None = None


@dataclass
class LLMRequest:
    messages: list[ChatMessage]
    system: str = ""
    max_tokens: int = 2048
    tools: list[ToolSpec] = field(default_factory=list)
    json_schema: dict | None = None  # structured output
    temperature: float | None = None  # honoured only where the provider/model supports it
    effort: str | None = None
    task_type: str = "chat"
    metadata: dict = field(default_factory=dict)  # demo-provider hints (e.g. context chunks)


@dataclass
class LLMResponse:
    text: str
    model: str
    provider: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    parsed: Any = None
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    stop_reason: str = "end_turn"
    raw_assistant: dict | None = None
    demo: bool = False
    refusal: bool = False


class ProviderError(Exception):
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class LLMProvider(Protocol):
    name: str

    def available(self) -> bool: ...

    def complete(self, model: str, req: LLMRequest, timeout_s: float) -> LLMResponse: ...
