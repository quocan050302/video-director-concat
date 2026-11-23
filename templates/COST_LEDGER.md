# Cost, License & Local-First Audit Ledger

Zero paid APIs by default. Track actual direct cost separately from user Antigravity token quota, hardware electricity/SSD wear, and media licenses.

| Component | Category | License (Code / Weights / Media) | Download Size | Installed? | Verified? | Cloud Upload? | Direct Monetary Cost | Owner Approval | Reason Chosen |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Concat (native MCP editor) | Video Engine | `AGPL-3.0-or-later` (bundled FFmpeg LGPL; OS codecs) | `~85–118 MB` installer | `<YES/NO>` | `<YES/NO>` | `NO (local-first)` | `$0` (free software; commercial license only for closed-source redistribution/modified hosted service) | `<PENDING/APPROVED>` | Sole native project & MP4 export engine |
| Antigravity / Agent Runtime | Orchestrator | User account plan | N/A | `YES` | `YES` | Prompts/metadata only (never upload private source video) | Depends on user quota/subscription | `ACTIVE_SESSION` | Creative direction & QA coordination |
| FFprobe / FFmpeg (local CLI) | Read-Only Probe & QA | LGPL/GPL local binary | Pre-installed | `<YES/NO>` | `<YES/NO>` | `NO` | `$0` | `N/A` | Read-only probing, contact sheets, post-export QA only (NEVER final renderer) |
| Local TTS (Optional) | Voice | Audit code, weights & voice preset separately | `~78–350 MB` (Kokoro) / `~1.1 GB` (Chatterbox) | `NO (on-demand)` | `PENDING` | Model download once if approved; inference local | `$0` | `REQUIRED_BEFORE_DOWNLOAD` | Only install if run requires VO |

## Paid API Gate
- Paid external APIs used in this run: **NONE**.
- If any paid stock/TTS/STT/cloud service is proposed -> stop with `STOP_FOR_COST_APPROVAL` and provide a zero-cost alternative.
