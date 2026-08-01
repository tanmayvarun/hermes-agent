# Model Benchmarking Framework

Hermes needs a reusable way to compare cloud LLMs against the growing eval suite and learn which model is best for which subusecase.
It also needs a way to compare prompt shapes for the same model and the same
screen fixture, because prompt engineering can materially change accuracy and
latency even when the provider/model stays fixed.

## Goals

- Benchmark multiple model/provider pairs on the same cases.
- Keep the benchmark generic and data-driven.
- Produce routing guidance, not just a leaderboard.
- Make it easy to add new evals without changing the runner.
- Measure prompt-shape quality separately from model quality.
- Support atomic perception evals before full end-to-end task evals.

## Core Concepts

### Candidate spec

A candidate is a concrete model/provider route:

- `name`
- `provider`
- `model`
- `base_url`
- `api_key`
- `api_mode`
- `temperature`
- `timeout_s`
- `max_output_tokens`

### Benchmark case

Each case is a small classification or decision prompt with:

- `case_id`
- `subusecase`
- `risk_tier`
- `prompt`
- `choices`
- `gold_choice`

The built-in suite focuses on routing-relevant decisions:

- message relevance
- source-message reconstruction
- editable affordance gating
- irreversible-action gating
- backtrack strategy
- procedure stage selection
- perception structure quality
- temporal persistence / occlusion handling
- capability precision

## Scoring

Per model:

- accuracy
- average confidence
- median latency
- per-subusecase accuracy

Per prompt shape:

- JSON parseability / completeness
- target-selection accuracy on the same perception fixture
- median latency
- score deltas between compact, balanced, and rich prompt variants

For perception-specific evals, also report:

- object / surface detection recall
- relation accuracy
- capability precision
- object identity persistence
- transition classification accuracy
- calibration error

Per routing recommendation:

- best model for each subusecase
- runner-up model
- accuracy gap
- sample count
- note when the sample size is small or the race is close

## Output

The runner emits JSON so future routing code can consume it directly.

The report contains:

- suite metadata
- candidate specs
- per-case results
- per-model summaries
- per-subusecase routing recommendations

## How it should be used

1. Add or update cases in the suite.
2. Run the benchmark across candidate models.
3. Inspect the per-subusecase recommendations.
4. Feed the resulting ranking into the model-selection policy for the agent.
5. Run the perception prompt-shape benchmark before trimming the live prompt
   again; the balanced default should only move after it wins on the eval set.
6. Add atomic perception cases whenever a live failure reveals a new
   structure-level mistake.

The perception path uses the `HERMES_PERCEPTION_PROMPT_SHAPE` knob with three
supported variants:

- `compact`
- `balanced` (default)
- `rich`

The dedicated CLI command is:

```bash
python -m plugin perception-prompt-benchmark --ollama-base-url http://HOST:11434 --json
```

## Design rule

Keep the benchmark generic. App-specific knowledge belongs in the cases, not in the runner.
Prompt-shape changes should be benchmarked, not guessed.
