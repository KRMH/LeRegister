- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-understand-a-new-command-or-say-why-not.md`
  summary: A near-4096-character `New` message can make the echo or rejection reply exceed Telegram's 4096-char limit, so `reply_text` fails and the Owner gets no answer.
  evidence: Edge Case Hunter; reply embeds the user-typed name. The single renderer that splits at 4096 chars belongs to the outbox work in Story 1.3/1.5; a name length cap would be a new rule the Owner should decide.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-understand-a-new-command-or-say-why-not.md`
  summary: Edited-message updates and non-text updates (photos, stickers) are handled like new text and get a "Could not understand" reply.
  evidence: Edge Case Hunter; epic context assigns edited-message handling (reply telling the Owner to send a Change command) to Story 1.3.
