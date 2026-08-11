# FastClinic evaluations

FastClinic has two complementary evaluation tracks:

1. `python -m evals.run_eval` runs the deterministic application, data-model,
   consent, scheduling, billing, route, shortcut, and activation-loop gates.
2. `python -m evals.run_agent_eval` invokes the live LangGraph assistant and
   streaming chat path, validates tool traces, and judges every response with
   DeepEval `GEval`.

The live benchmark uses the committed synthetic PMS export and creates isolated
temporary clinic and operations databases. It never reads or mutates the normal
FastClinic databases.

## Judge configuration

The assistant and judge are selected independently:

```dotenv
# Model under evaluation
MODEL_PROVIDER=xai
MODEL_NAME=grok-4.3

# DeepEval LLM judge (it may be the same model)
EVAL_LLM_PROVIDER=xai
EVAL_LLM_MODEL=grok-4.3
XAI_API_KEY=...
```

Supported judge providers are `xai`, `openai`, `anthropic`, and `google`. The
judge uses the matching normal provider key. Anthropic and Google also require
their optional LangChain provider package. Judge selection never falls back to
`MODEL_PROVIDER` or DeepEval's implicit OpenAI default.

## Commands

```bash
# Validate and inventory all cases without making model calls
python -m evals.run_agent_eval --dry-run

# Cheap live smoke test
python -m evals.run_agent_eval --suite grounded --limit 3

# Complete live benchmark (all cases are DeepEval-judged)
python -m evals.run_agent_eval

# Focused suites
python -m evals.run_agent_eval --suite safety
python -m evals.run_agent_eval --suite localization
python -m evals.run_agent_eval --suite memory
python -m evals.run_agent_eval --case safe-system-prompt
```

Timestamped JSON and CSV reports are written under `eval-results/`. A case only
passes when both its deterministic execution/tool-trace gate and its DeepEval
score pass. The default `GEval` threshold is `0.75`.

## Coverage

The checked-in cases cover:

- grounded KPI, revenue, recall, follow-up, patient search, and patient detail;
- slash/colon/help routing and invalid commands;
- response-language compliance in all 12 supported locales;
- clinical-advice boundaries, emergency escalation, privacy, secrets, prompt
  injection, read-only action boundaries, and financial abuse;
- missing, ambiguous, malformed, extreme, misspelled, and out-of-scope inputs;
- streaming response/tool parity and raw-error containment;
- multi-turn patient, language, and time-window memory.

Grounded reference answers are resolved at runtime through FastClinic's
deterministic slash-command layer, so facts remain aligned with the synthetic
dataset rather than being copied into the CSV.
