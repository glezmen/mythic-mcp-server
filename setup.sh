#!/bin/bash

SCRIPTDIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# setup MCP server
#
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .

# notify Pi harness about our MCP server
#
if [ $(which pi) ]; then
	echo "Adding to pi"
	pi mcp add mythic-gm \
	  --cwd "$SCRIPTDIR" \
	  --env "MYTHIC_STATE_FILE=$HOME/.mythic-gm-mcp/session.json" \
	  -- "$SCRIPTDIR/.venv/bin/mythic-gm-mcp"

	pi mcp list || echo "ERROR: Pi MCP servers not configured correctly"
fi
