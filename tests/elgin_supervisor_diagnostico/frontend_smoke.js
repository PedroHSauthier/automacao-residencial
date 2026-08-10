"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const listeners = new Map();
global.document = {
  addEventListener(type, listener) {
    if (!listeners.has(type)) listeners.set(type, new Set());
    listeners.get(type).add(listener);
  },
  removeEventListener(type, listener) {
    listeners.get(type)?.delete(listener);
  },
  createDocumentFragment() {
    return { children: [], append(...items) { this.children.push(...items); } };
  },
  createElement(tagName) {
    return {
      tagName,
      className: "",
      dataset: {},
      children: [],
      append(...items) { this.children.push(...items); },
    };
  },
};
global.window = { customCards: [] };
global.CustomEvent = class CustomEvent {
  constructor(type, options = {}) {
    this.type = type;
    Object.assign(this, options);
  }
};
global.HTMLElement = class HTMLElement {
  matches() { return false; }
};
const registry = new Map();
global.customElements = {
  get(name) { return registry.get(name); },
  define(name, value) { registry.set(name, value); },
};

const cardPath = process.argv[2];
const source = fs.readFileSync(cardPath, "utf8");
const closing = source.lastIndexOf("})();");
assert.notEqual(closing, -1, "IIFE do card não encontrada");
const instrumented = `${source.slice(0, closing)}globalThis.__elginSmoke = { ElginDiagnosticMultiselect, ElginSupervisorDiagnosticoCard, presentationValue };\n${source.slice(closing)}`;
vm.runInThisContext(instrumented, { filename: cardPath });

const { ElginDiagnosticMultiselect, ElginSupervisorDiagnosticoCard, presentationValue } = global.__elginSmoke;

const picker = new ElginDiagnosticMultiselect();
const otherPicker = new ElginDiagnosticMultiselect();
let focusRestored = false;
picker._details = { open: true };
picker._summary = { focus() { focusRestored = true; } };
picker._onDocumentPointerDown({ composedPath: () => [picker] });
assert.equal(picker._details.open, true, "clique interno não deve fechar o picker");
picker._onPickerOpened({ detail: { picker: otherPicker } });
assert.equal(picker._details.open, false, "abrir outro picker deve fechar o anterior");

picker._details.open = true;
picker._onDocumentPointerDown({ composedPath: () => [] });
assert.equal(picker._details.open, false, "clique externo deve fechar o picker");
picker._details.open = true;
picker._onDocumentFocusIn({ composedPath: () => [] });
assert.equal(picker._details.open, false, "retirar foco com Tab deve fechar o picker");
picker._details.open = true;
picker._onDocumentKeyDown({ key: "Escape", preventDefault() {} });
assert.equal(picker._details.open, false, "Escape deve fechar o picker");
assert.equal(focusRestored, true, "Escape deve devolver o foco ao campo");

picker._connectGlobalListeners();
assert.equal(picker._listenersConnected, true);
picker.disconnectedCallback();
assert.equal(picker._listenersConnected, false, "disconnect deve remover listeners globais");
for (const registered of listeners.values()) assert.equal(registered.size, 0);

assert.equal(presentationValue("severity", "debug"), "Rotina");
assert.equal(presentationValue("mode", "cool"), "Refrigeração");
assert.equal(presentationValue("mode", "cool", true), "Refrigeração · cool");
assert.equal(presentationValue("power_profile", "1"), "Não informado");
assert.equal(presentationValue("power_profile", true), "Não informado");
assert.equal(presentationValue("power_level", 2), "Nível 2");

const makeNode = () => ({
  hidden: false,
  dataset: {},
  textContent: "",
  children: [],
  replaceChildren(...items) { this.children = items; },
});
const flowNode = makeNode();
const titleNode = makeNode();
const metaNode = makeNode();
const missingNode = makeNode();
const correlationNode = makeNode();
const nodes = new Map([
  ["#last-flow", flowNode],
  ["#last-flow-title", titleNode],
  ["#last-flow-meta", metaNode],
  ["#last-flow-missing", missingNode],
  ["#last-flow-correlation", correlationNode],
]);
const card = new ElginSupervisorDiagnosticoCard();
card.shadowRoot = { querySelector(selector) { return nodes.get(selector) || null; } };
card._renderMaintenance = () => {};
card._snapshot = { last_complete_flow: { terminal: false, steps: [], missing_phases: [] } };
card._renderOverview();
assert.equal(titleNode.textContent, "Último fluxo observado");
assert.equal(flowNode.children[0].children[0].className, "flow-empty");

card._snapshot = {
  last_complete_flow: {
    terminal: true,
    state: "complete",
    correlation_id: "corr-1",
    occurred_at: "2026-08-09T12:00:00Z",
    steps: [{
      phase: "result",
      phase_label: "Resultado observado",
      event_id: "event-1",
      event_type: "localtuya.confirmed_full_state",
      summary: "LocalTuya confirmou o estado completo.",
      outcome: "confirmed_by_localtuya",
    }],
    missing_phases: ["Gatilho recebido"],
  },
};
card._renderOverview();
assert.equal(titleNode.textContent, "Último fluxo completo");
assert.equal(correlationNode.dataset.flowCorrelation, "corr-1");
assert.equal(missingNode.hidden, false);
assert.match(missingNode.textContent, /Não registradas/);
assert.equal(flowNode.children[0].children[0].dataset.eventId, "event-1");

console.log("frontend smoke: ok");
