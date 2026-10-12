# Using Delentia from an editor (Agent Client Protocol)

`delentia acp` makes Delentia an ACP agent: an editor that speaks the Agent Client Protocol (Zed, JetBrains IDEs, and others) starts it as a subprocess and sends it prompts.
The protocol is JSON-RPC 2.0, one message per line over stdin/stdout.

## Set it up
Tell the editor to run this command (check your editor's documentation for where an external ACP agent is declared; in Zed it is the `agent_servers` setting):

    command: python
    args:    -m rct_control_plane.cli acp
    env:     DELENTIA_HOME, DELENTIA_REPO_ROOT, DELENTIA_MODEL_CONFIG   (the same as for `delentia serve`)

## What you get, and what you do not
* Every prompt is one **governed episode**: the same gate as the CLI, the API and the chat channels (GUARD, THINK, ROUTE, ACT with the FDIA gate and your owner policy, the taint gate, RECORD).
  Each tool the episode used appears in the editor as a tool call (read / edit / search / fetch / execute).
* **An editor's "allow" button is not a signature.** An action that needs a human signature stops the episode; the editor shows "Waiting for a human signature" and the approval id.
  Sign on your own device (`delentia approvals sign`), then `delentia approvals approve`. `session/request_permission` is never used to authorise anything.
* **MCP servers the editor lists are ignored** (each session's audit row says how many). External servers come only from `~/.delentia/mcp_servers.json`, through the same gate.
* The working directory the editor reports is recorded, not obeyed: the agent's file tools stay inside `DELENTIA_REPO_ROOT`.
* It runs as your own namespace (`DELENTIA_ACP_NAMESPACE`, else the Desk's), like the CLI. Slash commands such as `/help` and `/status` work.
* Not supported (the capabilities say so): loading an old session, images, audio, the editor's own file and terminal methods.

## Checked
The command was driven over real pipes by a test client with a scripted model: initialize, a new session, a read, a write that stopped for a signature, a slash command, an unknown method, a parse error.
It was **not** tried in a real editor.
