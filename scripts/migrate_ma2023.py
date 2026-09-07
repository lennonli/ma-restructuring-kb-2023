#!/usr/bin/env python3
"""迁移 2023 年并购重组案例，生成本库 cases/、索引报告和年度总结页。

数据只取自 ma-restructuring-digest/cases_ma2026/*.md 及 state/ma2023.json，
仅迁移 state 文件列明的代码，不把其他年度案例带入本库。
源材料没有提供或无法确认的 IPO 旧字段保持为空，不根据常识补写事实。
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


KB = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = Path(
    "/Users/licheng/Documents/zhipu/.zcode/workspace/default/ma-restructuring-digest"
)
YEAR = "2023"
BASE_PATH = "/ma2023"
STATE_NAME = "ma2023.json"
REPORT_SOURCE_NAME = "2026并购重组案例回溯报告-2023年度-20260907-V1.md"
REPORT_DEST_NAME = "2023年度总结.md"

FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)
H1_RE = re.compile(r"^#\s+(.+?)\s*$", re.M)
CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
NUMERIC_RE = re.compile(r"^[+-]?\d+(?:\.\d+)?$")

FM_FIELDS = [
    "company",
    "short",
    "code",
    "board",
    "layer",
    "listing_date",
    "inquiry_rounds",
    "cutoff_date",
    "lawyer",
    "tags",
    "deal_type",
    "pay_method",
    "deal_amount",
    "status",
    "registered_date",
    "fin_adv",
]


def parse_scalar(value: str) -> str:
    value = value.strip()
    if not value or value in {"null", "Null", "NULL", "~"}:
        return ""
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            parsed = json.loads(value)
            return str(parsed) if parsed is not None else ""
        except json.JSONDecodeError:
            return value[1:-1]
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    return value


def parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    data: dict[str, str] = {}
    for line in match.group(1).splitlines():
        field = re.match(r"^([A-Za-z_][A-Za-z0-9_-]*):\s*(.*)$", line)
        if field:
            data[field.group(1)] = parse_scalar(field.group(2))
    return data, text[match.end() :]


def first_nonempty(*values: object) -> str:
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text.lower() not in {"none", "null"}:
            return text
    return ""


def code_from(filename: str, fm: dict[str, str]) -> str:
    value = first_nonempty(fm.get("code"), fm.get("stock_code"))
    if value:
        match = CODE_RE.search(value)
        if match:
            return match.group(1)
    match = CODE_RE.search(filename)
    return match.group(1) if match else ""


def normalize_board(raw: str, code: str) -> str:
    value = raw.strip()
    if "新三板" in value:
        return "新三板"
    if "北交所" in value or "北京证券交易所" in value:
        return "北交所"
    if "科创板" in value:
        return "科创板"
    if "创业板" in value:
        return "深市创业板"
    if "沪市主板" in value or "上交所" in value or "上海主板" in value:
        return "沪市主板"
    if "深市主板" in value or "深主板" in value or "深圳主板" in value:
        return "深市主板"

    # 仅在源材料未给出板块时，依据证券代码的交易所板块口径归一化。
    if code.startswith("688"):
        return "科创板"
    if code.startswith(("300", "301")):
        return "深市创业板"
    if code.startswith(("600", "601", "603", "605")):
        return "沪市主板"
    if code.startswith(("000", "001", "002")):
        return "深市主板"
    if code.startswith(("920",)):
        return "北交所"
    if code.startswith(("872", "873", "874", "875")):
        return "新三板"
    return ""


def company_from(h1: str) -> str:
    title = h1.strip()
    if not title:
        return ""
    return re.split(r"[（(]", title, maxsplit=1)[0].strip()


def normalize_amount(value: str) -> str:
    value = value.strip().replace(",", "")
    return value if NUMERIC_RE.fullmatch(value) else value


def yaml_value(value: str, *, numeric: bool = False) -> str:
    if not value:
        return ""
    if numeric and NUMERIC_RE.fullmatch(value):
        return value
    return json.dumps(value, ensure_ascii=False)


def tags_value(raw: str) -> str:
    if not raw:
        return "[]"
    stripped = raw.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped
    values = [item.strip().strip('"').strip("'") for item in stripped.split(",")]
    values = [item for item in values if item]
    return "[" + ", ".join(json.dumps(item, ensure_ascii=False) for item in values) + "]"


def build_frontmatter(
    fm: dict[str, str], state: dict[str, object], filename: str, body: str
) -> tuple[dict[str, str], str]:
    code = code_from(filename, fm)
    short = first_nonempty(fm.get("short"), state.get("short"))
    if not short:
        stem = Path(filename).stem
        short = stem[7:] if re.match(r"^\d{6}-", stem) else stem

    h1_match = H1_RE.search(body)
    h1_company = company_from(h1_match.group(1)) if h1_match else ""
    company = first_nonempty(fm.get("company"), state.get("full_name"), h1_company)
    board = normalize_board(
        first_nonempty(fm.get("board"), state.get("board")), code
    )
    tags = fm.get("tags", "")
    if not tags:
        tags = "[]"

    output = {
        "company": company,
        "short": short,
        "code": code,
        "board": board,
        "layer": first_nonempty(fm.get("layer")),
        "listing_date": first_nonempty(
            fm.get("listing_date"), fm.get("listed_date"), state.get("listing_date")
        ),
        "inquiry_rounds": first_nonempty(fm.get("inquiry_rounds")),
        "cutoff_date": first_nonempty(fm.get("cutoff_date")),
        "lawyer": first_nonempty(fm.get("lawyer"), state.get("lawyer")),
        "tags": tags,
        "deal_type": first_nonempty(fm.get("deal_type"), state.get("deal_type")),
        "pay_method": first_nonempty(fm.get("pay_method"), state.get("pay_method")),
        "deal_amount": normalize_amount(
            first_nonempty(fm.get("deal_amount"), state.get("deal_amount"))
        ),
        "status": first_nonempty(fm.get("status"), state.get("status")),
        "registered_date": first_nonempty(
            fm.get("registered_date"), state.get("registered_date"), state.get("reg_date")
        ),
        "fin_adv": first_nonempty(fm.get("fin_adv"), state.get("fin_adv")),
    }
    return output, body


def render_frontmatter(data: dict[str, str]) -> str:
    lines = ["---"]
    for field in FM_FIELDS:
        value = data.get(field, "")
        if field == "tags":
            rendered = tags_value(value)
        elif field == "deal_amount":
            rendered = yaml_value(value, numeric=True)
        elif field in {"code", "inquiry_rounds", "listing_date", "cutoff_date", "registered_date"}:
            rendered = yaml_value(value, numeric=False)
        else:
            rendered = yaml_value(value)
        lines.append(f"{field}: {rendered}" if rendered else f"{field}:")
    lines.extend(["---", ""])
    return "\n".join(lines)


def report_case_map(case_files: list[Path]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for case_file in case_files:
        filename = case_file.name
        stem = case_file.stem
        short = re.sub(r"^\d{6}-", "", stem)
        for key in {filename, stem, short}:
            mapping[key] = filename
        code_match = re.match(r"^(\d{6})-", stem)
        if code_match:
            mapping.setdefault(code_match.group(1), filename)
    return mapping


def link_case_heading(line: str, mapping: dict[str, str]) -> str:
    match = re.match(r"^(###\s+)(\d{6}-[^（(]+)(.*)$", line)
    if not match:
        return line
    prefix, label, suffix = match.groups()
    code = label[:6]
    filename = mapping.get(code)
    if not filename or "](/ma2023/" in line:
        return line
    return f"{prefix}[{label.strip()}]({BASE_PATH}/{Path(filename).stem}){suffix}"


def rewrite_report(text: str, mapping: dict[str, str]) -> str:
    link_pattern = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")

    def replace_link(match: re.Match[str]) -> str:
        label, target = match.groups()
        if "cases_ma2026/" not in target:
            return match.group(0)
        raw_name = target.rsplit("/", 1)[-1]
        raw_name = raw_name.removesuffix(".md")
        filename = mapping.get(raw_name) or mapping.get(f"{raw_name}.md")
        if not filename:
            filename = mapping.get(label.strip())
        if not filename:
            return match.group(0)
        return f"[{label}]({BASE_PATH}/{Path(filename).stem})"

    rewritten = link_pattern.sub(replace_link, text)
    rewritten = rewritten.replace("cases_ma2026/", f"{BASE_PATH}/")

    lines: list[str] = []
    h1_seen = False
    for line in rewritten.splitlines():
        if line.startswith("# "):
            if h1_seen:
                line = "#" + line
            else:
                h1_seen = True
        if line.startswith("### "):
            line = link_case_heading(line, mapping)
        lines.append(line)
    if not h1_seen:
        lines.insert(0, f"# {YEAR}年并购重组案例回溯报告")
    return "\n".join(lines).rstrip() + "\n"


def load_state(source: Path) -> dict[str, dict[str, object]]:
    payload = json.loads((source / "state" / STATE_NAME).read_text(encoding="utf-8"))
    rows = payload if isinstance(payload, list) else payload.get("cases", [])
    return {str(row.get("code", "")).zfill(6): row for row in rows if row.get("code")}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", nargs="?", type=Path, default=DEFAULT_SOURCE)
    args = parser.parse_args()
    source = args.source.resolve()
    cases_source = source / "cases_ma2026"
    cases_dest = KB / "cases"
    reports_dest = KB / "reports"
    cases_dest.mkdir(parents=True, exist_ok=True)
    reports_dest.mkdir(parents=True, exist_ok=True)

    state_by_code = load_state(source)
    source_files = []
    for source_file in sorted(cases_source.glob("*.md")):
        source_fm, _ = parse_frontmatter(source_file.read_text(encoding="utf-8"))
        if code_from(source_file.name, source_fm) in state_by_code:
            source_files.append(source_file)
    if len(source_files) != len(state_by_code):
        found = {code_from(path.name, parse_frontmatter(path.read_text(encoding="utf-8"))[0]) for path in source_files}
        missing_codes = sorted(set(state_by_code) - found)
        raise SystemExit(f"源案例与 {STATE_NAME} 不一致，缺少代码：{', '.join(missing_codes)}")
    board_counts: Counter[str] = Counter()
    lawyer_count = 0
    missing: Counter[str] = Counter()
    output_files: list[Path] = []

    for source_file in source_files:
        raw = source_file.read_text(encoding="utf-8")
        source_fm, body = parse_frontmatter(raw)
        code = code_from(source_file.name, source_fm)
        state = state_by_code.get(code, {})
        data, body = build_frontmatter(source_fm, state, source_file.name, body)
        output_file = cases_dest / source_file.name
        output_file.write_text(render_frontmatter(data) + body.lstrip("\n"), encoding="utf-8")
        output_files.append(output_file)
        board_counts[data["board"] or "待核验"] += 1
        if data["lawyer"]:
            lawyer_count += 1
        for field in ("company", "code", "board", "deal_type", "pay_method", "deal_amount", "status", "registered_date", "lawyer", "fin_adv"):
            if not data[field]:
                missing[field] += 1

    report_source = source / "reports" / REPORT_SOURCE_NAME
    if report_source.exists():
        report_text = rewrite_report(
            report_source.read_text(encoding="utf-8"), report_case_map(output_files)
        )
        (reports_dest / REPORT_DEST_NAME).write_text(report_text, encoding="utf-8")

    print(f"迁移完成：{len(output_files)} 家 → {cases_dest}")
    print("板块分布：" + "、".join(f"{board} {count}" for board, count in sorted(board_counts.items())))
    print(f"律师提取率：{lawyer_count}/{len(output_files)}")
    if missing:
        print("留空字段：" + "、".join(f"{field} {count} 家" for field, count in sorted(missing.items())))
    if report_source.exists():
        print(f"年度总结：{reports_dest / REPORT_DEST_NAME}")
    else:
        print(f"[警告] 未找到年度报告：{report_source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
