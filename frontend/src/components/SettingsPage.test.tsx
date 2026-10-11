import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "../api";
import { provider, settings } from "../test-fixtures";
import SettingsPage from "./SettingsPage";

vi.mock("../api", async () => {
  const real = await vi.importActual<typeof import("../api")>("../api");
  return { ...real, api: { saveSettings: vi.fn(), listModels: vi.fn(), setupChecks: vi.fn(), revealConfig: vi.fn() } };
});

beforeEach(() => {
  vi.mocked(api.setupChecks).mockResolvedValue([
    { name: "ffmpeg libass", ok: true, fix: "x" },
    { name: "Montserrat font", ok: false, fix: "Missing assets/fonts/Montserrat-Black.ttf." },
  ]);
});

const radio = (name: RegExp) => screen.getByRole("radio", { name });

describe("SettingsPage", () => {
  it("lists every provider with its logo, as one radio group with the one in use picked", async () => {
    const { container } = render(<SettingsPage settings={settings()} onSaved={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Settings" })).toBeInTheDocument();
    expect(container.querySelector(".settings-page > h2 + section")).not.toBeNull();   // no blurb under the title
    const group = screen.getByRole("radiogroup", { name: "AI provider" });
    expect(within(group).getAllByRole("radio").map((r) => (r as HTMLInputElement).value))
      .toEqual(["anthropic", "openai", "ollama"]);
    expect(within(group).getAllByRole("radio").filter((r) => (r as HTMLInputElement).checked)).toHaveLength(1);
    expect(radio(/Anthropic/)).toBeChecked();
    expect(group.querySelectorAll("svg.provider-logo")).toHaveLength(3);
    expect(radio(/Anthropic/).closest("label")).toHaveTextContent("In use");
    expect(radio(/OpenAI/).closest("label")).toHaveTextContent("No key yet");
    expect(radio(/Ollama/).closest("label")).toHaveTextContent("No key needed");
    await screen.findByText("Montserrat font");
  });

  it("picking another provider shows its own key field; only one is ever picked", async () => {
    render(<SettingsPage settings={settings()} onSaved={vi.fn()} />);
    expect(screen.getByRole("form", { name: "Anthropic settings" })).toHaveTextContent("A key is saved (ends in abcd)");
    await userEvent.click(radio(/OpenAI/));
    expect(radio(/OpenAI/)).toBeChecked();
    expect(radio(/Anthropic/)).not.toBeChecked();
    const form = screen.getByRole("form", { name: "OpenAI settings" });
    expect(within(form).getByRole("link", { name: "Get a key" })).toHaveAttribute("href", "https://platform.openai.com/api-keys");
    expect(within(form).getByRole("button", { name: "Use OpenAI" })).toBeDisabled();     // no key, no model
    await userEvent.click(radio(/Ollama/));
    expect(radio(/Ollama/).closest("label")).toHaveTextContent("No key needed");
    expect(screen.queryByLabelText("API key")).toBeNull();
  });

  it("checking a key lists its models, and saving sends the key once and makes the provider the one in use", async () => {
    vi.mocked(api.listModels).mockResolvedValue({ models: ["gpt-a", "gpt-b"] });
    const saved = settings({ provider: "openai", using: "openai",
      providers: [provider({ has_key: true, ready: true, key_source: "saved" }),
                  provider({ id: "openai", name: "OpenAI", has_key: true, ready: true, key_source: "saved", key_hint: "6789", model: "gpt-b" })] });
    vi.mocked(api.saveSettings).mockResolvedValue(saved);
    const onSaved = vi.fn();
    render(<SettingsPage settings={settings()} onSaved={onSaved} />);
    await userEvent.click(radio(/OpenAI/));
    const form = within(screen.getByRole("form", { name: "OpenAI settings" }));
    expect(form.getByRole("button", { name: "Check key & list models" })).toBeDisabled();
    await userEvent.type(form.getByLabelText(/API key/), " sk-openai-123 ");
    expect(form.getByLabelText(/API key/)).toHaveAttribute("type", "password");
    await userEvent.click(form.getByRole("button", { name: "Check key & list models" }));
    expect(api.listModels).toHaveBeenCalledWith("openai", "sk-openai-123");
    expect(await form.findByText("The key works: 2 models to choose from.")).toBeInTheDocument();
    await userEvent.selectOptions(form.getByLabelText(/Model/), "gpt-b");
    await userEvent.click(form.getByRole("button", { name: "Use OpenAI" }));
    expect(api.saveSettings).toHaveBeenCalledWith({ provider: "openai", model: "gpt-b", api_key: "sk-openai-123" });
    await waitFor(() => expect(onSaved).toHaveBeenCalledWith(saved));
    expect(form.getByLabelText(/API key/)).toHaveValue("");
    expect(form.getByText(/Clipper now picks moments with OpenAI/)).toBeInTheDocument();
  });

  it("a key that is already saved isn't sent again, and a wrong key says so", async () => {
    vi.mocked(api.saveSettings).mockResolvedValue(settings());
    vi.mocked(api.listModels).mockRejectedValue(new ApiError(400, "Anthropic didn't accept that API key."));
    render(<SettingsPage settings={settings()} onSaved={vi.fn()} />);
    const form = within(screen.getByRole("form", { name: "Anthropic settings" }));
    await userEvent.click(form.getByRole("button", { name: "Check key & list models" }));
    expect(api.listModels).toHaveBeenCalledWith("anthropic", undefined);
    expect(await form.findByText("Anthropic didn't accept that API key.")).toBeInTheDocument();
    await userEvent.click(form.getByRole("button", { name: "Use Anthropic" }));     // model is optional here
    expect(api.saveSettings).toHaveBeenCalledWith({ provider: "anthropic", model: "" });
  });

  it("as first-run setup it says so, shows what this computer is missing, and offers Done once ready", async () => {
    const { rerender } = render(<SettingsPage settings={settings({}, false)} setup onSaved={vi.fn()} />);
    expect(screen.getByRole("heading", { name: "Set up Clipper" })).toBeInTheDocument();
    expect(radio(/Anthropic/).closest("label")).toHaveTextContent("No key yet");
    expect(screen.queryByRole("link", { name: "Done" })).toBeNull();
    const checks = screen.getByRole("region", { name: "This computer" });
    expect(await within(checks).findByText("Missing assets/fonts/Montserrat-Black.ttf.")).toBeInTheDocument();
    expect(within(checks).queryByText("Everything Clipper needs is installed.")).toBeNull();
    vi.mocked(api.setupChecks).mockResolvedValue([{ name: "ffmpeg libass", ok: true, fix: "x" }]);
    await userEvent.click(within(checks).getByRole("button", { name: "Check again" }));
    expect(await within(checks).findByText("Everything Clipper needs is installed.")).toBeInTheDocument();
    rerender(<SettingsPage settings={settings()} setup onSaved={vi.fn()} />);
    expect(screen.getByRole("link", { name: "Done" })).toHaveAttribute("href", "#/");
  });

  it("shows a skeleton until the settings load", () => {
    const { container } = render(<SettingsPage settings={null} onSaved={vi.fn()} />);
    expect(container.querySelector(".skeleton")).not.toBeNull();
    expect(screen.queryByRole("radiogroup")).toBeNull();
  });
});
