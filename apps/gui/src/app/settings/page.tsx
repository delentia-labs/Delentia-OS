"use client";

import { useEffect, useState } from "react";
import { Badge, Button, Code, PageBody, PageHeader, Panel } from "@/components/desk/ui";
import { useLang } from "@/components/desk/i18n";
import { forgetStoredApiKey, getGateway, getHealthStatus, getSessionApiKey, setSessionApiKey } from "@/lib/delentia-client";

const DEFAULT_GATEWAY = "http://localhost:8000";

export default function SettingsPage() {
  const { lang } = useLang();
  const [gateway, setGateway] = useState(DEFAULT_GATEWAY);
  const [token, setToken] = useState("");
  const [show, setShow] = useState(false);
  const [saved, setSaved] = useState(false);
  const [test, setTest] = useState<{ tone: "leaf" | "rust"; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    forgetStoredApiKey();
    setGateway(getGateway());
    setToken(getSessionApiKey() ?? "");
  }, []);

  const save = () => {
    try {
      window.localStorage.setItem("delentia_gateway", gateway.trim() || DEFAULT_GATEWAY);
    } catch {
      /* storage blocked: the gateway then resets on reload */
    }
    setSessionApiKey(token);
    setSaved(true);
    window.setTimeout(() => setSaved(false), 2500);
  };

  const check = async () => {
    setTesting(true);
    setTest(null);
    const health = await getHealthStatus(gateway.trim() || DEFAULT_GATEWAY);
    setTest(health.version === "offline"
      ? { tone: "rust", text: `${gateway} is not reachable. Start it with \`delentia serve\`.` }
      : { tone: "leaf", text: `Reachable: ${health.service} v${health.version} (${health.status})` });
    setTesting(false);
  };

  return (
    <>
      <PageHeader title={lang === "th" ? "ตั้งค่า" : "Settings"}
        lead={lang === "th"
          ? "ที่อยู่ของ Delentia API และ token สำหรับเรียกใช้ token เก็บไว้ในหน่วยความจำของหน้าต่างนี้เท่านั้น ไม่ถูกเขียนลงดิสก์"
          : "Where the Delentia API lives and the token used to call it. The token is kept in this window's memory only, never written to disk."} />
      <PageBody>
        <div className="max-w-xl space-y-6">
          <Panel title="API">
            <label className="block">
              <span className="text-[13px] text-dl-muted">Gateway address</span>
              <input value={gateway} onChange={(e) => setGateway(e.target.value)} spellCheck={false}
                className="desk-focus desk-mono mt-1 w-full rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text" />
            </label>
            <label className="mt-4 block">
              <span className="text-[13px] text-dl-muted">API token (<Code>DELENTIA_API_TOKEN</Code>)</span>
              <div className="mt-1 flex gap-2">
                <input value={token} onChange={(e) => setToken(e.target.value)} type={show ? "text" : "password"} autoComplete="off" spellCheck={false}
                  placeholder="only needed when the API is not on localhost"
                  className="desk-focus desk-mono w-full rounded border border-dl-rule bg-dl-ink px-3 py-2 text-sm text-dl-text placeholder:text-dl-muted/50" />
                <Button tone="ghost" onClick={() => setShow((v) => !v)}>{show ? "Hide" : "Show"}</Button>
              </div>
            </label>
            <div className="mt-5 flex flex-wrap items-center gap-3">
              <Button onClick={save}>Save</Button>
              <Button tone="ghost" onClick={check} disabled={testing}>{testing ? "Checking…" : "Test connection"}</Button>
              {saved ? <Badge tone="leaf">saved</Badge> : null}
            </div>
            {test ? <p role="status" className={`mt-3 text-[13px] ${test.tone === "leaf" ? "text-dl-leaf" : "text-dl-rust"}`}>{test.text}</p> : null}
          </Panel>

          <Panel title={lang === "th" ? "อยู่ที่อื่น" : "Configured elsewhere"}>
            <ul className="space-y-2 text-sm leading-relaxed text-dl-muted">
              <li>Model and provider: the <Code>Models</Code> page, or <Code>delentia model set</Code>.</li>
              <li>Who may approve actions: <Code>delentia approvals keygen</Code> and <Code>DELENTIA_APPROVER_PUBKEYS</Code>.</li>
              <li>Chat channels and their allowlists: the <Code>Channels</Code> page shows them; they are set by environment variables.</li>
              <li>Pipeline and warm recall: <Code>DELENTIA_ALGORITHM_PIPELINE</Code>, <Code>DELENTIA_WARM_RECALL</Code> (on under <Code>delentia serve</Code>).</li>
            </ul>
          </Panel>
        </div>
      </PageBody>
    </>
  );
}
