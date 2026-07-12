# Agents

This file provides guidance to OpenAI Codex for working with code in this repository.

**constraint** Follow all the rules in all files in directory, [ai-rules](./ai-rules/).
**constraint** Add new general project rules to [PROJECT_CONTEXT.md](./ai-rules/PROJECT_CONTEXT.md).
**suggestion** If a new feature has a lot of new rules, create a new rule file in [ai-rules](./ai-rules/), purely for organization.  Otherwise add it to PROJECT_CONTEXT.md

## Shared agent contract

The shared `/btbai` command contract is injected at runtime from the
`SHARED_AGENT_CONTRACT` environment value in `.github/workflows/btb.yml`.
Update that workflow value, the executable workflow behavior, and
`requirements/spec/btb-workflow.md` together when command semantics or phase
boundaries change.

Do not paste the full shared contract into `CLAUDE.md`, `AGENTS.md`, client
`ai-rules`, or templates. Those files should contain local repo guidance and
short pointers only.

## Agent rules

- Treat `templates/` as client bootstrap material, not another source of truth
  for shared pipeline behavior.
- When a fix needs to reach client repositories, release this repository and move
  the floating `v1` tag as part of the ship flow.

- Follow every file in `ai-rules/` before editing.
- Work on a fresh branch from `main`; never edit directly on `main`.
- Keep the living spec in `requirements/spec/` synchronized with workflow
  behavior changes.
- For new code, always create a unit test
  - For Typescript, use Vitest
  - For Java, use JUnit 6
  - For Python, use Pytest
- If you can't make a needed change, give clear instructions on how I must manually change it.  Assume I'm a 5 year old that knows how to write, but I know nothing else.
