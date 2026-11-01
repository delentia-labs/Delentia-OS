# Pull Request

## Summary

Describe the change in 2-5 sentences, including the user-facing or developer-facing outcome, and link the issue if there is one.

## Type of Change

- [ ] Bug fix
- [ ] New feature
- [ ] Refactor
- [ ] Documentation
- [ ] Test-only change
- [ ] Security or compliance improvement

## How you checked it

The command you ran and what it printed. For a behaviour change, a test that fails without your change.

## Validation

- [ ] `python -m pytest <the files you touched>`
- [ ] `python -m ruff check core/ signedai/ rct_control_plane/ microservices/`
- [ ] `python -m mypy core/ signedai/ rct_control_plane/ --ignore-missing-imports --explicit-package-bases`
- [ ] `python -m bandit -r core/ signedai/ rct_control_plane/ microservices/ -lll`
- [ ] `mkdocs build --strict` if you touched `docs/`

## Checklist

- [ ] Tests added or updated where behavior changed
- [ ] No credentials, secrets, personal paths or internal-only URLs introduced
- [ ] A new tool is classified (a source of outside text, gated or inert) and goes through `agent_factory.build_governed_loop()`, never a plain `AutonomousLoop(...)`
- [ ] If a public claim changed (a number, a "works with"), it is backed by a test or a measurement linked here
- [ ] Public docs updated if public behavior changed
- [ ] This PR stays within the public SDK scope

## Notes for Reviewers

List any known tradeoffs, migration concerns, or follow-up work.
