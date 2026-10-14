#!/bin/bash

SCRIPTDIR="$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"

# setup MCP server
#
if [ ! -d ".venv" ]; then
	echo "Creating virtual environment"
	python3 -m venv .venv
fi
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
fi
