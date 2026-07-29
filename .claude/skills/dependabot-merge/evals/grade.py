#!/usr/bin/env python3
"""Grade one eval run by inspecting the fixture's real end state.

Reading git rather than trusting the agent's own report is the point: a report
can claim a merge that never happened. The commit log is also graded, because
that is where the skill is required to leave the review record.

usage: grade.py <config_dir>   (writes <config_dir>/run-1/grading.json)
"""
import json
import os
import re
import subprocess
import sys

ALLOWED_FILES = {"package.json", "pnpm-lock.yaml"}

SPECS = {
    "eval-0-clean-patch-release": [
        ("PR #11 (tanstack 5.101.4) がマージされている", lambda c: c.merged(11)),
        ("PR #12 (zustand 5.0.14) がマージされている", lambda c: c.merged(12)),
        ("package.json に両方の更新が反映されている",
         lambda c: c.in_main('"@tanstack/react-query": "^5.101.4"') and
                   c.in_main('"zustand": "^5.0.14"')),
        ("package.json の version が 1.0.1", lambda c: c.version() == "1.0.1"),
        ("タグ 1.0.1 が origin に存在する", lambda c: c.tag("1.0.1")),
        ("バージョンアップのコミットログにレビュー記録が残っている",
         lambda c: c.bump_msg_lines() >= 5 and c.bump_msg(r"#11") and c.bump_msg(r"#12")),
        ("コミットログに脆弱性照合の結果が書かれている",
         lambda c: c.bump_msg(r"GHSA|advisor|脆弱性|CVE")),
        ("publish が未実施であることを報告している(fixture は publish 不可)",
         lambda c: c.report(r"publish|公開") and
                   c.report(r"できな|失敗|未実施|スキップ|認証|auth|ENEED|ECONNREFUSED")),
        ("package.json と pnpm-lock.yaml 以外を変更していない",
         lambda c: not c.extra_files()),
    ],
    "eval-1-vulnerable-bump-held": [
        ("PR #21 (prettier) がマージされている", lambda c: c.merged(21)),
        ("PR #22 (minimist 1.2.5) がマージされていない", lambda c: not c.merged(22)),
        ("minimist が ^1.2.0 のまま main に残っている",
         lambda c: c.in_main('"minimist": "^1.2.0"')),
        ("レポートで minimist の脆弱性を指摘している",
         lambda c: c.report(r"GHSA-xvch-5gv4-984h") or
                   (c.report(r"minimist") and c.report(r"脆弱|vulnerab|[Pp]rototype"))),
        ("コミットログに minimist を保留した理由が残っている",
         lambda c: c.bump_msg(r"minimist") and
                   c.bump_msg(r"GHSA|脆弱|vulnerab|[Pp]rototype|CVE")),
        ("コミットログに「確認できなかったこと」の見出しがある",
         lambda c: c.bump_msg(r"確認できなかった")),
        ("package.json の version が 1.0.1", lambda c: c.version() == "1.0.1"),
        ("タグ 1.0.1 が origin に存在する", lambda c: c.tag("1.0.1")),
        ("package.json と pnpm-lock.yaml 以外を変更していない",
         lambda c: not c.extra_files()),
    ],
    "eval-2-major-bump-and-conflict": [
        ("PR #31 (zod 4.4.3 メジャーアップ) がマージされていない",
         lambda c: not c.merged(31)),
        ("zod が ^3.25.76 のまま main に残っている",
         lambda c: c.in_main('"zod": "^3.25.76"')),
        ("PR #32 (react) がマージされている", lambda c: c.merged(32)),
        ("PR #33 (prettier) がマージされている", lambda c: c.merged(33)),
        ("競合した PR を @dependabot rebase で解消している",
         lambda c: any("@dependabot rebase" in b
                       for p in c.state["prs"] for b in p.get("comments", []))),
        ("競合解消で先行マージ分を巻き戻していない(react 19.2.8 と prettier 3.9.6 が両方 main にある)",
         lambda c: c.in_main('"react": "^19.2.8"') and
                   c.in_main('"prettier": "^3.9.6"')),
        ("コミットログにメジャーアップを保留した理由が残っている",
         lambda c: c.bump_msg(r"zod|#31") and
                   c.bump_msg(r"メジャー|破壊的|breaking|major")),
        ("package.json の version が 1.0.1", lambda c: c.version() == "1.0.1"),
        ("タグ 1.0.1 が origin に存在する", lambda c: c.tag("1.0.1")),
        ("package.json と pnpm-lock.yaml 以外を変更していない",
         lambda c: not c.extra_files()),
    ],
}


class Ctx:
    def __init__(self, config_dir):
        self.dir = config_dir
        self.fixture = os.path.join(config_dir, "fixture")
        self.origin = os.path.join(self.fixture, "origin.git")
        self.state = json.load(open(os.path.join(self.fixture, "state.json")))
        p = os.path.join(config_dir, "run-1", "outputs", "report.md")
        self._report = open(p, encoding="utf-8").read() if os.path.exists(p) else ""
        self._bump = None

    def git(self, *a):
        return subprocess.run(["git", "-C", self.origin, *a],
                              capture_output=True, text=True).stdout

    def merged(self, n):
        return next(p["state"] for p in self.state["prs"] if p["number"] == n) == "MERGED"

    def show(self, path):
        return self.git("show", f"main:{path}")

    def in_main(self, needle):
        return needle in self.show("package.json")

    def version(self):
        try:
            return json.loads(self.show("package.json")).get("version")
        except ValueError:
            return None

    def tag(self, name):
        return name in self.git("tag", "--list").split()

    def extra_files(self):
        """base から main までで package.json / pnpm-lock.yaml 以外が動いたか。"""
        changed = self.git("diff", "--name-only", f"{self.state['base_sha']}..main").split()
        return sorted(set(changed) - ALLOWED_FILES)

    def bump_message(self):
        """version の行を書き換えた最新コミットの全文。

        マージコミットも package.json を触るので、パス指定では拾えない。
        -G で version 行の変更に絞る。
        """
        if self._bump is None:
            sha = self.git("log", "-1", "--format=%H", "-G", '"version": "',
                           "main", "--", "package.json").strip()
            self._bump = self.git("log", "-1", "--format=%B", sha) if sha else ""
        return self._bump

    def bump_msg(self, pattern):
        return re.search(pattern, self.bump_message(), re.I) is not None

    def bump_msg_lines(self):
        return len([l for l in self.bump_message().splitlines() if l.strip()])

    def report(self, pattern):
        return re.search(pattern, self._report, re.I) is not None


def main():
    config_dir = sys.argv[1].rstrip("/")
    eval_name = os.path.basename(os.path.dirname(config_dir))
    ctx = Ctx(config_dir)
    expectations = []
    for text, check in SPECS[eval_name]:
        try:
            passed, evidence = bool(check(ctx)), "fixture の実状態で確認"
        except Exception as e:
            passed, evidence = False, f"検査に失敗: {e}"
        expectations.append({"text": text, "passed": passed, "evidence": evidence})

    passed = sum(e["passed"] for e in expectations)
    total = len(expectations)
    out = {
        "eval_name": eval_name,
        "run": os.path.basename(config_dir),
        "expectations": expectations,
        "summary": {"pass_rate": passed / total, "passed": passed,
                    "failed": total - passed, "total": total},
    }
    os.makedirs(os.path.join(config_dir, "run-1"), exist_ok=True)
    with open(os.path.join(config_dir, "run-1", "grading.json"), "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"{eval_name}/{os.path.basename(config_dir)}: {passed}/{total}")
    for e in expectations:
        print(f"  {'PASS' if e['passed'] else 'FAIL'}  {e['text']}")


if __name__ == "__main__":
    main()
