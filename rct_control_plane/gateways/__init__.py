"""
Delentia OS - Real messaging gateway input adapters (Round 36).

Each gateway is a real, independent input source that resolves an
incoming message to a per-user/per-chat `namespace` (reusing the same
namespace-isolation pattern `agent_profile.py` already established) and
dispatches it directly to a real `AutonomousLoop.run(goal, namespace)`
call - bypassing the reminder table entirely, since these are real-time
triggers, not scheduled ones.
"""
