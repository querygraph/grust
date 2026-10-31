"""Build the Catalyst foldability table for every Sail scalar function name.

Inputs (extracted with `git archive` from the pinned sources):
  spark-expr/.../expressions/*.scala and analysis/FunctionRegistry.scala (Spark 617618396)
  sail-scalar/crates/sail-plan/src/function/scalar/*.rs (Sail 15fd1888c)
Output: Markdown table on stdout, a rule histogram on stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(sys.argv[1])
SPARK = ROOT / "spark-expr/sql/catalyst/src/main/scala/org/apache/spark/sql/catalyst"
SAIL = ROOT / "sail-scalar/crates/sail-plan/src/function/scalar"

# ---------------------------------------------------------------- Sail names
SAIL_ENTRY = re.compile(r'\(\s*"([A-Za-z_0-9]+)"\s*,\s*(F::[A-Za-z_]+)')
sail: dict[str, tuple[str, str]] = {}
for path in sorted(SAIL.glob("*.rs")):
    text = path.read_text()
    for m in SAIL_ENTRY.finditer(text):
        name, kind = m.group(1).lower(), m.group(2)[3:]
        wrapped = text[m.end() : m.end() + 60]
        if kind == "non_foldable":
            inner = re.match(r"\(F::([A-Za-z_]+)", wrapped)
            kind = f"non_foldable({inner.group(1) if inner else '?'})"
        sail.setdefault(name, (kind, path.name))

# ------------------------------------------------------ Spark registry map
registry_text = (SPARK / "analysis/FunctionRegistry.scala").read_text()
reg: dict[str, str] = {}
for m in re.finditer(r'expression\[(\w+)\]\(\s*"(\w+)"', registry_text):
    reg.setdefault(m.group(2).lower(), m.group(1))
for m in re.finditer(r'expressionBuilder\(\s*"(\w+)"\s*,\s*(\w+)', registry_text):
    reg.setdefault(m.group(1).lower(), m.group(2) + " (builder)")
for m in re.finditer(r'expressionGeneratorBuilder\(\s*"(\w+)"\s*,\s*(\w+)', registry_text):
    reg.setdefault(m.group(1).lower(), m.group(2) + " (builder)")
for m in re.finditer(r'expressionGeneratorOuter\[(\w+)\]\(\s*"(\w+)"', registry_text):
    reg.setdefault(m.group(2).lower(), m.group(1))
for m in re.finditer(r'castAlias\(\s*"(\w+)"', registry_text):
    reg.setdefault(m.group(1).lower(), "Cast")

# ------------------------------------------------- Spark class definitions
classes: dict[str, tuple[str, str]] = {}
DEF = re.compile(r"^(?:abstract\s+)?(?:case\s+)?(?:class|trait|object)\s+(\w+)", re.M)
for path in sorted((SPARK / "expressions").rglob("*.scala")):
    text = path.read_text()
    marks = [(m.start(), m.group(1)) for m in DEF.finditer(text)]
    for i, (start, name) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        body = text[start:end]
        brace = body.find("{")
        header = body[: brace if brace > 0 else len(body)]
        classes.setdefault(name, (header, body))

EXTENDS = re.compile(r"(?:extends|with)\s+(\w+)")


def parents(name: str) -> list[str]:
    if name not in classes:
        return []
    return EXTENDS.findall(classes[name][0])


MARKERS = {
    "Unevaluable": "never (Unevaluable)",
    "Nondeterministic": "never (Nondeterministic)",
    "Stateful": "never (Stateful → Nondeterministic)",
    "Generator": "never (Generator)",
    "HigherOrderFunction": "never (HigherOrderFunction)",
    "SimpleHigherOrderFunction": "never (HigherOrderFunction)",
    "UserDefinedExpression": "never (UDF, default foldable)",
}

FOLDABLE = re.compile(
    r"override\s+(?:lazy\s+val|def)\s+foldable\s*(?::\s*Boolean)?\s*=\s*([^\n]+)"
)
CHILDREN = re.compile(
    r"\w+\.forall\(_\.foldable\)|child\.foldable|left\.foldable && right\.foldable"
    r"|(?:\w+\.foldable(?: && )?)+"
)
REPLACEMENT = re.compile(
    r"replacement(?:\s*:\s*Expression)?\s*=\s*\{?\s*(?:new\s+)?(\w+)\s*\("
)


def classify(name: str, depth: int = 0) -> str:
    """Spark's foldability rule for the Catalyst class `name`."""
    if name in ("StaticInvoke", "Invoke"):
        return "children"  # InvokeLike.foldable: children foldable, deterministic, trusted type (objects.scala:74–75)
    if name in ("UnaryPositive", "ToTime", "ToBinary", "ParseToDate", "ParseToTimestamp", "Collation"):
        return "children"  # hand-read: replacement is a deterministic wrapper over the children
    if name == "TryReflect":
        return "never (replacement CallMethodViaReflection: Nondeterministic)"
    if name not in classes:
        return "? class not found"
    header, body = classes[name]
    if "Rand(" in body or "Randn(" in body:
        return "never (replacement uses Rand)"
    own = FOLDABLE.search(body)
    if own:
        value = own.group(1).strip()
        if value == "true":
            return "always (override true)"
        if value == "false":
            return "never (override false)"
        if CHILDREN.fullmatch(value):
            return "children"
        return f"custom: {value}"
    # Marker traits are `final override`s, so they win over any inherited
    # override wherever they sit in the linearization: scan the whole ancestry first.
    ancestry: list[str] = []
    seen: set[str] = set()
    stack = list(parents(name))
    while stack:
        p = stack.pop(0)
        if p in seen:
            continue
        seen.add(p)
        ancestry.append(p)
        stack.extend(parents(p))
    for p in ancestry:
        if p in MARKERS:
            return MARKERS[p]
    replaceable = any(p in ("RuntimeReplaceable", "InheritAnalysisRules") for p in ancestry)
    for p in ancestry:
        if p in classes:
            inherited = FOLDABLE.search(classes[p][1])
            if inherited:
                value = inherited.group(1).strip()
                if value == "true":
                    return f"always ({p} override true)"
                if value == "false":
                    return f"never ({p} override false)"
                if CHILDREN.fullmatch(value):
                    return "children"
                return f"custom ({p}): {value}"
    if replaceable:
        if "RaiseError" in body:
            return "never (replacement raises)"
        rep = REPLACEMENT.search(body)
        if rep and depth < 4 and rep.group(1) != name:
            inner = classify(rep.group(1), depth + 1)
            return inner if inner == "children" else f"replacement {rep.group(1)}: {inner}"
        if re.search(r"replacement:\s*Expression\)", header + body):
            return "children"  # hand-read: constructor-built deterministic wrapper (Nvl → Coalesce, TryX → TryEval(X), …)
        if "Invoke(" in body or "evaluator" in body:
            return "children"  # replacement is a deterministic Invoke (XPath evaluators)
        return "replacement (unparsed)"
    return "children"


VOLATILE = {"rand", "randn", "random", "randstr", "uniform", "random_poisson",
            "monotonically_increasing_id", "spark_partition_id", "uuid", "input_file_name",
            "shuffle", "input_file_block_start", "input_file_block_length"}
NAME_MARKED = {"aggregate", "reduce", "filter", "map_filter", "transform", "transform_keys",
               "transform_values", "exists", "forall", "array_sort"}
rows = []
for name in sorted(sail):
    kind, file = sail[name]
    cls = reg.get(name)
    if cls is None:
        spark, rule = "not in FunctionRegistry", "—"
    else:
        base = cls.replace(" (builder)", "")
        if cls.endswith("(builder)"):
            for candidate in (base.removesuffix("ExpressionBuilder"), base.removesuffix("Builder")):
                if candidate in classes:
                    base = candidate
                    break
        spark, rule = cls, classify(base)
    if kind == "unknown":
        action = "unsupported in Sail"
    elif rule.startswith("never") and name in VOLATILE:
        action = "already rejected: Volatile lowering"
    elif rule.startswith("never") and name in NAME_MARKED:
        action = "marked by name at function.rs:82"
    elif rule.startswith("never") and not kind.startswith("non_foldable"):
        action = "mark"
    elif rule.startswith("never"):
        action = "marked"
    elif rule.startswith("always"):
        action = "must stay unmarked"
    elif rule.startswith(("replacement", "custom", "?")):
        action = "read by hand"
    else:
        action = ""
    rows.append((name, kind, file, spark, rule, action))

print("| Sail name | Sail builder | file | Catalyst class | Spark foldability | Constant-context action |")
print("| --- | --- | --- | --- | --- | --- |")
for r in rows:
    print("| " + " | ".join(f"`{x}`" if i < 4 and x else x for i, x in enumerate(r)) + " |")

summary: dict[str, int] = {}
for r in rows:
    summary[r[4]] = summary.get(r[4], 0) + 1
for k, v in sorted(summary.items(), key=lambda kv: -kv[1]):
    print(f"- {k}: {v}", file=sys.stderr)
