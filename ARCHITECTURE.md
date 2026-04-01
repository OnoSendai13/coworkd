# Architecture Hermes — Configuration 2026

> **Derniere mise a jour:** Avril 2026  
> **Environnement:** WSL2 Ubuntu (Windows)  
> **Status:** Operationnel

---

## Vue d'Ensemble

Système multi-agent sur WSL2 Ubuntu orchestr par Hermes, avec collaboration Claude Code, automatisation n8n, et services containerises (Docker).

```
Internet
    │
    ├─ Discord (messaging utilisateur)
    ├─ Mailo (email)
    └─ Google Calendar (agenda)
            │
    ┌───────┴───────────────────────────────────────────────┐
    │                    WSL2 Ubuntu                         │
    │                                                     │
    │  ┌──────────┐     ┌─────────────┐     ┌────────────┐ │
    │  │  Hermes  │────>│  Coworkd    │────>│ Claude     │ │
    │  │ Gateway  │<────│  Daemon     │<────│ Code CLI   │ │
    │  └──────────┘     └─────────────┘     └────────────┘ │
    │       │                   │                    │      │
    │       │            ┌──────┴──────┐             │      │
    │       │            │   Redis     │             │      │
    │       │            │  (Valkey)   │             │      │
    │       │            └─────────────┘             │      │
    │       │                                        │      │
    │       └──────────┬─────────────────────────────┘      │
    │                  │                                     │
    │  ┌───────────────┼───────────────────────────────┐    │
    │  │               │         Plugins               │    │
    │  │               ├─ MolmoAgent (web)            │    │
    │  │               ├─ TaskOrchestrator            │    │
    │  │               ├─ ProcessMonitor              │    │
    │  │               ├─ FileWatcher                 │    │
    │  │               └─ ...                         │    │
    │  └───────────────────────────────────────────────┘    │
    │                                                         │
    └─────────────────────────────────────────────────────────┘
            │
    ┌───────┴───────────────────────────────────────────────┐
    │              Docker Desktop (Windows)                   │
    │  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────────┐ │
    │  │  n8n    │ │ SearXNG  │ │OpenWebUI│ │ TREK        │ │
    │  │ :5678   │ │ :8888   │ │ :3000   │ │ :6913       │ │
    │  └─────────┘ └─────────┘ └─────────┘ └─────────────┘ │
    │  ┌─────────┐                                         │
    │  │ Redis   │                                         │
    │  │ :6379   │                                         │
    │  └─────────┘                                         │
    └───────────────────────────────────────────────────────┘
```

---

## Composants Principaux

### 1. Hermes Agent

Agent AI centralisant messaging et orchestration.

| Propriete | Valeur |
|-----------|--------|
| Type | Messaging gateway + AI agent |
| Protocol | REST API (gateway) + Webhook |
| Interfaces | Discord, terminal, API |
| Modele | minimax/minimax-m2.7 (OpenRouter) |
| Outils | 60+ skills charges dynamiquement |

**Fichiers cles:**
- `~/.hermes/config.yaml` — configuration
- `~/.hermes/hermes-agent/` — code agent
- `~/.hermes/skills/` — skills disponibles
- `~/.hermes/cron/` — jobs cron

**Fonctions:**
- Reception des commandes utilisateur (Discord)
- Delegation aux tools/skills
- Orchestration Coworkd pour taches complexes
- Acces Recherche Academique (Consensus MCP)
- Gestion email (himalaya CLI)

---

### 2. Coworkd Daemon

Daemon Python asyncio servant de glue entre Hermes et Claude Code.

| Propriete | Valeur |
|-----------|--------|
| Type | Background service (asyncio) |
| Langage | Python 3 |
| Lancement | `python ~/.cowork/coworkd.py` (systemd ou manuel) |
| Communication | Redis pub/sub + fichier context.json |

**Plugins disponbles:**

| Plugin | Role | Status |
|--------|------|--------|
| `claude_code` | Bridge Claude Code CLI | Actif |
| `task_orchestrator` | Automation Hermes ↔ Claude Code | Actif |
| `molmo_agent` | Agent web multimodal | Actif |
| `process_monitor` | Surveillance systeme (CPU, RAM, GPU) | Actif |
| `file_watcher` | Surveillance fichiers (inotify) | Actif |
| `pcloud_sync` | Synchronisation pCloud | Inactif |
| `screenshot` | Capture ecran | Inactif |
| `browser_control` | Playwright legacy | Inactif |

**Contexte partage:**
- Fichier `~/.cowork/workspace/context.json`
- Poll interval: 2 secondes
- Channels Redis: `cowork:events`, `cowork:task_completed`

**Protocole Hermes ↔ Coworkd:**
```
1. Hermes (Discord) → cowork_run_code_task(task="code X")
   → ecrit context.json: goal_status=pending, goal_source=hermes

2. task_orchestrator (poll 2s) detecte pending
   → execute Claude Code --print
   → goal_status=done, goal_result={...}
   → publish Redis: cowork:task_completed

3. Hermes poll cowork_context_read
   → goal_status=done → lit goal_result
   → repond a l'utilisateur
```

---

### 3. Claude Code CLI

Interface CLI Anthropic pour codage autonomous.

| Propriete | Valeur |
|-----------|--------|
| Version | 2.1.89 |
| Installation | NVM (Node.js 22) |
| Auth | Compte Anthropic |
| Mode interactif | `claude` (shell) |
| Mode one-shot | `claude --print` |
| Mode stream | `claude --verbose --output-format stream-json` |

**OAuth MCP:**
- Consensus MCP (academique) — OAuth managed by Claude Code
- Tokens stockes dans `~/.claude/.credentials.json`
- Refresh automatique en mode interactif

---

### 4. Services Docker

Ensemble de services containerises via Docker Desktop (Windows).

| Service | Port | Role | Status |
|---------|------|------|--------|
| `n8n` | 5678 | Automation workflows | Running |
| `searxng` | 8888 | Metasearch engine | Running |
| `open-webui` | 3000 | Web UI for LLM | Running (healthy) |
| `trek` | 6913 | ? (application specifique) | Running |
| `redis` | 6379 | Message bus + cache | Running |

**n8n Workflows notables:**
- Publication automatique LinkedIn (ANLLF)
- Automationmail/calendar

---

### 5. Acces Recherche Academique

**Consensus MCP (recommand):**

| Propriete | Valeur |
|-----------|--------|
| Endpoint | `https://mcp.consensus.app/mcp` |
| Auth | OAuth (Claude Code managed) |
| Methode | Direct HTTP calls avec tokens Claude Code |
| Plan | Pro (20 resultats/recherche) |
| Limite | 1000 recherches/mois |

**Implementation:**
- Script: `~/.hermes/skills/consensus-direct/scripts/consensus.py`
- Lecture tokens: `~/.claude/.credentials.json`
- Refresh on-demand via Claude Code si token expire
- Aucun cron — mode reactif

**Limites:**
- Token access expire ~20 min
- Refresh token via Claude Code interactif
- Pas de refresh automatique (conso Pro a controler)

---

### 6. Email — Himalaya CLI

Client email en ligne de commande pour Mailo.

| Propriete | Valeur |
|-----------|--------|
| Provider | Mailo |
| Adresse | laurent.suchet@lilo.org |
| CLI | `himalaya` |
| Alias send | `himalaya-send` (bash function) |

**Commandes:**
```bash
himalaya list                    # Liste dossiers
himalaya search "query"          # Recherche
himalaya-send "dest@ex.com" "Sujet" "Corps"  # Envoi
```

**Note:** Dossier "sent" utilise "Messages envoyes" (minuscule) = folder "sent"

---

### 7. Messaging — Discord Bot

Bot Hermes connecte au serveur Discord.

| Propriete | Valeur |
|-----------|--------|
| Client ID | 1484126437190402088 |
| OAuth URL | https://discord.com/api/oauth2/authorize?... |
| Permissions | 8 (Administrator) |
| Requirement | `DISCORD_REQUIRE_MENTION=false` |

**Configuration:**
- Bot public (Aucun serveur = seuil)
- Responds tous les messages du canal (pas de @mention)
- Variable env: `DISCORD_REQUIRE_MENTION=false`

---

### 8. Services Web

| Service | URL | Role |
|---------|-----|------|
| SearXNG | http://127.0.0.1:8888 | Recherche web privee |
| OpenWebUI | http://localhost:3000 | Web UI for LLM |
| TREK | http://localhost:6913 | Application specifique |
| n8n | http://localhost:5678 | Automation |

---

## Arborescence

```
~/
├── .hermes/                          # Hermes Agent
│   ├── config.yaml                   # Config principale
│   ├── hermes-agent/                 # Code agent
│   ├── skills/                       # 60+ skills
│   │   ├── consensus-direct/        # Recherche Consensus
│   │   ├── notebooklm/              # NotebookLM CLI
│   │   └── ...
│   ├── cron/                         # Jobs cron
│   └── *.env                         # Environment (tokens)
│
├── .cowork/                         # Cowork Daemon
│   ├── coworkd.py                   # Daemon entry point
│   ├── config.yaml                  # Config daemon
│   ├── plugins/                     # Plugin packages
│   │   ├── base.py                 # ABC CoworkPlugin
│   │   ├── claude_code.py          # Claude Code bridge
│   │   ├── molmo_agent.py          # Web agent
│   │   ├── task_orchestrator.py   # Automation
│   │   └── ...
│   ├── workspace/
│   │   └── context.json            # Contexte partage
│   └── state/
│       └── context.json            # Snapshots contexte
│
├── .claude/                        # Claude Code
│   ├── .credentials.json           # OAuth tokens (Consensus)
│   ├── mcp-configs/               # MCP server configs
│   ├── sessions/                  # Sessions Claude Code
│   └── plugins/                   # Plugins Claude Code
│
├── .himalaya_aliases.sh           # Alias email
│
└── Docker (Windows Desktop)
    ├── n8n                       # Automation (:5678)
    ├── searxng                   # Metasearch (:8888)
    ├── open-webui                # Web LLM UI (:3000)
    ├── trek                      # App (:6913)
    └── redis                     # Message bus (:6379)
```

---

## Flux Donnees Typiques

### Recherche Academique (Discord)
```
Utilisateur (Discord)
    │
    ▼
Hermes Gateway
    │
    ▼
consensus.py (script)
    │ lit ~/.claude/.credentials.json
    ▼
POST https://mcp.consensus.app/mcp (Bearer token)
    │
    ▼
Resultat JSON → Hermes → Discord
```

### Tache de Codage (Discord)
```
Utilisateur (Discord)
    │
    ▼
Hermes Gateway
    │
    ▼
cowork_run_code_task (tool)
    │ ecrit context.json (goal_status=pending)
    ▼
task_orchestrator (poll 2s)
    │
    ▼
Claude Code --print --output-format=stream-json
    │
    ▼
context.json mis a jour (goal_status=done)
    │
    ▼
Hermes lit resultat → Discord
```

### Recherche Web (Discord)
```
Utilisateur (Discord)
    │
    ▼
Hermes Gateway
    │
    ▼
searxng_search (MCP tool)
    │
    ▼
SearXNG local (:8888)
    │
    ▼
Resultats JSON → Hermes → Discord
```

---

## Sécurité

| Point | Status | Notes |
|-------|--------|-------|
| Credentials | Locaux uniquement | `~/.claude/.credentials.json` non commit |
| Bot Discord | Public | 1 serveur, seuil non atteint |
| Docker | Firewall Windows | Ports non exposes externement |
| WSL2 | Bridge reseau | Acces via localhost |
| Tokens OAuth | Claude Code managed | Refresh manuel |

**Aucun credential sensibles dans ce document.**

---

## Maintenance

### Redemarrer Hermes Gateway
```bash
~/.hermes/bin/hermes restart
```

### Redemarrer Coworkd
```bash
# Manuel
pkill -f coworkd.py && python ~/.cowork/coworkd.py &

# Systemd
systemctl --user restart cowork
```

###Verifier services Docker
```bash
docker ps
```

###Verifier cron jobs
```bash
cronjob --list
```

###Logs
```bash
# Hermes gateway
tail -f ~/.hermes/gateway.log

# Coworkd
tail -f ~/.cowork/coworkd.log
```

---

## Limitations Connues

1. **Consensus OAuth:** Token expire ~20 min, refresh on-demand via Claude Code uniquement
2. **Claude Code mode -p:** MCP tools ne marchent pas en mode non-interactif
3. **Docker WSL2:** Services dependent de Docker Desktop Windows
4. **pCloud sync:** Plugin inactif (token non configure)

---

*Document genere automatiquement — Avril 2026*
