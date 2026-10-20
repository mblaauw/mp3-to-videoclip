# Test suite: invariants, not a quota

This suite protects **paid work and content-bound approvals**. Consolidate it;
never amputate it to hit a test-count target.

| Invariant | Where |
|---|---|
| Journal before charge; no blind resubmission; recovery | `test_production.py`, `test_generation_concurrency.py` |
| Cumulative budget, unknown reservations, correction cycles | `test_budget.py`, `test_production_defaults.py` |
| Approval hashes, preview/proof binding, review verdicts | `test_workflow_v2.py`, `test_creative_production.py`, `test_quality_cli.py` |
| Input-hash currency; foreign-model alternatives | `test_production_defaults.py` |
| Immutable reference import, permissions, crop provenance | `test_workflow_v2.py` |
| Path containment and safe downloads | `test_providers.py`, `test_storage`-style cases |
| Graphics cache integrity and sparse track coverage | `test_graphics_cache.py` |
| Frame-exact timeline, pacing bounds, adaptive wiring | `test_timeline.py`, `test_adaptive_pacing.py`, `test_pacing_integration.py` |
| Render, camera paths, previews, branding | `test_render.py`, `test_camera_path.py`, `test_preview.py`, `test_branding.py` |
| Provider parsing and audio/listening/transcription | `test_providers.py`, `test_runware_*.py`, `test_music_*.py` |
| Legacy artifact/approval preservation | `test_creative_production.py`, `test_quality_cli.py` |
| Skill routing and stage references | `test_stage_skills.py` |

Rules for future changes:

- Delete a test only when another test asserts the **same behaviour** against the same code path, or when the code it targets no longer exists.
- Prefer internal loops over multiplied parametrisations when the assertion body is identical.
- Do not assert exact prose/order that a harmless edit would break; assert structure.
- Keep the pre-change archive (`backups/pre-consolidation/`) until the next green full run is committed.
