# Security Policy

## Supported Versions

Security fixes are accepted for the latest released version.

## Reporting A Vulnerability

If you find a vulnerability, report it through GitHub Security Advisories when available. If advisories are not enabled, open an issue with a minimal description and avoid posting sensitive proof-of-concept details publicly.

Do not include private cookies, authentication headers, unpublished article text, or full cached source pages in reports.

## Scope

Relevant issues include:

- Unsafe cache deletion or path handling.
- Accidental leakage of local files, credentials, or environment data.
- Incorrect handling of untrusted HTML that could write outside the configured cache/output paths.
- Output behavior that republishes excessive copyrighted article text.

Out of scope:

- Third-party website downtime or markup changes.
- Ordinary news coverage mistakes or missed articles without a security impact.
- Rate limiting or blocking by source websites.
