"use client";

import { useCallback, useEffect, useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { ApprovalDevices } from "@/components/desk/ApprovalDevices";
import { ConfirmAction } from "@/components/desk/ConfirmAction";
import { Badge, Button, ErrorNote, PageBody, PageHeader, Panel, useDeskData } from "@/components/desk/ui";
import { desk, type BackupMade, type Checkup, type PracticeAction } from "@/lib/desk-api";
import { deviceSupport } from "@/lib/webauthn";
import { LEVELS, STEP_IDS, browserVerdict, nextStep, type BrowserVerdict, type LevelId, type StepId } from "@/lib/setup-model";

type Tone = "leaf" | "amber" | "rust" | "muted";
const LEVEL_TONE: Record<"ok" | "warn" | "fail", Tone> = { ok: "leaf", warn: "amber", fail: "rust" };
const LEVEL_WORD = { ok: { en: "ok", th: "ปกติ" }, warn: { en: "look", th: "ควรดู" }, fail: { en: "fix", th: "ต้องแก้" } } as const;

/**
 * The Setup assistant: the things a person does once to trust Delentia, done inside the Desk. Each step checks the real state first and only asks for what is missing. It never
 * approves anything by itself: every confirmation below is the person's own act (their device, or their approver key file), checked again by the server.
 */
export default function SetupPage() {
  const { lang } = useLang();
  const th = lang === "th";
  const T = (en: string, thai: string) => (th ? thai : en);

  const readiness = useDeskData(() => desk.readiness(), [], 8000);
  const devices = useDeskData(() => desk.devices(), [], 8000);
  const policy = useDeskData(() => desk.fdia(), [], 0);
  const waitingActions = useDeskData(() => desk.approvals("PENDING"), [], 8000);

  const [browser, setBrowser] = useState<BrowserVerdict | null>(null);
  const [checkup, setCheckup] = useState<Checkup | null>(null);
  const [backup, setBackup] = useState<BackupMade | null>(null);
  const [practice, setPractice] = useState<PracticeAction | null>(null);
  const [practiceResult, setPracticeResult] = useState<string | null>(null);
  const [chosen, setChosen] = useState<LevelId>("standard");
  const [pendingPolicy, setPendingPolicy] = useState<{ approvalId: string; sha: string; template: "argaware" | "planfirst" } | null>(null);
  const [levelMessage, setLevelMessage] = useState<{ tone: "ok" | "err"; text: string } | null>(null);
  const [levelSaved, setLevelSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const approverCheck = readiness.data?.checks.find((c) => c.id === "approver");
  const hasApprover = !!approverCheck?.ok;
  const activeDevices = devices.data?.devices.filter((d) => d.status === "ACTIVE").length ?? 0;
  const hasDevice = activeDevices > 0;

  const checkBrowser = useCallback(async () => {
    let platform: boolean | null = null;
    try {
      platform = deviceSupport() ? await window.PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable() : false;
    } catch {
      platform = null;
    }
    setBrowser(browserVerdict({ hostname: window.location.hostname, protocol: window.location.protocol, port: window.location.port, hasApi: deviceSupport(), platformAvailable: platform }, lang as "th" | "en"));
  }, [lang]);

  useEffect(() => {
    // Browser-only facts, read after hydration so the static HTML and the first render agree.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void checkBrowser();
  }, [checkBrowser]);

  const hasPolicyFile = !!policy.data?.exists;
  const currentLevel: LevelId = policy.data?.policy?.plan_first?.length ? "plan_first" : "standard";
  const next = nextStep({ browserOk: browser?.level === "ok" || browser?.level === "warn", hasApprover, policyChosen: levelSaved || hasPolicyFile, checkupRan: !!checkup, practiceDone: practiceResult !== null });

  const waitingEnrollments = (devices.data?.enrollments_waiting ?? []).filter((e) => e.status === "PENDING");

  const activate = async (approvalId: string) => {
    try {
      await desk.deviceActivate(approvalId);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
    devices.reload();
    readiness.reload();
  };

  const applyLevel = async () => {
    setBusy(true);
    setLevelMessage(null);
    setError(null);
    try {
      const level = LEVELS.find((l) => l.id === chosen)!;
      const { policy: template } = await desk.fdiaTemplate(level.template);
      const answer = await desk.fdiaSave(template);
      if ("pending_signature" in answer) {
        setPendingPolicy({ approvalId: answer.approval_id, sha: answer.action_sha256, template: level.template });
        setLevelMessage({ tone: "ok", text: T("Changing the rules is itself something you must confirm. Confirm it below.", "การเปลี่ยนกฎเป็นสิ่งที่คุณต้องยืนยันเอง ยืนยันด้านล่าง") });
      } else {
        setLevelSaved(true);
        setLevelMessage({ tone: "ok", text: T("Saved. The new level is in use now.", "บันทึกแล้ว ระดับใหม่ใช้งานทันที") });
        policy.reload();
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const policyDecided = async (status: string) => {
    if (!pendingPolicy) return;
    if (status === "REJECTED") {
      setPendingPolicy(null);
      setLevelMessage({ tone: "err", text: T("You refused. The rules were not changed.", "คุณปฏิเสธ กฎไม่ถูกเปลี่ยน") });
      return;
    }
    if (status !== "APPROVED") {
      setLevelMessage({ tone: "ok", text: T("Recorded. It needs another signature before it applies.", "บันทึกแล้ว ต้องมีลายเซ็นเพิ่มก่อนจึงจะใช้") });
      return;
    }
    try {
      const { policy: template } = await desk.fdiaTemplate(pendingPolicy.template);
      await desk.fdiaSave(template, pendingPolicy.approvalId);
      setPendingPolicy(null);
      setLevelSaved(true);
      setLevelMessage({ tone: "ok", text: T("Confirmed and saved. The new level is in use now, and the change is in the record.", "ยืนยันและบันทึกแล้ว ระดับใหม่ใช้งานทันที และการเปลี่ยนนี้อยู่ในบันทึก") });
      policy.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    }
  };

  const runCheckup = async () => {
    setBusy(true);
    setError(null);
    try {
      setCheckup(await desk.setupCheckup());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const backUp = async () => {
    setBusy(true);
    setError(null);
    try {
      setBackup(await desk.setupBackup());
      setCheckup(await desk.setupCheckup());
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const startPractice = async () => {
    setBusy(true);
    setError(null);
    setPracticeResult(null);
    try {
      setPractice(await desk.setupPractice());
      waitingActions.reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const practiceDecided = async (status: string) => {
    if (!practice) return;
    if (status === "APPROVED") {
      try {
        await desk.runApproved(practice.approval_id);
        setPracticeResult(T("It worked. You confirmed, the system ran the action exactly once, and it is in the record (see Audit). Nothing important was changed: only a short note was written.", "สำเร็จ คุณยืนยัน ระบบรันการกระทำนั้นหนึ่งครั้งพอดี และมีอยู่ในบันทึก (ดูหน้า Audit) ไม่มีอะไรสำคัญถูกเปลี่ยน มีเพียงบันทึกสั้น ๆ หนึ่งฉบับถูกเขียน"));
      } catch (err) {
        setError(err instanceof Error ? err.message : String(err));
      }
    } else if (status === "REJECTED") {
      setPracticeResult(T("You refused, and nothing ran. That is how a refusal works too.", "คุณปฏิเสธ และไม่มีอะไรรัน การปฏิเสธก็ทำงานแบบนี้"));
    }
    setPractice(null);
    waitingActions.reload();
  };

  const stepTitle: Record<StepId, [string, string]> = {
    browser: ["1. Is this browser ready?", "1. เบราว์เซอร์นี้พร้อมไหม"],
    approver: ["2. Who confirms risky work?", "2. ใครเป็นคนยืนยันงานเสี่ยง"],
    level: ["3. How careful should it be?", "3. จะให้ระวังแค่ไหน"],
    checkup: ["4. Check that everything works", "4. ตรวจว่าทุกอย่างทำงาน"],
    practice: ["5. Practice one approval", "5. ลองอนุมัติหนึ่งครั้ง"],
  };
  const doneMap: Record<StepId, boolean> = { browser: !!browser && browser.level === "ok", approver: hasApprover, level: levelSaved || hasPolicyFile, checkup: !!checkup, practice: practiceResult !== null };
  const stepBadge = (id: StepId) => (doneMap[id] ? <Badge tone="leaf">{T("done", "เสร็จ")}</Badge> : next === id ? <Badge tone="amber">{T("next", "ถัดไป")}</Badge> : <Badge tone="muted">{T("to do", "ยังไม่ได้ทำ")}</Badge>);
  const titleOf = (id: StepId) => stepTitle[id][th ? 1 : 0];
  const waitingPractice = practice ? waitingActions.data?.find((a) => a.approval_id === practice.approval_id) : undefined;

  return (
    <>
      <PageHeader
        title={T("Setup assistant", "ตัวช่วยตั้งค่า")}
        lead={T("Five short steps, all inside this window. Each one checks first and only asks for what is missing. You never have to open a terminal for the ordinary path, and nothing is approved without you.",
          "ห้าขั้นสั้น ๆ ทำในหน้าต่างนี้ทั้งหมด แต่ละขั้นตรวจก่อนและขอเฉพาะสิ่งที่ยังขาด ทางปกติไม่ต้องเปิดเทอร์มินัล และไม่มีอะไรถูกอนุมัติโดยที่คุณไม่ได้ทำ")}
        actions={<Badge tone={next ? "amber" : "leaf"}>{next ? T(`next: ${titleOf(next)}`, `ถัดไป: ${titleOf(next)}`) : T("all done", "ครบทุกขั้น")}</Badge>}
      />
      <PageBody>
        <div className="max-w-3xl space-y-6">
          {error ? <ErrorNote error={error} onRetry={() => setError(null)} /> : null}

          <Panel title={titleOf("browser")} aside={stepBadge("browser")}>
            {browser ? (
              <>
                <p className={`text-sm ${browser.level === "ok" ? "text-dl-leaf" : browser.level === "warn" ? "text-dl-amber" : "text-dl-rust"}`}>{browser.text}</p>
                {browser.fix ? <p className="mt-1 text-[13px] leading-relaxed text-dl-muted">{browser.fix}</p> : null}
              </>
            ) : <p className="text-sm text-dl-muted">{T("Checking…", "กำลังตรวจ…")}</p>}
            <div className="mt-3"><Button tone="ghost" onClick={() => void checkBrowser()}>{T("Check again", "ตรวจอีกครั้ง")}</Button></div>
          </Panel>

          <Panel title={titleOf("approver")} aside={stepBadge("approver")}>
            {hasApprover ? (
              <p className="text-sm text-dl-leaf">{T(`Someone can confirm risky work: ${approverCheck?.devices ?? 0} device(s), ${approverCheck?.keys ?? 0} key(s).`, `มีผู้ยืนยันงานเสี่ยงแล้ว: อุปกรณ์ ${approverCheck?.devices ?? 0} เครื่อง กุญแจ ${approverCheck?.keys ?? 0} ดอก`)}</p>
            ) : (
              <p className="text-sm text-dl-text">{T("Nobody can confirm yet, so risky work would wait forever. Add this computer below.", "ยังไม่มีผู้ยืนยัน งานเสี่ยงจะรอไปเรื่อย ๆ เพิ่มเครื่องนี้ด้านล่าง")}</p>
            )}
            {waitingEnrollments.map((e) => {
              const action = waitingActions.data?.find((a) => a.approval_id === e.approval_id);
              return (
                <div key={e.approval_id} className="mt-3 rounded border border-dl-amber/50 bg-dl-amber/5 p-3 text-[13px] leading-relaxed">
                  <p className="font-medium text-dl-text">{T(`The device “${e.name ?? "?"}” is waiting for an approver to vouch for it.`, `อุปกรณ์ “${e.name ?? "?"}” รอให้ผู้อนุมัติรับรอง`)}</p>
                  <p className="text-dl-muted">{T("A device can not vouch for another device. Use your approver key file once; the page signs in your browser and the file is not uploaded.", "อุปกรณ์รับรองอุปกรณ์อื่นไม่ได้ ใช้ไฟล์กุญแจ approver ของคุณหนึ่งครั้ง หน้านี้เซ็นในเบราว์เซอร์ของคุณและไม่อัปโหลดไฟล์")}</p>
                  {action ? <ConfirmAction approvalId={e.approval_id} actionSha256={action.action_sha256} hasDevice={false} allowDevice={false} onDecided={async (status) => { if (status === "APPROVED") await activate(e.approval_id); else { devices.reload(); } }} /> : <p className="mt-2 text-dl-muted">{T("Loading the request…", "กำลังโหลดคำขอ…")}</p>}
                </div>
              );
            })}
            <div className="mt-4"><ApprovalDevices /></div>
          </Panel>

          <Panel title={titleOf("level")} aside={stepBadge("level")}>
            <p className="text-[13px] leading-relaxed text-dl-muted">
              {T("Pick how much you want to be asked. Either way, risky work never runs without you. You can change this later on the FDIA / Policy page.", "เลือกว่าจะให้ถามมากแค่ไหน ไม่ว่าแบบไหน งานเสี่ยงไม่รันโดยไม่มีคุณ เปลี่ยนทีหลังได้ที่หน้า FDIA / Policy")}
              {" "}{T(`Now in use: ${currentLevel === "plan_first" ? "Plan first" : hasPolicyFile ? "your own rules" : "Standard"}.`, `ตอนนี้ใช้: ${currentLevel === "plan_first" ? "แผนก่อน" : hasPolicyFile ? "กฎที่คุณเขียนเอง" : "มาตรฐาน"}`)}
            </p>
            <fieldset className="mt-3 space-y-3">
              <legend className="sr-only">{T("Protection level", "ระดับการป้องกัน")}</legend>
              {LEVELS.map((l) => (
                <label key={l.id} className={`block cursor-pointer rounded border p-3 text-[13px] leading-relaxed ${chosen === l.id ? "border-dl-leaf bg-dl-pine/30" : "border-dl-rule"}`}>
                  <input type="radio" name="level" className="mr-2" checked={chosen === l.id} onChange={() => setChosen(l.id)} />
                  <span className="font-medium text-dl-text">{th ? l.th : l.en}</span>
                  <span className="mt-1 block text-dl-muted">{th ? l.whyTh : l.whyEn}</span>
                  {(th ? l.changesTh : l.changesEn).length ? (
                    <span className="mt-1 block text-dl-amber">{T("This level also loosens:", "ระดับนี้ผ่อนกฎเพิ่ม:")} {(th ? l.changesTh : l.changesEn).join(" · ")}</span>
                  ) : null}
                </label>
              ))}
            </fieldset>
            <div className="mt-3"><Button onClick={applyLevel} disabled={busy || !!pendingPolicy}>{T("Apply this level", "ใช้ระดับนี้")}</Button></div>
            {pendingPolicy ? <ConfirmAction approvalId={pendingPolicy.approvalId} actionSha256={pendingPolicy.sha} hasDevice={hasDevice} onDecided={policyDecided} /> : null}
            {levelMessage ? <p role="status" className={`mt-3 text-[13px] leading-relaxed ${levelMessage.tone === "ok" ? "text-dl-leaf" : "text-dl-rust"}`}>{levelMessage.text}</p> : null}
          </Panel>

          <Panel title={titleOf("checkup")} aside={stepBadge("checkup")}>
            <p className="text-[13px] leading-relaxed text-dl-muted">{T("Real checks, read-only: is the record intact, can a model answer, can someone approve, is there room and a backup.", "ตรวจจริง อ่านอย่างเดียว: บันทึกครบไหม มีโมเดลตอบได้ไหม มีคนอนุมัติได้ไหม พื้นที่พอไหม และมีสำรองข้อมูลไหม")}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={runCheckup} disabled={busy}>{checkup ? T("Check again", "ตรวจอีกครั้ง") : T("Run the check", "เริ่มตรวจ")}</Button>
              <Button tone="ghost" onClick={backUp} disabled={busy}>{T("Back up now", "สำรองข้อมูลตอนนี้")}</Button>
            </div>
            {checkup ? (
              <ul className="mt-4 divide-y divide-dl-rule rounded border border-dl-rule">
                {checkup.checks.map((c) => (
                  <li key={c.id} className="px-3 py-2 text-[13px] leading-relaxed">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone={LEVEL_TONE[c.level]}>{LEVEL_WORD[c.level][th ? "th" : "en"]}</Badge>
                      <span className="font-medium text-dl-text">{th ? c.th : c.en}</span>
                    </div>
                    {(th ? c.detail_th : c.detail_en) ? <p className="text-dl-muted">{th ? c.detail_th : c.detail_en}</p> : null}
                    {(th ? c.fix_th : c.fix_en) ? <p className="text-dl-amber">{th ? c.fix_th : c.fix_en}</p> : null}
                  </li>
                ))}
              </ul>
            ) : null}
            {backup ? <p role="status" className="mt-3 text-[13px] text-dl-leaf">{T(`Backed up ${backup.files} file(s) to ${backup.path}. Private keys are not in it.`, `สำรอง ${backup.files} ไฟล์ไปที่ ${backup.path} ไม่มีกุญแจส่วนตัวอยู่ในนั้น`)}</p> : null}
          </Panel>

          <Panel title={titleOf("practice")} aside={stepBadge("practice")}>
            <p className="text-[13px] leading-relaxed text-dl-muted">
              {T("A harmless action will wait for you, like real risky work does. Confirm it and watch it run once. It only writes a short note.", "การกระทำที่ไม่เป็นอันตรายหนึ่งอย่างจะรอให้คุณยืนยัน เหมือนงานเสี่ยงจริง ยืนยันแล้วดูมันรันหนึ่งครั้ง มันเขียนบันทึกสั้น ๆ เท่านั้น")}
            </p>
            <div className="mt-3"><Button onClick={startPractice} disabled={busy || !!practice || !hasApprover}>{T("Start a practice approval", "เริ่มลองอนุมัติ")}</Button></div>
            {!hasApprover ? <p className="mt-2 text-[12px] text-dl-muted">{T("Finish step 2 first: nobody can confirm yet.", "ทำขั้นที่ 2 ให้เสร็จก่อน: ยังไม่มีผู้ยืนยัน")}</p> : null}
            {practice ? (
              <div className="mt-3 rounded border border-dl-rule p-3 text-[13px] leading-relaxed">
                <p className="text-dl-text">{T("Waiting for you:", "รอคุณอยู่:")} {waitingPractice?.goal ?? T("practice approval", "ลองอนุมัติ")}</p>
                <p className="text-dl-muted">{T("It will write the note practice-approval.txt in the exchange folder, nothing else.", "จะเขียนบันทึก practice-approval.txt ในโฟลเดอร์ exchange เท่านั้น ไม่ทำอย่างอื่น")}</p>
                <ConfirmAction approvalId={practice.approval_id} actionSha256={practice.action_sha256} hasDevice={hasDevice} onDecided={practiceDecided} />
              </div>
            ) : null}
            {practiceResult ? <p role="status" className="mt-3 text-[13px] leading-relaxed text-dl-leaf">{practiceResult}</p> : null}
          </Panel>

          {next === null ? (
            <Panel title={T("All set", "พร้อมใช้งาน")}>
              <p className="text-sm text-dl-leaf">{T("Everything is checked and you have confirmed one action yourself. Go to Chat and ask for something real.", "ตรวจครบแล้ว และคุณยืนยันการกระทำหนึ่งครั้งด้วยตัวเองแล้ว ไปที่ Chat แล้วสั่งงานจริงได้เลย")}</p>
            </Panel>
          ) : null}
          <p className="text-[12px] text-dl-muted">{T(`Steps: ${STEP_IDS.length}. The setup writes nothing except what you confirm here, a backup you ask for, and a short practice note.`, `ทั้งหมด ${STEP_IDS.length} ขั้น ตัวช่วยตั้งค่าไม่เขียนอะไรนอกจากสิ่งที่คุณยืนยันที่นี่ สำรองข้อมูลที่คุณสั่ง และบันทึกฝึกสั้น ๆ`)}</p>
        </div>
      </PageBody>
    </>
  );
}
