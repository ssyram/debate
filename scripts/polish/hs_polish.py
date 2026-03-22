#!/usr/bin/env python3
"""scripts/hs_polish.py — Haskell design polish pipeline via Python glue.

Usage:
    python3 scripts/hs_polish.py <input.md> [OPTIONS]

Options:
    --design FILE          Predefined design file (skip LLM-generated design)
    --decisions FILE       Predefined decisions/guide file (skip initial check+debate)
    --output-dir DIR       Output working log directory (default: <input>_polish/)
    --model MODEL          LLM model name (default: gpt-5.4-nano)
    --max-polish-rounds N  Outer polish loop cap (default: 3)
    --max-rewrite-rounds N Inner rewrite loop cap (default: 2)
    --env FILE             Path to .env file (default: .local/.env)

Handles:
  - .env loading (DEBATE_BASE_URL / DEBATE_API_KEY)
  - GHC/cabal availability check via ghcup PATH injection
  - Auto-build the Haskell project if source is stale
  - Delegates to the compiled `polish` binary
  - Output is a full working log directory with every intermediate artifact
"""

import subprocess, sys, os, shutil, argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
HS_PROJECT = SCRIPT_DIR / "haskell-polish"
REPO_ROOT = SCRIPT_DIR.parent.parent
DEFAULT_ENV = REPO_ROOT / ".local" / ".env"


def load_env(env_file: Path):
    """Source a shell .env file into os.environ."""
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # handle: export KEY=VALUE or KEY=VALUE
        if line.startswith("export "):
            line = line[7:]
        if "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()


def check_ghc():
    """Verify ghc and cabal are available, injecting ghcup PATH if needed."""
    for tool in ["ghc", "cabal"]:
        if not shutil.which(tool):
            ghcup_bin = Path.home() / ".ghcup" / "bin"
            if (ghcup_bin / tool).exists():
                os.environ["PATH"] = str(ghcup_bin) + ":" + os.environ.get("PATH", "")
            else:
                sys.exit(
                    f"Error: {tool} not found. Install via ghcup: "
                    "curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | sh"
                )


def find_binary(name: str) -> Path | None:
    """Find the cabal-built binary by name."""
    result = subprocess.run(
        ["cabal", "list-bin", name],
        cwd=str(HS_PROJECT),
        capture_output=True, text=True
    )
    if result.returncode == 0:
        p = Path(result.stdout.strip())
        if p.exists():
            return p
    # Fallback: search dist-newstyle
    for p in HS_PROJECT.rglob(f"build/{name}/{name}"):
        if p.is_file() and os.access(p, os.X_OK):
            return p
    return None


def build_if_needed():
    """Run cabal build if executables don't exist or source is newer."""
    polish_bin = find_binary("polish")
    if polish_bin and polish_bin.exists():
        # Check if any source file is newer than binary
        hs_files = list(HS_PROJECT.rglob("*.hs"))
        cabal_file = HS_PROJECT / "new-polish.cabal"
        if hs_files:
            src_mtime = max(f.stat().st_mtime for f in hs_files)
        else:
            src_mtime = 0
        cabal_mtime = cabal_file.stat().st_mtime if cabal_file.exists() else 0
        bin_mtime = polish_bin.stat().st_mtime
        if bin_mtime > max(src_mtime, cabal_mtime):
            return  # binary is up to date

    print("\033[36m[hs_polish]\033[0m Building Haskell project...", flush=True)
    result = subprocess.run(
        ["cabal", "build", "polish"],
        cwd=str(HS_PROJECT),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"Error: cabal build failed (code {result.returncode})")
    print("\033[36m[hs_polish]\033[0m Build successful.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Haskell design polish pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("input", type=Path, nargs="?", default=None,
                        help="Topic .md file (--topic mode, fresh debate-tool run)")
    parser.add_argument("--topic", type=Path, default=None,
                        help="Topic .md file (alternative to positional)")
    parser.add_argument("--log", type=Path, default=None,
                        help="Existing debate log .json (resume mode)")
    parser.add_argument("--design", type=Path, default=None,
                        help="Predefined design file (skip LLM-generated design)")
    parser.add_argument("--decisions", type=Path, default=None,
                        help="Predefined decisions/guide file (skip initial check+debate)")
    parser.add_argument("--issues", type=Path, default=None,
                        help="Pre-computed issues file (skip check step)")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output working log directory (default: <input>_polish/)")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--max-polish-rounds", type=int, default=None,
                        help="Outer polish loop cap")
    parser.add_argument("--max-rewrite-rounds", type=int, default=None,
                        help="Inner rewrite loop cap")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV,
                        help="Path to .env file")
    args = parser.parse_args()

    # Resolve topic: positional or --topic
    topic = args.topic or args.input
    log_file = args.log
    if not topic and not log_file:
        parser.error("Either a topic file (positional or --topic) or --log FILE is required")
    if topic and not topic.exists():
        sys.exit(f"Error: topic file not found: {topic}")
    if log_file and not log_file.exists():
        sys.exit(f"Error: log file not found: {log_file}")
    if args.design and not args.design.exists():
        sys.exit(f"Error: design file not found: {args.design}")
    if args.decisions and not args.decisions.exists():
        sys.exit(f"Error: decisions file not found: {args.decisions}")
    if args.issues and not args.issues.exists():
        sys.exit(f"Error: issues file not found: {args.issues}")

    # Setup
    load_env(args.env)
    check_ghc()
    build_if_needed()

    binary = find_binary("polish")
    if not binary:
        sys.exit("Error: polish binary not found after build")

    cmd = [str(binary)]
    if topic:
        cmd += ["--topic", str(topic.resolve())]
    if log_file:
        cmd += ["--log", str(log_file.resolve())]

    if args.design:
        cmd += ["--design", str(args.design.resolve())]
    if args.decisions:
        cmd += ["--decisions", str(args.decisions.resolve())]
    if args.output_dir:
        cmd += ["--output-dir", str(args.output_dir.resolve())]
    if args.model:
        cmd += ["--model", args.model]
    if args.max_polish_rounds is not None:
        cmd += ["--max-polish-rounds", str(args.max_polish_rounds)]
    if args.max_rewrite_rounds is not None:
        cmd += ["--max-rewrite-rounds", str(args.max_rewrite_rounds)]

    # Run
    print(f"\033[36m[hs_polish]\033[0m Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
