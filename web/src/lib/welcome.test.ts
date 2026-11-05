import assert from "node:assert/strict";
import { test } from "node:test";

import { askFacts } from "./welcome.ts";

test("five facts follow 'Ask'; inside a space the first names that space", () => {
  assert.equal(askFacts(null, 365).length, 5);
  assert.equal(askFacts(null, 365)[0], "580 WRI publications");
  assert.equal(askFacts("Cities", 71)[0], "71 WRI publications on cities");
  assert.equal(askFacts("Ocean", null)[0], "the WRI publications on ocean");
});
