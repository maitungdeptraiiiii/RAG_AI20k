import { test } from "node:test";
import assert from "node:assert/strict";
import { compareRows } from "./versions";

const result = (id: string, verdict: string) => ({
  concept_id: id,
  rule_id: "r1",
  object: null,
  view: { title: id, verdict, contract: [] },
});

test("compareRows orders contract before cross, changed then added then removed", () => {
  const rows = compareRows({
    contract: {
      changed: [{ key: "a/r1@", before: result("a", "Vi phạm"), after: result("a", "Phù hợp") }],
      added: [result("b", "Thiếu")],
      removed: [result("c", "Phù hợp")],
      unchanged: 3,
    },
    cross: {
      compare: {
        changed: [{ key: "d/r1@x", before: result("d", "Đạt"), after: result("d", "Vi phạm") }],
        added: [],
        removed: [],
        unchanged: 1,
      },
    },
  });
  assert.deepEqual(
    rows.map((r) => [r.scope, r.group, r.key]),
    [
      ["contract", "changed", "a/r1@"],
      ["contract", "added", "b/r1@"],
      ["contract", "removed", "c/r1@"],
      ["cross", "changed", "d/r1@x"],
    ],
  );
  assert.equal(rows[0].before.view.verdict, "Vi phạm");
  assert.equal(rows[0].after.view.verdict, "Phù hợp");
  assert.equal(rows[1].before, undefined);
  assert.equal(rows[2].after, undefined);
});

test("compareRows tolerates missing sections", () => {
  assert.deepEqual(compareRows({ contract: null, cross: null }), []);
  assert.deepEqual(compareRows(null), []);
});
