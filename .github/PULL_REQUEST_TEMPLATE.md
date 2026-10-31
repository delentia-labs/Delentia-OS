## What this changes and why

<!-- One or two sentences. Link the issue if there is one. -->

## How you checked it

<!-- The command you ran and what it printed. For a behaviour change, a test that fails without your change. -->

## Checklist

- [ ] Tests added or updated, and `python -m pytest <the files you touched>` passes
- [ ] `ruff check core/ signedai/ rct_control_plane/ microservices/` is clean
- [ ] No keys, tokens, personal paths or internal URLs
- [ ] A new tool is classified (a source of outside text, gated, or inert) and goes through `agent_factory.build_governed_loop()`
- [ ] If you changed a public claim (a number, a "works with"), it is backed by a test or a measurement linked here
- [ ] `docs/` updated if behaviour changed (`mkdocs build --strict` passes)
