#!/bin/bash
# Setup Archon DIDs for Codex and Gemini agents
# Creates identities and adds them to daemon-collective group

set -e

: "${ARCHON_PASSPHRASE:=agent-mcp-2026}"
export ARCHON_PASSPHRASE

DAEMON_COLLECTIVE="did:cid:bagaaierausu7hgbctnkcdz66bgfxu2xfgxd5fgnf7cn2434b6cbtn73jydoa"
KEYMASTER_URL="${ARCHON_KEYMASTER_URL:-http://localhost:4226}"

# Function to setup an agent's DID
setup_agent_did() {
    local AGENT_NAME="$1"
    local AGENT_DIR="$HOME/.agent/$AGENT_NAME/archon"
    
    echo "=== Setting up $AGENT_NAME ==="
    
    # Create directory
    mkdir -p "$AGENT_DIR"
    
    export ARCHON_CONFIG_DIR="$AGENT_DIR"
    
    # Check if wallet already exists with a DID
    if [ -f "$AGENT_DIR/wallet.json" ]; then
        echo "Wallet exists at $AGENT_DIR/wallet.json"
        EXISTING_DID=$(npx @didcid/keymaster list-ids 2>/dev/null | grep "$AGENT_NAME" || true)
        if [ -n "$EXISTING_DID" ]; then
            echo "DID already exists for $AGENT_NAME: $EXISTING_DID"
            return 0
        fi
    else
        # Initialize new wallet
        echo "Creating new wallet..."
        npx @didcid/keymaster new-wallet
    fi
    
    # Create the agent DID
    echo "Creating DID for $AGENT_NAME..."
    npx @didcid/keymaster create-id "$AGENT_NAME"
    
    # Get the new DID
    NEW_DID=$(npx @didcid/keymaster list-ids 2>/dev/null | grep "$AGENT_NAME" | awk '{print $2}' | head -1)
    
    if [ -z "$NEW_DID" ]; then
        echo "ERROR: Failed to create DID for $AGENT_NAME"
        return 1
    fi
    
    echo "Created: $NEW_DID"
    
    # Save DID to a reference file
    echo "$NEW_DID" > "$AGENT_DIR/did.txt"
    echo "Saved DID to $AGENT_DIR/did.txt"
}

# Function to add agent to daemon-collective
add_to_collective() {
    local AGENT_NAME="$1"
    local AGENT_DIR="$HOME/.agent/$AGENT_NAME/archon"
    
    if [ ! -f "$AGENT_DIR/did.txt" ]; then
        echo "No DID found for $AGENT_NAME"
        return 1
    fi
    
    local AGENT_DID=$(cat "$AGENT_DIR/did.txt")
    
    echo "Adding $AGENT_NAME ($AGENT_DID) to daemon-collective..."
    
    # Use Hex's wallet to add to group (Hex is the group admin)
    export ARCHON_CONFIG_DIR="$HOME/.config/hex/archon"
    export ARCHON_PASSPHRASE="hex-daemon-lightning-hive-2026"
    
    # Check if already a member
    MEMBERS=$(npx @didcid/keymaster get-group "$DAEMON_COLLECTIVE" 2>/dev/null || echo "")
    if echo "$MEMBERS" | grep -q "$AGENT_DID"; then
        echo "$AGENT_NAME already in daemon-collective"
        return 0
    fi
    
    # Add to group
    npx @didcid/keymaster add-group-member "$DAEMON_COLLECTIVE" "$AGENT_DID"
    echo "Added $AGENT_NAME to daemon-collective"
}

# Main
echo "Setting up agent DIDs..."
echo "Keymaster: $KEYMASTER_URL"
echo ""

# Setup Codex
setup_agent_did "codex"
echo ""

# Setup Gemini
setup_agent_did "gemini"
echo ""

# Add to daemon-collective (requires Hex's admin access)
echo "=== Adding to daemon-collective ==="
add_to_collective "codex"
add_to_collective "gemini"

echo ""
echo "=== Summary ==="
for agent in codex gemini; do
    if [ -f "$HOME/.agent/$agent/archon/did.txt" ]; then
        echo "$agent: $(cat $HOME/.agent/$agent/archon/did.txt)"
    fi
done

echo ""
echo "Done! Update mcporter.json with the new DIDs."
