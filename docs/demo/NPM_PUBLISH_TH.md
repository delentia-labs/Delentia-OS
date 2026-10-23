# คู่มือ: publish npm `delentia-guard` 0.1.1 และ `delentia-mcp` 2.1.2 แล้วค่อย merge PR #8

เวลา ~20 นาที. ผมไม่ publish ให้ (กฎ: ถามก่อนทุกครั้งที่ publish npm). ทำเองตามลำดับนี้ **ห้ามสลับ**

## ทำไมต้องเรียงลำดับ

PR #8 ของ repo `delentia-mcp` แก้ไฟล์ `server.json` (บอกรุ่น 2.1.2). ทันทีที่ merge เข้า `main` workflow "Publish to MCP Registry" จะรันเอง (ทำงานเมื่อ push แตะ `server.json`, `package.json` หรือ server-card) และประกาศรุ่น 2.1.2 ลง MCP Registry ทั้งที่บน npm ยังเป็น 2.1.1. ผู้ใช้ที่ติดตั้งจาก registry จะได้ข้อความว่าไม่พบรุ่น. จึงต้อง publish npm **ก่อน** แล้วจึง merge.

## ก่อนเริ่ม

1. เปิด PowerShell หรือ Git Bash. ตรวจว่าล็อกอิน npm เป็นบัญชีขององค์กร:
   ```bash
   npm whoami
   ```
   ควรตอบ `delentia-labs` (ตอนที่ผมตรวจเครื่องนี้ตอบแบบนี้). ถ้าไม่ใช่ ให้ `npm login`.
2. ตรวจว่าเปิด 2FA ไว้ (npm จะถามรหัส 6 หลักตอน publish ใส่ด้วย `--otp=123456` หรือรอให้ถาม).
3. ตรวจว่ากำลังอยู่บน branch ของ PR #8 และไม่มีไฟล์ค้าง:
   ```bash
   cd C:/Users/whale/Delentia/delentia-mcp
   git status --short
   git branch --show-current
   ```
   branch ต้องเป็น `round91/guard-hardening-readme`. ไฟล์ที่ขึ้น `??` (BENCHMARK_REPORT.md, demo/delentia-logo.png, fdia-policy.json) ไม่ถูกส่งขึ้นไป เพราะ `files` ใน package.json ระบุเฉพาะ bin, dist, assets, README, LICENSE, server.json.

## ขั้นที่ 1: delentia-guard 0.1.1

```bash
cd C:/Users/whale/Delentia/delentia-mcp/ecosystem
npm ci
npm run build
npm run bundle:guard
cd packages/guard/npm
npm pack --dry-run
```

ดูรายการไฟล์: ควรมี `cli.mjs`, `policies/`, `README.md`, `LICENSE` (~5 ไฟล์ ~230 kB). ตรวจว่า bundle ใหม่จริง:

```bash
grep -c "allow-hosts" cli.mjs
```
ต้องได้เลข 1 ขึ้นไป. แล้ว publish:

```bash
npm publish
```

ตรวจผล (รอ 1-2 นาที):

```bash
npm view delentia-guard version
npx -y delentia-guard@0.1.1 --help
```

## ขั้นที่ 2: delentia-mcp 2.1.2

```bash
cd C:/Users/whale/Delentia/delentia-mcp
npm test
npm pack --dry-run
npm publish
```

`npm test` ต้องผ่านทั้งหมด (8 ข้อ). `npm pack --dry-run` ควรได้ 9 ไฟล์ ~80 kB. ตรวจผล:

```bash
npm view delentia-mcp version
npx -y delentia-mcp --version
```

## ขั้นที่ 3: merge PR #8

เมื่อ npm ทั้งสองตัวขึ้นแล้ว บอกผม (หรือกดเอง): `gh pr merge 8 -R delentia-labs/delentia-mcp --merge`.
จากนั้นดูว่างาน registry สำเร็จ:

```bash
gh run list -R delentia-labs/delentia-mcp --workflow "Publish to MCP Registry" --limit 1
```
ต้องเป็น `completed success`. ถ้าล้ม ส่งข้อความ error มาให้ผม. สถานะใน registry ตรวจได้ที่ https://registry.modelcontextprotocol.io (ค้น `io.github.delentia-labs/delentia-mcp`).

## ถ้าพลาด

- publish ผิดรุ่น: อย่าใช้ `npm unpublish` (ผิดกฎ zero-delete และ npm จำกัด). ออกรุ่นถัดไป (2.1.3) แทน และใช้ `npm deprecate delentia-mcp@2.1.2 "ใช้ 2.1.3"` ถ้าจำเป็น.
- `npm publish` ตอบ 403 "you must verify email" หรือ "OTP": ยืนยันอีเมล/ใส่ `--otp`.
- ถ้า `npx` ยังได้รุ่นเก่า: แคชของ npx ลอง `npx -y delentia-mcp@2.1.2 --version`.

## สิ่งที่ยังต้องทำหลังจากนี้ (ไม่เร่งด่วน)

- Worker ยังรายงาน `serverInfo.version` เป็น 2.1.0 (ต้อง redeploy Worker ซึ่งผมต้องถามคุณก่อนทุกครั้ง).
- วางข้อความใหม่ที่หน้า Smithery และตรวจ MCPize: ดู `MCP_LISTINGS_TH.md`.
