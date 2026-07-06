import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/ui/form-field";
import { Icon } from "@/components/ui/icon";
import { Input } from "@/components/ui/input";
import { PageContainer, PageHeader } from "@/components/ui/page-layout";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

describe("shared UI foundation", () => {
  it.each(["light", "dark"])("renders the shared page composition in %s mode", (theme) => {
    document.documentElement.setAttribute("data-theme", theme);
    render(
      <PageContainer>
        <PageHeader title="Profile" description="Manage your personal details." />
        <SectionCard title="Identity">
          <StatusBadge tone="success">Saved</StatusBadge>
        </SectionCard>
      </PageContainer>,
    );

    expect(screen.getByRole("heading", { level: 1, name: "Profile" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Identity" })).toBeInTheDocument();
    expect(screen.getByText("Saved")).toBeInTheDocument();
  });

  it("associates labels, descriptions, and errors with a field", () => {
    render(
      <FormField
        description="Use the address employers should contact."
        error="Enter a valid email address."
        id="contact-email"
        label="Email"
        required
      >
        <Input name="email" type="email" />
      </FormField>,
    );

    const input = screen.getByRole("textbox", { name: /email/i });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute(
      "aria-describedby",
      "contact-email-description contact-email-error",
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Enter a valid email address.");
  });

  it.each(["default", "destructive", "success", "outline", "secondary", "ghost"] as const)(
    "supports the %s button state",
    (variant) => {
      render(<Button variant={variant}>{variant}</Button>);
      expect(screen.getByRole("button", { name: variant })).toHaveClass("hatch-interactive");
    },
  );

  it("exposes loading and disabled button state", () => {
    render(<Button loading>Save profile</Button>);
    const button = screen.getByRole("button", { name: "Save profile" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
  });

  it("renders Lucide icons as decorative unless labelled", () => {
    const { rerender } = render(<Icon name="check" />);
    expect(document.querySelector("svg")).toHaveAttribute("aria-hidden", "true");

    rerender(<Icon label="Completed" name="check" />);
    expect(screen.getByLabelText("Completed")).toBeInTheDocument();
  });
});
