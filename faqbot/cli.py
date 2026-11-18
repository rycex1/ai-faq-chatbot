"""Command-line chat.

    python -m faqbot "Do you have gluten-free cakes?"
    python -m faqbot --dry-run "When are you open on Sunday?"
    python -m faqbot                      # interactive session
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from .bot import AnswerError, FAQBot, render_dry_run
from .config import Settings


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="faqbot", description="Answer customer questions from a folder of business documents.")
    p.add_argument("question", nargs="*", help="question to ask (omit for an interactive session)")
    p.add_argument("--dry-run", action="store_true", help="no API call: show the retrieved chunks and the exact prompt")
    p.add_argument("--docs", type=Path, help="documents folder (default: FAQBOT_DOCS_DIR or sample_docs/)")
    p.add_argument("--top-k", type=int, help="number of chunks to retrieve (default: 4)")
    p.add_argument("--sources", action="store_true", help="print which document sections were used")
    p.add_argument("-v", "--verbose", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    if args.docs:
        settings.docs_dir = args.docs.resolve()
    if args.top_k:
        settings.top_k = args.top_k
    if not args.dry_run and not settings.api_key_set:
        print("ANTHROPIC_API_KEY is not set. Add it to .env, or run with --dry-run to see retrieval and the prompt without a key.",
              file=sys.stderr)
        return 2
    try:
        bot = FAQBot(settings)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 2

    def ask(question: str, history: list[dict]) -> str | None:
        try:
            ans = bot.answer(question, history=history, dry_run=args.dry_run)
        except AnswerError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return None
        if args.dry_run:
            print(render_dry_run(ans, settings.model, settings.max_tokens))
            return None
        print(ans.text)
        if args.sources:
            for s in ans.sources():
                print(f"  - {s['section']} ({s['source']})")
        return ans.text

    if args.question:
        ask(" ".join(args.question), [])
        return 0

    print(f"{settings.business_name} assistant. Ask a question, or press Enter on an empty line to quit.")
    history: list[dict] = []
    while True:
        try:
            question = input("\nYou: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            break
        print("Bot: ", end="", flush=True)
        reply = ask(question, history)
        if reply:
            history += [{"role": "user", "content": question}, {"role": "assistant", "content": reply}]
    return 0


if __name__ == "__main__":
    sys.exit(main())
