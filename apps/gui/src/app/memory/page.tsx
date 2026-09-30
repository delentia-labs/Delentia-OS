"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Empty, ErrorNote, PageBody, PageHeader, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const KINDS = ["fact", "preference", "goal", "event", "skill", "conversation"];

export default function MemoryPage() {
  const { lang } = useLang();
  const [namespace, setNamespace] = useState<string>("");
  const list = useDeskData(() => desk.memories(namespace || undefined), [namespace], 20000);
  const [content, setContent] = useState("");
  const [kind, setKind] = useState("fact");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const add = async () => {
    setBusy(true);
    setNote(null);
    try {
      const r = await desk.remember(content.trim(), kind, namespace || undefined);
      setNote({ tone: "ok", text: `Stored in namespace ${r.namespace}.` });
      setContent("");
      list.reload();
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
                placeholder="The staging database is stg-db-1; deploys go through the blue-green pipeline and migrations are reviewed first."
                className="desk-focus desk-mono mt-2 w-full rounded border border-dl-rule bg-dl-ink p-2 text-[13px] text-dl-text placeholder:text-dl-muted/50" />
            </label>
            <div className="mt-3 flex flex-wrap items-center gap-3">
              <select value={kind} onChange={(e) => setKind(e.target.value)} aria-label="Memory type"
                className="desk-focus desk-mono rounded border border-dl-rule bg-dl-ink px-2 py-1.5 text-xs text-dl-text">
                {KINDS.map((k) => <option key={k} value={k}>{k}</option>)}
              </select>
              <Button onClick={add} disabled={busy || !content.trim()}>{busy ? "Saving…" : "Remember"}</Button>
            </div>
            {note ? <p role="status" className={`mt-3 text-[13px] ${note.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{note.text}</p> : null}
            <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
              Memories are stored on this machine in RCTDB (SQLite). Do not store secrets here: recalled text is placed in the model&apos;s prompt.
            </p>
          </Panel>

          <div className="min-w-0 space-y-4">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone={namespace === "" ? "leaf" : "muted"}>
                <button onClick={() => setNamespace("")} className="desk-focus">all</button>
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
              <Panel key={m.id} title={m.memory_type} aside={<span className="desk-mono text-[11px] text-dl-muted">{m.namespace} · used {m.accessed_count}×</span>}>
                <p className="whitespace-pre-wrap break-words text-sm text-dl-text">{m.content}</p>
                <p className="desk-mono mt-2 text-[11px] text-dl-muted">importance {m.importance} · {fmtTime(m.created_at)}</p>
              </Panel>
            ))}
          </div>
        </div>
      </PageBody>
    </>
  );
}
