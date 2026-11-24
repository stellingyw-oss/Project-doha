# First sprint — v0.1.2: trustworthy recording and saving

Scope: fix foundational safety and truthful UX, not production AI generation. Keep the current design. Inspect current source and test results; the earlier review of v0.1.1 is a starting point, not proof of the latest state.

## P0 implementation tasks
1. Inspect microphone/MediaRecorder lifecycle, stop completion, late callbacks and repeated recording. Make session-specific buffers, preserve ordered segments and original audio; never bind late events to another story. Handle errors and pending permission. Stop tracks when leaving; avoid fake waveforms.
2. Inspect IndexedDB and fallback behavior. Ensure recording and metadata are committed consistently; expose failures and retain recovery/export. Never claim full success if audio is missing. Prevent migration loss; guard concurrent save/open/delete and stale callbacks. Preserve old records.
3. Add per-record original audio download (all segments), metadata/transcript export, independent replay and deletion with confirmation. Verify reloading, multiple records and delete isolation. Clearly warn that local-only records can be lost on browser data deletion. Exports must not upload anything.
4. Remove forced initial dinosaur scene in actual recording mode. Start from a neutral screen. Clearly label canned scene visuals and filter-based styles as demo-only; preserve sample access separately. Do not claim free-form AI imagery or automated speech transcription before implementation.
5. Remove unsupported observation claims. Base observations on real input, not sample images, inferred psychology or fabricated events. Use generic open questions if evidence is insufficient.
6. Add tests for all acceptance criteria in AGENTS.md. If a behavior cannot be tested, report why and mark it unverified. Record actual browser/device coverage.

## Out of scope
External speech/image/video API integration, cloud storage, authentication, clinical analysis, paid services, production deployment, and history rewriting. These require separate design/approval. If implementation would require a larger migration or data loss risk, stop that change and document options.

## Deliverables
Branch with scoped changes, test results, migration/recovery notes, and a draft PR. No merge into main or deployment yet. Korean report: actual implementation, tests run, failed/not run, remaining risks, iPad/Safari verification plan. No real child data in the PR or screenshots.
