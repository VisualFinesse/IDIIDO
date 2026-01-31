# IDOIIDO

![Anthropic Claude](https://img.shields.io/badge/Anthropic-Claude-2d5bec)
![OpenRouter](https://img.shields.io/badge/OpenRouter-v1.0-ff6b35)
![Codex](https://img.shields.io/badge/Codex-v1.1-9649ff)
![Python Version](https://img.shields.io/badge/python-3.8%2B-blue)

Just a crazy script for AI task execution - auto-context management - that automates AI models to complete TODO.md files... overnight.

> [!WARNING]
> This will kill a whole bunch of trees...

Works with `claude code` subscription or `codex` subscription

== Or any API key

== Or a list of openrouter models to cycle.

- Executes tasks from `TODO.md` files with AI agents
- Automatic model switching when token limits are reached
- Definition-of-Done (DoD) validation with tests and checks
- Supports both interactive and CI pipeline modes

## Installation

```bash
git clone https://github.com/visualfinesse/idoiido.git
cd idoiido
pip install -r .claude/requirements.txt
```

1. Generate project codemap:

```bash
python .claude/scripts/codemap.py
```

1. Create your `TODO.md` file with your list of demands.

## // Just Run it //

`python .claude/scripts/todo_executor.py`
_you know you want to_

### FLAGS

| Option              | Description                                                 |
| ------------------- | ----------------------------------------------------------- |
| `--todo-file FILE`  | In case the script can't find your TODO.md automatically... |
| `--agent-select`    | `{claude,codex,router}` default: claude                     |
| `--skip-tests`      | Pure Anarchy                                                |
| `--agent-timeout N` | Timeout in seconds (default: 600)                           |
| `--max-tasks N`     | You're lame if you use this.                                |
| `--debug`           | Enable debug listener (port 5678)                           |

### Environment Variables

```bash
# Fallback order when primary agent fails
AGENT_FALLBACK_ORDER="router | codex | claude"

# OpenRouter credentials
OPENROUTER_API_KEY="your-api-key"

# Enable streaming output
LLM_STREAM="1"


███████╗ ██████╗ ███████╗████████╗███████╗██████╗
██╔════╝██╔═══██╗██╔════╝╚══██╔══╝██╔════╝██╔══██╗
█████╗  ██║   ██║███████╗   ██║   █████╗  ██████╔╝
██╔══╝  ██║   ██║╚════██║   ██║   ██╔══╝  ██╔══██╗
██║     ╚██████╔╝███████║   ██║   ███████╗██║  ██║
╚═╝      ╚═════╝ ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝
```

&copy; 2026 IDOIIDO Project | FOSTER | [Report Issues](https://github.com/visualfinesse/idoiido/issues)
