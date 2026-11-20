# Markdown vs JSON as LLM Context

A small, reproducible comparison of **Markdown** and **JSON** as the context format you hand to an LLM, built from a real-world artifact: a security policy for AI coding agents (`data/sample.md` vs `data/sample.json` — same information, both formats).

Question it answers: *when you feed documents, rules, and requirements to an LLM (as Ailtire-class platform, RAG pipelines, or agent context windows do), which format costs less, which recalls better, and which survives downstream tooling?*

## TL;DR

| Dimension | Winner | Measured |
|---|---|---|
| Token cost | **Markdown** | JSON costs **+29.9%** tokens for identical content (658 → 855, o200k_base) |
| Bytes | **Markdown** | JSON costs **+29.6%** bytes (2,638 → 3,420) |
| Downstream tooling | **JSON** | One `json.loads` recovers every rule by key path; Markdown needs a bespoke regex per rule |
| Parse/schema round-trip | **JSON** | Validated parse every time; Markdown has no equivalent guarantee |
| Human authorship & review | **Markdown** | Survives `git diff`, code review, and non-technical authors |
| LLM recall accuracy | model-dependent | Run `benchmark.py recall` with a `MISTRAL_API_KEY` to reproduce on your model (script included, 15-question ground-truth set) |

## The finding (why this is not "just use JSON")

1. **Tokens are not neutral.** The JSON serialization of the same policy costs ~30% more tokens. Over a 200k-token corpus of policies, requirements, and SOPs, that is a real context-window budget and, for paid inference, a real bill. Punctuation tokens (`"`, `{`, `,`) and repeated key names are pure overhead.

2. **Schema validity is the actual JSON win.** `results/metrics.json` shows a trivial `json.loads` + key-path read recover the credential-TTL rule (900s) with zero natural-language parsing. The identical extraction from Markdown needs a hand-written regex per rule — one regex per rule, forever, across every document type. If downstream consumers are programs, JSON is mandatory regardless of what the LLM prefers.

3. **But note the leak:** the JSON variant still buries decision values in prose strings (`"Maximum TTL 900 seconds"`). Auto-extractable types `[14]` count: only one number in the whole document is typed. JSON-by-itself doesn't make data machine-readable; **modeling** does. A well-modeled JSON (numbers as numbers, enums as enums) beats prose-in-braces by a wide margin; badly-modeled JSON is Markdown with punctuation tax.

4. **Recall is model-dependent, so it's a benchmark, not a claim.** The script ships a 15-question ground-truth set spanning both formats (`prompts/qa_set.json`) and scores exact / contains / wrong, at temperature 0. Run it yourself:

```bash
export MISTRAL_API_KEY=...
python scripts/benchmark.py recall mistral-small-latest
```

5. **Recommendation (what I tell teams):**
   - Human-authored context (policies, findings writeups, runbooks) → keep **Markdown**, index it, let the model read it.
   - Machine-consumed context (tool manifests, policy-as-code, findings interchange) → **well-modeled JSON** (typed values, enums, stable key names), validated by schema.
   - The hybrid case is the interesting one: author in Markdown for reviewers, **compile to modeled JSON** for agent/tool consumption. Treat Markdown as source code and JSON as a build artifact.

## Repo layout

```
data/sample.md        The same policy, as Markdown (658 tokens)
data/sample.json      The same policy, as JSON (855 tokens)
prompts/qa_set.json   15 ground-truth questions over both formats
scripts/benchmark.py  The benchmark (tokens | recall modes)
results/metrics.json  Output of `tokens` mode (reproducible now)
results/recall.json   Output of `recall` mode (generated when a key is present)
```

## Reproduce

```bash
python scripts/benchmark.py tokens     # deterministic metrics, no key needed
python scripts/benchmark.py recall     # needs MISTRAL_API_KEY
```

Python 3.9+. `recall` mode additionally needs `pip install mistralai`.

## A subtlety worth keeping

One more observation worth keeping: Markdown's `##` headings act as a free, line-indexed chunking scheme (see `h2_sections` in results), which pairs naturally with RAG split-by-heading. JSON has no such free chunking scheme — array order and nesting depth must stand in for it, and naive fixed-size chunking corrupts both.
