"""Operational commands.

python -m app.cli seed [--with-catalogue]
python -m app.cli create-owner --email owner@example.com --name "Owner"   (password is prompted)
"""

from __future__ import annotations

import argparse
import asyncio
import getpass
import sys

from app.core.config import get_settings
from app.db.session import build_engine, build_sessionmaker
from app.seed import seed_initial_catalogue, seed_reference
from app.services import user_service
from app.services.context import Actor


async def _run(args: argparse.Namespace) -> int:
    engine = build_engine(get_settings())
    maker = build_sessionmaker(engine)
    try:
        async with maker() as session:
            if args.command == "seed":
                await seed_reference(session)
                print("Reference data seeded (permissions, roles, occasions).")
                if args.with_catalogue:
                    created = await seed_initial_catalogue(session)
                    print("Initial catalogue seeded." if created else "Catalogue exists; skipped.")
            elif args.command == "create-owner":
                await seed_reference(session)
                password = getpass.getpass("Password (min 12 chars): ")
                if password != getpass.getpass("Repeat password: "):
                    print("Passwords do not match.", file=sys.stderr)
                    return 1
                user = await user_service.create_user(
                    session, args.email, args.name, password, ["OWNER"], Actor.system()
                )
                print(f"Owner created: {user.email}")
    finally:
        await engine.dispose()
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(prog="app.cli")
    sub = parser.add_subparsers(dest="command", required=True)
    seed = sub.add_parser("seed")
    seed.add_argument("--with-catalogue", action="store_true")
    owner = sub.add_parser("create-owner")
    owner.add_argument("--email", required=True)
    owner.add_argument("--name", required=True)
    sys.exit(asyncio.run(_run(parser.parse_args())))


if __name__ == "__main__":
    main()
