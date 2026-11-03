# Test suite: invariants, not a quota

This suite protects **paid work and content-bound approvals**. Consolidate it;
never amputate it to hit a test-count target.

| Invariant | Where |
|---|---|
| Journal before charge; no blind resubmission; recovery | `test_production.py`, `test_generation_concurrency.py` |
| Cumulative budget, unknown reservations, correction cycles | `test_budget.py`, `test_production_defaults.py` |
| Model spend in the cap, token limits, unknown never zero | `test_director_usage.py` |
| Approval hashes, preview/proof binding, review verdicts | `test_workflow_v2.py`, `test_creative_production.py`, `test_quality_cli.py` |
| Input-hash currency; foreign-model alternatives | `test_production_defaults.py` |
| Immutable reference import, permissions, crop provenance | `test_workflow_v2.py` |
| Path containment and safe downloads | `test_providers.py`, `test_storage`-style cases |
| Graphics composition and cache keys | `test_graphics.py`, `test_compact_graphics.py`, `legacy/test_graphics_compose.py` |
| Frame-exact timeline, pacing bounds, adaptive wiring | `test_timeline.py`, `test_adaptive_pacing.py`, `test_pacing_integration.py` |
| Render, motion, previews, branding | `test_render_service.py`, `test_chunk_render.py`, `test_remotion_adapter.py`, `test_motion_and_look.py`, `test_api_preview.py`, `test_branding.py` |
| Compiled prompt, integer-frame timing, Remotion request | `test_contract_golden.py` |
| Provider parsing and audio/listening/transcription | `test_providers.py`, `test_runware_*.py`, `test_music_*.py` |
| Legacy artifact/approval preservation | `test_creative_production.py`, `test_quality_cli.py` |
| Director prompts, roles and tools | `test_director_prompts.py`, `test_director_tools.py` |

Rules for future changes:

- Delete a test only when another test asserts the **same behaviour** against the same code path, or when the code it targets no longer exists.
- Prefer internal loops over multiplied parametrisations when the assertion body is identical.
- Do not assert exact prose/order that a harmless edit would break; assert structure.
- Keep the pre-change archive (`backups/pre-consolidation/`) until the next green full run is committed.
