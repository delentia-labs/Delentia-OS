# RCT Policy Gate action

This action uses the **Node 24** GitHub Actions runtime. Use a runner that supports Node 24 actions. Local packaged-process validation in the readiness round used Node 24.19.0; GitHub-hosted execution remains a separate validation step.

Build from the frozen lockfile with `npm ci`, then `npm run build` and `npm test -- --runInBand`. TypeScript preserves ES module imports for ncc to resolve the import-only `@actions/core` package. Commit both `dist/index.js` and the generated `dist/licenses.txt`; `tsc --noEmit` avoids leaving an unbundled entry point behind.

Configure a reachable `rct_api_url` and an API token through runner secrets. The default loopback URL requires an API on that runner; it is not a hosted Delentia service. The action calls the legacy compile/evaluate endpoints, not the declared-plan agent workflow. The API operator controls whether compilation may call a model; use its regex-only configuration when paid calls are not authorized.

Policy rejection (unless explicitly disabled by `fail_on_reject=false`), a score below the floor, and non-finite/out-of-range score or threshold values fail the step. Human approval requirements are currently warnings: this action does not collect signatures or authorize an agent effect. Branch protection must require the check before claiming a failed step blocks merging.

API redirects are refused (`maxRedirects: 0`); use the canonical API URL. This avoids forwarding bearer credentials through redirect handling. Production npm audit in this round still reports two high findings through `follow-redirects`, with no automatic fix available. The call-site mitigation and redirect-destination test do not establish that the library or other consumers are patched. Update reviewed dependencies and rebuild when a suitable patched release is available.
