"""ait: the ai-toolkit command line.

  ait hindsight ...    self-improving memory (alias: hs)
  ait rules ...        every rule Claude follows in a project, and the post-merge retro
  ait setup ...        inventory your Claude Code setup and replicate it on another machine
  ait ui               open the live, read-only dashboard
  ait doctor           check that everything is installed and healthy
  ait snapshot NAME    print a feature's dashboard JSON (for debugging the dashboard)
  ait migrate-legacy   remove what a 0.1 install.sh left behind, once the plugin is enabled
"""
import argparse
import json
import os
import sys

from . import __version__


def cmd_ui(a):
    from .dashboard.server import DIST, discover, serve
    if not a.api_only and not os.path.exists(os.path.join(DIST, "index.html")):
        ui = os.path.dirname(DIST)
        sys.exit("dashboard not built. Run: pnpm -C %s install && pnpm -C %s build" % (ui, ui))
    if a.feature and a.feature not in {f["name"] for f in discover()}:
        sys.exit("no enabled feature %r with a dashboard" % a.feature)
    try:
        httpd = serve(a.port)
    except OSError as e:
        sys.exit("can't listen on 127.0.0.1:%d (%s).\nAnother dashboard may be running: lsof -nP -iTCP:%d -sTCP:LISTEN\n"
                 "or pick another port: ait ui --port %d" % (a.port, e.strerror or e, a.port, a.port + 1))
    url = "http://127.0.0.1:%d/" % a.port + ("#%s" % a.feature if a.feature else "")
    print("ai-toolkit ui: %s (read-only, Ctrl-C to stop)" % ("http://127.0.0.1:%d/api/modules" % a.port if a.api_only else url),
          flush=True)
    if not a.no_open and not a.api_only:
        import webbrowser
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


def cmd_snapshot(a):
    from .dashboard.server import discover, run_snapshot
    feature = next((f for f in discover() if f["name"] == a.feature), None)
    if not feature:
        sys.exit("no enabled feature %r" % a.feature)
    code, body, _ = run_snapshot(feature)
    if code != 200:
        sys.exit(body.decode())
    print(json.dumps(json.loads(body), indent=2) if a.pretty else body.decode())


def cmd_doctor(a):
    from .core import config, install
    from .hindsight import cli as hs
    print("ai-toolkit %s" % __version__)
    print("  plugin:  %s" % (install.plugin_enabled() or "not enabled (see docs/getting-started.md)"))
    print("  config:  %s" % config.path())
    print("hindsight:")
    hs.cmd_doctor(a)


def cmd_migrate_legacy(a):
    from .core import install, legacy
    todo = legacy.plan()
    if not todo:
        print("nothing to remove: no 0.1 hooks or links found")
        return
    for kind, path, detail in todo:
        print("  remove %-5s %s  (%s)" % (kind, path, detail))
    if a.dry_run:
        return
    if not install.plugin_enabled() and not a.force:
        sys.exit("the ai-toolkit plugin isn't enabled, so removing these would turn hindsight off.\n"
                 "Enable it first (docs/getting-started.md), or pass --force.")
    if not a.yes and input("remove %d item(s)? [y/N] " % len(todo)).lower() != "y":
        sys.exit("aborted")
    backup = legacy.apply(todo)
    print("done.%s Restart Claude Code sessions to pick up the change." % (" settings.json backup: %s." % backup if backup else ""))


def build_parser():
    from .hindsight import cli as hindsight_cli
    from .rules import cli as rules_cli
    from .setup import cli as setup_cli
    p = argparse.ArgumentParser(prog="ait", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--version", action="version", version="ai-toolkit %s" % __version__)
    sub = p.add_subparsers(dest="cmd", metavar="COMMAND", required=True)
    hindsight_cli.register(sub)
    rules_cli.register(sub)
    setup_cli.register(sub)

    u = sub.add_parser("ui", help="open the live, read-only dashboard")
    u.add_argument("--feature", "--module", dest="feature", help="open on this feature")
    u.add_argument("--port", type=int, default=7319)
    u.add_argument("--no-open", action="store_true", help="don't open a browser")
    u.add_argument("--api-only", action="store_true", help="serve only /api (for the Vite dev server)")
    u.set_defaults(fn=cmd_ui)
    sub.add_parser("doctor", help="check installation and hindsight health").set_defaults(fn=cmd_doctor)
    s = sub.add_parser("snapshot", help="print a feature's dashboard JSON")
    s.add_argument("feature")
    s.add_argument("--pretty", action="store_true")
    s.set_defaults(fn=cmd_snapshot)
    m = sub.add_parser("migrate-legacy", help="remove what a 0.1 install.sh left behind (hooks in settings.json, links)")
    m.add_argument("--dry-run", action="store_true", help="only list what would be removed")
    m.add_argument("-y", "--yes", action="store_true", help="don't ask")
    m.add_argument("--force", action="store_true", help="even if the plugin isn't enabled")
    m.set_defaults(fn=cmd_migrate_legacy)
    return p


def main(argv=None):
    a = build_parser().parse_args(argv)
    a.fn(a)


def hs_main():
    """`hs ...` == `ait hindsight ...` (console script for `uv tool install`)."""
    main(["hindsight"] + sys.argv[1:])


def reference_markdown():
    """docs/reference/cli.md, generated from the parsers so it can't drift (tests/core/test_docs.py checks it)."""
    import argparse as ap

    def walk(parser, words, out):
        out.append("## `%s`\n\n```\n%s```\n" % (" ".join(words), parser.format_help().replace("\n\n\n", "\n\n")))
        for action in parser._actions:
            if isinstance(action, ap._SubParsersAction):
                for name, sub in action.choices.items():
                    walk(sub, words + [name], out)

    os.environ["COLUMNS"] = "110"  # stable wrapping
    out = ["# CLI reference\n\nGenerated by `make docs` from the argparse definitions. Do not edit by hand.\n"]
    walk(build_parser(), ["ait"], out)
    return "\n".join(out)
