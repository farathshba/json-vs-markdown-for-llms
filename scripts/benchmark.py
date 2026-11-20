#!/usr/bin/env python3
"""
Benchmark: Markdown vs JSON as LLM context.

Two modes:

  python scripts/benchmark.py tokens      # deterministic, no API key needed
  python scripts/benchmark.py recall     # needs MISTRAL_API_KEY in env

The `tokens` mode measures things that are objective and stable:
  - token count of each format (tiktoken o200k_base approximation)
  - bytes and chars
  - parse/round-trip reliability of naive structured extraction:
      * from JSON: json.loads (exact)
      * from Markdown: regex extraction (typical of what tooling must do)

The `recall` mode runs the identical Q&A set (prompts/qa_set.json) against
each format as context, with the same model and temperature 0, and scores
exact / contains / numeric-normalized recall. It is the part of the
comparison that is model-dependent, so results are emitted per model.
"""

import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_MD = ROOT / "data" / "sample.md"
DATA_JSON = ROOT / "data" / "sample.json"
QA = ROOT / "prompts" / "qa_set.json"
RESULTS = ROOT / "results"


# ---------------------------------------------------------------- tokens ---

def count_tokens(text: str) -> int:
    try:
        import tiktoken
        enc = tiktoken.get_encoding("o200k_base")
        return len(enc.encode(text))
    except Exception:
        # crude fallback: ~4 chars/token for english-ish text
        return max(1, len(text) // 4)


def collect_numbers(obj, out=None):
    if out is None:
        out = []
    if isinstance(obj, dict):
        for v in obj.values():
            collect_numbers(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_numbers(v, out)
    else:
        # bool is a subclass of int in Python; exclude it.
        if isinstance(obj, bool):
            pass
        elif isinstance(obj, (int, float)):
            out.append(obj)
    return out


def metrics_mode():
    md = DATA_MD.read_text()
    js_text = DATA_JSON.read_text()

    # JSON reliability: does it parse, and can a trivial program extract
    # the numeric rules without any LLM?  (simulate downstream tooling)
    parse = {}
    try:
        data = json.loads(js_text)
        parse["json_parse_ok"] = True
        nums = collect_numbers(data)
        parse["numbers_recoverable_without_llm"] = sorted(set(nums))
        # spot-check a business rule
        ttl = data["sections"]["tool_level_authorization"]["requirements"]
        ttl_rule = next(r for r in ttl if r["rule"] == "ephemeral_credentials")
        m = re.search(r"(\d+)", ttl_rule["detail"])
        parse["rule_ttl_seconds_recovered"] = m.group(1)
    except Exception as e:
        parse["json_parse_ok"] = False
        parse["error"] = repr(e)

    # Markdown reliability: same information, recovered with the same
    # triviality of tooling (regex), as a downstream tool would have to.
    md_parse = {}
    m = re.search(r"maximum TTL (\d+) seconds", md)
    md_parse["rule_ttl_seconds_recovered"] = m.group(1) if m else None
    m = re.search(r"maximum CVSS of (\S+)", md)
    md_parse["rule_max_cvss_recovered"] = m.group(1) if m else None
    # heading ambiguity: how many distinct H2 sections, machine-detectable?
    md_parse["h2_sections"] = re.findall(r"^## (.+)$", md, re.M)
    # trailing-comma / typo tolerance test is by nature JSON-only to fail;
    # here we just note the coupling between field names and data.
    md_parse["machine_readable_key_names"] = []  # none; regex per-rule needed

    out = {
        "bytes": {"markdown": len(md.encode()), "json": len(js_text.encode())},
        "chars": {"markdown": len(md), "json": len(js_text)},
        "tokens_o200k": {"markdown": count_tokens(md), "json": count_tokens(js_text)},
        "tool_downstream_extraction": {
            "json": {"method": "json.loads + key path", "result": parse},
            "markdown": {"method": "argv-by-regex, one regex per rule", "result": md_parse},
        },
    }
    t_md, t_js = out["tokens_o200k"]["markdown"], out["tokens_o200k"]["json"]
    out["token_overhead_json_vs_md_pct"] = round((t_js - t_md) / t_md * 100, 1)
    out["bytes_overhead_json_vs_md_pct"] = round(
        (out["bytes"]["json"] - out["bytes"]["markdown"]) / out["bytes"]["markdown"] * 100, 1
    )
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "metrics.json").write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
    print(f"\nWrote {RESULTS / 'metrics.json'}")


# ---------------------------------------------------------------- recall ---

SYSTEM = (
    "You are answering questions STRICTLY from the provided context document. "
    "Answer in as few words as possible. If the context does not contain the "
    "answer, reply only: NOT_IN_CONTEXT."
)


def normalize(s: str) -> str:
    s = s.lower().strip()
    s = re.sub(r"[\.,;:!?\"]", "", s)
    s = re.sub(r"\b(the|a|an|is|are|and|of|to|for|in)\b", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def score(answer: str, truth: str) -> str:
    a, t = normalize(answer), normalize(truth)
    if a == t:
        return "exact"
    if t in a or a in t:
        return "contains"
    return "wrong"


def recall_mode(model="mistral-small-latest"):
    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        sys.exit("Set MISTRAL_API_KEY to run recall mode.")
    from mistralai import Mistral
    client = Mistral(api_key=api_key)

    contexts = {
        "markdown": DATA_MD.read_text(),
        "json": DATA_JSON.read_text(),
    }
    qs = json.loads(QA.read_text())["questions"]
    results = {}
    for fmt, ctx in contexts.items():
        per_q = []
        for q in qs:
            resp = client.chat.complete(
                model=model,
                messages=[
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": f"CONTEXT:\n{ctx}\n\nQUESTION: {q['question']}"},
                ],
                temperature=0.0,
                max_tokens=120,
            )
            ans = resp.choices[0].message.content.strip()
            per_q.append({
                "id": q["id"], "question": q["question"],
                "truth": q["answer"], "model_answer": ans,
                "score": score(ans, q["answer"]),
            })
        exact = sum(1 for r in per_q if r["score"] == "exact")
        contains = sum(1 for r in per_q if r["score"] == "contains")
        results[fmt] = {
            "model": model, "n": len(per_q),
            "exact": exact, "exact_pct": round(100 * exact / len(per_q), 1),
            "contains": contains,
            "wrong": len(per_q) - exact - contains,
            "per_question": per_q,
        }
    RESULTS.mkdir(exist_ok=True)
    path = RESULTS / "recall.json"
    path.write_text(json.dumps(results, indent=2))
    for fmt, r in results.items():
        print(f"{fmt:9s} exact {r['exact']}/{r['n']} ({r['exact_pct']}%)  contains {r['contains']}  wrong {r['wrong']}")
    print(f"\nWrote {path}")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "tokens"
    if mode == "tokens":
        metrics_mode()
    elif mode == "recall":
        model = sys.argv[2] if len(sys.argv) > 2 else "mistral-small-latest"
        recall_mode(model)
    else:
        sys.exit("Usage: benchmark.py [tokens|recall] [model]")
