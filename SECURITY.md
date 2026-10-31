# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 2.4.x (alpha, experimental) | :white_check_mark: |
| older | no |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities **privately through GitHub**: open [**Report a vulnerability**](https://github.com/delentia-labs/Delentia-OS/security/advisories/new) (the Security tab of this repository, then "Report a vulnerability"). Only the maintainers can see it, and it can become a coordinated advisory when a fix is out.

There is **no monitored security mailbox yet**, so please do not rely on email. If you cannot use GitHub, open a public issue that says only "I have a security report, please tell me how to send it" and put no details in it.

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

This project has one maintainer. We aim to acknowledge a report within **7 days** and to fix critical issues within **30 days**; please treat both as goals, not guarantees.

## Security Scanning

This repository runs automated security scans on every pull request and daily via GitHub Actions:
- **gitleaks** — detect secrets in git history
- **bandit** — static analysis for Python security issues
- **pip-audit** — CVE scanning for Python dependencies

## Responsible Disclosure

Once a fix is released, we will credit the reporter (unless they prefer anonymity) in the CHANGELOG.

## Known Security Measures

- All core modules are scanned for OWASP Top 10 patterns before public release
- No hardcoded credentials, API keys, or internal server URLs are permitted in any public file
- All contributions are scanned via CI before merge
