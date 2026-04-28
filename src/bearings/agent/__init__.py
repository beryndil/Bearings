"""Bearings v1 ``agent`` layer — domain code between the SDK and the DB.

Per ``docs/architecture-v1.md`` §1.1.4 + §3, this package owns:

* the per-session SDK wrapper (:mod:`bearings.agent.session`);
* event types the streaming protocol carries
  (:mod:`bearings.agent.events`);
* runner-fleet types crossing the agent ⇄ web boundary
  (:mod:`bearings.agent.runner`);
* the routing-decision dataclass (:mod:`bearings.agent.routing`).

The package deliberately exposes its concerns via per-module imports
rather than a re-export wall — see arch §1.1.3 / §6.1 (the
``bearings.db.store`` re-export wall is the worked example of why a
facade module costs more than it saves). Downstream callers write
``from bearings.agent.session import AgentSession``, not
``from bearings.agent import AgentSession``.

Layer rule (arch §3.1): this package may not import from
:mod:`bearings.web` or :mod:`bearings.cli`. The cycle-prevention test
in ``tests/test_session_runner_factory.py`` walks every ``*.py`` under
``src/bearings/agent/`` and fails if either prefix appears.
"""

from __future__ import annotations

__all__: list[str] = []
