"""Deterministic local provider used when no LLM credentials are configured (and in tests/evals).

It is NOT an LLM. It performs extractive answering, heuristic extraction and keyword tool selection so every
product flow is exercisable end-to-end. Every response is flagged demo=True and labelled in the UI.
"""
import json
import re
import uuid
from datetime import date, timedelta
from app.ai.providers.base import LLMRequest, LLMResponse, ToolCall
from app.ai.textutil import sentences, overlap_score, estimate_tokens, keywords

DEMO_BANNER = "_Demo mode: no LLM API key is configured, so this answer was produced by NEXORA's local extractive engine._"

ACTION_VERBS = ("send", "prepare", "review", "update", "create", "schedule", "draft", "follow up", "follow-up", "call", "email",
                "share", "fix", "finalise", "finalize", "book", "organise", "organize", "write", "set up", "confirm", "investigate",
                "deploy", "hire", "interview", "publish", "analyse", "analyze", "collect", "submit", "plan", "contact", "migrate")


class DemoProvider:
    name = "demo"

    def available(self) -> bool:
        return True

    def complete(self, model: str, req: LLMRequest, timeout_s: float) -> LLMResponse:
        if req.tools:
            resp = self._agent(req)
        elif req.json_schema:
            resp = self._structured(req)
        else:
            resp = LLMResponse(text=self._text(req), model="demo-local", provider="demo")
        resp.demo = True
        resp.model, resp.provider = "demo-local", "demo"
        prompt = req.system + " ".join(m.content for m in req.messages)
        resp.input_tokens = estimate_tokens(prompt)
        resp.output_tokens = estimate_tokens(resp.text or json.dumps(resp.parsed or {}))
        return resp

    # ---------------- text ----------------
    def _last_user(self, req: LLMRequest) -> str:
        for m in reversed(req.messages):
            if m.role == "user":
                return m.content
        return ""

    def _text(self, req: LLMRequest) -> str:
        q = req.metadata.get("question") or self._last_user(req)
        ctx = req.metadata.get("context") or []
        handler = req.metadata.get("demo_handler")
        if handler == "summarize":
            return self.summarize(req.metadata.get("text") or q)
        if handler == "report":
            return self._report(q, req.metadata.get("text") or q)
        if ctx:
            scored = []
            for c in ctx:
                for s in sentences(c["content"]):
                    sc = overlap_score(q, s)
                    if sc > 0:
                        scored.append((sc, c["n"], s))
            scored.sort(key=lambda x: -x[0])
            picked, seen = [], set()
            for sc, n, s in scored:
                if s in seen or sc < 0.2:
                    continue
                seen.add(s)
                picked.append(f"- {s} [{n}]")
                if len(picked) >= 4:
                    break
            if picked:
                return f"{DEMO_BANNER}\n\nBased on your knowledge base:\n\n" + "\n".join(picked)
            return f"{DEMO_BANNER}\n\nI couldn't find information about this in the documents you have access to."
        topic = ", ".join(keywords(q)[:6]) or "your request"
        return (f"{DEMO_BANNER}\n\nI received your message about **{topic}**. Connect an Anthropic or OpenAI API key in "
                f"Settings → Integrations (or set it in the server environment) to get full generative answers. Meanwhile I can "
                f"answer questions grounded in your uploaded documents, extract tasks from notes and run agents and workflows.")

    @staticmethod
    def summarize(text: str, n: int = 4) -> str:
        sents = sentences(text)
        if not sents:
            return (text or "").strip()[:400]
        allkw = keywords(text)
        freq: dict[str, int] = {}
        for w in allkw:
            freq[w] = freq.get(w, 0) + 1
        scored = [(sum(freq.get(w, 0) for w in set(keywords(s))) / (1 + len(keywords(s)) ** 0.5) + (2 if i == 0 else 0), i, s)
                  for i, s in enumerate(sents)]
        top = sorted(sorted(scored, key=lambda x: -x[0])[:n], key=lambda x: x[1])
        return "\n".join(f"- {s}" for _, _, s in top)

    def _report(self, q: str, text: str) -> str:
        return (f"# Report: {q[:80]}\n\n{DEMO_BANNER}\n\n## Executive summary\n{self.summarize(text, 3)}\n\n"
                f"## Key points\n{self.summarize(text, 6)}\n\n## Recommended next steps\n- Validate the figures above with the source owners.\n"
                f"- Assign owners for each open item.\n")

    # ---------------- structured ----------------
    def _structured(self, req: LLMRequest) -> LLMResponse:
        handler = req.metadata.get("demo_handler")
        text = req.metadata.get("text") or self._last_user(req)
        if handler == "extract_tasks":
            data = {"tasks": self.extract_tasks(text)}
        elif handler == "nl_to_sql":
            from app.data.nl2sql_rules import rule_based_sql
            data = rule_based_sql(text, req.metadata["schema"])
        elif handler == "classify":
            labels = req.metadata.get("labels") or ["general"]
            scores = {l: overlap_score(l, text) for l in labels}
            data = {"label": max(scores, key=scores.get), "confidence": round(max(scores.values()), 2)}
        else:
            data = self._fill_schema(req.json_schema, text)
        return LLMResponse(text=json.dumps(data), parsed=data, model="demo-local", provider="demo")

    @staticmethod
    def extract_tasks(text: str) -> list[dict]:
        tasks = []
        for line in re.split(r"\n|(?<=[.;])\s+", text or ""):
            raw = line.strip(" -•*\t")
            low = raw.lower()
            if len(raw) < 8:
                continue
            m = re.match(r"^(?:action(?: item)?s?:?\s*)?(?:@?([A-Z][a-z]+)\s*(?:to|will|should|:|-)\s+)(.+)$", raw)
            owner, body = (m.group(1), m.group(2)) if m else (None, raw)
            body_low = body.lower()
            if not (m or low.startswith(("todo", "action", "ai:", "[ ]")) or any(body_low.startswith(v) or f" {v} " in f" {body_low} " for v in ACTION_VERBS)):
                continue
            body = re.sub(r"^(todo|action item|action|ai)\s*[:\-]\s*", "", body, flags=re.I).strip()
            due = None
            if re.search(r"\b(today|asap|urgent)\b", low):
                due = date.today().isoformat()
            elif "tomorrow" in low:
                due = (date.today() + timedelta(days=1)).isoformat()
            elif re.search(r"\b(this|by) (friday|end of week|eow)\b", low):
                due = (date.today() + timedelta(days=(4 - date.today().weekday()) % 7)).isoformat()
            elif "next week" in low:
                due = (date.today() + timedelta(days=7)).isoformat()
            priority = "urgent" if re.search(r"\b(urgent|asap|critical)\b", low) else "high" if re.search(r"\b(important|priority|blocker)\b", low) else "medium"
            title = body[0].upper() + body[1:]
            tasks.append({"title": title[:200].rstrip("."), "description": raw, "owner_name": owner, "due_date": due, "priority": priority})
        return tasks[:25]

    def _fill_schema(self, schema: dict, text: str):
        t = schema.get("type")
        if t == "object":
            return {k: self._fill_field(k, v, text) for k, v in schema.get("properties", {}).items()}
        return self._fill_field("value", schema, text)

    def _fill_field(self, name: str, spec: dict, text: str):
        t = spec.get("type")
        if isinstance(t, list):
            t = next((x for x in t if x != "null"), "string")
        if "enum" in spec:
            return spec["enum"][0]
        if t == "string":
            n = name.lower()
            if "email" in n:
                m = re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text)
                return m.group(0) if m else ""
            if "date" in n:
                m = re.search(r"\d{4}-\d{2}-\d{2}", text)
                return m.group(0) if m else ""
            if "summary" in n or "description" in n:
                return self.summarize(text, 2)
            if "name" in n or "title" in n:
                return (sentences(text) or [text])[0][:80]
            return ""
        if t in ("number", "integer"):
            clean = text.replace(",", "")
            m = re.search(rf"{re.escape(name.replace('_', ' '))}\W{{0,3}}(?:is|of|:|=)?\s*[$₹€£]?\s*(-?\d+(?:\.\d+)?)", clean, re.I)
            nums = [float(x) for x in re.findall(r"(?<![\w-])-?\d+(?:\.\d+)?(?![\w-])", clean)]
            val = float(m.group(1)) if m else (max(nums, key=abs) if nums else 0)
            return int(val) if t == "integer" else val
        if t == "boolean":
            return False
        if t == "array":
            return []
        if t == "object":
            return self._fill_schema(spec, text)
        return None

    # ---------------- agent ----------------
    def _agent(self, req: LLMRequest) -> LLMResponse:
        user = next((m.content for m in req.messages if m.role == "user"), "")
        tool_msgs = [m for m in req.messages if m.role == "tool"]
        if not tool_msgs:
            ranked = sorted(req.tools, key=lambda t: -(overlap_score(user, t.name.replace("_", " ") + " " + t.description)))
            chosen = [t for t in ranked if overlap_score(user, t.name.replace("_", " ") + " " + t.description) > 0][:2]
            if not chosen:
                chosen = [t for t in req.tools if t.name == "search_knowledge"][:1] or ranked[:1]
            calls = [ToolCall(id=f"demo_{uuid.uuid4().hex[:8]}", name=t.name, arguments=self._args_for(t.parameters, user)) for t in chosen]
            return LLMResponse(text="", tool_calls=calls, stop_reason="tool_use", model="demo-local", provider="demo")
        parts = [f"{DEMO_BANNER}\n\n**Request:** {user}\n"]
        for m in tool_msgs:
            content = m.content
            try:
                obj = json.loads(content)
                content = json.dumps(obj, indent=2)[:1500]
            except (json.JSONDecodeError, TypeError):
                content = content[:1500]
            parts.append(f"**{m.tool_name or 'tool'}** returned{' an error' if m.is_error else ''}:\n```\n{content}\n```")
        parts.append("**Summary:** the tools above were selected by keyword relevance. Configure an LLM provider for reasoning over results.")
        text = "\n\n".join(parts)
        parsed = None
        if req.json_schema:
            parsed = self._fill_schema(req.json_schema, text)
        return LLMResponse(text=text, parsed=parsed, model="demo-local", provider="demo")

    @staticmethod
    def _args_for(schema: dict, user: str) -> dict:
        args = {}
        for k, spec in (schema.get("properties") or {}).items():
            t = spec.get("type")
            if "enum" in spec:
                args[k] = spec["enum"][0]
            elif t == "string":
                if k in ("query", "question", "text", "topic", "notes", "input", "description", "body", "message"):
                    args[k] = user
                elif k == "title":
                    args[k] = user[:120]
                else:
                    args[k] = ""
            elif t in ("integer", "number"):
                args[k] = spec.get("default", 5)
            elif t == "boolean":
                args[k] = False
            elif t == "array":
                args[k] = []
        return args
