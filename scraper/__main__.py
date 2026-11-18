from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .config_loader import ConfigError
from .job_settings import load_app_config, open_store
from .runner import KEYWORDS_REQUIRED, RunResult, normalize_keywords, run


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="scraper",
        description="Scrape job listings using the job settings stored in Mongo",
    )
    parser.add_argument(
        "-k",
        "--keyword",
        action="append",
        dest="keywords",
        default=None,
        help="keyword to scrape (required); pass --keyword multiple times for several",
    )
    parser.add_argument(
        "sites",
        nargs="*",
        help="optional site names to run; overrides 'enabled' flags in the job settings",
    )
    return parser.parse_args(argv)


def _filtered_results(result: RunResult) -> list[dict[str, Any]]:
    return [
        {"keyword": keyword, "site": site, "payload": payloads.filtered}
        for (keyword, site), payloads in result.results.items()
    ]


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv if argv is not None else sys.argv[1:]))
    keywords = normalize_keywords(args.keywords)
    if not keywords:
        print(f"[cli] {KEYWORDS_REQUIRED}", file=sys.stderr)
        return 2
    try:
        config = load_app_config(open_store())
    except ConfigError as exc:
        print(f"[config] {exc}", file=sys.stderr)
        return 2
    result = run(config, targets=args.sites, keywords=keywords)
    json.dump(_filtered_results(result), sys.stdout, indent=2)
    sys.stdout.write("\n")
    return result.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
