# Implementation Plan

[Overview]
Prepare and relaunch the frontend UI reliably by rebuilding assets, starting the development server, and documenting exact run commands and expected runtime behavior.

This implementation focuses on operational reliability rather than feature development. The project uses a Vite + React frontend and a FastAPI backend; the immediate objective is to ensure the UI can be rebuilt and relaunched cleanly in the current local environment.

The plan emphasizes deterministic command execution, handling common local blockers (port conflicts and dependency/network issues), and producing repeatable launch instructions. It also captures alignment between frontend API usage and backend CORS constraints so the UI can communicate with the backend after launch.

[Types]
No application type system changes are required.

No new interfaces, enums, or schema definitions will be introduced. Existing runtime data shapes remain unchanged:
- Frontend reads API response records with fields compatible with `mi`, `reading`, `record_date`, and `unit`.
- Frontend request payload for creating readings remains `{ household: string, amount: number }`.

[Files]
Only operational planning artifacts are added; application source files are not modified for this task.

Detailed breakdown:
- New files:
  - `implementation_plan.md`: execution plan for rebuilding and relaunching UI.
- Existing files to review (no code edits planned):
  - `frontend/package.json` (scripts: `build`, `dev`)
  - `frontend/.npmrc` (current local npm SSL behavior)
  - `frontend/src/App.jsx`, `frontend/src/api.js`
  - `backend/main.py` (CORS and API endpoints)
- No files deleted or moved.
- No configuration changes required unless environment/network failures persist.

[Functions]
No function-level code changes are required.

New functions: none.

Modified functions: none.

Removed functions: none.

[Classes]
No class-level changes are required.

New classes: none.

Modified classes: none.

Removed classes: none.

[Dependencies]
No dependency version changes are required for this task.

Use the existing frontend dependency graph as locked in `frontend/package-lock.json`. If installation fails due to registry policy/certificates, treat as environment blocker and surface remediation steps instead of mutating package versions.

[Testing]
Validation is operational and runtime-focused.

Validation strategy:
- Run `npm --prefix frontend run build` and confirm a successful Vite production build.
- Run `npm --prefix frontend run dev` and confirm server startup + local URL.
- Verify UI is reachable in browser and can fetch backend data from `/readings`.
- If port `5173` is occupied, accept Vite-assigned fallback port and report it.

[Implementation Order]
Execute environment-safe operational steps in sequence to minimize runtime conflicts.

1. Confirm frontend scripts and current environment constraints (`package.json`, `.npmrc`, active ports/processes).
2. Ensure dependencies are present and not mid-conflict from stale install processes.
3. Execute `npm --prefix frontend run build` and verify completion.
4. Execute `npm --prefix frontend run dev` and capture served local URL.
5. Validate frontend loads and backend calls succeed; report blockers and exact remediation commands if any.
6. Provide final concise run command set for repeatability.
