# Credits

Bearings is built on the work of many open-source projects.
Thanks to everyone who maintains them.

## Foundation

- [Anthropic](https://www.anthropic.com) — Claude
- [claude-agent-sdk](https://github.com/anthropics/claude-agent-sdk-python)
- [Python](https://www.python.org)
- [SQLite](https://www.sqlite.org)

## Backend (runtime)

- [FastAPI](https://fastapi.tiangolo.com) (`fastapi`)
- [Uvicorn](https://www.uvicorn.org) (`uvicorn`)
- [Starlette](https://www.starlette.io) — FastAPI's foundation
- [websockets](https://websockets.readthedocs.io) (`websockets`)
- [Pydantic](https://docs.pydantic.dev) (`pydantic`)
- [pydantic-settings](https://github.com/pydantic/pydantic-settings) (`pydantic-settings`)
- [aiosqlite](https://github.com/omnilib/aiosqlite) (`aiosqlite`)
- [orjson](https://github.com/ijl/orjson) (`orjson`)
- [prometheus-client](https://github.com/prometheus/client_python) (`prometheus-client`)
- [tomli-w](https://github.com/hukkin/tomli-w) (`tomli-w`)
- [python-multipart](https://github.com/Kludex/python-multipart) (`python-multipart`)
- [Pillow](https://python-pillow.org) (`pillow`) — avatar image normalisation

## Frontend (shipped in the bundle)

- [Svelte](https://svelte.dev) / [SvelteKit](https://svelte.dev/docs/kit)
- [Tailwind CSS](https://tailwindcss.com)
- [marked](https://marked.js.org) (`marked`)
- [Shiki](https://shiki.style) (`shiki`)
- [DOMPurify](https://github.com/cure53/DOMPurify) — via
  [isomorphic-dompurify](https://github.com/kkomelin/isomorphic-dompurify)
  (`isomorphic-dompurify`)

---

The trailing parenthesised name on each runtime row is the package
identifier that appears in `pyproject.toml` or
`frontend/package.json`. `tests/test_credits_coverage.py` asserts
each runtime dependency is mentioned here so this list cannot
silently drift behind the manifests.
