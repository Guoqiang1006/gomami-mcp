# Security

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting for this repository. Do not open a public issue, and never include an API token, password or server credential in a report.

## What this project protects against

- **Accidental actions.** Access is read-only by default, and each state-changing tool needs exact confirmation text.
- **Actions on chosen servers.** `GOMAMI_MCP_PROTECTED_SERVERS` refuses state-changing tools for the listed servers, whatever the model sends.
- **Secrets entering the chat.** VNC credentials are redacted, and reset passwords are written to a local file with mode `600`.
- **Token leaks.** The token is only sent to `GOMAMI_API_BASE` (by default `https://cp.gomami.io/api`), which must use HTTPS. An invalid value refuses every request rather than falling back to GoMami. Each panel reads its own token file by default, redirects are not followed, and the token is never included in tool output.

## What it does not protect against

- **A model that chooses to act.** A model can fill in confirmation text by itself. Use the access tier, the protected list and your MCP client's approval prompts as the real controls.
- **Prompt injection.** Text returned by the API, such as a server name, reaches the model. Keep the access tier as low as your task allows.
- **A compromised local account.** Anyone who can read your user's files can read the token file and saved passwords.

VirtFusion API tokens, including GoMami's, have full account access. Revoke a token in your host's control panel if you think it has been exposed.
