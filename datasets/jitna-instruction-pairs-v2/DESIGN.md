# 🏛️ JITNA Pairs v2 — Multi-Turn Enterprise & State Rollback Dataset Design (SLM v0.2)

This specification defines the JITNA Pairs v2 dataset format for training and validating small language models (SLMs) in multi-agent environments. JITNA Pairs v2 supports long-horizon multi-turn negotiations, cryptographic transaction isolation, and cryptographically verifiable Delta Rollbacks.

---

## 1. Architectural Overview & ZK Pedersen Commitments

In a governed multi-agent ecosystem, agents transition database or runtime states via structured **JITNA packets**. When multiple agents negotiate or coordinate on database transactions, verifying the consistency and compliance of state changes is critical—especially when a transaction fails and must be rolled back.

To achieve verifiable transaction history without exposing sensitive payload details publicly, JITNA Pairs v2 integrates **Pedersen ZK Commitments**.

### Homomorphic State Mathematics

A Pedersen commitment to a value $v$ using a blinding factor $r$ is defined as:
$$C(v, r) = g^v \cdot h^r \pmod p$$
where $g$ and $h$ are generators of a group over a finite field (typically elliptic curve base points) such that the discrete logarithm $\log_g h$ is computationally intractable.

Pedersen commitments have an extremely powerful **homomorphic addition** property. The product of two commitments is a commitment to the sum of their values:
$$C(v_1, r_1) \cdot C(v_2, r_2) = (g^{v_1} \cdot h^{r_1}) \cdot (g^{v_2} \cdot h^{r_2}) = g^{v_1 + v_2} \cdot h^{r_1 + r_2} = C(v_1 + v_2, r_1 + r_2)$$

### Verifiable Delta Rollbacks

In enterprise transaction scenarios, a state $S_0$ transitions to $S_1$ by applying a delta $\Delta$:
$$S_1 = S_0 + \Delta$$

At each transaction step, the agents commit to the delta $\Delta$ using blinding factor $r_\Delta$:
$$C(S_1) = C(S_0) \cdot C(\Delta, r_\Delta)$$

If a transaction step fails (e.g., due to timeout, inventory lock failure, or policy violation), a **Delta Rollback** is triggered to restore $S_0$:
$$S_0 = S_1 - \Delta$$

Using homomorphic operations, the consensus layer verifies that the rolled-back state matches $S_0$ by dividing commitments (multiplying by the modular inverse):
$$C(S_0) = C(S_1) \cdot C(\Delta, r_\Delta)^{-1}$$

This guarantees mathematical compliance: the final state is cryptographically proven to be identical to the starting state without disclosing the database records.

---

## 2. File Schema Specifications

The dataset consists of two primary JSON Lines (`.jsonl`) files:

### A. `conversation-chains.jsonl`
Tracks multi-turn negotiations between agents attempting to agree on resource allocation or policy constraints.

#### Schema Fields:
- `scenario_id` (string): Unique identifier for the negotiation.
- `topic` (string): Domain of the negotiation (e.g., `resource_allocation`).
- `agents` (array of strings): List of participating agent IDs.
- `turns` (array of objects): Sequence of agent statements.
  - `turn` (int): Turn index starting from 1.
  - `agent` (string): ID of the speaking agent.
  - `action` (string): Action type (`propose`, `counter`, `accept`, `reject`).
  - `jitna_packet` (object): Standard JITNA packet structure.
    - `intent` (string): Textual statement of intent.
    - `domain` (string): Domain categorization.
    - `constraints` (object): Active operational limits.
    - `payload` (object): Target transaction variables.
    - `signature` (string): Cryptographic Ed25519 signature of the packet.
  - `commitment` (object): Cryptographic commitment of the turn's target value.
    - `value` (int): Raw value committed.
    - `blinding_factor` (string): Secret randomness.
    - `pedersen_hash` (string): Resulting hex hash $C(v, r)$.
- `consensus_result` (object): Outcome of the negotiation.
  - `status` (string): `APPROVED` or `FAILED`.
  - `final_state` (object): Resolved transaction variables.
  - `zk_proof_verification` (boolean): Whether ZK proofs passed.

### B. `rollback-scenarios.jsonl`
Logs transaction histories, delta computations, failures, and subsequent rollback executions.

#### Schema Fields:
- `scenario_id` (string): Unique identifier for the rollback scenario.
- `transaction_id` (string): Database transaction ID.
- `initial_state` (object): Database values at $S_0$.
- `delta_history` (array of objects): History of applied deltas.
  - `step` (int): Step index.
  - `action` (string): Database action performed.
  - `delta` (object): Numerical changes applied.
  - `commitment` (object): Pedersen commitment for the changes.
  - `state_after` (object): Resulting values at $S_i$ and the committed state hash.
- `failure_trigger` (object): Details of the exception that occurred.
  - `step_occurred` (int): Step at which failure was thrown.
  - `reason` (string): Cause of failure (e.g., `resource_insufficient`).
  - `error_code` (string): System error code.
- `rollback_execution` (object): Step-by-step rollback trail.
  - `steps` (array of objects): Sequence of inverse deltas.
    - `rollback_step` (int): Step index.
    - `inverse_delta` (object): Negative of the original delta.
    - `expected_state` (object): Target database values after this rollback step.
  - `verification` (object): Final validation checks.
    - `final_hash_matches_initial` (boolean): Proof that rolled-back state matches $S_0$.
    - `zk_homomorphic_sum_valid` (boolean): Homomorphic addition proof passes.

---

## 3. Benefits to the Ecosystem

1. **State Isolation:** Prevents data leakage between agent microservices during intermediate negotiation states.
2. **Deterministic Rollback:** Guarantees database state integrity in high-throughput transaction pipelines.
3. **Audit Trail:** Supports zero-knowledge compliance auditing by external regulatory entities.
