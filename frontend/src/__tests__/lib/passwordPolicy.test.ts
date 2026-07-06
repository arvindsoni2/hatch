import { describe, expect, it } from "vitest";
import {
  checkPassword,
  isPasswordValid,
  passwordError,
} from "@/lib/passwordPolicy";

describe("app-lock password policy", () => {
  it.each([
    "abc123",
    "letters-only-password",
    "123456789012",
    " valid-password-1",
    "valid-password-1 ",
  ])("rejects %j", (password) => {
    expect(isPasswordValid(password)).toBe(false);
    expect(passwordError(password)).toBeTruthy();
  });

  it("accepts a practical local password", () => {
    expect(isPasswordValid("valid-password-1")).toBe(true);
    expect(Object.values(checkPassword("valid-password-1")).every(Boolean)).toBe(true);
  });
});
