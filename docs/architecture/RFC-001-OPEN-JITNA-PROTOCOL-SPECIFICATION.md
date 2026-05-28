# RFC-001: Open JITNA Protocol Specification

**Request for Comments: 001**  
**Category: Standards Track**  
**Date: February 2, 2026**  
**Authors: Delentia Labs, The Architect**  
**Status: Proposed Standard**  
**License: Apache 2.0**

---

## Abstract

The Open JITNA (**Just In Time Nodal Assembly**) Protocol is a universal communication standard designed to bridge the gap between human intent and machine execution in the age of Agentic AI.

This specification defines a structured, secure, and extensible protocol for encoding "computable intent" that enables seamless interaction between AI systems and diverse computational tools.

JITNA transforms natural language intentions into precise, machine-executable packets while maintaining security, auditability, and compliance with **The 9 Codex** safety framework.

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Terminology](#2-terminology)
3. [Protocol Overview](#3-protocol-overview)
4. [JITNA Packet Structure](#4-jitna-packet-structure)
5. [Security Framework](#5-security-framework)
6. [Adapter Integration](#6-adapter-integration)
7. [Natural Language Translation](#7-natural-language-translation)
8. [Implementation Guidelines](#8-implementation-guidelines)
9. [Security Considerations](#9-security-considerations)
10. [References](#10-references)

---

## 1. Introduction

### 1.1 Background

The rapid advancement of AI agents and autonomous systems has created a critical need for standardized communication protocols that can safely and reliably translate human intentions into machine actions. Existing protocols primarily focus on data transfer rather than **intent preservation** and security validation.

JITNA addresses these challenges by providing:

- **Intent Fidelity** — Preserving semantic meaning across the human-machine boundary
- **Security by Design** — Built-in validation and The 9 Codex compliance
- **Universal Compatibility** — Standardized interface for diverse tools and systems
- **Auditability** — Complete execution trace and responsibility tracking

### 1.2 Goals

The Open JITNA Protocol aims to:

- Establish a universal standard for intent-based computing
- Enable safe AI agent interactions with critical systems
- Provide a foundation for the next generation of human-AI collaboration
- Foster an open ecosystem of compatible tools and adapters

### 1.3 Scope

This specification defines:

- JITNA packet structure and encoding
- Security and validation mechanisms
- Adapter interface requirements
- Natural language translation framework
- Reference implementation guidelines

### 1.4 The Name

**JITNA = Just In Time Nodal Assembly**

Agents are assembled into working groups *just in time* based on the intent of the current task, then dissolved when the task completes. There is no permanent agent hierarchy. There are no pre-configured workflows.

---

## 2. Terminology

The key words "MUST", "MUST NOT", "REQUIRED", "SHALL", "SHALL NOT", "SHOULD", "SHOULD NOT", "RECOMMENDED", "MAY", and "OPTIONAL" in this document are to be interpreted as described in RFC 2119.

**JITNA Packet**  
A structured data unit containing intent, parameters, and validation information.

**Intent**  
A high-level objective or goal that an agent wishes to accomplish.

**Adapter**  
A software component that implements JITNA protocol for a specific tool or system.

**The Architect**  
The authenticated entity responsible for issuing JITNA packets.

**The 9 Codex**  
The core security and safety rules governing JITNA execution.

**Computable Intent**  
Intent expressed in a format that machines can parse, validate, and execute reliably.

**Nodal Assembly**  
The dynamic formation of agent groups in response to task intent — and their dissolution upon task completion.

---

## 3. Protocol Overview

### 3.1 Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Human     │    │    JITNA    │    │  Universal  │    │   Target    │
│   Intent    │───▶│  Gateway    │───▶│   Adapter   │───▶│    Tool     │
│             │    │             │    │             │    │             │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                   │                   │                   │
       │                   ▼                   ▼                   ▼
   Natural            JITNA Packet        Tool-Specific        Execution
   Language            Validation          Command             Result
```

### 3.2 Protocol Layers

1. **Intent Layer** — Natural language or structured intent input
2. **Translation Layer** — Conversion to JITNA packet format
3. **Validation Layer** — Security and compliance checking
4. **Execution Layer** — Tool-specific command generation
5. **Response Layer** — Standardized result formatting

### 3.3 Communication Flow

1. **Intent Capture** — User expresses intent in natural language or structured format
2. **Packet Creation** — Intent is translated to JITNA packet with validation metadata
3. **Security Validation** — Packet undergoes The 9 Codex compliance checking
4. **Adapter Routing** — Packet is routed to appropriate Universal Adapter
5. **Tool Execution** — Adapter translates packet to tool-specific commands
6. **Response Generation** — Results are formatted as standard JITNA response
7. **Audit Logging** — Complete execution trace is recorded for accountability

### 3.4 Negotiation Pattern

JITNA agents do not blindly execute instructions. They **negotiate**:

```
Agent A: PROPOSE  → "I need you to analyze this dataset"
Agent B: COUNTER  → "I can analyze it, but I need the schema first"
Agent A: ACCEPT   → "Here is the schema" [attaches schema]
Agent B: ACCEPT   → "Executing analysis"
Agent B: COMPLETE → "Analysis complete" [attaches results + signature]
```

Or when capability does not match:

```
Agent A: PROPOSE  → "Translate this medical document to Thai"
Agent B: REJECT   → "Not qualified for medical translation"
Agent A: PROPOSE  → [redirects to Agent C, a medical specialist]
```

---

## 4. JITNA Packet Structure

### 4.1 Wire Format

JITNA packets MUST be encoded as JSON objects:

```json
{
  "header": {
    "version": "2.0",
    "packet_id": "550e8400-e29b-41d4-a716-446655440001",
    "sender_id": "agent-identifier",
    "target_id": "adapter-identifier",
    "priority": 3,
    "timestamp": 1738454400000,
    "signature": "ed25519-base64-optional",
    "trace_id": "uuid-for-tracing-optional"
  },
  "intent": {
    "objective": "High-level goal description",
    "action": "create|read|update|delete|execute|render|analyze|deploy|search|sync",
    "target_tool": "tool-identifier",
    "goal_state": "Expected outcome description",
    "context": {
      "user_context": "session-info",
      "environment": "execution-environment",
      "history": ["previous-related-actions"],
      "dependencies": ["required-prior-operations"]
    }
  },
  "payload": {
    "parameters": { "key": "value" },
    "constraints": {
      "max_execution_time": 60000,
      "max_memory_mb": 512,
      "network_access": "none|local|restricted|full",
      "filesystem_access": "none|read-only|restricted|full",
      "security_level": 3,
      "allowed_operations": [],
      "forbidden_operations": []
    },
    "resources": {
      "compute": { "cpu_cores": 2, "memory_gb": 4, "gpu_required": false }
    },
    "output_format": "expected-output-format"
  },
  "validation": {
    "checksum": "sha256-hash",
    "expire_at": 1738458000000,
    "schema_version": "2.0",
    "errors": []
  }
}
```

### 4.2 Field Definitions

#### 4.2.1 Header

| Field | Required | Description |
|-------|----------|-------------|
| `version` | REQUIRED | JITNA protocol version (semver) |
| `packet_id` | REQUIRED | Unique identifier (UUID v4) |
| `sender_id` | REQUIRED | Authenticated identity of originator |
| `target_id` | REQUIRED | Target adapter or tool identifier |
| `priority` | REQUIRED | Execution priority 1–5 (1 = highest) |
| `timestamp` | REQUIRED | Unix milliseconds |
| `signature` | OPTIONAL | Ed25519 digital signature (RFC 8032) |
| `trace_id` | OPTIONAL | For distributed tracing |

#### 4.2.2 Intent

| Field | Required | Description |
|-------|----------|-------------|
| `objective` | REQUIRED | Human-readable goal description |
| `action` | REQUIRED | Standardized JITNA action verb |
| `target_tool` | REQUIRED | Identifier of the tool to execute |
| `goal_state` | OPTIONAL | Expected end state |
| `context` | OPTIONAL | Additional context for interpretation |

#### 4.2.3 Validation

| Field | Required | Description |
|-------|----------|-------------|
| `checksum` | REQUIRED | SHA-256 hash of packet content |
| `schema_version` | REQUIRED | JITNA schema version used |
| `expire_at` | OPTIONAL | Expiration timestamp |
| `errors` | OPTIONAL | Validation error details |

### 4.3 Response Format

```json
{
  "header": {
    "packet_id": "response-uuid",
    "response_to": "original-packet-id",
    "timestamp": 1738454401500,
    "status": "success|error|pending|rejected|timeout"
  },
  "data": {
    "result": "execution-result-data",
    "output_files": [],
    "metrics": { "execution_time_ms": 1500 }
  },
  "error": {
    "code": "ERROR_CODE",
    "message": "Human-readable error description",
    "details": {}
  },
  "metadata": {
    "execution_time_ms": 1500,
    "resource_usage": { "cpu_usage_percent": 25, "memory_usage_mb": 128 },
    "trace_id": "trace-uuid",
    "adapter_version": "1.0.0"
  }
}
```

---

## 5. Security Framework

### 5.1 The 9 Codex

All JITNA implementations MUST enforce **The 9 Codex**:

1. Never execute commands that modify system security settings
2. Always validate digital signatures before execution
3. Respect resource constraints and limits
4. Log all operations for audit trail
5. Never expose sensitive data in responses
6. Validate all input parameters for safety
7. Implement graceful failure modes
8. Enforce time-based expiration of commands
9. Maintain principle of least privilege

### 5.2 Security Levels

| Level | Name | Operations |
|-------|------|------------|
| 1 | SAFE | Read-only, no system changes |
| 2 | RESTRICTED | Limited changes, sandboxed execution |
| 3 | MODERATE | Standard operations, monitored |
| 4 | ELEVATED | Administrative, enhanced logging |
| 5 | CRITICAL | System-critical, multi-factor authentication |

### 5.3 Signatures

JITNA packets use **Ed25519** (RFC 8032) for authentication:

1. **Signing** — Packet content (excluding `signature` field) is serialized and signed
2. **Verification** — Adapters MUST verify signatures when present
3. **Replay Detection** — SHA-256 checkpoint chain prevents replay attacks
4. **Key Management** — Public keys MUST be distributed through secure channels

### 5.4 Audit Logging

All JITNA implementations MUST maintain audit logs containing:

- Packet ID and content hash
- Execution timestamps
- Success/failure status
- Resource usage metrics
- Security validation results

---

## 6. Adapter Integration

### 6.1 Adapter Interface

Universal Adapters MUST implement:

```typescript
interface JITNAAdapter {
  // Adapter identification
  getCapability(): JITNAAdapterCapability;

  // Main execution interface
  execute(packet: JITNAPacket): Promise<JITNAResponse>;

  // Health and status
  performHealthCheck(): Promise<AdapterHealthStatus>;
  getStatistics(): AdapterStatistics;

  // Lifecycle
  initialize(): Promise<void>;
  shutdown(): Promise<void>;
}
```

### 6.2 Capability Declaration

```json
{
  "adapter_id": "unique-adapter-identifier",
  "name": "Human-readable adapter name",
  "version": "1.0.0",
  "supported_actions": ["create", "read", "execute"],
  "supported_formats": ["json"],
  "security_level": 3,
  "status": "healthy|degraded|offline"
}
```

### 6.3 Error Handling

Adapters MUST handle:

- **Validation Errors** — Input parameter violations
- **Execution Errors** — Tool-specific failures
- **Resource Errors** — Insufficient resources
- **Security Errors** — Policy violations
- **Timeout Errors** — Execution time exceeded

---

## 7. Natural Language Translation

### 7.1 Translation Pipeline

1. **Intent Analysis** — Extract objective, action, and target tool
2. **Parameter Extraction** — Identify relevant parameters from context
3. **Constraint Inference** — Apply appropriate security constraints
4. **Packet Assembly** — Create well-formed JITNA packet
5. **Confidence Validation** — Verify translation confidence meets threshold

### 7.2 Supported Languages

- English (REQUIRED)
- Thai (REQUIRED for RCT implementations)
- Mandarin Chinese (RECOMMENDED)
- Additional languages (OPTIONAL)

---

## 8. Implementation Guidelines

### 8.1 Reference Implementation

```
https://github.com/delentia-labs/delentia-os
```

### 8.2 Language Bindings

- Python (REQUIRED) — `rct_control_plane/jitna_protocol.py`
- TypeScript (REQUIRED) — `@rct/types`
- Go (RECOMMENDED)
- Rust (RECOMMENDED)

### 8.3 Versioning

JITNA follows semantic versioning:

- **Major** — Breaking changes to packet format or core protocol
- **Minor** — New features, backward compatible
- **Patch** — Bug fixes, no protocol changes

Constants:

```python
JITNA_SCHEMA_VERSION = "2.0"
JITNA_MAX_PAYLOAD_SIZE_BYTES = 1_048_576  # 1 MB
```

---

## 9. Security Considerations

### 9.1 Attack Vectors

- **Packet Injection** — Malicious packet creation or modification
- **Privilege Escalation** — Bypassing security level restrictions
- **Resource Exhaustion** — DoS through resource-intensive operations
- **Data Exfiltration** — Unauthorized access to sensitive information
- **Command Injection** — Malicious code in parameters or objectives

### 9.2 Mitigation Strategies

- **Input Validation** — Strict parameter and constraint validation
- **Sandboxing** — Isolated execution environments for adapters
- **Rate Limiting** — Prevent resource exhaustion attacks
- **Access Control** — Role-based permissions for JITNA operations
- **Monitoring** — Real-time detection of anomalous behavior

### 9.3 Privacy

- User intentions may contain sensitive information
- Audit logs MUST be protected with appropriate access controls
- Personal data MUST comply with applicable privacy laws (PDPA, GDPR)

---

## 10. References

### 10.1 Normative

- [RFC 2119] Bradner, S. — Key words for RFCs (Requirement Levels)
- [RFC 7159] Bray, T. — JSON Data Interchange Format
- [RFC 8032] Josefsson, S. & Liusvaara, I. — Edwards-Curve Digital Signature Algorithm (Ed25519)

### 10.2 Informative

- Delentia Labs — *RCT Platform SDK* — <https://github.com/delentia-labs/delentia-os>
- Delentia Labs — *The 9 Codex: Security Framework for Agentic AI Systems*
- Delentia Labs — *RCT Ecosystem Whitepaper 2026*

---

## Appendix A: Example Packets

### A.1 Simple File Operation

```json
{
  "header": {
    "version": "2.0",
    "packet_id": "550e8400-e29b-41d4-a716-446655440001",
    "sender_id": "user-12345",
    "target_id": "filesystem-adapter",
    "priority": 5,
    "timestamp": 1738454400000
  },
  "intent": {
    "objective": "Create a new configuration file",
    "action": "create",
    "target_tool": "filesystem"
  },
  "payload": {
    "parameters": { "filename": "app.config", "content": "debug=true\nport=8080", "path": "/etc/myapp/" },
    "constraints": { "security_level": 2, "max_execution_time": 5000, "filesystem_access": "restricted" }
  },
  "validation": { "checksum": "sha256-placeholder", "schema_version": "2.0" }
}
```

### A.2 Multi-Agent Consensus Task

```json
{
  "header": {
    "version": "2.0",
    "packet_id": "550e8400-e29b-41d4-a716-446655440002",
    "sender_id": "architect-system",
    "target_id": "signedai-tier-6",
    "priority": 2,
    "timestamp": 1738454400000,
    "signature": "base64-ed25519-signature"
  },
  "intent": {
    "objective": "Verify refactored authentication module",
    "action": "analyze",
    "target_tool": "signedai",
    "goal_state": "All 6 models reach consensus: PASS or REVISE"
  },
  "payload": {
    "parameters": { "artifact_hash": "sha256-of-code", "artifact_type": "code" },
    "constraints": { "security_level": 4, "max_execution_time": 30000 }
  },
  "validation": { "checksum": "sha256-placeholder", "schema_version": "2.0", "expire_at": 1738458000000 }
}
```

---

## Appendix B: Python Reference

```python
from rct_control_plane.jitna_protocol import (
    JITNAPacket,
    JITNAValidator,
    JITNANormalizer,
    JITNAProtocolRegistry,
)

# Create a packet
packet = JITNAPacket(
    packet_id="uuid-v4",
    source_agent_id="my-agent",
    target_agent_id="specialist-agent",
    message_type="TASK_REQUEST",
    payload={"objective": "Analyze Q1 data", "action": "analyze"},
    timestamp="2026-02-02T00:00:00Z",
    schema_version="2.0",
    priority=3,
    correlation_id="session-uuid",
    signature="",
    metadata={},
    status="PENDING",
)

# Validate
validator = JITNAValidator()
is_valid = validator.validate(packet)

# Register in protocol registry
registry = JITNAProtocolRegistry()
registry.register(packet)
```

---

**Authors' Addresses**

Delentia Labs  
Email: <open-jitna@delentia.com>  
URI: <https://delentia.com>

---

**Copyright Notice**

Copyright © 2026 Delentia Labs. Licensed under the Apache License, Version 2.0.

---

*End of RFC-001*
