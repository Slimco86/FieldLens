// TASK-055 AC-10 (implementer evidence, not independent acceptance): an uploaded PDF that no native
// profile reads is shown as "No native parser; model processing available"; Process goes through the
// existing estimate -> confirm flow against the real API (stub provider, no model call, no Meta).
//
// Boundary: the default e2e API runs the stub step, which reads pages and stores no model-read result
// (the model step is only wired by configuration/injection, and live Meta is never called here). So the
// model_read half of the flow is shown by rewriting the real GET /processing/documents response in the
// browser to carry a model_read after the real run is processed; everything else is the real API.
import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";
import { blockExternal, createProject, unique } from "./project-support";

test.beforeEach(async ({ page }) => blockExternal(page));
test.setTimeout(120_000);

/** Minimal valid two-page PDF with a correct xref table. */
function pdf(): Buffer {
  const objs = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 5 0 R /Resources << /Font << /F1 6 0 R >> >> >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 300 200] /Contents 7 0 R /Resources << /Font << /F1 6 0 R >> >> >>",
    "<< /Length 52 >>\nstream\nBT /F1 12 Tf 20 100 Td (Completion report) Tj ET\nendstream",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    "<< /Length 58 >>\nstream\nBT /F1 12 Tf 20 100 Td (Wellbore: NO 15/9-F-12 H) Tj ET\nendstream",
  ];
  let out = "%PDF-1.4\n";
  const offsets: number[] = [];
  objs.forEach((o, i) => {
    offsets.push(out.length);
    out += `${i + 1} 0 obj\n${o}\nendobj\n`;
  });
  const xref = out.length;
  out += `xref\n0 ${objs.length + 1}\n0000000000 65535 f \n`;
  for (const o of offsets) out += `${String(o).padStart(10, "0")} 00000 n \n`;
  out += `trailer\n<< /Size ${objs.length + 1} /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  return Buffer.from(out, "latin1");
}

async function openWithPdf(page: Page, name: string) {
  await page.goto("/");
  await createProject(page, name, "model processing e2e");
  await page.getByRole("button", { name: `Open project ${name}` }).click();
  await expect(page.getByRole("heading", { name })).toBeVisible();
  await page.getByLabel("Choose files").setInputFiles([{ name: "completion.pdf", mimeType: "application/pdf", buffer: pdf() }]);
  await page.getByRole("button", { name: "Upload 1 file(s)" }).click();
  await expect(page.getByRole("status").filter({ hasText: /Import accepted: 1 new file/ })).toBeVisible();
}

test("TASK-055: unsupported PDF -> Process -> estimate -> confirm -> model-read result with page and quote", async ({ page }) => {
  await openWithPdf(page, unique("ModelRead"));
  const inspect = page.getByRole("button", { name: /Inspect extraction for completion\.pdf/ });
  await expect(inspect).toBeVisible({ timeout: 30_000 });
  await inspect.click();

  // the dead end is gone: the section offers processing, and says nothing was started
  const section = page.getByRole("region", { name: /Model processing for completion\.pdf/ });
  await expect(section.getByText("No native parser; model processing available")).toBeVisible({ timeout: 60_000 });
  const process = section.getByRole("button", { name: /Process with model: completion\.pdf/ });
  await process.focus();
  await page.keyboard.press("Enter");

  // estimate: pages, tokens, USD and cap; nothing spent until Confirm
  const dialog = page.getByRole("dialog", { name: /Model processing estimate for completion\.pdf/ });
  await expect(dialog).toBeVisible();
  await expect(dialog.getByText(/This is an estimate only/)).toBeVisible();
  await expect(dialog.getByText("Pages to read")).toBeVisible();
  await expect(dialog.getByText(/input,.*output/)).toBeVisible();
  await expect(dialog.getByText(/USD [\d.]+ of USD 5(\.0+)? total cap/)).toBeVisible();
  const violations = (await new AxeBuilder({ page }).include('[role="dialog"]').analyze()).violations;
  expect(violations).toEqual([]);
  // Escape cancels without a run; the Process action is available again and focus returns to it
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(process).toBeFocused();

  await process.click();
  await page.getByRole("button", { name: /Confirm and start \(USD/ }).click();
  await expect(dialog).toBeHidden();
  const status = section.getByRole("status").filter({ hasText: /finished|queued|running/i });
  await expect(status).toBeVisible({ timeout: 60_000 });
  await expect(section.getByText("Processed", { exact: true })).toBeVisible({ timeout: 60_000 });
  // the stub step reads pages and stores no result: stated, not presented as a classification
  await expect(section.getByText(/This run stored no model-read result/)).toBeVisible();

  // the model_read result (see the boundary note at the top of this file)
  await page.route("**/processing/documents", async (route) => {
    const res = await route.fetch();
    const body = (await res.json()) as { items: Record<string, unknown>[] };
    body.items = body.items.map((i) => ({
      ...i,
      model_read: {
        document_id: i.document_id,
        run_id: i.last_run_id,
        category: "completion_equipment",
        unclassified: false,
        tags: ["completion report"],
        identities: [
          {
            proposal_id: "11111111-1111-4111-8111-111111111111",
            subject_kind: "wellbore",
            name_as_written: "NO 15/9-F-12 H",
            normalized_key: "15/9-F-12 H",
            page: 2,
            quote: "Wellbore: NO 15/9-F-12 H",
            status: "model_proposal",
            label: "Model-read, unverified",
            resolution: "unresolved",
            wellbore_id: null,
            wellbore_key: null,
          },
        ],
        warnings: [],
        pages: { page_start: 1, page_end: 2 },
        pages_read: 2,
        provider: "stub",
        model_revision: "e2e",
        prompt_version: "p1",
        schema_version: "s1",
        extraction_method: "model_classification",
        label: "Model-read, unverified",
        created_at: "2026-11-02T10:00:00Z",
      },
    }));
    await route.fulfill({ response: res, json: body });
  });
  await page.getByRole("button", { name: /Hide extraction for completion\.pdf/ }).click();
  await page.getByRole("button", { name: /Inspect extraction for completion\.pdf/ }).click();
  const result = page.getByLabel("Model-read result");
  await expect(result).toBeVisible({ timeout: 30_000 });
  await expect(result.getByText("Model-read, unverified").first()).toBeVisible();
  await expect(result.getByText("Completion equipment")).toBeVisible();
  await expect(result.getByText("Evidence on page 2:")).toBeVisible();
  await expect(result.getByText("Wellbore: NO 15/9-F-12 H")).toBeVisible();
  await expect(result.getByText(/Unresolved/)).toBeVisible();
  const a11y = (await new AxeBuilder({ page }).include('[aria-label="Model-read result"]').analyze()).violations;
  expect(a11y).toEqual([]);
});
