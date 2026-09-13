# Project Instructions

## 1. Project Identity

- **Official Project Title**: 多智能体协作智能地理空间数据强化分析系统
- **Project Nature**: 本科毕业设计
- **Author**: 敬博浩
- **Supervisor**: 刘希亮老师
- **Current Positioning**: A thesis-oriented research prototype for a general geospatial analysis agent system, built around an OpenCode-server-backed runtime. KDE density hotspot analysis, IDW spatial interpolation, and Gi* statistical hotspot analysis are coequal currently supported task families; the system should remain extensible to additional geospatial analysis tasks.

## 2. Thesis Task Handoff

Any thesis-related task must read and follow `bjutthesis/AGENTS.md` before making changes. This includes thesis writing, thesis editing, thesis structure updates, LaTeX compilation, thesis PDFs, thesis figures or tables, references, school formatting requirements, final submission formatting, and thesis-oriented experimental materials or evidence.

Keep this root `AGENTS.md` focused on repository-wide implementation, runtime, geospatial, and frontend rules. Thesis-specific source documents, compilation commands, writing style, and submission-format instructions live in `bjutthesis/AGENTS.md`.

## 3. Project Reference Material

- `documents/`: All non-code project-related documents. This is a symlink, so double-check paths before concluding whether a file exists.
- `documents/提交材料/开题/`: Approved proposal, background framing, and early architectural intent.
- `documents/提交材料/周报/`: Latest supervisor feedback and the best source for short-term scope corrections.
- `archive/`: Legacy prototype from a senior student. Treat it strictly as a minimal reference.

## 4. Runtime and Architecture Rules

- Use OpenCode's client-server runtime as the default execution substrate.
- Prefer OpenCode-native concepts for sessions, plans or todos, agent messages, subagent calls, skills, tool history, and execution traces. Do not rebuild these concepts in the app layer unless OpenCode lacks a capability we truly need.
- Do not design around pre-authored plans, fixed processing flows, canned result templates, hidden prompt rewriting, or app-owned workflow scripts. The user's prompt should enter the main agent flow unchanged; guidance belongs in bundled instructions, agent roles, skills, and tools.
- Treat `planner`, `data-prep`, `analysis`, `viz`, `report`, and `reflection` as stable responsibilities, not a fixed execution order. The orchestrator may invoke and interleave them dynamically.
- Keep the prototype as self-contained and independent from user-global machine state as practical. Backend-managed runtime setup, isolated directories, health checks, config injection, cleanup, and explicit configuration are preferred.
- The backend should be asyncio-native by default: async endpoints, async subprocess handling, async HTTP clients, and non-blocking streaming or supervision unless a contained sync bridge is unavoidable.

## 5. Geospatial and Evidence Rules

- Always track and validate `CRS` and `Bounding Box`. Be especially careful not to confuse latitude/longitude degrees with metric projections.
- Preserve real execution evidence: messages, todo evolution, subagent activity, tool calls, tool outputs, artifacts, and session metadata.
- Reflection or verification should be visible in the transcript and artifact trail. It may happen before, during, or after other work, and it may trigger repair, clarification, retry, or termination.

## 6. Frontend Rules

- Default frontend stack: Vue 3 + Vite + TypeScript + Tailwind CSS v4, unless an approved design changes that choice.
- Prefer a message-first notebook or transcript UI. Inline messages should present todo updates, subagent calls, tool activity, dataset previews, tables, charts, maps, markdown reports, reflection results, and intermediate artifacts.
- Keep the right sidebar limited to minimal global state such as current todo, final artifacts, runtime status, and workspace entry points.
- When validating frontend flows, run the app and inspect live UI behavior. If `browser-use:browser` is available, prefer that workflow over Chrome DevTools MCP.

## 7. Deep Research Ability by GPT Pro

The user has access to OpenAI's strongest model, GPT Pro, which provides professional deep research capabilities.
If a task would genuinely benefit from this capability, write a precise research prompt for the user to submit instead of analyzing locally.
