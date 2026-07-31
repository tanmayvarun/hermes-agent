# WhatsApp Evaluation Ladder

Status: design note

This ladder sequences WhatsApp tasks from low-risk perception to high-risk
actuation. The intent is to train the agent to read and synthesize message
content before it is trusted to perform forwarding or other irreversible
actions.

## Principle

- Start with message reading.
- Then learn source-message identification.
- Then learn content typing, scrolling, and backtracking.
- Only after that should the agent attempt forwarding.
- Contact rows and profile cards are gateways, not endpoints.
- Each prompt should be matched to the best declarative procedure, and the
  active procedure stage should guide which surface the agent treats as the
  next plausible move.
- For ambiguous or irreversible steps, the selector should reason with the LLM
  instead of relying on surface heuristics alone.

## Levels

### Level 1: chat identification

Goal: prove the agent can identify the current conversation.

Example prompts:

- `Open WhatsApp and tell me which chat is currently open.`
- `Open Kulvinder Ji and read the visible header.`
- `How many unread chats are visible on the list?`

Pass criteria:

- The agent reports the correct open chat or list state.
- It does not confuse navigation chrome with conversation content.

### Level 2: message reading

Goal: prove the agent can read the latest visible message content.

Example prompts:

- `Open Kulvinder Ji and read the latest visible message.`
- `What is the most recent message shown in this chat?`
- `Read the message immediately above the composer.`

Pass criteria:

- The agent reports message text from the conversation timeline.
- It does not answer from profile info or sidebar previews.

### Level 3: source-message finding

Goal: prove the agent can locate a named message or link in the thread.

Example prompts:

- `Find the message containing zarooratwala in Kulvinder Ji chat.`
- `Locate the link sent to Kulvinder Ji and tell me the domain.`
- `Find the message that mentions zarooratwala or zarooratwala.`

Pass criteria:

- The agent searches the conversation timeline first.
- It distinguishes text, link, media, and document content.

### Level 4: disambiguation and backtracking

Goal: prove the agent can recover from an ambiguous surface without leaving the source thread.

Example prompts:

- `If the first visible result is wrong, keep searching the source chat until the link is found.`
- `When the chat opens on a contact card, go back to the message timeline and continue.`
- `Find the zarooratwala link without using profile info as evidence.`

Pass criteria:

- The agent backtracks instead of thrashing on contact rows.
- It keeps the source conversation as the active world model.

### Level 5: controlled forwarding

Goal: prove the agent can forward a found message after it has been identified.

Example prompts:

- `Find the zarooratwala link sent to Kulvinder Ji on WhatsApp and forward it to Pallavi.`
- `Find the zarooratwala link in Kulvinder Ji chat and forward it to Pallavi.`
- `Forward the message containing zarooratwala to Pallavi after locating it.`

Pass criteria:

- The agent first identifies the source message.
- It then opens the forward flow and selects the destination.
- Irreversible forwarding choices must pass through the high-risk reasoning
  lane and confidence gate before they are executed.
- This is the canonical end-to-end regression for the WhatsApp forward-message
  procedure; the same structured goal should drive both UI prompt submit and
  live Terminal execution.

### Level 6: multi-hop recovery

Goal: prove the agent can survive overlays, search results, and false starts.

Example prompts:

- `Find the zarooratwala link sent to Kulvinder Ji and forward it to Pallavi even if an overlay appears.`
- `If the agent lands on a contact row, it should recover and continue from the source chat.`
- `Search the message thread, not the contact card, then forward the right result.`

Pass criteria:

- The agent can return to the source conversation after a wrong turn.
- It does not treat contact rows or avatars as proof of message discovery.

### Level 7: external-link forwarding

Goal: prove the agent can treat a non-WhatsApp link share as a source message
and forward it without getting distracted by profile chrome or side panels.

Example prompts:

- `Find the Google Maps share link of India Coffee House HSR Layout and share with Pallavi.`
- `Find the google maps share link of india coffee house hsr layout and forward it to Pallavi.`
- `Find the google share location of Godrej Nurture Electronic City Phase 1 and share with Pallavi on WhatsApp.`

Pass criteria:

- The agent first binds the source message/link from the chat timeline.
- It does not mistake info cards, media panels, or profile chrome for the source.
- It then proceeds through the same high-risk forwarding lane used by other
  irreversible share actions.

## Suggested training order

1. Level 1 until stable.
2. Level 2 until stable.
3. Level 3 with OCR enabled.
4. Level 4 with backtracking enabled.
5. Level 5 with irreversible-action confidence gating.
6. Level 6 only after the earlier levels are consistently passing.
7. Level 7 for externally sourced links such as Google Maps shares.

## Notes for future prompts

- Prefer prompts that mention the message content first and the destination
  second.
- Avoid using destination-forward prompts as the first evaluation of a new
  perception change.
- Use the same ladder for regression testing any new OCR engine, overlay rule,
  or selector change.
