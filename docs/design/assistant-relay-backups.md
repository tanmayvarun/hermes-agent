# Assistant Relay Backups

Hermes needs a first-class backup tier for cases where the primary LLM
providers are unavailable, underperforming, or return an answer that fails the
task-specific quality bar.

This is not a one-off “use ChatGPT in a browser” hack. It is a reusable
provider layer that can grow to include ChatGPT, Google-backed assistants, and
other login-protected chat surfaces, with the same lifecycle and visibility as
the rest of the runtime.

## Problem statement

The current system already knows how to:

- select models by task family
- manage provider auth state
- open cloud browser sessions
- surface onboarding and re-auth CTAs in the desktop UI

What is missing is a dedicated layer that treats browser-backed assistants as a
fallback transport for model access, not as a special case inside the computer
use loop.

The desired behavior is:

1. Try the configured primary model path first.
2. If the provider is down, times out, rate-limits, or the answer quality is
   below threshold, escalate to a relay provider.
3. Use a logged-in browser session for the relay provider.
4. Expose the auth and recovery path in the UI as explicit CTAs.
5. Keep the fallback provider list configurable and extensible.

## Core concept

Introduce an **assistant relay provider** abstraction.

An assistant relay provider is a browser-backed or externally managed chat
surface that can produce LLM answers for Hermes after the primary API path has
failed or been rejected by policy.

Examples:

- OpenAI ChatGPT web / OpenAI OAuth-backed surfaces
- Google-backed chat surfaces
- future providers with a login-protected interactive UI

This is intentionally broader than “computer use”:

- `computer_use` is the action/execution loop.
- `assistant relay` is the answer-source fallback loop.

Those two concerns must stay separate.

## Design goals

- Keep the relay provider list configurable.
- Preserve one-time login where possible.
- Support OAuth / PKCE / provider-specific auth flows first.
- Fall back to supervised browser-session auth only when the provider does not
  expose a better integration.
- Run relay sessions in the background without blocking the main UI.
- Surface every auth transition, consent prompt, captcha, MFA, and session
  failure in the desktop console as an explicit CTA.
- Never leak raw credentials into the model context.
- Never silently switch providers without recording why the fallback happened.

## Lifecycle

### 1. Provider discovery

Each relay provider registers a manifest with the runtime. The manifest should
declare:

- `id`
- `display_name`
- `auth_mode` (`oauth_pkce`, `oauth_device_code`, `browser_session`, or
  `provider_api`)
- `capabilities` (`chat`, `reasoning`, `web_chat`, `browser_ui`)
- `background_safe` (whether the provider can run without a visible foreground
  window)
- `requires_human_cta` (whether login/MFA/consent can interrupt the run)
- `risk_tier` (used for approval thresholds and fallback policy)
- `default_timeout_s`
- `max_context_policy` / `message_window_policy`

The provider manifest should live in the same catalog system that already
drives the desktop provider picker, so the UI and runtime stay in sync.

### 2. One-time auth

The auth flow should prefer:

1. OAuth / PKCE / device-code style auth
2. provider-approved session refresh
3. browser-session login only when the provider has no better machine flow

The authenticated state should be stored in the existing Hermes credential
store / OS-backed secure store, not in prompt context.

The relay provider should then be resumable without repeated logins unless the
provider actually revokes the session.

### 3. Background execution

Relay providers should execute in a separate worker process or isolated browser
session so the agent can continue other work while the fallback answer is being
retrieved.

The worker should:

- keep the browser session authenticated
- submit the user prompt
- wait for the answer
- stream status back to the UI
- emit recoverable CTAs when human input is required

The main runtime should only receive:

- provider state
- progress events
- final answer
- failure reason / retryability

It should not receive browser credentials or secret session material.

### 4. Fallback policy

Fallback should be explicit and bounded.

Suggested policy:

- Retry the primary API provider first.
- If the provider times out, rate-limits, or returns malformed output, try the
  next configured primary provider.
- If all configured model APIs fail or the prompt quality is still below the
  task threshold, escalate to a relay provider.
- If the relay provider also fails, surface a hard failure rather than silently
  inventing another path.

This keeps Hermes predictable while still giving it a powerful escape hatch.

### 5. UI CTAs

The desktop app should expose relay auth and recovery as first-class CTAs:

- `Sign in to ChatGPT`
- `Sign in to Google`
- `Resume relay session`
- `Approve browser consent`
- `Complete MFA`
- `Switch to next provider`
- `Retry with relay`

Relay sessions that are meant to stay out of the user's way should advertise
`background_safe: true` in their manifest so the UI can prefer background
workers and avoid unnecessary focus changes when the task does not need a
human confirmation step.

Those CTAs should appear in the same provider onboarding and session status
surfaces that already show API-key and OAuth provider state.

## Config shape

The relay list should be configurable, for example:

```yaml
assistant_relays:
  enabled: true
  fallback_order:
    - openai-codex
    - google-chat
    - gemini-web
  max_relay_wait_s: 180
  require_primary_failure: true
```

This keeps the system open-ended: the list can grow without code churn.

## Integration points in Hermes

The relay layer should reuse, not replace, the existing primitives:

- `hermes_cli/provider_catalog.py` for unified provider visibility
- `hermes_cli/auth_commands.py` for account setup and login state
- `hermes_cli/model_switch.py` for provider/model selection UI
- `agent/plugin_llm.py` for the primary model access path
- `agent/browser_provider.py` and `plugins/browser/*` for background browser
  execution
- `apps/desktop/src/components/onboarding/*` for provider CTAs and auth state
- `apps/desktop/src/app/settings/*` for provider management and recovery

## Important boundary

Relay providers are a **fallback transport**, not a replacement for the main
model selection policy.

Hermes should still prefer:

1. the best available direct model API for the task
2. the best available self-hosted model for the task
3. the relay provider only when the above paths are unavailable or underperform

That separation keeps the system fast when it can be, and resilient when it
must be.

## Next implementation steps

1. Add a relay-provider manifest registry.
2. Wire the UI to surface relay sign-in and retry CTAs.
3. Add a background worker for relay execution.
4. Teach the model router to escalate to relays after bounded primary failure.
5. Add evals for provider failure, quality rejection, login recovery, and
   background-session resumption.
6. Add replayable browser-relay evals that score multi-turn follow-up quality
   for ChatGPT/Google-backed browser conversations.
