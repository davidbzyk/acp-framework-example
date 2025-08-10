# Quickstart targets for AI Librarian

.PHONY: help install start-archivist start-critic start-catalog start-all start-all-tmux start-all-mcp stop-all client list kill-ports render-diagrams

help:
	@echo "Targets:"
	@echo "  install         - Sync dependencies (uv)"
	@echo "  start-archivist - Run CrewAI Archivist server on :8001"
	@echo "  start-critic    - Run Smolagents Critic server on :8002"
	@echo "  start-catalog   - Run optional MCP catalog server on :8003"
	@echo "  start-all       - Start Archivist, Critic (+ Catalog if desired). Uses tmux if available"
	@echo "  start-all-mcp   - Start Archivist, Catalog, and Critic with USE_MCP_DISCOVERY=1"
	@echo "  stop-all        - Stop servers on 8001/8002/8003"
	@echo "  client          - Run interactive ACP CLI client"
	@echo "  list            - One-off: ask critic to list available books"
	@echo "  kill-ports      - Kill processes on 8001/8002/8003 (if stuck)"
	@echo "  render-diagrams - Render Mermaid PNGs to diagrams/*.png (requires mmdc)"

install:
	uv sync

start-archivist:
	uv run python crew_agent_server.py

start-critic:
	uv run python smolagents_server.py

start-catalog:
	uv run python mcpserver.py

# Start all servers in a tmux session if tmux exists
start-all: start-all-tmux

start-all-tmux:
	@if command -v tmux >/dev/null 2>&1; then \
		session=ai_librarian; \
		tmux has-session -t $$session 2>/dev/null && tmux kill-session -t $$session || true; \
		tmux new-session -d -s $$session -n archivist 'uv run python crew_agent_server.py'; \
		tmux split-window -t $$session:0 -h 'uv run python smolagents_server.py'; \
		tmux select-layout -t $$session:0 tiled; \
		echo "Started tmux session '$$session'. Use: tmux attach -t $$session"; \
	else \
		echo "tmux not found. Start servers manually with 'make start-archivist' and 'make start-critic' in separate terminals."; \
		exit 1; \
	fi

start-all-mcp:
	@if command -v tmux >/dev/null 2>&1; then \
		session=ai_librarian_mcp; \
		tmux has-session -t $$session 2>/dev/null && tmux kill-session -t $$session || true; \
		tmux new-session -d -s $$session -n archivist 'uv run python crew_agent_server.py'; \
		tmux split-window -t $$session:0 -h 'uv run python mcpserver.py'; \
		tmux split-window -t $$session:0 -v 'USE_MCP_DISCOVERY=1 uv run python smolagents_server.py'; \
		tmux select-layout -t $$session:0 tiled; \
		echo "Started tmux session '$$session' with MCP discovery. Use: tmux attach -t $$session"; \
	else \
		echo "tmux not found. Start servers manually in three terminals:"; \
		echo "  1) uv run python crew_agent_server.py"; \
		echo "  2) uv run python mcpserver.py"; \
		echo "  3) USE_MCP_DISCOVERY=1 uv run python smolagents_server.py"; \
		exit 1; \
	fi

stop-all: kill-ports

client:
	uv run python main.py

list:
	uv run python scripts/list_books.py

kill-ports:
	-@pids=$$(lsof -i :8001 -t 2>/dev/null); if [ -n "$$pids" ]; then kill -TERM $$pids; fi; true
	-@pids=$$(lsof -i :8002 -t 2>/dev/null); if [ -n "$$pids" ]; then kill -TERM $$pids; fi; true
	-@pids=$$(lsof -i :8003 -t 2>/dev/null); if [ -n "$$pids" ]; then kill -TERM $$pids; fi; true

# Render diagrams using Mermaid CLI (install: npm i -g @mermaid-js/mermaid-cli)
render-diagrams: diagrams/architecture.png diagrams/sequence.png

diagrams/architecture.png: diagrams/architecture.mmd diagrams/puppeteer.json
	mmdc -i $< -o $@ -b transparent -p diagrams/puppeteer.json

diagrams/sequence.png: diagrams/sequence.mmd diagrams/puppeteer.json
	mmdc -i $< -o $@ -b transparent -p diagrams/puppeteer.json
