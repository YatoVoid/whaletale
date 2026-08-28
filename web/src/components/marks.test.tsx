import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnomalyMark, DegradedMark, VacantTag } from "./marks";

describe("state marks", () => {
  it("vacancy reads as a labelled state, not a blank", () => {
    render(<VacantTag />);
    expect(screen.getByText("vacant")).toBeInTheDocument();
  });

  it("anomaly mark carries its label", () => {
    render(<AnomalyMark />);
    expect(screen.getByText("anomalous")).toBeInTheDocument();
  });

  it("degraded mark renders nothing when there is nothing to flag", () => {
    const { container } = render(<DegradedMark count={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("degraded mark counts fallback buckets", () => {
    render(<DegradedMark count={3} />);
    expect(screen.getByText("3 degraded")).toBeInTheDocument();
  });
});
