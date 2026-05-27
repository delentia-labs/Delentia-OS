/**
 * @rctlabs/rct-edge โ€” Edge Runtime for RCT Platform
 *
 * Cloudflare Workers & browser compatible (no Node.js built-ins).
 * Provides:
 *  - EdgeCORD: 30 critical injection patterns, pure regex, <8KB
 *  - FDIA gate: F = D^I ร— A inline formula (no external dep)
 *  - edgeGate: combined CORD + FDIA in one call
 *
 * @example
 * ```ts
 * import { edgeGate } from '@rctlabs/rct-edge';
 * const result = edgeGate("Do task X", 0.85, 1.0, 0.9);
 * if (!result.allowed) throw new Error(result.reason);
 * ```
 */

// ---------------------------------------------------------------------------
// Inline FDIA โ€” F = D^I ร— A  (mirrors @rctlabs/fdia-wasm, zero-dep copy)
// ---------------------------------------------------------------------------

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low';

export interface EdgeFDIAResult {
  f: number;       // final FDIA score
  d: number;       // desirability input
  i: number;       // intent alignment input
  a: number;       // authority input
  risk: RiskLevel;
}

export function computeFDIA(d: number, i: number, a: number): EdgeFDIAResult {
  if (d < 0 || d > 1) throw new RangeError(`d must be in [0,1], got ${d}`);
  if (i < 0 || i > 1) throw new RangeError(`i must be in [0,1], got ${i}`);
  if (a < 0 || a > 1) throw new RangeError(`a must be in [0,1], got ${a}`);

  if (a === 0) return { f: 0, d, i, a, risk: 'critical' };

  const f = Math.pow(d, i) * a;
  let risk: RiskLevel;
  if (f >= 0.75) risk = 'low';
  else if (f >= 0.5) risk = 'medium';
  else if (f >= 0.25) risk = 'high';
  else risk = 'critical';

  return { f, d, i, a, risk };
}

export function meetsThreshold(result: EdgeFDIAResult, minF = 0.3): boolean {
  return result.f >= minF;
}

// ---------------------------------------------------------------------------
// Edge CORD โ€” 30 critical injection patterns
// ---------------------------------------------------------------------------

export interface EdgeCORDPattern {
  id: string;
  severity: 'soft' | 'hard';
  regex: RegExp;
  description: string;
}

export interface EdgeCORDResult {
  verdict: 'CLEAN' | 'SUSPICIOUS' | 'REJECTED';
  matched: EdgeCORDMatch[];
  score: number; // 0.0โ€“1.0, higher = more suspicious
  checkedAt: string;
}

export interface EdgeCORDMatch {
  patternId: string;
  severity: 'soft' | 'hard';
  description: string;
}

const EDGE_CORD_PATTERNS: EdgeCORDPattern[] = [
  // Direct prompt injection
  { id: 'E001', severity: 'hard', regex: /ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|context)/i, description: 'Direct prompt override' },
  { id: 'E002', severity: 'hard', regex: /disregard\s+(all\s+)?(previous|prior|your)\s+(instructions?|rules|guidelines)/i, description: 'Instruction disregard' },
  { id: 'E003', severity: 'hard', regex: /forget\s+(all\s+)?(everything|previous|prior)\s+(you|instructions?|context)/i, description: 'Context wipe command' },
  { id: 'E004', severity: 'hard', regex: /you\s+are\s+now\s+(?:a\s+)?(?:an?\s+)?(?:different|new|another|unrestricted|free)\s+\w+/i, description: 'Identity replacement' },
  { id: 'E005', severity: 'hard', regex: /act\s+as\s+(?:if\s+you\s+(?:are|were)\s+)?(?:an?\s+)?(?:unrestricted|unfiltered|jailbroken|free)\s+\w+/i, description: 'Jailbreak persona' },

  // System prompt extraction
  { id: 'E006', severity: 'hard', regex: /(?:print|show|reveal|output|display|repeat|tell\s+me)\s+(?:your\s+)?(?:system\s+prompt|instructions?|initial\s+prompt|full\s+prompt)/i, description: 'System prompt extraction' },
  { id: 'E007', severity: 'hard', regex: /what\s+(?:are\s+)?(?:your\s+)?(?:exact\s+)?(?:instructions?|system\s+prompt|guidelines|constraints)/i, description: 'Instruction probing' },
  { id: 'E008', severity: 'soft', regex: /start\s+(?:your\s+)?(?:response\s+)?with\s+["']?sure[,!]?\s*here/i, description: 'Compliance pre-seeding' },

  // Roleplay escalation
  { id: 'E009', severity: 'hard', regex: /pretend\s+(?:you\s+(?:are|have)\s+)?(?:no\s+(?:restrictions?|rules?|guidelines?|limits?|filters?))/i, description: 'Restriction removal roleplay' },
  { id: 'E010', severity: 'hard', regex: /(?:DAN|STAN|DUDE|BasedGPT|AIM|Jailbreak)\s*(?:mode|prompt|enabled?)/i, description: 'Known jailbreak persona' },
  { id: 'E011', severity: 'soft', regex: /hypothetically\s+speaking[,:]?\s+(?:if\s+there\s+were\s+no\s+rules|ignore|bypass)/i, description: 'Hypothetical framing bypass' },
  { id: 'E012', severity: 'soft', regex: /in\s+a\s+(?:fictional|hypothetical|imaginary)\s+(?:world|scenario)[,\s]+where\s+(?:rules?|laws?|ethics?)\s+don'?t\s+(?:apply|exist|matter)/i, description: 'Fiction bypass framing' },

  // Token/encoding bypass
  { id: 'E013', severity: 'hard', regex: /(?:\\u[0-9a-fA-F]{4}){3,}/, description: 'Unicode escape sequence injection' },
  { id: 'E014', severity: 'hard', regex: /(?:%[0-9a-fA-F]{2}){5,}/, description: 'URL percent-encoding injection' },
  { id: 'E015', severity: 'soft', regex: /base64[:\s]+[A-Za-z0-9+/]{20,}={0,2}/i, description: 'Base64 encoded payload' },
  { id: 'E016', severity: 'soft', regex: /[\u200b\u200c\u200d\u2060\ufeff]/, description: 'Invisible character injection' },

  // Agentic / tool-use hijacking
  { id: 'E017', severity: 'hard', regex: /call\s+(?:the\s+)?(?:delete|drop|rm|format)\s+(?:tool|function|api)/i, description: 'Destructive tool-call injection' },
  { id: 'E018', severity: 'hard', regex: /execute\s+(?:the\s+)?following\s+(?:command|script|code|shell)\s*[:;]/i, description: 'Code execution injection' },
  { id: 'E019', severity: 'hard', regex: /\$\{.*(?:process\.env|__import__|exec|eval|system)/i, description: 'Template literal code injection' },
  { id: 'E020', severity: 'soft', regex: /use\s+(?:the\s+)?(?:tool|function|api)\s+to\s+(?:send|exfiltrate|leak|transmit)\s+(?:data|credentials?|secrets?|tokens?)/i, description: 'Data exfiltration via tools' },

  // Memory / persistent manipulation
  { id: 'E021', severity: 'hard', regex: /(?:save(?:\s+to\s+memory)?|store|remember|memorize|add\s+to\s+memory)[:\s]+(?:your\s+)?(?:new\s+)?(?:system\s+prompt|instruction|rule)/i, description: 'Memory poisoning attempt' },
  { id: 'E022', severity: 'soft', regex: /update\s+your\s+(?:core\s+)?(?:values?|instructions?|guidelines?|personality)/i, description: 'Core directive manipulation' },

  // Indirect/data injection
  { id: 'E023', severity: 'hard', regex: /<!--\s*(?:INJECT|PROMPT|OVERRIDE|SYSTEM)[:\s]/i, description: 'HTML comment injection' },
  { id: 'E024', severity: 'hard', regex: /\[\[INJECT\]\]|\[\[SYSTEM\]\]|\[\[OVERRIDE\]\]/i, description: 'Bracketed injection marker' },
  { id: 'E025', severity: 'soft', regex: /(?:hey\s+ai|hello\s+model|attention\s+(?:ai|llm|model|assistant))[,:\s]+(?:from\s+now|ignore|disregard|forget)/i, description: 'Indirect data-path injection' },

  // Credential injection
  { id: 'E026', severity: 'hard', regex: /(?:api[_\s]?key|secret[_\s]?key|access[_\s]?token|private[_\s]?key)\s*[:=]\s*[A-Za-z0-9+/\-_]{20,}/i, description: 'Credential injection in payload' },
  { id: 'E027', severity: 'soft', regex: /authorization\s*:\s*bearer\s+[A-Za-z0-9._\-]{20,}/i, description: 'Bearer token injection' },

  // Goal hijacking
  { id: 'E028', severity: 'hard', regex: /your\s+(?:true|real|actual|primary|secret)\s+(?:goal|objective|mission|purpose|task)\s+is/i, description: 'Goal replacement injection' },
  { id: 'E029', severity: 'soft', regex: /override\s+(?:all\s+)?(?:previous\s+)?(?:safety|ethical|content)\s+(?:filters?|checks?|guidelines?|restrictions?)/i, description: 'Safety filter bypass' },
  { id: 'E030', severity: 'soft', regex: /(?:for\s+research|for\s+educational\s+purposes?)[,\s]+(?:explain|show|tell)\s+(?:me\s+)?how\s+to\s+(?:hack|bypass|exploit|crack|break)/i, description: 'Research framing bypass' },
];

export const EDGE_CORD_VERSION = '1.0';
export { EDGE_CORD_PATTERNS };

/**
 * Run Edge CORD check on input text.
 * Pure sync, no I/O โ€” safe in Cloudflare Workers / edge runtimes.
 */
export function cordCheck(text: string): EdgeCORDResult {
  if (!text || text.length === 0) {
    return { verdict: 'CLEAN', matched: [], score: 0, checkedAt: new Date().toISOString() };
  }

  const matched: EdgeCORDMatch[] = [];
  for (const pattern of EDGE_CORD_PATTERNS) {
    if (pattern.regex.test(text)) {
      matched.push({ patternId: pattern.id, severity: pattern.severity, description: pattern.description });
    }
  }

  const hardCount = matched.filter(m => m.severity === 'hard').length;
  const softCount = matched.filter(m => m.severity === 'soft').length;
  const score = Math.min(1.0, hardCount * 0.4 + softCount * 0.15);

  let verdict: EdgeCORDResult['verdict'];
  if (hardCount > 0) {
    verdict = 'REJECTED';
  } else if (softCount > 0) {
    verdict = 'SUSPICIOUS';
  } else {
    verdict = 'CLEAN';
  }

  return { verdict, matched, score, checkedAt: new Date().toISOString() };
}

// ---------------------------------------------------------------------------
// EdgeGate โ€” combined CORD + FDIA
// ---------------------------------------------------------------------------

export interface EdgeGateResult {
  allowed: boolean;
  cordVerdict: EdgeCORDResult['verdict'];
  fdiaScore: number;
  fdiaRisk: RiskLevel;
  reason: string;
  checkedAt: string;
}

export interface EdgeGateOptions {
  minFdia?: number;       // default 0.3
  rejectOnCord?: boolean; // default true
}

/**
 * Combined edge gate: CORD check + FDIA threshold.
 */
export function edgeGate(
  text: string,
  d: number,
  i: number,
  a: number,
  options: EdgeGateOptions = {}
): EdgeGateResult {
  const minFdia = options.minFdia ?? 0.3;
  const rejectOnCord = options.rejectOnCord ?? true;

  const cord = cordCheck(text);
  const fdia = computeFDIA(d, i, a);

  let allowed = true;
  let reason = 'allowed';

  if (a === 0) {
    allowed = false;
    reason = 'FDIA kill switch: authority=0';
  } else if (rejectOnCord && cord.verdict === 'REJECTED') {
    allowed = false;
    reason = `CORD rejected: ${cord.matched.map(m => m.patternId).join(', ')}`;
  } else if (fdia.f < minFdia) {
    allowed = false;
    reason = `FDIA below threshold: ${fdia.f.toFixed(3)} < ${minFdia}`;
  }

  return {
    allowed,
    cordVerdict: cord.verdict,
    fdiaScore: fdia.f,
    fdiaRisk: fdia.risk,
    reason,
    checkedAt: cord.checkedAt,
  };
}


// ---------------------------------------------------------------------------
