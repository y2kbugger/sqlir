"""CLI front end for sqlir migration system."""

import argparse
import importlib
import sys
import tomllib
from datetime import UTC, datetime
from pathlib import Path

from .migrate import Migrate, State, format_status
from .model import TableRow


def load_models_from_module(module_path: str) -> list[type[TableRow]]:
    """Import a module by dotted path and collect all TableRow subclasses."""
    module = importlib.import_module(module_path)
    models: list[type[TableRow]] = []
    for name in dir(module):
        obj = getattr(module, name)
        if isinstance(obj, type) and issubclass(obj, TableRow) and obj is not TableRow:
            models.append(obj)
    return models


def load_config() -> dict[str, str]:
    """Load [tool.sqlir] from ./pyproject.toml if it exists."""
    pyproject = Path("pyproject.toml")
    if not pyproject.exists():
        return {}
    with pyproject.open("rb") as f:
        data = tomllib.load(f)
    return data.get("tool", {}).get("sqlir", {})


def resolve_args(args: argparse.Namespace) -> tuple[str, str]:
    """Resolve db_path and models from CLI args + pyproject.toml fallback.

    Returns (db_path, models) strings. Raises SystemExit on missing values.
    """
    config = load_config()

    db_path = args.db_path or config.get("db_path")
    models = args.models_module or config.get("models_module")

    if not db_path:
        print("Error: --db-path is required (or set db_path in [tool.sqlir])")
        sys.exit(1)
    if not models:
        print("Error: --models-module is required (or set models_module in [tool.sqlir])")
        sys.exit(1)

    assert isinstance(db_path, str) and isinstance(models, str)
    return db_path, models


def make_migrate(args: argparse.Namespace) -> Migrate:
    """Build a Migrate object from resolved CLI args."""
    db_path, models_spec = resolve_args(args)
    models = load_models_from_module(models_spec)
    return Migrate(db_path, models=models)


def cmd_status(migrate: Migrate, args: argparse.Namespace) -> int:
    """Show summary of migrations in progress."""
    result = migrate.check()
    print(format_status(result))
    return 0 if result.state == State.CURRENT else 1


def cmd_generate(migrate: Migrate, args: argparse.Namespace) -> int:
    """Generate migration script from schema mismatch."""
    init = getattr(args, "init_declarative", False)
    if init:
        path = migrate.init_declarative()
        print(f"Initialized declarative SQL: {path}")

    result = migrate.check()
    if result.state == State.CURRENT:
        print("Nothing to generate — schema already matches the DB")
        return 0
    if init and not result.has_schema_mismatch:
        print("Nothing to generate — schema already matches the DB")
        return 0
    if result.state != State.MISMATCH:
        print(
            f"Can't generate: DB is out of sync with migration scripts ({result.state.value}).\n"
            "Resolve or apply existing migrations first so that script generation has a clean baseline to compare against."
        )
        return 1
    path = migrate.generate()
    print(f"Generated {path}")
    return 0


def cmd_apply(migrate: Migrate, args: argparse.Namespace) -> int:
    """Apply pending migrations."""
    result = migrate.check()
    if result.state == State.CURRENT:
        print("Nothing to apply — already up to date")
        return 0
    if result.state != State.PENDING:
        print(f"Can't apply: migrations aren't in a clean state ({result.state.value}).\nResolve conflicts or sync the DB with existing scripts before applying.")
        return 1

    filename = args.filename
    if filename:
        if filename not in result.pending:
            print(f"Migration '{filename}' is not pending")
            return 1
        to_apply = [filename]
    else:
        to_apply = list(result.pending)

    for script in to_apply:
        migrate.backup()
        migrate.apply(script)
        print(f"Applied {script}")

    return 0


def cmd_backup(migrate: Migrate, args: argparse.Namespace) -> int:
    """Create backup, optionally save ref."""
    path = migrate.backup()
    print(f"Backup created: {path}")
    if args.ref:
        migrate.save_ref()
        print(f"Ref saved: {migrate.ref_path}")
    return 0


def _format_size(num_bytes: int) -> str:
    """Human-readable file size (binary units)."""
    size = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if size < 1024 or unit == "TiB":
            precision = 0 if unit == "B" else 1
            return f"{size:.{precision}f} {unit}"
        size /= 1024
    return f"{size:.1f} TiB"  # unreachable, keeps type checker happy


def _parse_backup_name(name: str, db_name: str) -> tuple[datetime | None, int | None]:
    """Parse a backup filename into (local datetime, migration level).

    Filenames look like ``2026-02-10T14-30-05.123456.003.mydb.sqlite``:
    a UTC timestamp, the highest applied migration number captured in the
    snapshot, then the DB name. Returns ``(None, None)`` parts that cannot be
    parsed (e.g. a foreign file in the .bak dir).
    """
    suffix = f".{db_name}"
    if not name.endswith(suffix):
        return None, None
    stem = name[: -len(suffix)]  # e.g. 2026-02-10T14-30-05.123456.003
    ts_part, _, level_part = stem.rpartition(".")
    try:
        level = int(level_part)
    except ValueError:
        return None, None
    try:
        # Stored in UTC; render in the host's local timezone.
        dt = datetime.strptime(ts_part, "%Y-%m-%dT%H-%M-%S.%f").replace(tzinfo=UTC).astimezone()
    except ValueError:
        return None, level
    return dt, level


def _list_backups(migrate: Migrate) -> None:
    """Print available backups to stdout, newest first."""
    backups = migrate.list_backups()
    if not backups:
        print("No snapshots found")
    else:
        print("  #   when (local)          migration  size       file")
        for i, b in enumerate(backups, 1):
            dt, level = _parse_backup_name(b.name, migrate.db_path.name)
            when = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else "?"
            mig = f"{level:03d}" if level is not None else "?"
            size = _format_size(b.stat().st_size)
            print(f"  {i:<3} {when:<21} {mig:^9}  {size:>9}  {b.name}")
    if migrate.ref_path.exists():
        print(f"  ref: {migrate.ref_path.name}")


def cmd_restore(migrate: Migrate, args: argparse.Namespace) -> int:
    """Restore DB or scripts."""
    if args.scripts:
        migrate.restore_scripts()
        print("Restored scripts from ref DB.")
        return 0

    # Interactive mode: list backups and prompt for selection
    if args.interactive:
        backups = migrate.list_backups()
        if not backups:
            print("No snapshots available to restore.")
            return 1
        _list_backups(migrate)
        try:
            choice = input("Select backup number (or 'q' to cancel): ").strip()
        except EOFError, KeyboardInterrupt:
            print("\nCancelled.")
            return 1
        if choice.lower() == "q":
            print("Cancelled.")
            return 1
        try:
            idx = int(choice)
        except ValueError:
            print(f"Invalid selection: {choice}")
            return 1
        if idx < 1 or idx > len(backups):
            print(f"Selection out of range: {idx}")
            return 1
        selected = backups[idx - 1]
        migrate.backup()
        migrate.restore_db(selected)
        print(f"Restored DB from backup: {selected.name}")
        return 0

    # Restore specific backup by name
    if args.backup:
        backup_path = migrate.backup_dir / args.backup
        if not backup_path.exists():
            print(f"Backup not found: {args.backup}")
            _list_backups(migrate)
            return 1
        migrate.backup()
        migrate.restore_db(backup_path)
        print(f"Restored DB from backup: {args.backup}")
        return 0

    # Default: DB restore from ref
    migrate.backup()
    migrate.restore_db()
    print("Restored DB from ref.")
    return 0


def _dev_step(migrate: Migrate, *, prev_state: State | None = None) -> int:
    """Recursive dev auto-resolve state machine."""
    result = migrate.check()
    if prev_state is not None:
        print("----------------------", flush=True)
    print(format_status(result), flush=True)

    if result.state == prev_state:
        print(f"Still {result.state.value} after fix attempt. Manual intervention needed.")
        return 1

    match result.state:
        case State.CURRENT:
            return 0
        case State.ERROR:
            return 1
        case State.CONFLICTED:
            migrate.restore_scripts()
            print("Restored scripts from ref DB.")
            return _dev_step(migrate, prev_state=result.state)
        case State.DIVERGED:
            migrate.backup()
            migrate.restore_db()
            print("Restored DB from ref.")
            return _dev_step(migrate, prev_state=result.state)
        case State.PENDING:
            migrate.backup()
            for script in result.pending:
                migrate.apply(script)
                print(f"Applied {script}")
            return _dev_step(migrate, prev_state=result.state)
        case State.MISMATCH:
            path = migrate.generate()
            print(f"Generated {path}")
            return _dev_step(migrate, prev_state=result.state)


def cmd_dev(migrate: Migrate, args: argparse.Namespace) -> int:
    """Auto-resolve to CURRENT."""
    return _dev_step(migrate)


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(
        prog="sqlir-migrate",
        description="sqlir migration CLI",
        epilog=(
            "pyproject.toml config:\n"
            "  Options can also be set in [tool.sqlir]:\n"
            "\n"
            "    [tool.sqlir]\n"
            '    db_path = "path/to/db.sqlite"\n'
            '    models_module = "myapp.models"\n'
            "\n"
            "  CLI flags take precedence over pyproject.toml values."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--db-path", dest="db_path", help="Path to working SQLite DB")
    parser.add_argument("--models-module", dest="models_module", help="Dotted module path containing TableRow models")

    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("status", help="Show summary of migration in progress")
    gen_p = sub.add_parser("generate", help="Generate migration script from schema mismatch")
    gen_p.add_argument(
        "--init-declarative",
        action="store_true",
        help="Initialize declarative SQL folder and starter script (010.views.sql)",
    )

    apply_p = sub.add_parser("apply", help="Apply pending migrations")
    apply_p.add_argument("filename", nargs="?", default=None, help="Specific migration file to apply")

    backup_p = sub.add_parser("backup", help="Create backup")
    backup_p.add_argument("--ref", action="store_true", help="Set reference db to the current devlocal db.")

    restore_p = sub.add_parser("restore", help="Restore DB or scripts from ref/backup")
    restore_mode = restore_p.add_mutually_exclusive_group()
    restore_mode.add_argument("--scripts", action="store_true", help="Restore scripts instead of DB")
    restore_mode.add_argument("-i", "--interactive", action="store_true", help="Interactively select a backup to restore")
    restore_mode.add_argument("-b", "--backup", default=None, help="Specific backup filename to restore")

    sub.add_parser("dev", help="Automatically run migration commands to get devlocal DB up-to-date.")

    return parser


COMMANDS = {
    "status": cmd_status,
    "generate": cmd_generate,
    "apply": cmd_apply,
    "backup": cmd_backup,
    "restore": cmd_restore,
    "dev": cmd_dev,
}


def main(argv: list[str] | None = None) -> None:
    """Entry point for the CLI."""
    parser = build_parser()
    args = parser.parse_args(argv)
    migrate = make_migrate(args)
    handler = COMMANDS[args.command]
    code = handler(migrate, args)
    raise SystemExit(code)


if __name__ == "__main__":
    main()
