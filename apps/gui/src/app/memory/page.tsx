"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Empty, ErrorNote, PageBody, PageHeader, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type ReplaceHint } from "@/lib/desk-api";
import { TimeTravel } from "@/components/desk/memory/TimeTravel";

const KINDS = ["fact", "preference", "goal", "event", "skill", "conversation"];

export default function MemoryPage() {
  const { lang } = useLang();
  const [namespace, setNamespace] = useState<string>("");
  const [showRevoked, setShowRevoked] = useState(false);
  const [memoryRevision, setMemoryRevision] = useState(0);
  const list = useDeskData(() => desk.memories(namespace || undefined, showRevoked), [namespace, showRevoked], 20000);
  const [revoking, setRevoking] = useState<string | null>(null);
  const [reason, setReason] = useState("");
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("fact");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [hints, setHints] = useState<ReplaceHint[] | null>(null);
  const [replacing, setReplacing] = useState<{ id: string; text: string } | null>(null);

  const fail = (err: unknown) => setNote({ tone: "err", text: err instanceof Error ? err.message : String(err) });

  const store = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await desk.remember(content.trim(), kind, namespace || undefined);
      setNote({ tone: "ok", text: lang === "th" ? `บันทึกใน namespace ${r.namespace} แล้ว` : `Stored in namespace ${r.namespace}.` });
      setContent("");
      setHints(null);
      list.reload();
      setMemoryRevision((revision) => revision + 1);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  // Before storing, ask which existing memory this text may replace. A hint only: nothing changes until the person chooses.
  const add = async () => {
    setBusy(true);
    setNote(null);
    try {
      const found = await desk.memoryHints(content.trim(), namespace || undefined);
      if (found.hints.length) {
        setHints(found.hints);
        setBusy(false);
        return;
      }
    } catch {
      /* the hint is optional: store anyway */
    }
    setBusy(false);
    await store();
  };

  const replaceWith = async (oldId: string, text: string, after?: () => void) => {
    setBusy(true);
    setNote(null);
    try {
      const r = await desk.replaceMemory(oldId, text.trim(), namespace || undefined);
      setNote({ tone: "ok", text: lang === "th" ? `แทนที่แล้ว: ${r.old_id} ถูกเก็บไว้แต่ agent ไม่ใช้อีก${r.pin_moved ? " และกฎที่ปักหมุดย้ายมาที่ความจำใหม่" : ""}` : `Replaced: ${r.old_id} is kept on disk but no longer used${r.pin_moved ? "; the pinned rule moved to the new memory" : ""}.` });
      after?.();
      list.reload();
      setMemoryRevision((revision) => revision + 1);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const pin = async (m: { id: string; namespace: string; pinned_at?: string | null }) => {
    setBusy(true);
    setNote(null);
    try {
      await desk.pinMemory(m.id, !m.pinned_at, m.namespace);
      setNote({ tone: "ok", text: m.pinned_at ? (lang === "th" ? "เลิกปักหมุดแล้ว" : "Unpinned.") : (lang === "th" ? "ปักหมุดแล้ว: ทุก episode จะเห็นกฎนี้ ไม่ว่าเป้าหมายจะเป็นอะไร (สูงสุด 5 ข้อต่อคน)" : "Pinned: every episode is shown this rule, whatever the goal (at most 5 per person).") });
      list.reload();
      setMemoryRevision((revision) => revision + 1);
    } catch (err) {
      fail(err);
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (m: { id: string; namespace: string }) => {
    setBusy(true);
    setNote(null);
    try {
      await desk.revokeMemory(m.id, reason.trim(), m.namespace);
      setNote({ tone: "ok", text: lang === "th" ? "เพิกถอนแล้ว: ยังเก็บอยู่ในดิสก์เพื่อการตรวจสอบ แต่ agent จะไม่ใช้อีก" : "Revoked: it stays on disk for the audit, but the agent will not use it again." });
      setRevoking(null);
      setReason("");
      list.reload();
      setMemoryRevision((revision) => revision + 1);
    } catch (err) {
      setNote({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <PageHeader title={lang === "th" ? "ความจำ" : "Memory"}
        lead={lang === "th"
          ? "ข้อมูลของคุณที่ agent รู้ นี่คือ D ในสมการ FDIA: ยิ่งมีข้อมูลที่เกี่ยวข้องกับเป้าหมาย ค่า D ยิ่งสูง และงานเสี่ยงสูงจึงผ่านเกตได้ ความจำที่เกี่ยวข้องถูกดึงเข้า prompt อัตโนมัติและถูกใช้โดยอัลกอริทึม retrieval"
          : "What the agent knows about your world. This is D in the FDIA equation: the more relevant data you hold for a goal, the higher D, and the more risky work can pass the gate. Relevant memories reach the prompt automatically and feed the retrieval algorithms."} />
      <PageBody>
        <div className="grid gap-6 xl:grid-cols-[minmax(0,420px)_minmax(0,1fr)]">
          <Panel title={lang === "th" ? "เพิ่มข้อมูล" : "Add a fact"}>
            <label className="block">
              <span className="text-[13px] text-dl-muted">{lang === "th" ? "สิ่งที่ agent ควรรู้" : "What the agent should know"}</span>
              <textarea value={content} onChange={(e) => setContent(e.target.value)} rows={5} disabled={busy} maxLength={4000}
                placeholder={lang === "th" ? "ตัวอย่าง: งบประมาณของโครงการคือ 15,000 บาท และต้องตรวจสอบก่อนอนุมัติ" : "The staging database is stg-db-1; deploys go through the blue-green pipeline and migrations are reviewed first."}
                className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text placeholder:text-dl-muted/50" />
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Memory type"
                className="desk-focus desk-mono rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-xs text-dl-text">
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <Button onClick={add} disabled={busy || !content.trim()}>{busy ? (lang === "th" ? "กำลังบันทึก…" : "Saving…") : (lang === "th" ? "บันทึกความจำ" : "Remember")}</Button>
            </div>
            {hints ? (
              <div role="group" aria-label="This may replace" className="mt-3 space-y-2 rounded border border-dl-amber/50 p-3">
                <p className="text-[13px] text-dl-amber">{lang === "th" ? "ข้อความนี้อาจแทนที่ความจำที่มีอยู่แล้ว เลือกว่าจะทำอย่างไร (ยังไม่มีอะไรเปลี่ยน)" : "This may replace something you already told the agent. Nothing has changed yet."}</p>
                {hints.map((h) => (
                  <div key={h.id} className="space-y-1">
                    <p className="desk-mono break-words text-[12px] text-dl-muted">{h.id} · {h.score}: {h.content}</p>
                    <Button tone="amber" disabled={busy} onClick={() => replaceWith(h.id, content, () => { setContent(""); setHints(null); })}>{lang === "th" ? "แทนที่ข้อนี้" : "Replace this one"}</Button>
                  </div>
                ))}
                <div className="flex gap-2">
                  <Button tone="ghost" disabled={busy} onClick={store}>{lang === "th" ? "เก็บเป็นความจำใหม่ (ไม่แทนที่)" : "Store as a new memory"}</Button>
                  <Button tone="ghost" disabled={busy} onClick={() => setHints(null)}>{lang === "th" ? "ยกเลิก" : "Cancel"}</Button>
                </div>
              </div>
            ) : null}
            {note ? <p role="status" className={`mt-3 text-[13px] ${note.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{note.text}</p> : null}
            <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
              {lang === "th" ? "ความจำเก็บอยู่บนเครื่องนี้ใน RCTDB (SQLite) อย่าบันทึกข้อมูลลับ: ข้อความที่เรียกคืนจะถูกส่งเป็นข้อมูลให้โมเดล" : "Memories are stored on this machine in RCTDB (SQLite). Do not store secrets here: recalled text is placed in the model’s prompt."}
            </p>
          </Panel>

          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={namespace === "" ? "leaf" : "muted"}>
                <button onClick={() => setNamespace("")} className="desk-focus">all</button>
              </Badge>
              <Badge tone={showRevoked ? "amber" : "muted"}>
                <button onClick={() => setShowRevoked((v) => !v)} className="desk-focus" aria-pressed={showRevoked}>
                  {lang === "th" ? "แสดงที่เพิกถอนแล้ว" : "show revoked"}
                </button>
              </Badge>
              {list.data?.namespaces.map((n) => (
                <Badge key={n.namespace} tone={namespace === n.namespace ? "leaf" : "muted"}>
                  <button onClick={() => setNamespace(n.namespace)} className="desk-focus">{n.namespace} · {n.n}</button>
                </Badge>
              ))}
            </div>
            {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
            {list.data && !list.data.memories.length ? (
              <Empty title="Nothing remembered yet">Add a fact on the left, or ask the agent to remember something in Chat.</Empty>
            ) : null}
            {list.data?.memories.map((m) => (
              <Panel key={m.id} title={m.pinned_at ? `${m.memory_type} · ${lang === "th" ? "กฎที่ปักหมุด" : "pinned rule"}` : m.memory_type} aside={<span className="desk-mono text-[11px] text-dl-muted">{m.namespace} · used {m.accessed_count}×</span>}>
                <p className={`whitespace-pre-wrap break-words text-sm ${m.revoked_at ? "text-dl-muted line-through" : "text-dl-text"}`}>{m.content}</p>
                <p className="desk-mono mt-2 text-[11px] text-dl-muted">importance {m.importance} · {fmtTime(m.created_at)}</p>
                {m.revoked_at ? (
                  <p role="status" className="desk-mono mt-2 text-[12px] text-dl-amber">
                    {lang === "th" ? "เพิกถอนแล้ว" : "Revoked"} {fmtTime(m.revoked_at)}{m.revoked_reason ? ` · ${m.revoked_reason}` : ""} · {lang === "th" ? "ยังอยู่บนดิสก์ แต่ agent ไม่ใช้อีก" : "still on disk, no longer used by the agent"}
                  </p>
                ) : revoking === m.id ? (
                  <div className="mt-3 space-y-2">
                    <label className="block">
                      <span className="text-[12px] text-dl-muted">{lang === "th" ? "เหตุผล (จำเป็น, บันทึกในบันทึกตรวจสอบ)" : "Reason (required, written to the audit trail)"}</span>
                      <input value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} disabled={busy}
                        className="desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-xs text-dl-text" />
                    </label>
                    <div className="flex gap-2">
                      <Button tone="amber" onClick={() => revoke(m)} disabled={busy || !reason.trim()}>{lang === "th" ? "ยืนยันเพิกถอน" : "Confirm revoke"}</Button>
                      <Button tone="ghost" onClick={() => { setRevoking(null); setReason(""); }} disabled={busy}>{lang === "th" ? "ยกเลิก" : "Cancel"}</Button>
                    </div>
                    <p className="text-[12px] text-dl-muted">{lang === "th" ? "ข้อความจะไม่ถูกลบ: ถูกเก็บไว้ตามนโยบาย Zero-Delete" : "The text is not deleted: it is kept under the Zero-Delete policy."}</p>
                  </div>
                ) : replacing?.id === m.id ? (
                  <div className="mt-3 space-y-2">
                    <label className="block">
                      <span className="text-[12px] text-dl-muted">{lang === "th" ? "ข้อความใหม่ที่เป็นเวอร์ชันปัจจุบัน" : "The new text: the current version of this memory"}</span>
                      <textarea value={replacing.text} onChange={(e) => setReplacing({ id: m.id, text: e.target.value })} rows={3} maxLength={4000} disabled={busy}
                        className="desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text" />
                    </label>
                    <div className="flex gap-2">
                      <Button tone="amber" onClick={() => replaceWith(m.id, replacing.text, () => setReplacing(null))} disabled={busy || !replacing.text.trim()}>{lang === "th" ? "ยืนยันแทนที่" : "Confirm replace"}</Button>
                      <Button tone="ghost" onClick={() => setReplacing(null)} disabled={busy}>{lang === "th" ? "ยกเลิก" : "Cancel"}</Button>
                    </div>
                    <p className="text-[12px] text-dl-muted">{lang === "th" ? "ความจำเก่าไม่ถูกลบ: ยังอยู่ในประวัติและย้อนดูได้ แต่ agent จะไม่เห็นอีก" : "The old memory is not deleted: it stays in the history and in time travel, but the agent no longer sees it."}</p>
                  </div>
                ) : (
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Button tone="ghost" onClick={() => pin(m)} disabled={busy}>{m.pinned_at ? (lang === "th" ? "เลิกปักหมุด" : "Unpin") : (lang === "th" ? "ปักหมุดเป็นกฎ" : "Pin as a rule")}</Button>
                    <Button tone="ghost" onClick={() => setReplacing({ id: m.id, text: m.content })} disabled={busy}>{lang === "th" ? "แทนที่ด้วยข้อความใหม่" : "Replace"}</Button>
                    <Button tone="ghost" onClick={() => { setRevoking(m.id); setReason(""); }} disabled={busy}>{lang === "th" ? "เพิกถอน" : "Revoke"}</Button>
                  </div>
                )}
              </Panel>
            ))}
          </div>
        </div>
        <div className="mt-6"><TimeTravel namespace={namespace} refreshVersion={memoryRevision} /></div>
      </PageBody>
    </>
  );
}
