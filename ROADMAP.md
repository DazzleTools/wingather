# Roadmap

wingather is a focused tool for window discovery, recovery, and visibility. It intentionally stays in its lane — composable with other tools rather than trying to do everything.

## Milestones

### 1.0 — Production-Ready Windows

- [ ] Config file support (`~/.wingather.toml` or similar)
- [ ] Watch mode — periodic re-scan for new suspicious windows
- [ ] Window grouping by process tree
- [ ] Improved output formatting and summary statistics
- [ ] PyPI publication

### Future — Cross-Platform

- [ ] macOS implementation via PyObjC / Quartz CGWindow API
- [ ] Linux/X11 implementation via python-xlib / wmctrl
- [ ] Platform-specific test suites

See [docs/platform-support.md](docs/platform-support.md) for platform details and how to help.

## Out of Scope

These are valuable ideas better served probably by companion tools:

- **Process behavior monitoring** (spawning patterns, cmd shell activity) → [process-delta](https://github.com/DazzleTools/process-delta)
- **Service change detection** → process-delta
- **Window movement tracking over time** → potential standalone tool

wingather runs, reports, and exits. Long-running monitoring probably belongs elsewhere (subject to change though).

## Tracking

- [Issue #1 — ROADMAP](https://github.com/DazzleTools/wingather/issues/1)
- [Issue #2 — Feature backlog](https://github.com/DazzleTools/wingather/issues/2)
