# คู่มือ: แก้ข้อความหน้ารายการ MCP (Smithery, MCPize) ให้ตรงกับของจริง

ผมแก้ได้เฉพาะไฟล์ใน repo. หน้าเว็บของ Smithery และ MCPize ต้องคุณล็อกอินแล้ววางข้อความเอง. ตั้งแต่ Round 49 มีข้อความเดิมที่ผิดค้างอยู่ ("World's First…", "ZK-FDIA", "85%", 5 จาก 6 เครื่องมือ). ทำหลัง publish npm 2.1.2 (ดู `NPM_PUBLISH_TH.md`) เพื่อให้ข้อความตรงกับรุ่นที่ติดตั้งได้จริง.

## ข้อความสั้น (ช่อง description / tagline)

> Advisory MCP tools for Claude, Cursor and Windsurf: a deterministic policy score (F = D^I × A), a seven-step reasoning checklist, deterministic context compression, and signed task packets. Hosted on Cloudflare Workers, reached through a stdio bridge. The tools are advisory: an agent that does not call them is not stopped. To enforce a policy on every tool call, use delentia-guard.

## ข้อความยาว (ช่อง README / long description)

```
Delentia MCP connector is a small stdio bridge that lets MCP clients call six tools hosted on Delentia's Cloudflare Workers.

What the tools do
- evaluate_fdia: returns a policy score F = D^I × A from the data quality, intent precision and owner decision you pass in. Same inputs, same answer.
- rct_think: a seven-step reasoning checklist that returns a heuristic alignment score. It helps catch vague plans; it does not guarantee correctness.
- compress_context / expand_context: deterministic compression of long tool output and logs (no model call). On real code, logs and documentation the aggressive mode removed about 70-75% of tokens; the default mode about 6-12%. The original can be kept and expanded.
- configure_policy, orchestrate_swarm: policy configuration and signed task packets.

What it is not
- The tools are advisory. An agent that never calls evaluate_fdia is not stopped by it. To check every tool call before it runs, use delentia-guard (npm).
- Not a sandbox, not a guarantee of safety, and not a measured reduction in hallucinations. See BENCHMARKS.md for what was measured and what was not.

Free sandbox: 50 calls per day per IP, counted approximately.
Source: https://github.com/delentia-labs/delentia-mcp (Apache-2.0). Security reports: security@delentia.com.
```

## วางที่ไหน

1. **Smithery** — https://smithery.ai/servers/delentia/delentia-sovereign → Settings/Edit (ปุ่มแก้ของเจ้าของ). วางข้อความสั้นที่ช่อง description และข้อความยาวที่ช่อง README. ลบคำว่า "World's First", "ZK", "zero-knowledge", "mathematical", ตัวเลข 74%/85%/91% ถ้ามีในช่องอื่น (tags, features list).
2. **MCPize** — ตรวจหน้ารายการของ `delentia-mcp`: ทุกข้อความที่พูดถึงจำนวนเครื่องมือต้องเป็น 6 และไม่มีเปอร์เซ็นต์ที่ไม่อยู่ในข้อความด้านบน.
3. ถ่ายภาพหน้าจอก่อนและหลัง ส่งให้ผมตรวจ ผมจะอัปเดตเอกสาร Round 91/92 ว่าแก้แล้ว.

## ข้อควรระวัง

- ตัวเลข 70-75% และ 6-12% มาจากการวัดบนข้อความจริง ตามรายงาน `ecosystem/benchmarks/compression-real/REPORT.md`. อย่าเปลี่ยนเป็นตัวเลขที่สูงกว่านี้.
- ถ้าจะเพิ่มคำใหม่ (เช่น "secure", "certified", "production-ready") ให้ถามผมก่อน: คำเหล่านั้นถูกเก็บกลับมาแล้วหลายแห่ง.
