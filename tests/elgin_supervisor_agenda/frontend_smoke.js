"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const registered = new Map();
vm.runInNewContext(fs.readFileSync(path.join(__dirname, "../../custom_components/elgin_supervisor_agenda/frontend/elgin-supervisor-agenda-card.js"), "utf8"), {
  HTMLElement: class {},
  customElements: { get: (name) => registered.get(name), define: (name, value) => registered.set(name, value) },
  window: {}, console: { info() {} }, Date, setInterval, clearInterval,
});
const Card = registered.get("elgin-supervisor-presets-power-card");

function editor(preset) {
  const fields = new Map();
  const body = {
    set innerHTML(html) {
      for (const match of html.matchAll(/<(select|textarea|span|button)\b([^>]*\bid="([^"]+)"[^>]*)>([\s\S]*?)<\/\1>/g)) {
        const [, tag, attrs, id, content] = match;
        const selected = tag === "select" && (content.match(/<option value="([^"]+)"[^>]*\bselected/) || content.match(/<option value="([^"]+)"/));
        fields.set(`#${id}`, {
          value: selected ? selected[1] : attrs.match(/\bvalue="([^"]*)"/)?.[1] || "",
          disabled: /\bdisabled\b/.test(attrs), step: attrs.match(/\bstep="([^"]+)"/)?.[1],
          handlers: {}, addEventListener(type, handler) { this.handlers[type] = handler; }, reportValidity() { return true; },
        });
      }
      // Void inputs need their own scan: they have no closing tag.
      for (const match of html.matchAll(/<input\b([^>]*\bid="([^"]+)"[^>]*)>/g)) {
        const [, attrs, id] = match;
        fields.set(`#${id}`, { value: attrs.match(/\bvalue="([^"]*)"/)?.[1] || "", disabled: false, step: attrs.match(/\bstep="([^"]+)"/)?.[1], reportValidity() { return true; } });
      }
      fields.set(".dry-field", {});
    },
    querySelector: (selector) => fields.get(selector),
    querySelectorAll: () => [...fields.values()].filter((field) => field.reportValidity),
  };
  const dialog = { open: false, showModal() { this.open = true; }, close() { this.open = false; } };
  const card = new Card();
  card.activeMode = "cool";
  card.querySelector = (selector) => selector === "#unified-editor-body" ? body : selector === "#unified-editor[open]" ? (dialog.open ? dialog : null) : selector === "#unified-editor" ? dialog : null;
  card.querySelectorAll = () => [];
  card.load = async () => {};
  card.ws = async (type, payload) => { card.saved = { type, payload }; };
  card.openPresetEditor(preset);
  return { card, body, dialog, fields };
}

async function main() {
  const base = { id: "cool_test", name: "Teste", mode: "cool", level: 0, start: 26, stop: 23, power_modifier: 0, enabled: true, proximity: { enabled: true, temperature_margin: 0.5, humidity_margin: 7, minutes: 10 } };
  const { card, fields, dialog } = editor(base);
  assert.equal(dialog.open, true);
  assert.equal(fields.get("#e-proximity-temperature").disabled, false);
  assert.equal(fields.get("#e-proximity-humidity").disabled, true);
  assert.equal(fields.get("#e-start").step, "0.1");
  fields.get("#e-proximity-temperature").value = "0.7";
  card.innerHTML = "unsaved editor";
  card.render();
  assert.equal(card.innerHTML, "unsaved editor", "incoming snapshot must preserve an open editor");
  await fields.get("#save-editor").handlers.click();
  assert.equal(card.saved.type, "save_preset");
  assert.deepEqual(JSON.parse(JSON.stringify(card.saved.payload.preset.proximity)), { enabled: true, temperature_margin: 0.7, humidity_margin: 7, minutes: 10 });

  const dry = editor({ ...base, id: undefined });
  dry.fields.get("#e-mode").value = "dry";
  dry.fields.get("#e-mode").handlers.change();
  assert.equal(dry.fields.get("#e-start").step, "1");
  assert.equal(dry.fields.get("#e-stop").step, "1");
  assert.equal(dry.fields.get("#e-start").min, "30");
  assert.equal(dry.fields.get("#e-stop").min, "20");
  assert.equal(dry.fields.get("#e-proximity-temperature").disabled, true);
  assert.equal(dry.fields.get("#e-proximity-humidity").disabled, false);
  assert.equal(dry.fields.get("#e-min").disabled, false);
  dry.fields.get("#e-proximity-enabled").value = "false";
  dry.fields.get("#e-proximity-enabled").handlers.change();
  await dry.fields.get("#save-editor").handlers.click();
  assert.equal(dry.card.saved.payload.preset.proximity.enabled, false);
  assert.equal(dry.card.saved.payload.preset.proximity.temperature_margin, 0.5);
  assert.equal(dry.card.saved.payload.preset.proximity.humidity_margin, 7);
  assert.match(card.proximityStatus("cool", { proximity: base.proximity, proximity_state: { status: "outside" } }), /Fora da faixa/);
  assert.match(card.proximityStatus("cool", { proximity: base.proximity, proximity_state: { status: "invalid" } }), /Leitura ou configuração inválida/);
  console.log("Frontend proximity smoke: editor save, preserved inactive metric, mode steps, disable/re-enable settings and unsaved edits passed.");
}
main().catch((error) => { console.error(error); process.exitCode = 1; });
