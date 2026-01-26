#!/usr/bin/env python3
"""
Claude Code Session History Summarizer

Parses Claude Code session history and generates dated summaries.
Pure stdlib - no external dependencies.

Usage:
    python claude_session_summary.py                    # Default markdown output
    python claude_session_summary.py --output md       # Output as markdown
    python claude_session_summary.py --output json     # Output as JSON
    python claude_session_summary.py --output text     # Output as plain text
    python claude_session_summary.py --save report.md  # Save to file
    python claude_session_summary.py --view <id>       # View a session's conversation
"""

import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict
from typing import Optional
import argparse


def get_claude_projects_dir() -> Path:
    """Get the Claude Code projects directory."""
    return Path.home() / ".claude" / "projects"


def find_session_indexes(projects_dir: Path) -> list[Path]:
    """Find all sessions-index.json files."""
    return list(projects_dir.glob("*/sessions-index.json"))


def parse_session_index(index_path: Path) -> list[dict]:
    """Parse a sessions-index.json file and return session metadata."""
    try:
        with open(index_path, "r") as f:
            data = json.load(f)

        sessions = []
        for entry in data.get("entries", []):
            # Parse the created timestamp
            created_str = entry.get("created", "")
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                except ValueError:
                    created = None
            else:
                created = None

            sessions.append({
                "session_id": entry.get("sessionId", ""),
                "summary": entry.get("summary", "No summary"),
                "first_prompt": entry.get("firstPrompt", "")[:100],
                "message_count": entry.get("messageCount", 0),
                "created": created,
                "modified": entry.get("modified", ""),
                "project_path": entry.get("projectPath", data.get("originalPath", "")),
                "git_branch": entry.get("gitBranch", ""),
                "full_path": entry.get("fullPath", ""),
            })

        return sessions
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Warning: Could not parse {index_path}: {e}")
        return []


def find_orphan_sessions(projects_dir: Path, indexed_sessions: set[str]) -> list[dict]:
    """Find session files not in any index (orphans)."""
    orphans = []

    for jsonl_file in projects_dir.glob("*/*.jsonl"):
        # Skip subagent files
        if "subagents" in str(jsonl_file) or jsonl_file.name.startswith("agent-"):
            continue

        session_id = jsonl_file.stem
        if session_id not in indexed_sessions:
            # Try to extract info from the file
            try:
                stat = jsonl_file.stat()
                created = datetime.fromtimestamp(stat.st_mtime)

                # Read first line to get initial prompt
                first_prompt = ""
                with open(jsonl_file, "r") as f:
                    for line in f:
                        try:
                            data = json.loads(line)
                            if "message" in data:
                                content = data["message"].get("content", "")
                                if isinstance(content, str):
                                    first_prompt = content[:100]
                                    break
                        except json.JSONDecodeError:
                            continue

                orphans.append({
                    "session_id": session_id,
                    "summary": f"Unindexed session: {first_prompt[:50]}..." if first_prompt else "Unindexed session",
                    "first_prompt": first_prompt,
                    "message_count": 0,
                    "created": created,
                    "project_path": str(jsonl_file.parent).replace(str(projects_dir) + "/", ""),
                    "full_path": str(jsonl_file),
                })
            except Exception as e:
                print(f"Warning: Could not process orphan {jsonl_file}: {e}")

    return orphans


def collect_all_sessions(projects_dir: Optional[Path] = None) -> list[dict]:
    """Collect all sessions from all project indexes."""
    if projects_dir is None:
        projects_dir = get_claude_projects_dir()

    all_sessions = []
    indexed_session_ids = set()

    # Get sessions from index files
    for index_path in find_session_indexes(projects_dir):
        sessions = parse_session_index(index_path)
        for session in sessions:
            indexed_session_ids.add(session["session_id"])
        all_sessions.extend(sessions)

    # Find orphan sessions
    orphans = find_orphan_sessions(projects_dir, indexed_session_ids)
    all_sessions.extend(orphans)

    return all_sessions


def normalize_datetime(dt: Optional[datetime]) -> Optional[datetime]:
    """Normalize datetime to naive UTC for comparison."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        # Convert to UTC and make naive
        from datetime import timezone
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def group_sessions_by_date(sessions: list[dict]) -> dict[str, list[dict]]:
    """Group sessions by date."""
    by_date = defaultdict(list)

    for session in sessions:
        if session["created"]:
            date_key = session["created"].strftime("%Y-%m-%d")
            by_date[date_key].append(session)
        else:
            by_date["Unknown"].append(session)

    # Sort sessions within each date by time (normalize for comparison)
    for date_key in by_date:
        by_date[date_key].sort(
            key=lambda s: normalize_datetime(s["created"]) or datetime.min
        )

    return dict(sorted(by_date.items()))


def decode_project_dir_name(encoded: str) -> str:
    """Decode an encoded project directory name back to a path."""
    # Claude encodes paths like /home/patrick/foo as -home-patrick-foo
    if not encoded.startswith("-"):
        return encoded

    # Split by hyphen and try to reconstruct
    parts = encoded[1:].split("-")
    # Try to find path separators - usually after 'home', 'username', etc.
    # Heuristic: look for common path components
    path_parts = []
    i = 0
    while i < len(parts):
        part = parts[i]
        # Check if this could be a compound name (has underscore or is a known dir)
        if i + 1 < len(parts):
            # Look ahead for underscored names (e.g., Info_Gyms -> Info-Gyms in encoding)
            combined = part + "_" + parts[i + 1]
            test_path = "/" + "/".join(path_parts + [combined])
            if Path(test_path).exists():
                path_parts.append(combined)
                i += 2
                continue
        path_parts.append(part)
        i += 1

    return "/" + "/".join(path_parts)


def format_project_path(path: str) -> str:
    """Format project path for display."""
    home = str(Path.home())

    # Handle encoded directory names (e.g., -home-patrick-Development-Info-Gyms)
    if path.startswith("-"):
        path = decode_project_dir_name(path)

    if path.startswith(home):
        return "~" + path[len(home):]
    return path


def generate_markdown_summary(sessions_by_date: dict[str, list[dict]]) -> str:
    """Generate a markdown summary of sessions."""
    lines = ["# Claude Code Session History\n"]

    total_sessions = sum(len(s) for s in sessions_by_date.values())
    total_messages = sum(
        session["message_count"]
        for sessions in sessions_by_date.values()
        for session in sessions
    )

    lines.append(f"**Total Sessions:** {total_sessions}  ")
    lines.append(f"**Total Messages:** {total_messages}\n")
    lines.append("---\n")

    for date_str, sessions in sessions_by_date.items():
        # Format date header
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%B %d, %Y (%A)")
        except ValueError:
            formatted_date = date_str

        lines.append(f"## {formatted_date}\n")
        lines.append("| Project | Summary | Messages |")
        lines.append("|---------|---------|----------|")

        for session in sessions:
            project = format_project_path(session["project_path"])
            summary = session["summary"].replace("|", "\\|")
            msg_count = session["message_count"]

            # Add time if available
            if session["created"]:
                time_str = session["created"].strftime("%H:%M")
                summary = f"**{summary}** ({time_str})"
            else:
                summary = f"**{summary}**"

            lines.append(f"| `{project}` | {summary} | {msg_count} |")

        lines.append("")

    return "\n".join(lines)


def generate_json_summary(sessions_by_date: dict[str, list[dict]]) -> str:
    """Generate a JSON summary of sessions."""
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_sessions": sum(len(s) for s in sessions_by_date.values()),
        "sessions_by_date": {}
    }

    for date_str, sessions in sessions_by_date.items():
        output["sessions_by_date"][date_str] = [
            {
                "project": format_project_path(s["project_path"]),
                "summary": s["summary"],
                "first_prompt": s["first_prompt"],
                "message_count": s["message_count"],
                "created": s["created"].isoformat() if s["created"] else None,
                "session_id": s["session_id"],
            }
            for s in sessions
        ]

    return json.dumps(output, indent=2)


def generate_text_summary(sessions_by_date: dict[str, list[dict]]) -> str:
    """Generate a plain text summary of sessions."""
    lines = ["CLAUDE CODE SESSION HISTORY", "=" * 40, ""]

    for date_str, sessions in sessions_by_date.items():
        try:
            date_obj = datetime.strptime(date_str, "%Y-%m-%d")
            formatted_date = date_obj.strftime("%B %d, %Y")
        except ValueError:
            formatted_date = date_str

        lines.append(f"\n{formatted_date}")
        lines.append("-" * len(formatted_date))

        for session in sessions:
            project = format_project_path(session["project_path"])
            summary = session["summary"]
            msg_count = session["message_count"]

            lines.append(f"  [{project}]")
            lines.append(f"    {summary}")
            if msg_count > 0:
                lines.append(f"    ({msg_count} messages)")
            lines.append("")

    return "\n".join(lines)


def find_session_file(session_id: str, projects_dir: Optional[Path] = None) -> Optional[Path]:
    """Find a session file by session ID (full or partial match)."""
    if projects_dir is None:
        projects_dir = get_claude_projects_dir()

    matches = []
    for jsonl_file in projects_dir.glob("*/*.jsonl"):
        if "subagents" in str(jsonl_file) or jsonl_file.name.startswith("agent-"):
            continue
        if session_id in jsonl_file.stem:
            matches.append(jsonl_file)

    if len(matches) == 1:
        return matches[0]
    elif len(matches) > 1:
        print(f"Multiple sessions match '{session_id}':")
        for m in matches:
            print(f"  {m.stem}")
        return None
    return None


def extract_message_content(content) -> str:
    """Extract readable text from message content (handles various formats)."""
    if isinstance(content, str):
        return content
    elif isinstance(content, list):
        # Content blocks (text, tool_use, tool_result, etc.)
        parts = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
                elif block.get("type") == "tool_use":
                    tool_name = block.get("name", "unknown")
                    tool_input = block.get("input", {})
                    # Summarize tool use
                    if tool_name == "Read":
                        parts.append(f"[Reading: {tool_input.get('file_path', '?')}]")
                    elif tool_name == "Edit":
                        parts.append(f"[Editing: {tool_input.get('file_path', '?')}]")
                    elif tool_name == "Write":
                        parts.append(f"[Writing: {tool_input.get('file_path', '?')}]")
                    elif tool_name == "Bash":
                        cmd = tool_input.get("command", "")[:80]
                        parts.append(f"[Running: {cmd}]")
                    elif tool_name == "Grep":
                        parts.append(f"[Searching: {tool_input.get('pattern', '?')}]")
                    elif tool_name == "Glob":
                        parts.append(f"[Finding: {tool_input.get('pattern', '?')}]")
                    else:
                        parts.append(f"[Tool: {tool_name}]")
                elif block.get("type") == "tool_result":
                    result = block.get("content", "")
                    if isinstance(result, str) and len(result) > 200:
                        result = result[:200] + "..."
                    parts.append(f"[Result: {result}]")
            elif isinstance(block, str):
                parts.append(block)
        return "\n".join(parts)
    return str(content)


def view_session(session_id: str, projects_dir: Optional[Path] = None, max_messages: int = 0) -> str:
    """View a session's conversation."""
    session_file = find_session_file(session_id, projects_dir)
    if not session_file:
        return f"Session not found: {session_id}"

    lines = []
    lines.append(f"# Session: {session_file.stem}")
    lines.append(f"**File:** `{session_file}`\n")
    lines.append("---\n")

    message_count = 0
    with open(session_file, "r") as f:
        for line in f:
            if max_messages > 0 and message_count >= max_messages:
                lines.append(f"\n... truncated (showing {max_messages} messages) ...")
                break

            try:
                data = json.loads(line)
                if "message" not in data:
                    continue

                msg = data["message"]
                role = msg.get("role", "unknown")
                content = extract_message_content(msg.get("content", ""))

                if not content.strip():
                    continue

                message_count += 1

                # Format based on role
                if role == "user":
                    lines.append(f"## User\n")
                    lines.append(content)
                    lines.append("")
                elif role == "assistant":
                    lines.append(f"## Assistant\n")
                    # Truncate very long responses
                    if len(content) > 2000:
                        content = content[:2000] + "\n\n... (truncated)"
                    lines.append(content)
                    lines.append("")

            except json.JSONDecodeError:
                continue

    if message_count == 0:
        lines.append("No messages found in session.")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Summarize Claude Code session history",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                          # List all sessions (markdown)
  %(prog)s --output json            # List all sessions (JSON)
  %(prog)s --output text            # List all sessions (plain text)
  %(prog)s --save report.md         # Save summary to file
  %(prog)s --view 49f2e931          # View session by ID (partial match OK)
  %(prog)s --view 49f2e931 -m 10    # View first 10 messages only
        """
    )
    parser.add_argument(
        "--output", "-o",
        choices=["md", "markdown", "json", "text"],
        default="md",
        help="Output format (default: md)"
    )
    parser.add_argument(
        "--projects-dir", "-p",
        type=Path,
        default=None,
        help="Path to Claude projects directory (default: ~/.claude/projects)"
    )
    parser.add_argument(
        "--save", "-s",
        type=Path,
        default=None,
        help="Save output to file instead of stdout"
    )
    parser.add_argument(
        "--view", "-v",
        type=str,
        default=None,
        metavar="SESSION_ID",
        help="View a specific session's conversation (can be partial ID)"
    )
    parser.add_argument(
        "--max-messages", "-m",
        type=int,
        default=0,
        help="Limit number of messages when viewing a session (0 = unlimited)"
    )

    args = parser.parse_args()

    # Handle --view mode
    if args.view:
        output = view_session(args.view, args.projects_dir, args.max_messages)
        if args.save:
            with open(args.save, "w") as f:
                f.write(output)
            print(f"Saved to {args.save}")
        else:
            print(output)
        return

    # Collect sessions
    sessions = collect_all_sessions(args.projects_dir)

    if not sessions:
        print("No sessions found.")
        return

    # Group by date
    sessions_by_date = group_sessions_by_date(sessions)

    # Generate output
    if args.output in ["md", "markdown"]:
        output = generate_markdown_summary(sessions_by_date)
    elif args.output == "json":
        output = generate_json_summary(sessions_by_date)
    else:
        output = generate_text_summary(sessions_by_date)

    # Output
    if args.save:
        with open(args.save, "w") as f:
            f.write(output)
        print(f"Saved to {args.save}")
    else:
        print(output)


if __name__ == "__main__":
    main()
