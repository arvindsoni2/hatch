import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";

describe("overlay primitives", () => {
  it("traps dialog focus, closes with Escape, and restores trigger focus", async () => {
    const user = userEvent.setup();
    render(
      <Dialog>
        <DialogTrigger>Open dialog</DialogTrigger>
        <DialogContent>
          <DialogTitle>Example dialog</DialogTitle>
          <DialogDescription>Dialog behavior test.</DialogDescription>
          <button type="button">First action</button>
          <button type="button">Last action</button>
        </DialogContent>
      </Dialog>,
    );

    const trigger = screen.getByRole("button", { name: "Open dialog" });
    await user.click(trigger);

    expect(screen.getByRole("dialog", { name: "Example dialog" })).toBeVisible();
    expect(screen.getByRole("button", { name: "First action" })).toHaveFocus();

    await user.tab();
    expect(screen.getByRole("button", { name: "Last action" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Close dialog" })).toHaveFocus();
    await user.tab();
    expect(screen.getByRole("button", { name: "First action" })).toHaveFocus();

    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("keeps a protected dialog open while work is in progress", async () => {
    const user = userEvent.setup();
    render(
      <Dialog defaultOpen>
        <DialogContent preventClose>
          <DialogTitle>Saving changes</DialogTitle>
          <DialogDescription>Please wait.</DialogDescription>
        </DialogContent>
      </Dialog>,
    );

    await user.keyboard("{Escape}");
    expect(screen.getByRole("dialog", { name: "Saving changes" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Close dialog" })).toBeDisabled();
  });

  it("gives destructive confirmation an explicit cancel path", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    render(
      <AlertDialog>
        <AlertDialogTrigger>Delete item</AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogTitle>Delete item?</AlertDialogTitle>
          <AlertDialogDescription>This cannot be undone.</AlertDialogDescription>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={onConfirm}>Delete</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>,
    );

    const trigger = screen.getByRole("button", { name: "Delete item" });
    await user.click(trigger);
    expect(screen.getByRole("alertdialog", { name: "Delete item?" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await user.click(screen.getByRole("button", { name: "Delete" }));
    expect(onConfirm).toHaveBeenCalledOnce();
    expect(trigger).toHaveFocus();
  });

  it("restores focus when a sheet closes", async () => {
    const user = userEvent.setup();
    render(
      <Sheet>
        <SheetTrigger>Open panel</SheetTrigger>
        <SheetContent>
          <SheetTitle>Application details</SheetTitle>
          <SheetDescription>Review this application.</SheetDescription>
        </SheetContent>
      </Sheet>,
    );

    const trigger = screen.getByRole("button", { name: "Open panel" });
    await user.click(trigger);
    expect(screen.getByRole("dialog", { name: "Application details" })).toBeVisible();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
  });

  it("keeps the parent sheet active when a nested dialog closes", async () => {
    const user = userEvent.setup();
    render(
      <Sheet defaultOpen>
        <SheetContent>
          <SheetTitle>Application details</SheetTitle>
          <SheetDescription>Review this application.</SheetDescription>
          <Dialog>
            <DialogTrigger>Preview email</DialogTrigger>
            <DialogContent>
              <DialogTitle>Email preview</DialogTitle>
              <DialogDescription>Review the message before copying it.</DialogDescription>
            </DialogContent>
          </Dialog>
        </SheetContent>
      </Sheet>,
    );

    const nestedTrigger = screen.getByRole("button", { name: "Preview email" });
    await user.click(nestedTrigger);
    expect(screen.getByRole("dialog", { name: "Email preview" })).toBeVisible();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Email preview" })).not.toBeInTheDocument();
    expect(screen.getByRole("dialog", { name: "Application details" })).toBeVisible();
    expect(nestedTrigger).toHaveFocus();
  });

  it("closes a popover with Escape and returns focus to its trigger", async () => {
    const user = userEvent.setup();
    render(
      <Popover>
        <PopoverTrigger>Open menu</PopoverTrigger>
        <PopoverContent aria-label="Example menu">
          <button type="button">Menu action</button>
        </PopoverContent>
      </Popover>,
    );

    const trigger = screen.getByRole("button", { name: "Open menu" });
    await user.click(trigger);
    expect(screen.getByLabelText("Example menu")).toBeVisible();
    await user.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByLabelText("Example menu")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });
});
