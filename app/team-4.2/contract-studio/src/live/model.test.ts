import { test } from "node:test";
import assert from "node:assert/strict";
import {
  emptyScenario,
  applyEvent,
  applyGraph,
  particlesFor,
  choreographyFor,
} from "./model";

test("no graph, candidates or findings are invented for a new upload", () => {
  const s = emptyScenario();
  assert.deepEqual(s.graphModel, { nodes: [], edges: [] });
  assert.deepEqual(particlesFor(s), []);
  assert.equal(choreographyFor(s, 0).visibleLegalCount, 0);
});

test("a particle is created per actual candidate, unknown is never excluded", () => {
  let s = applyEvent(emptyScenario(), {
    type: "legal_candidate",
    concept_id: "c",
    pid: "p",
  });
  assert.equal(particlesFor(s).length, 1);
  assert.equal(particlesFor(s)[0].filteredAtMs, Infinity);
  s = applyEvent(s, {
    type: "legal_resolution",
    concept_id: "c",
    pid: "p",
    decision: "unknown",
    provision: null,
  });
  assert.equal(particlesFor(s)[0].group, "unknown");
  assert.equal(choreographyFor(s, 5).droppedParticleCount, 0);
  assert.deepEqual(s.legalVersions, []);
});

test("graph projection preserves the real edge direction and node IDs", () => {
  const s = applyGraph(emptyScenario(), {
    nodes: [
      { node_id: "c", node_type: "Contract" },
      { node_id: "u", node_type: "Unit", uid: "p0.d1" },
    ],
    edges: [{ type: "EVIDENCE", src: "f", dst: "u", props: {} }],
  });
  assert.equal(s.graphModel!.edges[0].from, "f");
  assert.equal(s.graphModel!.edges[0].to, "u");
  assert.equal(s.graphModel!.nodes[1].id, "u");
});

test("an available version is rendered from the returned citation only", () => {
  const s = applyEvent(emptyScenario(), {
    type: "legal_resolution",
    concept_id: "c",
    pid: "p",
    decision: "kept",
    provision: {
      in_force: true,
      text: "Exact text",
      citation: {
        provision_id: "p",
        version_id: "v",
        valid_from: "2025-01-01",
        valid_to: "2026-01-01",
      },
    },
  });
  assert.equal(s.legalNodes[0].id, "v");
  assert.equal(s.legalVersions.length, 1);
  assert.equal(s.legalVersions[0].effectiveTo, "2026-01-01");
});
