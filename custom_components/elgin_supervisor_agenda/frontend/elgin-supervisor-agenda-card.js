(() => {
  "use strict";

  const DOMAIN = "elgin_supervisor_agenda";
  const POLICY_ENTITY = "sensor.elgin_supervisor_agenda_politica";
  const AGENDA_SWITCH = "switch.elgin_supervisor_agenda_habilitada";
  const REEVALUATE_BUTTON = "button.elgin_supervisor_agenda_reavaliar_agora";
  const CANCEL_BUTTON = "button.elgin_supervisor_agenda_cancelar_excecoes_unicas_ativas";
  const BUILD_TARGET = "agenda-pipeline-atomic-20260730.3";

  const PRESET_MANUAL_ADJUST_ENTITIES = {
    heat: "input_number.elgin_supervisor_ajuste_nivel_preset_aquecimento",
    cool: "input_number.elgin_supervisor_ajuste_nivel_preset_refrigeracao",
    dry: "input_number.elgin_supervisor_ajuste_nivel_preset_desumidificacao",
  };

  const POLICY_REACTIVE_ENTITIES = [
    AGENDA_SWITCH,
    "input_boolean.elgin_supervisor_habilitado",
    "input_boolean.elgin_supervisor_usar_clima_regional",
    "input_boolean.elgin_supervisor_usar_limites_automaticos",
    "input_boolean.elgin_supervisor_fisico_semiautomatico",
    "input_boolean.elgin_supervisor_respeitar_controle_manual",
    "input_boolean.elgin_supervisor_usar_eco",
    "input_boolean.elgin_aux_turbo",
    "input_boolean.elgin_aux_sleep",
    "input_boolean.elgin_aux_health",
    "input_boolean.elgin_aux_ifeel",
    "input_select.elgin_aux_fonte_temperatura",
    "input_number.elgin_supervisor_tempo_minimo_ligado",
    "input_number.elgin_supervisor_tempo_minimo_desligado",
    "input_number.elgin_supervisor_tempo_protecao_troca_modo",
    "input_number.elgin_supervisor_pausa_manual_minutos",
    "binary_sensor.elgin_supervisor_clima_regional_efetivo",
    "binary_sensor.elgin_supervisor_limites_automaticos_efetivos",
    "binary_sensor.elgin_supervisor_fisico_semiautomatico_efetivo",
    "binary_sensor.elgin_supervisor_respeitar_controle_manual_efetivo",
    "binary_sensor.elgin_supervisor_eco_efetivo",
    "binary_sensor.elgin_supervisor_turbo_efetivo",
    "binary_sensor.elgin_supervisor_sleep_efetivo",
    "binary_sensor.elgin_supervisor_health_efetivo",
    "binary_sensor.elgin_supervisor_ifeel_efetivo",
    "binary_sensor.elgin_supervisor_operacao_efetivamente_autorizada",
    "sensor.elgin_supervisor_fonte_ifeel_efetiva",
    "sensor.elgin_supervisor_tempos_efetivos",
    "sensor.elgin_supervisor_funcoes_avancadas_efetivas",
    "sensor.elgin_supervisor_politica_temporal_efetiva",
    "sensor.elgin_supervisor_presets_de_condicao",
    "select.elgin_supervisor_preset_base_aquecimento",
    "select.elgin_supervisor_preset_base_refrigeracao",
    "select.elgin_supervisor_preset_base_desumidificacao",
    "input_number.elgin_supervisor_ajuste_nivel_preset_aquecimento",
    "input_number.elgin_supervisor_ajuste_nivel_preset_refrigeracao",
    "input_number.elgin_supervisor_ajuste_nivel_preset_desumidificacao",
    "sensor.elgin_supervisor_potencias",
    "select.elgin_supervisor_potencia_base_aquecimento",
    "select.elgin_supervisor_potencia_base_refrigeracao",
    "select.elgin_supervisor_potencia_base_desumidificacao",
  ];

  const MODES = [
    ["heat", "Aquecimento", "mdi:radiator"],
    ["cool", "Refrigeração", "mdi:snowflake"],
    ["dry", "Desumidificação", "mdi:water-percent"],
  ];
  const MODE_LABELS = {};
  MODES.forEach(([id, label]) => { MODE_LABELS[id] = label; });
  const WEEKDAYS = ["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"];
  const MONTHS = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const MONTHS_LONG = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const RECURRENCE_LABELS = { once: "Uma vez", daily: "Diária", weekly: "Semanal", monthly: "Mensal", yearly: "Anual" };
  const GLOBAL_ACTION_LABELS = {
    normal: "Operação normal",
    suspend: "Suspender decisões",
    shadow: "Modo sombra",
    disable_supervisor: "Desativar Supervisor",
    power_off: "Desligar o ar",
    power_off_block: "Desligar e bloquear religamento",
  };

  const EFFECT_GROUPS = [
    ["operation", "Operação e modos"],
    ["power", "Potência, preset e prioridades"],
    ["comfort", "Conforto e condições"],
    ["advanced", "Funções avançadas"],
    ["protection", "Proteções e bloqueios"],
  ];

  const EFFECTS = {
    global_action: { label: "Ação global", category: "operation", scope: "global", kind: "select", help: "Normal mantém o Supervisor ativo; Suspender/Desativar não enviam comandos; Sombra calcula sem transmitir; Desligar atua uma vez; Desligar e bloquear mantém o ar desligado.", options: [
      ["normal", "Operação normal"], ["suspend", "Suspender decisões"], ["shadow", "Modo sombra"],
      ["disable_supervisor", "Desativar Supervisor"], ["power_off", "Desligar o ar"],
      ["power_off_block", "Desligar e bloquear religamento"],
    ]},
    enable_modes: { label: "Habilitar modos", category: "operation", scope: "mode", kind: "none", help: "Habilita os modos selecionados enquanto a regra estiver ativa." },
    disable_modes: { label: "Desabilitar modos", category: "operation", scope: "mode", kind: "none", help: "Desabilita os modos selecionados." },
    only_modes: { label: "Permitir somente os modos", category: "operation", scope: "mode", kind: "none", help: "Desabilita todos os modos não selecionados." },
    enable_all_modes: { label: "Habilitar todos os modos", category: "operation", scope: "global", kind: "none" },
    disable_all_modes: { label: "Desabilitar todos os modos", category: "operation", scope: "global", kind: "none" },

    power_delta: { label: "Ajustar potência em níveis", category: "power", scope: "mode", kind: "number", min: -10, max: 10, step: 1, help: "Soma ou reduz níveis sobre a potência calculada." },
    power_base: { label: "Forçar potência base", category: "power", scope: "mode", kind: "power", singleMode: true, help: "Substitui temporariamente a potência base apenas no modo selecionado." },
    power_force: { label: "Forçar potência", category: "power", scope: "mode", kind: "power" , singleMode: true },
    power_min: { label: "Potência mínima", category: "power", scope: "mode", kind: "power" , singleMode: true },
    power_max: { label: "Potência máxima", category: "power", scope: "mode", kind: "power" , singleMode: true },
    preset: { label: "Forçar preset base", category: "power", scope: "mode", kind: "preset", singleMode: true, help: "Seleciona um preset cadastrado exclusivamente para um modo. O identificador interno permanece estável mesmo que o nome seja alterado." },
    preset_level_delta: { label: "Ajustar nível do preset", category: "power", scope: "mode", kind: "number", min: -10, max: 10, step: 1, help: "Soma níveis ao preset base de cada modo. É separado do ajuste de potência." },
    priority_delta: { label: "Ajustar prioridade do modo", category: "power", scope: "mode", kind: "number", min: -100, max: 100, step: 1 },
    fan: { label: "Ventilação", category: "power", scope: "mode", kind: "select", options: [
      ["auto", "Automática"], ["low", "Baixa"], ["medium", "Média"], ["high", "Alta"], ["quiet", "Silenciosa (IR baixa)"],
    ]},
    swing: { label: "Swing", category: "power", scope: "mode", kind: "select", options: [
      ["auto", "Automático do Supervisor"], ["off", "Desligado"], ["vertical", "Vertical"], ["horizontal", "Horizontal"], ["both", "Ambos"],
    ]},

    regional: { label: "Clima regional", category: "comfort", scope: "global", kind: "tri" },
    limits_auto: { label: "Limites automáticos", category: "comfort", scope: "global", kind: "tri", help: "Só fica efetivo com clima regional válido." },
    physical_semiautomatic: { label: "Físico semi-automático", category: "comfort", scope: "global", kind: "tri" },
    respect_manual: { label: "Respeitar controle manual", category: "comfort", scope: "global", kind: "tri" },
    eco: { label: "Eco LocalTuya", category: "comfort", scope: "global", kind: "tri", help: "O comando Eco é emitido apenas em refrigeração." },
    start_offset: { label: "Offset do limite de início", category: "comfort", scope: "mode", allowedModes: ["heat", "cool"], kind: "number", min: -20, max: 20, step: 0.1, help: "Desloca o limite de temperatura que inicia Aquecimento ou Refrigeração." },
    stop_offset: { label: "Offset do limite de fim", category: "comfort", scope: "mode", allowedModes: ["heat", "cool"], kind: "number", min: -20, max: 20, step: 0.1, help: "Desloca o limite de temperatura que encerra Aquecimento ou Refrigeração." },
    dry_min_temperature_offset: { label: "Offset da mínima do Dry", category: "comfort", scope: "mode", allowedModes: ["dry"], kind: "number", min: -20, max: 20, step: 0.1 },
    humidity_start_offset: { label: "Offset de umidade inicial", category: "comfort", scope: "mode", allowedModes: ["dry"], kind: "number", min: -50, max: 50, step: 1 },
    humidity_stop_offset: { label: "Offset de umidade final", category: "comfort", scope: "mode", allowedModes: ["dry"], kind: "number", min: -50, max: 50, step: 1 },

    turbo: { label: "Turbo", category: "advanced", scope: "global", kind: "tri" },
    sleep: { label: "Sleep", category: "advanced", scope: "global", kind: "tri" },
    health: { label: "Health / IonAir", category: "advanced", scope: "global", kind: "tri" },
    ifeel: { label: "I Feel", category: "advanced", scope: "global", kind: "tri" },
    ifeel_source: { label: "Fonte do I Feel", category: "advanced", scope: "global", kind: "select", options: [
      ["Manual", "Manual"], ["Sensor dedicado", "Sensor dedicado"], ["Semi-automático", "Semi-automático"],
    ]},

    minimum_on_minutes: { label: "Mínimo ligado", category: "protection", scope: "global", kind: "number", min: 0, max: 1440, step: 1 },
    minimum_off_minutes: { label: "Mínimo desligado", category: "protection", scope: "global", kind: "number", min: 0, max: 1440, step: 1 },
    mode_protection_minutes: { label: "Proteção entre modos", category: "protection", scope: "global", kind: "number", min: 0, max: 1440, step: 1 },
    manual_pause_minutes: { label: "Pausa manual", category: "protection", scope: "global", kind: "number", min: 0, max: 1440, step: 1 },
    block_start: { label: "Bloquear partida", category: "protection", scope: "global", kind: "bool", help: "Impede apenas novas partidas automáticas; não desliga um ciclo já ativo." },
    block_automatic_off: { label: "Bloquear desligamento automático", category: "protection", scope: "global", kind: "bool", help: "Mantém um ciclo já ligado mesmo quando a demanda normal termina." },
    cancel_manual_pause: { label: "Cancelar pausa manual", category: "protection", scope: "global", kind: "bool", help: "Cancela a pausa manual existente quando a política entra ou é reavaliada." },
  };

  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
  const deepClone = (value) => typeof structuredClone === "function" ? structuredClone(value) : JSON.parse(JSON.stringify(value));
  const toArray = (value) => Array.isArray(value) ? value : [];
  const fmtDateTime = (value, options = {}) => {
    if (!value) return "—";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString("pt-BR", options);
  };
  const fmtDuration = (endValue) => {
    if (!endValue) return "";
    const seconds = Math.max(0, Math.round((new Date(endValue).getTime() - Date.now()) / 1000));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.round(seconds / 60);
    if (minutes < 60) return `${minutes} min`;
    const hours = Math.floor(minutes / 60);
    const remainder = minutes % 60;
    return remainder ? `${hours}h ${remainder}min` : `${hours}h`;
  };
  const storageGet = (key) => { try { return localStorage.getItem(key); } catch (_error) { return null; } };
  const storageSet = (key, value) => { try { localStorage.setItem(key, value); } catch (_error) { /* restricted WebView */ } };
  const openDialog = (dialog) => { if (!dialog) return; if (typeof dialog.showModal === "function") dialog.showModal(); else dialog.setAttribute("open", ""); };
  const closeDialog = (dialog) => { if (!dialog) return; if (typeof dialog.close === "function") dialog.close(); else dialog.removeAttribute("open"); };
  const boolLabel = (value) => value === true || value === "on" ? "Ligado" : value === false || value === "off" ? "Desligado" : "Padrão";
  const signed = (value) => Number(value || 0) > 0 ? `+${Number(value || 0)}` : String(Number(value || 0));

  const sharedStyles = `
    :host{display:block;min-width:0;color:var(--primary-text-color)}
    :host [hidden]{display:none!important}
    ha-card{box-sizing:border-box;overflow:hidden;container-type:inline-size;border-radius:18px}
    .surface{padding:clamp(12px,1.7vw,20px)}
    .title-row{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:14px}
    .title-row h2{margin:0;font-size:1.25rem;line-height:1.2}.title-row p{margin:5px 0 0;color:var(--secondary-text-color);font-size:.9rem}
    .eyebrow{font-size:.72rem;text-transform:uppercase;letter-spacing:.08em;color:var(--primary-color);font-weight:700}
    button{font:inherit;border:0;border-radius:11px;padding:9px 12px;cursor:pointer;display:inline-flex;align-items:center;justify-content:center;gap:7px;background:var(--primary-color);color:var(--text-primary-color,#fff);min-width:0}
    button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}
    button.danger{background:var(--error-color,#db4437);color:#fff}button:disabled{opacity:.5;cursor:wait}
    .icon-button{width:38px;height:38px;padding:0;flex:0 0 38px}
    .muted{color:var(--secondary-text-color)}.error{color:var(--error-color)}
    .chip-row{display:flex;flex-wrap:wrap;gap:6px}.chip{display:inline-flex;align-items:center;gap:5px;border-radius:999px;padding:4px 9px;background:var(--secondary-background-color);font-size:.78rem;border:1px solid transparent}
    .chip.active{border-color:color-mix(in srgb,var(--primary-color) 55%,transparent);background:color-mix(in srgb,var(--primary-color) 16%,var(--card-background-color))}
    .chip.warn{border-color:color-mix(in srgb,var(--warning-color,#ff9800) 55%,transparent)}
    .chip.error{border-color:color-mix(in srgb,var(--error-color) 55%,transparent)}
    .status-line{padding:10px 12px;border-radius:12px;background:var(--secondary-background-color);margin:10px 0;font-size:.88rem}
    @container(max-width:540px){.title-row{display:block}.title-row>.chip-row{margin-top:10px}}
  `;

  class AgendaBase extends HTMLElement {
    setConfig(config) {
      this.config = config || {};
      this.entryId = this.config.entry_id || this.entryId;
      this._policyEntityId = this.config.policy_entity || POLICY_ENTITY;
      this._loaded = false;
      this._loading = false;
      this._reloadTimer = null;
      this._reactiveTimer = null;
      this._pendingLoad = false;
      this._requestSequence = 0;
      this._acceptedRequest = 0;
      this._snapshotRevision = -1;
    }

    reactiveEntityIds() {
      return [];
    }

    hasReactiveStateChange(previousHass, currentHass) {
      if (!previousHass || !currentHass) return false;
      return this.reactiveEntityIds().some(
        (entityId) => previousHass.states?.[entityId] !== currentHass.states?.[entityId],
      );
    }

    set hass(hass) {
      const previousHass = this._hass;
      const previousPolicy = previousHass?.states?.[this._policyEntityId];
      this._hass = hass;
      const currentPolicy = hass?.states?.[this._policyEntityId];
      if (!this._loaded) {
        this.load?.();
        this.subscribePolicyEvents();
      } else if (currentPolicy && currentPolicy !== previousPolicy) {
        this.scheduleLoad();
      } else if (this.hasReactiveStateChange(previousHass, hass)) {
        this.scheduleReactiveRender();
      }
    }

    disconnectedCallback() {
      if (this._reloadTimer) clearTimeout(this._reloadTimer);
      if (this._reactiveTimer) clearTimeout(this._reactiveTimer);
      const unsubscribe = this._unsubPolicyEvent;
      this._unsubPolicyEvent = null;
      if (unsubscribe) {
        try {
          const result = unsubscribe();
          if (result && typeof result.catch === "function") result.catch(() => undefined);
        } catch (_error) { /* connection already closed */ }
      }
    }

    async subscribePolicyEvents() {
      if (!this._hass || this._unsubPolicyEvent || this._subscribingPolicyEvent) return;
      this._subscribingPolicyEvent = true;
      try {
        const unsubscribe = await this._hass.connection.subscribeEvents(
          () => this.scheduleLoad(),
          `${DOMAIN}_policy_changed`,
        );
        this._unsubPolicyEvent = unsubscribe;
      } catch (_error) {
        this._unsubPolicyEvent = null;
      } finally {
        this._subscribingPolicyEvent = false;
      }
    }

    scheduleLoad(delay = 120) {
      if (this._loading) {
        this._pendingLoad = true;
        return;
      }
      if (this._reloadTimer) clearTimeout(this._reloadTimer);
      this._reloadTimer = setTimeout(() => { this._reloadTimer = null; this.load?.(); }, delay);
    }

    snapshotRevision(data) {
      const raw = data?.snapshot?.snapshot_revision
        ?? data?.policy?.snapshot_revision
        ?? data?.power_state?.snapshot_revision
        ?? data?.preset_state?.snapshot_revision
        ?? -1;
      const value = Number(raw);
      return Number.isFinite(value) ? value : -1;
    }

    acceptSnapshot(data, requestId) {
      const revision = this.snapshotRevision(data);
      if (requestId < this._acceptedRequest) return false;
      if (revision >= 0 && revision < this._snapshotRevision) return false;
      this._acceptedRequest = requestId;
      if (revision >= 0) this._snapshotRevision = revision;
      return true;
    }

    finishLoad() {
      this._loading = false;
      this.render?.();
      if (this._pendingLoad) {
        this._pendingLoad = false;
        this.scheduleLoad(0);
      }
    }

    scheduleReactiveRender(delay = 180) {
      if (this._reactiveTimer) clearTimeout(this._reactiveTimer);
      this._reactiveTimer = setTimeout(() => {
        this._reactiveTimer = null;
        this.onReactiveStateChange?.();
      }, delay);
    }

    onReactiveStateChange() {
      this.render?.();
    }

    async ws(type, payload = {}) {
      if (!this._hass) throw new Error("Home Assistant ainda não está disponível");
      const message = { type: `${DOMAIN}/${type}`, ...payload };
      const entryId = this.entryId || this.config?.entry_id;
      if (entryId) message.entry_id = entryId;
      return this._hass.callWS(message);
    }

    async listRules() {
      const data = await this.ws("get_snapshot");
      this.entryId = data.entry_id || this.entryId;
      return data;
    }
  }

  class ElginSupervisorAgendaCard extends AgendaBase {
    reactiveEntityIds() { return [AGENDA_SWITCH]; }

    onReactiveStateChange() {
      if (!this.editing) this.render();
    }

    setConfig(config) {
      super.setConfig(config);
      this.data = null;
      this.editing = null;
      this.effects = [];
      this._status = "";
      this._statusError = false;
      this._rulesExpanded = null;
      this._pendingReload = false;
      this.render();
    }

    getCardSize() { return this._rulesExpanded ? 12 : 5; }
    getGridOptions() { return { columns: 12, min_columns: 6, rows: 6, min_rows: 3 }; }

    async load() {
      if (!this._hass || this.editing) { if (this.editing) this._pendingLoad = true; return; }
      if (this._loading) { this._pendingLoad = true; return; }
      this._loaded = true;
      this._loading = true;
      const requestId = ++this._requestSequence;
      try {
        const data = await this.listRules();
        if (this.acceptSnapshot(data, requestId)) this.data = data;
        if (this._rulesExpanded === null) {
          const stored = storageGet(`${DOMAIN}.rules_expanded.${this.entryId || "default"}`);
          this._rulesExpanded = stored === null ? toArray(this.data?.rules).length <= 4 : stored === "true";
        }
      } catch (error) {
        if (requestId >= this._acceptedRequest) this.data = { error: error.message || String(error), rules: [], policy: {}, catalog: {} };
      } finally {
        this.finishLoad();
      }
    }

    emptyRule() {
      const today = new Date().toISOString().slice(0, 10);
      return { name: "", enabled: true, priority: 50, recurrence: "weekly", interval: 1, start_date: today, end_date: "", start_time: "16:00:00", end_time: "23:59:00", weekdays: [0, 1, 2, 3, 4], months: [], monthdays: [], exclude_dates: [], ordinal: 0, ordinal_weekday: 0, all_day: false, modes: ["heat", "cool", "dry"], effects: [], notes: "" };
    }

    formatDate(value) {
      if (!value) return "sem limite";
      const parts = String(value).slice(0, 10).split("-").map(Number);
      return parts.length === 3 ? new Date(parts[0], parts[1] - 1, parts[2]).toLocaleDateString("pt-BR") : String(value);
    }

    formatTime(value) { return value ? String(value).replace(/:00$/, "") : "—"; }

    recurrenceSummary(rule) {
      const recurrence = RECURRENCE_LABELS[rule.recurrence] || rule.recurrence;
      const details = [];
      if (Number(rule.interval || 1) > 1) details.push(`a cada ${rule.interval}`);
      details.push(rule.all_day ? "dia inteiro" : `${this.formatTime(rule.start_time)}–${this.formatTime(rule.end_time)}`);
      if (rule.recurrence === "weekly" && toArray(rule.weekdays).length) details.push(toArray(rule.weekdays).map((d) => WEEKDAYS[d]).join(", "));
      if (toArray(rule.months).length) details.push(toArray(rule.months).map((m) => MONTHS[m - 1]).join(", "));
      if (toArray(rule.monthdays).length) details.push(`dias ${rule.monthdays.join(", ")}`);
      if (Number(rule.ordinal || 0)) details.push(`${rule.ordinal === -1 ? "última" : `${rule.ordinal}ª`} ${WEEKDAYS[rule.ordinal_weekday]}`);
      if (toArray(rule.exclude_dates).length) details.push(`${rule.exclude_dates.length} exclusão(ões)`);
      details.push(`desde ${this.formatDate(rule.start_date)}`);
      if (rule.end_date) details.push(`até ${this.formatDate(rule.end_date)}`);
      return `${recurrence} · ${details.join(" · ")}`;
    }

    effectValueLabel(effect) {
      const def = EFFECTS[effect.type];
      const value = effect.value;
      if (effect.type === "global_action") return GLOBAL_ACTION_LABELS[value] || value;
      if (def?.kind === "tri") return ({ default: "seguir configuração", on: "ligado", off: "desligado" })[value] || value;
      if (def?.kind === "bool") return value ? "sim" : "não";
      if (effect.type === "preset") {
        const mode = toArray(effect.modes)[0];
        const option = toArray(this.data?.catalog?.preset_options?.[mode]).find((item) => item.id === value);
        return option ? `${option.name} (nível ${option.level})` : value;
      }
      if (["power_base", "power_force", "power_min", "power_max"].includes(effect.type)) {
        const mode = toArray(effect.modes)[0];
        const option = toArray(this.data?.catalog?.power_profile_options?.[mode]).find((item) => item.id === value);
        return option ? `${option.name} (nível ${option.level})` : value;
      }
      if (["power_delta", "preset_level_delta", "priority_delta", "start_offset", "stop_offset", "dry_min_temperature_offset", "humidity_start_offset", "humidity_stop_offset"].includes(effect.type)) {
        const number = Number(value || 0); return number > 0 ? `+${number}` : String(number);
      }
      return value ?? "";
    }

    effectSummary(effect) {
      const def = EFFECTS[effect.type] || { label: effect.type, scope: "global" };
      const value = this.effectValueLabel(effect);
      const modes = def.scope === "mode" ? toArray(effect.modes).map((mode) => MODE_LABELS[mode] || mode).join(", ") : "";
      return `${def.label}${value !== "" && value !== null ? `: ${value}` : ""}${modes ? ` · ${modes}` : ""}`;
    }

    effectResultLines(rule) {
      const traces = toArray(this.data?.policy?.effect_traces?.[rule.id]);
      return traces.map((trace) => {
        const mode = MODE_LABELS[trace.mode] || trace.mode || "Global";
        if (trace.type === "preset_level_delta") {
          return `${mode}: Agenda ${signed(trace.agenda_delta)} · Base ${trace.base_name || "—"} N${trace.base_level ?? "—"} → ${trace.effective_name || "—"} N${trace.effective_level ?? "—"} · potência ${signed(trace.power_modifier)}`;
        }
        if (trace.type === "power_delta") {
          return `${mode}: ajuste consolidado ${signed(trace.consolidated)} → ${trace.effective_name || "—"} N${trace.applied_level ?? "—"}`;
        }
        if (trace.applied === false) return `${mode}: efeito não vencedor; outra regra de maior prioridade foi aplicada.`;
        if (trace.consolidated !== undefined) return `${mode}: resultado consolidado ${String(trace.consolidated)}`;
        return `${mode}: efeito aplicado.`;
      });
    }

    render() {
      const policy = this.data?.policy || {};
      const rules = toArray(this.data?.rules);
      const activeIds = new Set(toArray(policy.active_rule_ids));
      const expanded = this._rulesExpanded !== false;
      const enabled = this.data?.enabled !== false;
      this.innerHTML = `<style>${sharedStyles}
        .editor-card{padding:clamp(12px,1.7vw,20px)}
        .overview{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:9px;margin-bottom:14px}
        .metric{padding:11px;border:1px solid var(--divider-color);border-radius:13px;background:color-mix(in srgb,var(--secondary-background-color) 65%,transparent)}
        .metric small{display:block;color:var(--secondary-text-color);font-size:.75rem}.metric strong{display:block;margin-top:4px;font-size:1rem;white-space:normal;overflow-wrap:anywhere}
        .toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.rules-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding-top:12px;border-top:1px solid var(--divider-color)}
        .rule-list{display:grid;gap:9px;margin-top:10px}.rule{display:grid;grid-template-columns:minmax(0,1fr) auto;gap:12px;padding:13px;border:1px solid var(--divider-color);border-radius:15px;background:var(--ha-card-background,var(--card-background-color))}
        .rule.now{border-color:color-mix(in srgb,var(--primary-color) 68%,var(--divider-color));box-shadow:0 0 0 1px color-mix(in srgb,var(--primary-color) 20%,transparent) inset}.rule.paused{opacity:.68}
        .rule h3{margin:0;font-size:1rem}.schedule{margin:7px 0;color:var(--secondary-text-color);font-size:.86rem;line-height:1.35}.effects{display:grid;gap:4px;margin-top:8px}.effect-line{font-size:.84rem;display:flex;gap:6px}.effect-line:before{content:'•';color:var(--primary-color)}.applied-result{margin-top:9px;padding:9px 10px;border-radius:11px;background:color-mix(in srgb,var(--primary-color) 10%,var(--secondary-background-color));font-size:.8rem;display:grid;gap:3px}.applied-result strong{color:var(--primary-color)}
        .row-actions{display:flex;gap:5px;align-items:flex-start}
        dialog{border:0;border-radius:20px;background:var(--card-background-color);color:var(--primary-text-color);width:min(980px,calc(100vw - 24px));max-height:92vh;padding:0;box-shadow:var(--ha-card-box-shadow)}dialog::backdrop{background:rgba(0,0,0,.58)}
        .dialog-body{padding:clamp(14px,2vw,24px);max-height:calc(92vh - 20px);overflow:auto}.dialog-title{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:16px}.dialog-title h2{margin:0}
        .form-section{border:1px solid var(--divider-color);border-radius:16px;padding:14px;margin:12px 0}.form-section h3{margin:0 0 12px;font-size:1rem}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.full{grid-column:1/-1}
        label{font-size:.82rem;color:var(--secondary-text-color)}input,select,textarea{box-sizing:border-box;width:100%;margin-top:5px;padding:10px;border:1px solid var(--divider-color);border-radius:10px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}
        textarea{min-height:76px;resize:vertical}.checks{display:flex;flex-wrap:wrap;gap:8px;margin-top:7px}.check{display:inline-flex;align-items:center;gap:5px;color:var(--primary-text-color);padding:6px 9px;border:1px solid var(--divider-color);border-radius:999px}.check input{width:auto;margin:0}
        .effect-list{display:grid;gap:10px}.effect-row{border:1px solid var(--divider-color);border-radius:14px;padding:12px;background:color-mix(in srgb,var(--secondary-background-color) 42%,transparent)}
        .effect-grid{display:grid;grid-template-columns:minmax(190px,1.5fr) minmax(135px,1fr) minmax(210px,1.5fr) auto;gap:10px;align-items:end}.effect-help{font-size:.78rem;color:var(--secondary-text-color);margin:7px 0 0}.effect-modes.global{display:none}
        .dialog-actions{position:sticky;bottom:-1px;background:var(--card-background-color);border-top:1px solid var(--divider-color);padding:12px 0 2px;display:flex;justify-content:flex-end;gap:8px;z-index:2}
        @container(max-width:920px){.overview{grid-template-columns:repeat(2,minmax(0,1fr))}}
        @container(max-width:650px){.rule{grid-template-columns:1fr}.row-actions{justify-content:flex-start}.rules-head{align-items:flex-start;flex-direction:column}.rules-head button{width:100%}.effect-grid{grid-template-columns:1fr 1fr}.effect-modes{grid-column:1/-1}.remove-effect{justify-self:end}}
        @media(max-width:700px){.grid{grid-template-columns:1fr}.full{grid-column:auto}.effect-grid{grid-template-columns:1fr}.effect-modes{grid-column:auto}.remove-effect{width:100%}.dialog-actions{display:grid;grid-template-columns:1fr 1fr}.dialog-actions button{width:100%}.overview{grid-template-columns:1fr 1fr}}
        @media(max-width:430px){.overview{grid-template-columns:1fr}.toolbar{display:grid}.toolbar button{width:100%}.row-actions{display:grid;grid-template-columns:repeat(3,1fr);width:100%}.row-actions button{width:100%}}
      </style><ha-card><div class="editor-card">
        <div class="title-row"><div><div class="eyebrow">Editor local</div><h2>Regras da Agenda</h2><p>Recorrências, prioridades e efeitos temporários sem alterar os helpers manuais.</p></div><div class="chip-row"><span class="chip ${enabled ? "active" : "warn"}"><ha-icon icon="${enabled ? "mdi:calendar-check" : "mdi:calendar-remove"}"></ha-icon>${enabled ? "Agenda ligada" : "Agenda desligada"}</span></div></div>
        ${this.data?.error ? `<ha-alert alert-type="error">${esc(this.data.error)}</ha-alert>` : ""}
        <div class="overview">
          <div class="metric"><small>Cadastradas</small><strong>${Number(policy.registered_rule_count ?? rules.length)}</strong></div>
          <div class="metric"><small>Habilitadas</small><strong>${Number(policy.enabled_rule_count ?? rules.filter((r) => r.enabled).length)}</strong></div>
          <div class="metric"><small>Ativas agora</small><strong>${Number(policy.active_count || 0)}</strong></div>
          <div class="metric"><small>Efeitos efetivos</small><strong>${Number(policy.effective_effect_count || 0)}</strong></div>
        </div>
        ${this._status ? `<div class="status-line ${this._statusError ? "error" : ""}">${esc(this._status)}</div>` : ""}
        <div class="toolbar"><button id="new"><ha-icon icon="mdi:calendar-plus"></ha-icon>Nova regra</button><button class="secondary" id="refresh"><ha-icon icon="mdi:calendar-refresh"></ha-icon>Reavaliar</button><button class="secondary" id="reload"><ha-icon icon="mdi:refresh"></ha-icon>Atualizar dados</button></div>
        <div class="rules-head"><div><strong>Lista de regras</strong><div class="muted">Efeitos aditivos são somados. Somente efeitos absolutos usam prioridade e regra vencedora.</div></div><button class="secondary" id="toggle-rules"><ha-icon icon="mdi:chevron-${expanded ? "up" : "down"}"></ha-icon>${expanded ? "Recolher lista" : `Mostrar regras (${rules.length})`}</button></div>
        <div class="rule-list" ${expanded ? "" : "hidden"}>${rules.length ? rules.map((rule) => this.ruleHtml(rule, activeIds.has(rule.id))).join("") : '<div class="status-line muted">Nenhuma regra cadastrada.</div>'}</div>
        <dialog id="editor"><div class="dialog-body" id="editor-body"></div></dialog>
      </div></ha-card>`;
      this.bindMain();
    }

    ruleHtml(rule, active) {
      const effects = toArray(rule.effects).map((effect) => this.effectSummary(effect));
      const results = active ? this.effectResultLines(rule) : [];
      return `<article class="rule ${active ? "now" : ""} ${rule.enabled ? "" : "paused"}"><div><div class="chip-row"><span class="chip ${active ? "active" : ""}">${active ? "Ativa agora" : rule.enabled ? "Habilitada" : "Pausada"}</span><span class="chip">P${Number(rule.priority || 0)}</span>${toArray(rule.modes).map((m) => `<span class="chip">${esc(MODE_LABELS[m] || m)}</span>`).join("")}</div><h3>${esc(rule.name)}</h3><div class="schedule"><ha-icon icon="mdi:calendar-clock"></ha-icon> ${esc(this.recurrenceSummary(rule))}</div><div class="effects">${effects.length ? effects.map((text) => `<div class="effect-line">${esc(text)}</div>`).join("") : '<div class="muted">Sem efeitos configurados.</div>'}</div>${results.length ? `<div class="applied-result"><strong>Resultado efetivo</strong>${results.map((text) => `<div>${esc(text)}</div>`).join("")}</div>` : ""}${rule.notes ? `<div class="status-line"><strong>Nota:</strong> ${esc(rule.notes)}</div>` : ""}</div><div class="row-actions"><button class="secondary icon-button edit" data-id="${esc(rule.id)}" title="Editar"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="secondary icon-button toggle" data-id="${esc(rule.id)}" data-enabled="${rule.enabled ? "false" : "true"}" title="${rule.enabled ? "Pausar" : "Ativar"}"><ha-icon icon="mdi:${rule.enabled ? "pause" : "play"}"></ha-icon></button><button class="danger icon-button delete" data-id="${esc(rule.id)}" title="Excluir"><ha-icon icon="mdi:delete"></ha-icon></button></div></article>`;
    }

    bindMain() {
      this.querySelector("#new")?.addEventListener("click", () => this.openEditor(this.emptyRule()));
      this.querySelector("#refresh")?.addEventListener("click", async () => { try { await this.ws("evaluate"); this._status = "Política reavaliada."; await this.load(); } catch (e) { this._status = e.message || String(e); this._statusError = true; this.render(); } });
      this.querySelector("#reload")?.addEventListener("click", () => this.load());
      this.querySelector("#toggle-rules")?.addEventListener("click", () => { this._rulesExpanded = !this._rulesExpanded; storageSet(`${DOMAIN}.rules_expanded.${this.entryId || "default"}`, String(this._rulesExpanded)); this.render(); });
      this.querySelectorAll(".edit").forEach((button) => button.addEventListener("click", () => { const rule = toArray(this.data?.rules).find((item) => item.id === button.dataset.id); if (rule) this.openEditor(deepClone(rule)); }));
      this.querySelectorAll(".toggle").forEach((button) => button.addEventListener("click", async () => { try { await this.ws("set_rule_enabled", { rule_id: button.dataset.id, enabled: button.dataset.enabled === "true" }); this._status = "Regra atualizada e política recalculada."; this._statusError = false; await this.load(); } catch (e) { this._status = e.message || String(e); this._statusError = true; this.render(); } }));
      this.querySelectorAll(".delete").forEach((button) => button.addEventListener("click", async () => { if (!confirm("Excluir esta regra permanentemente?")) return; try { await this.ws("delete_rule", { rule_id: button.dataset.id }); this._status = "Regra excluída e política recalculada."; this._statusError = false; await this.load(); } catch (e) { this._status = e.message || String(e); this._statusError = true; this.render(); } }));
    }

    openEditor(rule) {
      this.editing = rule;
      this.effects = deepClone(rule.effects || []);
      this.renderEditor();
      openDialog(this.querySelector("#editor"));
    }

    renderEditor() {
      const rule = this.editing;
      const body = this.querySelector("#editor-body");
      if (!body) return;
      body.innerHTML = `<div class="dialog-title"><div><div class="eyebrow">Configuração temporal</div><h2>${rule.id ? "Editar regra" : "Nova regra"}</h2></div><button class="secondary icon-button" id="close-x" type="button"><ha-icon icon="mdi:close"></ha-icon></button></div>
        <section class="form-section"><h3>Identificação</h3><div class="grid"><label>Nome<input id="f-name" value="${esc(rule.name)}"></label><label>Prioridade<input id="f-priority" type="number" min="0" max="100" value="${Number(rule.priority || 50)}"></label><label class="full">Notas<textarea id="f-notes">${esc(rule.notes || "")}</textarea></label></div></section>
        <section class="form-section"><h3>Recorrência</h3><div class="grid"><label>Recorrência<select id="f-recurrence">${Object.entries(RECURRENCE_LABELS).map(([value, label]) => `<option value="${value}" ${rule.recurrence === value ? "selected" : ""}>${label}</option>`).join("")}</select></label><div id="recurrence-hint" class="full status-line muted"></div><label data-recurrence="interval">Intervalo<input id="f-interval" type="number" min="1" value="${Number(rule.interval || 1)}"></label><label>Data inicial<input id="f-start-date" type="date" value="${esc(rule.start_date)}"></label><label>Data final<input id="f-end-date" type="date" value="${esc(rule.end_date)}"></label><label>Hora inicial<input id="f-start-time" type="time" step="1" value="${esc(rule.start_time)}"></label><label>Hora final<input id="f-end-time" type="time" step="1" value="${esc(rule.end_time)}"></label><div class="full checks"><label class="check"><input id="f-all-day" type="checkbox" ${rule.all_day ? "checked" : ""}>Evento de dia inteiro</label></div><div class="full" data-recurrence="weekdays"><label>Dias da semana</label><div class="checks">${WEEKDAYS.map((name, i) => `<label class="check"><input class="weekday" type="checkbox" value="${i}" ${toArray(rule.weekdays).includes(i) ? "checked" : ""}>${name}</label>`).join("")}</div></div><div class="full" data-recurrence="months"><label>Meses permitidos — vazio significa todos</label><div class="checks">${MONTHS.map((name, i) => `<label class="check"><input class="month" type="checkbox" value="${i + 1}" ${toArray(rule.months).includes(i + 1) ? "checked" : ""}>${name}</label>`).join("")}</div></div><label data-recurrence="monthdays">Dias do mês<input id="f-monthdays" placeholder="1, 15, 31" value="${esc(toArray(rule.monthdays).join(", "))}"></label><label>Datas excluídas<input id="f-exclude-dates" placeholder="2026-12-25, 2027-01-01" value="${esc(toArray(rule.exclude_dates).join(", "))}"></label><label data-recurrence="ordinal">Ocorrência mensal<select id="f-ordinal"><option value="0">Não usar</option>${[[1, "Primeira"], [2, "Segunda"], [3, "Terceira"], [4, "Quarta"], [5, "Quinta"], [-1, "Última"]].map(([v, n]) => `<option value="${v}" ${Number(rule.ordinal) === v ? "selected" : ""}>${n}</option>`).join("")}</select></label><label data-recurrence="ordinal-weekday">Dia da ocorrência<select id="f-ordinal-weekday">${WEEKDAYS.map((name, i) => `<option value="${i}" ${Number(rule.ordinal_weekday) === i ? "selected" : ""}>${name}</option>`).join("")}</select></label></div></section>
        <section class="form-section"><h3>Escopo padrão</h3><div class="checks">${MODES.map(([value, label]) => `<label class="check"><input class="mode" type="checkbox" value="${value}" ${toArray(rule.modes).includes(value) ? "checked" : ""}>${label}</label>`).join("")}</div></section>
        <section class="form-section"><div class="title-row"><div><h3>Efeitos</h3><p>Vários efeitos podem coexistir. Valores absolutos usam a maior prioridade; ajustes numéricos são somados.</p></div><button class="secondary" id="add-effect" type="button"><ha-icon icon="mdi:plus"></ha-icon>Adicionar efeito</button></div><div class="effect-list" id="effect-list"></div></section>
        <div class="dialog-actions"><button class="secondary" id="close" type="button">Cancelar</button><button id="save" type="button"><ha-icon icon="mdi:content-save"></ha-icon>Salvar regra</button></div>`;
      this.renderEffects();
      this.updateRecurrenceVisibility();
      body.querySelector("#f-recurrence")?.addEventListener("change", () => this.updateRecurrenceVisibility());
      body.querySelector("#f-ordinal")?.addEventListener("change", () => this.updateRecurrenceVisibility());
      body.querySelector("#f-all-day")?.addEventListener("change", () => this.updateRecurrenceVisibility());
      body.querySelector("#add-effect")?.addEventListener("click", () => { this.effects.push({ type: "power_delta", value: -1, modes: ["heat", "cool", "dry"] }); this.renderEffects(); });
      ["#close", "#close-x"].forEach((selector) => body.querySelector(selector)?.addEventListener("click", () => { this.editing = null; closeDialog(this.querySelector("#editor")); if (this._pendingReload) { this._pendingReload = false; this.load(); } }));
      body.querySelector("#save")?.addEventListener("click", () => this.saveEditor());
    }

    updateRecurrenceVisibility() {
      const recurrence = this.querySelector("#f-recurrence")?.value || "weekly";
      const visibility = {
        interval: recurrence !== "once",
        weekdays: ["daily", "weekly"].includes(recurrence),
        months: ["daily", "weekly", "monthly"].includes(recurrence),
        monthdays: recurrence === "monthly",
        ordinal: recurrence === "monthly",
        "ordinal-weekday": recurrence === "monthly" && Number(this.querySelector("#f-ordinal")?.value || 0) !== 0,
      };
      Object.entries(visibility).forEach(([key, visible]) => {
        this.querySelectorAll(`[data-recurrence="${key}"]`).forEach((element) => { element.hidden = !visible; });
      });
      const hints = {
        once: "Executa uma única ocorrência entre a data/hora inicial e final.",
        daily: "Repete a cada N dias; dias da semana e meses podem restringir as ocorrências.",
        weekly: "Repete nas semanas e dias selecionados; a data inicial é o limite absoluto de início.",
        monthly: "Use dias do mês ou uma ocorrência ordinal, como a primeira segunda-feira.",
        yearly: "Repete no dia e mês da data inicial, conforme o intervalo de anos.",
      };
      const hint = this.querySelector("#recurrence-hint");
      if (hint) hint.textContent = hints[recurrence] || "";
      const allDay = this.querySelector("#f-all-day")?.checked;
      ["#f-start-time", "#f-end-time"].forEach((selector) => { const input = this.querySelector(selector); if (input) input.disabled = Boolean(allDay); });
    }

    effectOptions(selected) {
      return EFFECT_GROUPS.map(([group, label]) => `<optgroup label="${esc(label)}">${Object.entries(EFFECTS).filter(([, def]) => def.category === group).map(([value, def]) => `<option value="${value}" ${selected === value ? "selected" : ""}>${esc(def.label)}</option>`).join("")}</optgroup>`).join("");
    }

    renderEffects() {
      const list = this.querySelector("#effect-list");
      if (!list) return;
      const catalog = this.data?.catalog || {};
      list.innerHTML = this.effects.length ? this.effects.map((effect, index) => {
        const def = EFFECTS[effect.type] || EFFECTS.power_delta;
        const allowedModes = def.allowedModes || MODES.map(([value]) => value);
        const modeChoices = MODES.filter(([value]) => allowedModes.includes(value));
        const selectedModes = toArray(effect.modes).filter((mode) => allowedModes.includes(mode));
        const selectedMode = selectedModes[0] || allowedModes[0] || "heat";
        const modeControl = def.scope === "global" ? "" : def.singleMode
          ? `<label>Modo<select class="e-mode-single">${modeChoices.map(([value, label]) => `<option value="${value}" ${selectedMode === value ? "selected" : ""}>${label}</option>`).join("")}</select></label>`
          : `<div class="effect-modes"><label>Modos afetados</label><div class="checks">${modeChoices.map(([value, label]) => `<label class="check"><input class="e-mode" type="checkbox" value="${value}" ${selectedModes.includes(value) ? "checked" : ""}>${label}</label>`).join("")}</div></div>`;
        const normalizedEffect = { ...effect, modes: def.singleMode ? [selectedMode] : selectedModes };
        return `<div class="effect-row" data-index="${index}"><div class="effect-grid"><label>Efeito<select class="e-type">${this.effectOptions(effect.type)}</select></label><label>Valor${this.valueControl(def, normalizedEffect, catalog)}</label>${modeControl}<button type="button" class="danger icon-button remove-effect" title="Remover"><ha-icon icon="mdi:delete"></ha-icon></button></div>${def.help ? `<p class="effect-help">${esc(def.help)}</p>` : ""}</div>`;
      }).join("") : '<div class="status-line muted">Nenhum efeito. A regra pode ser salva, mas não alterará o Supervisor.</div>';

      list.querySelectorAll(".e-type").forEach((select) => select.addEventListener("change", (event) => {
        const index = Number(event.target.closest(".effect-row").dataset.index);
        const type = event.target.value;
        const def = EFFECTS[type];
        const allowedModes = def.allowedModes || MODES.map(([value]) => value);
        const defaults = (toArray(this.editing.modes).length ? [...this.editing.modes] : ["heat", "cool", "dry"]).filter((mode) => allowedModes.includes(mode));
        const modes = def.scope === "mode" ? (def.singleMode ? [defaults[0] || allowedModes[0]] : (defaults.length ? defaults : [...allowedModes])) : [];
        this.effects[index].type = type;
        this.effects[index].modes = modes;
        this.effects[index].value = this.defaultValue(type, modes[0], catalog);
        this.renderEffects();
      }));
      list.querySelectorAll(".e-mode-single").forEach((select) => select.addEventListener("change", (event) => {
        const index = Number(event.target.closest(".effect-row").dataset.index);
        const mode = event.target.value;
        const effect = this.effects[index];
        effect.modes = [mode];
        effect.value = this.defaultValue(effect.type, mode, catalog);
        this.renderEffects();
      }));
      list.querySelectorAll(".remove-effect").forEach((button) => button.addEventListener("click", (event) => {
        this.effects.splice(Number(event.target.closest(".effect-row").dataset.index), 1);
        this.renderEffects();
      }));
    }

    defaultValue(type, mode = null, catalog = {}) {
      const def = EFFECTS[type];
      if (def.kind === "tri") return "default";
      if (def.kind === "bool") return true;
      if (def.kind === "number") return 0;
      if (def.kind === "select") return def.options?.[0]?.[0] ?? "";
      if (def.kind === "power") return toArray(catalog.power_profile_options?.[mode])[0]?.id || "";
      if (def.kind === "preset") return toArray(catalog.preset_options?.[mode])[0]?.id || "";
      return "";
    }

    valueControl(def, effect, catalog) {
      if (def.kind === "none") return '<input class="e-value" type="hidden" value="">';
      if (def.kind === "number") return `<input class="e-value" type="number" min="${def.min}" max="${def.max}" step="${def.step}" value="${esc(effect.value ?? 0)}">`;
      if (def.kind === "bool") return `<select class="e-value"><option value="true" ${effect.value === true ? "selected" : ""}>Sim</option><option value="false" ${effect.value === false ? "selected" : ""}>Não</option></select>`;
      let options = def.options || [];
      if (def.kind === "tri") options = [["default", "Seguir configuração normal"], ["on", "Ligado"], ["off", "Desligado"]];
      if (def.kind === "power") {
        const mode = toArray(effect.modes)[0];
        options = toArray(catalog.power_profile_options?.[mode]).map((item) => [item.id, `${item.name} · nível ${item.level}`]);
        if (!options.length) options = [["", "Nenhum perfil habilitado neste modo"]];
      }
      if (def.kind === "preset") {
        const mode = toArray(effect.modes)[0];
        options = toArray(catalog.preset_options?.[mode]).map((item) => [item.id, `${item.name} · nível ${item.level}`]);
        if (!options.length) options = [["", "Nenhum preset habilitado neste modo"]];
      }
      return `<select class="e-value">${options.map(([value, label]) => `<option value="${esc(value)}" ${String(effect.value) === String(value) ? "selected" : ""}>${esc(label)}</option>`).join("")}</select>`;
    }

    collectEffects() {
      return [...this.querySelectorAll(".effect-row")].map((row) => {
        const type = row.querySelector(".e-type").value;
        const def = EFFECTS[type];
        let value = row.querySelector(".e-value")?.value;
        if (def.kind === "number") value = Number(value);
        if (def.kind === "bool") value = value === "true";
        if (def.kind === "none") value = null;
        let modes = [];
        if (def.scope === "mode") {
          modes = def.singleMode
            ? [row.querySelector(".e-mode-single")?.value].filter(Boolean)
            : [...row.querySelectorAll(".e-mode:checked")].map((item) => item.value);
        }
        return { type, value, modes };
      });
    }

    async saveEditor() {
      const q = (id) => this.querySelector(id);
      const modes = [...this.querySelectorAll(".mode:checked")].map((item) => item.value);
      if (!modes.length) { alert("Selecione ao menos um modo padrão para a regra."); return; }
      const rule = { ...this.editing, name: q("#f-name").value.trim() || "Regra sem nome", priority: Number(q("#f-priority").value), recurrence: q("#f-recurrence").value, interval: Number(q("#f-interval").value), start_date: q("#f-start-date").value, end_date: q("#f-end-date").value, start_time: q("#f-start-time").value, end_time: q("#f-end-time").value, weekdays: [...this.querySelectorAll(".weekday:checked")].map((item) => Number(item.value)), months: [...this.querySelectorAll(".month:checked")].map((item) => Number(item.value)), monthdays: q("#f-monthdays").value.split(",").map((value) => Number(value.trim())).filter((value) => value > 0), exclude_dates: q("#f-exclude-dates").value.split(",").map((value) => value.trim()).filter(Boolean), ordinal: Number(q("#f-ordinal").value), ordinal_weekday: Number(q("#f-ordinal-weekday").value), all_day: q("#f-all-day").checked, modes, notes: q("#f-notes").value, effects: this.collectEffects(), enabled: this.editing.enabled !== false };
      try {
        await this.ws("save_rule", { rule });
        this.editing = null;
        closeDialog(this.querySelector("#editor"));
        this._pendingReload = false;
        this._status = `Regra salva: ${rule.name}.`;
        this._statusError = false;
        await this.load();
      } catch (error) { alert(`Não foi possível salvar: ${error.message || error}`); }
    }
  }

  class ElginSupervisorAgendaPolicyCard extends AgendaBase {
    reactiveEntityIds() { return POLICY_REACTIVE_ENTITIES; }

    setConfig(config) { super.setConfig(config); this.data = null; this._expanded = storageGet(`${DOMAIN}.policy.expanded`) !== "false"; this.render(); }
    getCardSize() { return this._expanded ? 9 : 4; }
    getGridOptions() { return { columns: 12, min_columns: 6, rows: 6, min_rows: 3 }; }

    async load() {
      if (!this._hass) return;
      if (this._loading) { this._pendingLoad = true; return; }
      this._loaded = true; this._loading = true;
      const requestId = ++this._requestSequence;
      try {
        const data = await this.listRules();
        if (this.acceptSnapshot(data, requestId)) this.data = data;
      } catch (error) {
        if (requestId >= this._acceptedRequest) this.data = { error: error.message || String(error), policy: {} };
      } finally { this.finishLoad(); }
    }

    sourceText(key) {
      const source = this.data?.policy?.effect_sources?.[key];
      if (!source) return "Configuração manual";
      if (Array.isArray(source)) return source.map((item) => `${item.rule} (P${item.priority})`).join(" + ");
      return `${source.rule} (P${source.priority})`;
    }

    valueRow(label, value, sourceKey, icon = "mdi:tune") {
      const source = sourceKey ? this.sourceText(sourceKey) : "";
      return `<div class="value-row"><ha-icon icon="${icon}"></ha-icon><div><span>${esc(label)}</span><strong>${esc(value)}</strong>${source ? `<small>${esc(source)}</small>` : ""}</div></div>`;
    }

    modePanel(mode, policy) {
      const label = MODE_LABELS[mode];
      const enabled = policy.modes?.[mode] !== false;
      const preset = this.data?.preset_state?.modes?.[mode] || {};
      const items = [];
      if (preset.available) {
        items.push(`Base ${preset.base_name} · nível ${preset.base_level}`);
        if (preset.agenda_base_override) items.push(`Base forçada pela Agenda: ${preset.calculation_base_name}`);
        items.push(`Base ${preset.calculation_base_level ?? 0} + Manual ${signed(preset.manual_level_delta)} + Agenda ${signed(preset.agenda_level_delta)} + Regional ${signed(preset.regional_level_delta)} = nível ${preset.calculated_level}`);
        items.push(`Efetivo ${preset.effective_name} · nível ${preset.effective_level} · potência ${signed(preset.power_modifier)}`);
      }
      if (Number(policy.power_delta?.[mode] || 0)) items.push(`Potência Agenda ${Number(policy.power_delta[mode]) > 0 ? "+" : ""}${policy.power_delta[mode]}`);
      if (Number(policy.preset_level_delta?.[mode] || 0)) items.push(`Preset Agenda ${Number(policy.preset_level_delta[mode]) > 0 ? "+" : ""}${policy.preset_level_delta[mode]}`);
      if (policy.power_force?.[mode]) items.push(`Potência forçada ${policy.power_force[mode]}`);
      if (policy.power_min?.[mode]) items.push(`Potência mín. ${policy.power_min[mode]}`);
      if (policy.power_max?.[mode]) items.push(`Potência máx. ${policy.power_max[mode]}`);
      if (Number(policy.priority_delta?.[mode] || 0)) items.push(`Prioridade ${Number(policy.priority_delta[mode]) > 0 ? "+" : ""}${policy.priority_delta[mode]}`);
      if (policy.fan?.[mode]) items.push(`Fan ${policy.fan[mode]}`);
      if (policy.swing?.[mode]) items.push(`Swing ${policy.swing[mode]}`);
      return `<div class="mode-panel ${enabled ? "" : "disabled"}"><div class="mode-title"><ha-icon icon="${MODES.find(([id]) => id === mode)?.[2] || "mdi:air-conditioner"}"></ha-icon><strong>${label}</strong><span class="chip ${enabled ? "active" : "error"}">${enabled ? "Permitido" : "Bloqueado"}</span></div><div class="mode-details">${items.length ? items.map((item) => `<span>${esc(item)}</span>`).join("") : '<span class="muted">Sem preset disponível</span>'}</div>${toArray(preset.diagnostics).length ? `<div class="muted" style="margin-top:6px">${toArray(preset.diagnostics).map((item) => esc(item)).join(" · ")}</div>` : ""}</div>`;
    }

    render() {
      const policy = this.data?.policy || {};
      const action = policy.global_action || "normal";
      const active = toArray(policy.active_occurrences);
      const next = policy.next_transition;
      const conflicts = toArray(policy.conflicts);
      const agendaState = this._hass?.states?.[AGENDA_SWITCH]?.state === "on";
      const effectiveBinary = (entityId, fallback) => {
        const state = this._hass?.states?.[entityId]?.state;
        return state === "on" ? "Ligado" : state === "off" ? "Desligado" : fallback;
      };
      const timesEntity = this._hass?.states?.["sensor.elgin_supervisor_tempos_efetivos"];
      const times = timesEntity?.attributes || {};
      const effective = {
        regional: effectiveBinary("binary_sensor.elgin_supervisor_clima_regional_efetivo", boolLabel(policy.regional)),
        limits: effectiveBinary("binary_sensor.elgin_supervisor_limites_automaticos_efetivos", boolLabel(policy.limits_auto)),
        physical: effectiveBinary("binary_sensor.elgin_supervisor_fisico_semiautomatico_efetivo", boolLabel(policy.physical_semiautomatic)),
        manual: effectiveBinary("binary_sensor.elgin_supervisor_respeitar_controle_manual_efetivo", boolLabel(policy.respect_manual)),
        eco: effectiveBinary("binary_sensor.elgin_supervisor_eco_efetivo", boolLabel(policy.eco)),
        turbo: effectiveBinary("binary_sensor.elgin_supervisor_turbo_efetivo", boolLabel(policy.turbo)),
        sleep: effectiveBinary("binary_sensor.elgin_supervisor_sleep_efetivo", boolLabel(policy.sleep)),
        health: effectiveBinary("binary_sensor.elgin_supervisor_health_efetivo", boolLabel(policy.health)),
        ifeel: effectiveBinary("binary_sensor.elgin_supervisor_ifeel_efetivo", boolLabel(policy.ifeel)),
        source: this._hass?.states?.["sensor.elgin_supervisor_fonte_ifeel_efetiva"]?.state || policy.ifeel_source || "Padrão",
        authorized: effectiveBinary("binary_sensor.elgin_supervisor_operacao_efetivamente_autorizada", "Indisponível"),
        authorizedReason: this._hass?.states?.["binary_sensor.elgin_supervisor_operacao_efetivamente_autorizada"]?.attributes?.motivo || "",
        oneShotProcessed: Boolean(this._hass?.states?.["sensor.elgin_supervisor_politica_temporal_efetiva"]?.attributes?.desligamento_unico_processado),
        minimumOn: Number(times.minimo_ligado ?? policy.minimum_on_minutes),
        minimumOff: Number(times.minimo_desligado ?? policy.minimum_off_minutes),
        modeProtection: Number(times.protecao_troca_modo ?? policy.mode_protection_minutes),
        manualPause: Number(times.pausa_manual ?? policy.manual_pause_minutes),
      };
      this.innerHTML = `<style>${sharedStyles}
        .policy-card{padding:clamp(12px,1.7vw,20px)}.hero{display:grid;grid-template-columns:minmax(0,1.5fr) repeat(3,minmax(120px,.7fr));gap:10px;margin-bottom:12px}.hero-main,.stat{border:1px solid var(--divider-color);border-radius:15px;padding:14px;background:color-mix(in srgb,var(--secondary-background-color) 48%,transparent)}
        .hero-main strong{display:block;font-size:1.15rem;margin:4px 0}.stat small{display:block;color:var(--secondary-text-color)}.stat strong{display:block;margin-top:6px;overflow-wrap:anywhere}.toolbar{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}
        .active-list{display:grid;gap:8px}.active-rule{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:10px;align-items:center;border:1px solid var(--divider-color);border-radius:13px;padding:10px}.priority{width:42px;height:42px;border-radius:12px;display:grid;place-items:center;background:color-mix(in srgb,var(--primary-color) 18%,transparent);font-weight:700}.active-rule h4{margin:0}.active-rule p{margin:3px 0 0;font-size:.82rem;color:var(--secondary-text-color)}.active-effects{margin-top:7px;font-size:.78rem}.active-effects summary{cursor:pointer;color:var(--primary-color);font-weight:600}.effects-expanded{display:grid;gap:3px;margin-top:6px;color:var(--secondary-text-color)}
        .section-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:16px 0 8px}.section-head h3{margin:0;font-size:1rem}.groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.group{border:1px solid var(--divider-color);border-radius:15px;padding:12px}.group h4{margin:0 0 9px}.value-list{display:grid;gap:7px}.value-row{display:grid;grid-template-columns:auto minmax(0,1fr);gap:9px;align-items:start}.value-row ha-icon{color:var(--primary-color);margin-top:2px}.value-row span,.value-row small{display:block;color:var(--secondary-text-color);font-size:.76rem}.value-row strong{display:block;font-size:.9rem;margin:1px 0}.modes{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px}.mode-panel{border:1px solid var(--divider-color);border-radius:14px;padding:11px}.mode-panel.disabled{opacity:.6}.mode-title{display:flex;align-items:center;gap:7px;flex-wrap:wrap}.mode-title .chip{margin-left:auto}.mode-details{display:grid;gap:4px;margin-top:8px;font-size:.8rem}.conflicts{padding:10px;border-radius:12px;background:color-mix(in srgb,var(--error-color) 12%,transparent);border:1px solid color-mix(in srgb,var(--error-color) 50%,transparent)}
        @container(max-width:900px){.hero{grid-template-columns:repeat(2,minmax(0,1fr))}.hero-main{grid-column:1/-1}.modes{grid-template-columns:1fr}.groups{grid-template-columns:1fr}}
        @container(max-width:520px){.hero{grid-template-columns:1fr}.hero-main{grid-column:auto}.active-rule{grid-template-columns:auto minmax(0,1fr)}.active-rule>.chip{grid-column:2}.toolbar{display:grid}.toolbar button{width:100%}}
      </style><ha-card><div class="policy-card">
        <div class="title-row"><div><div class="eyebrow">Estado efetivo</div><h2>Política temporal</h2><p>Resultado consolidado das regras ativas, com origem e prioridade.</p></div><div class="chip-row"><span class="chip ${agendaState ? "active" : "warn"}"><ha-icon icon="mdi:calendar-${agendaState ? "check" : "remove"}"></ha-icon>${agendaState ? "Agenda habilitada" : "Agenda desabilitada"}</span></div></div>
        ${this.data?.error ? `<ha-alert alert-type="error">${esc(this.data.error)}</ha-alert>` : ""}
        <div class="hero"><div class="hero-main"><small class="muted">Ação global</small><strong>${esc(GLOBAL_ACTION_LABELS[action] || action)}</strong><div class="muted">${esc(this.sourceText("global_action"))} · ${esc(effective.authorizedReason || `Transmissão automática: ${effective.authorized}`)}</div>${action === "power_off" ? `<div class="chip-row" style="margin-top:8px"><span class="chip ${effective.oneShotProcessed ? "active" : "warn"}">${effective.oneShotProcessed ? "Desligamento já aplicado; religamento manual permitido" : "Desligamento pendente"}</span></div>` : ""}</div><div class="stat"><small>Regras ativas</small><strong>${Number(policy.active_count || 0)}</strong></div><div class="stat"><small>Próxima transição</small><strong>${next ? fmtDateTime(next, { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—"}</strong>${next ? `<div class="muted">em ${fmtDuration(next)}</div>` : ""}</div><div class="stat"><small>Conflitos</small><strong>${conflicts.length}</strong></div></div>
        <div class="toolbar"><button id="toggle-agenda" class="${agendaState ? "secondary" : ""}"><ha-icon icon="mdi:${agendaState ? "calendar-remove" : "calendar-check"}"></ha-icon>${agendaState ? "Desabilitar Agenda" : "Habilitar Agenda"}</button><button class="secondary" id="reevaluate"><ha-icon icon="mdi:calendar-refresh"></ha-icon>Reavaliar agora</button><button class="secondary" id="cancel-once"><ha-icon icon="mdi:calendar-remove"></ha-icon>Cancelar exceções únicas</button><button class="secondary" id="expand"><ha-icon icon="mdi:chevron-${this._expanded ? "up" : "down"}"></ha-icon>${this._expanded ? "Recolher detalhes" : "Mostrar detalhes"}</button></div>
        <div class="section-head"><h3>Ativas agora</h3><span class="muted">Aditivos somam; absolutos usam maior prioridade</span></div><div class="active-list">${active.length ? active.map((item) => { const effects = toArray(item.effects); return `<div class="active-rule"><div class="priority">P${Number(item.priority || 0)}</div><div><h4>${esc(item.name)}</h4><p>${fmtDateTime(item.start)} → ${fmtDateTime(item.end)} · termina em ${fmtDuration(item.end)}</p><div class="chip-row">${effects.slice(0, 4).map((effect) => `<span class="chip">${esc(effect)}</span>`).join("")}</div>${effects.length > 4 ? `<details class="active-effects"><summary>Ver todos os ${effects.length} efeitos</summary><div class="effects-expanded">${effects.map((effect) => `<span>• ${esc(effect)}</span>`).join("")}</div></details>` : ""}${toArray(policy.effect_traces?.[item.rule_id]).length ? `<details class="active-effects" open><summary>Resultado aplicado</summary><div class="effects-expanded">${toArray(policy.effect_traces[item.rule_id]).map((trace) => trace.type === "preset_level_delta" ? `<span>• ${esc(MODE_LABELS[trace.mode] || trace.mode)}: base N${trace.base_level ?? "—"} + Agenda ${signed(trace.agenda_delta)} = ${esc(trace.effective_name || "—")} N${trace.effective_level ?? "—"}; potência ${signed(trace.power_modifier)}</span>` : `<span>• ${esc(MODE_LABELS[trace.mode] || trace.mode)}: ${esc(trace.type)} → ${esc(trace.consolidated ?? (trace.applied ? "aplicado" : "não vencedor"))}</span>`).join("")}</div></details>` : ""}</div><span class="chip active">Ativa</span></div>`; }).join("") : '<div class="status-line muted">Nenhuma ocorrência ativa. Os helpers manuais governam o Supervisor.</div>'}</div>
        <div ${this._expanded ? "" : "hidden"}>
          <div class="section-head"><h3>Modos, potência e perfil</h3></div><div class="modes">${["heat", "cool", "dry"].map((mode) => this.modePanel(mode, policy)).join("")}</div>
          <div class="section-head"><h3>Overrides efetivos</h3></div><div class="groups"><div class="group"><h4>Automação e ambiente</h4><div class="value-list">${this.valueRow("Clima regional", effective.regional, "regional", "mdi:weather-partly-cloudy")}${this.valueRow("Limites automáticos", effective.limits, "limits_auto", "mdi:tune-variant")}${this.valueRow("Físico semi-automático", effective.physical, "physical_semiautomatic", "mdi:remote")}${this.valueRow("Respeitar controle manual", effective.manual, "respect_manual", "mdi:hand-back-right")}${this.valueRow("Eco", effective.eco, "eco", "mdi:leaf")}</div></div><div class="group"><h4>Funções avançadas</h4><div class="value-list">${this.valueRow("I Feel", effective.ifeel, "ifeel", "mdi:thermometer-lines")}${this.valueRow("Fonte do I Feel", effective.source, "ifeel_source", "mdi:thermometer-auto")}${this.valueRow("Turbo", effective.turbo, "turbo", "mdi:weather-windy")}${this.valueRow("Sleep", effective.sleep, "sleep", "mdi:power-sleep")}${this.valueRow("Health / IonAir", effective.health, "health", "mdi:air-filter")}</div></div><div class="group"><h4>Proteções</h4><div class="value-list">${this.valueRow("Mínimo ligado", Number.isFinite(effective.minimumOn) ? `${effective.minimumOn} min` : "Indisponível", "minimum_on_minutes", "mdi:timer-lock")}${this.valueRow("Mínimo desligado", Number.isFinite(effective.minimumOff) ? `${effective.minimumOff} min` : "Indisponível", "minimum_off_minutes", "mdi:timer-lock-outline")}${this.valueRow("Proteção entre modos", Number.isFinite(effective.modeProtection) ? `${effective.modeProtection} min` : "Indisponível", "mode_protection_minutes", "mdi:timer-cog")}${this.valueRow("Pausa manual", Number.isFinite(effective.manualPause) ? `${effective.manualPause} min` : "Indisponível", "manual_pause_minutes", "mdi:remote-off")}</div></div><div class="group"><h4>Bloqueios</h4><div class="value-list">${this.valueRow("Bloquear partida", policy.block_start ? "Sim" : "Não", "block_start", "mdi:play-circle-outline")}${this.valueRow("Bloquear desligamento automático", policy.block_automatic_off ? "Sim" : "Não", "block_automatic_off", "mdi:power-cycle")}${this.valueRow("Cancelar pausa manual", policy.cancel_manual_pause ? "Sim" : "Não", "cancel_manual_pause", "mdi:timer-remove")}</div></div></div>
          ${conflicts.length ? `<div class="section-head"><h3>Conflitos detectados</h3></div><div class="conflicts">${conflicts.map((conflict) => `<div>• ${esc(conflict)}</div>`).join("")}</div>` : ""}
        </div>
      </div></ha-card>`;
      this.querySelector("#toggle-agenda")?.addEventListener("click", async () => { await this._hass.callService("switch", agendaState ? "turn_off" : "turn_on", {}, { entity_id: AGENDA_SWITCH }); this.scheduleLoad(250); });
      this.querySelector("#reevaluate")?.addEventListener("click", async () => { await this._hass.callService("button", "press", {}, { entity_id: REEVALUATE_BUTTON }); this.scheduleLoad(250); });
      this.querySelector("#cancel-once")?.addEventListener("click", async () => { await this._hass.callService("button", "press", {}, { entity_id: CANCEL_BUTTON }); this.scheduleLoad(250); });
      this.querySelector("#expand")?.addEventListener("click", () => { this._expanded = !this._expanded; storageSet(`${DOMAIN}.policy.expanded`, String(this._expanded)); this.render(); });
    }
  }

  class ElginSupervisorPresetCard extends AgendaBase {
    reactiveEntityIds() {
      return [
        POLICY_ENTITY,
        "sensor.elgin_supervisor_presets_de_condicao",
        "sensor.elgin_supervisor_potencias",
        "sensor.elgin_supervisor_tratamento_desejado",
        "input_select.elgin_supervisor_tratamento_ativo",
        ...POLICY_REACTIVE_ENTITIES,
      ];
    }

    setConfig(config) {
      super.setConfig(config);
      this.data = null;
      this.activeMode = storageGet(`${DOMAIN}.presetsPower.mode`) || "heat";
      this.activeTab = storageGet(`${DOMAIN}.presetsPower.tab`) || "overview";
      if (!["overview", "presets", "profiles", "rules", "settings", "diagnostics"].includes(this.activeTab)) this.activeTab = "overview";
      this._status = "";
      this._statusError = false;
      this.render();
    }

    getCardSize() { return 16; }
    getGridOptions() { return { columns: 12, min_columns: 6, rows: 12, min_rows: 6 }; }

    onReactiveStateChange() { this.scheduleLoad(180); }

    async load() {
      if (!this._hass) return;
      if (this._loading) { this._pendingLoad = true; return; }
      this._loaded = true;
      this._loading = true;
      const requestId = ++this._requestSequence;
      try {
        const data = await this.ws("get_snapshot");
        if (this.acceptSnapshot(data, requestId)) {
          this.data = data;
          this.entryId = data.entry_id || this.entryId;
        }
      } catch (error) {
        if (requestId >= this._acceptedRequest) this.data = { error: error.message || String(error), presets: [], power_profiles: [], power_rules: [], power_settings: {}, preset_state: {}, power_state: {} };
      } finally {
        this.finishLoad();
      }
    }

    modeMeta(mode = this.activeMode) {
      const row = MODES.find(([value]) => value === mode) || MODES[0];
      return { id: row[0], label: row[1], icon: row[2] };
    }

    modeItems(source, mode = this.activeMode) {
      return toArray(source).filter((item) => item.mode === mode).sort((a, b) => Number(a.level) - Number(b.level) || String(a.name).localeCompare(String(b.name), "pt-BR"));
    }

    modeState(mode = this.activeMode) { return this.data?.power_state?.modes?.[mode] || {}; }
    presetModeState(mode = this.activeMode) { return this.data?.preset_state?.modes?.[mode] || {}; }

    flash(message, error = false) {
      this._status = message;
      this._statusError = error;
      this.render();
    }

    tabs() {
      const tabs = [
        ["overview", "Panorama", "mdi:view-dashboard-outline"],
        ["presets", "Presets", "mdi:tune-vertical"],
        ["profiles", "Perfis de potência", "mdi:speedometer"],
        ["rules", "Regras automáticas", "mdi:source-branch"],
        ["settings", "Limites e prioridades", "mdi:tune-variant"],
        ["diagnostics", "Diagnóstico", "mdi:clipboard-text-search-outline"],
      ];
      return `<div class="nav-tabs">${tabs.map(([id,label,icon]) => `<button class="secondary nav-tab ${this.activeTab === id ? "active" : ""}" data-tab="${id}"><ha-icon icon="${icon}"></ha-icon><span>${label}</span></button>`).join("")}</div>`;
    }

    modeTabs() {
      return `<div class="mode-tabs">${MODES.map(([mode,label,icon]) => `<button class="secondary mode-tab ${this.activeMode === mode ? "active" : ""}" data-mode="${mode}"><ha-icon icon="${icon}"></ha-icon>${label}</button>`).join("")}</div>`;
    }

    overview() {
      const power = this.data?.power_state || {};
      const preset = this.data?.preset_state || {};
      const decision = power.mode_decision || {};
      const active = power.active_mode;
      const cards = MODES.map(([mode,label,icon]) => {
        const ps = preset.modes?.[mode] || {};
        const ws = power.modes?.[mode] || {};
        const candidate = decision.candidates?.[mode] || {};
        return `<article class="mode-overview ${active === mode ? "in-use" : ""}">
          <header><ha-icon icon="${icon}"></ha-icon><div><strong>${label}</strong><small>${active === mode ? "Controlando agora" : candidate.eligible ? "Elegível" : "Em espera"}</small></div><span class="badge">${candidate.score ?? "—"} pts</span></header>
          <div class="kv"><span>Preset efetivo</span><b>${esc(ps.effective_name || "—")}</b></div>
          <div class="kv"><span>Potência base</span><b>${esc(ws.calculation_base_name || ws.base_name || "—")} · N${ws.calculation_base_level ?? "—"}</b></div>
          <div class="formula"><span>Base ${ws.calculation_base_level ?? 0}</span><span>Preset ${signed(ws.modifiers?.preset)}</span><span>Agenda ${signed(ws.modifiers?.agenda)}</span><span>Clima ${signed(ws.modifiers?.regional)}</span><span>Regras ${signed(ws.modifiers?.rules)}</span></div>
          <div class="result"><div><small>Nível calculado</small><strong>${ws.calculated_level ?? "—"}</strong></div><div><small>Perfil aplicado</small><strong>${esc(ws.effective_name || "—")}</strong></div><div><small>Comando</small><strong>${ws.target_temperature ?? "—"} °C · ${esc(ws.fan || "—")}</strong></div></div>
          ${toArray(ws.diagnostics).length ? `<div class="diag-note">${toArray(ws.diagnostics).map(esc).join(" · ")}</div>` : ""}
        </article>`;
      }).join("");
      return `<section class="panel"><div class="section-title"><div><h3>Panorama atual</h3><p>Limites selecionam o tratamento; prioridade resolve conflitos; o perfil determina a intensidade.</p></div><span class="chip active">${esc(decision.selected_name || "Nenhum modo")}</span></div>
        <div class="decision-strip"><div><small>Modo desejado</small><strong>${esc(decision.selected_name || "Nenhum")}</strong></div><div><small>Motivo</small><strong>${esc(decision.reason || "Sem avaliação")}</strong></div><div><small>Perfil em uso</small><strong>${esc(power.profile_in_use || "Nenhum")}</strong></div><div><small>Preset em uso</small><strong>${esc(preset.preset_in_use || "Nenhum")}</strong></div></div>
        <div class="mode-grid">${cards}</div>
      </section>`;
    }

    presetPanel() {
      const mode = this.activeMode;
      const items = this.modeItems(this.data?.presets, mode);
      const state = this.presetModeState(mode);
      const baseId = this.data?.base_presets?.[mode] || "";
      const manual = Number(state.manual_level_delta || 0);
      const agenda = Number(state.agenda_level_delta || 0);
      const regional = Number(state.regional_level_delta || 0);
      const baseLevel = Number(state.calculation_base_level ?? 0);
      const agendaSources = toArray(state.sources?.agenda_level);
      const nextTransition = this.data?.policy?.next_transition;
      const formula = `Base ${baseLevel} + Manual ${signed(manual)} + Agenda ${signed(agenda)} + Regional ${signed(regional)} = Nível ${state.calculated_level ?? "—"}`;
      return `<section class="panel">${this.modeTabs()}<div class="section-title"><div><h3>Presets de condição — ${this.modeMeta(mode).label}</h3><p>Definem quando o ciclo inicia e termina. Somente o preset efetivo do modo ativo participa da potência.</p></div><button id="new-preset"><ha-icon icon="mdi:plus"></ha-icon>Novo preset</button></div>
        <div class="config-row"><label>Preset base<select id="preset-base">${items.filter((p) => p.enabled).map((p) => `<option value="${esc(p.id)}" ${p.id === baseId ? "selected" : ""}>${esc(p.name)} · nível ${p.level}</option>`).join("")}</select></label><div class="mini-metric"><small>Nível calculado</small><strong>${state.calculated_level ?? "—"}</strong></div><div class="mini-metric"><small>Preset efetivo</small><strong>${esc(state.effective_name || "—")}</strong></div><div class="mini-metric"><small>Modificador de potência</small><strong>${signed(state.power_modifier)}</strong></div></div>
        <div class="calculation-card"><div><small>Cálculo completo</small><strong>${esc(formula)}</strong></div><div class="chip-row"><span class="chip ${manual ? "warn" : ""}">Manual ${signed(manual)}</span><span class="chip ${agenda ? "active" : ""}">Agenda ${signed(agenda)}</span><span class="chip ${regional ? "warn" : ""}">Regional ${signed(regional)}</span>${state.agenda_base_override ? '<span class="chip active">Base temporária da Agenda</span>' : ""}</div><div class="manual-adjust"><span>Ajuste manual persistente</span><button class="secondary icon-button" id="manual-minus" title="Reduzir ajuste manual"><ha-icon icon="mdi:minus"></ha-icon></button><strong>${signed(manual)}</strong><button class="secondary icon-button" id="manual-plus" title="Aumentar ajuste manual"><ha-icon icon="mdi:plus"></ha-icon></button><button class="secondary" id="manual-reset" ${manual === 0 ? "disabled" : ""}><ha-icon icon="mdi:restore"></ha-icon>Zerar</button></div>${agendaSources.length ? `<div class="source-list"><strong>Origem da Agenda</strong>${agendaSources.map((source) => `<span>${esc(source.rule)} · P${source.priority} · ${signed(source.value)}</span>`).join("")}${nextTransition ? `<span>Válido até a próxima transição: ${esc(fmtDateTime(nextTransition))} (${esc(fmtDuration(nextTransition))})</span>` : ""}</div>` : ""}${toArray(state.diagnostics).length ? `<div class="diag-note">${toArray(state.diagnostics).map(esc).join(" · ")}</div>` : ""}</div>
        <div class="catalog-grid">${items.map((item) => this.presetCard(item, state, baseId)).join("") || '<div class="empty">Nenhum preset neste modo.</div>'}</div>
      </section>`;
    }

    presetCard(item, state, baseId) {
      const isEffective = state.effective_id === item.id;
      return `<article class="catalog-card ${isEffective ? "effective" : ""}"><div class="card-head"><div class="chip-row"><span class="chip ${item.enabled ? "active" : "warn"}">${item.enabled ? "Habilitado" : "Desabilitado"}</span><span class="chip">Nível ${item.level}</span>${item.id === baseId ? '<span class="chip active">Base</span>' : ""}${isEffective ? '<span class="chip active">Efetivo</span>' : ""}</div><div class="card-actions"><button class="secondary icon-button edit-preset" data-id="${esc(item.id)}"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="secondary icon-button duplicate-preset" data-id="${esc(item.id)}"><ha-icon icon="mdi:content-copy"></ha-icon></button><button class="danger icon-button delete-preset" data-id="${esc(item.id)}" ${item.protected ? "disabled" : ""}><ha-icon icon="mdi:delete"></ha-icon></button></div></div><h4>${esc(item.name)}</h4><div class="profile-line">${item.mode === "dry" ? `${item.start}% → ${item.stop}% · mínima ${item.minimum_temperature} °C` : `${item.start} °C → ${item.stop} °C`} · potência ${signed(item.power_modifier)}</div><p>${esc(item.description || "Sem descrição")}</p></article>`;
    }

    profilesPanel() {
      const mode = this.activeMode;
      const items = this.modeItems(this.data?.power_profiles, mode);
      const state = this.modeState(mode);
      const baseId = this.data?.base_power_profiles?.[mode] || "";
      return `<section class="panel">${this.modeTabs()}<div class="section-title"><div><h3>Perfis de potência — ${this.modeMeta(mode).label}</h3><p>Temperatura-alvo e ventilação são persistentes e não estão limitadas a Fraco, Normal, Forte e Extremo.</p></div><div class="toolbar"><button class="secondary" id="restore-power"><ha-icon icon="mdi:restore"></ha-icon>Restaurar padrões</button><button id="new-profile"><ha-icon icon="mdi:plus"></ha-icon>Novo perfil</button></div></div>
        <div class="config-row"><label>Potência base e fallback<select id="power-base">${items.filter((p) => p.enabled).map((p) => `<option value="${esc(p.id)}" ${p.id === baseId ? "selected" : ""}>${esc(p.name)} · nível ${p.level}</option>`).join("")}</select></label><div class="mini-metric"><small>Nível calculado</small><strong>${state.calculated_level ?? "—"}</strong></div><div class="mini-metric"><small>Nível aplicado</small><strong>${state.applied_level ?? "—"}</strong></div><div class="mini-metric"><small>Perfil efetivo</small><strong>${esc(state.effective_name || "—")}</strong></div></div>
        <div class="catalog-grid">${items.map((item) => this.powerProfileCard(item, state, baseId)).join("") || '<div class="empty">Nenhum perfil neste modo.</div>'}</div>
      </section>`;
    }

    powerProfileCard(item, state, baseId) {
      const effective = state.effective_id === item.id;
      return `<article class="catalog-card ${effective ? "effective" : ""}"><div class="card-head"><div class="chip-row"><span class="chip ${item.enabled ? "active" : "warn"}">${item.enabled ? "Habilitado" : "Desabilitado"}</span><span class="chip">Nível ${item.level}</span>${item.id === baseId ? '<span class="chip active">Base/fallback</span>' : ""}${effective ? '<span class="chip active">Efetivo</span>' : ""}</div><div class="card-actions"><button class="secondary icon-button edit-profile" data-id="${esc(item.id)}"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="secondary icon-button duplicate-profile" data-id="${esc(item.id)}"><ha-icon icon="mdi:content-copy"></ha-icon></button><button class="danger icon-button delete-profile" data-id="${esc(item.id)}" ${item.protected ? "disabled" : ""}><ha-icon icon="mdi:delete"></ha-icon></button></div></div><h4>${esc(item.name)}</h4><div class="profile-line">${item.target_temperature} °C · ventilação ${esc(item.fan)}</div><p>${esc(item.description || "Sem descrição")}</p></article>`;
    }

    rulesPanel() {
      const rules = toArray(this.data?.power_rules);
      const diagnosticById = new Map(toArray(this.data?.power_state?.rules).map((item) => [item.id, item]));
      return `<section class="panel"><div class="section-title"><div><h3>Regras automáticas de potência</h3><p>Máquinas de estado com histerese. Regras independentes somam; grupos exclusivos contribuem uma por vez.</p></div><button id="new-rule"><ha-icon icon="mdi:plus"></ha-icon>Nova regra</button></div><div class="rule-grid">${rules.map((rule) => this.powerRuleCard(rule, diagnosticById.get(rule.id))).join("") || '<div class="empty">Nenhuma regra cadastrada. A potência será calculada pela base, preset, Agenda e clima regional.</div>'}</div></section>`;
    }

    powerRuleCard(rule, diag = {}) {
      const activeModes = Object.entries(diag.modes || {}).filter(([,state]) => state.active).map(([mode]) => MODE_LABELS[mode]);
      const adjustments = Object.entries(rule.adjustments || {}).filter(([,v]) => Number(v)).map(([mode,v]) => `${MODE_LABELS[mode]} ${signed(v)}`).join(" · ");
      const source = rule.source?.kind === "fixed" ? `valor fixo ${rule.source.value}` : `${rule.source?.entity_id || "sem entidade"}${rule.source?.attribute ? ` · ${rule.source.attribute}` : ""}`;
      return `<article class="rule-card ${activeModes.length ? "effective" : ""}"><div class="card-head"><div class="chip-row"><span class="chip ${rule.enabled ? "active" : "warn"}">${rule.enabled ? "Habilitada" : "Desabilitada"}</span>${activeModes.length ? `<span class="chip active">Ativa: ${esc(activeModes.join(", "))}</span>` : '<span class="chip">Inativa</span>'}${rule.exclusive_group ? `<span class="chip">Grupo ${esc(rule.exclusive_group)}</span>` : ""}</div><div class="card-actions"><button class="secondary icon-button edit-rule" data-id="${esc(rule.id)}"><ha-icon icon="mdi:pencil"></ha-icon></button><button class="secondary icon-button toggle-rule" data-id="${esc(rule.id)}" data-enabled="${rule.enabled}"><ha-icon icon="mdi:${rule.enabled ? "pause" : "play"}"></ha-icon></button><button class="danger icon-button delete-rule" data-id="${esc(rule.id)}"><ha-icon icon="mdi:delete"></ha-icon></button></div></div><h4>${esc(rule.name)}</h4><div class="rule-details"><span><b>Fonte:</b> ${esc(source)}</span><span><b>Referência:</b> ${esc(rule.reference?.kind || "—")}</span><span><b>Entrada:</b> ${esc(rule.entry_operator)} ${rule.entry_value}</span><span><b>Saída:</b> ${esc(rule.exit_operator)} ${rule.exit_value}</span><span><b>Ajustes:</b> ${esc(adjustments || "nenhum")}</span></div><p>${esc(rule.description || diag.last_reason || "Sem descrição")}</p></article>`;
    }

    settingsPanel() {
      const settings = this.data?.power_settings || {};
      const limits = settings.cycle_limits || {};
      const priorities = settings.priorities || {};
      return `<section class="panel"><div class="section-title"><div><h3>Limites locais dos ciclos</h3><p>Fonte única de verdade usada pelos presets base, pelas regras automáticas e pelo diagnóstico.</p></div><button id="save-settings"><ha-icon icon="mdi:content-save"></ha-icon>Salvar configurações</button></div>
        <div class="settings-grid">
          <article class="settings-card"><h4><ha-icon icon="mdi:radiator"></ha-icon>Aquecimento</h4><label>Iniciar abaixo de<input id="limit-heat-start" type="number" step="0.1" value="${limits.heat?.start ?? 16.5}"></label><label>Encerrar acima de<input id="limit-heat-stop" type="number" step="0.1" value="${limits.heat?.stop ?? 19.0}"></label></article>
          <article class="settings-card"><h4><ha-icon icon="mdi:snowflake"></ha-icon>Refrigeração</h4><label>Iniciar acima de<input id="limit-cool-start" type="number" step="0.1" value="${limits.cool?.start ?? 24.3}"></label><label>Encerrar abaixo de<input id="limit-cool-stop" type="number" step="0.1" value="${limits.cool?.stop ?? 22.3}"></label></article>
          <article class="settings-card"><h4><ha-icon icon="mdi:water-percent"></ha-icon>Desumidificação</h4><label>Iniciar acima de<input id="limit-dry-start" type="number" step="1" value="${limits.dry?.start ?? 65}"></label><label>Encerrar abaixo de<input id="limit-dry-stop" type="number" step="1" value="${limits.dry?.stop ?? 60}"></label><label>Temperatura mínima<input id="limit-dry-min" type="number" step="0.1" value="${limits.dry?.minimum_temperature ?? 20}"></label></article>
        </div>
        <div class="section-title sub"><div><h3>Prioridade e continuidade</h3><p>Escolhem qual tratamento atua quando mais de um modo está elegível; não alteram o nível de potência.</p></div></div>
        <div class="priority-grid">${MODES.map(([mode,label,icon]) => `<label class="priority-card"><ha-icon icon="${icon}"></ha-icon><span>${label}<small>Prioridade base</small></span><input id="priority-${mode}" type="number" min="0" max="1000" step="1" value="${priorities[mode] ?? (mode === "dry" ? 50 : 60)}"></label>`).join("")}<label class="priority-card"><ha-icon icon="mdi:repeat"></ha-icon><span>Bônus de continuidade<small>Favorece manter o tratamento atual</small></span><input id="continuity-bonus" type="number" min="0" max="1000" step="1" value="${settings.continuity_bonus ?? 10}"></label></div>
        <div class="status-line"><ha-icon icon="mdi:shield-clock-outline"></ha-icon> As proteções temporais permanecem na Configuração avançada. Este painel apenas informa quando uma proteção impede uma alteração.</div>
      </section>`;
    }

    diagnosticsPanel() {
      const snapshot = this.data?.snapshot || {};
      const integrity = this.data?.integrity || this.data?.policy?.integrity || { ok: true, issues: [] };
      const presetModes = this.data?.preset_state?.modes || {};
      const powerModes = this.data?.power_state?.modes || {};
      const readable = MODES.map(([mode,label,icon]) => {
        const preset = presetModes[mode] || {};
        const power = powerModes[mode] || {};
        return `<article class="diagnostic-mode"><h4><ha-icon icon="${icon}"></ha-icon>${label}</h4><div class="trace-line"><span>Preset</span><b>Base ${preset.calculation_base_name || "—"} N${preset.calculation_base_level ?? "—"} + Manual ${signed(preset.manual_level_delta)} + Agenda ${signed(preset.agenda_level_delta)} + Regional ${signed(preset.regional_level_delta)} = ${preset.effective_name || "—"} N${preset.effective_level ?? "—"}</b></div><div class="trace-line"><span>Potência</span><b>Base ${power.calculation_base_name || "—"} N${power.calculation_base_level ?? "—"} + Preset ${signed(power.modifiers?.preset)} + Agenda ${signed(power.modifiers?.agenda)} + Clima ${signed(power.modifiers?.regional)} + Regras ${signed(power.modifiers?.rules)} = ${power.effective_name || "—"} N${power.applied_level ?? "—"}</b></div><div class="trace-line"><span>Comando calculado</span><b>${power.target_temperature ?? "—"} °C · fan ${power.fan || "—"}</b></div></article>`;
      }).join("");
      const state = { snapshot, integrity, mode_decision: this.data?.power_state?.mode_decision, cycle_limits: this.data?.power_state?.cycle_limits, priorities: this.data?.power_state?.priorities, continuity_bonus: this.data?.power_state?.continuity_bonus, powers: powerModes, active_rules: this.data?.power_state?.active_rules, presets: presetModes, policy: this.data?.policy };
      return `<section class="panel"><div class="section-title"><div><h3>Diagnóstico ponta a ponta</h3><p>Leitura humana do mesmo snapshot atômico usado pela Agenda, presets, potência e Supervisor.</p></div><div class="chip-row"><span class="chip ${integrity.ok ? "active" : "error"}">${integrity.ok ? "Cadeia consistente" : `${toArray(integrity.issues).length} inconsistência(s)`}</span><span class="chip">Revisão ${snapshot.snapshot_revision ?? "—"}</span></div></div>${integrity.ok ? "" : `<div class="integrity-errors">${toArray(integrity.issues).map((issue) => `<div><b>${esc(issue.stage)} · ${esc(issue.mode || "global")}</b><span>${esc(issue.message)}</span></div>`).join("")}</div>`}<div class="diagnostic-grid">${readable}</div><details class="raw-diagnostic"><summary>JSON técnico completo</summary><div class="section-title sub"><div><p>Use este conteúdo para auditoria e suporte.</p></div><button class="secondary" id="copy-diagnostic"><ha-icon icon="mdi:content-copy"></ha-icon>Copiar</button></div><pre id="diagnostic-json">${esc(JSON.stringify(state, null, 2))}</pre></details></section>`;
    }

    render() {
      const body = this.activeTab === "overview" ? this.overview() : this.activeTab === "presets" ? this.presetPanel() : this.activeTab === "profiles" ? this.profilesPanel() : this.activeTab === "rules" ? this.rulesPanel() : this.activeTab === "settings" ? this.settingsPanel() : this.diagnosticsPanel();
      this.innerHTML = `<style>${sharedStyles}
        ha-card{background:var(--ha-card-background,var(--card-background-color))}.unified{padding:clamp(12px,1.8vw,22px)}
        .nav-tabs,.mode-tabs,.toolbar{display:flex;gap:8px;flex-wrap:wrap}.nav-tabs{margin:0 0 14px}.nav-tab.active,.mode-tab.active{border-color:var(--primary-color);background:color-mix(in srgb,var(--primary-color) 18%,var(--card-background-color))}
        .panel{display:grid;gap:14px}.section-title{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}.section-title.sub{margin-top:12px;border-top:1px solid var(--divider-color);padding-top:16px}.section-title h3{margin:0}.section-title p{margin:4px 0 0;color:var(--secondary-text-color)}
        .decision-strip,.config-row{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px}.decision-strip>div,.mini-metric{border:1px solid var(--divider-color);border-radius:14px;padding:12px;background:color-mix(in srgb,var(--secondary-background-color) 50%,transparent)}small{color:var(--secondary-text-color)}.decision-strip strong,.mini-metric strong{display:block;margin-top:4px;overflow-wrap:anywhere}
        .mode-grid,.catalog-grid,.rule-grid,.settings-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.mode-overview,.catalog-card,.rule-card,.settings-card{border:1px solid var(--divider-color);border-radius:17px;padding:14px;background:color-mix(in srgb,var(--secondary-background-color) 35%,transparent);min-width:0}.mode-overview.in-use,.catalog-card.effective,.rule-card.effective{border-color:color-mix(in srgb,var(--primary-color) 70%,var(--divider-color));box-shadow:0 0 0 1px color-mix(in srgb,var(--primary-color) 18%,transparent) inset}
        .mode-overview header,.card-head,.settings-card h4{display:flex;align-items:center;justify-content:space-between;gap:10px}.mode-overview header>div{flex:1}.mode-overview header small{display:block}.badge{border:1px solid var(--divider-color);border-radius:999px;padding:4px 8px}.kv{display:flex;justify-content:space-between;gap:10px;margin-top:10px}.kv span{color:var(--secondary-text-color)}.formula{display:flex;flex-wrap:wrap;gap:6px;margin:10px 0}.formula span{font-size:.78rem;padding:4px 7px;border-radius:999px;background:var(--secondary-background-color)}.result{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:8px}.result div{padding:8px;border-radius:10px;background:var(--secondary-background-color)}.result strong{display:block;margin-top:3px}.diag-note{margin-top:8px;color:var(--warning-color,#ff9800);font-size:.8rem}.calculation-card{margin:12px 0;padding:13px;border:1px solid var(--divider-color);border-radius:15px;background:color-mix(in srgb,var(--secondary-background-color) 45%,transparent);display:grid;gap:10px}.calculation-card small,.calculation-card strong{display:block}.manual-adjust{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.manual-adjust>span{margin-right:auto;color:var(--secondary-text-color)}.source-list{display:grid;gap:4px;font-size:.8rem;color:var(--secondary-text-color)}.source-list strong{color:var(--primary-text-color)}.diagnostic-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}.diagnostic-mode{border:1px solid var(--divider-color);border-radius:15px;padding:12px}.diagnostic-mode h4{margin:0 0 10px;display:flex;gap:7px;align-items:center}.trace-line{display:grid;gap:3px;margin-top:8px}.trace-line span{font-size:.75rem;color:var(--secondary-text-color)}.trace-line b{font-size:.82rem}.integrity-errors{display:grid;gap:7px;margin-bottom:12px}.integrity-errors>div{padding:10px;border:1px solid var(--error-color);border-radius:12px}.integrity-errors span{display:block;margin-top:3px}.raw-diagnostic{margin-top:14px}.raw-diagnostic summary{cursor:pointer;font-weight:700}
        .config-row{align-items:end}.config-row label{grid-column:span 1}.catalog-card h4,.rule-card h4{margin:10px 0 5px}.catalog-card p,.rule-card p{margin:6px 0 0;color:var(--secondary-text-color);font-size:.86rem}.profile-line{font-weight:600}.card-actions{display:flex;gap:5px}.rule-details{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;font-size:.82rem;color:var(--secondary-text-color)}
        label{display:block;color:var(--secondary-text-color);font-size:.82rem}input,select,textarea{box-sizing:border-box;width:100%;margin-top:5px;padding:10px;border:1px solid var(--divider-color);border-radius:10px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}.settings-card{display:grid;gap:10px}.settings-card h4{justify-content:flex-start;margin:0}.priority-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px}.priority-card{display:grid;grid-template-columns:auto minmax(0,1fr) 100px;align-items:center;gap:10px;padding:12px;border:1px solid var(--divider-color);border-radius:14px}.priority-card small{display:block}.priority-card input{margin:0}
        pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;max-height:70vh;overflow:auto;padding:14px;border-radius:14px;background:#111;color:#e6edf3;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}.empty{padding:20px;border:1px dashed var(--divider-color);border-radius:14px;color:var(--secondary-text-color)}
        dialog{border:0;border-radius:20px;background:var(--card-background-color);color:var(--primary-text-color);width:min(760px,calc(100vw - 24px));max-height:92vh;padding:0;box-shadow:var(--ha-card-box-shadow)}dialog::backdrop{background:rgba(0,0,0,.6)}.dialog-body{padding:20px;max-height:86vh;overflow:auto}.dialog-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.dialog-grid .full{grid-column:1/-1}.dialog-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:16px}
        @container(max-width:760px){.mode-grid,.catalog-grid,.rule-grid,.settings-grid,.decision-strip,.config-row,.priority-grid,.diagnostic-grid{grid-template-columns:1fr}.result{grid-template-columns:1fr}.section-title{display:grid}.nav-tab span{display:none}.rule-details{grid-template-columns:1fr}.priority-card{grid-template-columns:auto minmax(0,1fr) 84px}.dialog-grid{grid-template-columns:1fr}.dialog-grid .full{grid-column:auto}}
      </style><ha-card><div class="unified"><div class="title-row"><div><div class="eyebrow">Configuração consolidada</div><h2>Presets e Potência</h2><p>Condições do ciclo, prioridade do modo, perfis dinâmicos, regras de intensidade e diagnóstico.</p></div><span class="chip active"><ha-icon icon="mdi:database-check-outline"></ha-icon>Persistência local</span></div>${this.data?.error ? `<ha-alert alert-type="error">${esc(this.data.error)}</ha-alert>` : ""}${this._status ? `<div class="status-line ${this._statusError ? "error" : ""}">${esc(this._status)}</div>` : ""}${this.tabs()}${body}<dialog id="unified-editor"><div class="dialog-body" id="unified-editor-body"></div></dialog></div></ha-card>`;
      this.bind();
    }

    bind() {
      this.querySelectorAll(".nav-tab").forEach((button) => button.addEventListener("click", () => { this.activeTab = button.dataset.tab; storageSet(`${DOMAIN}.presetsPower.tab`, this.activeTab); this.render(); }));
      this.querySelectorAll(".mode-tab").forEach((button) => button.addEventListener("click", () => { this.activeMode = button.dataset.mode; storageSet(`${DOMAIN}.presetsPower.mode`, this.activeMode); this.render(); }));
      this.querySelector("#preset-base")?.addEventListener("change", async (event) => this.action("set_base_preset", { mode: this.activeMode, preset_id: event.target.value }, "Preset base atualizado."));
      const setManualPresetDelta = async (value) => {
        const entityId = PRESET_MANUAL_ADJUST_ENTITIES[this.activeMode];
        if (!entityId) return;
        try {
          await this._hass.callService("input_number", "set_value", { value }, { entity_id: entityId });
          this._status = `Ajuste manual de ${MODE_LABELS[this.activeMode]} atualizado para ${signed(value)}.`;
          this._statusError = false;
          this.scheduleLoad(250);
        } catch (error) { this.flash(error.message || String(error), true); }
      };
      const currentManual = Number(this.presetModeState(this.activeMode).manual_level_delta || 0);
      this.querySelector("#manual-minus")?.addEventListener("click", () => setManualPresetDelta(currentManual - 1));
      this.querySelector("#manual-plus")?.addEventListener("click", () => setManualPresetDelta(currentManual + 1));
      this.querySelector("#manual-reset")?.addEventListener("click", () => setManualPresetDelta(0));
      this.querySelector("#power-base")?.addEventListener("change", async (event) => this.action("set_base_power_profile", { mode: this.activeMode, profile_id: event.target.value }, "Potência base e fallback atualizados."));
      this.querySelector("#new-preset")?.addEventListener("click", () => this.openPresetEditor({ mode: this.activeMode, enabled: true, level: 0, start: this.activeMode === "dry" ? 65 : this.activeMode === "heat" ? 16.5 : 24.3, stop: this.activeMode === "dry" ? 60 : this.activeMode === "heat" ? 19 : 22.3, minimum_temperature: 20, power_modifier: 0 }));
      this.querySelectorAll(".edit-preset").forEach((button) => button.addEventListener("click", () => this.openPresetEditor(deepClone(toArray(this.data?.presets).find((item) => item.id === button.dataset.id)))));
      this.querySelectorAll(".duplicate-preset").forEach((button) => button.addEventListener("click", async () => { const mode = window.prompt("Modo da cópia: heat, cool ou dry", this.activeMode); if (mode && ["heat","cool","dry"].includes(mode)) await this.action("duplicate_preset", { preset_id: button.dataset.id, mode }, "Preset duplicado; revise antes de habilitar."); }));
      this.querySelectorAll(".delete-preset").forEach((button) => button.addEventListener("click", async () => { if (!button.disabled && confirm("Excluir este preset e reparar suas referências?")) await this.action("delete_preset", { preset_id: button.dataset.id }, "Preset excluído."); }));
      this.querySelector("#new-profile")?.addEventListener("click", () => this.openProfileEditor({ mode: this.activeMode, enabled: true, level: 0, target_temperature: this.activeMode === "heat" ? 24 : this.activeMode === "cool" ? 23 : 24, fan: "low" }));
      this.querySelectorAll(".edit-profile").forEach((button) => button.addEventListener("click", () => this.openProfileEditor(deepClone(toArray(this.data?.power_profiles).find((item) => item.id === button.dataset.id)))));
      this.querySelectorAll(".duplicate-profile").forEach((button) => button.addEventListener("click", async () => { const mode = window.prompt("Modo da cópia: heat, cool ou dry", this.activeMode); if (mode && ["heat","cool","dry"].includes(mode)) await this.action("duplicate_power_profile", { profile_id: button.dataset.id, mode }, "Perfil duplicado."); }));
      this.querySelectorAll(".delete-profile").forEach((button) => button.addEventListener("click", async () => { if (!button.disabled && confirm("Excluir este perfil? Referências inválidas serão diagnosticadas e o modo usará seu fallback.")) await this.action("delete_power_profile", { profile_id: button.dataset.id }, "Perfil excluído."); }));
      this.querySelector("#restore-power")?.addEventListener("click", async () => { if (confirm("Restaurar somente os 12 perfis padrões protegidos? Perfis personalizados serão preservados. O Supervisor deve estar desativado e o modo sombra ativo.")) await this.action("restore_default_power_profiles", {}, "Perfis padrões restaurados."); });
      this.querySelector("#new-rule")?.addEventListener("click", () => this.openRuleEditor({ enabled: true, source: { kind: "entity", variable: "temperature", entity_id: "sensor.sensor_temperatura_sensor_dedicado", attribute: "" }, reference: { kind: "cycle_end", entity_id: "", attribute: "", value: 0 }, operation: "directional_by_mode", entry_operator: "ge", entry_value: 8, exit_operator: "le", exit_value: 6, adjustments: { heat: 2, cool: 2, dry: 0 }, modes: ["heat","cool"], exclusive_group: "", priority: 0 }));
      this.querySelectorAll(".edit-rule").forEach((button) => button.addEventListener("click", () => this.openRuleEditor(deepClone(toArray(this.data?.power_rules).find((item) => item.id === button.dataset.id)))));
      this.querySelectorAll(".toggle-rule").forEach((button) => button.addEventListener("click", async () => this.action("set_power_rule_enabled", { rule_id: button.dataset.id, enabled: button.dataset.enabled !== "true" }, "Estado da regra atualizado.")));
      this.querySelectorAll(".delete-rule").forEach((button) => button.addEventListener("click", async () => { if (confirm("Excluir esta regra dinâmica?")) await this.action("delete_power_rule", { rule_id: button.dataset.id }, "Regra excluída."); }));
      this.querySelector("#save-settings")?.addEventListener("click", () => this.saveSettings());
      this.querySelector("#copy-diagnostic")?.addEventListener("click", async () => { try { await navigator.clipboard.writeText(this.querySelector("#diagnostic-json")?.textContent || ""); this.flash("Diagnóstico copiado."); } catch (error) { this.flash(error.message || String(error), true); } });
    }

    async action(type, payload, success) {
      try { await this.ws(type, payload); this._status = success; this._statusError = false; await this.load(); }
      catch (error) { this.flash(error.message || String(error), true); }
    }

    async saveSettings() {
      const number = (id) => Number(this.querySelector(id)?.value);
      const settings = { cycle_limits: { heat: { start: number("#limit-heat-start"), stop: number("#limit-heat-stop") }, cool: { start: number("#limit-cool-start"), stop: number("#limit-cool-stop") }, dry: { start: number("#limit-dry-start"), stop: number("#limit-dry-stop"), minimum_temperature: number("#limit-dry-min") } }, priorities: { heat: number("#priority-heat"), cool: number("#priority-cool"), dry: number("#priority-dry") }, continuity_bonus: number("#continuity-bonus") };
      await this.action("update_power_settings", { settings }, "Limites, prioridades e bônus atualizados.");
    }

    editorShell(title, subtitle, content, saveId) {
      return `<div class="section-title"><div><h3>${esc(title)}</h3><p>${esc(subtitle)}</p></div><button class="secondary icon-button close-editor"><ha-icon icon="mdi:close"></ha-icon></button></div>${content}<div class="dialog-actions"><button class="secondary close-editor">Cancelar</button><button id="${saveId}"><ha-icon icon="mdi:content-save"></ha-icon>Salvar</button></div>`;
    }

    openPresetEditor(item) {
      if (!item) return;
      const dialog = this.querySelector("#unified-editor"), body = this.querySelector("#unified-editor-body"); if (!dialog || !body) return;
      const existing = Boolean(item.id), mode = item.mode || this.activeMode;
      body.innerHTML = this.editorShell(existing ? `Editar ${item.name}` : "Novo preset de condição", existing ? `ID imutável: ${item.id}` : "O modo será imutável depois da criação.", `<div class="dialog-grid"><label>Modo<select id="e-mode" ${existing ? "disabled" : ""}>${MODES.map(([m,l]) => `<option value="${m}" ${m === mode ? "selected" : ""}>${l}</option>`).join("")}</select></label><label>Nome<input id="e-name" value="${esc(item.name || "")}"></label><label>Nível<input id="e-level" type="number" step="1" value="${item.level ?? 0}"></label><label>Modificador de potência<input id="e-modifier" type="number" step="1" value="${item.power_modifier ?? 0}"></label><label>Condição de início<input id="e-start" type="number" step="${mode === "dry" ? 1 : .1}" value="${item.start ?? ""}"></label><label>Condição de encerramento<input id="e-stop" type="number" step="${mode === "dry" ? 1 : .1}" value="${item.stop ?? ""}"></label><label class="dry-field">Temperatura mínima do Dry<input id="e-min" type="number" step="0.1" value="${item.minimum_temperature ?? 20}"></label><label>Estado<select id="e-enabled"><option value="true" ${item.enabled !== false ? "selected" : ""}>Habilitado</option><option value="false" ${item.enabled === false ? "selected" : ""}>Desabilitado</option></select></label><label class="full">Descrição<textarea id="e-description">${esc(item.description || "")}</textarea></label></div>`, "save-editor");
      const sync = () => { body.querySelector(".dry-field").hidden = body.querySelector("#e-mode").value !== "dry"; }; sync(); body.querySelector("#e-mode")?.addEventListener("change", sync);
      this.bindDialogClose(dialog); body.querySelector("#save-editor").addEventListener("click", async () => { const m = body.querySelector("#e-mode").value; const preset = { ...(existing ? item : {}), mode:m, name:body.querySelector("#e-name").value.trim(), level:Number(body.querySelector("#e-level").value), power_modifier:Number(body.querySelector("#e-modifier").value), start:Number(body.querySelector("#e-start").value), stop:Number(body.querySelector("#e-stop").value), minimum_temperature:m === "dry" ? Number(body.querySelector("#e-min").value) : null, enabled:body.querySelector("#e-enabled").value === "true", description:body.querySelector("#e-description").value.trim() }; try { await this.ws("save_preset", { preset }); closeDialog(dialog); this.activeMode=m; this._status="Preset salvo."; await this.load(); } catch(error){ alert(error.message || error); } }); openDialog(dialog);
    }

    openProfileEditor(item) {
      if (!item) return;
      const dialog = this.querySelector("#unified-editor"), body = this.querySelector("#unified-editor-body"); if (!dialog || !body) return;
      const existing = Boolean(item.id), mode = item.mode || this.activeMode;
      body.innerHTML = this.editorShell(existing ? `Editar ${item.name}` : "Novo perfil de potência", existing ? `ID imutável: ${item.id}` : "Temperatura e ventilação serão usadas no comando final.", `<div class="dialog-grid"><label>Modo<select id="e-mode" ${existing ? "disabled" : ""}>${MODES.map(([m,l]) => `<option value="${m}" ${m===mode?"selected":""}>${l}</option>`).join("")}</select></label><label>Nome<input id="e-name" value="${esc(item.name || "")}"></label><label>Nível inteiro<input id="e-level" type="number" step="1" value="${item.level ?? 0}"></label><label>Temperatura-alvo<input id="e-target" type="number" min="16" max="30" step="1" value="${item.target_temperature ?? 24}"></label><label>Ventilação<select id="e-fan">${["auto","low","medium","high"].map((fan) => `<option value="${fan}" ${item.fan===fan?"selected":""}>${fan}</option>`).join("")}</select></label><label>Estado<select id="e-enabled"><option value="true" ${item.enabled!==false?"selected":""}>Habilitado</option><option value="false" ${item.enabled===false?"selected":""}>Desabilitado</option></select></label><label class="full">Descrição<textarea id="e-description">${esc(item.description || "")}</textarea></label></div>`, "save-editor");
      this.bindDialogClose(dialog); body.querySelector("#save-editor").addEventListener("click", async () => { const m=body.querySelector("#e-mode").value; const profile={...(existing?item:{}),mode:m,name:body.querySelector("#e-name").value.trim(),level:Number(body.querySelector("#e-level").value),target_temperature:Number(body.querySelector("#e-target").value),fan:body.querySelector("#e-fan").value,enabled:body.querySelector("#e-enabled").value==="true",description:body.querySelector("#e-description").value.trim()}; try{await this.ws("save_power_profile",{profile});closeDialog(dialog);this.activeMode=m;this._status="Perfil de potência salvo.";await this.load();}catch(error){alert(error.message||error);}}); openDialog(dialog);
    }

    openRuleEditor(rule) {
      if (!rule) return;
      const dialog=this.querySelector("#unified-editor"),body=this.querySelector("#unified-editor-body");if(!dialog||!body)return;
      const existing=Boolean(rule.id),adjust=rule.adjustments||{};
      body.innerHTML=this.editorShell(existing?`Editar ${rule.name}`:"Nova regra automática",existing?`ID imutável: ${rule.id}`:"A entrada ativa a contribuição; a saída a remove. Não há ajuste inverso.",`<div class="dialog-grid"><label>Nome<input id="r-name" value="${esc(rule.name||"")}"></label><label>Estado<select id="r-enabled"><option value="true" ${rule.enabled!==false?"selected":""}>Habilitada</option><option value="false" ${rule.enabled===false?"selected":""}>Desabilitada</option></select></label><label>Fonte<select id="r-source-kind"><option value="entity" ${rule.source?.kind!=="fixed"?"selected":""}>Entidade</option><option value="fixed" ${rule.source?.kind==="fixed"?"selected":""}>Valor fixo</option></select></label><label>Tipo da variável<select id="r-variable">${[["temperature","Temperatura"],["humidity","Umidade"],["number","Número"]].map(([v,l])=>`<option value="${v}" ${rule.source?.variable===v?"selected":""}>${l}</option>`).join("")}</select></label><label>Entidade observada<input id="r-entity" value="${esc(rule.source?.entity_id||"")}" placeholder="sensor..."></label><label>Atributo da medição<input id="r-attribute" value="${esc(rule.source?.attribute||"")}"></label><label>Valor fixo da medição<input id="r-source-value" type="number" step="0.1" value="${rule.source?.value??0}"></label><label>Referência<select id="r-reference">${[["cycle_end","Fim do ciclo do modo"],["cycle_start","Início do ciclo do modo"],["preset_end","Fim do preset efetivo"],["preset_start","Início do preset efetivo"],["dry_minimum","Temperatura mínima do Dry"],["fixed","Valor fixo"],["entity","Outra entidade"]].map(([v,l])=>`<option value="${v}" ${rule.reference?.kind===v?"selected":""}>${l}</option>`).join("")}</select></label><label>Operação<select id="r-operation">${[["directional_by_mode","Diferença direcional por modo"],["current_minus_reference","Valor atual − referência"],["reference_minus_current","Referência − valor atual"],["absolute_difference","Diferença absoluta"]].map(([v,l])=>`<option value="${v}" ${rule.operation===v?"selected":""}>${l}</option>`).join("")}</select></label><label>Entidade de referência<input id="r-ref-entity" value="${esc(rule.reference?.entity_id||"")}" placeholder="sensor..."></label><label>Atributo da referência<input id="r-ref-attribute" value="${esc(rule.reference?.attribute||"")}"></label><label>Valor/referência fixa<input id="r-ref-value" type="number" step="0.1" value="${rule.reference?.value??0}"></label><label>Entrada<select id="r-entry-op">${[["ge",">="],["gt",">"],["le","<="],["lt","<"]].map(([v,l])=>`<option value="${v}" ${rule.entry_operator===v?"selected":""}>${l}</option>`).join("")}</select><input id="r-entry" type="number" step="0.1" value="${rule.entry_value??8}"></label><label>Saída<select id="r-exit-op">${[["le","<="],["lt","<"],["ge",">="],["gt",">"]].map(([v,l])=>`<option value="${v}" ${rule.exit_operator===v?"selected":""}>${l}</option>`).join("")}</select><input id="r-exit" type="number" step="0.1" value="${rule.exit_value??6}"></label>${MODES.map(([m,l])=>`<label>Ajuste ${l}<input id="r-${m}" type="number" step="1" value="${adjust[m]??0}"></label>`).join("")}<label>Grupo exclusivo opcional<input id="r-group" value="${esc(rule.exclusive_group||"")}"></label><label>Prioridade no grupo<input id="r-priority" type="number" step="1" value="${rule.priority??0}"></label><label class="full">Descrição<textarea id="r-description">${esc(rule.description||"")}</textarea></label><div class="full status-line" id="r-preview"></div></div>`,"save-editor");
      const refreshPreview=()=>this.updateRulePreview(body); body.querySelectorAll("input,select").forEach((element)=>element.addEventListener("input",refreshPreview)); refreshPreview();
      this.bindDialogClose(dialog);body.querySelector("#save-editor").addEventListener("click",async()=>{const adjustments={heat:Number(body.querySelector("#r-heat").value),cool:Number(body.querySelector("#r-cool").value),dry:Number(body.querySelector("#r-dry").value)};const modes=Object.entries(adjustments).filter(([,v])=>v!==0).map(([m])=>m);const next={...(existing?rule:{}),name:body.querySelector("#r-name").value.trim(),enabled:body.querySelector("#r-enabled").value==="true",source:{kind:body.querySelector("#r-source-kind").value,variable:body.querySelector("#r-variable").value,entity_id:body.querySelector("#r-entity").value.trim(),attribute:body.querySelector("#r-attribute").value.trim(),value:Number(body.querySelector("#r-source-value").value)},reference:{kind:body.querySelector("#r-reference").value,value:Number(body.querySelector("#r-ref-value").value),entity_id:body.querySelector("#r-ref-entity").value.trim(),attribute:body.querySelector("#r-ref-attribute").value.trim()},operation:body.querySelector("#r-operation").value,entry_operator:body.querySelector("#r-entry-op").value,entry_value:Number(body.querySelector("#r-entry").value),exit_operator:body.querySelector("#r-exit-op").value,exit_value:Number(body.querySelector("#r-exit").value),adjustments,modes,exclusive_group:body.querySelector("#r-group").value.trim(),priority:Number(body.querySelector("#r-priority").value),description:body.querySelector("#r-description").value.trim()};try{await this.ws("save_power_rule",{rule:next});closeDialog(dialog);this._status="Regra automática salva.";await this.load();}catch(error){alert(error.message||error);}});openDialog(dialog);
    }

    updateRulePreview(body) {
      const output=body.querySelector("#r-preview"); if(!output) return;
      const sourceKind=body.querySelector("#r-source-kind")?.value||"entity";
      const variable=body.querySelector("#r-variable")?.value||"number";
      let current=null;
      if(sourceKind==="fixed") current=Number(body.querySelector("#r-source-value")?.value);
      else { const entityId=body.querySelector("#r-entity")?.value.trim(); const attribute=body.querySelector("#r-attribute")?.value.trim(); const state=this._hass?.states?.[entityId]; const raw=attribute?state?.attributes?.[attribute]:state?.state; current=raw!==undefined&&raw!==null&&!["unknown","unavailable","none",""] .includes(String(raw).toLowerCase())?Number(raw):null; if(!Number.isFinite(current)) current=null; }
      const refKind=body.querySelector("#r-reference")?.value||"cycle_end";
      const op=body.querySelector("#r-operation")?.value||"directional_by_mode";
      const entryOp=body.querySelector("#r-entry-op")?.value||"ge"; const entry=Number(body.querySelector("#r-entry")?.value); const exitOp=body.querySelector("#r-exit-op")?.value||"le"; const exit=Number(body.querySelector("#r-exit")?.value);
      const rows=[];
      MODES.forEach(([mode,label])=>{ const adjustment=Number(body.querySelector(`#r-${mode}`)?.value||0); if(!adjustment) return; let reference=null; if(refKind==="fixed") reference=Number(body.querySelector("#r-ref-value")?.value); else if(refKind==="entity"){const id=body.querySelector("#r-ref-entity")?.value.trim();const attr=body.querySelector("#r-ref-attribute")?.value.trim();const state=this._hass?.states?.[id];const raw=attr?state?.attributes?.[attr]:state?.state;reference=Number(raw);if(!Number.isFinite(reference))reference=null;} else if(refKind==="cycle_start"||refKind==="cycle_end"){reference=Number(this.data?.power_settings?.cycle_limits?.[mode]?.[refKind==="cycle_start"?"start":"stop"]);} else if(refKind==="preset_start"||refKind==="preset_end"){reference=Number(this.data?.preset_state?.modes?.[mode]?.[refKind==="preset_start"?"start":"stop"]);} else if(refKind==="dry_minimum"){reference=mode==="dry"?Number(this.data?.power_settings?.cycle_limits?.dry?.minimum_temperature):null;} let difference=null; if(current!==null&&reference!==null&&Number.isFinite(reference)){if(op==="current_minus_reference")difference=current-reference;else if(op==="reference_minus_current")difference=reference-current;else if(op==="absolute_difference")difference=Math.abs(current-reference);else if(variable==="temperature"&&mode==="heat")difference=Math.max(0,reference-current);else difference=Math.max(0,current-reference);} rows.push(`<div><b>${label}</b>: atual ${current===null?"indisponível":current} · referência ${reference===null||!Number.isFinite(reference)?"indisponível":reference} · diferença ${difference===null?"—":difference.toFixed(1)} · ajuste ${signed(adjustment)}</div>`); });
      output.innerHTML=`<b>Prévia</b><div>Entrada: diferença ${esc(entryOp)} ${entry} · Saída: diferença ${esc(exitOp)} ${exit}</div>${rows.join("")||"<div>Defina ao menos um ajuste diferente de zero.</div>"}`;
    }

    bindDialogClose(dialog) { this.querySelectorAll(".close-editor").forEach((button) => button.addEventListener("click", () => closeDialog(dialog))); }
  }


  class ElginSupervisorAgendaCalendarCard extends AgendaBase {
    setConfig(config) {
      super.setConfig(config);
      const now = new Date();
      this.cursor = new Date(now.getFullYear(), now.getMonth(), 1);
      this.occurrences = [];
      this.selected = null;
      this.render();
    }
    getCardSize() { return 10; }
    getGridOptions() { return { columns: 12, min_columns: 6, rows: 8, min_rows: 5 }; }

    monthRange() {
      const first = new Date(this.cursor.getFullYear(), this.cursor.getMonth(), 1);
      const mondayIndex = (first.getDay() + 6) % 7;
      const start = new Date(first); start.setDate(first.getDate() - mondayIndex);
      const end = new Date(start); end.setDate(start.getDate() + 42);
      return { start, end };
    }

    async load() {
      if (!this._hass || this._loading) return;
      this._loaded = true; this._loading = true;
      try {
        const { start, end } = this.monthRange();
        const response = await this.ws("get_occurrences", { start: start.toISOString(), end: end.toISOString() });
        this.entryId = response.entry_id || this.entryId;
        this.occurrences = toArray(response.occurrences);
      } catch (error) { this.error = error.message || String(error); }
      finally { this._loading = false; this.render(); }
    }

    eventsForDay(date) {
      const start = new Date(date.getFullYear(), date.getMonth(), date.getDate());
      const end = new Date(start); end.setDate(end.getDate() + 1);
      return this.occurrences.filter((event) => new Date(event.start) < end && new Date(event.end) > start).sort((a, b) => Number(b.priority || 0) - Number(a.priority || 0));
    }

    calendarCells() {
      const first = new Date(this.cursor.getFullYear(), this.cursor.getMonth(), 1);
      const mondayIndex = (first.getDay() + 6) % 7;
      const gridStart = new Date(first); gridStart.setDate(first.getDate() - mondayIndex);
      const cells = [];
      for (let i = 0; i < 42; i += 1) { const date = new Date(gridStart); date.setDate(gridStart.getDate() + i); cells.push(date); }
      return cells;
    }

    render() {
      const todayKey = new Date().toDateString();
      const cells = this.calendarCells();
      const upcoming = [...this.occurrences].filter((event) => new Date(event.end) > new Date()).sort((a, b) => new Date(a.start) - new Date(b.start)).slice(0, 10);
      this.innerHTML = `<style>${sharedStyles}
        .calendar-card{padding:clamp(10px,1.5vw,18px)}.calendar-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:12px}.month-nav{display:flex;align-items:center;gap:7px}.month-title{min-width:170px;text-align:center;font-size:1.08rem;font-weight:700}.calendar-layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(240px,.8fr);gap:12px}.month-grid{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));border:1px solid var(--divider-color);border-radius:14px;overflow:hidden}.weekday-head{padding:8px 4px;text-align:center;font-size:.72rem;text-transform:uppercase;color:var(--secondary-text-color);background:var(--secondary-background-color);border-right:1px solid var(--divider-color)}.day{min-height:92px;padding:6px;border-top:1px solid var(--divider-color);border-right:1px solid var(--divider-color);background:var(--card-background-color);min-width:0}.day.other{opacity:.42}.day.today{box-shadow:inset 0 0 0 2px var(--primary-color)}.day-number{font-size:.78rem;font-weight:700;margin-bottom:5px}.event-pill{display:block;width:100%;text-align:left;border:0;border-radius:7px;padding:4px 6px;margin:3px 0;background:color-mix(in srgb,var(--primary-color) 18%,var(--secondary-background-color));color:var(--primary-text-color);font-size:.7rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.event-pill.high{background:color-mix(in srgb,var(--error-color) 16%,var(--secondary-background-color))}.more{font-size:.68rem;color:var(--secondary-text-color);padding:2px}.upcoming{border:1px solid var(--divider-color);border-radius:14px;padding:11px;min-width:0}.upcoming h3{margin:0 0 9px}.upcoming-list{display:grid;gap:7px;max-height:540px;overflow:auto}.upcoming-item{border:1px solid var(--divider-color);border-radius:11px;padding:9px;cursor:pointer}.upcoming-item strong,.upcoming-item small{display:block}.upcoming-item small{color:var(--secondary-text-color);margin-top:3px}.detail{margin-top:10px;padding:10px;border-radius:11px;background:var(--secondary-background-color);font-size:.82rem}.detail h4{margin:0 0 6px}.calendar-legend{display:flex;flex-wrap:wrap;gap:8px;margin:0 0 10px;font-size:.75rem;color:var(--secondary-text-color)}.legend-dot{width:9px;height:9px;border-radius:50%;display:inline-block;background:color-mix(in srgb,var(--primary-color) 55%,var(--secondary-background-color));margin-right:4px}.legend-dot.high{background:color-mix(in srgb,var(--error-color) 65%,var(--secondary-background-color))}
        @container(max-width:850px){.calendar-layout{grid-template-columns:1fr}.upcoming-list{max-height:280px}.day{min-height:78px}}
        @container(max-width:520px){.calendar-head{align-items:flex-start;flex-direction:column}.month-nav{width:100%;justify-content:space-between}.month-title{min-width:0}.weekday-head{font-size:.62rem}.day{min-height:62px;padding:3px}.event-pill{font-size:0;width:8px;height:8px;padding:0;border-radius:50%;display:inline-block;margin:2px}.day-number{font-size:.7rem}.calendar-card{padding:8px}}
      </style><ha-card><div class="calendar-card"><div class="calendar-head"><div><div class="eyebrow">Ocorrências expandidas</div><h2 style="margin:3px 0 0">Calendário da Agenda</h2></div><div class="month-nav"><button class="secondary icon-button" id="prev"><ha-icon icon="mdi:chevron-left"></ha-icon></button><button class="secondary" id="today">Hoje</button><div class="month-title">${MONTHS_LONG[this.cursor.getMonth()]} de ${this.cursor.getFullYear()}</div><button class="secondary icon-button" id="next"><ha-icon icon="mdi:chevron-right"></ha-icon></button></div></div>${this.error ? `<ha-alert alert-type="error">${esc(this.error)}</ha-alert>` : ""}<div class="calendar-legend"><span><i class="legend-dot"></i>Prioridade abaixo de 80</span><span><i class="legend-dot high"></i>Prioridade 80 ou maior</span><span>Toque em uma ocorrência para ver todos os efeitos</span></div><div class="calendar-layout"><div class="month-grid">${WEEKDAYS.map((day) => `<div class="weekday-head">${day}</div>`).join("")}${cells.map((date) => { const events = this.eventsForDay(date); const sameMonth = date.getMonth() === this.cursor.getMonth(); return `<div class="day ${sameMonth ? "" : "other"} ${date.toDateString() === todayKey ? "today" : ""}"><div class="day-number">${date.getDate()}</div>${events.slice(0, 3).map((event) => `<button class="event-pill ${Number(event.priority || 0) >= 80 ? "high" : ""}" data-id="${esc(event.rule_id)}" data-start="${esc(event.start)}" title="P${Number(event.priority || 0)} · ${esc(event.name)}">P${Number(event.priority || 0)} · ${esc(event.name)}</button>`).join("")}${events.length > 3 ? `<div class="more">+${events.length - 3}</div>` : ""}</div>`; }).join("")}</div><aside class="upcoming"><h3>Próximas ocorrências</h3><div class="upcoming-list">${upcoming.length ? upcoming.map((event) => `<div class="upcoming-item" data-id="${esc(event.rule_id)}" data-start="${esc(event.start)}"><strong>P${Number(event.priority || 0)} · ${esc(event.name)}</strong><small>${fmtDateTime(event.start, { weekday: "short", day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" })} → ${fmtDateTime(event.end, { hour: "2-digit", minute: "2-digit" })}</small></div>`).join("") : '<div class="muted">Nenhuma ocorrência neste mês.</div>'}</div>${this.selected ? `<div class="detail"><h4>${esc(this.selected.name)}</h4><div>Prioridade ${Number(this.selected.priority || 0)}</div><div>${fmtDateTime(this.selected.start)} → ${fmtDateTime(this.selected.end)}</div><div class="chip-row" style="margin-top:7px">${toArray(this.selected.effects).map((effect) => `<span class="chip">${esc(typeof effect === "string" ? effect : effect.type)}</span>`).join("")}</div>${this.selected.notes ? `<p>${esc(this.selected.notes)}</p>` : ""}</div>` : ""}</aside></div></div></ha-card>`;
      this.querySelector("#prev")?.addEventListener("click", () => { this.cursor = new Date(this.cursor.getFullYear(), this.cursor.getMonth() - 1, 1); this.selected = null; this.load(); });
      this.querySelector("#next")?.addEventListener("click", () => { this.cursor = new Date(this.cursor.getFullYear(), this.cursor.getMonth() + 1, 1); this.selected = null; this.load(); });
      this.querySelector("#today")?.addEventListener("click", () => { const now = new Date(); this.cursor = new Date(now.getFullYear(), now.getMonth(), 1); this.selected = null; this.load(); });
      this.querySelectorAll("[data-id][data-start]").forEach((element) => element.addEventListener("click", () => { this.selected = this.occurrences.find((event) => event.rule_id === element.dataset.id && event.start === element.dataset.start) || null; this.render(); }));
    }
  }

  class ElginSupervisorPresetLegacyCard extends ElginSupervisorPresetCard {}

  const registrations = [
    ["elgin-supervisor-agenda-card", ElginSupervisorAgendaCard],
    ["elgin-supervisor-agenda-policy-card", ElginSupervisorAgendaPolicyCard],
    ["elgin-supervisor-agenda-calendar-card", ElginSupervisorAgendaCalendarCard],
    ["elgin-supervisor-presets-power-card", ElginSupervisorPresetCard],
    ["elgin-supervisor-preset-card", ElginSupervisorPresetLegacyCard],
  ];
  registrations.forEach(([tag, klass]) => {
    if (!customElements.get(tag)) customElements.define(tag, klass);
  });

  window.customCards = Array.isArray(window.customCards) ? window.customCards : [];
  const cardMetadata = [
    {
      type: "elgin-supervisor-agenda-policy-card",
      name: "Elgin Agenda — Política temporal",
      description: "Política temporal efetiva, regras ativas e origem dos overrides",
      preview: false,
    },
    {
      type: "elgin-supervisor-agenda-card",
      name: "Elgin Agenda — Editor de regras",
      description: "Criação e edição de regras recorrentes do Supervisor",
      preview: false,
    },
    {
      type: "elgin-supervisor-presets-power-card",
      name: "Elgin Supervisor — Presets e Potência",
      description: "Configuração consolidada de presets, perfis de potência, regras automáticas, limites, prioridades e diagnóstico.",
      preview: false,
      documentationURL: "https://www.home-assistant.io/dashboards/",
    },
    {
      type: "elgin-supervisor-preset-card",
      name: "Elgin Supervisor — Presets e Potência",
      description: "Configuração consolidada de presets, perfis dinâmicos, regras, limites, prioridades e diagnóstico",
      preview: false,
    },
    {
      type: "elgin-supervisor-agenda-calendar-card",
      name: "Elgin Agenda — Calendário",
      description: "Calendário local e próximas ocorrências da Agenda",
      preview: false,
    },
  ];
  cardMetadata.forEach((metadata) => {
    if (!window.customCards.some((card) => card.type === metadata.type)) {
      window.customCards.push(metadata);
    }
  });

  console.info(`[Elgin Supervisor Agenda] quatro cards registrados; painel unificado de Presets e Potência ativo (${BUILD_TARGET})`);
})();
