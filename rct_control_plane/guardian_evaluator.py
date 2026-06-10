"""
Guardian Evaluator — Constitutional AI Safety Evaluation Shield

Integrates the Guardian LoRA adapter into the RCT Control Plane.
Calculates safety verdicts and FDIA scores: F = D^I * A.
Throws SecurityException if A=0 or status=REJECTED.
"""

import json
import time
from typing import Any, Dict, Tuple

from rct_control_plane.lora_multiplexer import LoRAMultiplexer
from rct_control_plane.otel_adapter import get_otel_adapter


class SecurityException(Exception):
    """Exception raised when malicious or non-compliant intent is detected."""
    pass


class GuardianEvaluator:
    """
    Constitutional AI safety shield using the Guardian LoRA adapter.
    Evaluates inputs using the FDIA metric gate.
    """

    def __init__(self, multiplexer: LoRAMultiplexer) -> None:
        self.multiplexer = multiplexer
        self.otel = get_otel_adapter()

    def evaluate_intent(self, intent: str, intent_id: str = "unknown") -> Tuple[bool, Dict[str, Any], float]:
        """
        Evaluates the user intent safety.
        Returns:
            Tuple of (is_authorized_bool, verdict_dict, latency_ms)
        Raises:
            SecurityException if intent is rejected.
        """
        start_time = time.perf_counter()

        # Swap to guardian adapter
        self.multiplexer.swap_adapter("guardian")

        # Format safety evaluation prompt
        system_context = (
            "You are The Guardian (slm-jitna-guardian) — a specialized Constitutional AI "
            "safety evaluator within the Delentia OS 1+4 Pillar Architecture. "
            "Your purpose is to evaluate every user intent for safety using the FDIA formula: "
            "F = D^I × A, where D=Data integrity, I=Intent clarity, A=Architect approval (0 or 1). "
            "Output ONLY a JSON verdict. If the intent is harmful, set A=0 and status=REJECTED. "
            "If safe, set A=1 and status=AUTHORIZED."
        )
        prompt = f"{system_context}\n\nUser intent: {intent}"

        # Generate verdict JSON
        response = self.multiplexer.generate(prompt)
        
        latency = (time.perf_counter() - start_time) * 1000

        try:
            verdict = json.loads(response)
        except json.JSONDecodeError:
            # Safe default fallback if JSON format parsing fails
            verdict = {
                "status": "REJECTED",
                "fdia": {"D": 0.1, "I": 0.1, "A": 0, "F": 0.0},
                "reason": "Malformed safety verdict JSON returned by adapter",
                "action": "BLOCK_AND_LOG",
            }

        # Calculate scores
        fdia = verdict.get("fdia", {})
        d_score = float(fdia.get("D", 0.0))
        i_score = float(fdia.get("I", 0.0))
        a_value = int(fdia.get("A", 0))
        f_score = float(fdia.get("F", 0.0))
        status = verdict.get("status", "REJECTED")

        # Emit telemetry spans to Langfuse/OTel
        if self.otel.is_enabled:
            self.otel.emit_fdia_metric(
                intent_id=intent_id,
                f_score=f_score,
                d_score=d_score,
                i_score=i_score,
                a_value=a_value,
                risk_level="HIGH" if a_value == 0 else "LOW",
            )

        print(f"[INFO] Guardian Evaluator: Safety status is {status} (FDIA: F={f_score:.4f}, A={a_value})")

        if status == "REJECTED" or a_value == 0:
            reason = verdict.get("reason", "Hostile intent detected.")
            rule = verdict.get("rct_rule_violated", "RCT-1: Constitutional Boundary")
            incident = verdict.get("incident_id", "sec_unassigned")
            
            # Print detailed security violation log
            print(f"[SECURITY ALERT] Harmful request blocked! Incident ID: {incident}, Rule Violated: {rule}, Reason: {reason}")
            raise SecurityException(
                f"Security block (FDIA={f_score:.2f}, A={a_value}). Intent violated rule {rule}. Reason: {reason}"
            )

        return True, verdict, latency
