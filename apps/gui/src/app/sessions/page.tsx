"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import { CycleStrip } from "@/components/desk/CycleStrip";
import { useLang } from "@/components/desk/i18n";
import { Badge, Empty, ErrorNote, PageBody, PageHeader, Panel, Row, fmtNum, fmtTime, reasonTone, useDeskData } from "@/components/desk/ui";
import { desk, type SessionEvent } from "@/lib/desk-api";

function EventLine({ e }: { e: SessionEvent }) {
  const d = e.data as Record<string, unknown>;
  if (e.type === "autonomous_loop_step") {
    return (
      <div className="desk-mono text-[12px]">
        <p className="text-dl-text">
          <span className="text-dl-leaf">●</span> {String(d.tool_name ?? "finish")}{" "}
          <span className="text-dl-muted">{d.tool_args ? JSON.stringify(d.tool_args).slice(0, 160) : ""}</span>
        </p>
        {d.reasoning ? <p className="pl-4 text-dl-muted">thinking · {String(d.reasoning)}</p> : null}
      </div>
    );
  }
  if (e.type === "governed_loop_fdia_gate") {
    const blocked = Boolean(d.blocked);
    return (
      <p className={`desk-mono text-[12px] ${blocked ? "text-dl-rust" : "text-dl-muted"}`}>
        FDIA gate · {String(d.tool_name)} · D {fmtNum(d.D as number)} I {fmtNum(d.I as number)} A {fmtNum(d.A as number)} → F {fmtNum(d.F as number)}
        {blocked ? ` (blocked, threshold ${String(d.threshold)}: ${String(d.A_reason)})` : ""}
      </p>
    );
  }
  if (e.type === "governed_loop_guard") {
    return <p className="desk-mono text-[12px] text-dl-rust">GUARD · CORD {String(d.cord_verdict)} · the goal was not run</p>;
  }
  if (e.type === "notary_receipt") {
    const r = (d.receipt ?? {}) as Record<string, unknown>;
    return <p className="desk-mono text-[12px] text-dl-muted">notary · {e.action} · seq {String(r.seq)} · {String(r.hash ?? "").slice(0, 16)}…</p>;
  }
  if (e.type === "notary_gap") {
    return <p className="desk-mono text-[12px] text-dl-amber">notary gap · {e.action} · {String(d.error ?? "")}</p>;
  }
  return <p className="desk-mono text-[12px] text-dl-muted">{e.type} · {e.action}</p>;
}

function Detail({ id }: { id: number }) {
  const s = useDeskData(() => desk.session(id), [id]);
  if (s.error) return <ErrorNote error={s.error} onRetry={s.reload} />;
  if (!s.data) return <p className="desk-mono text-sm text-dl-muted">Loading…</p>;
  const d = s.data;
  const v = d.verification;
  return (
    <div className="space-y-5">
      <div>
        <p className="text-base text-dl-text">{d.goal}</p>
        <p className="desk-mono mt-1 text-[12px] text-dl-muted">
          {d.namespace} · {fmtTime(d.started_at)} · {d.duration_s ? `${Math.round(d.duration_s)} s` : "-"}
        </p>
      </div>
      <CycleStrip s={d} rct7Count={d.rct7_steps.length} />

      <div className="grid gap-5 lg:grid-cols-2">
        <Panel title="FDIA">
          <Row label="D (data)">{fmtNum(d.D)}</Row>
          <Row label="I (intent)">{fmtNum(d.I)}</Row>
          <Row label="F of the goal (A = 1)">{fmtNum(d.goal_F)}</Row>
          <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">Each risky action is gated separately with its own A; see the events below.</p>
        </Panel>
        <Panel title="VERIFY (RCT-7 step 7)">
          {v?.applicable ? (
            <>
              <Row label="Aligned with the goal">{v.aligned_with_intent ? <Badge tone="leaf">yes</Badge> : <Badge tone="rust">no</Badge>}</Row>
              <Row label="Similarity / threshold">{`${v.similarity_score} / ${v.threshold}`}</Row>
              <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">A heuristic: it decides what may be learned as a skill, never what you are shown.</p>
            </>
          ) : <p className="text-sm text-dl-muted">{v?.reason ?? "Not applicable to this episode."}</p>}
        </Panel>
      </div>

      {d.data_evidence ? (
        <Panel title="D · the data behind this goal" aside={d.warm_recall?.hit ? <Badge tone="leaf">answered from warm recall</Badge> : undefined}>
          <div className="grid gap-x-8 sm:grid-cols-2">
            {(["clarity", "grounding", "memory", "skills", "record"] as const).map((k) => (
              <Row key={k} label={{ clarity: "Request clarity", grounding: "Files / targets found", memory: "Relevant memory", skills: "Verified skills", record: "Track record" }[k]}>
                {fmtNum(d.data_evidence!.parts[k])}
              </Row>
            ))}
          </div>
          {d.data_evidence.missing.length ? (
            <ul className="mt-3 list-disc space-y-1 pl-5 text-[13px] leading-relaxed text-dl-muted">
              {d.data_evidence.missing.map((m, i) => <li key={i}>{m}</li>)}
            </ul>
          ) : <p className="mt-3 text-[13px] text-dl-muted">Every kind of data was present.</p>}
        </Panel>
      ) : null}

      {d.pillars ? (
        <Panel title="Intent Loop · the five pillars" aside={d.growth ? <Badge tone="leaf">Δ {fmtNum(d.growth.delta)} → G {fmtNum(d.growth.G)}</Badge> : undefined}>
          <div className="grid gap-x-8 lg:grid-cols-2">
            <div>
              <p className="desk-mono mb-1 text-[12px] text-dl-leaf">1 · FDIA gatekeeper</p>
              <Row label="CORD">{d.pillars.gatekeeper.guard ?? "-"}</Row>
              <Row label="D / I">{fmtNum(d.pillars.gatekeeper.D)} / {fmtNum(d.pillars.gatekeeper.I)}</Row>
              <p className="desk-mono mb-1 mt-3 text-[12px] text-dl-leaf">2 · Memory</p>
              <Row label="Memories recalled / skills injected">{d.pillars.memory.memories_recalled} / {d.pillars.memory.skills_injected}</Row>
              <Row label="Retrieval algorithms that ran">{d.pillars.memory.retrieval_algorithms_ok}</Row>
              <p className="desk-mono mb-1 mt-3 text-[12px] text-dl-leaf">3 · Specialist executor</p>
              <Row label="Route / steps / tool calls">{d.pillars.executor.route ?? "-"} / {d.pillars.executor.iterations ?? "-"} / {d.pillars.executor.tool_calls}</Row>
              <Row label="Model calls / cost">{d.pillars.executor.model_calls ?? "-"} / {d.pillars.executor.cost_usd != null ? `$${d.pillars.executor.cost_usd}` : "-"}</Row>
            </div>
            <div>
              <p className="desk-mono mb-1 text-[12px] text-dl-leaf">4 · Verifier</p>
              <Row label="Aligned with the intent">{d.pillars.verifier.intent_aligned === null ? "n/a" : d.pillars.verifier.intent_aligned ? "yes" : "no"}</Row>
              <Row label="Belief confidence (ALGO-30)">{fmtNum(d.pillars.verifier.belief_confidence)}</Row>
              <Row label="Hallucination probability (ALGO-33)">{fmtNum(d.pillars.verifier.hallucination_probability)}</Row>
              <p className="mt-1 text-[12px] text-dl-muted">{d.pillars.verifier.multi_model_consensus}</p>
              <p className="desk-mono mb-1 mt-3 text-[12px] text-dl-leaf">5 · Evolution committer</p>
              <Row label="Verified / skill kept">{d.pillars.committer.verified ? "yes" : "no"} / {d.pillars.committer.skill_extracted ? "yes" : "no"}</Row>
              <Row label="Algorithms recorded">{d.pillars.committer.audit_algorithms_recorded ?? "pipeline off"}</Row>
            </div>
          </div>
        </Panel>
      ) : null}

      {d.rct7_steps.length ? (
        <Panel title={`RCT-7 plan (${d.rct7_steps.length} steps)`}>
          <ol className="space-y-1 text-sm leading-relaxed text-dl-text">
            {d.rct7_steps.map((step, i) => <li key={i}>{step}</li>)}
          </ol>
        </Panel>
      ) : null}

      <Panel title={`Events (${d.events.length})`}>
        {d.events.length ? <div className="space-y-2">{d.events.map((e) => <EventLine key={e.id} e={e} />)}</div> : <p className="text-sm text-dl-muted">No steps recorded.</p>}
      </Panel>

      <Panel title="JITNA record">
        <Row label="Packet">{d.jitna.packet_id ?? "-"}</Row>
        <Row label="Content hash">{d.jitna.content_hash ? `${d.jitna.content_hash.slice(0, 24)}…` : "-"}</Row>
        <Row label="Signed with a persistent key">{d.jitna.key_persistent ? "yes" : "no (per-process key)"}</Row>
        {d.approval_id ? <Row label="Approval"><Link href="/approvals" className="text-dl-amber underline">{d.approval_id}</Link></Row> : null}
      </Panel>
    </div>
  );
}

function SessionsInner() {
  const { t, lang } = useLang();
  const params = useSearchParams();
  const router = useRouter();
  const selected = params.get("id") ? Number(params.get("id")) : null;
  const list = useDeskData(() => desk.sessions(100), [], 20000);

  return (
    <>
      <PageHeader title={t("sessions")}
        lead={lang === "th"
          ? "ทุก episode ของ agent ที่ถูกบันทึกใน audit trail: ผ่านวงจรแต่ละขั้นอย่างไร, ค่า FDIA, แผน RCT-7 และทุก tool call"
          : "Every agent episode in the audit trail: how it went through each step of the cycle, its FDIA values, RCT-7 plan and every tool call."} />
      <div className="flex min-h-0 flex-1 flex-col lg:flex-row">
        <div className="max-h-[40vh] shrink-0 overflow-y-auto border-b border-dl-rule lg:max-h-none lg:w-[380px] lg:border-b-0 lg:border-r">
          {list.error ? <div className="p-4"><ErrorNote error={list.error} onRetry={list.reload} /></div> : null}
          {list.data && !list.data.sessions.length ? <div className="p-4"><Empty title="No sessions yet">Run a goal in Chat (Agent mode).</Empty></div> : null}
          <ul>
            {list.data?.sessions.map((s) => (
              <li key={s.id}>
                <button onClick={() => router.replace(`/sessions?id=${s.id}`)} aria-current={selected === s.id ? "true" : undefined}
                  className="desk-focus block w-full border-b border-dl-rule/60 px-4 py-3 text-left hover:bg-dl-pine/30 aria-[current=true]:bg-dl-pine/50">
                  <p className="truncate text-sm text-dl-text">{s.goal ?? s.namespace}</p>
                  <div className="mt-1 flex items-center gap-2">
                    <Badge tone={reasonTone(s.stopped_reason)}>{s.stopped_reason}</Badge>
                    <span className="desk-mono text-[11px] text-dl-muted">{s.route ?? "-"} · {fmtTime(s.started_at)}</span>
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
        <PageBody>
          {selected ? <Detail id={selected} /> : <Empty title="Choose a session">Pick one from the list to see how it went through the Constitutional Cycle.</Empty>}
        </PageBody>
      </div>
    </>
  );
}

export default function SessionsPage() {
  return (
    <Suspense fallback={null}>
      <SessionsInner />
    </Suspense>
  );
}
