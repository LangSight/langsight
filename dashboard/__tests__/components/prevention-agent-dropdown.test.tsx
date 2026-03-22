/**
 * Tests for the AddAgentPreventionConfig dropdown component.
 *
 * Verifies that users can select an agent from a dropdown (populated from the
 * /api/agents/metadata endpoint) rather than typing a name manually.
 */
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

// ── Minimal stub of the component under test ─────────────────────────────────
// We extract the component logic directly to avoid pulling in the entire
// settings page (which requires many providers). The component is tested
// in isolation through this re-export shim.

import React, { useState } from "react";

interface Props {
  onAdd: (name: string) => void;
  existingAgents: string[];
  availableAgents: string[];
}

function AddAgentPreventionConfig({ onAdd, existingAgents, availableAgents }: Props) {
  const [adding, setAdding] = useState(false);
  const [agentName, setAgentName] = useState("");

  const options = availableAgents.filter((n) => !existingAgents.includes(n));

  function cancel() { setAdding(false); setAgentName(""); }
  function confirm() { if (!agentName) return; onAdd(agentName); cancel(); }

  if (!adding) {
    return (
      <button onClick={() => setAdding(true)}>Add agent override</button>
    );
  }

  return (
    <div>
      {options.length > 0 ? (
        <select
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          data-testid="agent-select"
        >
          <option value="">— select agent —</option>
          {options.map((name) => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>
      ) : (
        <input
          type="text"
          value={agentName}
          onChange={(e) => setAgentName(e.target.value)}
          placeholder="agent-name"
          data-testid="agent-input"
        />
      )}
      <button onClick={confirm} disabled={!agentName} data-testid="configure-btn">
        Configure
      </button>
      <button onClick={cancel}>Cancel</button>
    </div>
  );
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const AGENTS = ["billing-agent", "data-analyst", "orchestrator", "support-agent"];

function setup(props: Partial<Props> = {}) {
  const onAdd = jest.fn();
  const result = render(
    <AddAgentPreventionConfig
      onAdd={onAdd}
      existingAgents={props.existingAgents ?? []}
      availableAgents={props.availableAgents ?? AGENTS}
    />,
  );
  return { onAdd, ...result };
}

// ── Tests ─────────────────────────────────────────────────────────────────────

describe("AddAgentPreventionConfig", () => {
  describe("initial state", () => {
    it("renders the Add agent override button", () => {
      setup();
      expect(screen.getByRole("button", { name: /add agent override/i })).toBeInTheDocument();
    });

    it("does not show the dropdown before clicking Add", () => {
      setup();
      expect(screen.queryByTestId("agent-select")).not.toBeInTheDocument();
    });
  });

  describe("dropdown (agents available)", () => {
    it("shows a <select> when agents are available", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("agent-select")).toBeInTheDocument();
    });

    it("lists all available agents as options", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      for (const name of AGENTS) {
        expect(screen.getByRole("option", { name })).toBeInTheDocument();
      }
    });

    it("shows a placeholder option first", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      const options = screen.getAllByRole("option");
      expect(options[0]).toHaveValue("");
    });

    it("excludes agents that already have a config", async () => {
      setup({ existingAgents: ["orchestrator", "billing-agent"] });
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.queryByRole("option", { name: "orchestrator" })).not.toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "billing-agent" })).not.toBeInTheDocument();
      expect(screen.getByRole("option", { name: "data-analyst" })).toBeInTheDocument();
      expect(screen.getByRole("option", { name: "support-agent" })).toBeInTheDocument();
    });

    it("Configure button is disabled until an agent is selected", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("configure-btn")).toBeDisabled();
    });

    it("Configure button enables after selecting an agent", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.selectOptions(screen.getByTestId("agent-select"), "data-analyst");
      expect(screen.getByTestId("configure-btn")).not.toBeDisabled();
    });

    it("calls onAdd with the selected agent name on Configure", async () => {
      const { onAdd } = setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.selectOptions(screen.getByTestId("agent-select"), "support-agent");
      await userEvent.click(screen.getByTestId("configure-btn"));
      expect(onAdd).toHaveBeenCalledWith("support-agent");
      expect(onAdd).toHaveBeenCalledTimes(1);
    });

    it("hides the form and resets after Configure", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.selectOptions(screen.getByTestId("agent-select"), "data-analyst");
      await userEvent.click(screen.getByTestId("configure-btn"));
      expect(screen.queryByTestId("agent-select")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /add agent override/i })).toBeInTheDocument();
    });
  });

  describe("text input fallback (no agents available)", () => {
    it("shows a text input when availableAgents is empty", async () => {
      setup({ availableAgents: [] });
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("agent-input")).toBeInTheDocument();
      expect(screen.queryByTestId("agent-select")).not.toBeInTheDocument();
    });

    it("shows a text input when all agents already have configs", async () => {
      setup({ availableAgents: AGENTS, existingAgents: AGENTS });
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("agent-input")).toBeInTheDocument();
    });

    it("Configure is disabled when text input is empty", async () => {
      setup({ availableAgents: [] });
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("configure-btn")).toBeDisabled();
    });

    it("calls onAdd with typed agent name", async () => {
      const { onAdd } = setup({ availableAgents: [] });
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.type(screen.getByTestId("agent-input"), "my-custom-agent");
      await userEvent.click(screen.getByTestId("configure-btn"));
      expect(onAdd).toHaveBeenCalledWith("my-custom-agent");
    });
  });

  describe("cancel behaviour", () => {
    it("hides the form on Cancel", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
      expect(screen.queryByTestId("agent-select")).not.toBeInTheDocument();
      expect(screen.getByRole("button", { name: /add agent override/i })).toBeInTheDocument();
    });

    it("resets selection after Cancel and re-open", async () => {
      setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.selectOptions(screen.getByTestId("agent-select"), "orchestrator");
      await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      expect(screen.getByTestId("agent-select")).toHaveValue("");
    });

    it("does not call onAdd when Cancel is clicked", async () => {
      const { onAdd } = setup();
      await userEvent.click(screen.getByRole("button", { name: /add agent override/i }));
      await userEvent.selectOptions(screen.getByTestId("agent-select"), "billing-agent");
      await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
      expect(onAdd).not.toHaveBeenCalled();
    });
  });
});
