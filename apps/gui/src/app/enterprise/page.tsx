"use client";

import Link from "next/link";
import { useLang } from "@/components/desk/i18n";
import { Empty, PageBody, PageHeader, Panel, Row, Code } from "@/components/desk/ui";

// Round 50: this page used to show a fixed PDPA "compliance rating" (35/100)
// with two written-in findings for any contract text, a made-up "master
// keypair" and a random "seal" - none of it computed. It now says what exists.
export default function EnterprisePage() {
  const { lang } = useLang();
  return (
    <>
      <PageHeader
        title="Enterprise vault"
        lead={lang === "th"
          ? "ยังไม่ได้สร้างส่วนตรวจสัญญา PDPA และตราประทับลายเซ็น หน้านี้จึงบอกเฉพาะสิ่งที่มีอยู่จริงในระบบตอนนี้"
          : "Contract (PDPA) review and signed seals are not built. This page lists only what exists today."}
      />
      <PageBody>
        <div className="grid gap-6 xl:grid-cols-2">
          <Panel title="What exists">
            <Row label="Hash-chained audit trail">
              <Link href="/audit" className="text-dl-leaf underline">Audit</Link>
            </Row>
            <Row label="Ed25519-signed human approvals">
              <Link href="/approvals" className="text-dl-leaf underline">Approvals</Link>
            </Row>
            <Row label="Signed audit for MCP tool calls">Delentia Guard (npm: <Code>delentia-guard</Code>)</Row>
            <Row label="Outside witness for the chain head">A3, in <Link href="/audit" className="text-dl-leaf underline">Audit</Link></Row>
          </Panel>
          <Panel title="What does not exist yet">
            <Empty title="No contract review, no compliance score">
              Nothing in Delentia reads a contract and rates it against PDPA yet. A rating would need a reviewed legal ruleset
              and a model that passes the tool-selection test; until then this page shows no score.
            </Empty>
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
