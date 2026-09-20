"""
iwfm-io command line: API search, model inspection, PEST++ calibration.

Installed as the ``iwfm-io`` console script::

    iwfm-io api <keyword>
    iwfm-io init-agent [project_dir]
    iwfm-io describe <model_dir>
    iwfm-io pest setup   --model-dir M --obs obs.smp --dest pest_template
    iwfm-io pest agents  --template pest_template -n 8
    iwfm-io pest run     --template pest_template -n 8
    iwfm-io pest analyze <master_dir or case.pst>

Each command is a thin wrapper over the public API (``open_model``,
``iwfm_io.pest.pest_setup_from_model``, ``setup_agents``,
``load_ies_ensembles`` + ``diagnose_ies``) — everything the CLI does can
be scripted in Python with the same names.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

__all__ = ["main"]


# ------------------------------------------------------------- commands
def _cmd_describe(args) -> int:
    from iwfm_io.model_adapter import open_model
    info = open_model(args.model_dir).describe()
    print(json.dumps(info, indent=2, default=str))
    return 0


def _cmd_api(args) -> int:
    from iwfm_io._api_index import (index_path, load_index, safe_print,
                                    search)

    if args.path:
        print(index_path())
        return 0

    if not args.query:
        safe_print(load_index())
        return 0

    query = " ".join(args.query)
    hits = search(query)
    if not hits:
        safe_print(
            f"no iwfm-io name matches {query!r}.\n"
            f"`iwfm-io api` lists the whole index ({index_path()}).\n"
            f"If nothing there fits, writing it yourself is the right "
            f"call.")
        return 1
    safe_print(f"{len(hits)} match(es) for {query!r} - call these instead "
               f"of writing your own:\n")
    for entry in hits:
        safe_print(f"- {entry.parent}{entry.qualname}{entry.signature}\n"
                   f"    {entry.summary}")
    return 0


AGENT_RULES_FILENAME = "AGENT_RULES.md"
_BEGIN = "<!-- iwfm-io:begin"
_END = "<!-- iwfm-io:end -->"


def agent_rules_path() -> Path:
    """Path of the shipped coding-agent instruction block."""
    return Path(__file__).with_name(AGENT_RULES_FILENAME)


def _cmd_init_agent(args) -> int:
    """Install the "call iwfm-io, do not reimplement it" block."""
    import re

    block = agent_rules_path().read_text(encoding="utf-8").strip() + "\n"
    if args.print_only:
        from iwfm_io._api_index import safe_print
        safe_print(block)
        return 0

    target = Path(args.directory) / args.file
    if not target.parent.is_dir():
        print(f"error: {target.parent} does not exist", file=sys.stderr)
        return 1

    if not target.exists():
        target.write_text(f"# {target.parent.resolve().name}\n\n{block}",
                          encoding="utf-8")
        print(f"created {target}")
        return 0

    existing = target.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(_BEGIN) + r".*?" + re.escape(_END), re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(block.strip(), existing, count=1)
        if updated == existing:
            print(f"{target} is already up to date")
            return 0
        target.write_text(updated, encoding="utf-8")
        print(f"updated the iwfm-io block in {target}")
        return 0

    separator = "" if existing.endswith("\n\n") else (
        "\n" if existing.endswith("\n") else "\n\n")
    target.write_text(existing + separator + block, encoding="utf-8")
    print(f"appended the iwfm-io block to {target}")
    return 0


def _cmd_pest_setup(args) -> int:
    from iwfm_io.pest.quickstart import pest_setup_from_model

    qs = pest_setup_from_model(
        args.model_dir, args.obs, args.dest, case=args.case,
        parameters=tuple(args.parameters), zones=args.zones,
        date_format=args.date_format, max_gap=args.max_gap,
        weight=args.weight, noptmax=args.noptmax,
        ies_num_reals=args.reals, run_steps=tuple(args.steps),
        link_model=not args.no_link, overwrite=args.overwrite)
    print(json.dumps(qs.summary(), indent=2, default=str))
    pst = Path(args.dest) / f"{args.case}.pst"
    print(f"\ntemplate ready: {pst}")
    print(f"check it with a single forward run (noptmax={args.noptmax}):")
    print(f"  iwfm-io pest run --template {args.dest}")
    print("then scale out:")
    print(f"  iwfm-io pest run --template {args.dest} -n 8")
    return 0


def _cmd_pest_agents(args) -> int:
    from iwfm_io.pest.orchestrate import setup_agents, write_manager_script

    agents = setup_agents(
        args.template, args.n, dest_root=args.dest_root, exe=args.exe,
        host=args.host, port=args.port, overwrite=args.overwrite)
    manager = write_manager_script(args.template, exe=args.exe,
                                   port=args.port)
    print(f"created {len(agents)} agent dir(s) under "
          f"{Path(agents[0]).parent}")
    print(f"manager script: {manager}")
    print("start the manager, then each agent's start_agent script.")
    return 0


def _cmd_pest_run(args) -> int:
    import shutil
    import subprocess
    import time

    from iwfm_io.pest.orchestrate import _find_pst, setup_agents

    template = Path(args.template)
    pst = _find_pst(template)
    exe = shutil.which(args.exe) or (
        args.exe if Path(args.exe).is_file() else None)
    if exe is None:
        print(f"error: {args.exe!r} not found on PATH (install PEST++ "
              f"or pass --exe with a full path)", file=sys.stderr)
        return 1

    if args.agents <= 0:
        print(f"running {Path(exe).name} {pst} in {template} (serial)")
        return subprocess.run([exe, pst], cwd=template).returncode

    agents_root = Path(args.agents_root) if args.agents_root else \
        template.parent / f"{template.name}_agents"
    agent_dirs = setup_agents(
        template, args.agents, dest_root=agents_root, pst=pst, exe=exe,
        host="localhost", port=args.port, overwrite=True)
    print(f"master: {Path(exe).name} {pst} /h :{args.port}  "
          f"+ {len(agent_dirs)} agent(s)")
    master = subprocess.Popen([exe, pst, "/h", f":{args.port}"],
                              cwd=template)
    time.sleep(1.0)  # let the master bind its port (agents also retry)
    agent_procs = [
        subprocess.Popen([exe, pst, "/h", f"localhost:{args.port}"],
                         cwd=d, stdout=subprocess.DEVNULL,
                         stderr=subprocess.STDOUT)
        for d in agent_dirs]
    try:
        rc = master.wait()
    except KeyboardInterrupt:
        master.terminate()
        rc = 130
    for p in agent_procs:
        try:
            p.wait(timeout=30)
        except subprocess.TimeoutExpired:
            p.terminate()
    print(f"master finished with exit code {rc}; results in {template}")
    return rc


def _cmd_pest_analyze(args) -> int:
    import pandas as pd

    from iwfm_io.pest.diagnostics import diagnose_ies
    from iwfm_io.pest.ies import load_ies_ensembles

    path = Path(args.path)
    results = load_ies_ensembles(path)
    master_dir = path.parent if path.is_file() else path

    par_data = args.par_data
    if par_data is None:
        found = sorted(master_dir.glob("*_par_data.csv"))
        par_data = found[0] if found else None
    diag = diagnose_ies(results,
                        par_data=pd.read_csv(par_data)
                        if par_data is not None else None)
    print(diag.summary())
    if args.json:
        diag.to_json(args.json)
        print(f"\njson report written: {args.json}")
    return 0


# --------------------------------------------------------------- parser
def _add_traceback_everywhere(parser):
    """Accept ``--traceback`` after any subcommand too (the error hint
    tells users to re-run with it, wherever they typed the command)."""
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for sp in action.choices.values():
                sp.add_argument("--traceback", action="store_true",
                                default=argparse.SUPPRESS,
                                help=argparse.SUPPRESS)
                _add_traceback_everywhere(sp)


def _build_parser() -> "argparse.ArgumentParser":
    parser = argparse.ArgumentParser(
        prog="iwfm-io",
        description="Search the iwfm-io API, inspect a model, and drive "
                    "the PEST++ calibration workflow. Start with "
                    "`iwfm-io api <keyword>` to find the function you "
                    "need.")
    parser.add_argument("--traceback", action="store_true",
                        help="show full tracebacks on errors")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("describe",
                       help="summarize a model folder as JSON")
    p.add_argument("model_dir", help="model root folder")
    p.set_defaults(func=_cmd_describe)

    p = sub.add_parser(
        "api", help="search the API index: does iwfm-io already do this?",
        description="Search every public iwfm-io name by keyword. Run "
                    "this before writing any function that reads, "
                    "writes, parses, converts or aggregates IWFM data.")
    p.add_argument("query", nargs="*",
                   help="words to match against names and summaries "
                        "(no query prints the whole index)")
    p.add_argument("--path", action="store_true",
                   help="print the index file's location and exit")
    p.set_defaults(func=_cmd_api)

    p = sub.add_parser(
        "init-agent",
        help="add the 'use iwfm-io, don't reimplement it' block to a "
             "project's CLAUDE.md",
        description="Write the iwfm-io instruction block into a "
                    "project's agent instructions, so coding agents "
                    "working there call the package instead of "
                    "rewriting its readers. Re-run to update the block "
                    "in place; edits outside the markers are kept.")
    p.add_argument("directory", nargs="?", default=".",
                   help="project directory (default: the current one)")
    p.add_argument("--file", default="CLAUDE.md",
                   help="instructions filename (default: CLAUDE.md; "
                        "use AGENTS.md for other agent tooling)")
    p.add_argument("--print", dest="print_only", action="store_true",
                   help="print the block instead of writing it")
    p.set_defaults(func=_cmd_init_agent)

    pest = sub.add_parser("pest", help="PEST++ calibration workflow")
    pest_sub = pest.add_subparsers(dest="pest_command")

    p = pest_sub.add_parser(
        "setup", help="build a runnable pestpp-ies template from a "
                      "model folder + observed heads")
    p.add_argument("--model-dir", "-m", required=True,
                   help="IWFM model root folder (must have been run "
                        "once)")
    p.add_argument("--obs", required=True,
                   help="observed heads: SMP file or CSV with "
                        "site,datetime,value; sites = GW hydrograph "
                        "names/ids")
    p.add_argument("--dest", "-d", default="pest_template",
                   help="template directory to create "
                        "(default: pest_template)")
    p.add_argument("--case", default="iwfm_cal",
                   help="control-file stem (default: iwfm_cal)")
    p.add_argument("--parameters", nargs="+", default=["kh"],
                   help="properties to parameterize as multipliers "
                        "(e.g. kh ss sy strk; default: kh)")
    p.add_argument("--zones", default="subregion",
                   choices=["subregion", "layer", "global"],
                   help="multiplier granularity (default: subregion)")
    p.add_argument("--date-format", default=None,
                   choices=["dd/mm/yyyy", "mm/dd/yyyy"],
                   help="SMP date convention when ambiguous")
    p.add_argument("--max-gap", default="45D",
                   help="interpolation gap guard (default: 45D)")
    p.add_argument("--weight", type=float, default=1.0,
                   help="initial observation weight (default: 1)")
    p.add_argument("--noptmax", type=int, default=0,
                   help="noptmax in the control file (default: 0 — a "
                        "single check run)")
    p.add_argument("--reals", type=int, default=None,
                   help="ies_num_reals (default: pestpp-ies default)")
    p.add_argument("--steps", nargs="+",
                   default=["preprocessor", "simulation"],
                   help="IWFM tools the forward run executes")
    p.add_argument("--no-link", action="store_true",
                   help="copy the model instead of hardlinking")
    p.add_argument("--overwrite", action="store_true",
                   help="replace an existing template model copy")
    p.set_defaults(func=_cmd_pest_setup)

    p = pest_sub.add_parser(
        "agents", help="stamp out hardlinked PEST++ agent directories")
    p.add_argument("--template", "-t", required=True,
                   help="template directory (contains the .pst)")
    p.add_argument("-n", type=int, required=True,
                   help="number of agent directories")
    p.add_argument("--dest-root", default=None,
                   help="parent for agent dirs (default: template's "
                        "parent)")
    p.add_argument("--exe", default="pestpp-ies",
                   help="PEST++ executable (default: pestpp-ies)")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=4004)
    p.add_argument("--overwrite", action="store_true",
                   help="replace existing agent dirs")
    p.set_defaults(func=_cmd_pest_agents)

    p = pest_sub.add_parser(
        "run", help="run PEST++ on a template (optionally with local "
                    "parallel agents)")
    p.add_argument("--template", "-t", required=True,
                   help="template directory (contains the .pst)")
    p.add_argument("-n", "--agents", type=int, default=0, dest="agents",
                   help="local parallel agents to launch (default: 0 = "
                        "serial)")
    p.add_argument("--exe", default="pestpp-ies",
                   help="PEST++ executable (default: pestpp-ies)")
    p.add_argument("--port", type=int, default=4004,
                   help="manager port (default: 4004)")
    p.add_argument("--agents-root", default=None,
                   help="parent for agent dirs (default: "
                        "<template>_agents next to it)")
    p.set_defaults(func=_cmd_pest_run)

    p = pest_sub.add_parser(
        "analyze", help="diagnose a finished pestpp-ies run")
    p.add_argument("path", help="master directory or .pst file")
    p.add_argument("--par-data", default=None,
                   help="parameter-data CSV for bound-railing checks "
                        "(default: auto-discover *_par_data.csv)")
    p.add_argument("--json", default=None,
                   help="also write the full diagnostics state to this "
                        "JSON file")
    p.set_defaults(func=_cmd_pest_analyze)

    _add_traceback_everywhere(parser)
    return parser


def main(argv=None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        # bare `iwfm-io` or `iwfm-io pest`
        if getattr(args, "command", None) == "pest":
            print("usage: iwfm-io pest {setup,agents,run,analyze} — "
                  "see iwfm-io pest -h")
        else:
            parser.print_help()
        return 1
    try:
        return args.func(args)
    except KeyboardInterrupt:
        return 130
    except Exception as exc:
        if args.traceback:
            raise
        print(f"error: {exc}", file=sys.stderr)
        print("(re-run with --traceback for the full stack trace)",
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
