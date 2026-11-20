# AI Agent Security Policy — Tier-2 Coding Agents

**Document ID:** OLY-SEC-POL-014 · **Version:** 2.3 · **Owner:** AppSec Architecture · **Effective:** 2026-09-01

## 1. Scope and Classification

This policy governs Tier-2 AI coding agents: any LLM-based system that can propose or apply changes to application source code, pipelines, or infrastructure-as-code in Olympus-controlled environments. Tier-1 agents (documentation summarization, test generation without write access) are out of scope.

## 2. Tool-Level Authorization

All tools exposed to a Tier-2 agent **must** go through the gateway registry. Each tool declaration requires:

- **Capability grant**: the minimum OAuth/API scope needed, per tool, never account-level credentials.
- **Explicit allowlist**: tools not on the allowlist are unreachable; a denied call returns `AUTHZ_DENIED` and must be logged.
- **Ephemeral credentials**: maximum TTL 900 seconds; renewal requires a new capability grant.

Direct shell access is **prohibited**. Shell-equivalent tools (file write outside the repo sandbox, network calls beyond the package registry allowlist) are Tier-3 and require two-person approval.

## 3. Least Privilege Enforcement Points

Enforcement happens at three layers, in order:

1. **Gateway (pre-execution)**: schema-validate every tool call against the registry entry; reject unknown parameters.
2. **Sandbox (during execution)**: filesystem restricted to the workspace; outbound network restricted to allowlisted domains.
3. **Post-run (verification)**: diff review plus secret scan before any merge. An agent change that introduces a new dependency must include an SCA report with a maximum CVSS of 7.0 for known vulnerabilities.

## 4. What To Do When Teams Move Faster Than Policy

Exception requests follow the fast lane:

- **Duration**: maximum 14 days, auto-expiring, no renewal without review.
- **Approval**: the team's engineering manager plus one AppSec reviewer (either may block).
- **Compensating controls**: agent output quarantined to a fork; no direct writes to protected branches; full prompt-and-response transcript retained for 30 days.

An unregistered exception is treated as a **policy violation**, not a technicality, and is escalated to the CISO office.

## 5. Audit and Review Cadence

- All `AUTHZ_DENIED` events are reviewed weekly by AppSec; three denials for the same tool in one week trigger a registry review.
- The gateway registry itself is version-controlled; changes require a pull request with AppSec approval.
- Quarterly red-team exercise must include at least one prompt-injection attempt against a Tier-2 agent.
