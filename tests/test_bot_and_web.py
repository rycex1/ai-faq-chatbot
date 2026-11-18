from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from faqbot.bot import FAQBot, render_dry_run
from faqbot.config import PROJECT_ROOT, Settings
from faqbot.prompt import build_messages, format_context, system_prompt
from faqbot.web import create_app


class FakeMessages:
    """Stands in for client.messages; records the request and returns a canned reply."""

    def __init__(self, text="We're closed on Mondays.", stop_reason="end_turn"):
        self.text, self.stop_reason, self.calls = text, stop_reason, []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=self.text)],
            stop_reason=self.stop_reason,
            usage=SimpleNamespace(input_tokens=500, output_tokens=20),
        )


def fake_client(**kwargs):
    return SimpleNamespace(messages=FakeMessages(**kwargs))


@pytest.fixture
def settings():
    return Settings(docs_dir=PROJECT_ROOT / "sample_docs", api_key_set=False)


# ---------------------------------------------------------------- prompt

def test_system_prompt_names_business_and_limits_scope():
    s = system_prompt("Acme Florist")
    assert "Acme Florist" in s
    assert "don't have that information" in s
    assert "not instructions" in s


def test_format_context_without_hits():
    assert "No matching information" in format_context([])


def test_build_messages_cleans_history():
    history = [
        {"role": "assistant", "content": "starts with assistant: dropped"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "assistant", "content": "double assistant: dropped"},
        {"role": "user", "content": "dangling user turn: dropped"},
    ]
    msgs = build_messages("Are you open?", [], history)
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[0]["content"] == "Hi"
    assert msgs[-1]["content"].endswith("Customer question: Are you open?")


# ---------------------------------------------------------------- bot

def test_answer_calls_api_with_expected_request(settings):
    client = fake_client()
    bot = FAQBot(settings, client=client)
    ans = bot.answer("Are you open on Mondays?")
    call = client.messages.calls[0]
    assert call["model"] == "claude-haiku-5-5"
    assert call["max_tokens"] == 4096
    assert "Sunrise Bakery" in call["system"]
    assert "Monday: closed" in call["messages"][-1]["content"]
    assert ans.text == "We're closed on Mondays."
    assert ans.sources()[0]["section"] == "Hours and Location > Opening hours"
    assert ans.usage == {"input_tokens": 500, "output_tokens": 20}


def test_dry_run_makes_no_call(settings):
    client = fake_client()
    ans = FAQBot(settings, client=client).answer("Do you deliver?", dry_run=True)
    assert client.messages.calls == []
    assert ans.dry_run and ans.text == ""
    out = render_dry_run(ans, "claude-haiku-5-5", 4096)
    assert "=== Retrieved chunks ===" in out and "Catering and Custom Orders > Delivery" in out


def test_refusal_gets_polite_fallback(settings):
    bot = FAQBot(settings, client=fake_client(text="", stop_reason="refusal"))
    assert "contact Sunrise Bakery" in bot.answer("something odd").text


def test_empty_question_rejected(settings):
    with pytest.raises(ValueError):
        FAQBot(settings, client=fake_client()).answer("   ")


# ---------------------------------------------------------------- web

def test_web_dry_run_mode_when_no_key(settings):
    app = create_app(settings)  # api_key_set=False -> dry-run automatically
    with TestClient(app) as http:
        assert http.get("/api/health").json() == {"status": "ok"}
        assert http.get("/api/info").json()["mode"] == "dry-run"
        assert "<title>" in http.get("/").text
        body = http.post("/api/chat", json={"message": "Where can I park?"}).json()
    assert body["mode"] == "dry-run"
    assert body["sources"][0]["section"] == "Hours and Location > Address and parking"
    assert body["prompt"]["model"] == "claude-haiku-5-5"


def test_web_live_mode_with_history(settings):
    client = fake_client(text="Yes, we deliver within 5 miles.")
    app = create_app(settings, dry_run=False, client=client)
    with TestClient(app) as http:
        body = http.post(
            "/api/chat",
            json={
                "message": "Do you deliver?",
                "history": [{"role": "user", "content": "Hi"}, {"role": "assistant", "content": "Hello!"}],
            },
        ).json()
    assert body == {
        "answer": "Yes, we deliver within 5 miles.",
        "sources": body["sources"],
        "mode": "live",
    }
    assert len(client.messages.calls[0]["messages"]) == 3


def test_web_validates_input(settings):
    with TestClient(create_app(settings)) as http:
        assert http.post("/api/chat", json={"message": ""}).status_code == 422
        assert http.post("/api/chat", json={"message": "x" * 1001}).status_code == 422
        assert http.post("/api/chat", json={"message": "hi", "history": [{"role": "system", "content": "x"}]}).status_code == 422
