"""FAQBot: retrieve relevant chunks, then ask Claude to answer from them."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from .chunking import chunk_folder
from .config import Settings
from .prompt import build_messages, system_prompt
from .retrieval import BM25Index, Hit

log = logging.getLogger(__name__)


class AnswerError(RuntimeError):
    """The model call failed; the message is safe to show to an end user or operator."""


@dataclass
class Answer:
    text: str
    hits: list[Hit]
    system: str
    messages: list[dict]
    dry_run: bool = False
    usage: dict = field(default_factory=dict)

    def sources(self) -> list[dict]:
        seen, out = set(), []
        for h in self.hits:
            key = (h.chunk.source, h.chunk.heading)
            if key not in seen:
                seen.add(key)
                out.append({"source": h.chunk.source, "section": h.chunk.label(), "score": round(h.score, 2)})
        return out


class FAQBot:
    def __init__(self, settings: Settings, client=None):
        self.settings = settings
        self.chunks = chunk_folder(settings.docs_dir, settings.chunk_chars)
        self.index = BM25Index(self.chunks)
        self._client = client
        log.info("Indexed %d chunks from %s", len(self.chunks), settings.docs_dir)

    @property
    def client(self):
        if self._client is None:
            import anthropic

            self._client = anthropic.Anthropic()
        return self._client

    def retrieve(self, question: str) -> list[Hit]:
        return self.index.search(question, top_k=self.settings.top_k)

    def answer(self, question: str, history: list[dict] | None = None, dry_run: bool = False) -> Answer:
        question = question.strip()
        if not question:
            raise ValueError("Question is empty")
        hits = self.retrieve(question)
        system = system_prompt(self.settings.business_name)
        messages = build_messages(question, hits, history)
        if dry_run:
            return Answer(text="", hits=hits, system=system, messages=messages, dry_run=True)

        import anthropic

        try:
            response = self.client.messages.create(
                model=self.settings.model,
                max_tokens=self.settings.max_tokens,
                system=system,
                messages=messages,
            )
        except anthropic.AuthenticationError as exc:
            raise AnswerError("The Anthropic API key was rejected. Check ANTHROPIC_API_KEY.") from exc
        except anthropic.NotFoundError as exc:
            raise AnswerError(f"Model '{self.settings.model}' was not found. Check FAQBOT_MODEL.") from exc
        except anthropic.RateLimitError as exc:
            raise AnswerError("Too many requests right now. Please try again in a moment.") from exc
        except anthropic.APIConnectionError as exc:
            raise AnswerError("Couldn't reach the AI service. Please try again.") from exc
        except anthropic.APIStatusError as exc:
            raise AnswerError(f"The AI service returned an error ({exc.status_code}). Please try again.") from exc
        except TypeError as exc:  # raised by the SDK when no credentials are configured at all
            raise AnswerError("No Anthropic API key configured. Set ANTHROPIC_API_KEY or use dry-run mode.") from exc

        text = "".join(block.text for block in response.content if block.type == "text").strip()
        if response.stop_reason == "refusal" or not text:
            text = f"Sorry, I can't help with that here. Please contact {self.settings.business_name} directly."
        elif response.stop_reason == "max_tokens":
            log.warning("Answer hit max_tokens (%d); consider raising FAQBOT_MAX_TOKENS", self.settings.max_tokens)
        usage = {"input_tokens": response.usage.input_tokens, "output_tokens": response.usage.output_tokens}
        return Answer(text=text, hits=hits, system=system, messages=messages, usage=usage)


def render_dry_run(answer: Answer, model: str, max_tokens: int) -> str:
    """Human-readable view of what would be sent to the API."""
    lines = ["=== Retrieved chunks ==="]
    if not answer.hits:
        lines.append("(none matched)")
    for i, h in enumerate(answer.hits, 1):
        lines.append(f"[{i}] {h.chunk.source} | {h.chunk.label()} | score {h.score:.2f}")
    lines += [
        "",
        f"=== Request that would be sent (model={model}, max_tokens={max_tokens}) ===",
        "--- system ---",
        answer.system,
    ]
    for m in answer.messages:
        lines += [f"--- {m['role']} ---", m["content"]]
    return "\n".join(lines)
