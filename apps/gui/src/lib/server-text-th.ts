// Round 106: sentences the SERVER builds and the Thai interface shows as they are (task results of the daemon, the residency hints, the identity notes, the law disclaimer, the witness summary,
// the signature check of the audit page). Exact sentences map to Thai; the ones with numbers in them are matched by pattern. A sentence nobody listed here is shown as the server wrote it, so a
// new server sentence is never lost, only left in English until it is added (the test lists every sentence the server is known to build).
//
// Audit event lines (the explorer's one-line summaries) are a log, not prose for a person to read at length, and stay as the server wrote them.

const EXACT: Record<string, string> = {
  "no token (loopback clients only)": "ไม่มีโทเคน (รับเฉพาะผู้เรียกจากเครื่องนี้)",
  "one shared token": "โทเคนร่วมหนึ่งอัน",
  "per-person tokens": "โทเคนรายบุคคล",
  "A token is shown once when created and only its SHA-256 is stored, so this page can list people but never show or recover a token.":
    "โทเคนแสดงครั้งเดียวตอนสร้าง และเก็บไว้เฉพาะ SHA-256 ของมัน หน้านี้จึงแสดงรายชื่อคนได้ แต่ไม่เคยแสดงหรือกู้โทเคนคืน",
  "this machine's local zone": "เขตเวลาของเครื่องนี้",
  "Ollama on this machine or network": "Ollama บนเครื่องนี้หรือในเครือข่ายนี้",
  "No sovereignty policy is set, so nothing stops a prompt from leaving this machine when a cloud model is selected. Set DELENTIA_HOME_REGION or run `delentia sovereignty set`.":
    "ยังไม่ได้ตั้งนโยบายอธิปไตยข้อมูล ดังนั้นถ้าเลือกโมเดลบนคลาวด์ ไม่มีอะไรกันไม่ให้ข้อความออกจากเครื่องนี้ ตั้ง DELENTIA_HOME_REGION หรือรัน `delentia sovereignty set`",
  "No sovereignty policy is set, so nothing restricts where prompts go.": "ยังไม่ได้ตั้งนโยบายอธิปไตยข้อมูล จึงไม่มีอะไรจำกัดว่าข้อความจะไปที่ไหน",
  "Not legal advice. This answer comes only from the text the owner supplied for this pack (check its edition); read the statute itself and ask a lawyer before relying on it.":
    "ไม่ใช่คำแนะนำทางกฎหมาย คำตอบนี้มาจากข้อความที่เจ้าของใส่ไว้ในชุดนี้เท่านั้น (ตรวจฉบับที่ใช้) อ่านตัวบทกฎหมายเองและปรึกษาทนายก่อนนำไปใช้",
  "no reminders due": "ไม่มีการเตือนที่ถึงเวลา",
  "no cron job due": "ไม่มีงานตามเวลาที่ถึงกำหนด",
  "no witness is configured: a rewrite of the whole log by someone with the host's root would not be noticed":
    "ยังไม่ได้ตั้งพยานภายนอก: ถ้าผู้ที่มีสิทธิ์ root บนเครื่องเขียนบันทึกทั้งหมดใหม่ ก็จะไม่มีใครสังเกตเห็น",
  "no witness has received the head recently: treat the log as tamper-EVIDENT only against edits, not against a rewrite of everything":
    "ไม่มีพยานได้รับหัวห่วงโซ่เมื่อไม่นานมานี้: ให้ถือว่าบันทึกเห็นร่องรอยการแก้เป็นจุดๆ ได้ แต่ไม่ครอบคลุมการเขียนใหม่ทั้งหมด",
  "NOT checked: the chain's hashes are verified, but no public key is known here to check the signatures against":
    "ยังไม่ได้ตรวจลายเซ็น: ตรวจแฮชของห่วงโซ่แล้ว แต่ที่นี่ไม่รู้จักกุญแจสาธารณะที่ใช้เทียบลายเซ็น",
  // Round 115: the 20 bundled starter skills (rct_control_plane/starter_skills.py), shown as the titles on the Skills page. The Architect reads these before they are merged.
  "read a file in the repository and summarize what it does": "อ่านไฟล์ในที่เก็บโค้ดแล้วสรุปว่ามันทำอะไร",
  "find where a function, class or setting is defined or used in the repository": "หาว่าฟังก์ชัน คลาส หรือการตั้งค่าหนึ่งถูกนิยามหรือถูกใช้อยู่ที่ใดในที่เก็บโค้ด",
  "explain how a module or feature works by reading its source": "อธิบายว่าโมดูลหรือฟีเจอร์ทำงานอย่างไร โดยอ่านซอร์สโค้ดของมัน",
  "list the TODO and FIXME comments in the code": "ไล่รายการคอมเมนต์ TODO และ FIXME ในโค้ด",
  "compare two files and say what differs between them": "เปรียบเทียบไฟล์สองไฟล์ แล้วบอกว่าต่างกันตรงไหน",
  "remember a fact or preference the user told me for later": "จำข้อเท็จจริงหรือความชอบที่ผู้ใช้บอกไว้ เพื่อใช้ภายหลัง",
  "recall what the user told me before about a topic": "นึกย้อนถึงสิ่งที่ผู้ใช้เคยบอกไว้เกี่ยวกับหัวข้อหนึ่ง",
  "read a web page at a given url and summarize it": "อ่านหน้าเว็บจาก URL ที่ให้มา แล้วสรุป",
  "research a topic on the web and answer with sources": "ค้นคว้าหัวข้อหนึ่งบนเว็บ แล้วตอบพร้อมแหล่งที่มา",
  "check whether a claim or number about the project is true": "ตรวจสอบว่าข้ออ้างหรือตัวเลขเกี่ยวกับโปรเจกต์เป็นจริงหรือไม่",
  "run a command or the tests and report the result": "รันคำสั่งหรือชุดทดสอบ แล้วรายงานผล",
  "fix a bug in a source file with a small patch and check it": "แก้บั๊กในไฟล์ซอร์สด้วยแพตช์เล็กๆ แล้วตรวจสอบ",
  "create a new file with given content in the repository": "สร้างไฟล์ใหม่ที่มีเนื้อหาตามที่กำหนดในที่เก็บโค้ด",
  "remind the user about something later or schedule a task": "เตือนผู้ใช้เรื่องหนึ่งในภายหลัง หรือตั้งเวลาให้งานหนึ่ง",
  "split a large job into independent subtasks that run in parallel": "แบ่งงานใหญ่เป็นงานย่อยที่เป็นอิสระต่อกันและรันพร้อมกัน",
  "show what the agent did recently from the audit log": "แสดงสิ่งที่เอเจนต์ทำล่าสุดจากบันทึกตรวจสอบ",
  "convert stored content to another format such as markdown or json": "แปลงเนื้อหาที่เก็บไว้เป็นรูปแบบอื่น เช่น markdown หรือ json",
  "list what tools and capabilities this agent has": "ไล่รายการเครื่องมือและความสามารถที่เอเจนต์นี้มี",
  "use a tool the system built for itself earlier": "ใช้เครื่องมือที่ระบบสร้างขึ้นเองก่อนหน้านี้",
  "read the full text of a tool result that was compressed": "อ่านข้อความเต็มของผลลัพธ์เครื่องมือที่ถูกบีบอัดไว้",
};

const PATTERNS: [RegExp, (m: RegExpMatchArray) => string][] = [
  [/^audit chain OK: (\d+) chained rows \((\d+) signed\), head seq (\d+)$/, (m) => `ห่วงโซ่ตรวจสอบปกติ: ${m[1]} แถว (เซ็นแล้ว ${m[2]}), head seq ${m[3]}`],
  [/^advanced (\d+) task\(s\)$/, (m) => `เดินงานต่อ ${m[1]} งาน`],
  [/^(\d+) cron job\(s\) started$/, (m) => `เริ่มงานตามเวลา ${m[1]} งาน`],
  [/^(\d+) reminder\(s\) fired$/, (m) => `ส่งการเตือน ${m[1]} รายการ`],
  [/^reviewed (\d+) learned skill\(s\): (\d+) proposal\(s\) ?(.*); nothing archived$/, (m) => `ตรวจทักษะที่เรียนรู้ ${m[1]} รายการ: ข้อเสนอ ${m[2]} รายการ; ไม่มีอะไรถูกเก็บเข้าคลัง`],
  [/^skill report by the curator \(report\): (\d+) proposal\(s\); nothing was archived$/, (m) => `รายงานทักษะจากผู้ดูแล: ข้อเสนอ ${m[1]} รายการ; ไม่มีอะไรถูกเก็บเข้าคลัง`],
  [/^signatures verified with (.+) \(fingerprint ([0-9a-f]+)\)$/i, (m) => `ตรวจลายเซ็นด้วย ${m[1]} (ลายนิ้วมือ ${m[2]})`],
  [/^(\d+) independent witness\(es\) hold a recent signed head; the (\d+) row\(s\) newer than the newest anchor are the window an attacker with the host's root could still rewrite unnoticed(; with only one witness.*)?$/,
    (m) => `พยานอิสระ ${m[1]} ราย ถือหัวห่วงโซ่ที่เซ็นไว้ล่าสุด; ${m[2]} แถวที่ใหม่กว่าจุดยึดล่าสุดคือช่วงที่ผู้โจมตีซึ่งมีสิทธิ์ root ยังเขียนใหม่ได้โดยไม่มีใครสังเกต${m[3] ? "; มีพยานรายเดียว ถ้าฝ่ายนั้นถูกยึดก็จบ: เพิ่มพยานคนที่สอง" : ""}`],
];

export function serverText(text: string | null | undefined, thai: boolean): string {
  if (text === null || text === undefined) return "";
  if (!thai) return text;
  const exact = EXACT[text];
  if (exact) return exact;
  for (const [re, make] of PATTERNS) {
    const m = text.match(re);
    if (m) return make(m);
  }
  return text;
}

/** For a test: the sentences that have a Thai text. */
export const KNOWN_EXACT = Object.keys(EXACT);
export const KNOWN_PATTERN_COUNT = PATTERNS.length;
