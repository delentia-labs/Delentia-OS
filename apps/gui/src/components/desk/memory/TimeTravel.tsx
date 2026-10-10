"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Empty, ErrorNote, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type MemoryAt } from "@/lib/desk-api";

/** Round 67: the memory event log as a history. Pick an event and see what the agent's memory held right after it. */
export function TimeTravel({ namespace }: { namespace: string }) {
  const { lang } = useLang();
  const th = lang === "th";
  const history = useDeskData(() => desk.memoryHistory(namespace || undefined, 200), [namespace], 30000);
  const status = useDeskData(() => desk.memoryLog().catch(() => null), [], 60000);   // owner only: a person gets a 403, which simply hides the line
  const [picked, setPicked] = useState<number | null>(null);
  const [state, setState] = useState<{ seq: number; memories: MemoryAt[] } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const view = async (seq: number) => {
    setBusy(true);
    setErr(null);
    setPicked(seq);
    try {
      const r = await desk.memoryAt(seq, namespace || undefined);
      setState({ seq: r.seq, memories: r.memories });
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const events = history.data?.events ?? [];
  const log = status.data;
  return (
    <Panel title={th ? "ย้อนเวลา: ความจำเคยเป็นอย่างไร" : "Time travel: what the memory held"}
      aside={log && log.enabled ? (
        <span className="flex items-center gap-2">
          <Badge tone={log.chain?.ok ? "leaf" : "rust"}>{th ? "ห่วงโซ่" : "chain"} {log.chain?.ok ? "ok" : "BROKEN"}</Badge>
          <Badge tone={log.anchors?.ok ? "leaf" : "rust"}>{th ? "จุดยึดใน audit" : "audit anchors"} {log.anchors?.ok ? `${log.anchors.anchors} ok` : "MISMATCH"}</Badge>
          {log.anchors && log.anchors.unanchored_events > 0 ? <Badge tone="muted">{log.anchors.unanchored_events} {th ? "ยังไม่ยึด" : "not yet anchored"}</Badge> : null}
        </span>
      ) : undefined}>
      {history.error ? <ErrorNote error={history.error} onRetry={history.reload} /> : null}
      {history.data && !history.data.enabled ? (
        <Empty title={th ? "ยังไม่ได้เปิด event log" : "The event log is off"}>
          {th ? "ตั้ง DELENTIA_MEMORY_EVENTLOG=1 ที่โฮสต์ เหตุการณ์ต่อจากนั้นจะถูกบันทึกและย้อนดูได้" : "Set DELENTIA_MEMORY_EVENTLOG=1 on the host; events written from then on can be replayed here."}
        </Empty>
      ) : null}
      {history.data?.enabled && !events.length ? <Empty title={th ? "ยังไม่มีเหตุการณ์" : "No events yet"}>{th ? "เพิ่มหรือเพิกถอนความจำเพื่อให้มีประวัติ" : "Add or revoke a memory to start a history."}</Empty> : null}
      {events.length ? (
        <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <ul className="max-h-80 space-y-1 overflow-y-auto pr-1">
            {events.map((e) => (
              <li key={e.seq}>
                <button onClick={() => view(e.seq)} disabled={busy} aria-pressed={picked === e.seq}
                  className={`desk-focus desk-mono w-full rounded border px-2 py-1 text-left text-[12px] ${picked === e.seq ? "border-dl-leaf text-dl-text" : "border-dl-rule text-dl-muted"}`}>
                  #{e.seq} · {e.kind} · {fmtTime(e.at)}{e.tainted ? " · outside origin" : ""}
                  {e.preview ? <span className="block truncate text-dl-text">{e.preview}</span> : null}
                </button>
              </li>
            ))}
          </ul>
          <div className="min-w-0">
            {err ? <p role="alert" className="text-[13px] text-dl-rust">{err}</p> : null}
            {!state ? <p className="text-[13px] text-dl-muted">{th ? "เลือกเหตุการณ์ทางซ้ายเพื่อดูความจำหลังเหตุการณ์นั้น" : "Pick an event on the left to see the memory right after it."}</p> : (
              <div className="space-y-2">
                <p className="desk-mono text-[12px] text-dl-muted">{th ? "หลังเหตุการณ์" : "after event"} #{state.seq} · {state.memories.length} {th ? "รายการ" : "items"}</p>
                {state.memories.map((m) => (
                  <p key={m.id} className={`whitespace-pre-wrap break-words text-sm ${m.revoked_at ? "text-dl-muted line-through" : "text-dl-text"}`}>
                    {m.content}{m.revoked_at ? <span className="desk-mono text-[11px] text-dl-amber"> · {th ? "เพิกถอน" : "revoked"}{m.revoked_reason ? `: ${m.revoked_reason}` : ""}</span> : null}
                  </p>
                ))}
                <Button tone="ghost" onClick={() => { setState(null); setPicked(null); }}>{th ? "ล้าง" : "Clear"}</Button>
              </div>
            )}
          </div>
        </div>
      ) : null}
    </Panel>
  );
}
