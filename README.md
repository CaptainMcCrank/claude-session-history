# Claude Session History

A Python script to summarize and view Claude Code session history. Pure stdlib - no external dependencies.

## Installation

```bash
# Clone or copy to your preferred location
cp claude_session_summary.py ~/.local/bin/

# Make executable
chmod +x claude_session_summary.py

# Or run directly with Python
python3 claude_session_summary.py
```

Requires Python 3.10+.

## Usage

### List All Sessions

```bash
# Default markdown output
python3 claude_session_summary.py

# JSON output
python3 claude_session_summary.py --output json

# Plain text output
python3 claude_session_summary.py --output text

# Save to file
python3 claude_session_summary.py --save ~/session_report.md
```

### View a Specific Session

```bash
# View by session ID (partial match supported)
python3 claude_session_summary.py --view 49f2e931

# Limit number of messages displayed
python3 claude_session_summary.py --view 49f2e931 --max-messages 20

# Save session transcript to file
python3 claude_session_summary.py --view 49f2e931 --save transcript.md
```

### Options

| Option | Short | Description |
|--------|-------|-------------|
| `--output` | `-o` | Output format: `md`, `json`, or `text` (default: `md`) |
| `--save` | `-s` | Save output to file instead of stdout |
| `--view` | `-v` | View a specific session's conversation |
| `--max-messages` | `-m` | Limit messages when viewing (0 = unlimited) |
| `--projects-dir` | `-p` | Custom projects directory (default: `~/.claude/projects`) |

## How It Works

Claude Code stores session data in `~/.claude/projects/`:

```
~/.claude/projects/
├── -home-user-project1/
│   ├── sessions-index.json      # Session metadata & summaries
│   ├── <session-id>.jsonl       # Full conversation transcript
│   └── ...
└── -home-user-project2/
    └── ...
```

The script:
1. Reads `sessions-index.json` files for pre-generated summaries
2. Detects orphan `.jsonl` files not in any index
3. Groups sessions by date
4. Formats output in your preferred format

Session summaries are generated automatically by Claude Code - no LLM calls needed.

## Example Output

```
# Claude Code Session History

**Total Sessions:** 25
**Total Messages:** 405

---

## January 24, 2026 (Saturday)

| Project | Summary | Messages |
|---------|---------|----------|
| `~/Development/Info_Gyms` | **Backend API implementation** (21:42) | 81 |
| `~/Development/Info_Gyms` | **Debugging Vite dev server** (21:00) | 22 |
```

## License

MIT
