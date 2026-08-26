/**
 * Derived-metric expression evaluator (action-plan.md §4, §9).
 *
 * "Derived metrics are text expressions evaluated at read time, not in the
 * ETL. Change the formula and the entire history updates instantly, with no
 * re-extraction." Expressions reference metric keys (e.g.
 * "engaged_sessions / sessions") and are evaluated against ALREADY-AGGREGATED
 * numerator/denominator values for the currently visible rows — this module
 * never touches raw rows itself, so it automatically inherits the
 * ratio-safety of `aggregateMetric` in aggregation.ts instead of
 * re-implementing it.
 *
 * A small hand-rolled parser (+ - * / parens, metric-key identifiers,
 * numeric literals) is used instead of `eval`/`new Function` — this
 * expression string is analyst-authored config, not developer code, and
 * must not be able to execute arbitrary JS.
 */

const TOKEN_RE = /\s*([A-Za-z_][A-Za-z0-9_]*|[0-9]+(?:\.[0-9]+)?|[()+\-*/])/g;

type Token = { type: "ident" | "number" | "op" | "paren"; value: string };

function tokenize(expression: string): Token[] {
  const tokens: Token[] = [];
  let match: RegExpExecArray | null;
  let consumed = 0;
  TOKEN_RE.lastIndex = 0;
  while ((match = TOKEN_RE.exec(expression))) {
    if (match.index !== consumed) {
      throw new DerivedMetricError(`Unexpected character in expression at position ${consumed}: ${expression}`);
    }
    const raw = match[1];
    if (raw === undefined) break;
    consumed = TOKEN_RE.lastIndex;
    if (/^[A-Za-z_]/.test(raw)) tokens.push({ type: "ident", value: raw });
    else if (/^[0-9]/.test(raw)) tokens.push({ type: "number", value: raw });
    else if (raw === "(" || raw === ")") tokens.push({ type: "paren", value: raw });
    else tokens.push({ type: "op", value: raw });
  }
  if (consumed !== expression.length) {
    throw new DerivedMetricError(`Unexpected trailing content in expression: ${expression}`);
  }
  return tokens;
}

export class DerivedMetricError extends Error {}

/** Recursive-descent parser/evaluator over `+ - * /` with standard
 * precedence and parentheses. `resolve(metricKey)` supplies the aggregated
 * value for a metric identifier, or `null` when unavailable — unavailability
 * propagates through the whole expression rather than being treated as 0,
 * so "engagement_rate" doesn't silently render as 0% when sessions is 0. */
export function evaluateExpression(expression: string, resolve: (metricKey: string) => number | null): number | null {
  const tokens = tokenize(expression);
  let pos = 0;

  function peek(): Token | undefined {
    return tokens[pos];
  }
  function consume(): Token {
    const t = tokens[pos];
    if (!t) throw new DerivedMetricError(`Unexpected end of expression: ${expression}`);
    pos += 1;
    return t;
  }

  function parsePrimary(): number | null {
    const t = consume();
    if (t.type === "number") return Number(t.value);
    if (t.type === "ident") return resolve(t.value);
    if (t.type === "paren" && t.value === "(") {
      const inner = parseExpr();
      const closing = consume();
      if (closing.type !== "paren" || closing.value !== ")") {
        throw new DerivedMetricError(`Missing closing parenthesis: ${expression}`);
      }
      return inner;
    }
    throw new DerivedMetricError(`Unexpected token '${t.value}' in expression: ${expression}`);
  }

  function parseUnary(): number | null {
    const t = peek();
    if (t?.type === "op" && t.value === "-") {
      consume();
      const value = parseUnary();
      return value === null ? null : -value;
    }
    return parsePrimary();
  }

  function parseTerm(): number | null {
    let left = parseUnary();
    while (peek()?.type === "op" && (peek()!.value === "*" || peek()!.value === "/")) {
      const opToken = consume();
      const right = parseUnary();
      if (left === null || right === null) {
        left = null;
        continue;
      }
      if (opToken.value === "*") left = left * right;
      else left = right === 0 ? null : left / right;
    }
    return left;
  }

  function parseExpr(): number | null {
    let left = parseTerm();
    while (peek()?.type === "op" && (peek()!.value === "+" || peek()!.value === "-")) {
      const opToken = consume();
      const right = parseTerm();
      if (left === null || right === null) {
        left = null;
        continue;
      }
      left = opToken.value === "+" ? left + right : left - right;
    }
    return left;
  }

  const result = parseExpr();
  if (pos !== tokens.length) {
    throw new DerivedMetricError(`Unconsumed tokens in expression: ${expression}`);
  }
  return result;
}
