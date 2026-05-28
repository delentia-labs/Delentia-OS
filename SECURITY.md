# Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.x (alpha) | :white_check_mark: |

## Reporting a Vulnerability

**Do not open a public GitHub issue for security vulnerabilities.**

Please report security vulnerabilities via email to:
**security@delentia.com**

Include in your report:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (optional)

We will acknowledge your email within **48 hours** and aim to provide a fix within **14 days** for critical issues.

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
