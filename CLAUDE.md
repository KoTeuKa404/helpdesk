# Claude Code notes

Please read [AGENTS.md](AGENTS.md) first. It is the canonical set of instructions for all coding agents in this repository.

See [README.md](README.md) for architecture, running the self-contained Docker Compose stack, the optional Local AI Gateway override, testing, API endpoints and security assumptions.

Key invariant: an LLM result is only a draft until a human operator approves it. A duplicate event must not create another outgoing reply. Do not commit or disclose secrets.
