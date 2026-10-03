"use client";

import { useState } from "react";
import { Badge, Button, Code, Empty, Panel } from "@/components/desk/ui";
import { desk, type FdiaActionType, type FdiaPolicy, type FdiaRule, type FdiaState, type PolicySavePending } from "@/lib/desk-api";
import { BUILT_IN_THRESHOLD } from "@/lib/fdia-math";

type T = (en: string, th: string) => string;

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/50";
const label = "text-[12px] text-dl-muted";

export const EMPTY_POLICY: FdiaPolicy = {
  version: "1.0.0", policy_id: "owner-policy", policy_name: "Owner policy", default_fallback_A: 0, custom_safety_threshold: BUILT_IN_THRESHOLD,
  rules: [], blocked_action_patterns: [], require_human_dual_signoff: [], roles: { default_role: "developer", principals: {} }, jury_by_risk: {},
};

const NEW_RULE: FdiaRule = {
  rule_id: "", intent_patterns: [], action_type: "ALLOW", description: "", assigned_A: 1, require_human_confirmation: false,
  denied_paths: [], allowed_roles: [], human_approver_role: [], required_signatures: 1, jury_tier: "",
};

const ACTION_TONE: Record<FdiaActionType, "leaf" | "amber" | "rust"> = { ALLOW: "leaf", CONDITIONAL: "amber", REQUIRE_HUMAN_SIGNATURE: "rust" };

/** A list edited as text, committed on blur or Enter so a trailing comma is not eaten while typing. */
function ListInput({ value, onChange, placeholder, aria, lines = false }: {
  value: string[]; onChange: (v: string[]) => void; placeholder?: string; aria: string; lines?: boolean;
}) {
  const [text, setText] = useState(value.join(lines ? "\n" : ", "));
  const commit = () => {
    const parts = text.split(lines ? /\n+/ : /[,\n]+/).map((x) => x.trim()).filter(Boolean);
    onChange(parts);
    setText(parts.join(lines ? "\n" : ", "));
  };
  return lines ? (
    <textarea value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} rows={3} placeholder={placeholder} aria-label={aria} className={field} />
  ) : (
    <input value={text} onChange={(e) => setText(e.target.value)} onBlur={commit} onKeyDown={(e) => { if (e.key === "Enter") commit(); }}
      placeholder={placeholder} aria-label={aria} className={field} />
  );
}

function RuleCard({ rule, index, onChange, onRemove, state, T }: {
  rule: FdiaRule; index: number; onChange: (r: FdiaRule) => void; onRemove: () => void; state: FdiaState; T: T;
}) {
  const [open, setOpen] = useState(rule.rule_id === "");
  const signature = rule.action_type === "REQUIRE_HUMAN_SIGNATURE" || rule.require_human_confirmation;
  const set = (patch: Partial<FdiaRule>) => onChange({ ...rule, ...patch });
  return (
    <div className="rounded border border-dl-rule bg-dl-ink/40">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open}
        className="desk-focus flex w-full items-center justify-between gap-3 px-3 py-2 text-left">
        <span className="flex min-w-0 flex-wrap items-center gap-2">
          <span className="desk-mono text-[13px] text-dl-text">{rule.rule_id || T("(new rule)", "(กฎใหม่)")}</span>
          <Badge tone={ACTION_TONE[rule.action_type]}>{rule.action_type}</Badge>
          {signature ? <Badge tone="amber">{rule.required_signatures}× {T("signature", "ลายเซ็น")}</Badge> : null}
          {rule.jury_tier ? <Badge tone="fern">{T("jury", "คณะลูกขุน")} {rule.jury_tier}</Badge> : null}
        </span>
        <span className="desk-mono truncate text-[11px] text-dl-muted">{rule.intent_patterns.join(", ") || "—"}</span>
      </button>
      {open ? (
        <div className="grid gap-3 border-t border-dl-rule px-3 py-3 md:grid-cols-2">
          <label className="block"><span className={label}>{T("Rule name (letters, digits, - _ .)", "ชื่อกฎ (ตัวอักษร ตัวเลข - _ .)")}</span>
            <input value={rule.rule_id} onChange={(e) => set({ rule_id: e.target.value })} className={field} aria-label={`Rule ${index + 1} name`} /></label>
          <label className="block"><span className={label}>{T("What it does", "ทำอะไร")}</span>
            <select value={rule.action_type} onChange={(e) => set({ action_type: e.target.value as FdiaActionType })} className={field} aria-label={`Rule ${index + 1} action`}>
              <option value="ALLOW">{T("ALLOW · free to run", "ALLOW · รันได้เลย")}</option>
              <option value="CONDITIONAL">{T("CONDITIONAL · free unless an argument hits a forbidden path", "CONDITIONAL · รันได้ เว้นแต่ argument ตรง path ต้องห้าม")}</option>
              <option value="REQUIRE_HUMAN_SIGNATURE">{T("REQUIRE_HUMAN_SIGNATURE · waits for people", "REQUIRE_HUMAN_SIGNATURE · รอมนุษย์เซ็น")}</option>
            </select></label>
          <label className="block md:col-span-2"><span className={label}>{T("Tools it covers (patterns, comma separated; * is a wildcard)", "เครื่องมือที่ครอบคลุม (pattern คั่นด้วยจุลภาค; * คือ wildcard)")}</span>
            <ListInput value={rule.intent_patterns} onChange={(v) => set({ intent_patterns: v })} placeholder="read_*, recall" aria={`Rule ${index + 1} tools`} /></label>
          <label className="block md:col-span-2"><span className={label}>{T("Description (shown as the reason)", "คำอธิบาย (แสดงเป็นเหตุผล)")}</span>
            <input value={rule.description} onChange={(e) => set({ description: e.target.value })} className={field} aria-label={`Rule ${index + 1} description`} /></label>
          <label className="block"><span className={label}>{T("Forbidden paths, one per line (.env, .git/*, *.pem)", "path ต้องห้าม บรรทัดละหนึ่ง (.env, .git/*, *.pem)")}</span>
            <ListInput lines value={rule.denied_paths} onChange={(v) => set({ denied_paths: v })} placeholder={".env\n.git/*\n*.pem"} aria={`Rule ${index + 1} forbidden paths`} /></label>
          <label className="block"><span className={label}>{T("Only these roles may ask (empty = anyone; * = anyone)", "เฉพาะ role เหล่านี้ขอได้ (ว่าง = ใครก็ได้; * = ใครก็ได้)")}</span>
            <ListInput value={rule.allowed_roles} onChange={(v) => set({ allowed_roles: v })} placeholder="devops, admin" aria={`Rule ${index + 1} roles`} /></label>
          {signature ? (
            <>
              <label className="block"><span className={label}>{T("Approver roles that may sign (empty = any trusted key)", "role ของผู้อนุมัติที่เซ็นได้ (ว่าง = กุญแจที่ไว้ใจได้ทุกอัน)")}</span>
                <ListInput value={rule.human_approver_role} onChange={(v) => set({ human_approver_role: v })} placeholder="Security_Admin" aria={`Rule ${index + 1} approver roles`} /></label>
              <label className="block"><span className={label}>{T("Signatures needed, from distinct keys", "จำนวนลายเซ็นที่ต้องมี จากกุญแจคนละอัน")}</span>
                <select value={rule.required_signatures} onChange={(e) => set({ required_signatures: Number(e.target.value) })} className={field} aria-label={`Rule ${index + 1} signatures`}>
                  <option value={1}>1</option><option value={2}>2 · {T("dual sign-off", "เซ็นสองคน")}</option><option value={3}>3</option>
                </select></label>
            </>
          ) : null}
          <label className="block"><span className={label}>{T("Jury before it runs", "คณะลูกขุนก่อนรัน")}</span>
            <select value={rule.jury_tier} onChange={(e) => set({ jury_tier: e.target.value })} className={field} aria-label={`Rule ${index + 1} jury`}>
              <option value="">{T("none", "ไม่ใช้")}</option>
              {state.limits.jury_tiers.map((tier) => <option key={tier} value={tier}>{tier}</option>)}
            </select></label>
          <label className="flex items-end gap-2 text-[13px] text-dl-text">
            <input type="checkbox" checked={rule.require_human_confirmation} onChange={(e) => set({ require_human_confirmation: e.target.checked })} className="mb-1 accent-[var(--dl-leaf)]" />
            <span>{T("Always ask a human, whatever the type", "ถามมนุษย์เสมอ ไม่ว่าชนิดอะไร")}</span>
          </label>
          <div className="md:col-span-2"><Button tone="ghost" onClick={onRemove}>{T("Remove this rule", "ลบกฎนี้")}</Button></div>
        </div>
      ) : null}
    </div>
  );
}

function principalsToText(p: Record<string, string>): string {
  return Object.entries(p).map(([who, role]) => `${who} = ${role}`).join("\n");
}

function textToPrincipals(text: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const line of text.split(/\n+/)) {
    const [who, ...rest] = line.split("=");
    const role = rest.join("=").trim();
    if (who && who.trim() && role) out[who.trim()] = role;
  }
  return out;
}

export type PolicyMessage = { tone: "leaf" | "rust" | "amber"; text: string; list?: string[] } | null;

export function Policy({ state, draft, setDraft, dirty, reload, message, setMessage, T }: {
  state: FdiaState; draft: FdiaPolicy; setDraft: (p: FdiaPolicy) => void; dirty: boolean; reload: () => void;
  message: PolicyMessage; setMessage: (m: PolicyMessage) => void; T: T;
}) {
  const [busy, setBusy] = useState(false);
  const [waiting, setWaiting] = useState<{ kind: "save" | "disable"; info: PolicySavePending } | null>(null);
  const [understand, setUnderstand] = useState(false);
  const [json, setJson] = useState<string | null>(null);
  const set = (patch: Partial<FdiaPolicy>) => setDraft({ ...draft, ...patch });
  const blocksEverything = draft.rules.length === 0 && draft.default_fallback_A <= 0;
  const needsConfirm = blocksEverything || draft.default_fallback_A > 0;

  const fromTemplate = async (name: "balanced" | "strict") => {
    setBusy(true); setMessage(null);
    try { setDraft((await desk.fdiaTemplate(name)).policy); setUnderstand(false); }
    catch (err) { setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) }); }
    finally { setBusy(false); }
  };

  const save = async () => {
    setBusy(true); setMessage(null);
    try {
      const checked = await desk.fdiaValidate(draft);
      if (!checked.valid) { setMessage({ tone: "rust", text: T("The policy has problems:", "นโยบายมีปัญหา:"), list: checked.errors }); return; }
      const saved = await desk.fdiaSave(draft, waiting?.kind === "save" ? waiting.info.approval_id : undefined);
      if ("pending_signature" in saved) {
        setWaiting({ kind: "save", info: saved });
        setMessage({ tone: "amber", text: T("This server asks for a signature before the rules change. Sign the request, then apply it.", "server นี้ต้องมีลายเซ็นก่อนเปลี่ยนกฎ เซ็นคำขอแล้วกดใช้") });
        return;
      }
      setWaiting(null);
      setMessage({ tone: "leaf", text: T(`Saved ${saved.rules} rule(s). It applies to the next tool call; nothing restarts.`, `บันทึก ${saved.rules} กฎแล้ว มีผลกับการเรียกเครื่องมือครั้งถัดไป ไม่ต้องรีสตาร์ต`) });
      reload();
    } catch (err) { setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) }); }
    finally { setBusy(false); }
  };

  const disable = async () => {
    setBusy(true); setMessage(null);
    try {
      const r = await desk.fdiaDisable(waiting?.kind === "disable" ? waiting.info.approval_id : undefined);
      if ("pending_signature" in r) {
        setWaiting({ kind: "disable", info: r });
        setMessage({ tone: "amber", text: T("Turning the policy off needs a signature on this server. Sign the request, then apply it.", "การปิดนโยบายต้องมีลายเซ็นบน server นี้ เซ็นคำขอแล้วกดใช้") });
        return;
      }
      setWaiting(null);
      setMessage({ tone: "amber", text: T(`Policy turned off. The file was kept as ${r.archived_as}.`, `ปิดนโยบายแล้ว เก็บไฟล์ไว้เป็น ${r.archived_as}`) });
      reload();
    }
    catch (err) { setMessage({ tone: "rust", text: err instanceof Error ? err.message : String(err) }); }
    finally { setBusy(false); }
  };

  const applyJson = (text: string) => {
    try { setDraft({ ...EMPTY_POLICY, ...JSON.parse(text) } as FdiaPolicy); setJson(null); setMessage(null); }
    catch { setMessage({ tone: "rust", text: T("That is not valid JSON.", "JSON ไม่ถูกต้อง") }); }
  };

  return (
    <div className="space-y-6">
      <Panel title={T("Status", "สถานะ")} aside={state.exists && !state.error ? <Badge tone="leaf">{T("active", "ใช้งานอยู่")}</Badge> : state.error ? <Badge tone="rust">{T("broken file", "ไฟล์เสีย")}</Badge> : <Badge tone="amber">{T("no policy", "ยังไม่มีนโยบาย")}</Badge>}>
        {state.error ? (
          <p role="alert" className="mb-3 rounded border border-dl-rust/50 bg-dl-rust/10 px-3 py-2 text-[13px] text-dl-text">
            {T("The policy file cannot be read, so the agent refuses every tool call until it is fixed (a broken policy never turns into no policy). ", "อ่านไฟล์นโยบายไม่ได้ agent จึงปฏิเสธทุกการเรียกจนกว่าจะแก้ (นโยบายเสียจะไม่กลายเป็นไม่มีนโยบาย) ")}
            <span className="desk-mono text-dl-muted">{state.error}</span>
          </p>
        ) : null}
        <p className="text-[13px] leading-relaxed text-dl-muted">
          {state.exists && !state.error
            ? T(`Every tool call is judged against ${state.policy?.rules.length ?? 0} rule(s).`, `ทุกการเรียกเครื่องมือถูกตัดสินด้วย ${state.policy?.rules.length ?? 0} กฎ`)
            : T("No policy: only the built-in gate applies (12 risky tools; repository writes always wait for a signature). Start from a template below, or write your own.", "ยังไม่มีนโยบาย: ใช้เฉพาะด่านในตัว (เครื่องมือเสี่ยง 12 ตัว; การเขียน repo ต้องรอลายเซ็นเสมอ) เริ่มจากแม่แบบด้านล่าง หรือเขียนเอง")}
        </p>
        <p className="desk-mono mt-2 text-[11px] text-dl-muted">{state.path}{state.digest ? ` · digest ${state.digest.slice(0, 12)}` : ""}</p>
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button tone="ghost" onClick={() => fromTemplate("balanced")} disabled={busy}>{T("Start from: balanced", "เริ่มจาก: balanced")}</Button>
          <Button tone="ghost" onClick={() => fromTemplate("strict")} disabled={busy}>{T("Start from: strict (jury on shell, threshold 0.6)", "เริ่มจาก: strict (jury กับ shell, เกณฑ์ 0.6)")}</Button>
          <Button tone="ghost" onClick={() => setDraft(EMPTY_POLICY)} disabled={busy}>{T("Empty", "ว่าง")}</Button>
          {state.exists ? <Button tone="amber" onClick={disable} disabled={busy}>{T("Turn the policy off (file kept)", "ปิดนโยบาย (เก็บไฟล์ไว้)")}</Button> : null}
        </div>
      </Panel>

      <Panel title={T("Rules", "กฎ")} aside={<span className="desk-mono text-[11px] text-dl-muted">{draft.rules.length}/{state.limits.max_rules}</span>}>
        <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">
          {T("When several rules match a tool, the most restrictive one wins (signature, then conditional, then allow), whatever their order here.", "เมื่อหลายกฎตรงกับเครื่องมือเดียว กฎที่เข้มที่สุดชนะ (ต้องเซ็น แล้วมีเงื่อนไข แล้วอนุญาต) ไม่ขึ้นกับลำดับที่นี่")}
        </p>
        {draft.rules.length === 0 ? <Empty title={T("No rules yet", "ยังไม่มีกฎ")}>{T("With zero rules and the zero-trust fallback every tool is refused. Add a rule or start from a template.", "ไม่มีกฎและใช้ zero-trust ทุกเครื่องมือจะถูกปฏิเสธ เพิ่มกฎ หรือเริ่มจากแม่แบบ")}</Empty> : (
          <div className="space-y-2">
            {draft.rules.map((rule, i) => (
              <RuleCard key={i} rule={rule} index={i} state={state} T={T}
                onChange={(r) => set({ rules: draft.rules.map((x, j) => (j === i ? r : x)) })}
                onRemove={() => set({ rules: draft.rules.filter((_, j) => j !== i) })} />
            ))}
          </div>
        )}
        <div className="mt-3"><Button onClick={() => set({ rules: [...draft.rules, { ...NEW_RULE }] })} disabled={draft.rules.length >= state.limits.max_rules}>{T("Add a rule", "เพิ่มกฎ")}</Button></div>
      </Panel>

      <div className="grid gap-6 xl:grid-cols-2">
        <Panel title={T("Floor and fallback", "เกณฑ์ขั้นต่ำและ fallback")}>
          <label className="block">
            <span className="flex justify-between text-[13px] text-dl-muted"><span>{T("Threshold F must reach", "เกณฑ์ที่ F ต้องถึง")}</span><span className="desk-mono text-dl-text">{draft.custom_safety_threshold.toFixed(2)}</span></span>
            <input type="range" min={0} max={1} step={0.05} value={draft.custom_safety_threshold} aria-label="Threshold"
              onChange={(e) => set({ custom_safety_threshold: Number(e.target.value) })} className="desk-focus w-full accent-[var(--dl-leaf)]" />
          </label>
          <p className="mt-1 text-[12px] leading-relaxed text-dl-muted">
            {draft.custom_safety_threshold < BUILT_IN_THRESHOLD
              ? T(`Below ${BUILT_IN_THRESHOLD} has no effect: the built-in floor stays at ${BUILT_IN_THRESHOLD}.`, `ต่ำกว่า ${BUILT_IN_THRESHOLD} ไม่มีผล: เกณฑ์ในตัวคงที่ที่ ${BUILT_IN_THRESHOLD}`)
              : T("Reads you allow are not held to it; risky tools and non-ALLOW rules are.", "การอ่านที่คุณอนุญาตไม่ถูกจำกัดด้วยเกณฑ์นี้ เครื่องมือเสี่ยงและกฎที่ไม่ใช่ ALLOW ถูกจำกัด")}
          </p>
          <label className="mt-4 flex items-start gap-2 text-[13px] text-dl-text">
            <input type="checkbox" checked={draft.default_fallback_A <= 0} onChange={(e) => set({ default_fallback_A: e.target.checked ? 0 : 1 })} className="mt-1 accent-[var(--dl-leaf)]" />
            <span>{T("Zero trust: a tool no rule mentions has A = 0", "Zero trust: เครื่องมือที่ไม่มีกฎใดกล่าวถึง A = 0")}
              <span className="block text-[12px] text-dl-muted">{T("Recommended. Unticked, an unlisted tool is allowed.", "แนะนำ ถ้าไม่ติ๊ก เครื่องมือที่ไม่อยู่ในกฎจะถูกอนุญาต")}</span></span>
          </label>
        </Panel>

        <Panel title={T("Forbidden whatever the rule", "ห้ามไม่ว่ากฎใด")}>
          <label className="block"><span className={label}>{T("Tool patterns that are always refused, even with a signature", "pattern ของเครื่องมือที่ปฏิเสธเสมอ แม้มีลายเซ็น")}</span>
            <ListInput value={draft.blocked_action_patterns} onChange={(v) => set({ blocked_action_patterns: v })} placeholder="*drop_database*, *export_credentials*" aria="Forbidden patterns" /></label>
          <label className="mt-3 block"><span className={label}>{T("Always need two signatures", "ต้องมีสองลายเซ็นเสมอ")}</span>
            <ListInput value={draft.require_human_dual_signoff} onChange={(v) => set({ require_human_dual_signoff: v })} placeholder="deploy_to_production, grant_admin_privilege" aria="Dual sign-off" /></label>
        </Panel>

        <Panel title={T("Who is asking", "ใครเป็นผู้ขอ")}>
          <p className="mb-2 text-[12px] leading-relaxed text-dl-muted">
            {T("A role comes from the identity the server attached to the request (the user or the chat sender), never from what the request says about itself.", "role มาจากตัวตนที่ server ผูกกับคำขอ (ผู้ใช้หรือผู้ส่งในแชท) ไม่ใช่จากที่คำขอบอกเอง")}
          </p>
          <label className="block"><span className={label}>{T("Role when nobody is listed", "role เมื่อไม่อยู่ในรายการ")}</span>
            <input value={draft.roles.default_role} onChange={(e) => set({ roles: { ...draft.roles, default_role: e.target.value } })} className={field} aria-label="Default role" /></label>
          <label className="mt-3 block"><span className={label}>{T("identity = role, one per line", "ตัวตน = role บรรทัดละหนึ่ง")}</span>
            <PrincipalsInput value={draft.roles.principals} onChange={(p) => set({ roles: { ...draft.roles, principals: p } })} /></label>
        </Panel>

        <Panel title={T("Jury by the goal's risk", "คณะลูกขุนตามความเสี่ยงของเป้าหมาย")}>
          <p className="mb-2 text-[12px] leading-relaxed text-dl-muted">
            {T("Before an episode starts, a goal the intent compiler rates at this level needs the chosen jury to agree.", "ก่อนเริ่ม episode เป้าหมายที่ intent compiler ประเมินที่ระดับนี้ ต้องให้คณะลูกขุนที่เลือกเห็นด้วย")}
          </p>
          <div className="grid grid-cols-3 gap-2">
            {state.limits.risk_levels.map((risk) => (
              <label key={risk} className="block"><span className={label}>{risk}</span>
                <select value={draft.jury_by_risk[risk] ?? ""} aria-label={`Jury for ${risk}`} className={field}
                  onChange={(e) => { const next = { ...draft.jury_by_risk }; if (e.target.value) next[risk] = e.target.value; else delete next[risk]; set({ jury_by_risk: next }); }}>
                  <option value="">{T("none", "ไม่ใช้")}</option>
                  {state.limits.jury_tiers.map((tier) => <option key={tier} value={tier}>{tier}</option>)}
                </select></label>
            ))}
          </div>
          <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
            {state.jury.configured
              ? <><Badge tone="leaf">{T("jury members configured", "ตั้งค่าสมาชิกแล้ว")}</Badge> <span className="desk-mono">{state.jury.path}</span></>
              : <><Badge tone="amber">{T("no jury members yet", "ยังไม่ตั้งสมาชิก")}</Badge> {T("A rule that needs a jury is refused until members exist. Create ", "กฎที่ต้องใช้คณะลูกขุนจะถูกปฏิเสธจนกว่าจะมีสมาชิก สร้างไฟล์ ")}<Code>{state.jury.path}</Code> {T("(see README, SignedAI jury).", "(ดู README หัวข้อ SignedAI jury)")}</>}
          </p>
        </Panel>
      </div>

      <Panel title={T("Approvers you trust", "ผู้อนุมัติที่คุณไว้ใจ")}>
        {state.approvers.length ? (
          <ul className="divide-y divide-dl-rule/60">
            {state.approvers.map((a) => (
              <li key={a.key_prefix} className="flex items-center justify-between gap-3 py-2 text-[13px]">
                <span className="desk-mono text-dl-text">{a.name}</span>
                <span className="desk-mono text-[11px] text-dl-muted">{a.key_prefix}…</span>
                {a.role ? <Badge tone="fern">{a.role}</Badge> : <Badge tone="muted">{T("no role", "ไม่มี role")}</Badge>}
              </li>
            ))}
          </ul>
        ) : <p className="text-[13px] text-dl-amber">{T("Nobody is trusted yet, so nothing that needs a signature can ever be approved.", "ยังไม่มีผู้อนุมัติที่ไว้ใจ สิ่งที่ต้องเซ็นจึงไม่มีทางผ่าน")}</p>}
        <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
          {T("Add one on the machine that will sign: ", "เพิ่มบนเครื่องที่จะเป็นผู้เซ็น: ")}<Code>delentia approvals keygen --out ~/keys/sec.pem --trust alice --role Security_Admin</Code>.
          {" "}{T("The Desk never holds a private key; the list shows only a key's first 12 characters.", "Desk ไม่เก็บ private key; รายการแสดงแค่ 12 ตัวแรกของกุญแจ")}
        </p>
      </Panel>

      <Panel title={T("Save", "บันทึก")} aside={dirty ? <Badge tone="amber">{T("unsaved changes", "ยังไม่ได้บันทึก")}</Badge> : <Badge tone="muted">{T("saved", "บันทึกแล้ว")}</Badge>}>
        {needsConfirm ? (
          <label className="mb-3 flex items-start gap-2 text-[13px] text-dl-text">
            <input type="checkbox" checked={understand} onChange={(e) => setUnderstand(e.target.checked)} className="mt-1 accent-[var(--dl-leaf)]" />
            <span>{blocksEverything
              ? T("I understand this policy has no rules, so every tool will be refused.", "ฉันเข้าใจว่านโยบายนี้ไม่มีกฎ ทุกเครื่องมือจะถูกปฏิเสธ")
              : T("I understand that tools no rule mentions will be allowed.", "ฉันเข้าใจว่าเครื่องมือที่ไม่มีกฎกล่าวถึงจะถูกอนุญาต")}</span>
          </label>
        ) : null}
        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={busy || (needsConfirm && !understand)}>{busy ? "…" : T("Check and save", "ตรวจและบันทึก")}</Button>
          <Button tone="ghost" onClick={() => setJson(JSON.stringify(draft, null, 2))}>{T("Edit as JSON", "แก้เป็น JSON")}</Button>
          <span className="text-[12px] text-dl-muted">{T("Same file as ", "ไฟล์เดียวกับ ")}<Code>delentia fdia</Code>. {T("Each save is recorded in the audit trail.", "ทุกการบันทึกถูกบันทึกใน audit trail")}</span>
        </div>
        {message ? (
          <div role="status" className={`mt-3 text-[13px] ${message.tone === "leaf" ? "text-dl-leaf" : message.tone === "amber" ? "text-dl-amber" : "text-dl-rust"}`}>
            <p>{message.text}</p>
            {message.list ? <ul className="mt-1 list-disc pl-5">{message.list.map((e) => <li key={e}>{e}</li>)}</ul> : null}
          </div>
        ) : null}
        {waiting ? (
          <div className="mt-4 rounded border border-dl-amber/60 bg-dl-amber/10 p-3 text-[13px] leading-relaxed text-dl-text">
            <p>{T("Waiting for a signature. Request ", "รอลายเซ็น คำขอ ")}<Code>{waiting.info.approval_id}</Code> {T("is bound to this exact policy.", "ผูกกับนโยบายฉบับนี้เท่านั้น")}</p>
            <p className="mt-1 text-dl-muted">{T("On the machine that holds the approver key: ", "บนเครื่องที่มีกุญแจผู้อนุมัติ: ")}<Code>delentia approvals approve {waiting.info.approval_id} --key &lt;key&gt;</Code></p>
            <div className="mt-2 flex gap-2">
              <Button onClick={waiting.kind === "save" ? save : disable} disabled={busy}>{T("It is signed: apply", "เซ็นแล้ว: ใช้เลย")}</Button>
              <Button tone="ghost" onClick={() => setWaiting(null)}>{T("Forget this request", "ยกเลิกคำขอนี้")}</Button>
            </div>
          </div>
        ) : null}
        {json !== null ? (
          <div className="mt-4">
            <textarea value={json} onChange={(e) => setJson(e.target.value)} rows={14} aria-label="Policy JSON" className={`${field} font-mono text-[12px]`} />
            <div className="mt-2 flex gap-2"><Button onClick={() => applyJson(json)}>{T("Use this JSON", "ใช้ JSON นี้")}</Button><Button tone="ghost" onClick={() => setJson(null)}>{T("Close", "ปิด")}</Button></div>
          </div>
        ) : null}
      </Panel>
    </div>
  );
}

function PrincipalsInput({ value, onChange }: { value: Record<string, string>; onChange: (p: Record<string, string>) => void }) {
  const [text, setText] = useState(principalsToText(value));
  return (
    <textarea value={text} rows={3} placeholder={"alice = devops\ntelegram:12345 = admin"} aria-label="Identities and roles"
      onChange={(e) => setText(e.target.value)} onBlur={() => { const parsed = textToPrincipals(text); onChange(parsed); setText(principalsToText(parsed)); }} className={field} />
  );
}
