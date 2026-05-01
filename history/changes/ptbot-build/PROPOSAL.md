# /deft:change ptbot-build

## Scope

Implement PTBot from `SPECIFICATION.md` as a Python CLI project and installable Warp skill.

## Planned Changes

- Scaffold Python project configuration (`pyproject.toml`, `Taskfile.yml`, package layout, tests)
- Implement two-pass precedent transaction research pipeline
- Implement CLI launcher with prompt generation and config-only mode
- Implement PDF and Excel output generators
- Write skill packaging files (`SKILL.md`, references, scripts)
- Install the skill to `~/.agents/skills/precedent-transactions/`
- Run tests and `task check`

## Acceptance Criteria

- `task check` passes
- `task test:coverage` passes at ≥85%
- `precedent_txns.py --config-only` produces valid JSON
- Skill directory exists at `~/.agents/skills/precedent-transactions/`
- PTBot does not modify `attack.market`
