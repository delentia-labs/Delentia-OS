import assert from "node:assert/strict";
import { toBase64Url, fromBase64Url, creationOptions, requestOptions, serializeCredential, placeProblem, ceremonyMessage } from "./webauthn.ts";

const bytes = new Uint8Array([0, 1, 2, 250, 251, 252, 253, 254, 255]);
assert.equal(toBase64Url(bytes), "AAEC-vv8_f7_");                                  // url alphabet, no padding
assert.deepEqual([...fromBase64Url(toBase64Url(bytes))], [...bytes]);
for (let n = 0; n < 40; n++) {                                                      // every length, so each padding case
  const b = new Uint8Array(n).map((_, i) => (i * 37 + n) & 255);
  assert.deepEqual([...fromBase64Url(toBase64Url(b))], [...b]);
}

const creation = creationOptions({ challenge: toBase64Url(bytes), user: { id: toBase64Url(bytes), name: "x", displayName: "x" }, rp: { id: "localhost" } });
assert.deepEqual([...creation.challenge], [...bytes]);
assert.deepEqual([...creation.user.id], [...bytes]);
assert.equal(creation.rp.id, "localhost");

const request = requestOptions({ challenge: toBase64Url(bytes), rpId: "localhost", allowCredentials: [{ type: "public-key", id: toBase64Url(bytes) }] });
assert.deepEqual([...request.allowCredentials[0].id], [...bytes]);
assert.equal(requestOptions({ challenge: toBase64Url(bytes) }).allowCredentials.length, 0);

const out = serializeCredential({ id: "abc", rawId: bytes.buffer, type: "public-key", response: { clientDataJSON: bytes.buffer, userHandle: null } });
assert.equal(out.rawId, toBase64Url(bytes));
assert.equal(out.response.userHandle, null);
assert.equal(out.response.clientDataJSON, toBase64Url(bytes));

assert.equal(placeProblem({ protocol: "http:", hostname: "localhost", port: "3010" }, true), null);
assert.match(placeProblem({ protocol: "http:", hostname: "127.0.0.1", port: "3010" }, true), /http:\/\/localhost:3010/);
assert.match(placeProblem({ protocol: "http:", hostname: "127.0.0.1", port: "3010" }, true, "th"), /localhost:3010/);
assert.match(placeProblem({ protocol: "https:", hostname: "desk.example.com" }, true), /DELENTIA_PASSKEY_RP_ID/);
assert.match(placeProblem({ protocol: "http:", hostname: "localhost" }, false), /WebAuthn/);

const cancelled = new Error("x");
cancelled.name = "NotAllowedError";
assert.match(ceremonyMessage(cancelled), /Nothing was recorded/);
assert.match(ceremonyMessage(cancelled, "th"), /ไม่มีอะไรถูกบันทึก/);
console.log("webauthn: all checks passed");
