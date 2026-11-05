import assert from "node:assert/strict";
import { test } from "node:test";

import { scoped } from "./spaces.ts";

test("a space adds its topic to the request's filters; all of WRI adds nothing", () => {
  assert.deepEqual(scoped({ yearFrom: 2020, region: "Africa" }, "Ocean"), { yearFrom: 2020, region: "Africa", topic: "Ocean" });
  assert.deepEqual(scoped({ yearFrom: 2020 }, null), { yearFrom: 2020 });
});
