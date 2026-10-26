"use client";

import { useEffect, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, Code, ErrorNote, Panel, fmtTime, useDeskData } from "@/components/desk/ui";
import { desk, type ApprovalDevice } from "@/lib/desk-api";
import { ceremonyMessage, createCredential, deviceSupport, placeProblem } from "@/lib/webauthn";

/** Why this page can or can not use a device, as a sentence (null = it can). Computed after hydration, because it reads the address bar. */
export function useDeviceProblem(): string | null | undefined {
  const { lang } = useLang();
  const [problem, setProblem] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    // Browser-only values, read after hydration so the static HTML and the first render agree.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setProblem(placeProblem({ protocol: window.location.protocol, hostname: window.location.hostname, port: window.location.port }, deviceSupport(), lang as "th" | "en"));
  }, [lang]);
  return problem;
}

function scopeText(device: ApprovalDevice, th: boolean): string {
  const parts: string[] = [];
  if (device.scope.kinds?.length) parts.push(`${th ? "ประเภทงาน" : "kinds"}: ${device.scope.kinds.join(", ")}`);
  if (device.scope.namespaces?.length) parts.push(`${th ? "ผู้ใช้" : "people"}: ${device.scope.namespaces.join(", ")}`);
  if (device.scope.workspaces?.length) parts.push(`${th ? "โฟลเดอร์" : "folders"}: ${device.scope.workspaces.join(", ")}`);
  return parts.length ? parts.join(" · ") : th ? "ไม่จำกัด" : "no limit";
}

const TONE = { ACTIVE: "leaf", PENDING: "amber", REVOKED: "muted" } as const;

export function ApprovalDevices() {
  const { lang } = useLang();
  const th = lang === "th";
  const list = useDeskData(() => desk.devices(), [], 10000);
  const problem = useDeviceProblem();
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const firstOpen = !!list.data?.first_device?.open;             // nobody can approve yet: the first device is added with a one-time code
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);

  const add = async () => {
    setBusy(true);
    setMessage(null);
    try {
      const begun = await desk.deviceBegin(name.trim());
      const credential = await createCredential(begun.options);        // Windows Hello / Touch ID / phone asks the person here
      const finished = await desk.deviceFinish(begun.enrollment_id, credential, firstOpen ? code.trim() : undefined);
      setName("");
      setCode("");
      if ("activated" in finished && finished.activated) {
        setMessage({ tone: "ok", text: th
          ? "เครื่องนี้เป็นผู้อนุมัติคนแรกแล้ว ต่อไปนี้กด “อนุมัติด้วยเครื่องนี้” ในหน้าอนุมัติได้เลย (เครื่องถัดไปต้องให้เครื่องนี้หรือกุญแจ approver เซ็นรับรองก่อน)"
          : "This computer is now your first approver. You can press “Approve with this device” on the Approvals page. Any further device needs an existing approver's signature." });
        list.reload();
        return;
      }
      setMessage({ tone: "ok", text: th
        ? "เครื่องนี้ถูกเพิ่มแล้ว แต่ยังใช้ไม่ได้ ต้องให้ผู้อนุมัติเดิม (คนที่มีกุญแจ approver) เซ็นรับรองเครื่องนี้หนึ่งครั้ง: ดับเบิลคลิก SIGN_PENDING.bat แล้วกลับมากด “เปิดใช้”"
        : "The device is added but cannot approve yet. An existing approver (the holder of the approver key) must sign for it once: double-click SIGN_PENDING.bat, then come back and press Activate." });
      list.reload();
    } catch (err) {
      setMessage({ tone: "err", text: ceremonyMessage(err, lang as "th" | "en") });
    } finally {
      setBusy(false);
    }
  };

  const activate = async (approvalId: string) => {
    setBusy(true);
    setMessage(null);
    try {
      await desk.deviceActivate(approvalId);
      setMessage({ tone: "ok", text: th ? "เปิดใช้เครื่องนี้แล้ว ต่อไปนี้ยืนยันงานที่รอได้ด้วยเครื่องนี้" : "The device is active. It can now confirm waiting actions." });
      list.reload();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  const revoke = async (device: ApprovalDevice) => {
    if (!window.confirm(th ? `ถอนสิทธิ์ของ “${device.name}” ใช่ไหม งานที่เครื่องนี้เคยอนุมัติและยังไม่ได้รันจะใช้ไม่ได้อีก` : `Remove “${device.name}”? Anything it approved that has not run yet becomes void.`)) return;
    setBusy(true);
    try {
      await desk.deviceRevoke(device.id);
      list.reload();
    } catch (err) {
      setMessage({ tone: "err", text: err instanceof Error ? err.message : String(err) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Panel title={th ? "อุปกรณ์ยืนยัน (Windows Hello / ลายนิ้วมือ / มือถือ)" : "Approval devices (Windows Hello / fingerprint / phone)"}
      aside={list.data ? <Badge tone="muted">{list.data.devices.filter((d) => d.status === "ACTIVE").length} {th ? "เครื่องใช้งานอยู่" : "active"}</Badge> : null}>
      <p className="text-[13px] leading-relaxed text-dl-muted">
        {th
          ? "งานเสี่ยงจริง (ลบ ส่งออกนอก เงิน เผยแพร่ แผนหลายขั้น) ต้องมีคนยืนยัน แทนที่จะพิมพ์คำสั่งทุกครั้ง คุณยืนยันด้วยเครื่องนี้: กดปุ่มในหน้า Approvals แล้ว Windows Hello ถามหน้า/ลายนิ้วมือ/PIN กุญแจส่วนตัวไม่เคยออกจากเครื่อง งานที่ปลอดภัยไม่ต้องยืนยัน"
          : "Risky actions (delete, send out, money, publish, multi-step plans) need a person. Instead of typing a command each time, confirm with this device: press the button on the Approvals page and Windows Hello asks for your face, fingerprint or PIN. The private key never leaves the device. Safe actions never ask."}
      </p>

      {problem ? <p role="status" className="mt-3 text-[13px] leading-relaxed text-dl-amber">{problem}</p> : null}
      {list.error ? <ErrorNote error={list.error} onRetry={list.reload} /> : null}

      {list.data?.devices.length ? (
        <ul className="mt-4 divide-y divide-dl-rule rounded border border-dl-rule">
          {list.data.devices.map((d) => {
            const waiting = list.data!.enrollments_waiting.find((e) => e.name === d.name && d.status === "PENDING");
            return (
              <li key={d.id} className="flex flex-wrap items-center gap-3 px-3 py-2 text-[13px]">
                <span className="font-medium text-dl-text">{d.name}</span>
                <Badge tone={TONE[d.status]}>{d.status === "ACTIVE" ? (th ? "ใช้งานอยู่" : "active") : d.status === "PENDING" ? (th ? "รอผู้อนุมัติเซ็นรับรอง" : "waiting for an approver") : (th ? "ถอนแล้ว" : "removed")}</Badge>
                <span className="text-dl-muted">{d.role ? `${th ? "บทบาท" : "role"} ${d.role} · ` : ""}{scopeText(d, th)}</span>
                <span className="desk-mono text-[11px] text-dl-muted">{d.last_used_at ? `${th ? "ใช้ล่าสุด" : "last used"} ${fmtTime(new Date(d.last_used_at * 1000).toISOString())}` : th ? "ยังไม่เคยใช้" : "not used yet"}</span>
                <span className="ml-auto flex gap-2">
                  {waiting && waiting.status === "APPROVED" ? <Button onClick={() => activate(waiting.approval_id)} disabled={busy}>{th ? "เปิดใช้" : "Activate"}</Button> : null}
                  {d.status !== "REVOKED" ? <Button tone="ghost" onClick={() => revoke(d)} disabled={busy}>{th ? "ถอนสิทธิ์" : "Remove"}</Button> : null}
                </span>
              </li>
            );
          })}
        </ul>
      ) : <p className="mt-4 text-[13px] text-dl-muted">{th ? "ยังไม่มีอุปกรณ์ยืนยัน" : "No approval device yet."}</p>}

      {list.data?.enrollments_waiting.some((e) => e.status === "PENDING") ? (
        <p className="mt-3 text-[13px] leading-relaxed text-dl-muted">
          {th ? "มีเครื่องที่รอผู้อนุมัติเซ็นรับรอง: ดับเบิลคลิก " : "A device is waiting for an approver: double-click "}<Code>SIGN_PENDING.bat</Code>
          {th ? " (หรือวางลายเซ็นในหน้า Approvals) แล้วกลับมากด “เปิดใช้”" : " (or paste the signature on the Approvals page), then press Activate here."}
        </p>
      ) : null}

      {firstOpen ? (
        <div className="mt-4 rounded border border-dl-amber/50 bg-dl-amber/5 p-3 text-[13px] leading-relaxed text-dl-text">
          <p className="font-medium">{th ? "ยังไม่มีผู้อนุมัติ: เพิ่มเครื่องแรกด้วยรหัสครั้งเดียว" : "Nobody can approve yet: add the first device with a one-time code"}</p>
          <ol className="mt-1 list-decimal space-y-0.5 pl-5 text-dl-muted">
            <li>{th ? <>ในเทอร์มินัลบนเครื่องนี้ พิมพ์ <Code>delentia approvals first-device-code</Code> จะได้รหัส 8 ตัว (ใช้ได้ 10 นาที ลองได้ 5 ครั้ง)</> : <>In a terminal on this computer run <Code>delentia approvals first-device-code</Code> to get an 8-character code (valid 10 minutes, 5 tries).</>}</li>
            <li>{th ? "พิมพ์ชื่อเครื่องและรหัสด้านล่าง แล้วกด เพิ่มเครื่องนี้ Windows Hello จะถามตัวคุณ" : "Type a name and the code below, then press Add this device. Windows Hello asks you."}</li>
          </ol>
          {list.data?.first_device.code_waiting ? <p className="mt-1 text-dl-leaf">{th ? "มีรหัสรออยู่แล้ว" : "A code is waiting."}</p> : null}
        </div>
      ) : null}

      <div className="mt-5 flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="text-[13px] text-dl-muted">{th ? "ชื่อเครื่องนี้" : "A name for this device"}</span>
          <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} placeholder={th ? "เช่น โน้ตบุ๊กของฉัน" : "for example: my laptop"}
            className="desk-focus mt-1 block w-64 rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text placeholder:text-dl-muted/50" />
        </label>
        {firstOpen ? (
          <label className="block">
            <span className="text-[13px] text-dl-muted">{th ? "รหัสครั้งเดียว" : "One-time code"}</span>
            <input value={code} onChange={(e) => setCode(e.target.value)} maxLength={12} autoComplete="off" spellCheck={false} placeholder="ABCD-EFGH"
              className="desk-focus desk-mono mt-1 block w-40 rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm uppercase text-dl-text placeholder:text-dl-muted/50" />
          </label>
        ) : null}
        <Button onClick={add} disabled={busy || !name.trim() || !!problem || (firstOpen && code.trim().length < 8)}>{busy ? (th ? "รอการยืนยันจากเครื่อง…" : "Waiting for the device…") : th ? "เพิ่มเครื่องนี้" : "Add this device"}</Button>
      </div>
      {message ? <p role="status" className={`mt-3 text-[13px] leading-relaxed ${message.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{message.text}</p> : null}
      <p className="mt-4 text-[12px] leading-relaxed text-dl-muted">
        {th
          ? "ข้อจำกัดที่ควรรู้: อุปกรณ์เซ็นยืนยัน “เลขรหัสของงาน” ไม่ได้เซ็นข้อความที่เห็นบนจอ ดังนั้นหน้าจอนี้ต้องเชื่อถือได้ (เปิดที่ localhost ของเครื่องคุณเอง) และงานที่เสี่ยงสูงควรให้ผู้เซ็นสองคน"
          : "A limit to know: the device signs the action's digest, not the text on screen, so this screen must be trustworthy (opened at localhost on your own machine), and the riskiest actions should need two signers."}
      </p>
    </Panel>
  );
}
