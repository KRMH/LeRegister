- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-understand-a-new-command-or-say-why-not.md`
  summary: A near-4096-character `New` message can make the echo or rejection reply exceed Telegram's 4096-char limit, so `reply_text` fails and the Owner gets no answer.
  evidence: Edge Case Hunter; reply embeds the user-typed name. The single renderer that splits at 4096 chars belongs to the outbox work in Story 1.3/1.5; a name length cap would be a new rule the Owner should decide.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-2-understand-a-new-command-or-say-why-not.md`
  summary: Edited-message updates and non-text updates (photos, stickers) are handled like new text and get a "Could not understand" reply.
  evidence: Edge Case Hunter; epic context assigns edited-message handling (reply telling the Owner to send a Change command) to Story 1.3.
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-journal-protect-and-de-duplicate-every-command.md`
  summary: An outbox row that always fails (unknown kind, a chat Telegram permanently refuses) is retried every 5 minutes forever, with no maximum attempts or failed state.
  evidence: Verification Gap and Edge Case Hunter; the story AC requires a row to stay pending until it succeeds, so a cap or a `failed` status needs an Owner decision (Story 1.5 hardens the reply path).
- source_spec: `_bmad-output/implementation-artifacts/spec-1-3-journal-protect-and-de-duplicate-every-command.md`
  summary: If `record_command` raises (database locked, disk full), the Command is lost and the Owner gets no reply.
  evidence: Edge Case Hunter; the handler error hook only logs. Story 1.5 covers unexpected errors reaching the Owner.
