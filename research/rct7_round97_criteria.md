# RCT-7 round 97: criteria written BEFORE the code and the measurement

Scope: close the gaps of the creator's RCT-7 (R1-R7, definition v0.3) that a RULE can close. What needs a capable model (general understanding of the request, unknowns the
words do not show, before-act questions about vague intent) is out of scope here and stays labelled as such.

Everything below is decided without a language model. The cases of the measurement are written by the author of the rules, so a pass is a regression guard, not independent
evidence; each measurement says how many cases were written before the code and which were added after a failure.

## W1 the wait ends (R5/R7 "ask, wait, then continue")
* An answer to a question sticks to the EXACT goal it was asked about (whitespace-normalised equality, same person). The next time that person sends that goal, the episode runs on the
  revised intent (original words + the person's answer, labelled), and the answer is consumed once.
* Pass: (a) used once, never twice; (b) another person's identical goal does not pick it up; (c) an expired or cancelled question is not used; (d) a different goal does not pick it up;
  (e) an infrastructure failure (model unreachable) gives the answer back; (f) "accept" ends the question without running anything; (g) requirement overriding: an answer that states a
  new requirement of the same kind replaces the old one (the original "answer in Thai" plus the answer "English is fine: in English" must not stop again), and WITHOUT such an answer the
  same mismatch asks again (negative control).
* A clarification answer never lifts a gate, a forbidden path or a signature requirement (existing property; one test repeats it for the continued episode).

## W5 more requirements a rule can read and test (R2/R7)
New kinds: `max_words` ("in at most/under N words"), `item_count` ("list N items / N bullet points" / "N ข้อ"), `max_chars` ("under N characters" / "ไม่เกิน N ตัวอักษร").
Thai word counts are NOT checked (Thai has no spaces; a count would be a guess).
* False-stop rule, measured on a labelled set of at least 40 NEW cases (20 that must pass, 20 that must stop) written before the code: at most 2 false stops among the must-pass cases
  and at least 17 of the 20 must-stop cases stopped. The earlier P6 set (60 cases) must give the same result as before (1 false stop, 20 of 20).
* If the rule is missed or false-stops more than allowed, the kind is not enabled (the code stays out), and the result is reported as it is.

## W3 deconstruction without a model (R3)
`parts_of(goal)`: only explicit enumerations (numbered or bulleted lists, "first ... then ... finally", Thai "ก่อน ... แล้ว ..."); anything else is ONE part, never a guess.
* Pass: on 20 labelled goals written before the code, the parts equal the expected list in at least 18; a goal without an enumeration is never split (0 of 10 wrongly split).

## W2 unknowns by rule (R1)
`unknowns_for(goal, workspace)`: (a) a file the goal tells the agent to READ, EDIT or SUMMARISE whose name exists nowhere in the workspace and that no creation verb explains;
(b) a goal that is only a reference with no antecedent ("fix it", "do that again", "แก้อันนั้น") when there is no conversation to refer to.
* Reported in the plan always (information). A before-act question is asked only with DELENTIA_ASK_AND_WAIT=1.
* Pass on a labelled set of at least 40 cases (20 real unknowns, 20 that look similar but are fine, e.g. a file in a sub-folder, a file to be created, a pronoun with context):
  at most 2 false unknowns, at least 17 of the 20 real ones found.

## W4 the plan reaches every caller (R6)
* The result of every governed episode carries `rct7_plan` ({steps, route, conditions, parts, unknowns}); the Desk event carries the same fields.
* Chat channels: the question reaches the person (a stopped episode no longer sends the held-back answer as if it were the result); `/questions`, `/answer`, `/accept` exist and touch
  only the sender's own questions. A plan sent BEFORE the first tool on chat channels is NOT built here (each of the seven gateways runs its own loop); it is listed as open.

## Not claimed
Nothing here measures whether a language model does better with the plan or the questions. The answer "is it RCT-7 complete" stays: R1, R3 and R5 are complete only for the
rule-checkable part; the rest needs a model that can drive the loop and a held-out set.
