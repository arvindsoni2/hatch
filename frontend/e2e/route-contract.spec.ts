import { expect, test } from "@playwright/test";

test("legacy applications bookmarks redirect without losing query parameters", async ({
  page,
}) => {
  await page.goto("/jobs");
  await page.goto(
    "/applications?status=applied&status=interview&query=platform%20engineer",
  );

  await expect(page).toHaveURL(
    /\/tracker\?status=applied&status=interview&query=platform(\+|%20)engineer$/,
  );

  await page.goBack();
  await expect(page).toHaveURL(/\/jobs$/);

  await page.goForward();
  await expect(page).toHaveURL(
    /\/tracker\?status=applied&status=interview&query=platform(\+|%20)engineer$/,
  );
});
