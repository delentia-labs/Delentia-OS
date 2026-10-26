"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type Checkpoint } from "@/lib/desk-api";

function state(c: Checkpoint, th: boolean) {
  if (c.rolled_back_at) return { tone: "muted" as const, text: th ? "ย้อนกลับแล้ว" : "rolled back" };
  if (!c.protected) return { tone: "rust" as const, text: th ? "ไม่มีการป้องกัน" : "unprotected" };
  return { tone: "leaf" as const, text: th ? "ย้อนกลับได้" : "can be rolled back" };
}

export default function CheckpointsPage() {
  const { lang } = useLang();
  const L = (en: string, thai: string) => (lang === "th" ? thai : en);
  const list = useDeskData(() => desk.checkpoints(), [], 15000);
  const [open, setOpen] = useState<{ id: number; diff: string } | null>(null);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string; force?: number } | null>(null);
  const [busy, setBusy] = useState(false);

  const show = async (id: number) => {
    try { setOpen({ id, diff: (await desk.checkpointDiff(id)).diff || (lang === "th" ? "(ไม่มีความต่าง)" : "(no difference)") }); } catch (e) { setMessage({ tone: "err", text: e instanceof Error ? e.message : String(e) }); }
  };
  const rollback = async (id: number, force = false) => {
    setBusy(true);
    setMessage(null);
    try {
      const r = await desk.checkpointRollback(id, force);
      setMessage({ tone: "ok", text: `${r.path}: ${r.result}${r.undo_checkpoint ? ` (undo: checkpoint #${r.undo_checkpoint})` : ""}` });
      setOpen(null);
      list.reload();
    } catch (e) {
      const text = e instanceof Error ? e.message : String(e);
      setMessage({ tone: "err", text, force: text.includes("no longer holds") ? id : undefined });
    } finally {
      setBusy(false);
    }
  };

  const d = list.data;
  return (
    <>
      <PageHeader title={lang === "th" ? "Checkpoint ไฟล์" : "Checkpoints"}
        lead={lang === "th"
          ? "ก่อน agent เขียนหรือแก้ไฟล์ ระบบเก็บเนื้อหาเดิมไว้ ย้อนกลับได้เฉพาะเมื่อไฟล์ยังเป็นสิ่งที่ agent เขียน (ถ้าคุณแก้ต่อ ระบบไม่ทับ ยกเว้นสั่ง force) การย้อนกลับเองก็ย้อนได้อีก ไม่มีอะไรถูกลบ"
          : "Before the agent writes or patches a file, its previous content is stored. A rollback only restores it if the file still holds what the agent wrote (your later edits are never overwritten without force), and a rollback can itself be undone. Nothing is deleted."} />
      <PageBody>
        {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}
        {message ? (
          <div role="status" className={`mb-4 text-[13px] ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>
            <p>{message.text}</p>
            {message.force ? <div className="mt-2"><Button tone="amber" onClick={() => rollback(message.force as number, true)} disabled={busy}>{L("Restore anyway (keeps your current content as a checkpoint)", "กู้คืนต่อไป (เก็บเนื้อหาปัจจุบันของคุณไว้เป็น checkpoint)")}</Button></div> : null}
          </div>
        ) : null}
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,460px)]">
          <Panel title={L("Checkpoints", "Checkpoint")} aside={d ? <Badge>{d.status.checkpoints}</Badge> : undefined}>
            {d && !d.checkpoints.length ? <Empty title={L("No file has been written by the agent yet", "เอเจนต์ยังไม่เคยเขียนไฟล์ใด")}>{L("Writes and patches through ", "การเขียนและการแก้ผ่าน ")}<Code>delentia_write_repo_file</Code>{L(" and ", " และ ")}<Code>delentia_patch_repo_file</Code>{L(" appear here.", " จะแสดงที่นี่")}</Empty> : null}
            <ul className="divide-y divide-dl-rule/60">
              {d?.checkpoints.map((c) => {
                const st = state(c, lang === "th");
                return (
                  <li key={c.id} className="flex flex-wrap items-center gap-2 py-2">
                    <span className="desk-mono w-10 text-[12px] text-dl-muted">#{c.id}</span>
                    <span className="min-w-0 flex-1 truncate text-[13px] text-dl-text" title={c.rel_path}>{c.rel_path}</span>
                    <Badge>{c.existed_before ? L("changed", "แก้ไข") : L("new file", "ไฟล์ใหม่")}</Badge>
                    <Badge tone={st.tone}>{st.text}</Badge>
                    <span className="desk-mono text-[11px] text-dl-muted">{fmtTime(new Date(c.created_at * 1000).toISOString())}</span>
                    <Button tone="ghost" onClick={() => show(c.id)}>{L("Diff", "ดูความต่าง")}</Button>
                    {!c.rolled_back_at && c.protected ? <Button tone="amber" onClick={() => rollback(c.id)} disabled={busy}>{L("Roll back", "ย้อนกลับ")}</Button> : null}
                  </li>
                );
              })}
            </ul>
          </Panel>
          <div className="space-y-6">
            {d ? (
              <Panel title={L("Storage", "พื้นที่เก็บ")}>
                <Row label={L("Checkpoints", "Checkpoint")}>{d.status.checkpoints}</Row>
                <Row label={L("Unprotected (over the size limit)", "ไม่มีการป้องกัน (เกินขีดจำกัดขนาด)")}>{d.status.unprotected}</Row>
                <Row label={L("Stored content", "เนื้อหาที่เก็บไว้")}>{(d.status.stored_bytes / 1024).toFixed(1)} KB</Row>
                <Row label={L("On", "เปิดอยู่")}>{d.status.enabled ? L("yes", "ใช่") : L("no (DELENTIA_CHECKPOINTS=0)", "ไม่ (DELENTIA_CHECKPOINTS=0)")}</Row>
                <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">{L("Covers files written through the agent's file tools, not what a shell command changes. The runtime never deletes a checkpoint; clearing old ones is your decision, outside this page.", "ครอบคลุมไฟล์ที่เขียนผ่านเครื่องมือไฟล์ของเอเจนต์ ไม่รวมสิ่งที่คำสั่งเชลล์เปลี่ยน ระบบไม่เคยลบ checkpoint การล้างอันเก่าเป็นการตัดสินใจของคุณ นอกหน้านี้")}</p>
              </Panel>
            ) : null}
            {open ? (
              <Panel title={`${L("Diff of", "ความต่างของ")} #${open.id}`} aside={<Button tone="ghost" onClick={() => setOpen(null)}>{L("Close", "ปิด")}</Button>}>
                <pre tabIndex={0} className="desk-mono max-h-96 overflow-auto whitespace-pre-wrap rounded border border-dl-rule bg-dl-ink p-3 text-[12px] text-dl-muted">{open.diff}</pre>
              </Panel>
            ) : null}
          </div>
        </div>
      </PageBody>
    </>
  );
}
