"use client";

import { useLang } from "@/components/desk/i18n";
import { Badge, Code, ErrorNote, PageBody, PageHeader, Panel, Row, useDeskData } from "@/components/desk/ui";
import { desk } from "@/lib/desk-api";

const NAMES: Record<string, string> = { telegram: "Telegram", discord: "Discord", slack: "Slack", line: "LINE", whatsapp: "WhatsApp", signal: "Signal", email: "Email" };

export default function ChannelsPage() {
  const { t, lang } = useLang();
  const channels = useDeskData(() => desk.channels(), [], 15000);
  return (
    <>
      <PageHeader title={t("channels")}
        lead={lang === "th"
          ? "ช่องทางแชทที่ส่งงานให้ agent ได้ ทุกช่องทางปิดไว้โดยปริยาย: ถ้าไม่ตั้ง allowlist จะไม่มีใครส่งงานได้เลย"
          : "Chat channels that can hand work to the agent. Every channel fails closed: without an allowlist, nobody can send it work."} />
      <PageBody>
        {channels.error ? <ErrorNote error={channels.error} onRetry={channels.reload} /> : null}
        <div className="grid gap-4 xl:grid-cols-2">
          {channels.data?.channels.map((c) => (
            <Panel key={c.channel} title={NAMES[c.channel] ?? c.channel}
              aside={c.running ? <Badge tone="leaf">running</Badge> : c.token_present ? <Badge>configured</Badge> : <Badge>not set up</Badge>}>
              <Row label="Bot token in the environment">{c.token_present ? "yes" : "no"}</Row>
              <Row label="Who may send work">
                {c.allowlist === "everyone" ? <Badge tone="amber">everyone</Badge>
                  : c.allowlist === "nobody" ? "nobody" : `${c.allowlist_count} listed sender${c.allowlist_count === 1 ? "" : "s"}`}
              </Row>
              <p className="mt-3 text-[12px] leading-relaxed text-dl-muted">
                Allowlist: <Code>{c.allowlist_env}</Code> (comma-separated sender ids, or <Code>*</Code> for everyone). Sender ids stay on the host and are not shown here.
              </p>
            </Panel>
          ))}
        </div>
      </PageBody>
    </>
  );
}
