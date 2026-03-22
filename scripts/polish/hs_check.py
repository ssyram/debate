#!/usr/bin/env python3
"""scripts/hs_check.py — Haskell finegrained check via Python glue.

Usage:
    python3 scripts/hs_check.py <input.md> [--output DIR] [--model MODEL] [--env FILE]

Handles:
  - .env loading (DEBATE_BASE_URL / DEBATE_API_KEY)
  - GHC/cabal availability check
  - Auto-build the Haskell project if needed
  - Delegates to the compiled `check` binary
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
    """Verify ghc and cabal are available."""
    for tool in ["ghc", "cabal"]:
        if not shutil.which(tool):
            # Try ghcup paths
            ghcup_bin = Path.home() / ".ghcup" / "bin"
            if (ghcup_bin / tool).exists():
                os.environ["PATH"] = str(ghcup_bin) + ":" + os.environ.get("PATH", "")
            else:
                sys.exit(f"Error: {tool} not found. Install via ghcup: curl --proto '=https' --tlsv1.2 -sSf https://get-ghcup.haskell.org | sh")


def build_if_needed():
    """Run cabal build if executables don't exist or source is newer."""
    check_bin = find_binary("check")
    if check_bin and check_bin.exists():
        # Check if any source is newer than binary
        src_mtime = max(f.stat().st_mtime for f in HS_PROJECT.rglob("*.hs"))
        cabal_mtime = (HS_PROJECT / "new-polish.cabal").stat().st_mtime
        bin_mtime = check_bin.stat().st_mtime
        if bin_mtime > max(src_mtime, cabal_mtime):
            return  # up to date
    print("\033[36m[hs_check]\033[0m Building Haskell project...", flush=True)
    result = subprocess.run(
        ["cabal", "build", "check"],
        cwd=str(HS_PROJECT),
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(f"Error: cabal build failed (code {result.returncode})")


def find_binary(name: str) -> Path | None:
    """Find the cabal-built binary."""
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


def main():
    parser = argparse.ArgumentParser(description="Haskell finegrained check")
    parser.add_argument("input", type=Path, help="Design document (.md)")
    parser.add_argument("--output", type=Path, default=None, help="Output directory for artifacts")
    parser.add_argument("--model", default=None, help="LLM model name")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV, help="Path to .env file")
    args = parser.parse_args()

    if not args.input.exists():
        sys.exit(f"Error: input file not found: {args.input}")

    # Setup
    load_env(args.env)
    check_ghc()
    build_if_needed()

    binary = find_binary("check")
    if not binary:
        sys.exit("Error: check binary not found after build")

    # Build command
    cmd = [str(binary), "--input", str(args.input.resolve())]
    if args.output:
        cmd += ["--output", str(args.output.resolve())]
    if args.model:
        cmd += ["--model", args.model]

    # Run
    print(f"\033[36m[hs_check]\033[0m Running: {' '.join(cmd)}", flush=True)
    result = subprocess.run(cmd)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
