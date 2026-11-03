// TASK-076: merge review in the Reconstruction view against the real app shell (stub provider, no model call).
// Boundary: the default e2e API has no live proposer (S3 runs as a stub), so the merge-proposals
// endpoints are answered statefully in the browser; the real panel, keyboard flow and refresh are exercised.
import { expect, test } from "@playwright/test";
import { blockExternal, createProject, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));
test.setTimeout(90_000);

const member = (name: string, role: string, evidence: unknown[] = []) => ({
  key: name.toLowerCase(), kind: "label", name, role, wellbore_id: null, evidence,
});

test("TASK-076: proposal is accepted then reverted from the keyboard; nothing merges before Accept", async ({ page }) => {
  let status = "pending";
  const posts: string[] = [];
  await page.route(/\/api\/v1\/projects\/[^/]+\/merge-proposals(\?.*)?$/, async (route) => {
    const body = {
      proposal_id: "p1", project_id: "x", run_id: "r1", status, acceptable: status === "pending", dataset_current: true,
      dataset_fingerprint: "f", rationale: "same well", decided_by: null, decided_at: null, decision_note: null,
      created_at: "2026-11-02T08:00:00Z", target: member("15/9-F-12", "target"),
      members: [member("F-12", "member", [{ document_id: "d1", quote: "Well F-12 is the same well as 15/9-F-12", content_sha256: "s" }])],
      guard_results: [{ code: "g1_scope", passed: true, detail: "same project" }],
    };
    await route.fulfill({ json: { items: [body], total: 1 } });
  });
  await page.route(/\/api\/v1\/projects\/[^/]+\/merge-proposals\/p1\/(accept|reject|revert)$/, async (route) => {
    const action = /(accept|reject|revert)$/.exec(route.request().url())![1];
    posts.push(action);
    status = action === "accept" ? "accepted" : action === "revert" ? "reverted" : "rejected";
    await route.fulfill({ json: {} });
  });

  const name = unique("MergeReview");
  await page.goto("/");
  await createProject(page, name, "merge review e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByLabel("Choose files").setInputFiles([{ name: "notes.csv", mimeType: "text/csv", buffer: Buffer.from("a,b\n1,2\n") }]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Import accepted: 1 new file/ })).toBeVisible();
  await page.reload();
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await page.getByRole("button", { name: "Reconstruction" }).click();

  const list = page.getByRole("list", { name: "To review name matches" });
  await expect(list).toContainText("F-12 → 15/9-F-12");
  await expect(list).toContainText("Well F-12 is the same well as 15/9-F-12");
  expect(posts).toEqual([]);

  const accept = page.getByRole("button", { name: "Accept F-12 → 15/9-F-12" });
  await accept.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Merged name matches" })).toBeVisible();

  const revert = page.getByRole("button", { name: "Revert F-12 → 15/9-F-12" });
  await revert.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("list", { name: "Reverted name matches" })).toBeVisible();
  expect(posts).toEqual(["accept", "revert"]);
});
