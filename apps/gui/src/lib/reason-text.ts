/**
 * Why an episode ended, in words a person can act on (Round 101, UX audit).
 *
 * The Desk used to show the runtime's own codes (`fdia_blocked`, `pending_approval`, `llm_finished`...) as badges. They are exact for the people who built the system and mean nothing to anyone else.
 * Each code now has a short label, one sentence on what happened, and what the person can do about it. Pure (no React, no network) so a plain node test checks that every code the runtime can produce has a text
 * in both languages. An unknown code is shown as it is, with a neutral sentence, never hidden.
 */
export type ReasonTone = "leaf" | "amber" | "rust" | "muted";
export type Lang = "th" | "en";
export interface ReasonText { label: string; what: string; next: string; tone: ReasonTone }

type Pair = { en: string; th: string };
interface Entry { label: Pair; what: Pair; next: Pair; tone: ReasonTone }

const E = (label: Pair, what: Pair, next: Pair, tone: ReasonTone): Entry => ({ label, what, next, tone });

const TABLE: Record<string, Entry> = {
  llm_finished: E({ en: "Done", th: "เสร็จแล้ว" }, { en: "The agent finished and gave an answer.", th: "เอเจนต์ทำงานเสร็จและตอบแล้ว" }, { en: "Read the answer; open the steps if you want to see how it got there.", th: "อ่านคำตอบ ถ้าอยากรู้ว่าทำอย่างไรให้เปิดดูขั้นตอน" }, "leaf"),
  warm_recall: E({ en: "Answered from memory", th: "ตอบจากที่เคยทำ" }, { en: "The same request was answered before and nothing it depended on has changed, so no model was called.", th: "เคยตอบคำขอเดียวกันนี้แล้วและสิ่งที่เกี่ยวข้องไม่เปลี่ยน จึงไม่ได้เรียกโมเดล" }, { en: "Nothing to do. Ask again with a changed request if you want a fresh answer.", th: "ไม่ต้องทำอะไร ถ้าอยากได้คำตอบใหม่ให้เปลี่ยนคำขอ" }, "leaf"),
  pending_approval: E({ en: "Waiting for you", th: "รอคุณอนุมัติ" }, { en: "The agent wants to do something that needs your approval. Nothing has been done yet.", th: "เอเจนต์ต้องการทำสิ่งที่ต้องให้คุณอนุมัติ ยังไม่มีอะไรถูกทำ" }, { en: "Open Approvals, read what it wants to do, then approve or reject.", th: "เปิดหน้าอนุมัติ อ่านสิ่งที่มันจะทำ แล้วอนุมัติหรือปฏิเสธ" }, "amber"),
  plan_ready: E({ en: "Plan ready", th: "แผนพร้อมแล้ว" }, { en: "The agent made a plan and is waiting for you to confirm it.", th: "เอเจนต์วางแผนแล้วและรอให้คุณยืนยัน" }, { en: "Open Approvals and read the numbered steps.", th: "เปิดหน้าอนุมัติ อ่านขั้นตอนที่เรียงเลข" }, "amber"),
  needs_clarification: E({ en: "Has a question", th: "มีคำถามถึงคุณ" }, { en: "The agent stopped before starting because something in the request is missing or unclear.", th: "เอเจนต์หยุดก่อนเริ่มเพราะคำขอขาดหรือคลุมเครือบางส่วน" }, { en: "Answer the question, then send the request again.", th: "ตอบคำถาม แล้วส่งคำขอเดิมอีกครั้ง" }, "amber"),
  waiting_for_clarification: E({ en: "Has a question", th: "มีคำถามถึงคุณ" }, { en: "The result did not match what you asked, so the agent is asking which part should change.", th: "ผลที่ได้ไม่ตรงกับที่ขอ เอเจนต์จึงถามว่าจะให้แก้ส่วนไหน" }, { en: "Answer the question.", th: "ตอบคำถาม" }, "amber"),
  waiting_for_input: E({ en: "Waiting for you", th: "รอคุณตอบ" }, { en: "The agent is waiting for something only you can give.", th: "เอเจนต์รอสิ่งที่มีแต่คุณให้ได้" }, { en: "Open the question and answer it.", th: "เปิดคำถามและตอบ" }, "amber"),
  fdia_blocked: E({ en: "Refused by safety check", th: "ถูกปฏิเสธโดยด่านความปลอดภัย" }, { en: "A safety rule stopped the action before it ran: it was forbidden, or there was too little to go on. Nothing was changed.", th: "กฎความปลอดภัยหยุดการกระทำก่อนทำจริง: ต้องห้าม หรือหลักฐานไม่พอ ไม่มีอะไรถูกเปลี่ยน" }, { en: "Open the episode to see which rule and which numbers. If it is something you want, change the request or the policy.", th: "เปิดดูรายละเอียดว่ากฎไหนและตัวเลขเท่าไร ถ้าต้องการให้ทำ ให้แก้คำขอหรือนโยบาย" }, "rust"),
  guard_blocked: E({ en: "Refused: unsafe request", th: "ถูกปฏิเสธ: คำขอไม่ปลอดภัย" }, { en: "The request itself looked like an attack or an attempt to override the agent's rules, so it was not run.", th: "คำขอดูเหมือนการโจมตีหรือพยายามข้ามกฎของเอเจนต์ จึงไม่ถูกรัน" }, { en: "If you wrote it yourself, say it differently and avoid instructions about ignoring rules.", th: "ถ้าคุณเขียนเอง ให้เรียบเรียงใหม่และเลี่ยงคำสั่งให้ละเลยกฎ" }, "rust"),
  jury_rejected: E({ en: "Refused by the jury", th: "คณะตรวจไม่เห็นด้วย" }, { en: "The independent reviewers did not agree to this action, so it was not run.", th: "ผู้ตรวจอิสระไม่เห็นด้วยกับการกระทำนี้ จึงไม่ถูกรัน" }, { en: "Read their reasons in the episode; change the request if needed.", th: "อ่านเหตุผลในรายละเอียด แก้คำขอถ้าจำเป็น" }, "rust"),
  intent_constraint_blocked: E({ en: "Stopped: outside what you asked", th: "หยุด: เกินจากที่ขอ" }, { en: "The agent was about to do something your request did not allow.", th: "เอเจนต์กำลังจะทำสิ่งที่คำขอของคุณไม่อนุญาต" }, { en: "Check the request's conditions and send it again.", th: "ตรวจเงื่อนไขในคำขอแล้วส่งใหม่" }, "rust"),
  notary_unavailable: E({ en: "Stopped: record keeper offline", th: "หยุด: ผู้บันทึกไม่พร้อม" }, { en: "The separate record keeper could not be reached, so the agent did not act (it will not act without a record).", th: "ติดต่อผู้บันทึกแยกไม่ได้ เอเจนต์จึงไม่ลงมือ (ไม่ทำโดยไม่มีบันทึก)" }, { en: "Start the notary (see Status) and try again.", th: "เริ่ม notary (ดูหน้าสถานะ) แล้วลองใหม่" }, "rust"),
  residency_blocked: E({ en: "Stopped: data would leave the allowed region", th: "หยุด: ข้อมูลจะออกนอกภูมิภาคที่อนุญาต" }, { en: "Sending this to the chosen model would break your data-location policy, so nothing was sent.", th: "การส่งเรื่องนี้ไปยังโมเดลที่เลือกจะขัดกับนโยบายที่เก็บข้อมูล จึงไม่ได้ส่ง" }, { en: "Choose a model inside the allowed region, or change the policy (Sovereignty).", th: "เลือกโมเดลในภูมิภาคที่อนุญาต หรือแก้นโยบาย (หน้าอธิปไตยข้อมูล)" }, "rust"),
  budget_exceeded: E({ en: "Stopped: spending limit", th: "หยุด: ถึงวงเงิน" }, { en: "The next model call would have gone over the limit for this task, so it stopped.", th: "การเรียกโมเดลครั้งถัดไปจะเกินวงเงินของงานนี้ จึงหยุด" }, { en: "Raise the limit or make the request smaller.", th: "เพิ่มวงเงินหรือทำคำขอให้เล็กลง" }, "amber"),
  daily_budget_exhausted: E({ en: "Stopped: today's limit reached", th: "หยุด: ถึงวงเงินวันนี้" }, { en: "Today's spending limit has been reached. Nothing was run.", th: "ใช้ถึงวงเงินของวันนี้แล้ว ไม่ได้รันอะไร" }, { en: "It resets as the 24-hour window moves on, or raise the limit (Safety).", th: "จะรีเซ็ตเมื่อครบ 24 ชั่วโมง หรือเพิ่มวงเงิน (หน้าความปลอดภัย)" }, "amber"),
  rate_limited: E({ en: "Too many requests", th: "คำขอถี่เกินไป" }, { en: "Too many requests in the last hour. Nothing was run.", th: "ส่งคำขอถี่เกินไปในชั่วโมงที่ผ่านมา ไม่ได้รันอะไร" }, { en: "Wait a while and try again.", th: "รอสักครู่แล้วลองใหม่" }, "amber"),
  paused: E({ en: "Paused", th: "พักอยู่" }, { en: "The agent is paused by its owner. Nothing was run.", th: "เจ้าของสั่งพักเอเจนต์ ไม่ได้รันอะไร" }, { en: "Resume it in Safety when you are ready.", th: "กลับมาทำงานได้ที่หน้าความปลอดภัย" }, "amber"),
  stuck_repeating: E({ en: "Stopped: going in circles", th: "หยุด: วนซ้ำ" }, { en: "The agent kept repeating the same step without getting anywhere, so it stopped.", th: "เอเจนต์ทำขั้นเดิมซ้ำโดยไม่คืบหน้า จึงหยุด" }, { en: "Rephrase the request or give it the missing detail.", th: "เรียบเรียงคำขอใหม่หรือเพิ่มรายละเอียดที่ขาด" }, "amber"),
  max_iterations_reached: E({ en: "Ran out of steps", th: "ใช้ขั้นตอนครบแล้ว" }, { en: "The agent used all the steps it is allowed for one request without finishing.", th: "เอเจนต์ใช้ขั้นตอนที่อนุญาตต่อหนึ่งคำขอจนหมดโดยยังไม่เสร็จ" }, { en: "Break the request into smaller parts.", th: "แบ่งคำขอเป็นส่วนเล็กลง" }, "amber"),
  max_seconds_exceeded: E({ en: "Ran out of time", th: "หมดเวลา" }, { en: "The request took longer than the time allowed.", th: "คำขอใช้เวลานานกว่าที่กำหนด" }, { en: "Try a smaller request, or a faster model.", th: "ลองคำขอที่เล็กลงหรือใช้โมเดลที่เร็วกว่า" }, "amber"),
  parse_error: E({ en: "The model's reply was unusable", th: "คำตอบของโมเดลใช้ไม่ได้" }, { en: "The model answered in a form the agent could not read, even after one more try.", th: "โมเดลตอบในรูปแบบที่เอเจนต์อ่านไม่ได้ แม้ลองอีกครั้ง" }, { en: "Try again, or choose a stronger model (Models).", th: "ลองใหม่ หรือเลือกโมเดลที่แข็งแรงกว่า (หน้าโมเดล)" }, "amber"),
  llm_error: E({ en: "The model could not be reached", th: "เรียกโมเดลไม่สำเร็จ" }, { en: "The model service did not answer properly (it may be offline, out of credit or busy).", th: "บริการโมเดลไม่ตอบอย่างถูกต้อง (อาจปิดอยู่ เครดิตหมด หรือคิวแน่น)" }, { en: "Check that the model is running or the account has credit, then try again.", th: "ตรวจว่าโมเดลทำงานอยู่หรือบัญชียังมีเครดิต แล้วลองใหม่" }, "rust"),
  exception: E({ en: "Something went wrong inside", th: "ระบบขัดข้องภายใน" }, { en: "An unexpected error stopped this request. Nothing was changed by the agent after it.", th: "เกิดข้อผิดพลาดที่ไม่คาดคิดจนต้องหยุด ไม่มีการเปลี่ยนแปลงหลังจากนั้น" }, { en: "Try again. If it repeats, send the episode id to the developer.", th: "ลองใหม่ ถ้าเกิดซ้ำให้ส่งรหัส episode ให้ผู้พัฒนา" }, "rust"),
  nesting_limit: E({ en: "Stopped: too many helpers inside helpers", th: "หยุด: ผู้ช่วยซ้อนกันเกินไป" }, { en: "An agent started another agent too many levels deep.", th: "เอเจนต์เรียกเอเจนต์อื่นซ้อนกันลึกเกินกำหนด" }, { en: "Make the request simpler.", th: "ทำคำขอให้ง่ายขึ้น" }, "amber"),
  delegation_depth_exceeded: E({ en: "Stopped: too many helpers inside helpers", th: "หยุด: ผู้ช่วยซ้อนกันเกินไป" }, { en: "An agent started another agent too many levels deep.", th: "เอเจนต์เรียกเอเจนต์อื่นซ้อนกันลึกเกินกำหนด" }, { en: "Make the request simpler.", th: "ทำคำขอให้ง่ายขึ้น" }, "amber"),
  running: E({ en: "Running", th: "กำลังทำงาน" }, { en: "The agent is working on it right now.", th: "เอเจนต์กำลังทำอยู่" }, { en: "Wait, or watch the steps.", th: "รอ หรือดูขั้นตอน" }, "muted"),
  interrupted: E({ en: "Interrupted", th: "ถูกขัดจังหวะ" }, { en: "The process stopped in the middle (a restart or a crash).", th: "โปรเซสหยุดกลางคัน (รีสตาร์ทหรือล่ม)" }, { en: "Open Sessions to see what already ran before you send it again.", th: "เปิดหน้าประวัติเพื่อดูว่าอะไรรันไปแล้วก่อนส่งใหม่" }, "amber"),
};

export function knownReasons(): string[] {
  return Object.keys(TABLE);
}

export function describeReason(code: string | null | undefined, lang: Lang = "en"): ReasonText {
  const raw = String(code ?? "").trim();
  const hit = raw ? TABLE[raw] : undefined;
  if (hit) return { label: hit.label[lang], what: hit.what[lang], next: hit.next[lang], tone: hit.tone };
  return {
    label: raw || (lang === "th" ? "ไม่ทราบ" : "Unknown"),
    what: lang === "th" ? "ระบบไม่มีคำอธิบายสำหรับสถานะนี้ (แสดงรหัสตามที่ระบบรายงาน)" : "No plain-language text exists for this status (shown as the system reported it).",
    next: lang === "th" ? "เปิดรายละเอียดของ episode" : "Open the episode for details.",
    tone: "muted",
  };
}
