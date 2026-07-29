#!/usr/bin/env python3
"""Build an isolated fixture (bare origin + clone + PR branches) for one eval run.

All version pairs are real and published, and every upstream repo supports the
GitHub compare API — so the "read the upstream diff" step is actually
exercisable. Each branch's pnpm-lock.yaml is regenerated with the real pnpm
(network access required), because a Dependabot PR always rewrites the lockfile
and the skill's --frozen-lockfile verification depends on it being consistent.

The baseline package.json gets a publishConfig pointing at an unroutable
registry, so an agent that reaches the publish step can never hit real npm —
even on a machine where the operator is logged in.

usage: setup.py <scenario> <dest_dir>
"""
import json
import os
import shutil
import subprocess
import sys

REPO = "/home/asuka1975/work/typescript/frontend-library-catalog"

PUBLISH_GUARD = (
    '"packageManager": "pnpm@11.5.1",',
    '"packageManager": "pnpm@11.5.1",\n'
    '  "publishConfig": {\n'
    '    "registry": "http://127.0.0.1:1/"\n'
    '  },',
)

TANSTACK = [
    ('"@tanstack/query-sync-storage-persister": "^5.100.0"',
     '"@tanstack/query-sync-storage-persister": "^5.101.4"'),
    ('"@tanstack/react-query": "^5.100.0"',
     '"@tanstack/react-query": "^5.101.4"'),
    ('"@tanstack/react-query-devtools": "^5.100.0"',
     '"@tanstack/react-query-devtools": "^5.101.4"'),
    ('"@tanstack/react-query-persist-client": "^5.100.0"',
     '"@tanstack/react-query-persist-client": "^5.101.4"'),
]
TANSTACK_BODY = (
    "Bumps the tanstack group with 4 updates: "
    "[@tanstack/react-query](https://github.com/TanStack/query), "
    "@tanstack/react-query-devtools, @tanstack/react-query-persist-client "
    "and @tanstack/query-sync-storage-persister.\n"
    "Updates `@tanstack/react-query` from 5.100.0 to 5.101.4\n"
)

SCENARIOS = {
    # 健全な更新のみ。tanstack と zustand は package.json でも lockfile でも
    # 離れた行を触るので競合しない(実測済み)。
    "clean": {
        "seed": [(new, old) for old, new in TANSTACK] +
                [('"zustand": "^5.0.14"', '"zustand": "^5.0.13"')],
        "prs": [
            {"number": 11,
             "title": "Bump the tanstack group with 4 updates",
             "headRefName": "dependabot/npm_and_yarn/tanstack-79a1c2d3e4",
             "changes": TANSTACK,
             "body": TANSTACK_BODY},
            {"number": 12,
             "title": "Bump zustand from 5.0.13 to 5.0.14",
             "headRefName": "dependabot/npm_and_yarn/zustand-5.0.14",
             "changes": [('"zustand": "^5.0.13"', '"zustand": "^5.0.14"')],
             "body": "Bumps [zustand](https://github.com/pmndrs/zustand) "
                     "from 5.0.13 to 5.0.14.\n"},
        ],
    },
    # minimist 1.2.0 -> 1.2.5 は GHSA-xvch-5gv4-984h (critical, patched 1.2.6)
    # の範囲内に留まるので保留すべき更新。prettier は健全なパッチ。
    "vulnerable": {
        "seed": [('"prettier": "^3.9.6"', '"prettier": "^3.9.5"'),
                 ('"jsdom": "^30.0.0",',
                  '"jsdom": "^30.0.0",\n    "minimist": "^1.2.0",')],
        "prs": [
            {"number": 21,
             "title": "Bump prettier from 3.9.5 to 3.9.6",
             "headRefName": "dependabot/npm_and_yarn/prettier-3.9.6",
             "changes": [('"prettier": "^3.9.5"', '"prettier": "^3.9.6"')],
             "body": "Bumps [prettier](https://github.com/prettier/prettier) "
                     "from 3.9.5 to 3.9.6.\n"},
            {"number": 22,
             "title": "Bump minimist from 1.2.0 to 1.2.5",
             "headRefName": "dependabot/npm_and_yarn/minimist-1.2.5",
             "changes": [('"minimist": "^1.2.0"', '"minimist": "^1.2.5"')],
             "body": "Bumps [minimist](https://github.com/minimistjs/minimist) "
                     "from 1.2.0 to 1.2.5.\n"},
        ],
    },
    # zod 3 -> 4 はメジャーアップなので保留。prettier と react は package.json の
    # 隣接行(prettier の直下が react)なので、片方をマージすると他方が競合し、
    # @dependabot rebase が要る(実測済み)。lockfile だけが絡むペアは git が
    # 自動マージしてしまうことがあり、競合源として当てにならない。
    "major_conflict": {
        "seed": [('"zod": "^4.4.3"', '"zod": "^3.25.76"'),
                 ('"react": "^19.2.8"', '"react": "^19.2.7"'),
                 ('"react-dom": "^19.2.8"', '"react-dom": "^19.2.7"'),
                 ('"prettier": "^3.9.6"', '"prettier": "^3.9.5"')],
        "prs": [
            {"number": 31,
             "title": "Bump zod from 3.25.76 to 4.4.3",
             "headRefName": "dependabot/npm_and_yarn/zod-4.4.3",
             "changes": [('"zod": "^3.25.76"', '"zod": "^4.4.3"')],
             "body": "Bumps [zod](https://github.com/colinhacks/zod) "
                     "from 3.25.76 to 4.4.3.\n"},
            {"number": 32,
             "title": "Bump the react group with 2 updates",
             "headRefName": "dependabot/npm_and_yarn/react-1f2e3d4c5b",
             "changes": [('"react": "^19.2.7"', '"react": "^19.2.8"'),
                         ('"react-dom": "^19.2.7"', '"react-dom": "^19.2.8"')],
             "body": "Bumps the react group with 2 updates: "
                     "[react](https://github.com/facebook/react) and "
                     "[react-dom](https://github.com/facebook/react).\n"
                     "Updates `react` from 19.2.7 to 19.2.8\n"},
            {"number": 33,
             "title": "Bump prettier from 3.9.5 to 3.9.6",
             "headRefName": "dependabot/npm_and_yarn/prettier-3.9.6",
             "changes": [('"prettier": "^3.9.5"', '"prettier": "^3.9.6"')],
             "body": "Bumps [prettier](https://github.com/prettier/prettier) "
                     "from 3.9.5 to 3.9.6.\n"},
        ],
    },
}


def git(*args, cwd, check=True):
    return subprocess.run(["git", *args], cwd=cwd, check=check,
                          capture_output=True, text=True)


def edit_package_json(repo_dir, pairs):
    path = os.path.join(repo_dir, "package.json")
    text = open(path).read()
    for old, new in pairs:
        assert old in text, f"replace target not found: {old!r}"
        text = text.replace(old, new)
    open(path, "w").write(text)


def regen_lockfile(repo_dir):
    subprocess.run(["pnpm", "install", "--lockfile-only"], cwd=repo_dir,
                   check=True, capture_output=True, text=True)


def main():
    scenario, dest = sys.argv[1], sys.argv[2]
    spec = SCENARIOS[scenario]
    prs = spec["prs"]

    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    origin = os.path.join(dest, "origin.git")

    # 現在のリポジトリを種にして、送り先がローカルだけの origin を作る
    seed = os.path.join(dest, "_seed")
    git("clone", "-q", REPO, seed, cwd=dest)
    git("config", "user.email", "dependabot[bot]@users.noreply.github.com", cwd=seed)
    git("config", "user.name", "dependabot[bot]", cwd=seed)

    # main を「更新前」の状態に戻し、publish を封じ、lockfile を整合させる
    edit_package_json(seed, [PUBLISH_GUARD] + spec["seed"])
    # publish 封じの相棒。これが無いと pnpm が fetch-timeout の既定値(60 秒)まで
    # リトライし続け、エージェントが publish で固まる(実測)。この設定で 0.3 秒で
    # 失敗する。pnpm 11 は fetch 設定を .npmrc でなく pnpm-workspace.yaml から
    # 読むので、ここに書く。install は実レジストリに向くので影響しない。
    with open(os.path.join(seed, "pnpm-workspace.yaml"), "a") as f:
        f.write("\n# eval fixture: fail fast on the unreachable publish-guard registry\n"
                "fetchRetries: 0\n"
                "fetchTimeout: 5000\n")
    regen_lockfile(seed)
    git("commit", "-qam", "Set fixture baseline", cwd=seed)

    git("init", "-q", "--bare", "-b", "main", origin, cwd=dest)
    git("remote", "remove", "origin", cwd=seed, check=False)
    git("remote", "add", "origin", origin, cwd=seed)
    git("push", "-q", "origin", "main", cwd=seed)

    for pr in prs:
        git("checkout", "-q", "-B", pr["headRefName"], "main", cwd=seed)
        edit_package_json(seed, pr["changes"])
        regen_lockfile(seed)
        git("commit", "-qam", pr["title"], cwd=seed)
        git("push", "-q", "origin", pr["headRefName"], cwd=seed)
    git("checkout", "-q", "main", cwd=seed)
    shutil.rmtree(seed)

    work = os.path.join(dest, "work")
    git("clone", "-q", origin, work, cwd=dest)
    git("config", "user.email", "bot@example.com", cwd=work)
    git("config", "user.name", "gh-mock", cwd=work)

    # エージェントが作業するチェックアウト
    repo = os.path.join(dest, "repo")
    git("clone", "-q", origin, repo, cwd=dest)
    git("config", "user.email", "asuka1975@example.com", cwd=repo)
    git("config", "user.name", "asuka1975", cwd=repo)

    base = git("rev-parse", "main", cwd=origin).stdout.strip()
    state = {
        "base_sha": base,
        "prs": [dict(p, file="package.json", state="OPEN",
                     url=f"https://github.com/asuka1975/frontend-library-catalog/pull/{p['number']}")
                for p in prs],
    }
    with open(os.path.join(dest, "state.json"), "w") as f:
        json.dump(state, f, indent=2)

    print(f"fixture ready: {dest}  base={base[:8]}  PRs={[p['number'] for p in prs]}")


if __name__ == "__main__":
    main()
