// Run with: npm run test:http  (node 22.6+, no test framework)
import assert from "node:assert/strict";
import { httpMessage } from "./http-message.ts";

assert.match(httpMessage(401, "missing token", false), /Settings/);
assert.match(httpMessage(401, "missing token", true), /หน้าตั้งค่า/);
assert.match(httpMessage(403, "owner only", true), /ไม่ได้รับอนุญาต/);
assert.match(httpMessage(404, "no such approval", false), /already used/);
assert.match(httpMessage(409, "x", true), /โหลดหน้าใหม่/);
assert.match(httpMessage(500, "boom", false), /server's log/);
assert.match(httpMessage(502, "bad gateway", true), /ขัดข้อง/);
assert.equal(httpMessage(400, "decision must be APPROVED or REJECTED", false), "400: decision must be APPROVED or REJECTED");
assert.ok(httpMessage(403, "owner only", false).includes("owner only"), "the server's own words stay for whoever debugs");
console.log("http-message: all checks passed");
