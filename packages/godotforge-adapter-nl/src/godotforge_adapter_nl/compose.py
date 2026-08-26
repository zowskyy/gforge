"""godotforge-compose — natural-language candidate-manifest adapter CLI.

Shells out to an existing AI CLI (default: `claude -p`, reading the prompt
via stdin) to translate a plain-language game description into a goal
document, per docs/contracts/candidate-manifest-adapter.md. The candidate
is then validated through the real, unmodified compile_goal() pipeline —
this module never invents its own validation or writes to any
godotforge-core file. On a missing required field (compile_goal()
status="clarification"), the human is asked directly for the answer; no
further LLM round-trip is needed for filling in a single structured field.
Never auto-applies — it only ever writes a goal file and tells the human
the exact `hub run` commands to preview/apply it themselves.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

from godotforge_core.hub.goal import compile_goal

from godotforge_adapter_nl.rejection_log import log_rejection as _log_rejection

_CONTRACT_DOC_RELATIVE = Path("docs/contracts/candidate-manifest-adapter.md")
_DEFAULT_LLM_CMD = "claude -p"
_MAX_CLARIFICATION_ROUNDS = 3


def find_contract_doc(start: Path | None = None) -> Path:
    """Walk upward from *start* (default: cwd) looking for the contract
    document. Raises FileNotFoundError with a clear message if not found —
    this tool refuses to guess at the contract's content."""
    here = (start or Path.cwd()).resolve()
    for candidate_dir in (here, *here.parents):
        candidate = candidate_dir / _CONTRACT_DOC_RELATIVE
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f"could not find {_CONTRACT_DOC_RELATIVE} above {here} — "
        "run this from inside the godot-forge repo"
    )


def extract_json(text: str) -> dict[str, Any]:
    """Extract a JSON object from LLM output, tolerating a ```json fenced
    block (LLMs often wrap output in one despite being asked not to)."""
    fenced = re.search(r"```(?:json)?\s*\n(.*?)\n```", text, re.DOTALL)
    candidate_text = fenced.group(1) if fenced else text
    return json.loads(candidate_text.strip())


def build_prompt(contract_text: str, description: str) -> str:
    return (
        f"{contract_text}\n\n"
        "---\n\n"
        "Following the contract above exactly, translate this game "
        "description into a single goal JSON document. Output ONLY the "
        "JSON object itself — no prose, no markdown fences, no "
        'explanation. If the description does not fit either template per '
        'the contract\'s "When an idea doesn\'t fit" section, output '
        'exactly this shape instead: {"error": "<plain explanation>"}\n\n'
        f"Description: {description}"
    )


def invoke_llm(prompt: str, *, command: str, timeout: float = 120.0) -> str:
    """Run *command* as a shell command, piping *prompt* via stdin.

    shell=True is deliberate here, not an oversight: on Windows, CLI tools
    installed via npm (claude included) are typically a `.cmd`/`.bat` shim,
    which CreateProcess cannot launch directly even given a fully-resolved
    path — only cmd.exe can. subprocess.run(["claude", "-p"], shell=False)
    fails with WinError 2 "cannot find the file specified" even when
    `claude` is genuinely on PATH and runs fine when typed at a prompt
    (confirmed by hand on Windows while building this). shell=True is safe
    here specifically because *command* comes from a local CLI flag
    (--llm-cmd) the person running this tool already controls directly —
    equivalent trust to them typing it in their own terminal — and the
    actual untrusted content (the game description) is never part of the
    command string; it's piped via stdin as *prompt*.

    encoding="utf-8" is explicit (not just text=True) because on Windows,
    text=True alone falls back to the console's active codepage (cp1252 by
    default) for encoding stdin/stdout, and the contract doc this prompt
    embeds contains non-ASCII characters (e.g. U+2192 "->") that cp1252
    cannot represent — confirmed by hand on Windows while building this
    (UnicodeEncodeError: 'charmap' codec can't encode character '→').
    """
    try:
        result = subprocess.run(
            command,
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=timeout,
            shell=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            f"could not execute LLM command {command!r}: {exc}. "
            "Check that it's installed and on PATH."
        ) from exc
    if result.returncode != 0:
        raise RuntimeError(f"LLM CLI ({command!r}) exited {result.returncode}: {result.stderr.strip()}")
    return result.stdout


def set_dotted_field(document: dict[str, Any], dotted_field: str, value: str) -> None:
    """Set document['a']['b'] = value for dotted_field == 'a.b', creating
    intermediate dicts as needed."""
    parts = dotted_field.split(".")
    node = document
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def compile_with_clarification(
    candidate: dict[str, Any],
    *,
    out_path: Path,
    ask: callable = input,
    say: callable = print,
    rounds_left: int = _MAX_CLARIFICATION_ROUNDS,
) -> int:
    """Drive compile_goal()'s three real outcomes (see
    docs/contracts/candidate-manifest-adapter.md): ok -> write the goal
    file; clarification -> ask the human directly for each missing field
    and retry; ValueError -> report it and stop (never retried blindly)."""
    try:
        result = compile_goal(candidate)
    except ValueError as exc:
        say(f"error: {exc}", file=sys.stderr)
        return 1

    if result.status == "ok":
        out_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        say(f"wrote {out_path}")
        say(f"next: godotforge hub run {out_path}          (preview, read-only)")
        say(f"      godotforge hub run {out_path} --apply  (apply, after reviewing the preview)")
        return 0

    if rounds_left <= 0:
        say(
            "error: too many clarification rounds without resolving all required fields",
            file=sys.stderr,
        )
        return 1

    for issue in result.issues:
        answer = ask(f"{issue.message}\n> ").strip()
        set_dotted_field(candidate, issue.field, answer)

    return compile_with_clarification(
        candidate, out_path=out_path, ask=ask, say=say, rounds_left=rounds_left - 1
    )


def compose(
    description: str,
    *,
    llm_command: str,
    out_path: Path,
    contract_path: Path | None = None,
    invoke: callable = invoke_llm,
    ask: callable = input,
    say: callable = print,
    log_rejection: callable = _log_rejection,
) -> int:
    contract_text = (contract_path or find_contract_doc()).read_text(encoding="utf-8")
    prompt = build_prompt(contract_text, description)

    say(f"invoking: {llm_command}", file=sys.stderr)
    raw_output = invoke(prompt, command=llm_command)

    try:
        candidate = extract_json(raw_output)
    except json.JSONDecodeError as exc:
        say(
            f"error: LLM output was not valid JSON: {exc}\n\nraw output:\n{raw_output}",
            file=sys.stderr,
        )
        return 1

    if set(candidate) == {"error"}:
        reason = candidate["error"]
        say(reason)
        try:
            log_rejection(description, reason)
        except OSError as exc:
            say(f"warning: could not persist rejection log: {exc}", file=sys.stderr)
        return 1

    return compile_with_clarification(candidate, out_path=out_path, ask=ask, say=say)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("description", nargs="?", help="Plain-language game description")
    parser.add_argument("--file", type=Path, help="Read the description from a file instead")
    parser.add_argument(
        "--llm-cmd",
        default=_DEFAULT_LLM_CMD,
        help=f"Shell command to invoke as the LLM (prompt piped via stdin). Default: {_DEFAULT_LLM_CMD!r}",
    )
    parser.add_argument(
        "--out", type=Path, default=Path("goal.json"), help="Output goal file path"
    )
    args = parser.parse_args(argv)

    if args.file:
        description = args.file.read_text(encoding="utf-8")
    elif args.description:
        description = args.description
    else:
        description = sys.stdin.read()

    if not description.strip():
        print("error: no description given (positional arg, --file, or stdin)", file=sys.stderr)
        return 1

    return compose(description, llm_command=args.llm_cmd, out_path=args.out)


if __name__ == "__main__":
    raise SystemExit(main())
