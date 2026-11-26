# Contributing to Career Context AI

Thanks for helping. The project is small on purpose: Python 3.11 or newer, the standard library, and one HTML file for the Studio.

## Run it

```sh
python -m v2.launch --demo --open   # the Studio on a fictional sample vault
python -m unittest v2/test_v2.py -v # the test suite
python -m v2.assess                 # the offline assessment
```

Open the address the launcher prints. Opening `v2/ui.html` as a file shows the page without any data.

## Where things live

- `v2/db.py`: the vault, tiers, gap check and leak checks.
- `v2/server.py` and `v2/ui.html`: the local server and the Studio it serves.
- `v2/mcp_server.py`: the MCP server your assistant talks to.
- `v2/importers.py`, `v2/exporters.py`: getting material in, and briefs and context packs out.
- `SKILL.md`: the instructions an assistant follows.
- `docs/index.html`: the playable experiment on GitHub Pages.

## The Studio

- Four places: Home, Career, Sources and Share. Add to one of them before adding a fifth.
- Labels use plain words (Private, Confidential-safe, Public). The tier codes `L0` to `L3` appear only where the tiers are explained and in technical output.
- Surfaces are flat, lists are ruled rows, and the accent colour marks the primary action, the current item and focus.
- Check a change at 1440, 768, 375 and 320 pixels wide, in light and dark, and on both a sample vault (`--demo`) and a new empty one.

## Privacy rules

- Use fictional examples everywhere: code, tests, issues, screenshots and pull requests. Never attach a real vault, source export, credential or private link.
- Exported `L2` and `L3` pages must stay free of JavaScript and pass the leak checks.
- Commits must use a GitHub noreply address for the author, the committer and any trailer. Check a range before pushing:

```sh
python tools/check_git_privacy.py origin/main..HEAD
```

## Pull requests

Keep each one to a single purpose, say what you checked, and say what you did not.
