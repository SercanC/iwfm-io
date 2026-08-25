"""
iwfm-io command line: model inspection and PEST++ calibration workflow.

Installed as the ``iwfm-io`` console script::

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
def _build_parser() -> "argparse.ArgumentParser":
    parser = argparse.ArgumentParser(
        prog="iwfm-io",
        description="IWFM model inspection and PEST++ calibration "
                    "workflow (iwfm-io).")
    parser.add_argument("--traceback", action="store_true",
                        help="show full tracebacks on errors")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("describe",
                       help="summarize a model folder as JSON")
    p.add_argument("model_dir", help="model root folder")
    p.set_defaults(func=_cmd_describe)

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
