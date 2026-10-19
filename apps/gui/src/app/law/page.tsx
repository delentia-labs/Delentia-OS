"use client";

import { useState } from "react";
import { useLang } from "@/components/desk/i18n";
import { Badge, Button, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk, type LawCheck, type LawLookup, type LawPackInfo } from "@/lib/desk-api";

type T = (en: string, th: string) => string;

const field = "desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-1.5 text-[13px] text-dl-text placeholder:text-dl-muted/50";
const label = "text-[12px] text-dl-muted";

function verifiedBadge(p: LawPackInfo, T: T) {
  if (p.error) return <Badge tone="rust">{T("unreadable", "อ่านไม่ได้")}</Badge>;
  if (p.verified === true) return <Badge tone="leaf" title={T("The text is exactly what was imported", "ข้อความตรงกับที่นำเข้า")}>{T("unchanged since import", "ไม่ถูกแก้หลังนำเข้า")}</Badge>;
  if (p.verified === false) return <Badge tone="rust" title={T("Do not rely on this pack", "ห้ามใช้ pack นี้")}>{T("CHANGED after import", "ถูกแก้หลังนำเข้า")}</Badge>;
  return <Badge tone="amber" title={T("Imported before fingerprints existed: import it again", "นำเข้าก่อนมี fingerprint: นำเข้าใหม่")}>{T("cannot be checked", "ตรวจไม่ได้")}</Badge>;
}

export default function LawPage() {
  const { lang } = useLang();
  const T: T = (en, th) => (lang === "th" ? th : en);
  const state = useDeskData(() => desk.lawPacks(), [], 30000);
  const d = state.data;

  const [name, setName] = useState("");
  const [edition, setEdition] = useState("");
  const [jurisdiction, setJurisdiction] = useState("");
  const [source, setSource] = useState("");
  const [text, setText] = useState("");
  const [embed, setEmbed] = useState(true);
  const [allowFlagged, setAllowFlagged] = useState(false);
  const [importing, setImporting] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const [pack, setPack] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [found, setFound] = useState<LawLookup | null>(null);
  const [checked, setChecked] = useState<LawCheck | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const doImport = async () => {
    setImporting(true); setNote(null);
    try {
      const r = await desk.lawImport({ name: name.trim(), text, edition: edition.trim(), jurisdiction: jurisdiction.trim(), source: source.trim(), embed, allow_flagged: allowFlagged });
      setNote(T(`Imported ${r.label}: ${r.sections} sections, ${r.chunks} passages, ${r.embedded ? "searchable by meaning" : "word search only"} (fingerprint ${r.fingerprint})${r.reviewed_flags.length ? `; ${r.reviewed_flags.length} flagged place(s) recorded` : ""}.`,
        `นำเข้า ${r.label} แล้ว: ${r.sections} มาตรา ${r.chunks} ท่อน ${r.embedded ? "ค้นด้วยความหมายได้" : "ค้นด้วยคำเท่านั้น"} (fingerprint ${r.fingerprint})${r.reviewed_flags.length ? ` บันทึกจุดที่ถูกตั้งธง ${r.reviewed_flags.length} จุด` : ""}`));
      setText(""); state.reload();
    } catch (e) { setNote(e instanceof Error ? e.message : String(e)); } finally { setImporting(false); }
  };

  const doArchive = async (packName: string) => {
    if (!window.confirm(T(`Take ${packName} out of use? The file is moved to an archive folder, not deleted.`, `เลิกใช้ ${packName}? ไฟล์จะถูกย้ายไปโฟลเดอร์เก็บถาวร ไม่ถูกลบ`))) return;
    setNote(null);
    try { const r = await desk.lawArchive(packName); setNote(T(`Archived ${r.archived}.`, `เก็บถาวรแล้ว ${r.archived}`)); state.reload(); } catch (e) { setNote(e instanceof Error ? e.message : String(e)); }
  };

  const doLookup = async () => {
    setBusy(true); setErr(null); setChecked(null);
    try { setFound(await desk.lawLookup(pack, question.trim())); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  const doCheck = async () => {
    setBusy(true); setErr(null);
    try { setChecked(await desk.lawCheck(pack, question.trim(), answer.trim())); } catch (e) { setErr(e instanceof Error ? e.message : String(e)); } finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title={T("Law Pack", "ตัวบทกฎหมาย (Law Pack)")}
        lead={lang === "th"
          ? "คุณนำเข้าตัวบทกฎหมายเอง ระบบค้นท่อนที่ตอบคำถามได้ โมเดลตอบจากท่อนเหล่านั้นและต้องระบุมาตรา และตัวตรวจจะติดป้ายคำตอบที่อ้างเลขหรือมาตราที่ไม่ได้อยู่ในท่อนที่แสดง ไม่ใช่คำแนะนำทางกฎหมาย และไม่ได้แปลว่าโมเดลรู้กฎหมาย ข้อความที่นำเข้าอาจล้าสมัย ตรวจฉบับ (edition) ทุกครั้ง"
          : "You import the statute text yourself. The system finds the passages that answer a question; the model answers only from them and must name the sections; a checker labels any answer that quotes a number or section the shown passages do not contain. Not legal advice, and not a model that knows the law. The text you import may be out of date: always check the edition."} />
      <PageBody>
        {state.error ? <ErrorNote error={state.error} onRetry={state.reload} /> : null}
        {note ? <p role="status" className="mb-4 rounded border border-dl-fern bg-dl-pine/30 px-3 py-2 text-[13px] text-dl-text">{note}</p> : null}
        {d ? (
          <div className="space-y-6">
            <Panel title={T("Imported packs", "pack ที่นำเข้าแล้ว")} aside={<span className="desk-mono text-[11px] text-dl-muted">{d.packs.length}</span>}>
              {d.packs.length ? (
                <div className="space-y-3">
                  {d.packs.map((p) => (
                    <div key={p.name} className="rounded border border-dl-rule bg-dl-ink/40 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2"><span className="desk-mono text-[13px] text-dl-text">{p.name}</span>{verifiedBadge(p, T)}{p.reviewed_flags ? <Badge tone="amber" title={T("The content screen flagged places in this text; they were read and imported on the owner's say-so", "ตัวกรองเนื้อหาตั้งธงบางจุดในข้อความนี้ เจ้าของอ่านแล้วอนุมัตินำเข้า")}>{T(`${p.reviewed_flags} flagged place(s) accepted`, `ธงที่รับแล้ว ${p.reviewed_flags} จุด`)}</Badge> : null}{p.embedded ? <Badge tone="fern">{T("meaning search", "ค้นด้วยความหมาย")}</Badge> : <Badge tone="muted">{T("word search", "ค้นด้วยคำ")}</Badge>}<span className="ml-auto"><Button tone="amber" onClick={() => doArchive(p.name)}>{T("Archive", "เก็บถาวร")}</Button></span></div>
                      {!p.error ? <p className="mt-1 text-[12px] text-dl-muted">{p.jurisdiction} · {T("edition", "ฉบับ")}: {p.edition} · {p.sections} {T("sections", "มาตรา")} · {p.chunks} {T("passages", "ท่อน")} · sha256 {p.sha256}</p> : null}
                    </div>
                  ))}
                  <Row label={T("Agent tool", "เครื่องมือของ agent")}>{d.tool_listed ? T("listed in the agent's menu (delentia_law_lookup)", "อยู่ในเมนูของ agent (delentia_law_lookup)") : T("not listed (no pack)", "ไม่อยู่ในเมนู (ยังไม่มี pack)")}</Row>
                </div>
              ) : <p className="text-[13px] text-dl-muted">{T("No pack yet. Import one below; until then the agent's law tool is not even in its menu.", "ยังไม่มี pack นำเข้าด้านล่าง จนกว่าจะมี เครื่องมือกฎหมายของ agent จะไม่อยู่ในเมนูด้วยซ้ำ")}</p>}
            </Panel>

            <Panel title={T("Ask and check", "ถามและตรวจ")}>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block"><span className={label}>{T("Pack", "pack")}</span>
                  <select value={pack} onChange={(e) => setPack(e.target.value)} className={field} aria-label="Pack">
                    <option value="">{d.packs.length === 1 ? d.packs[0].name : T("(choose)", "(เลือก)")}</option>
                    {d.packs.filter((p) => !p.error).map((p) => <option key={p.name} value={p.name}>{p.name}</option>)}
                  </select></label>
                <label className="block"><span className={label}>{T("Question", "คำถาม")}</span><input value={question} onChange={(e) => setQuestion(e.target.value)} className={field} aria-label="Question" /></label>
              </div>
              <div className="mt-3 flex items-center gap-3">
                <Button onClick={doLookup} disabled={busy || !question.trim() || !d.packs.length}>{T("Find the passages", "ค้นท่อน")}</Button>
                <span className="text-[12px] text-dl-muted">{T("No model is called: this only shows what the agent would be shown.", "ไม่เรียกโมเดล: แสดงเฉพาะสิ่งที่ agent จะได้เห็น")}</span>
              </div>
              {err ? <p role="alert" className="mt-3 text-[13px] text-dl-rust">{err}</p> : null}
              {found?.error ? <p role="alert" className="mt-3 text-[13px] text-dl-rust">{found.error}</p> : null}
              {found?.passages ? (
                <div className="mt-4 space-y-2">
                  <p className="text-[12px] text-dl-muted">{found.pack}</p>
                  {found.passages.map((p, i) => (
                    <div key={i} className="rounded border border-dl-rule bg-dl-ink/40 px-3 py-2"><p className="desk-mono text-[12px] text-dl-fern">{T("Section", "มาตรา")} {p.section}</p><p className="mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-dl-text">{p.text}</p></div>
                  ))}
                  <label className="block pt-2"><span className={label}>{T("Paste an answer from anywhere to check it against these passages", "วางคำตอบจากที่ใดก็ได้เพื่อตรวจกับท่อนเหล่านี้")}</span><textarea value={answer} onChange={(e) => setAnswer(e.target.value)} rows={4} className={field} aria-label="Answer to check" /></label>
                  <Button onClick={doCheck} disabled={busy || !answer.trim()}>{T("Check the answer", "ตรวจคำตอบ")}</Button>
                </div>
              ) : null}
              {checked ? (
                <div className="mt-4 rounded border border-dl-rule px-3 py-3" role="status">
                  <div className="flex flex-wrap items-center gap-2"><Badge tone={checked.check.grounded ? "leaf" : "rust"}>{checked.check.grounded ? T("grounded in the shown passages", "อิงท่อนที่แสดง") : T("NOT confirmed", "ยืนยันไม่ได้")}</Badge><span className="desk-mono text-[12px] text-dl-muted">{checked.check.status}</span></div>
                  <ul className="mt-2 list-disc pl-5 text-[13px] text-dl-text">
                    {checked.check.unsupported_numbers.length ? <li>{T("numbers not in the passages", "ตัวเลขที่ไม่อยู่ในท่อน")}: {checked.check.unsupported_numbers.join(", ")}</li> : null}
                    {checked.check.cites_unseen.length ? <li>{T("sections cited but not shown", "มาตราที่อ้างแต่ไม่ได้แสดง")}: {checked.check.cites_unseen.join(", ")}</li> : null}
                    {checked.check.cited_sections.length ? <li>{T("sections cited", "มาตราที่อ้าง")}: {checked.check.cited_sections.join(", ")}</li> : null}
                  </ul>
                  <p className="mt-2 text-[12px] text-dl-muted">{T("This checks the text against the passages. It does not check that the passages are current or that the answer is right: grounded is not the same as correct.", "ตรวจข้อความกับท่อนเท่านั้น ไม่ได้ตรวจว่าท่อนยังเป็นปัจจุบันหรือว่าคำตอบถูกต้อง: grounded ไม่เท่ากับ ถูกต้อง")}</p>
                </div>
              ) : null}
            </Panel>

            <Panel title={T("Import a statute", "นำเข้าตัวบท")}>
              <p className="mb-3 text-[13px] leading-relaxed text-dl-muted">{T(`Paste the text; a heading must start a line ("Section 12", "Article 12" or "มาตรา 12"). At most ${d.max_chars.toLocaleString()} characters, one statute per pack. The text is screened for instructions to a reader and refused if any are found. The pack gets a fingerprint: a file edited afterwards is refused.`,
                `วางข้อความ หัวมาตราต้องขึ้นต้นบรรทัด ("Section 12", "Article 12" หรือ "มาตรา 12") ไม่เกิน ${d.max_chars.toLocaleString()} ตัวอักษร หนึ่งฉบับต่อหนึ่ง pack ข้อความจะถูกตรวจว่ามีคำสั่งถึงผู้อ่านหรือไม่ ถ้ามีจะปฏิเสธ pack มี fingerprint ถ้าไฟล์ถูกแก้ภายหลังจะถูกปฏิเสธ`)}</p>
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block"><span className={label}>{T("Name (letters, digits, . _ -)", "ชื่อ (ตัวอักษร ตัวเลข . _ -)")}</span><input value={name} onChange={(e) => setName(e.target.value)} placeholder="thai-pdpa" className={field} aria-label="Pack name" /></label>
                <label className="block"><span className={label}>{T("Jurisdiction", "เขตอำนาจ")}</span><input value={jurisdiction} onChange={(e) => setJurisdiction(e.target.value)} placeholder="TH" className={field} aria-label="Jurisdiction" /></label>
                <label className="block"><span className={label}>{T("Edition (which version of the text this is)", "ฉบับ (ข้อความนี้คือฉบับไหน)")}</span><input value={edition} onChange={(e) => setEdition(e.target.value)} placeholder="Royal Gazette 2019-05-27" className={field} aria-label="Edition" /></label>
                <label className="block"><span className={label}>{T("Source (where you got it)", "แหล่งที่มา")}</span><input value={source} onChange={(e) => setSource(e.target.value)} placeholder="ratchakitcha.soc.go.th ..." className={field} aria-label="Source" /></label>
              </div>
              <label className="mt-3 block"><span className={label}>{T("Statute text", "ข้อความตัวบท")}</span><textarea value={text} onChange={(e) => setText(e.target.value)} rows={10} className={field} aria-label="Statute text" /></label>
              <label className="mt-3 flex items-center gap-2 text-[13px] text-dl-text"><input type="checkbox" checked={embed} onChange={(e) => setEmbed(e.target.checked)} />{T("Search by meaning (needs the local embedding model; can take minutes for a long statute)", "ค้นด้วยความหมาย (ต้องมีโมเดล embedding ในเครื่อง ตัวบทยาวอาจใช้เวลาหลายนาที)")}</label>
              <label className="mt-2 flex items-start gap-2 text-[13px] text-dl-text"><input type="checkbox" className="mt-1" checked={allowFlagged} onChange={(e) => setAllowFlagged(e.target.checked)} />{T("The content screen flagged places in this text and I have read them: they are genuine statute text (a real statute speaks of closing, destroying and cancelling). Record the flags and import.", "ตัวกรองเนื้อหาตั้งธงบางจุดและฉันอ่านแล้ว: เป็นข้อความตัวบทจริง (ตัวบทจริงพูดถึงการปิด การทำลาย การยกเลิกได้) บันทึกธงและนำเข้า")}</label>
              <div className="mt-3 flex items-center gap-3">
                <Button onClick={doImport} disabled={importing || !name.trim() || !edition.trim() || !jurisdiction.trim() || !source.trim() || !text.trim()}>{importing ? T("Importing…", "กำลังนำเข้า…") : T("Import", "นำเข้า")}</Button>
                <span className="text-[12px] text-dl-muted">{d.notice}</span>
              </div>
            </Panel>
          </div>
        ) : null}
      </PageBody>
    </>
  );
}
