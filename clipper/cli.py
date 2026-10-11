"""Command line entry point: clipper run / approve / render / preview / doctor / clean / serve / app."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from clipper import doctor, jobs, pipeline, preview, provision, shell
from clipper.config import AppConfig, load_config
from clipper.models import Candidate


def _config() -> AppConfig:
    path = shell.project_home() / "config.yaml"
    return load_config(path if path.exists() else None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="clipper")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="process a video file")
    run.add_argument("source")
    run.add_argument("--campaign", required=True)
    run.add_argument("--stop-after", choices=pipeline.STEPS)
    run.add_argument("--from", dest="start_from", choices=pipeline.STEPS,
                     help="reuse the job's saved output of earlier steps")

    approve = sub.add_parser("approve", help="mark candidates approved for rendering")
    approve.add_argument("job_id")
    approve.add_argument("numbers", nargs="+", type=int)

    for name, help_text in (("render", "render approved clips"),
                            ("preview", "write caption-free crop previews")):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("job_id")

    sub.add_parser("doctor", help="check that the setup is complete")
    sub.add_parser("setup", help="download what's missing (ffmpeg, the face model), then check")
    sub.add_parser("clean", help="delete expired working copies and scratch files")
    serve = sub.add_parser("serve", help="start the review app in your browser")
    serve.add_argument("--port", type=int, default=8765)
    serve.add_argument("--no-browser", action="store_true")
    app = sub.add_parser("app", help="make a Clipper app you can open instead of running serve")
    app.add_argument("--port", type=int, default=8765)
    app.add_argument("--dest", help="folder to put Clipper.app in (default: ~/Applications)")
    return parser


def _cmd_run(args, cfg: AppConfig) -> int:
    paths = pipeline.run_job(args.source, args.campaign, cfg, stop_after=args.stop_after,
                             start_from=args.start_from)
    if not paths.candidates.exists():
        print(f"job {paths.root.name}: stopped after {args.stop_after}")
        return 0
    data = jobs.read_json(paths.candidates)
    print(f"job {paths.root.name}: {len(data['candidates'])} candidates")
    for raw in data["candidates"]:
        c = Candidate.from_dict(raw)
        flag = "  [check framing]" if c.needs_check else ""
        print(f"  {c.n}. [{c.start:7.1f}-{c.end:7.1f}] score {c.score}  {c.headline}{flag}")
        print(f"      {c.reason}")
    if data["candidates"]:
        print(f"\nNext: clipper approve {paths.root.name} <numbers>")
    return 0


def _cmd_approve(args, cfg: AppConfig) -> int:
    paths = jobs.paths_for(args.job_id, cfg)
    data = jobs.read_json(paths.candidates)
    known = {raw["n"] for raw in data["candidates"]}
    unknown = sorted(set(args.numbers) - known)
    if unknown:
        print(f"no such candidate(s): {', '.join(str(n) for n in unknown)}. "
              f"this job has {sorted(known)}")
        return 1
    for raw in data["candidates"]:
        raw["approved"] = raw["n"] in args.numbers
    jobs.write_json(paths.candidates, data)
    print(f"approved: {sorted(args.numbers)}")
    print(f"\nNext: clipper render {args.job_id}")
    return 0


def _cmd_render(args, cfg: AppConfig) -> int:
    outputs = pipeline.render_approved(args.job_id, cfg)
    if not outputs:
        print("nothing approved yet — run: clipper approve <job-id> <numbers>")
        return 0
    for path in outputs:
        print(path)
    return 0


def _cmd_preview(args, cfg: AppConfig) -> int:
    job = pipeline.load_render_inputs(args.job_id, cfg)
    for cand in job.candidates:
        print(preview.render_preview(job.paths, job.meta, job.plans[cand.n], cand,
                                     transcript=job.transcript, pacing=job.campaign.pacing))
    return 0


def _cmd_doctor(_args, _cfg: AppConfig) -> int:
    failed = False
    for name, ok, fix in doctor.check_all():
        print(f"{'OK  ' if ok else 'FAIL'} {name}" + ("" if ok else f"  -> {fix}"))
        failed = failed or not ok
    return 1 if failed else 0


def _cmd_setup(args, cfg: AppConfig) -> int:
    for item in provision.ITEMS:
        try:
            provision.ensure((item,), report=print)
        except provision.ProvisionError as exc:
            print(f"error: {exc}", file=sys.stderr)
    return _cmd_doctor(args, cfg)


def _cmd_clean(_args, cfg: AppConfig) -> int:
    removed = pipeline.clean(cfg)
    for path in removed:
        print(f"removed {path}")
    if not removed:
        print("nothing to clean")
    return 0


def _serve_lock(jobs_dir: Path, port: int):
    """Held for the server's lifetime; None if another `clipper serve` holds it.

    A second server would load the first one's running task as "interrupted" and
    start it again, two ffmpeg processes writing the same files.
    """
    try:
        import fcntl
    except ImportError:                                  # Windows: no lock yet
        return object()
    jobs_dir.mkdir(parents=True, exist_ok=True)
    handle = open(jobs_dir / "serve.lock", "a+")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.seek(0)
        other = handle.read().strip()
        handle.close()
        print(f"Clipper is already running at http://127.0.0.1:{other or '?'}"
              " — use that one, or stop it first.")
        return None
    handle.seek(0)
    handle.truncate()
    handle.write(str(port))
    handle.flush()
    return handle


def _cmd_serve(args, cfg: AppConfig) -> int:
    import threading
    import webbrowser

    import uvicorn

    from clipper.web import tasks
    from clipper.web.app import create_app
    from clipper.web.worker import Worker

    lock = _serve_lock(Path(cfg.jobs_dir), args.port)
    if lock is None:
        return 1
    # On start, then daily. Nothing renders yet, so every partial file is junk.
    pipeline.clean(cfg, all_partials=True)
    provision.start_background()                         # a fresh install fetches ffmpeg and the model
    tasks.start_daily_cleanup(cfg)
    worker = Worker(Path(cfg.jobs_dir) / "queue.json", tasks.make_runners(cfg))
    tasks.mark_interrupted(cfg, worker)                  # after the queue is loaded
    worker.start()
    url = f"http://127.0.0.1:{args.port}"
    print(f"Clipper is running at {url}  (Ctrl-C to stop)")
    if not args.no_browser:
        threading.Timer(1.0, webbrowser.open, [url]).start()
    try:
        uvicorn.run(create_app(cfg, worker, shell.project_home() / "frontend" / "dist"),
                    host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        worker.stop()
    return 0


def _cmd_app(args, _cfg: AppConfig) -> int:
    from clipper import appbundle
    app = appbundle.install(Path(args.dest).expanduser() if args.dest else None, args.port)
    print(f"Made {app}\nOpen it (Spotlight: Clipper) to start Clipper; drag it to the Dock to keep it handy.")
    return 0


COMMANDS = {
    "run": _cmd_run,
    "approve": _cmd_approve,
    "render": _cmd_render,
    "preview": _cmd_preview,
    "doctor": _cmd_doctor,
    "setup": _cmd_setup,
    "clean": _cmd_clean,
    "serve": _cmd_serve,
    "app": _cmd_app,
}


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    cfg = _config()
    shell.tools_on_path()
    try:
        return COMMANDS[args.command](args, cfg)
    except Exception as exc:                      # a CLI shows the message, not a traceback
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
