"use client";

import { useRef, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Button } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";
import { ceremonyMessage, getAssertion } from "@/lib/webauthn";
import { signWithKeyFile } from "@/lib/setup-model";

/**
 * Confirm (or refuse) one waiting action without leaving the Desk, in either of the two ways the system accepts:
 *  - with this computer's device (Windows Hello): the server checks the answer belongs to THIS action and THIS decision;
 *  - with an approver key file: the file is read here, in this browser, the decision is signed in memory and only the signature and the public key are sent.
 * Nothing here decides for the person: a button press is the person's act, and the server checks every signature again.
 */
export function ConfirmAction({ approvalId, actionSha256, hasDevice, allowDevice = true, onDecided }: {
  approvalId: string; actionSha256: string; hasDevice: boolean; allowDevice?: boolean; onDecided: (status: string) => Promise<void> | void;
}) {
  const { lang } = useLang();
  const th = lang === "th";
  const L = lang as "th" | "en";
  const fileRef = useRef<HTMLInputElement>(null);
  const wanted = useRef<"APPROVED" | "REJECTED">("APPROVED");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const finish = async (status: string) => { await onDecided(status); };

  const withDevice = async (decision: "APPROVED" | "REJECTED") => {
    setBusy(true);
    setMessage(null);
    try {
      const asked = await desk.deviceOptions(approvalId, decision);
      const assertion = await getAssertion(asked.options);
      const decided = await desk.deviceDecide(approvalId, decision, assertion);
      await finish(decided.status);
    } catch (err) {
      setMessage(ceremonyMessage(err, L));
    } finally {
      setBusy(false);
    }
  };

  const chooseKey = (decision: "APPROVED" | "REJECTED") => {
    wanted.current = decision;
    setMessage(null);
    fileRef.current?.click();
  };

  const withKeyFile = async (file: File | undefined) => {
    if (!file) return;
    setBusy(true);
    setMessage(null);
    try {
      if (file.size > 20_000) throw new Error(th ? "ไฟล์นี้ใหญ่เกินกว่าจะเป็นกุญแจ approver" : "This file is too large to be an approver key.");
      const body = await signWithKeyFile(await file.text(), approvalId, actionSha256, wanted.current, L);
      const decided = await desk.decide(approvalId, body);
      await finish(String(decided.status ?? ""));
    } catch (err) {
      setMessage(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
      if (fileRef.current) fileRef.current.value = "";            // the file is forgotten; the page never keeps the key
    }
  };

  return (
    <div className="mt-3">
      <div className="flex flex-wrap items-center gap-2">
        {allowDevice ? (
          <>
            <Button onClick={() => withDevice("APPROVED")} disabled={busy || !hasDevice}>{th ? "อนุมัติด้วยเครื่องนี้" : "Approve with this device"}</Button>
            <Button tone="ghost" onClick={() => withDevice("REJECTED")} disabled={busy || !hasDevice}>{th ? "ปฏิเสธด้วยเครื่องนี้" : "Refuse with this device"}</Button>
          </>
        ) : null}
        <Button tone="ghost" onClick={() => chooseKey("APPROVED")} disabled={busy}>{th ? "อนุมัติด้วยไฟล์กุญแจ approver" : "Approve with an approver key file"}</Button>
        <Button tone="ghost" onClick={() => chooseKey("REJECTED")} disabled={busy}>{th ? "ปฏิเสธด้วยไฟล์กุญแจ" : "Refuse with a key file"}</Button>
        <input ref={fileRef} type="file" accept=".pem,text/plain" className="sr-only" tabIndex={-1} aria-label={th ? "เลือกไฟล์กุญแจ approver (.pem)" : "Choose the approver key file (.pem)"}
          onChange={(e) => withKeyFile(e.target.files?.[0])} />
      </div>
      {allowDevice && !hasDevice ? (
        <p className="mt-2 text-[12px] text-dl-muted">{th ? "ยังไม่มีอุปกรณ์ที่เปิดใช้งาน ใช้ไฟล์กุญแจแทน หรือเพิ่มอุปกรณ์ในขั้นที่ 2" : "No device is active yet. Use a key file, or add a device in step 2."}</p>
      ) : null}
      <p className="mt-2 text-[12px] leading-relaxed text-dl-muted">
        {th ? "ไฟล์กุญแจถูกอ่านในเบราว์เซอร์นี้เท่านั้น ไม่ถูกอัปโหลด หน้านี้ส่งแค่ลายเซ็นกับกุญแจสาธารณะ และลืมไฟล์ทันทีหลังเซ็น"
          : "The key file is read in this browser only, never uploaded. The page sends only the signature and the public key, and forgets the file right after signing."}
      </p>
      {message ? <p role="status" className="mt-2 text-[13px] leading-relaxed text-dl-rust">{message}</p> : null}
    </div>
  );
}
