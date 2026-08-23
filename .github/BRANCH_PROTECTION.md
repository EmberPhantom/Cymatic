# GitHub Repository Settings

Configure these settings in the GitHub repository because they cannot be enforced solely by tracked files.

## Main branch

- Require pull requests before merging.
- Require at least one approving review and require CODEOWNERS review for owned paths.
- Dismiss stale approvals when new commits are pushed.
- Require all conversations to be resolved.
- Require these status checks: `Frontend Lint & Type Check`, `Backend API Lint & Test`, `Worker Lint & Test`, `LLM Router Lint & Test`, `Schema Validation`, `Docker Build Test`, `Docker Compose Integration Test`, and `Security Scan`.
- Require branches to be up to date before merging.
- Disable force-pushes and branch deletion.

## Security

- Enable Dependabot security updates and grouped version updates where appropriate.
- Enable secret scanning and push protection.
- Review uploaded SARIF results from Trivy and any future CodeQL workflow.
- Store provider credentials only in GitHub Actions secrets or environment-level secrets.

## Environments

- Keep production deployment approvals separate from pull-request validation.
- Restrict production secrets to protected branches and approved environments.
