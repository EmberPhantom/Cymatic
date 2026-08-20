# Security Policy

## Reporting a Vulnerability

Do not open a public GitHub issue for a suspected vulnerability. Report it privately to the CYMATIC maintainers with:

- affected component and version/commit;
- reproduction steps or proof of concept;
- impact and suspected attack prerequisites;
- any suggested mitigation.

Until a private reporting channel is configured, use the repository owner’s private GitHub security advisory workflow.

## Sensitive Data Rules

- Never commit API keys, JWT secrets, database passwords, MinIO credentials, certificates, or private tenant data.
- Free LLM providers may only receive internal development, non-sensitive demo, or non-tenant test data.
- Production secrets must be supplied through deployment secret management, not repository files.
- Report suspected credential exposure immediately and rotate the credential before investigating further.

## Security Expectations

Changes affecting authentication, authorization, tenant isolation, provider routing, credits, storage, or streaming signaling require focused security tests and documentation of the trust boundary.
