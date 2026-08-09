(() => {
  "use strict";

  const DOMAIN = "elgin_supervisor_diagnostico";
  const CARD_TAG = "elgin-supervisor-diagnostico-card";
  const PICKER_TAG = "elgin-diagnostic-multiselect";
  const BUILD = "diagnostico-observabilidade-20260809.3";

  const TABS = [
    ["overview", "Panorama", "mdi:view-dashboard-outline"],
    ["timeline", "Linha do tempo", "mdi:timeline-clock-outline"],
    ["decisions", "Decisões", "mdi:state-machine"],
    ["states", "Mudanças de estado", "mdi:swap-horizontal"],
    ["actions", "Ações e transmissões", "mdi:remote"],
    ["external", "Alterações externas", "mdi:account-arrow-right-outline"],
    ["anomalies", "Anomalias", "mdi:alert-decagram-outline"],
    ["observations", "Observações", "mdi:notebook-edit-outline"],
    ["statistics", "Estatísticas", "mdi:chart-box-outline"],
    ["settings", "Configurações", "mdi:cog-outline"],
    ["export", "Exportação", "mdi:file-export-outline"],
  ];

  const EVENT_TABS = new Set([
    "timeline", "decisions", "states", "actions", "external", "observations",
  ]);

  const FILTER_TABS = new Set([...EVENT_TABS, "statistics"]);

  const FACET_FILTERS = [
    ["categories", "Categoria"],
    ["event_types", "Tipo"],
    ["severities", "Severidade"],
    ["outcomes", "Resultado"],
    ["actors", "Ator"],
    ["users", "Usuário"],
    ["origins", "Origem"],
    ["entities", "Entidade"],
    ["domains", "Domínio"],
    ["modes", "Modo climático"],
    ["treatments", "Tratamento"],
    ["presets", "Preset"],
    ["power_profiles", "Potência"],
    ["agendas", "Agenda"],
    ["protections", "Proteção"],
    ["audibilities", "Audibilidade"],
    ["activation_models", "Modelo de ativação"],
    ["functions", "Função"],
  ];

  const BOOLEAN_FILTERS = [
    ["is_external", "Alteração externa"],
    ["is_anomaly", "Anomalia"],
    ["has_transmission", "Possui transmissão"],
    ["has_error", "Possui erro"],
    ["has_change", "Possui mudança"],
    ["has_correlation", "Possui correlação"],
  ];

  const DEFAULT_OPERATORS = [
    ["eq", "é"], ["ne", "não é"], ["contains", "contém"],
    ["not_contains", "não contém"], ["exists", "existe"],
    ["not_exists", "não existe"], ["changed", "mudou"],
    ["not_changed", "não mudou"], ["gt", "maior que"], ["gte", "maior ou igual"],
    ["lt", "menor que"], ["lte", "menor ou igual"], ["in", "está em"],
    ["not_in", "não está em"], ["starts", "começa com"], ["ends", "termina com"], ["between", "entre"],
    ["before", "antes de"], ["after", "depois de"],
  ];

  const DEFAULT_QUICK_FILTERS = [
    { value: "errors", label: "Erros", icon: "mdi:alert-circle", filters: { has_error: true } },
    { value: "transmissions", label: "Transmissões", icon: "mdi:remote", filters: { has_transmission: true } },
    { value: "external", label: "Mudanças externas", icon: "mdi:account-arrow-right", filters: { is_external: true } },
    { value: "decisions", label: "Decisões", icon: "mdi:state-machine", filters: { categories: ["decision", "evaluation"] } },
    { value: "blocked", label: "Bloqueios", icon: "mdi:shield-lock", filters: { outcomes: ["blocked", "suppressed"] } },
    { value: "ifeel", label: "I Feel", icon: "mdi:thermometer-auto", filters: { text: "I Feel" } },
    { value: "cool", label: "Cool", icon: "mdi:snowflake", filters: { modes: ["cool"] } },
    { value: "heat", label: "Heat", icon: "mdi:radiator", filters: { modes: ["heat"] } },
    { value: "dry", label: "Dry", icon: "mdi:water-percent", filters: { modes: ["dry"] } },
    { value: "today", label: "Hoje", icon: "mdi:calendar-today", period: "today" },
    { value: "last_hour", label: "Última hora", icon: "mdi:clock-outline", period: "last_hour" },
  ];

  const DEFAULT_SETTINGS = {
    capture_mode: "normal",
    capture_decisions: true,
    capture_state_changes: true,
    capture_service_calls: true,
    capture_localtuya: true,
    capture_climate: true,
    capture_agenda: true,
    capture_presets: true,
    capture_power_profiles: true,
    capture_protections: true,
    capture_errors: true,
    capture_external_changes: true,
    retention_essential_days: 60,
    retention_error_days: 30,
    retention_trace_days: 7,
    compaction_enabled: true,
    compaction_window_seconds: 60,
    compact_identical_evaluations: true,
    compact_no_change: true,
    compact_identical_states: true,
    compact_repeated_blocks: true,
    compact_repeated_unavailable: true,
    rate_window_seconds: 60,
    rate_warning_events: 500,
    rate_hard_limit_events: 2000,
    correlation_window_seconds: 30,
    localtuya_confirmation_window_seconds: 30,
    external_observation_window_seconds: 60,
    beep_window_before_seconds: 120,
    beep_window_after_seconds: 120,
    anomalies_enabled: true,
    anomaly_enabled_types: ["commands_too_close", "repeated_commands", "decision_oscillation", "desired_state_divergence", "localtuya_not_confirmed", "external_change_reaction", "excessive_volume", "repeated_error", "critical_entity_unavailable"],
    anomaly_close_commands_seconds: 2,
    anomaly_repeated_command_window_seconds: 300,
    anomaly_oscillation_window_seconds: 600,
    anomaly_oscillation_min_changes: 4,
    anomaly_divergence_seconds: 60,
    anomaly_volume_window_seconds: 60,
    anomaly_volume_event_limit: 1000,
    anomaly_repeated_error_window_seconds: 300,
    anomaly_repeated_error_count: 3,
    anomaly_unavailable_seconds: 120,
    anomaly_no_change_threshold: 100,
    anomaly_duplicate_window_seconds: 10,
    anomaly_audible_burst_seconds: 20,
    anomaly_audible_burst_count: 3,
    anomaly_window_minutes: 15,
    notifications_enabled: false,
    notification_min_severity: "warning",
    notification_types: ["commands_too_close", "repeated_commands", "decision_oscillation", "desired_state_divergence", "localtuya_not_confirmed", "external_change_reaction", "excessive_volume", "repeated_error", "critical_entity_unavailable"],
    notification_cooldown_seconds: 900,
    notification_persistent: true,
    notification_service: "",
    interface_items_per_page: 50,
    interface_auto_refresh: true,
    interface_columns: ["occurred_at", "severity", "category", "summary", "actor", "origin", "entity_id", "before", "after", "outcome", "correlation_id"],
    interface_density: "comfortable",
    interface_show_technical_codes: false,
    interface_show_unchanged_attributes: false,
    interface_date_format: "locale",
    interface_detail_mode: "panel",
    saved_filters: [],
    default_saved_filter_id: "",
    privacy_resolve_user_names: true,
    privacy_store_user_ids: true,
    privacy_store_user_names: true,
    privacy_capture_raw_events: true,
    privacy_capture_service_data: true,
    privacy_redact_sensitive_values: true,
    maintenance_database_limit_mb: 250,
    maintenance_cleanup_interval_hours: 6,
    maintenance_export_max_rows: 50000,
    queue_limit: 5000,
    critical_queue_limit: 2000,
    batch_size: 100,
    flush_interval_seconds: 0.25,
    anonymize_entity_ids: false,
  };

  const LEGACY_SETTING_ALIASES = {
    capture_state_changes: ["capture_state_changed"],
    capture_power_profiles: ["capture_power"],
    localtuya_confirmation_window_seconds: ["localtuya_confirmation_seconds"],
    external_observation_window_seconds: ["external_observation_seconds"],
    notification_service: ["notify_service"],
    interface_items_per_page: ["default_page_size"],
    interface_auto_refresh: ["auto_update"],
    interface_density: ["density"],
    interface_columns: ["columns"],
    interface_show_technical_codes: ["show_technical_codes"],
    interface_show_unchanged_attributes: ["show_unchanged_attributes"],
    interface_date_format: ["date_format"],
    interface_detail_mode: ["detail_mode"],
  };

  const OPERATOR_LABELS = new Map(DEFAULT_OPERATORS);
  const CODE_LABELS = {
    info: "Informação", warning: "Atenção", error: "Erro", critical: "Crítico", success: "Sucesso",
    decision: "Decisão", evaluation: "Avaliação", state_change: "Mudança de estado",
    action: "Ação", transmission: "Transmissão", external: "Alteração externa",
    observation: "Observação", user_observation: "Observação do usuário", anomaly: "Anomalia",
    cool: "Refrigeração · Cool", heat: "Aquecimento · Heat", dry: "Desumidificação · Dry",
    fan_only: "Ventilação", off: "Desligado", blocked: "Bloqueado", suppressed: "Suprimido",
    confirmed: "Confirmado", failed: "Falhou", observed_by_user: "Observado pelo usuário",
    audible_expected: "Audível esperado", silent_expected: "Silencioso esperado",
    no_ir_transmission: "Sem transmissão IR", unknown: "Não determinado",
  };

  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);

  const asArray = (value) => {
    if (Array.isArray(value)) return value;
    if (value === null || value === undefined || value === "") return [];
    return [value];
  };

  const asObject = (value) => {
    if (value && typeof value === "object" && !Array.isArray(value)) return value;
    if (typeof value === "string" && value.trim()) {
      try {
        const parsed = JSON.parse(value);
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
      } catch (_error) {
        return {};
      }
    }
    return {};
  };

  const clone = (value) => {
    if (value === undefined) return undefined;
    try { return structuredClone(value); } catch (_error) {
      try { return JSON.parse(JSON.stringify(value)); } catch (_jsonError) { return value; }
    }
  };

  const canonicalSettings = (value) => {
    const source = asObject(value);
    const result = {};
    Object.keys(DEFAULT_SETTINGS).forEach((key) => {
      if (source[key] !== undefined) {
        result[key] = clone(source[key]);
        return;
      }
      const alias = asArray(LEGACY_SETTING_ALIASES[key]).find((name) => source[name] !== undefined);
      if (alias) result[key] = clone(source[alias]);
    });
    return result;
  };

  const humanizeCode = (value) => String(value || "")
    .replace(/[._-]+/g, " ")
    .replace(/\b\w/g, (letter) => letter.toLocaleUpperCase("pt-BR"));

  const localInputValue = (value) => {
    const date = value instanceof Date ? value : new Date(value);
    return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 19);
  };

  const storageGet = (key, fallback = null) => {
    try {
      const value = localStorage.getItem(key);
      return value === null ? fallback : JSON.parse(value);
    } catch (_error) {
      return fallback;
    }
  };

  const storageSet = (key, value) => {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (_error) { /* restricted WebView */ }
  };

  const isEmptyObject = (value) => !value || !Object.keys(value).length;

  const formatBytes = (value) => {
    const size = Number(value || 0);
    if (!Number.isFinite(size) || size <= 0) return "0 B";
    if (size < 1024) return `${Math.round(size)} B`;
    if (size < 1024 ** 2) return `${(size / 1024).toFixed(1)} KB`;
    if (size < 1024 ** 3) return `${(size / 1024 ** 2).toFixed(1)} MB`;
    return `${(size / 1024 ** 3).toFixed(2)} GB`;
  };

  const formatDuration = (milliseconds) => {
    const value = Number(milliseconds);
    if (!Number.isFinite(value)) return "—";
    if (value < 1000) return `${Math.round(value)} ms`;
    if (value < 60000) return `${(value / 1000).toFixed(1)} s`;
    return `${(value / 60000).toFixed(1)} min`;
  };

  const normalizeOption = (item) => {
    if (item && typeof item === "object") {
      const value = item.value ?? item.id ?? item.key ?? item.name ?? "";
      return {
        ...item,
        value: String(value),
        label: String(item.label ?? item.name ?? value),
        count: item.count ?? null,
      };
    }
    return { value: String(item ?? ""), label: String(item ?? ""), count: null };
  };

  const normalizeItems = (response, primary = "items", alternative = "events") => {
    if (Array.isArray(response)) return response;
    return asArray(response?.[primary] ?? response?.[alternative] ?? response?.data);
  };

  const getEventId = (event) => event?.event_id ?? event?.id ?? event?.observation_id ?? "";

  const getObservationId = (event) => {
    const details = asObject(event?.details_json ?? event?.details);
    return event?.observation_id ?? details.observation_id ?? "";
  };

  const semanticValue = (value) => {
    if (value === undefined) return "Ausente";
    if (value === null) return "Nulo";
    if (value === "unknown") return "unknown · valor desconhecido pelo Home Assistant";
    if (value === "unavailable") return "unavailable · fonte indisponível";
    if (value === true) return "Sim";
    if (value === false) return "Não";
    if (typeof value === "object") {
      try { return JSON.stringify(value); } catch (_error) { return String(value); }
    }
    return String(value);
  };

  const flattenSnapshot = (snapshot) => {
    if (snapshot === null || snapshot === undefined) return snapshot;
    const source = asObject(snapshot);
    const attributes = asObject(source.attributes);
    return {
      state: source.state,
      ...attributes,
    };
  };

  const comparisonRows = (before, after, diff) => {
    if (before === null && after === null) return [];
    const left = before === null ? null : flattenSnapshot(before);
    const right = after === null ? null : flattenSnapshot(after);
    const changes = asObject(diff);
    const keys = new Set([
      ...Object.keys(left || {}),
      ...Object.keys(right || {}),
      ...Object.keys(changes || {}),
    ]);
    return [...keys].sort().map((field) => {
      const change = asObject(changes[field]);
      const hasStructuredChange = Object.prototype.hasOwnProperty.call(changes, field);
      const beforeValue = change.before_present === false
        ? undefined
        : Object.prototype.hasOwnProperty.call(change, "before") ? change.before : left?.[field];
      const afterValue = change.after_present === false
        ? undefined
        : Object.prototype.hasOwnProperty.call(change, "after") ? change.after : right?.[field];
      let valuesEqual = beforeValue === afterValue;
      if (!valuesEqual && beforeValue && afterValue && typeof beforeValue === "object" && typeof afterValue === "object") {
        try { valuesEqual = JSON.stringify(beforeValue) === JSON.stringify(afterValue); } catch (_error) { /* unequal */ }
      }
      return {
        field,
        before: beforeValue,
        after: afterValue,
        changed: hasStructuredChange || !valuesEqual,
      };
    });
  };

  class ElginDiagnosticMultiselect extends HTMLElement {
    constructor() {
      super();
      this._options = [];
      this._selected = [];
      this._mounted = false;
    }

    connectedCallback() {
      if (this._mounted) return;
      this._mounted = true;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = `
        <style>
          :host{display:block;min-width:0;color:var(--primary-text-color)}
          *{box-sizing:border-box}details{position:relative}summary{list-style:none;min-height:40px;padding:8px 34px 8px 10px;border:1px solid var(--divider-color);border-radius:10px;background:var(--card-background-color);cursor:pointer;position:relative;font-size:.85rem}summary::-webkit-details-marker{display:none}summary:after{content:"▾";position:absolute;right:11px;top:9px;color:var(--secondary-text-color)}
          .placeholder{color:var(--secondary-text-color)}.chips{display:flex;gap:4px;flex-wrap:wrap}.chip{display:inline-flex;align-items:center;border-radius:999px;padding:2px 7px;background:color-mix(in srgb,var(--primary-color) 14%,var(--secondary-background-color));font-size:.72rem;max-width:180px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
          .popup{position:absolute;z-index:30;left:0;right:0;top:calc(100% + 4px);padding:8px;border:1px solid var(--divider-color);border-radius:12px;background:var(--card-background-color);box-shadow:var(--ha-card-box-shadow,0 8px 30px rgba(0,0,0,.25));min-width:240px}.search{width:100%;padding:8px;border:1px solid var(--divider-color);border-radius:8px;background:var(--secondary-background-color);color:var(--primary-text-color);font:inherit}.options{max-height:240px;overflow:auto;margin-top:7px;display:grid;gap:2px}.option{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;padding:7px;border-radius:8px;font-size:.82rem}.option:hover{background:var(--secondary-background-color)}.option input{margin:0}.count{color:var(--secondary-text-color);font-variant-numeric:tabular-nums}.empty{padding:12px;color:var(--secondary-text-color);text-align:center}
          :focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
        </style>
        <details>
          <summary aria-label="Abrir seleção múltipla"><span class="selection placeholder">Todas</span></summary>
          <div class="popup">
            <input class="search" type="search" placeholder="Buscar opções" aria-label="Buscar opções">
            <div class="options" role="listbox" aria-multiselectable="true"></div>
          </div>
        </details>`;
      this._search = root.querySelector(".search");
      this._optionsNode = root.querySelector(".options");
      this._selectionNode = root.querySelector(".selection");
      this._search.addEventListener("input", () => this._renderOptions());
      root.addEventListener("change", (event) => {
        const input = event.target.closest("input[data-value]");
        if (!input) return;
        const value = input.dataset.value;
        this._selected = input.checked
          ? [...new Set([...this._selected, value])]
          : this._selected.filter((item) => item !== value);
        this._renderSelection();
        this.dispatchEvent(new CustomEvent("change", { bubbles: true, composed: true }));
      });
      this._renderOptions();
      this._renderSelection();
    }

    set label(value) {
      this.setAttribute("aria-label", value || "Seleção múltipla");
      if (this.shadowRoot) this.shadowRoot.querySelector("summary")?.setAttribute("aria-label", `Selecionar ${value}`);
    }

    setOptions(options) {
      this._options = asArray(options).map(normalizeOption).filter((item) => item.value);
      const available = new Set(this._options.map((item) => item.value));
      this._selected = this._selected.filter((item) => available.has(item) || item);
      if (this._mounted) {
        this._renderOptions();
        this._renderSelection();
      }
    }

    setValue(values) {
      this._selected = [...new Set(asArray(values).map(String).filter(Boolean))];
      if (this._mounted) {
        this._renderOptions();
        this._renderSelection();
      }
    }

    getValue() { return [...this._selected]; }

    _renderSelection() {
      if (!this._selectionNode) return;
      this._selectionNode.replaceChildren();
      if (!this._selected.length) {
        this._selectionNode.className = "selection placeholder";
        this._selectionNode.textContent = "Todas";
        return;
      }
      this._selectionNode.className = "selection chips";
      this._selected.slice(0, 3).forEach((value) => {
        const item = this._options.find((option) => option.value === value);
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = item?.label || value;
        this._selectionNode.append(chip);
      });
      if (this._selected.length > 3) {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = `+${this._selected.length - 3}`;
        this._selectionNode.append(chip);
      }
    }

    _renderOptions() {
      if (!this._optionsNode) return;
      const query = String(this._search?.value || "").trim().toLocaleLowerCase("pt-BR");
      const visible = this._options.filter((item) => !query || `${item.label} ${item.value}`.toLocaleLowerCase("pt-BR").includes(query));
      const fragment = document.createDocumentFragment();
      visible.forEach((item) => {
        const label = document.createElement("label");
        label.className = "option";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.dataset.value = item.value;
        input.checked = this._selected.includes(item.value);
        input.setAttribute("role", "option");
        input.setAttribute("aria-selected", String(input.checked));
        const text = document.createElement("span");
        text.textContent = item.label;
        const count = document.createElement("span");
        count.className = "count";
        count.textContent = item.count === null || item.count === undefined ? "" : String(item.count);
        label.append(input, text, count);
        fragment.append(label);
      });
      if (!visible.length) {
        const empty = document.createElement("div");
        empty.className = "empty";
        empty.textContent = "Nenhuma opção";
        fragment.append(empty);
      }
      this._optionsNode.replaceChildren(fragment);
    }
  }

  if (!customElements.get(PICKER_TAG)) customElements.define(PICKER_TAG, ElginDiagnosticMultiselect);

  class ElginSupervisorDiagnosticoCard extends HTMLElement {
    constructor() {
      super();
      this._config = {};
      this._hass = null;
      this._entryId = null;
      this._mounted = false;
      this._initialized = false;
      this._initializing = null;
      this._subscribing = false;
      this._unsubscribe = null;
      this._connected = false;
      this._requestSerial = 0;
      this._activeTab = "overview";
      this._snapshot = {};
      this._catalog = { facets: {}, fields: [], operators: [], quick_filters: [] };
      this._statistics = {};
      this._anomalies = [];
      this._deletedObservationIds = new Set();
      this._filterDraft = { relevant_only: true };
      this._appliedFilters = {};
      this._advancedGroups = [{ operator: "and", conditions: [{ field: "", operator: "eq", value: "" }] }];
      this._savedFilters = [];
      this._settingsSaved = clone(DEFAULT_SETTINGS);
      this._settingsDraft = clone(DEFAULT_SETTINGS);
      this._settingsDirty = false;
      this._pendingEvents = 0;
      this._detailEvent = null;
      this._detailEvaluation = null;
      this._detailCorrelation = [];
      this._activeDetailTab = "comparison";
      this._viewStates = new Map();
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
    }

    static getStubConfig() { return {}; }

    setConfig(config) {
      const previousEntry = this._entryId;
      this._config = config || {};
      this._entryId = this._config.entry_id || this._entryId || null;
      this._ensureMounted();
      if (previousEntry && this._entryId && previousEntry !== this._entryId) {
        this._resetForEntry();
      }
      this._restoreLocalState();
      this._tryInitialize();
    }

    set hass(hass) {
      this._hass = hass;
      this._ensureMounted();
      this._updateAdminControls();
      this._tryInitialize();
      this._subscribe();
    }

    get hass() { return this._hass; }

    connectedCallback() {
      this._connected = true;
      this._ensureMounted();
      this._tryInitialize();
      this._subscribe();
    }

    disconnectedCallback() {
      this._connected = false;
      const unsubscribe = this._unsubscribe;
      this._unsubscribe = null;
      this._subscribing = false;
      if (unsubscribe) {
        try {
          const result = unsubscribe();
          if (result && typeof result.catch === "function") result.catch(() => undefined);
        } catch (_error) { /* connection already closed */ }
      }
    }

    getCardSize() { return 18; }

    getGridOptions() {
      return { columns: "full", min_columns: 6 };
    }

    _newViewState() {
      return {
        items: [],
        total: null,
        nextCursor: null,
        previousCursor: null,
        cursor: null,
        loaded: false,
        loading: false,
        requestId: 0,
        fingerprint: "",
        direction: "older",
        hasMore: false,
        atLatest: true,
        atOldest: false,
      };
    }

    _resetForEntry() {
      this._initialized = false;
      this._snapshot = {};
      this._statistics = {};
      this._anomalies = [];
      this._pendingEvents = 0;
      this._viewStates.clear();
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
    }

    _storageKey(suffix) {
      const user = this._hass?.user?.id || this._hass?.user?.name || "local";
      return `${DOMAIN}.${this._entryId || "default"}.${user}.${suffix}`;
    }

    _restoreLocalState() {
      const tab = storageGet(this._storageKey("active_tab"), this._activeTab);
      if (TABS.some(([id]) => id === tab)) this._activeTab = tab;
      this._savedFilters = storageGet(this._storageKey("saved_filters"), []);
      if (!Array.isArray(this._savedFilters)) this._savedFilters = [];
      const defaultFilter = this._savedFilters.find((item) => item.is_default);
      if (defaultFilter && isEmptyObject(this._appliedFilters)) {
        this._filterDraft = { relevant_only: true, ...clone(defaultFilter.filters || {}) };
        this._appliedFilters = clone(this._normalizeFilterPayload(this._filterDraft));
        this._advancedGroups = clone(defaultFilter.advanced || this._advancedGroups);
      }
      if (this._mounted) {
        this._activateTabDom();
        this._renderSavedFilterOptions();
      }
    }

    _ensureMounted() {
      if (this._mounted) return;
      this._mounted = true;
      const root = this.attachShadow({ mode: "open" });
      root.innerHTML = this._template();
      this._cacheNodes();
      this._bindStaticEvents();
      this._activateTabDom();
      this._renderAdvancedBuilder();
      this._renderQuickFilters();
      this._renderSavedFilterOptions();
      this._updatePendingBanner();
      this._applyInterfaceSettings();
    }

    _template() {
      const tabs = TABS.map(([id, label, icon]) => `
        <button class="tab" type="button" role="tab" aria-selected="false" aria-controls="panel-${id}" data-tab="${id}">
          <ha-icon icon="${icon}"></ha-icon><span>${label}</span>
        </button>`).join("");
      const facetPickers = FACET_FILTERS.map(([key, label]) => `
        <label class="field"><span>${label}</span><${PICKER_TAG} data-filter="${key}"></${PICKER_TAG}></label>`).join("");
      const booleanFilters = BOOLEAN_FILTERS.map(([key, label]) => `
        <label class="field"><span>${label}</span><select data-filter="${key}"><option value="">Qualquer</option><option value="true">Sim</option><option value="false">Não</option></select></label>`).join("");
      const operatorOptions = DEFAULT_OPERATORS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
      return `
        <style>${this._styles()}</style>
        <ha-card class="diagnostic-card">
          <header class="hero">
            <div class="hero-title">
              <div class="eyebrow">Elgin Supervisor · observabilidade local</div>
              <h1>Diagnóstico</h1>
              <p>Reconstrua decisões, comandos, confirmações, mudanças externas e possíveis causas de bips sem alterar o controle climático.</p>
            </div>
            <div class="hero-actions">
              <button type="button" class="accent observation-beep" data-action="open-beep"><ha-icon icon="mdi:volume-high"></ha-icon>Registrar bip agora</button>
              <button type="button" class="secondary" data-action="refresh-current"><ha-icon icon="mdi:refresh"></ha-icon>Atualizar</button>
            </div>
          </header>

          <ha-alert id="status-banner" hidden></ha-alert>

          <section id="pending-banner" class="pending-banner" hidden aria-live="polite">
            <div><ha-icon icon="mdi:timeline-plus"></ha-icon><strong id="pending-label">0 novos eventos</strong><span>A análise atual foi preservada.</span></div>
            <button type="button" data-action="load-new"><ha-icon icon="mdi:download"></ha-icon>Carregar novos eventos</button>
          </section>

          <nav class="tabs" role="tablist" aria-label="Áreas do diagnóstico">${tabs}</nav>

          <section id="query-toolbar" class="query-toolbar" aria-label="Busca e filtros">
            <label class="global-search"><ha-icon icon="mdi:magnify"></ha-icon><input id="global-search" type="search" placeholder="Buscar resumo, entidade, usuário, regra, preset, potência, ação ou correlação" aria-label="Busca textual global"><button type="button" class="icon-button" data-action="clear-search" aria-label="Limpar busca"><ha-icon icon="mdi:close"></ha-icon></button></label>
            <button type="button" class="secondary" data-action="toggle-filters" aria-expanded="false"><ha-icon icon="mdi:filter-variant"></ha-icon>Filtros <span id="filter-count" class="count-badge">0</span></button>
            <label class="saved-select"><span class="sr-only">Filtro salvo</span><select id="saved-filter-select" aria-label="Abrir filtro salvo"><option value="">Filtros salvos</option></select></label>
            <button type="button" class="secondary icon-button" data-action="save-filter" aria-label="Salvar consulta atual"><ha-icon icon="mdi:content-save-outline"></ha-icon></button>
            <button type="button" class="secondary icon-button saved-filter-tool" data-action="rename-filter" aria-label="Renomear filtro salvo"><ha-icon icon="mdi:rename-outline"></ha-icon></button>
            <button type="button" class="secondary icon-button saved-filter-tool" data-action="delete-filter" aria-label="Excluir filtro salvo"><ha-icon icon="mdi:delete-outline"></ha-icon></button>
          </section>
          <div id="quick-filters" class="quick-filters" aria-label="Filtros rápidos"></div>

          <section id="filter-panel" class="filter-panel" hidden>
            <div class="filter-panel-head">
              <div><h2>Filtros</h2><p>As opções e contagens vêm do banco de diagnóstico. Categoria e Tipo aceitam múltiplos valores.</p></div>
              <div class="button-row"><button type="button" class="secondary" data-action="clear-filters">Limpar</button><button type="button" data-action="apply-filters">Aplicar filtros</button></div>
            </div>
            <details open>
              <summary>Período e classificação</summary>
              <div class="filter-grid period-grid">
                <label class="field"><span>De</span><input type="datetime-local" step="1" data-filter="start"></label>
                <label class="field"><span>Até</span><input type="datetime-local" step="1" data-filter="end"></label>
                ${facetPickers}
                <label class="field"><span>Temperatura ambiente · mínima °C</span><input type="number" step="0.1" data-filter="temperature_min"></label>
                <label class="field"><span>Temperatura ambiente · máxima °C</span><input type="number" step="0.1" data-filter="temperature_max"></label>
                <label class="field"><span>Temperatura-alvo · mínima °C</span><input type="number" step="0.1" data-filter="target_temperature_min"></label>
                <label class="field"><span>Temperatura-alvo · máxima °C</span><input type="number" step="0.1" data-filter="target_temperature_max"></label>
                ${booleanFilters}
              </div>
            </details>
            <details>
              <summary>Alteração antes / depois / diferença</summary>
              <div class="filter-grid change-grid">
                <label class="field"><span>Campo alterado contém</span><${PICKER_TAG} data-filter="changed_fields"></${PICKER_TAG}></label>
                <label class="field"><span>Campo no estado anterior</span><input data-filter="before_field" placeholder="Ex.: mode"></label>
                <label class="field"><span>Operador do estado anterior</span><select data-filter="before_operator">${operatorOptions}</select></label>
                <label class="field"><span>Valor anterior</span><input data-filter="before_value" placeholder="Ex.: cool"></label>
                <label class="field"><span>Campo no estado novo</span><input data-filter="after_field" placeholder="Ex.: mode"></label>
                <label class="field"><span>Operador do estado novo</span><select data-filter="after_operator">${operatorOptions}</select></label>
                <label class="field"><span>Valor novo</span><input data-filter="after_value" placeholder="Ex.: off"></label>
                <label class="field"><span>Campo da diferença</span><input data-filter="diff_field" placeholder="Ex.: target_temperature"></label>
                <label class="field"><span>Operador da diferença</span><select data-filter="diff_operator">${operatorOptions}</select></label>
                <label class="field"><span>Valor da diferença</span><input data-filter="diff_value" placeholder="Ex.: -1"></label>
                <label class="toggle-field"><input type="checkbox" data-filter="relevant_only" checked><span>Apenas alterações relevantes</span></label>
              </div>
            </details>
            <details>
              <summary>Construtor avançado AND / OR</summary>
              <div class="advanced-head"><p>Combine grupos com <strong>TODAS</strong> ou <strong>QUALQUER</strong> condição, sem escrever SQL.</p><button type="button" class="secondary" data-action="add-filter-group"><ha-icon icon="mdi:plus"></ha-icon>Adicionar grupo</button></div>
              <div id="advanced-builder" class="advanced-builder"></div>
            </details>
            <div class="filter-footer"><span id="query-summary">Nenhum filtro aplicado.</span><div class="button-row"><button type="button" class="secondary" data-action="clear-filters">Limpar</button><button type="button" data-action="apply-filters">Aplicar filtros</button></div></div>
          </section>

          <main>
            <section id="panel-overview" class="tab-panel" role="tabpanel" data-panel="overview">
              <div id="overview-metrics" class="metrics" aria-live="polite"></div>
              <div class="overview-layout">
                <article class="surface flow-surface"><div class="section-title"><div><div class="eyebrow">Correlação mais recente</div><h2>Último fluxo completo</h2></div><ha-icon icon="mdi:transit-connection-variant"></ha-icon></div><div id="last-flow" class="flow"></div></article>
                <article class="surface"><div class="section-title"><div><div class="eyebrow">Estado atual</div><h2>Supervisor e tratamento</h2></div><ha-icon icon="mdi:robot-outline"></ha-icon></div><dl id="overview-state" class="definition-list"></dl></article>
              </div>
              <article class="surface"><div class="section-title"><div><div class="eyebrow">Eventos essenciais</div><h2>Atividade recente</h2><p class="section-subtitle">Resumo fixo dos eventos mais recentes. Busca e filtros ficam disponíveis nas abas de consulta.</p></div><button type="button" class="secondary" data-tab-jump="timeline">Abrir linha do tempo</button></div><div id="recent-events" class="compact-events"></div></article>
            </section>

            ${this._eventPanelTemplate("timeline", "Linha do tempo", "Todos os acontecimentos correlacionáveis em ordem temporal.")}
            ${this._eventPanelTemplate("decisions", "Decisões", "Entradas, demandas, regras, limites, proteções, configuração calculada e ação tomada.")}
            ${this._eventPanelTemplate("states", "Mudanças de estado", "Estado anterior, estado novo, campos relevantes e contexto capturados no próprio evento.")}
            ${this._eventPanelTemplate("actions", "Ações e transmissões", "Solicitações Home Assistant, expectativa de audibilidade e confirmação observada posteriormente.")}
            ${this._eventPanelTemplate("external", "Alterações externas", "Mudanças sem ação causal correlacionada, sua classificação e a reação posterior do Supervisor.")}

            <section id="panel-anomalies" class="tab-panel" role="tabpanel" data-panel="anomalies" hidden>
              <div class="panel-head"><div><div class="eyebrow">Investigação</div><h2>Anomalias</h2><p>Reconhecer registra ciência; resolver encerra a ocorrência sem apagar sua história.</p></div><label class="inline-field">Estado<select id="anomaly-status"><option value="active">Ativas</option><option value="acknowledged">Reconhecidas</option><option value="resolved">Resolvidas</option><option value="all">Todas</option></select></label></div>
              <div id="anomaly-list" class="anomaly-grid"></div>
            </section>

            <section id="panel-observations" class="tab-panel" role="tabpanel" data-panel="observations" hidden>
              <div class="panel-head"><div><div class="eyebrow">Evidência humana</div><h2>Observações</h2><p>Registre bips e anotações no instante percebido para correlacioná-los com decisões e comandos.</p></div><div class="button-row"><button type="button" class="accent" data-action="open-beep"><ha-icon icon="mdi:volume-high"></ha-icon>Registrar bip</button><button type="button" data-action="open-note"><ha-icon icon="mdi:notebook-plus-outline"></ha-icon>Registrar observação</button></div></div>
              <div id="events-observations" class="observation-list"></div>
              ${this._paginationTemplate("observations")}
            </section>

            <section id="panel-statistics" class="tab-panel" role="tabpanel" data-panel="statistics" hidden>
              <div class="panel-head"><div><div class="eyebrow">Agregações do backend</div><h2>Estatísticas</h2><p>Os gráficos usam consultas agregadas; o navegador não carrega o banco inteiro.</p></div><button type="button" class="secondary" data-action="refresh-statistics"><ha-icon icon="mdi:refresh"></ha-icon>Atualizar</button></div>
              <div id="statistics-grid" class="statistics-grid"></div>
            </section>

            <section id="panel-settings" class="tab-panel" role="tabpanel" data-panel="settings" hidden>
              ${this._settingsTemplate()}
            </section>

            <section id="panel-export" class="tab-panel" role="tabpanel" data-panel="export" hidden>
              ${this._exportTemplate()}
            </section>
          </main>

          ${this._dialogsTemplate()}
        </ha-card>`;
    }

    _eventPanelTemplate(id, title, description) {
      return `
        <section id="panel-${id}" class="tab-panel" role="tabpanel" data-panel="${id}" hidden>
          <div class="panel-head"><div><div class="eyebrow">Consulta estruturada</div><h2>${title}</h2><p>${description}</p></div><div class="view-meta"><span id="total-${id}">— eventos</span><span id="loading-${id}" class="loading-indicator" hidden><ha-icon icon="mdi:loading"></ha-icon>Carregando</span></div></div>
          <div id="events-${id}" class="events-container"></div>
          ${this._paginationTemplate(id)}
        </section>`;
    }

    _paginationTemplate(id) {
      return `
        <nav class="pagination" data-pagination="${id}" aria-label="Paginação de ${id}">
          <button type="button" class="secondary" data-page-action="latest" data-page-tab="${id}"><ha-icon icon="mdi:page-first"></ha-icon>Mais recentes</button>
          <button type="button" class="secondary" data-page-action="previous" data-page-tab="${id}"><ha-icon icon="mdi:chevron-left"></ha-icon>Anterior</button>
          <label>Ir para horário<input type="datetime-local" step="1" data-anchor-tab="${id}"></label>
          <button type="button" class="secondary" data-page-action="anchor" data-page-tab="${id}">Ir</button>
          <button type="button" class="secondary" data-page-action="next" data-page-tab="${id}">Próxima<ha-icon icon="mdi:chevron-right"></ha-icon></button>
          <button type="button" class="secondary" data-page-action="oldest" data-page-tab="${id}">Mais antigos<ha-icon icon="mdi:page-last"></ha-icon></button>
        </nav>`;
    }

    _settingsTemplate() {
      const captureToggles = [
        ["capture_decisions", "Decisões"], ["capture_state_changes", "Mudanças de estado"],
        ["capture_service_calls", "Chamadas de ação"], ["capture_localtuya", "LocalTuya"],
        ["capture_climate", "Climate"], ["capture_agenda", "Agenda"],
        ["capture_presets", "Presets"], ["capture_power_profiles", "Potência"],
        ["capture_protections", "Proteções"], ["capture_errors", "Erros"],
        ["capture_external_changes", "Mudanças externas"],
      ].map(([key, label]) => `<label class="toggle-field"><input type="checkbox" data-setting="${key}"><span>${label}</span></label>`).join("");
      const anomalyToggles = [
        ["commands_too_close", "Comandos muito próximos"],
        ["repeated_commands", "Comandos repetidos"],
        ["decision_oscillation", "Decisão oscilando"],
        ["desired_state_divergence", "Desejado divergente"],
        ["localtuya_not_confirmed", "LocalTuya sem confirmação"],
        ["external_change_reaction", "Mudança externa seguida por reação"],
        ["excessive_volume", "Volume excessivo"],
        ["repeated_error", "Erro repetitivo"],
        ["critical_entity_unavailable", "Entidade crítica unavailable"],
      ].map(([value, label]) => `<label class="toggle-field"><input type="checkbox" value="${value}" data-setting-list="anomaly_enabled_types"><span>${label}</span></label>`).join("");
      return `
        <div class="panel-head settings-head"><div><div class="eyebrow">ConfigEntry.options</div><h2>Configurações</h2><p>O rascunho permanece intacto mesmo enquanto novos eventos chegam.</p></div><span id="settings-dirty" class="dirty-chip" hidden>Alterações não salvas</span></div>
        <form id="settings-form" class="settings-form">
          <details open><summary>Captura</summary><div class="settings-grid"><label class="field"><span>Modo</span><select data-setting="capture_mode"><option value="essential">Essencial</option><option value="normal">Normal</option><option value="intensive">Intensivo</option></select></label><div class="toggle-grid full">${captureToggles}</div></div></details>
          <details><summary>Retenção</summary><div class="settings-grid"><label class="field"><span>Eventos essenciais · dias</span><input type="number" min="1" max="3650" data-setting="retention_essential_days"></label><label class="field"><span>Erros detalhados · dias</span><input type="number" min="1" max="3650" data-setting="retention_error_days"></label><label class="field"><span>Trace completo · dias</span><input type="number" min="1" max="365" data-setting="retention_trace_days"></label><div id="retention-summary" class="setting-info full"></div></div></details>
          <details><summary>Compactação</summary><div class="settings-grid"><label class="toggle-field"><input type="checkbox" data-setting="compaction_enabled"><span>Compactação habilitada</span></label><label class="field"><span>Janela · segundos</span><input type="number" min="1" max="3600" data-setting="compaction_window_seconds"></label><div class="toggle-grid full"><label class="toggle-field"><input type="checkbox" data-setting="compact_identical_evaluations"><span>Avaliações idênticas</span></label><label class="toggle-field"><input type="checkbox" data-setting="compact_no_change"><span>Avaliações sem mudança</span></label><label class="toggle-field"><input type="checkbox" data-setting="compact_identical_states"><span>Estados idênticos</span></label><label class="toggle-field"><input type="checkbox" data-setting="compact_repeated_blocks"><span>Bloqueios repetitivos</span></label><label class="toggle-field"><input type="checkbox" data-setting="compact_repeated_unavailable"><span>Indisponibilidades repetitivas</span></label></div><label class="field"><span>Janela da taxa · s</span><input type="number" min="1" max="3600" data-setting="rate_window_seconds"></label><label class="field"><span>Alerta de volume</span><input type="number" min="1" data-setting="rate_warning_events"></label><label class="field"><span>Limite rígido de volume</span><input type="number" min="1" data-setting="rate_hard_limit_events"></label><p class="setting-info full">Transmissões, erros diferentes, mudanças externas, mudanças de tratamento e observações manuais nunca são compactadas.</p></div></details>
          <details><summary>Correlação</summary><div class="settings-grid"><label class="field"><span>Janela temporal padrão · s</span><input type="number" min="1" max="3600" data-setting="correlation_window_seconds"></label><label class="field"><span>Confirmação LocalTuya · s</span><input type="number" min="1" max="3600" data-setting="localtuya_confirmation_window_seconds"></label><label class="field"><span>Observação externa · s</span><input type="number" min="1" max="3600" data-setting="external_observation_window_seconds"></label><label class="field"><span>Bip · antes · s</span><input type="number" min="1" max="3600" data-setting="beep_window_before_seconds"></label><label class="field"><span>Bip · depois · s</span><input type="number" min="1" max="3600" data-setting="beep_window_after_seconds"></label></div></details>
          <details><summary>Anomalias</summary><div class="settings-grid"><label class="toggle-field"><input type="checkbox" data-setting="anomalies_enabled"><span>Detecção de anomalias habilitada</span></label><div class="toggle-grid full">${anomalyToggles}</div><label class="field"><span>Comandos próximos · s</span><input type="number" min="1" data-setting="anomaly_close_commands_seconds"></label><label class="field"><span>Comando repetido · janela s</span><input type="number" min="1" data-setting="anomaly_repeated_command_window_seconds"></label><label class="field"><span>Oscilação · janela s</span><input type="number" min="1" data-setting="anomaly_oscillation_window_seconds"></label><label class="field"><span>Oscilação · mudanças</span><input type="number" min="2" data-setting="anomaly_oscillation_min_changes"></label><label class="field"><span>Divergência · s</span><input type="number" min="1" data-setting="anomaly_divergence_seconds"></label><label class="field"><span>Volume · janela s</span><input type="number" min="1" data-setting="anomaly_volume_window_seconds"></label><label class="field"><span>Volume · limite</span><input type="number" min="1" data-setting="anomaly_volume_event_limit"></label><label class="field"><span>Erro repetido · janela s</span><input type="number" min="1" data-setting="anomaly_repeated_error_window_seconds"></label><label class="field"><span>Erro repetido · quantidade</span><input type="number" min="2" data-setting="anomaly_repeated_error_count"></label><label class="field"><span>Unavailable crítico · s</span><input type="number" min="1" data-setting="anomaly_unavailable_seconds"></label><label class="field"><span>Sem mudança · limiar</span><input type="number" min="1" data-setting="anomaly_no_change_threshold"></label><label class="field"><span>Duplicata · janela s</span><input type="number" min="1" data-setting="anomaly_duplicate_window_seconds"></label><label class="field"><span>Rajada audível · janela s</span><input type="number" min="1" data-setting="anomaly_audible_burst_seconds"></label><label class="field"><span>Rajada audível · quantidade</span><input type="number" min="2" data-setting="anomaly_audible_burst_count"></label><label class="field"><span>Janela geral · minutos</span><input type="number" min="1" data-setting="anomaly_window_minutes"></label></div></details>
          <details><summary>Notificações</summary><div class="settings-grid"><label class="toggle-field"><input type="checkbox" data-setting="notifications_enabled"><span>Habilitar notificações</span></label><label class="field"><span>Severidade mínima</span><select data-setting="notification_min_severity"><option value="info">Informação</option><option value="warning">Atenção</option><option value="error">Erro</option><option value="critical">Crítico</option></select></label><label class="field"><span>Tipos (separados por vírgula)</span><input data-setting-csv="notification_types"></label><label class="field"><span>Cooldown · segundos</span><input type="number" min="60" max="86400" data-setting="notification_cooldown_seconds"></label><label class="toggle-field"><input type="checkbox" data-setting="notification_persistent"><span>persistent_notification</span></label><label class="field"><span>Serviço notify opcional</span><input data-setting="notification_service" placeholder="notify.mobile_app"></label></div></details>
          <details><summary>Interface</summary><div class="settings-grid"><label class="field"><span>Itens por página</span><input type="number" min="10" max="250" data-setting="interface_items_per_page"></label><label class="toggle-field"><input type="checkbox" data-setting="interface_auto_refresh"><span>Atualização ao vivo</span></label><label class="field"><span>Colunas (separadas por vírgula)</span><input data-setting-csv="interface_columns"></label><label class="field"><span>Densidade</span><select data-setting="interface_density"><option value="comfortable">Confortável</option><option value="compact">Compacta</option></select></label><label class="toggle-field"><input type="checkbox" data-setting="interface_show_technical_codes"><span>Mostrar códigos técnicos</span></label><label class="toggle-field"><input type="checkbox" data-setting="interface_show_unchanged_attributes"><span>Mostrar atributos sem mudança</span></label><label class="field"><span>Formato da data</span><select data-setting="interface_date_format"><option value="locale">Local</option><option value="relative">Relativo</option><option value="iso">ISO</option></select></label><label class="field"><span>Abrir detalhe</span><select data-setting="interface_detail_mode"><option value="modal">Modal</option><option value="panel">Painel</option></select></label></div></details>
          <details><summary>Privacidade</summary><div class="settings-grid"><label class="toggle-field"><input type="checkbox" data-setting="privacy_resolve_user_names"><span>Resolver nomes de usuários</span></label><label class="toggle-field"><input type="checkbox" data-setting="privacy_store_user_ids"><span>Armazenar IDs de usuários</span></label><label class="toggle-field"><input type="checkbox" data-setting="privacy_store_user_names"><span>Armazenar nomes de usuários</span></label><label class="toggle-field"><input type="checkbox" data-setting="privacy_capture_raw_events"><span>Capturar evento bruto sanitizado</span></label><label class="toggle-field"><input type="checkbox" data-setting="privacy_capture_service_data"><span>Capturar dados de ações</span></label><label class="toggle-field"><input type="checkbox" data-setting="privacy_redact_sensitive_values"><span>Remover valores sensíveis</span></label><label class="toggle-field"><input type="checkbox" data-setting="anonymize_entity_ids"><span>Anonimizar IDs de entidades na exportação</span></label><p class="setting-info full">Tokens, senhas, SSID, chaves de API e credenciais nunca devem ser exportados.</p></div></details>
          <details><summary>Manutenção</summary><div class="settings-grid"><label class="field"><span>Limite do banco · MB</span><input type="number" min="10" data-setting="maintenance_database_limit_mb"></label><label class="field"><span>Intervalo de limpeza · h</span><input type="number" min="1" data-setting="maintenance_cleanup_interval_hours"></label><label class="field"><span>Máximo de linhas exportadas</span><input type="number" min="1" data-setting="maintenance_export_max_rows"></label><label class="field"><span>Limite da fila normal</span><input type="number" min="100" data-setting="queue_limit"></label><label class="field"><span>Limite da fila crítica</span><input type="number" min="100" data-setting="critical_queue_limit"></label><label class="field"><span>Tamanho do lote</span><input type="number" min="1" data-setting="batch_size"></label><label class="field"><span>Intervalo de flush · s</span><input type="number" min="0.05" step="0.05" data-setting="flush_interval_seconds"></label></div><div id="maintenance-summary" class="maintenance-grid"></div><div class="button-row maintenance-actions"><button type="button" class="secondary admin-only" data-action="run-cleanup"><ha-icon icon="mdi:broom"></ha-icon>Limpar e compactar</button><button type="button" class="secondary" data-action="clear-view"><ha-icon icon="mdi:eye-off-outline"></ha-icon>Limpar visualização</button><button type="button" class="secondary" data-action="export-current"><ha-icon icon="mdi:file-export"></ha-icon>Exportar</button><button type="button" class="danger admin-only" data-action="clear-filtered"><ha-icon icon="mdi:delete-sweep"></ha-icon>Excluir logs filtrados</button><button type="button" class="danger admin-only" data-action="clear-old"><ha-icon icon="mdi:archive-remove-outline"></ha-icon>Excluir logs antigos</button><button type="button" class="danger admin-only" data-action="clear-all"><ha-icon icon="mdi:delete-forever"></ha-icon>Excluir todos</button></div></details>
          <div class="sticky-form-actions"><button type="button" class="secondary" data-action="reset-settings">Restaurar padrões</button><button type="button" class="secondary" data-action="cancel-settings">Cancelar</button><button type="button" class="admin-only" data-action="save-settings">Salvar configurações</button></div>
        </form>`;
    }

    _exportTemplate() {
      return `
        <div class="panel-head"><div><div class="eyebrow">Dados sanitizados</div><h2>Exportação</h2><p>Exporte a consulta atual ou uma investigação específica sem carregar o banco inteiro no navegador.</p></div></div>
        <div class="export-layout">
          <form id="export-form" class="surface export-form">
            <label class="field"><span>Formato</span><select name="format"><option value="csv">CSV</option><option value="json">JSON</option><option value="text">Relatório textual</option><option value="diagnostic_package">Pacote de diagnóstico</option></select></label>
            <label class="field"><span>Escopo</span><select name="scope"><option value="current_query">Consulta atual</option><option value="selected_event">Evento selecionado</option><option value="correlation">Correlação selecionada</option><option value="evaluation">Avaliação selecionada</option><option value="interval">Intervalo atual</option><option value="anomaly">Anomalia selecionada</option></select></label>
            <label class="toggle-field"><input type="checkbox" name="include_details" checked><span>Incluir detalhes técnicos sanitizados</span></label>
            <label class="field"><span>ID opcional</span><input name="selected_id" placeholder="Evento, correlação, avaliação ou anomalia"></label>
            <button type="button" data-action="create-export"><ha-icon icon="mdi:download"></ha-icon>Gerar exportação</button>
          </form>
          <article class="surface privacy-note"><ha-icon icon="mdi:shield-lock-outline"></ha-icon><div><h3>Privacidade</h3><p>O backend remove segredos e dados privados desnecessários. O frontend não tenta reconstruir frame IR, confirmação física ou informação indisponível.</p></div></article>
        </div>`;
    }

    _dialogsTemplate() {
      return `
        <dialog id="event-dialog" class="wide-dialog"><article class="dialog-shell"><header><div><div id="detail-type" class="eyebrow"></div><h2 id="detail-title">Detalhes do evento</h2><div id="detail-chips" class="chip-row"></div></div><button type="button" class="secondary icon-button" data-action="close-detail" aria-label="Fechar detalhes"><ha-icon icon="mdi:close"></ha-icon></button></header><nav id="detail-tabs" class="detail-tabs"><button type="button" data-detail-tab="comparison">Antes · Depois · Diferença</button><button type="button" data-detail-tab="context">Contexto</button><button type="button" data-detail-tab="technical">Técnico</button><button type="button" data-detail-tab="related">Relacionados</button></nav><div id="detail-loading" class="empty-state">Carregando detalhes…</div><div id="detail-content"></div></article></dialog>

        <dialog id="observation-dialog"><form id="observation-form" class="dialog-shell"><header><div><div class="eyebrow">Evidência humana</div><h2 id="observation-title">Registrar observação</h2></div><button type="button" class="secondary icon-button" data-action="close-observation" aria-label="Fechar"><ha-icon icon="mdi:close"></ha-icon></button></header><input type="hidden" name="observation_type" value="note"><label class="field beep-only" hidden><span>Quantidade percebida</span><select name="expected_count"><option value="1">1 bip</option><option value="2">2 bips</option><option value="many">Vários</option><option value="uncertain">Incerto</option></select></label><label class="field"><span>Horário</span><input type="datetime-local" step="1" name="occurred_at" required></label><label class="field note-only"><span>Título</span><input name="title" maxlength="160" placeholder="Ex.: comportamento durante Dry"></label><label class="field"><span>Observação</span><textarea name="note" rows="5" maxlength="4000" placeholder="Descreva o que você ouviu ou observou"></textarea></label><label class="field note-only"><span>Tags</span><input name="tags" placeholder="bip, dry, umidade"></label><p class="notice">Resultado: <strong>Observado pelo usuário</strong>. A correlação temporal não será apresentada como causalidade confirmada.</p><footer><button type="button" class="secondary" data-action="close-observation">Cancelar</button><button type="button" data-action="submit-observation">Registrar</button></footer></form></dialog>

        <dialog id="confirm-dialog"><form class="dialog-shell"><header><div><div class="eyebrow">Confirmação obrigatória</div><h2 id="confirm-title">Confirmar ação</h2></div></header><p id="confirm-message"></p><label id="confirm-code-field" class="field" hidden><span>Digite APAGAR</span><input id="confirm-code" autocomplete="off"></label><footer><button type="button" class="secondary" data-confirm="cancel">Cancelar</button><button type="button" class="danger" data-confirm="accept">Confirmar</button></footer></form></dialog>

        <dialog id="saved-filter-dialog"><form class="dialog-shell"><header><div><div class="eyebrow">Consulta reutilizável</div><h2>Salvar filtro</h2></div><button type="button" class="secondary icon-button" data-action="close-save-filter"><ha-icon icon="mdi:close"></ha-icon></button></header><label class="field"><span>Nome</span><input name="name" maxlength="100" required placeholder="Ex.: Problema dos bips"></label><label class="toggle-field"><input type="checkbox" name="is_default"><span>Usar como padrão</span></label><footer><button type="button" class="secondary" data-action="close-save-filter">Cancelar</button><button type="button" data-action="confirm-save-filter">Salvar</button></footer></form></dialog>`;
    }

    _cacheNodes() {
      const root = this.shadowRoot;
      this._nodes = {
        banner: root.querySelector("#status-banner"),
        pendingBanner: root.querySelector("#pending-banner"),
        pendingLabel: root.querySelector("#pending-label"),
        queryToolbar: root.querySelector("#query-toolbar"),
        filterPanel: root.querySelector("#filter-panel"),
        filterToggle: root.querySelector('[data-action="toggle-filters"]'),
        filterCount: root.querySelector("#filter-count"),
        querySummary: root.querySelector("#query-summary"),
        globalSearch: root.querySelector("#global-search"),
        quickFilters: root.querySelector("#quick-filters"),
        savedFilterSelect: root.querySelector("#saved-filter-select"),
        advancedBuilder: root.querySelector("#advanced-builder"),
        eventDialog: root.querySelector("#event-dialog"),
        detailLoading: root.querySelector("#detail-loading"),
        detailContent: root.querySelector("#detail-content"),
        observationDialog: root.querySelector("#observation-dialog"),
        observationForm: root.querySelector("#observation-form"),
        confirmDialog: root.querySelector("#confirm-dialog"),
        savedFilterDialog: root.querySelector("#saved-filter-dialog"),
        settingsForm: root.querySelector("#settings-form"),
        settingsDirty: root.querySelector("#settings-dirty"),
      };
    }

    _bindStaticEvents() {
      const root = this.shadowRoot;
      root.addEventListener("click", (event) => {
        const tab = event.target.closest("[data-tab]");
        if (tab) {
          this._setActiveTab(tab.dataset.tab);
          return;
        }
        const jump = event.target.closest("[data-tab-jump]");
        if (jump) {
          this._setActiveTab(jump.dataset.tabJump);
          return;
        }
        const action = event.target.closest("[data-action]");
        if (action) {
          event.preventDefault();
          this._handleAction(action.dataset.action, action);
          return;
        }
        const page = event.target.closest("[data-page-action]");
        if (page) {
          event.preventDefault();
          this._handlePageAction(page.dataset.pageTab, page.dataset.pageAction);
          return;
        }
        const eventTarget = event.target.closest("[data-event-id]");
        if (eventTarget) {
          event.preventDefault();
          this._openEvent(eventTarget.dataset.eventId);
          return;
        }
        const anomalyAction = event.target.closest("[data-anomaly-action]");
        if (anomalyAction) {
          event.preventDefault();
          this._handleAnomalyAction(anomalyAction.dataset.anomalyAction, anomalyAction.dataset.anomalyId).catch((error) => this._showError(error));
          return;
        }
        const observationDelete = event.target.closest("[data-delete-observation]");
        if (observationDelete) {
          event.preventDefault();
          this._deleteObservation(observationDelete.dataset.deleteObservation).catch((error) => this._showError(error));
          return;
        }
        const detailTab = event.target.closest("[data-detail-tab]");
        if (detailTab) {
          this._setDetailTab(detailTab.dataset.detailTab);
          return;
        }
        const confirm = event.target.closest("[data-confirm]");
        if (confirm) this._settleConfirmation(confirm.dataset.confirm === "accept");
      });

      root.addEventListener("change", (event) => {
        const filter = event.target.closest("[data-filter]");
        if (filter) {
          this._readOneFilterControl(filter);
          if (["categories", "modes", "domains"].includes(filter.dataset.filter)) this._updateDependentFacets();
        }
        const setting = event.target.closest("[data-setting],[data-setting-list],[data-setting-csv]");
        if (setting) this._readOneSetting(setting);
      });

      root.addEventListener("input", (event) => {
        const filter = event.target.closest("[data-filter]");
        if (filter && filter.tagName !== PICKER_TAG.toUpperCase()) this._readOneFilterControl(filter);
        const setting = event.target.closest("[data-setting],[data-setting-list],[data-setting-csv]");
        if (setting) this._readOneSetting(setting);
      });

      this._nodes.globalSearch.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
          event.preventDefault();
          this._filterDraft.text = this._nodes.globalSearch.value.trim();
          this._applyFilters();
        }
      });
      this._nodes.globalSearch.addEventListener("input", () => {
        this._filterDraft.text = this._nodes.globalSearch.value.trim();
      });

      this._nodes.savedFilterSelect.addEventListener("change", () => {
        if (this._nodes.savedFilterSelect.value) {
          const result = this._loadSavedFilter(this._nodes.savedFilterSelect.value);
          if (result?.catch) result.catch((error) => this._showError(error));
        }
      });

      root.querySelector("#anomaly-status")?.addEventListener("change", () => this._loadAnomalies());
      this._nodes.observationDialog.addEventListener("close", () => this._nodes.observationForm.reset());
      this._nodes.eventDialog.addEventListener("close", () => {
        this._detailEvent = null;
        this._detailEvaluation = null;
        this._detailCorrelation = [];
      });
    }

    async _tryInitialize() {
      if (!this._hass || !this._mounted || this._initialized) return;
      if (this._initializing) return this._initializing;
      this._initializing = this._initialize();
      try { await this._initializing; } finally { this._initializing = null; }
    }

    async _initialize() {
      this._setStatus("Carregando diagnóstico…", "info");
      const results = await Promise.allSettled([
        this._loadSnapshot(),
        this._loadCatalog(),
        this._loadSettings(),
        this._loadStatistics(),
        this._loadAnomalies(),
      ]);
      const failures = results.filter((result) => result.status === "rejected");
      this._initialized = failures.length < results.length;
      if (failures.length) {
        const first = failures[0].reason;
        this._setStatus(`Parte do diagnóstico não pôde ser carregada: ${first?.message || first}`, "warning");
      } else {
        this._clearStatus();
      }
      this._writeFilterControls();
      this._renderOverview();
      this._renderStatistics();
      this._renderAnomalies();
      this._renderSettings();
      if (EVENT_TABS.has(this._activeTab)) await this._loadEvents(this._activeTab, { reset: true });
    }

    async _ws(command, payload = {}) {
      if (!this._hass) throw new Error("Home Assistant ainda não está disponível");
      const message = { type: `${DOMAIN}/${command}`, ...payload };
      if (this._entryId) message.entry_id = this._entryId;
      return this._hass.callWS(message);
    }

    async _subscribe() {
      if (!this._hass || !this._connected || this._unsubscribe || this._subscribing) return;
      if (this._settingsSaved.interface_auto_refresh === false) return;
      if (!this._hass.connection?.subscribeMessage) return;
      this._subscribing = true;
      try {
        const message = { type: `${DOMAIN}/subscribe` };
        if (this._entryId) message.entry_id = this._entryId;
        this._unsubscribe = await this._hass.connection.subscribeMessage(
          (update) => this._handleSubscription(update),
          message,
        );
      } catch (error) {
        this._setStatus(`Atualização ao vivo indisponível: ${error?.message || error}`, "warning");
      } finally {
        this._subscribing = false;
      }
    }

    _handleSubscription(update) {
      const kind = update?.type ?? update?.event_type ?? "event";
      if (kind === "health" || kind === "snapshot") {
        this._mergeSmallSnapshot(update.snapshot ?? update.data ?? update);
        return;
      }
      if (kind !== "event" && !update?.event && !update?.event_id) return;
      this._pendingEvents += Number(update?.count || 1);
      this._updatePendingBanner();
      // Deliberately do not mutate list rows, filters, dialogs or form drafts here.
    }

    _mergeSmallSnapshot(value) {
      const patch = asObject(value);
      this._snapshot = { ...this._snapshot, ...patch };
      const healthValue = patch.status?.health ?? patch.health;
      if (healthValue) {
        const metric = this.shadowRoot.querySelector('[data-metric="health"] .metric-value');
        if (metric) metric.textContent = semanticValue(healthValue);
      }
    }

    _setActiveTab(tab) {
      if (!TABS.some(([id]) => id === tab)) return;
      this._activeTab = tab;
      storageSet(this._storageKey("active_tab"), tab);
      this._setFilterPanelOpen(false);
      this._activateTabDom();
      if (EVENT_TABS.has(tab)) this._ensureEventsLoaded(tab);
      if (tab === "anomalies") this._loadAnomalies();
      if (tab === "statistics") this._loadStatistics().then(() => this._renderStatistics()).catch((error) => this._showError(error));
    }

    _activateTabDom() {
      if (!this.shadowRoot) return;
      this.shadowRoot.querySelectorAll("[data-tab]").forEach((button) => {
        const active = button.dataset.tab === this._activeTab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
        button.tabIndex = active ? 0 : -1;
      });
      this.shadowRoot.querySelectorAll("[data-panel]").forEach((panel) => {
        panel.hidden = panel.dataset.panel !== this._activeTab;
      });
      const filtersAvailable = FILTER_TABS.has(this._activeTab);
      if (this._nodes?.queryToolbar) this._nodes.queryToolbar.hidden = !filtersAvailable;
      if (this._nodes?.quickFilters) this._nodes.quickFilters.hidden = !filtersAvailable;
      if (!filtersAvailable) this._setFilterPanelOpen(false);
    }

    _setFilterPanelOpen(open) {
      if (!this._nodes?.filterPanel) return;
      const shouldOpen = Boolean(open) && FILTER_TABS.has(this._activeTab);
      this._nodes.filterPanel.hidden = !shouldOpen;
      this._nodes.filterToggle?.setAttribute("aria-expanded", String(shouldOpen));
    }

    async _ensureEventsLoaded(tab) {
      const state = this._viewStates.get(tab);
      const fingerprint = this._queryFingerprint(tab);
      if (!state?.loaded || state.fingerprint !== fingerprint) await this._loadEvents(tab, { reset: true });
    }

    async _loadSnapshot() {
      const response = await this._ws("get_snapshot");
      this._snapshot = asObject(response?.snapshot ?? response);
      this._entryId = response?.entry_id ?? this._snapshot.entry_id ?? this._entryId;
      this._renderOverview();
      this._renderMaintenance();
      return response;
    }

    async _loadCatalog() {
      const response = await this._ws("get_filter_catalog");
      const catalog = asObject(response?.catalog ?? response);
      const rawFields = catalog.fields;
      const fields = Array.isArray(rawFields)
        ? rawFields.map(normalizeOption)
        : Object.entries(asObject(rawFields)).map(([name, specification]) => ({
          value: name,
          label: humanizeCode(name),
          ...asObject(specification),
        }));
      this._catalog = {
        facets: asObject(catalog.facets),
        fields,
        operators: asArray(catalog.operators).map(normalizeOption).map((item) => ({
          ...item,
          label: OPERATOR_LABELS.get(item.value) || humanizeCode(item.value),
        })),
        quick_filters: asArray(catalog.quick_filters),
        saved_filters: asArray(catalog.saved_filters),
      };
      this._populateFacetPickers();
      this._renderQuickFilters();
      this._renderAdvancedBuilder();
      return response;
    }

    async _loadSettings() {
      const response = await this._ws("get_settings");
      const settings = canonicalSettings(response?.settings ?? response);
      this._settingsSaved = { ...clone(DEFAULT_SETTINGS), ...clone(settings) };
      if (!this._settingsDirty) this._settingsDraft = clone(this._settingsSaved);
      if (Array.isArray(settings.saved_filters) && (this._hass?.user?.is_admin || settings.saved_filters.length)) {
        this._savedFilters = clone(settings.saved_filters);
        const defaultId = settings.default_saved_filter_id;
        this._savedFilters.forEach((item) => { item.is_default = defaultId ? item.id === defaultId : Boolean(item.is_default); });
        storageSet(this._storageKey("saved_filters"), this._savedFilters);
        this._renderSavedFilterOptions();
        const defaultFilter = this._savedFilters.find((item) => item.is_default);
        if (defaultFilter && isEmptyObject(this._appliedFilters)) {
          this._filterDraft = { relevant_only: true, ...clone(defaultFilter.filters || {}) };
          this._appliedFilters = clone(this._normalizeFilterPayload(this._filterDraft));
          this._advancedGroups = clone(defaultFilter.advanced || this._advancedGroups);
          this._renderAdvancedBuilder();
        }
      }
      this._applyInterfaceSettings();
      this._renderSettings();
      return response;
    }

    async _loadStatistics() {
      const response = await this._ws("get_statistics", { filters: this._effectiveFilters(this._activeTab) });
      this._statistics = asObject(response?.statistics ?? response);
      return response;
    }

    async _loadAnomalies() {
      if (!this._hass) return;
      const status = this.shadowRoot?.querySelector("#anomaly-status")?.value || "active";
      const payload = { status };
      const response = await this._ws("list_anomalies", payload);
      this._anomalies = normalizeItems(response, "items", "anomalies");
      this._renderAnomalies();
      return response;
    }

    _scopeFilters(tab) {
      if (tab === "decisions") return { categories: ["decision", "evaluation"] };
      if (tab === "states") return { categories: ["state", "state_import"] };
      if (tab === "actions") return { categories: ["action", "transmission"] };
      if (tab === "external") return { is_external: true };
      if (tab === "observations") return { categories: ["observation", "user_observation"] };
      return {};
    }

    _effectiveFilters(tab = this._activeTab) {
      const base = clone(this._appliedFilters || {});
      const relevantOnly = base.relevant_only === true;
      delete base.relevant_only;
      if (relevantOnly && tab === "states" && base.has_change === undefined) {
        base.has_change = true;
      }
      const scope = this._scopeFilters(tab);
      Object.entries(scope).forEach(([key, value]) => {
        if (Array.isArray(value) && Array.isArray(base[key])) {
          base[key] = base[key].filter((item) => value.includes(item));
          if (!base[key].length) base.advanced = this._appendAdvancedCondition(
            base.advanced,
            { field: key === "categories" ? "category" : key, operator: "in", value: ["__sem_resultado__"] },
          );
        }
        else base[key] = value;
      });
      const manualAdvanced = this._serializeAdvancedGroups();
      const advancedParts = [base.advanced, manualAdvanced]
        .filter((group) => asArray(group?.conditions ?? group?.children).length);
      if (advancedParts.length === 1) base.advanced = advancedParts[0];
      else if (advancedParts.length > 1) base.advanced = { logic: "and", conditions: advancedParts };
      else delete base.advanced;
      return base;
    }

    _appendAdvancedCondition(existing, condition) {
      if (!existing || !asArray(existing.conditions ?? existing.children).length) {
        return { logic: "and", conditions: [condition] };
      }
      return { logic: "and", conditions: [existing, condition] };
    }

    _queryFingerprint(tab) {
      return JSON.stringify({ tab, filters: this._effectiveFilters(tab), size: this._settingsSaved.interface_items_per_page || 50 });
    }

    async _loadEvents(tab, options = {}) {
      if (!EVENT_TABS.has(tab)) return;
      const state = this._viewStates.get(tab) || this._newViewState();
      this._viewStates.set(tab, state);
      const requestId = ++this._requestSerial;
      state.requestId = requestId;
      state.loading = true;
      this._setPanelLoading(tab, true);
      const reset = options.reset === true;
      const cursor = reset
        ? null
        : Object.prototype.hasOwnProperty.call(options, "cursor") ? options.cursor : state.cursor;
      const payload = {
        filters: this._effectiveFilters(tab),
        cursor: cursor || undefined,
        limit: Number(this._settingsSaved.interface_items_per_page || 50),
        direction: options.direction === "newer" ? "newer" : "older",
        include_details: true,
      };
      try {
        const response = await this._ws("list_events", payload);
        if (state.requestId !== requestId) return;
        state.items = normalizeItems(response).filter((event) => {
          const observationId = getObservationId(event);
          return !observationId || !this._deletedObservationIds.has(String(observationId));
        });
        state.total = response?.total_estimate ?? response?.total ?? null;
        state.nextCursor = response?.next_cursor ?? null;
        state.previousCursor = response?.previous_cursor ?? null;
        state.hasMore = Boolean(response?.has_more ?? state.nextCursor);
        state.cursor = cursor;
        state.direction = payload.direction;
        state.atLatest = (payload.direction === "older" && !cursor)
          || (payload.direction === "newer" && response?.has_more === false);
        state.atOldest = (payload.direction === "newer" && !cursor)
          || (payload.direction === "older" && response?.has_more === false);
        state.loaded = true;
        state.fingerprint = this._queryFingerprint(tab);
        this._renderEventView(tab);
        this._updatePagination(tab);
      } catch (error) {
        if (state.requestId === requestId) this._showError(error);
      } finally {
        if (state.requestId === requestId) {
          state.loading = false;
          this._setPanelLoading(tab, false);
        }
      }
    }

    async _handlePageAction(tab, action) {
      const state = this._viewStates.get(tab);
      if (!state || state.loading) return;
      if (action === "latest") {
        await this._loadEvents(tab, { reset: true, direction: "older" });
        return;
      }
      if (action === "oldest") {
        await this._loadEvents(tab, { reset: false, cursor: null, direction: "newer" });
        return;
      }
      if (action === "anchor") {
        const input = this.shadowRoot.querySelector(`[data-anchor-tab="${tab}"]`);
        if (!input?.value) return;
        const anchor = new Date(input.value);
        if (Number.isNaN(anchor.getTime())) return;
        this._filterDraft.end = input.value;
        this._writeFilterControls();
        await this._applyFilters();
        return;
      }
      if (action === "next" && state.nextCursor) {
        await this._loadEvents(tab, { cursor: state.nextCursor, direction: "older" });
        return;
      }
      if (action === "previous" && state.previousCursor) {
        await this._loadEvents(tab, { cursor: state.previousCursor, direction: "newer" });
      }
    }

    _setPanelLoading(tab, loading) {
      const node = this.shadowRoot?.querySelector(`#loading-${tab}`);
      if (node) node.hidden = !loading;
    }

    _updatePagination(tab) {
      const state = this._viewStates.get(tab);
      const nav = this.shadowRoot.querySelector(`[data-pagination="${tab}"]`);
      if (!state || !nav) return;
      const previous = nav.querySelector('[data-page-action="previous"]');
      const next = nav.querySelector('[data-page-action="next"]');
      if (previous) previous.disabled = state.atLatest || !state.previousCursor;
      if (next) next.disabled = state.atOldest || !state.nextCursor || (state.direction === "older" && !state.hasMore);
    }

    _populateFacetPickers() {
      FACET_FILTERS.forEach(([key, label]) => {
        const picker = this.shadowRoot.querySelector(`${PICKER_TAG}[data-filter="${key}"]`);
        if (!picker) return;
        picker.label = label;
        picker.setOptions(this._facetOptions(key));
        picker.setValue(this._filterDraft[key] || []);
      });
      const changed = this.shadowRoot.querySelector(`${PICKER_TAG}[data-filter="changed_fields"]`);
      if (changed) {
        changed.label = "Campos alterados";
        const options = this._facetOptions("changed_fields");
        changed.setOptions(options.length ? options : this._catalog.fields);
        changed.setValue(this._filterDraft.changed_fields || []);
      }
    }

    _facetOptions(key) {
      const aliases = {
        categories: ["categories", "category"], event_types: ["event_types", "types", "event_type"],
        severities: ["severities", "severity"], outcomes: ["outcomes", "outcome"],
        actors: ["actors", "actor"], users: ["users", "user"], origins: ["origins", "origin"],
        entities: ["entities", "entity_id"], domains: ["domains", "domain"], modes: ["modes", "mode"],
        treatments: ["treatments", "treatment"], presets: ["presets", "preset"],
        power_profiles: ["power_profiles", "powers", "power_profile"], agendas: ["agendas", "agenda"],
        protections: ["protections", "protection"], audibilities: ["audibilities", "audibility"],
        activation_models: ["activation_models", "activation_model"], functions: ["functions", "function"],
        changed_fields: ["changed_fields", "fields"],
      };
      let values = [];
      for (const alias of aliases[key] || [key]) {
        if (Array.isArray(this._catalog.facets?.[alias])) {
          values = this._catalog.facets[alias];
          break;
        }
      }
      const preserveCode = new Set(["entities", "users", "actors"]);
      return values.map((value) => {
        const option = normalizeOption(value);
        const explicitlyLabeled = value && typeof value === "object" && (value.label || value.name);
        if (!explicitlyLabeled && !preserveCode.has(key)) {
          option.label = CODE_LABELS[option.value] || humanizeCode(option.value);
        }
        return option;
      });
    }

    _updateDependentFacets() {
      const categories = asArray(this._filterDraft.categories);
      const modes = asArray(this._filterDraft.modes);
      const domains = asArray(this._filterDraft.domains);
      const filterOptions = (key, predicate) => {
        const picker = this.shadowRoot.querySelector(`${PICKER_TAG}[data-filter="${key}"]`);
        if (!picker) return;
        const selected = picker.getValue();
        const all = this._facetOptions(key);
        const compatible = all.filter((item) => predicate(item) || selected.includes(item.value));
        picker.setOptions(compatible);
        picker.setValue(selected);
      };
      filterOptions("event_types", (item) => !categories.length || !item.category || categories.includes(String(item.category)) || asArray(item.categories).some((value) => categories.includes(String(value))));
      filterOptions("presets", (item) => !modes.length || !item.mode || modes.includes(String(item.mode)) || asArray(item.modes).some((value) => modes.includes(String(value))));
      filterOptions("power_profiles", (item) => !modes.length || !item.mode || modes.includes(String(item.mode)) || asArray(item.modes).some((value) => modes.includes(String(value))));
      filterOptions("entities", (item) => !domains.length || !item.domain || domains.includes(String(item.domain)) || domains.some((domain) => item.value.startsWith(`${domain}.`)));
    }

    _readOneFilterControl(control) {
      const key = control.dataset.filter;
      if (!key) return;
      let value;
      if (control.tagName === PICKER_TAG.toUpperCase()) value = control.getValue();
      else if (control.type === "checkbox") value = control.checked;
      else if (control.type === "number") value = control.value === "" ? "" : Number(control.value);
      else if (BOOLEAN_FILTERS.some(([name]) => name === key)) value = control.value === "" ? "" : control.value === "true";
      else value = control.value;
      if (BOOLEAN_FILTERS.some(([name]) => name === key) && value !== "") this._filterDraft[key] = value;
      else if (Array.isArray(value) ? value.length : value !== "" && value !== false) this._filterDraft[key] = value;
      else if (key === "relevant_only") this._filterDraft[key] = value;
      else delete this._filterDraft[key];
      this._updateFilterCount();
    }

    _readAllFilterControls() {
      this.shadowRoot.querySelectorAll("[data-filter]").forEach((control) => this._readOneFilterControl(control));
      const text = this._nodes.globalSearch.value.trim();
      if (text) this._filterDraft.text = text;
      else delete this._filterDraft.text;
    }

    _writeFilterControls() {
      if (!this.shadowRoot) return;
      this.shadowRoot.querySelectorAll("[data-filter]").forEach((control) => {
        const key = control.dataset.filter;
        const value = this._filterDraft[key];
        if (control.tagName === PICKER_TAG.toUpperCase()) control.setValue(asArray(value));
        else if (control.type === "checkbox") control.checked = value ?? (key === "relevant_only");
        else if (BOOLEAN_FILTERS.some(([name]) => name === key)) control.value = value === true ? "true" : value === false ? "false" : "";
        else control.value = value ?? "";
      });
      this._nodes.globalSearch.value = this._filterDraft.text || "";
      this._updateFilterCount();
      this._updateDependentFacets();
    }

    async _applyFilters(options = {}) {
      this._readAllFilterControls();
      this._appliedFilters = clone(this._normalizeFilterPayload(this._filterDraft));
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
      this._pendingEvents = 0;
      this._updatePendingBanner();
      this._updateFilterCount();
      if (options.closePanel === true) this._setFilterPanelOpen(false);
      if (EVENT_TABS.has(this._activeTab)) await this._loadEvents(this._activeTab, { reset: true });
      if (this._activeTab === "statistics") {
        await this._loadStatistics();
        this._renderStatistics();
      }
    }

    _normalizeFilterPayload(filters) {
      const result = {};
      Object.entries(filters || {}).forEach(([key, value]) => {
        if (value === "" || value === null || value === undefined) return;
        if (Array.isArray(value) && !value.length) return;
        result[key] = clone(value);
      });
      ["start", "end"].forEach((key) => {
        if (!result[key]) return;
        const date = new Date(result[key]);
        if (!Number.isNaN(date.getTime())) result[key] = date.toISOString();
      });
      if (result.changed_fields) {
        result.changed_field = clone(result.changed_fields);
        delete result.changed_fields;
      }
      const generatedConditions = [];
      if (result.users) {
        generatedConditions.push({ field: "user_name", operator: "in", value: clone(result.users) });
        delete result.users;
      }
      if (result.origins) {
        generatedConditions.push({ field: "origin_class", operator: "in", value: clone(result.origins) });
        delete result.origins;
      }
      [
        ["temperature_min", "temperature", "gte"],
        ["temperature_max", "temperature", "lte"],
        ["target_temperature_min", "target_temperature", "gte"],
        ["target_temperature_max", "target_temperature", "lte"],
      ].forEach(([key, field, operator]) => {
        if (result[key] === undefined) return;
        generatedConditions.push({ field, operator, value: result[key] });
        delete result[key];
      });
      ["before", "after", "diff"].forEach((prefix) => {
        const field = result[`${prefix}_field`];
        if (!field) return;
        const operator = this._canonicalOperator(result[`${prefix}_operator`] || "eq");
        generatedConditions.push({
          field: `${prefix}.${field}`,
          operator,
          value: this._conditionValue(operator, result[`${prefix}_value`]),
        });
        delete result[`${prefix}_field`];
        delete result[`${prefix}_operator`];
        delete result[`${prefix}_value`];
      });
      if (generatedConditions.length) {
        result.advanced = { logic: "and", conditions: generatedConditions };
      }
      return result;
    }

    _canonicalOperator(operator) {
      return operator === "neq" ? "ne" : String(operator || "eq");
    }

    _conditionValue(operator, rawValue) {
      if (["exists", "not_exists", "changed", "not_changed"].includes(operator)) return null;
      if (["in", "not_in", "between"].includes(operator) && typeof rawValue === "string") {
        return rawValue.split(",").map((item) => item.trim()).filter(Boolean).map((item) => this._scalarValue(item));
      }
      return this._scalarValue(rawValue);
    }

    _scalarValue(value) {
      if (typeof value !== "string") return value;
      const trimmed = value.trim();
      if (trimmed === "true") return true;
      if (trimmed === "false") return false;
      if (trimmed === "null") return null;
      if (/^-?(?:\d+|\d*\.\d+)$/.test(trimmed)) return Number(trimmed);
      return trimmed;
    }

    _clearFilters() {
      this._filterDraft = { relevant_only: true };
      this._appliedFilters = {};
      this._advancedGroups = [{ operator: "and", conditions: [{ field: "", operator: "eq", value: "" }] }];
      this._writeFilterControls();
      this._renderAdvancedBuilder();
      return this._applyFilters();
    }

    _updateFilterCount() {
      if (!this._nodes?.filterCount) return;
      const normalCount = Object.entries(this._filterDraft || {}).filter(([key, value]) => key !== "relevant_only" && (Array.isArray(value) ? value.length : value !== "" && value !== null && value !== undefined)).length;
      const advancedCount = this._advancedGroups.reduce((total, group) => total + group.conditions.filter((condition) => condition.field).length, 0);
      const count = normalCount + advancedCount;
      this._nodes.filterCount.textContent = String(count);
      this._nodes.querySummary.textContent = count ? `${count} condição${count === 1 ? "" : "ões"} aplicada${count === 1 ? "" : "s"}.` : "Nenhum filtro aplicado.";
    }

    _renderQuickFilters() {
      if (!this._nodes?.quickFilters) return;
      const backend = this._catalog.quick_filters.map((item) => ({
        ...item,
        value: item.value ?? item.id ?? item.key,
      }));
      const backendById = new Map(backend.map((item) => [item.value, item]));
      const defaultIds = new Set(DEFAULT_QUICK_FILTERS.map((item) => item.value));
      const source = [
        ...DEFAULT_QUICK_FILTERS.map((item) => ({ ...item, ...asObject(backendById.get(item.value)) })),
        ...backend.filter((item) => !defaultIds.has(item.value)),
      ];
      const fragment = document.createDocumentFragment();
      source.map((item) => ({ ...item, value: item.value ?? item.id ?? item.key, label: item.label ?? item.name ?? item.value })).forEach((item) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "quick-filter";
        button.dataset.quickFilter = item.value;
        button.innerHTML = `<ha-icon icon="${esc(item.icon || "mdi:filter-outline")}"></ha-icon><span>${esc(item.label)}</span>`;
        button.addEventListener("click", () => this._activateQuickFilter(item).catch((error) => this._showError(error)));
        fragment.append(button);
      });
      this._nodes.quickFilters.replaceChildren(fragment);
    }

    _activateQuickFilter(item) {
      const filters = clone(item.filters ?? item.query ?? {});
      const aliases = {
        category: "categories", event_type: "event_types", severity: "severities",
        outcome: "outcomes", audibility: "audibilities", external: "is_external",
        mode: "modes", preset: "presets", power_profile: "power_profiles",
      };
      Object.entries(aliases).forEach(([legacy, canonical]) => {
        if (filters[legacy] === undefined || filters[canonical] !== undefined) return;
        filters[canonical] = clone(filters[legacy]);
        delete filters[legacy];
      });
      if (item.period === "last_hour") {
        filters.start = localInputValue(Date.now() - 3600000);
        filters.end = "";
      }
      if (item.period === "today") {
        const start = new Date();
        start.setHours(0, 0, 0, 0);
        filters.start = localInputValue(start);
        filters.end = "";
      }
      this._filterDraft = { relevant_only: true, ...filters };
      this._writeFilterControls();
      return this._applyFilters();
    }

    _renderSavedFilterOptions() {
      if (!this._nodes?.savedFilterSelect) return;
      const current = this._nodes.savedFilterSelect.value;
      const fragment = document.createDocumentFragment();
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Filtros salvos";
      fragment.append(placeholder);
      this._savedFilters.forEach((item) => {
        const option = document.createElement("option");
        option.value = item.id;
        option.textContent = `${item.is_default ? "★ " : ""}${item.name}`;
        fragment.append(option);
      });
      this._nodes.savedFilterSelect.replaceChildren(fragment);
      if (this._savedFilters.some((item) => item.id === current)) this._nodes.savedFilterSelect.value = current;
    }

    _loadSavedFilter(id) {
      const item = this._savedFilters.find((saved) => saved.id === id);
      if (!item) return;
      this._filterDraft = clone(item.filters || {});
      this._advancedGroups = clone(item.advanced || [{ operator: "and", conditions: [] }]);
      this._writeFilterControls();
      this._renderAdvancedBuilder();
      return this._applyFilters();
    }

    _openSaveFilter() {
      this._nodes.savedFilterDialog.querySelector("form").reset();
      this._openDialog(this._nodes.savedFilterDialog);
    }

    async _saveFilter() {
      const form = this._nodes.savedFilterDialog.querySelector("form");
      const data = new FormData(form);
      const name = String(data.get("name") || "").trim();
      if (!name) return;
      this._readAllFilterControls();
      if (data.get("is_default")) this._savedFilters.forEach((item) => { item.is_default = false; });
      const existing = this._savedFilters.find((item) => item.name.toLocaleLowerCase("pt-BR") === name.toLocaleLowerCase("pt-BR"));
      const record = {
        id: existing?.id || (crypto.randomUUID?.() ?? `${Date.now()}-${Math.random()}`),
        name,
        is_default: Boolean(data.get("is_default")),
        filters: clone(this._filterDraft),
        advanced: clone(this._advancedGroups),
      };
      if (existing) Object.assign(existing, record);
      else this._savedFilters.push(record);
      storageSet(this._storageKey("saved_filters"), this._savedFilters);
      await this._persistSavedFilters();
      this._renderSavedFilterOptions();
      this._nodes.savedFilterSelect.value = record.id;
      this._nodes.savedFilterDialog.close();
      this._setStatus(`Filtro “${name}” salvo.`, "success", 3500);
    }

    async _renameCurrentSavedFilter() {
      const id = this._nodes.savedFilterSelect.value;
      const record = this._savedFilters.find((item) => item.id === id);
      if (!record) return;
      const name = window.prompt("Novo nome do filtro", record.name);
      if (name === null || !name.trim()) return;
      record.name = name.trim();
      storageSet(this._storageKey("saved_filters"), this._savedFilters);
      await this._persistSavedFilters();
      this._renderSavedFilterOptions();
      this._nodes.savedFilterSelect.value = id;
    }

    async _deleteCurrentSavedFilter() {
      const id = this._nodes.savedFilterSelect.value;
      if (!id) return;
      const confirmed = await this._confirm("Excluir filtro salvo", "A consulta salva será removida; os eventos do diagnóstico não serão alterados.");
      if (!confirmed) return;
      this._savedFilters = this._savedFilters.filter((item) => item.id !== id);
      storageSet(this._storageKey("saved_filters"), this._savedFilters);
      await this._persistSavedFilters();
      this._renderSavedFilterOptions();
    }

    async _persistSavedFilters() {
      if (!this._hass?.user?.is_admin) return false;
      const defaultRecord = this._savedFilters.find((item) => item.is_default);
      const settings = {
        ...clone(this._settingsSaved),
        saved_filters: clone(this._savedFilters),
        default_saved_filter_id: defaultRecord?.id || "",
      };
      const response = await this._ws("update_settings", { settings });
      this._settingsSaved = { ...clone(DEFAULT_SETTINGS), ...canonicalSettings(response?.settings ?? settings) };
      if (!this._settingsDirty) this._settingsDraft = clone(this._settingsSaved);
      return true;
    }

    _renderAdvancedBuilder() {
      if (!this._nodes?.advancedBuilder) return;
      const fieldOptions = this._catalog.fields.length
        ? this._catalog.fields
        : ["category", "event_type", "severity", "outcome", "entity_id", "user_id", "mode", "treatment", "preset", "power_profile", "before.state", "after.state", "diff.target_temperature"].map(normalizeOption);
      const operatorOptions = this._catalog.operators.length
        ? this._catalog.operators
        : DEFAULT_OPERATORS.map(([value, label]) => ({ value, label }));
      const fragment = document.createDocumentFragment();
      this._advancedGroups.forEach((group, groupIndex) => {
        const section = document.createElement("section");
        section.className = "filter-group";
        section.innerHTML = `
          <header><label>Condições do grupo<select data-group-operator="${groupIndex}"><option value="and" ${group.operator === "and" ? "selected" : ""}>TODAS · AND</option><option value="or" ${group.operator === "or" ? "selected" : ""}>QUALQUER · OR</option></select></label><div class="button-row"><button type="button" class="secondary" data-add-condition="${groupIndex}"><ha-icon icon="mdi:plus"></ha-icon>Condição</button><button type="button" class="secondary icon-button" data-remove-group="${groupIndex}" aria-label="Remover grupo"><ha-icon icon="mdi:delete-outline"></ha-icon></button></div></header>
          <div class="conditions"></div>`;
        const conditions = section.querySelector(".conditions");
        group.conditions.forEach((condition, conditionIndex) => {
          const row = document.createElement("div");
          row.className = "condition-row";
          row.innerHTML = `
            <label><span>Campo</span><select data-condition-field="${groupIndex}:${conditionIndex}"><option value="">Selecione</option>${fieldOptions.map((item) => `<option value="${esc(item.value)}" ${condition.field === item.value ? "selected" : ""}>${esc(item.label)}</option>`).join("")}</select></label>
            <label><span>Operador</span><select data-condition-operator="${groupIndex}:${conditionIndex}">${operatorOptions.map((item) => `<option value="${esc(item.value)}" ${condition.operator === item.value ? "selected" : ""}>${esc(item.label)}</option>`).join("")}</select></label>
            <label><span>Valor</span><input data-condition-value="${groupIndex}:${conditionIndex}" value="${esc(condition.value ?? "")}" placeholder="Valor ou intervalo"></label>
            <button type="button" class="secondary icon-button" data-remove-condition="${groupIndex}:${conditionIndex}" aria-label="Remover condição"><ha-icon icon="mdi:close"></ha-icon></button>`;
          conditions.append(row);
        });
        fragment.append(section);
      });
      this._nodes.advancedBuilder.replaceChildren(fragment);
      this._bindAdvancedBuilderEvents();
      this._updateFilterCount();
    }

    _bindAdvancedBuilderEvents() {
      const builder = this._nodes.advancedBuilder;
      builder.querySelectorAll("[data-group-operator]").forEach((control) => control.addEventListener("change", () => {
        this._advancedGroups[Number(control.dataset.groupOperator)].operator = control.value;
        this._updateFilterCount();
      }));
      builder.querySelectorAll("[data-add-condition]").forEach((button) => button.addEventListener("click", () => {
        this._advancedGroups[Number(button.dataset.addCondition)].conditions.push({ field: "", operator: "eq", value: "" });
        this._renderAdvancedBuilder();
      }));
      builder.querySelectorAll("[data-remove-group]").forEach((button) => button.addEventListener("click", () => {
        this._advancedGroups.splice(Number(button.dataset.removeGroup), 1);
        if (!this._advancedGroups.length) this._advancedGroups.push({ operator: "and", conditions: [] });
        this._renderAdvancedBuilder();
      }));
      builder.querySelectorAll("[data-remove-condition]").forEach((button) => button.addEventListener("click", () => {
        const [groupIndex, conditionIndex] = button.dataset.removeCondition.split(":").map(Number);
        this._advancedGroups[groupIndex].conditions.splice(conditionIndex, 1);
        this._renderAdvancedBuilder();
      }));
      ["field", "operator", "value"].forEach((name) => {
        builder.querySelectorAll(`[data-condition-${name}]`).forEach((control) => control.addEventListener(name === "value" ? "input" : "change", () => {
          const [groupIndex, conditionIndex] = control.dataset[`condition${name[0].toUpperCase()}${name.slice(1)}`].split(":").map(Number);
          this._advancedGroups[groupIndex].conditions[conditionIndex][name] = control.value;
          this._updateFilterCount();
        }));
      });
    }

    _serializeAdvancedGroups() {
      return {
        logic: "and",
        conditions: this._advancedGroups.map((group) => ({
          logic: group.operator === "or" ? "or" : "and",
          conditions: group.conditions.filter((condition) => condition.field).map((condition) => ({
            field: condition.field,
            operator: this._canonicalOperator(condition.operator),
            value: this._conditionValue(this._canonicalOperator(condition.operator), condition.value),
          })),
        })).filter((group) => group.conditions.length),
      };
    }

    _addFilterGroup() {
      this._advancedGroups.push({ operator: "and", conditions: [{ field: "", operator: "eq", value: "" }] });
      this._renderAdvancedBuilder();
    }

    _renderOverview() {
      if (!this.shadowRoot) return;
      const snapshot = this._snapshot || {};
      const status = asObject(snapshot.status);
      const counters = asObject(snapshot.counters);
      const storage = asObject(snapshot.storage ?? snapshot.database);
      const recent = asArray(snapshot.recent_events);
      const activeAnomalies = snapshot.active_anomalies ?? counters.active_anomalies ?? this._anomalies.filter((item) => item.status === "active").length;
      const healthLabel = status.health
        ?? snapshot.health
        ?? (typeof snapshot.status === "string" ? snapshot.status : snapshot.healthy === true ? "Operacional" : snapshot.healthy === false ? "Com falha" : "Não informada");
      const metrics = [
        ["health", "Saúde do diagnóstico", healthLabel, "mdi:heart-pulse", snapshot.healthy === false || status.healthy === false ? "error" : "success"],
        ["supervisor", "Estado do Supervisor", status.supervisor_state ?? snapshot.supervisor_state ?? "Não disponível", "mdi:robot-outline", "info"],
        ["treatment", "Tratamento atual", status.treatment ?? snapshot.treatment ?? "Indisponível", "mdi:thermostat-auto", "cyan"],
        ["last_decision", "Última decisão", this._shortText(snapshot.last_decision?.summary ?? snapshot.last_decision ?? "Nenhuma"), "mdi:state-machine", "purple"],
        ["last_action", "Última ação", this._shortText(snapshot.last_action?.summary ?? snapshot.last_action ?? "Nenhuma"), "mdi:play-circle-outline", "orange"],
        ["last_esphome", "Última solicitação ESPHome", this._shortText(snapshot.last_esphome?.summary ?? snapshot.last_esphome_request?.summary ?? "Nenhuma"), "mdi:remote", "orange"],
        ["external", "Última alteração externa", this._shortText(snapshot.last_external_change?.summary ?? "Nenhuma"), "mdi:account-arrow-right", "cyan"],
        ["anomalies", "Anomalias ativas", activeAnomalies ?? 0, "mdi:alert-decagram", Number(activeAnomalies || 0) ? "error" : "success"],
        ["hour", "Eventos na última hora", counters.last_hour ?? counters.events_last_hour ?? 0, "mdi:clock-outline", "info"],
        ["day", "Eventos nas últimas 24 h", counters.last_24h ?? counters.events_last_24h ?? 0, "mdi:calendar-clock", "info"],
        ["database", "Tamanho do banco", formatBytes(storage.size_bytes ?? counters.database_size_bytes ?? 0), "mdi:database", "purple"],
        ["capture", "Modo de captura", status.capture_mode ?? snapshot.capture_mode ?? snapshot.settings?.capture_mode ?? this._settingsSaved.capture_mode, "mdi:record-rec", "orange"],
        ["retention", "Retenção", `${snapshot.settings?.retention_essential_days ?? this._settingsSaved.retention_essential_days} dias`, "mdi:archive-clock-outline", "info"],
        ["rate", "Taxa atual", `${counters.current_rate ?? counters.events_per_minute ?? 0} ev/min`, "mdi:speedometer", "info"],
      ];
      const metricsNode = this.shadowRoot.querySelector("#overview-metrics");
      if (metricsNode) {
        const fragment = document.createDocumentFragment();
        metrics.forEach(([key, label, value, icon, tone]) => {
          const article = document.createElement("article");
          article.className = `metric ${tone}`;
          article.dataset.metric = key;
          article.innerHTML = `<ha-icon icon="${icon}"></ha-icon><div><span>${esc(label)}</span><strong class="metric-value" title="${esc(semanticValue(value))}">${esc(semanticValue(value))}</strong></div>`;
          fragment.append(article);
        });
        metricsNode.replaceChildren(fragment);
      }

      const stateNode = this.shadowRoot.querySelector("#overview-state");
      if (stateNode) {
        const currentTreatment = status.treatment ?? snapshot.treatment;
        const effectiveApplicable = status.effective_configuration_applicable
          ?? snapshot.effective_configuration_applicable
          ?? ["Aquecimento", "Refrigeração", "Desumidificação"].includes(currentTreatment);
        const effectiveFallback = currentTreatment == null
          ? "Tratamento indisponível"
          : currentTreatment === "Nenhum"
            ? "Não aplicável — sem tratamento ativo"
            : effectiveApplicable
              ? "Entidade indisponível"
              : "Não aplicável ao tratamento atual";
        const entries = [
          ["Tratamento", currentTreatment ?? "Entidade indisponível"],
          ["Modo físico", status.physical_mode ?? snapshot.physical_mode ?? "Entidade indisponível"],
          ["Preset efetivo", status.preset ?? snapshot.preset ?? effectiveFallback],
          ["Potência efetiva", status.power_profile ?? snapshot.power_profile ?? effectiveFallback],
          ["Agenda influenciando", status.agenda ?? snapshot.agenda ?? "Não informada"],
          ["Proteção ativa", status.protection ?? snapshot.protection ?? "Nenhuma"],
          ["Última confirmação", snapshot.last_confirmation?.summary ?? snapshot.last_confirmation?.event_type ?? "Nenhuma desde o início do diagnóstico"],
        ];
        stateNode.replaceChildren(this._definitionFragment(entries));
      }

      const flowNode = this.shadowRoot.querySelector("#last-flow");
      if (flowNode) {
        const flow = asArray(snapshot.last_complete_flow?.steps ?? snapshot.last_flow?.steps ?? snapshot.last_complete_flow ?? snapshot.last_flow);
        const steps = this._overviewFlowSteps(flow);
        const fragment = document.createDocumentFragment();
        steps.forEach((step, index) => {
          const item = document.createElement("div");
          item.className = `flow-step ${esc(step.status || "unknown")}`;
          item.title = step.fullText || step.label;
          item.innerHTML = `<span class="flow-index">${index + 1}</span><div><strong>${esc(step.label)}</strong>${step.detail ? `<small>${esc(step.detail)}</small>` : ""}</div>${index < steps.length - 1 ? '<ha-icon icon="mdi:arrow-right"></ha-icon>' : ""}`;
          fragment.append(item);
        });
        flowNode.replaceChildren(fragment);
      }

      const recentNode = this.shadowRoot.querySelector("#recent-events");
      if (recentNode) {
        recentNode.replaceChildren(this._compactEventFragment(recent.length ? recent : asArray(snapshot.events).slice(0, 8)));
      }
      this._renderMaintenance();
    }

    _overviewFlowSteps(flow) {
      const phases = [
        ["sensor", "Sensor mudou"],
        ["evaluation", "Supervisor avaliou"],
        ["decision", "Decisão calculada"],
        ["action", "Ação verificada"],
        ["observed", "Estado observado"],
      ];
      const matches = new Map();
      asArray(flow).forEach((rawStep) => {
        const step = typeof rawStep === "string" ? { label: rawStep } : asObject(rawStep);
        const phase = this._flowPhase(step);
        if (phase) matches.set(phase, step);
      });
      return phases.map(([phase, label]) => {
        const match = matches.get(phase);
        const fullText = match
          ? semanticValue(match.label || match.summary || match.reason || match.event_type || label)
          : "";
        return {
          label,
          status: match?.status || match?.outcome || "unknown",
          detail: fullText ? this._shortText(fullText, 92) : "",
          fullText,
        };
      });
    }

    _flowPhase(step) {
      const signature = `${step.event_type || ""} ${step.category || ""} ${step.label || ""}`.toLocaleLowerCase("pt-BR");
      if (/localtuya|external|confirm|observ/.test(signature)) return "observed";
      if (/transmiss|action|service|command|comando|eco_requested/.test(signature)) return "action";
      if (/decision|decis/.test(signature)) return "decision";
      if (/evaluation|avalia|supervisor avaliou/.test(signature)) return "evaluation";
      if (/state|sensor|input_|mudou|alterou/.test(signature)) return "sensor";
      return null;
    }

    _definitionFragment(entries) {
      const fragment = document.createDocumentFragment();
      entries.forEach(([label, value]) => {
        const dt = document.createElement("dt");
        dt.textContent = label;
        const dd = document.createElement("dd");
        dd.textContent = semanticValue(value);
        fragment.append(dt, dd);
      });
      return fragment;
    }

    _compactEventFragment(events) {
      const fragment = document.createDocumentFragment();
      if (!events.length) {
        const empty = document.createElement("div");
        empty.className = "empty-state";
        empty.textContent = "Nenhum evento recente disponível.";
        fragment.append(empty);
        return fragment;
      }
      events.forEach((event) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "compact-event";
        button.dataset.eventId = getEventId(event);
        button.innerHTML = `<time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time><span class="severity-dot ${esc(event.severity || "info")}"></span><strong>${esc(event.summary || event.event_type || "Evento")}</strong><small>${esc(event.entity_id || event.source_component || event.category || "")}</small><ha-icon icon="mdi:chevron-right"></ha-icon>`;
        fragment.append(button);
      });
      return fragment;
    }

    _renderEventView(tab) {
      const state = this._viewStates.get(tab);
      const container = this.shadowRoot.querySelector(`#events-${tab}`);
      if (!state || !container) return;
      const total = this.shadowRoot.querySelector(`#total-${tab}`);
      if (total) total.textContent = state.total === null ? `${state.items.length} nesta página` : `≈ ${state.total} eventos`;
      if (tab === "timeline") container.replaceChildren(this._timelineFragment(state.items));
      else if (tab === "decisions") container.replaceChildren(this._decisionFragment(state.items));
      else if (tab === "states") container.replaceChildren(this._stateChangeFragment(state.items));
      else if (tab === "actions") container.replaceChildren(this._actionFragment(state.items));
      else if (tab === "external") container.replaceChildren(this._externalFragment(state.items));
      else if (tab === "observations") container.replaceChildren(this._observationFragment(state.items));
      container.dataset.renderedAt = new Date().toISOString();
      this._updateAdminControls();
    }

    _emptyFragment(message = "Nenhum evento corresponde à consulta.") {
      const fragment = document.createDocumentFragment();
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.innerHTML = `<ha-icon icon="mdi:timeline-remove-outline"></ha-icon><span>${esc(message)}</span>`;
      fragment.append(empty);
      return fragment;
    }

    _timelineFragment(events) {
      if (!events.length) return this._emptyFragment();
      const fragment = document.createDocumentFragment();
      const wrap = document.createElement("div");
      wrap.className = "table-wrap";
      const table = document.createElement("table");
      table.className = "event-table";
      const columnLabels = {
        occurred_at: "Horário", severity: "Severidade", category: "Categoria",
        summary: "Evento", event_type: "Tipo", actor: "Ator", origin: "Origem",
        entity_id: "Entidade", before: "Antes", after: "Depois", outcome: "Resultado",
        correlation_id: "Correlação", mode: "Modo", treatment: "Tratamento",
        preset: "Preset", power_profile: "Potência", audibility: "Audibilidade",
      };
      const configured = asArray(this._settingsSaved.interface_columns).map(String);
      const columns = (configured.length ? configured : DEFAULT_SETTINGS.interface_columns)
        .filter((column, index, source) => column && source.indexOf(column) === index);
      table.style.minWidth = `${Math.max(760, columns.length * 125)}px`;
      table.innerHTML = `<thead><tr>${columns.map((column) => `<th>${esc(columnLabels[column] || humanizeCode(column))}</th>`).join("")}</tr></thead><tbody></tbody>`;
      const tbody = table.querySelector("tbody");
      events.forEach((event) => {
        const row = document.createElement("tr");
        row.tabIndex = 0;
        row.dataset.eventId = getEventId(event);
        row.className = `${event.is_anomaly ? "anomaly" : ""} ${event.is_external ? "external" : ""}`;
        row.innerHTML = columns.map((column) => `<td>${this._timelineCell(column, event)}</td>`).join("");
        row.addEventListener("keydown", (keyEvent) => {
          if (keyEvent.key === "Enter" || keyEvent.key === " ") {
            keyEvent.preventDefault();
            this._openEvent(getEventId(event));
          }
        });
        tbody.append(row);
      });
      wrap.append(table);
      fragment.append(wrap);
      return fragment;
    }

    _timelineCell(column, event) {
      const technical = Boolean(this._settingsSaved.interface_show_technical_codes);
      const cells = {
        occurred_at: () => `<time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time>${Number(event.compacted_count || 1) > 1 ? `<small>${Number(event.compacted_count)} ocorrências</small>` : ""}`,
        severity: () => this._chip(event.severity || "info", event.severity || "info", "severity"),
        category: () => this._chip(event.category || "—", event.category || "—", "category"),
        summary: () => `<strong>${esc(event.summary || event.event_type || "Evento")}</strong>${technical && event.event_type ? `<small>${esc(event.event_type)}</small>` : ""}`,
        event_type: () => `<code>${esc(event.event_type || "—")}</code>`,
        actor: () => esc(event.user_name || event.actor_name || event.actor_type || "Sistema / não determinado"),
        origin: () => esc(event.origin_label || event.origin_class || event.source_component || "—"),
        entity_id: () => `<code>${esc(event.entity_id || event.source_entity_id || "—")}</code>`,
        before: () => esc(this._snapshotSummary(event.before_json ?? event.before)),
        after: () => esc(this._snapshotSummary(event.after_json ?? event.after)),
        outcome: () => this._chip(event.outcome || "unknown", event.outcome_label || event.outcome || "Não informado", "outcome"),
        correlation_id: () => `<code title="${esc(event.correlation_id || "")}">${esc(this._shortId(event.correlation_id))}</code>`,
        mode: () => esc(event.climate_mode || event.mode || "—"),
        treatment: () => esc(event.treatment || "—"),
        preset: () => esc(event.preset || "—"),
        power_profile: () => esc(event.power_profile || "—"),
        audibility: () => this._chip(event.expected_audibility || "unknown", event.audibility_label || event.expected_audibility || "Não determinada", "audibility"),
      };
      if (cells[column]) return cells[column]();
      return esc(semanticValue(event[column]));
    }

    _decisionFragment(events) {
      if (!events.length) return this._emptyFragment("Nenhuma avaliação encontrada.");
      const fragment = document.createDocumentFragment();
      const grid = document.createElement("div");
      grid.className = "decision-grid";
      events.forEach((event) => {
        const details = asObject(event.details_json ?? event.details);
        const demands = asObject(event.demands ?? details.demands);
        const card = document.createElement("article");
        card.className = "decision-card";
        card.innerHTML = `
          <header><div><time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time><h3>${esc(event.summary || "Avaliação do Supervisor")}</h3></div>${this._chip(event.outcome || "calculated", event.outcome_label || event.outcome || "Calculada", "outcome")}</header>
          <div class="decision-columns"><section><span class="section-label">ENTRADAS</span><dl>${this._dlHtml([["Gatilho", event.trigger_label || event.trigger || details.trigger], ["Temperatura", details.temperature ?? details.inputs?.temperature], ["Umidade", details.humidity ?? details.inputs?.humidity], ["Agenda", event.agenda ?? details.agenda]])}</dl></section><section><span class="section-label">DEMANDAS</span><dl>${this._dlHtml([["Heat", demands.heat], ["Cool", demands.cool], ["Dry", demands.dry], ["Prioridade", details.priority]])}</dl></section><section><span class="section-label">DECISÃO</span><dl>${this._dlHtml([["Anterior", details.previous_decision ?? event.before_treatment], ["Calculada", event.treatment ?? details.treatment], ["Preset", event.preset ?? details.preset], ["Potência", event.power_profile ?? details.power_profile]])}</dl></section><section><span class="section-label">RESULTADO</span><dl>${this._dlHtml([["Ação", event.action_name ?? details.action], ["Motivo", event.reason ?? details.reason], ["Proteção", event.protection ?? details.protection], ["Correlação", this._shortId(event.correlation_id)]])}</dl></section></div>
          <footer><button type="button" class="secondary" data-event-id="${esc(getEventId(event))}">Ver avaliação completa</button></footer>`;
        grid.append(card);
      });
      fragment.append(grid);
      return fragment;
    }

    _stateChangeFragment(events) {
      if (!events.length) return this._emptyFragment("Nenhuma mudança de estado encontrada.");
      const fragment = document.createDocumentFragment();
      const list = document.createElement("div");
      list.className = "state-change-list";
      events.forEach((event) => {
        const before = event.before_json ?? event.before;
        const after = event.after_json ?? event.after;
        const diff = event.diff_json ?? event.diff;
        const relevant = asObject(diff).changed_fields_relevant ?? event.changed_fields_relevant ?? Object.keys(asObject(diff));
        const card = document.createElement("article");
        card.className = "state-change-card";
        card.innerHTML = `
          <header><div><time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time><h3>${esc(event.summary || event.entity_id || "Mudança de estado")}</h3><code>${esc(event.entity_id || "—")}</code></div>${event.is_external ? this._chip("external", "Externa", "origin") : this._chip("observed", "Observada", "origin")}</header>
          <div class="before-after"><section><span>ANTES</span><strong>${esc(this._snapshotSummary(before))}</strong></section><ha-icon icon="mdi:arrow-right"></ha-icon><section><span>DEPOIS</span><strong>${esc(this._snapshotSummary(after))}</strong></section></div>
          <div class="chip-row">${asArray(relevant).slice(0, 12).map((field) => this._chip("changed", typeof field === "string" ? field : field.field || field.name, "field")).join("")}</div>
          <footer><span>${esc(event.actor_name || event.user_name || "Ator não determinado")}</span><button type="button" class="secondary" data-event-id="${esc(getEventId(event))}">Antes · Depois · Diff</button></footer>`;
        list.append(card);
      });
      fragment.append(list);
      return fragment;
    }

    _actionFragment(events) {
      if (!events.length) return this._emptyFragment("Nenhuma ação ou solicitação de transmissão encontrada.");
      const fragment = document.createDocumentFragment();
      const grid = document.createElement("div");
      grid.className = "action-grid";
      events.forEach((event) => {
        const details = asObject(event.details_json ?? event.details);
        const requested = asObject(event.service_data ?? details.service_data ?? details.requested);
        const card = document.createElement("article");
        card.className = "action-card";
        card.innerHTML = `
          <header><div class="chip-row">${this._chip(event.expected_audibility || "unknown", event.audibility_label || event.expected_audibility || "Não determinada", "audibility")}${this._chip(event.outcome || "requested", event.outcome_label || event.outcome || "Solicitada", "outcome")}</div><time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time></header>
          <h3>${esc(event.action_name || event.service || event.event_type || "Ação")}</h3><p>${esc(event.summary || "Solicitação observada no Home Assistant")}</p>
          <dl>${this._dlHtml([["Solicitado por", event.user_name || event.actor_name || event.source_component], ["Modo", event.mode ?? requested.mode], ["Alvo", requested.target_temperature ?? requested.temperature], ["Fan", requested.fan ?? requested.fan_mode], ["Swing", requested.swing ?? requested.swing_mode], ["Confirmação", details.confirmation ?? event.confirmation], ["Tempo até confirmação", formatDuration(details.confirmation_delay_ms ?? event.confirmation_delay_ms)], ["Correlação", this._shortId(event.correlation_id)]])}</dl>
          <p class="layer-note">Representa uma <strong>solicitação do Home Assistant</strong>; não confirma emissão ou recepção física do frame.</p>
          <footer><button type="button" class="secondary" data-event-id="${esc(getEventId(event))}">Dados e correlação</button></footer>`;
        grid.append(card);
      });
      fragment.append(grid);
      return fragment;
    }

    _externalFragment(events) {
      if (!events.length) return this._emptyFragment("Nenhuma alteração externa encontrada.");
      const fragment = document.createDocumentFragment();
      const list = document.createElement("div");
      list.className = "external-list";
      events.forEach((event) => {
        const details = asObject(event.details_json ?? event.details);
        const card = document.createElement("article");
        card.className = "external-card";
        card.innerHTML = `
          <div class="external-icon"><ha-icon icon="mdi:account-question-outline"></ha-icon></div>
          <div class="external-main"><header><time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time>${this._chip(event.origin_class || "indeterminate", event.origin_label || event.origin_class || "Indeterminada", "origin")}</header><h3>${esc(event.summary || event.entity_id || "Alteração externa")}</h3><code>${esc(event.entity_id || "—")}</code><div class="before-after compact"><section><span>Antes</span><strong>${esc(this._snapshotSummary(event.before_json ?? event.before))}</strong></section><section><span>Depois</span><strong>${esc(this._snapshotSummary(event.after_json ?? event.after))}</strong></section></div><dl>${this._dlHtml([["Usuário", event.user_name || "Ator externo / origem não determinada"], ["Reação do Supervisor", details.supervisor_reaction], ["Consequência", details.consequence], ["Relação", event.correlation_class || details.correlation_class]])}</dl></div>
          <button type="button" class="secondary" data-event-id="${esc(getEventId(event))}">Investigar</button>`;
        list.append(card);
      });
      fragment.append(list);
      return fragment;
    }

    _observationFragment(events) {
      if (!events.length) return this._emptyFragment("Nenhuma observação manual registrada.");
      const fragment = document.createDocumentFragment();
      events.forEach((event) => {
        const details = asObject(event.details_json ?? event.details);
        const metadata = asObject(details.metadata);
        const observationId = getObservationId(event);
        const item = document.createElement("article");
        item.className = "observation-card";
        const isBeep = String(event.event_type || details.observation_type || "").includes("beep");
        item.innerHTML = `
          <ha-icon icon="${isBeep ? "mdi:volume-high" : "mdi:notebook-outline"}"></ha-icon><div><header><time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time>${this._chip("observed", "Observado pelo usuário", "outcome")}</header><h3>${esc(event.summary || metadata.title || details.title || (isBeep ? "Bip observado" : "Observação"))}</h3><p>${esc(event.note || details.note || event.technical_message || "Sem texto adicional")}</p><div class="chip-row">${asArray(metadata.tags ?? details.tags).map((tag) => this._chip("tag", tag, "field")).join("")}</div></div><div class="observation-actions"><button type="button" class="secondary" data-event-id="${esc(getEventId(event))}">Correlacionar</button>${observationId ? `<button type="button" class="secondary admin-only" data-delete-observation="${esc(observationId)}">Excluir</button>` : ""}</div>`;
        fragment.append(item);
      });
      return fragment;
    }

    _renderAnomalies() {
      const container = this.shadowRoot?.querySelector("#anomaly-list");
      if (!container) return;
      if (!this._anomalies.length) {
        container.replaceChildren(this._emptyFragment("Nenhuma anomalia neste estado."));
        return;
      }
      const fragment = document.createDocumentFragment();
      this._anomalies.forEach((anomaly) => {
        const status = anomaly.status || anomaly.state || "active";
        const relatedEventIds = asArray(anomaly.related_event_ids ?? anomaly.event_ids);
        const firstRelatedEvent = anomaly.event_id || relatedEventIds[0];
        const card = document.createElement("article");
        card.className = `anomaly-card severity-${esc(anomaly.severity || "warning")}`;
        card.innerHTML = `
          <header><div class="chip-row">${this._chip(anomaly.severity || "warning", anomaly.severity_label || anomaly.severity || "Atenção", "severity")}${this._chip(status, anomaly.status_label || status, "outcome")}</div><span class="anomaly-count">${Number(anomaly.count || anomaly.occurrences || 1)}×</span></header>
          <h3>${esc(anomaly.summary || anomaly.anomaly_type || anomaly.type || "Anomalia")}</h3><p>${esc(anomaly.explanation || anomaly.technical_message || "Sem explicação adicional")}</p>
          <dl>${this._dlHtml([["Primeira ocorrência", this._formatDate(anomaly.first_seen)], ["Última ocorrência", this._formatDate(anomaly.last_seen)], ["Eventos relacionados", relatedEventIds.length || (anomaly.event_id ? 1 : 0)], ["Reconhecida por", anomaly.acknowledged_by], ["Reconhecida em", this._formatDate(anomaly.acknowledged_at)], ["Nota", anomaly.note]])}</dl>
          <footer>${status === "active" ? `<button type="button" class="secondary" data-anomaly-action="acknowledge" data-anomaly-id="${esc(anomaly.anomaly_id || anomaly.id)}">Reconhecer</button>` : ""}${status !== "resolved" ? `<button type="button" data-anomaly-action="resolve" data-anomaly-id="${esc(anomaly.anomaly_id || anomaly.id)}">Resolver</button>` : ""}${firstRelatedEvent ? `<button type="button" class="secondary" data-event-id="${esc(firstRelatedEvent)}">Eventos relacionados</button>` : ""}</footer>`;
        fragment.append(card);
      });
      container.replaceChildren(fragment);
      this._updateAdminControls();
    }

    _renderStatistics() {
      const container = this.shadowRoot?.querySelector("#statistics-grid");
      if (!container) return;
      const source = this._statistics || {};
      const groups = [
        ["Eventos por hora", source.events_by_hour ?? source.by_hour], ["Eventos por categoria", source.events_by_category ?? source.by_category],
        ["Eventos por tipo", source.events_by_type ?? source.by_type], ["Eventos por origem", source.events_by_origin ?? source.by_origin],
        ["Eventos por ator", source.events_by_actor ?? source.by_actor], ["Eventos por modo", source.events_by_mode ?? source.by_mode],
        ["Erros por tipo", source.errors_by_type], ["Top 10 produtores", source.top_producers],
        ["Por tratamento", source.by_treatment], ["Por preset", source.by_preset],
        ["Por potência", source.by_power], ["Por audibilidade", source.by_audibility],
      ];
      const summary = [
        ["Eventos", source.total_events], ["Avaliações", source.total_evaluations],
        ["Mudanças externas", source.external_changes], ["Transmissões", source.transmissions ?? source.total_transmission_requests],
        ["SensorUpdate", source.sensor_updates], ["Decisões com ação", source.decisions_with_action],
        ["Decisões sem ação", source.decisions_without_action], ["Bloqueios", source.blocked],
        ["Ações audíveis esperadas", source.expected_audible_actions], ["Confirmações LocalTuya", source.localtuya_confirmations],
        ["Anomalias", source.anomalies ?? source.active_anomalies],
      ];
      const fragment = document.createDocumentFragment();
      const summaryCard = document.createElement("article");
      summaryCard.className = "stat-card stat-summary";
      summaryCard.innerHTML = `<h3>Resumo</h3><div class="stat-summary-grid">${summary.map(([label, value]) => `<div><span>${esc(label)}</span><strong>${esc(value ?? 0)}</strong></div>`).join("")}</div>`;
      fragment.append(summaryCard);
      groups.forEach(([title, data]) => {
        const rows = this._normalizeAggregation(data).slice(0, title.startsWith("Top") ? 10 : 24);
        const card = document.createElement("article");
        card.className = "stat-card";
        const max = Math.max(1, ...rows.map((item) => Number(item.count || item.value || 0)));
        card.innerHTML = `<h3>${esc(title)}</h3><div class="bars">${rows.length ? rows.map((item) => { const value = Number(item.count ?? item.total ?? 0); const label = item.label ?? item.key ?? item.value ?? "—"; return `<div class="bar-row"><span title="${esc(label)}">${esc(label)}</span><div><i style="width:${Math.max(2, (value / max) * 100)}%"></i></div><strong>${value}</strong></div>`; }).join("") : '<div class="empty-small">Sem dados</div>'}</div>`;
        fragment.append(card);
      });
      container.replaceChildren(fragment);
    }

    _normalizeAggregation(value) {
      if (Array.isArray(value)) return value.map((item) => typeof item === "object" ? item : { key: String(item), count: 1 });
      return Object.entries(asObject(value)).map(([key, count]) => ({ key, label: key, count }));
    }

    async _openEvent(eventId) {
      if (!eventId) return;
      this._detailEvent = { event_id: eventId };
      this._detailEvaluation = null;
      this._detailCorrelation = [];
      this._activeDetailTab = "comparison";
      this._nodes.detailLoading.hidden = false;
      this._nodes.detailContent.replaceChildren();
      // Always use the top layer. A non-modal dialog remains inside the card's
      // containment context and can be clipped by the dashboard. CSS still
      // renders this as a side panel when that interface mode is selected.
      this._openDialog(this._nodes.eventDialog, true);
      try {
        const response = await this._ws("get_event", { event_id: eventId });
        const event = asObject(response?.event ?? response);
        this._detailEvent = event;
        const relatedRequests = [];
        if (event.evaluation_id) relatedRequests.push(this._ws("get_evaluation", { evaluation_id: event.evaluation_id }).then((value) => { this._detailEvaluation = asObject(value?.evaluation ?? value); }));
        if (event.correlation_id) relatedRequests.push(this._ws("get_correlation", { correlation_id: event.correlation_id }).then((value) => { this._detailCorrelation = normalizeItems(value, "items", "events"); }));
        await Promise.allSettled(relatedRequests);
        this._renderEventDetail();
      } catch (error) {
        this._nodes.detailLoading.hidden = true;
        const alert = document.createElement("ha-alert");
        alert.setAttribute("alert-type", "error");
        alert.textContent = error?.message || String(error);
        this._nodes.detailContent.replaceChildren(alert);
      }
    }

    _renderEventDetail() {
      const event = this._detailEvent || {};
      this._nodes.detailLoading.hidden = true;
      this.shadowRoot.querySelector("#detail-type").textContent = this._settingsSaved.interface_show_technical_codes
        ? `${event.category || "evento"} · ${event.event_type || ""}`
        : humanizeCode(event.category || "evento");
      this.shadowRoot.querySelector("#detail-title").textContent = event.summary || "Detalhes do evento";
      this.shadowRoot.querySelector("#detail-chips").innerHTML = `${this._chip(event.severity || "info", event.severity || "Informação", "severity")}${this._chip(event.outcome || "unknown", event.outcome_label || event.outcome || "Não informado", "outcome")}${event.expected_audibility ? this._chip(event.expected_audibility, event.audibility_label || event.expected_audibility, "audibility") : ""}`;
      const wrapper = document.createElement("div");
      wrapper.className = "detail-panels";
      const comparison = document.createElement("section");
      comparison.dataset.detailPanel = "comparison";
      comparison.append(this._comparisonDetail(event));
      const context = document.createElement("section");
      context.dataset.detailPanel = "context";
      context.innerHTML = this._contextDetailHtml(event);
      const technical = document.createElement("section");
      technical.dataset.detailPanel = "technical";
      technical.innerHTML = this._technicalDetailHtml(event);
      const related = document.createElement("section");
      related.dataset.detailPanel = "related";
      related.append(this._relatedDetailFragment());
      wrapper.append(comparison, context, technical, related);
      this._nodes.detailContent.replaceChildren(wrapper);
      this._setDetailTab(this._activeDetailTab);
    }

    _comparisonDetail(event) {
      const fragment = document.createDocumentFragment();
      const before = event.before_json ?? event.before;
      const after = event.after_json ?? event.after;
      const diff = event.diff_json ?? event.diff;
      const rows = comparisonRows(before, after, diff);
      const lifecycle = document.createElement("div");
      lifecycle.className = "lifecycle-note";
      if (before === undefined && after === undefined) lifecycle.textContent = "Este tipo de evento não possui snapshots Antes/Depois. Chamadas de ação e eventos de manutenção usam outras seções técnicas.";
      else if (before === null) lifecycle.textContent = "Antes = null: a entidade ainda não existia.";
      else if (after === null) lifecycle.textContent = "Depois = null: a entidade foi removida.";
      else lifecycle.textContent = "Snapshots capturados atomicamente no state_changed; valores unknown e unavailable são preservados literalmente.";
      fragment.append(lifecycle);
      const tableWrap = document.createElement("div");
      tableWrap.className = "table-wrap comparison-wrap";
      const showUnchanged = Boolean(this._settingsSaved.interface_show_unchanged_attributes);
      const visible = showUnchanged ? rows : rows.filter((row) => row.changed);
      tableWrap.innerHTML = `<table class="comparison-table"><thead><tr><th>Campo</th><th>Antes</th><th>Depois</th><th>Mudança</th></tr></thead><tbody>${visible.map((row) => `<tr class="${row.changed ? "changed" : "unchanged"}"><th>${esc(row.field)}</th><td>${this._comparisonCellHtml(row.before)}</td><td>${this._comparisonCellHtml(row.after)}</td><td>${row.changed ? "alterado" : "—"}</td></tr>`).join("") || '<tr><td colspan="4">Nenhuma diferença estruturada disponível.</td></tr>'}</tbody></table>`;
      fragment.append(tableWrap);
      const full = document.createElement("details");
      full.innerHTML = `<summary>Mostrar estado completo</summary><div class="json-columns"><div><h4>Antes</h4><pre>${esc(this._pretty(before))}</pre></div><div><h4>Depois</h4><pre>${esc(this._pretty(after))}</pre></div><div><h4>Diferença</h4><pre>${esc(this._pretty(diff))}</pre></div></div>`;
      fragment.append(full);
      return fragment;
    }

    _contextDetailHtml(event) {
      const evaluation = this._detailEvaluation || {};
      const details = asObject(event.details_json ?? event.details);
      return `<div class="detail-grid">
        ${this._detailSectionHtml("Ocorrência", [["Horário", this._formatDate(event.occurred_at_local ?? event.occurred_at)], ["Recebido em", this._formatDate(event.received_at)], ["Entidade", event.entity_id], ["Domínio", event.domain], ["Componente", event.source_component]])}
        ${this._detailSectionHtml("Ator e origem", [["Tipo de ator", event.actor_type], ["Ator", event.actor_name], ["Usuário", event.user_name], ["User ID", event.user_id], ["Origem", event.origin_label || event.origin_class], ["Confiança", event.origin_confidence]])}
        ${this._detailSectionHtml("Contexto Home Assistant", [["Context ID", event.context_id], ["Parent context", event.parent_context_id], ["Correlation ID", event.correlation_id], ["Evaluation ID", event.evaluation_id], ["Classificação", event.correlation_class]])}
        ${this._detailSectionHtml("Supervisor", [["Gatilho", evaluation.trigger || details.trigger], ["Preset", event.preset ?? evaluation.presets], ["Potência", event.power_profile ?? evaluation.powers], ["Agenda", event.agenda ?? evaluation.agenda], ["Limites", event.limits ?? evaluation.limits], ["Proteções", event.protection ?? evaluation.protections], ["Motivo", event.reason ?? evaluation.reason]])}
      </div>`;
    }

    _technicalDetailHtml(event) {
      const details = event.details_json ?? event.details ?? {};
      const serviceData = event.service_data ?? asObject(details).service_data;
      const evaluation = this._detailEvaluation;
      const supervisorLayers = {
        agenda: event.agenda ?? evaluation?.agenda,
        presets: event.preset ?? evaluation?.presets,
        powers: event.power_profile ?? evaluation?.powers,
        protections: event.protection ?? evaluation?.protections,
      };
      return `<div class="technical-sections">
        <details open><summary>Raw event sanitizado</summary><pre>${esc(this._pretty(event))}</pre></details>
        <details><summary>Service data</summary>${this._technicalPayloadHtml(serviceData, "Não se aplica: este evento não foi originado por uma chamada de serviço capturada.")}</details>
        <details><summary>Avaliação completa</summary>${this._technicalPayloadHtml(evaluation, event.evaluation_id ? "A avaliação vinculada não pôde ser recuperada." : "Não se aplica: este evento não possui evaluation_id.")}</details>
        <details><summary>Agenda / Preset / Potência / Proteções</summary>${this._technicalPayloadHtml(supervisorLayers, "Nenhum dado estruturado dessas camadas está associado a este evento.")}</details>
        <p class="layer-note"><strong>Frame bruto:</strong> ${esc(event.raw_frame ?? "Não disponível nesta camada de diagnóstico.")}</p>
      </div>`;
    }

    _technicalPayloadHtml(value, emptyMessage) {
      const empty = value === undefined
        || value === null
        || (typeof value === "object" && !Array.isArray(value) && !Object.values(value).some((item) => item !== undefined && item !== null && item !== ""));
      return empty
        ? `<p class="detail-empty">${esc(emptyMessage)}</p>`
        : `<pre>${esc(this._pretty(value))}</pre>`;
    }

    _comparisonCellHtml(value) {
      const rendered = value && typeof value === "object"
        ? this._pretty(value)
        : semanticValue(value);
      return `<code class="comparison-value">${esc(rendered)}</code>`;
    }

    _relatedDetailFragment() {
      const fragment = document.createDocumentFragment();
      const relation = document.createElement("div");
      relation.className = "relation-explanation";
      relation.textContent = this._detailEvent?.correlation_class
        ? `Relação registrada: ${this._detailEvent.correlation_class}.`
        : "A proximidade temporal isolada não comprova causalidade.";
      fragment.append(relation);
      const list = document.createElement("div");
      list.className = "related-events";
      if (!this._detailCorrelation.length) {
        list.textContent = "Nenhum evento relacionado disponível.";
      } else {
        this._detailCorrelation.forEach((event) => {
          const button = document.createElement("button");
          button.type = "button";
          button.className = "related-event secondary";
          button.dataset.eventId = getEventId(event);
          button.innerHTML = `<time>${esc(this._formatDate(event.occurred_at_local ?? event.occurred_at))}</time><strong>${esc(event.summary || event.event_type || "Evento")}</strong><span>${esc(event.correlation_class || event.outcome || "")}</span>`;
          list.append(button);
        });
      }
      fragment.append(list);
      return fragment;
    }

    _setDetailTab(tab) {
      this._activeDetailTab = tab;
      this.shadowRoot.querySelectorAll("[data-detail-tab]").forEach((button) => {
        const active = button.dataset.detailTab === tab;
        button.classList.toggle("active", active);
        button.setAttribute("aria-selected", String(active));
      });
      this.shadowRoot.querySelectorAll("[data-detail-panel]").forEach((panel) => { panel.hidden = panel.dataset.detailPanel !== tab; });
    }

    _detailSectionHtml(title, rows) {
      return `<section class="detail-section"><h3>${esc(title)}</h3><dl>${this._dlHtml(rows)}</dl></section>`;
    }

    _dlHtml(rows) {
      return rows.filter(([, value]) => value !== undefined && value !== null && value !== "").map(([label, value]) => `<dt>${esc(label)}</dt><dd>${esc(semanticValue(value))}</dd>`).join("") || "<dd>Não informado</dd>";
    }

    _chip(value, label, kind = "generic") {
      return `<span class="chip ${esc(kind)} value-${esc(String(value).replace(/[^a-zA-Z0-9_-]/g, "-"))}">${esc(label)}</span>`;
    }

    _snapshotSummary(value) {
      if (value === null) return "null";
      if (value === undefined) return "—";
      const snapshot = asObject(value);
      const flat = flattenSnapshot(snapshot) || {};
      const fields = ["state", "power", "mode", "temperature", "target_temperature", "fan", "fan_mode", "swing", "preset", "power_profile"];
      const parts = fields.filter((key) => flat[key] !== undefined).slice(0, 3).map((key) => `${key}: ${semanticValue(flat[key])}`);
      return parts.length ? parts.join(" · ") : semanticValue(value);
    }

    _shortText(value, max = 64) {
      const text = semanticValue(value);
      return text.length > max ? `${text.slice(0, max - 1)}…` : text;
    }

    _shortId(value) {
      if (!value) return "—";
      const text = String(value);
      return text.length > 13 ? `${text.slice(0, 8)}…${text.slice(-4)}` : text;
    }

    _pretty(value) {
      try { return JSON.stringify(value ?? null, null, 2); } catch (_error) { return semanticValue(value); }
    }

    _formatDate(value) {
      if (!value) return "—";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return String(value);
      if (this._settingsSaved.interface_date_format === "iso") return date.toISOString();
      const locale = this._hass?.locale?.language || this._hass?.language || "pt-BR";
      if (this._settingsSaved.interface_date_format === "relative") {
        const seconds = Math.round((date.getTime() - Date.now()) / 1000);
        const [amount, unit] = Math.abs(seconds) < 60
          ? [seconds, "second"]
          : Math.abs(seconds) < 3600
            ? [Math.round(seconds / 60), "minute"]
            : Math.abs(seconds) < 86400
              ? [Math.round(seconds / 3600), "hour"]
              : [Math.round(seconds / 86400), "day"];
        return new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(amount, unit);
      }
      return new Intl.DateTimeFormat(locale, { dateStyle: "short", timeStyle: "medium" }).format(date);
    }

    async _handleAction(action, source) {
      try {
        if (action === "toggle-filters") {
          this._setFilterPanelOpen(this._nodes.filterPanel.hidden);
        } else if (action === "apply-filters") {
          await this._applyFilters({ closePanel: true });
        } else if (action === "clear-filters") {
          await this._clearFilters();
        } else if (action === "clear-search") {
          this._nodes.globalSearch.value = "";
          delete this._filterDraft.text;
          await this._applyFilters();
          this._nodes.globalSearch.focus();
        } else if (action === "add-filter-group") {
          this._addFilterGroup();
        } else if (action === "save-filter") {
          this._openSaveFilter();
        } else if (action === "close-save-filter") {
          this._nodes.savedFilterDialog.close();
        } else if (action === "confirm-save-filter") {
          await this._saveFilter();
        } else if (action === "rename-filter") {
          await this._renameCurrentSavedFilter();
        } else if (action === "delete-filter") {
          await this._deleteCurrentSavedFilter();
        } else if (action === "refresh-current") {
          await this._refreshCurrent();
        } else if (action === "load-new") {
          await this._loadPendingEvents();
        } else if (action === "open-beep") {
          this._openObservation("beep");
        } else if (action === "open-note") {
          this._openObservation("note");
        } else if (action === "close-observation") {
          this._nodes.observationDialog.close();
        } else if (action === "submit-observation") {
          await this._submitObservation();
        } else if (action === "close-detail") {
          this._nodes.eventDialog.close();
        } else if (action === "refresh-statistics") {
          await this._loadStatistics();
          this._renderStatistics();
        } else if (action === "save-settings") {
          await this._saveSettings();
        } else if (action === "cancel-settings") {
          this._cancelSettings();
        } else if (action === "reset-settings") {
          this._resetSettings();
        } else if (action === "run-cleanup") {
          await this._runCleanup();
        } else if (action === "clear-view") {
          this._clearCurrentView();
        } else if (action === "clear-filtered") {
          await this._clearEvents("filtered");
        } else if (action === "clear-old") {
          await this._clearEvents("old");
        } else if (action === "clear-all") {
          await this._clearEvents("all");
        } else if (action === "create-export" || action === "export-current") {
          if (action === "export-current") this._setActiveTab("export");
          else await this._createExport();
        }
      } catch (error) {
        this._showError(error);
      }
    }

    async _refreshCurrent() {
      if (this._activeTab === "overview") {
        await this._loadSnapshot();
      } else if (EVENT_TABS.has(this._activeTab)) {
        await this._loadEvents(this._activeTab, { reset: true });
      } else if (this._activeTab === "anomalies") {
        await this._loadAnomalies();
      } else if (this._activeTab === "statistics") {
        await this._loadStatistics();
        this._renderStatistics();
      } else if (this._activeTab === "settings") {
        if (this._settingsDirty) {
          this._setStatus("O rascunho de configuração foi preservado; cancele ou salve antes de recarregar.", "warning", 5000);
        } else {
          await this._loadSettings();
        }
      }
    }

    async _loadPendingEvents() {
      this._pendingEvents = 0;
      this._updatePendingBanner();
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
      if (EVENT_TABS.has(this._activeTab)) await this._loadEvents(this._activeTab, { reset: true });
      else await this._loadSnapshot();
    }

    _updatePendingBanner() {
      if (!this._nodes?.pendingBanner) return;
      this._nodes.pendingBanner.hidden = this._pendingEvents <= 0;
      this._nodes.pendingLabel.textContent = `${this._pendingEvents} novo${this._pendingEvents === 1 ? " evento" : "s eventos"}`;
    }

    _openObservation(type) {
      const form = this._nodes.observationForm;
      form.reset();
      form.elements.observation_type.value = type;
      const beep = type === "beep";
      this.shadowRoot.querySelector("#observation-title").textContent = beep ? "Registrar bip agora" : "Registrar observação";
      form.querySelectorAll(".beep-only").forEach((node) => { node.hidden = !beep; });
      form.querySelectorAll(".note-only").forEach((node) => { node.hidden = beep; });
      const local = new Date();
      local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
      form.elements.occurred_at.value = local.toISOString().slice(0, 19);
      this._openDialog(this._nodes.observationDialog);
      queueMicrotask(() => (beep ? form.elements.expected_count : form.elements.title)?.focus());
    }

    async _submitObservation() {
      const form = this._nodes.observationForm;
      if (!form.reportValidity()) return;
      const data = new FormData(form);
      const occurred = new Date(data.get("occurred_at"));
      const type = String(data.get("observation_type") || "note");
      const metadata = {};
      const title = String(data.get("title") || "").trim();
      const tags = String(data.get("tags") || "").split(",").map((item) => item.trim()).filter(Boolean);
      if (title) metadata.title = title;
      if (tags.length) metadata.tags = tags;
      const payload = {
        observation_type: type,
        occurred_at: Number.isNaN(occurred.getTime()) ? new Date().toISOString() : occurred.toISOString(),
        note: String(data.get("note") || "").trim() || undefined,
        metadata,
      };
      if (type === "beep") {
        const perceivedCount = String(data.get("expected_count") || "uncertain");
        if (perceivedCount === "1" || perceivedCount === "2") payload.expected_count = Number(perceivedCount);
        else {
          metadata.expected_count_label = perceivedCount === "many" ? "multiple" : "uncertain";
          metadata.beep_count = metadata.expected_count_label;
        }
      }
      await this._ws("register_observation", payload);
      this._nodes.observationDialog.close();
      this._setStatus(type === "beep" ? "Bip registrado para correlação." : "Observação registrada.", "success", 4000);
      this._pendingEvents += 1;
      this._updatePendingBanner();
      if (this._activeTab === "observations") await this._loadEvents("observations", { reset: true });
    }

    async _deleteObservation(id) {
      if (!id) return;
      const confirmed = await this._confirm("Excluir observação", "A observação será removida do diagnóstico. Eventos correlacionados não serão apagados.");
      if (!confirmed) return;
      const state = this._viewStates.get("observations");
      const observationEvent = state?.items.find((event) => String(getObservationId(event)) === String(id));
      const eventId = getEventId(observationEvent);
      const response = await this._ws("delete_observation", { observation_id: id });
      if (response?.success !== true) throw new Error("A observação não foi encontrada ou não pôde ser excluída.");
      this._deletedObservationIds.add(String(id));
      EVENT_TABS.forEach((tab) => {
        const tabState = this._viewStates.get(tab);
        if (!tabState) return;
        const previousLength = tabState.items.length;
        tabState.items = tabState.items.filter((event) => (
          String(getObservationId(event)) !== String(id)
          && (!eventId || String(getEventId(event)) !== String(eventId))
        ));
        if (tabState.items.length === previousLength) return;
        if (typeof tabState.total === "number") tabState.total = Math.max(0, tabState.total - 1);
        this._renderEventView(tab);
        this._updatePagination(tab);
      });
      this._setStatus("Observação excluída.", "success", 3000);
    }

    async _handleAnomalyAction(action, anomalyId) {
      if (!anomalyId) return;
      const promptLabel = action === "resolve" ? "Nota de resolução (opcional)" : "Nota de reconhecimento (opcional)";
      const note = window.prompt(promptLabel, "");
      if (note === null) return;
      await this._ws(action === "resolve" ? "resolve_anomaly" : "acknowledge_anomaly", {
        anomaly_id: anomalyId,
        note: note.trim() || undefined,
      });
      await this._loadAnomalies();
      this._setStatus(action === "resolve" ? "Anomalia resolvida." : "Anomalia reconhecida.", "success", 3500);
    }

    _readOneSetting(control) {
      const key = control.dataset.setting || control.dataset.settingList || control.dataset.settingCsv;
      if (!key) return;
      let value;
      if (control.dataset.settingList) {
        value = [...this._nodes.settingsForm.querySelectorAll(`[data-setting-list="${key}"]:checked`)].map((item) => item.value);
      } else if (control.dataset.settingCsv) {
        value = control.value.split(",").map((item) => item.trim()).filter(Boolean);
      } else if (control.type === "checkbox") value = control.checked;
      else if (control.type === "number") value = control.value === "" ? null : Number(control.value);
      else value = control.value;
      this._settingsDraft[key] = value;
      this._settingsDirty = JSON.stringify(this._settingsDraft) !== JSON.stringify(this._settingsSaved);
      this._updateSettingsDirtyState();
    }

    _renderSettings() {
      const form = this._nodes?.settingsForm;
      if (!form || this._settingsDirty) return;
      form.querySelectorAll("[data-setting],[data-setting-list],[data-setting-csv]").forEach((control) => {
        const key = control.dataset.setting || control.dataset.settingList || control.dataset.settingCsv;
        const value = this._settingsDraft[key];
        if (control.dataset.settingList) control.checked = asArray(value).includes(control.value);
        else if (control.dataset.settingCsv) control.value = asArray(value).join(", ");
        else if (control.type === "checkbox") control.checked = Boolean(value);
        else control.value = value ?? "";
      });
      this._updateSettingsDirtyState();
      this._renderMaintenance();
    }

    _applyInterfaceSettings() {
      this.dataset.density = this._settingsSaved.interface_density === "compact" ? "compact" : "comfortable";
      this.dataset.detailMode = this._settingsSaved.interface_detail_mode === "modal" ? "modal" : "panel";
      this.dataset.showTechnicalCodes = String(Boolean(this._settingsSaved.interface_show_technical_codes));
      if (!this._hass || !this._connected) return;
      if (this._settingsSaved.interface_auto_refresh === false && this._unsubscribe) {
        const unsubscribe = this._unsubscribe;
        this._unsubscribe = null;
        try {
          const result = unsubscribe();
          if (result && typeof result.catch === "function") result.catch(() => undefined);
        } catch (_error) { /* conexão já encerrada */ }
      } else if (this._settingsSaved.interface_auto_refresh !== false) {
        this._subscribe();
      }
    }

    _updateSettingsDirtyState() {
      if (!this._nodes?.settingsDirty) return;
      this._nodes.settingsDirty.hidden = !this._settingsDirty;
    }

    async _saveSettings() {
      if (!this._nodes.settingsForm.reportValidity()) return;
      this._nodes.settingsForm.querySelectorAll("[data-setting],[data-setting-list],[data-setting-csv]").forEach((control) => this._readOneSetting(control));
      const response = await this._ws("update_settings", { settings: clone(this._settingsDraft) });
      this._settingsSaved = { ...clone(DEFAULT_SETTINGS), ...canonicalSettings(response?.settings ?? this._settingsDraft) };
      this._settingsDraft = clone(this._settingsSaved);
      this._settingsDirty = false;
      this._applyInterfaceSettings();
      this._renderSettings();
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
      if (EVENT_TABS.has(this._activeTab)) await this._loadEvents(this._activeTab, { reset: true });
      this._setStatus("Configurações salvas na entrada da integração.", "success", 4000);
    }

    _cancelSettings() {
      this._settingsDraft = clone(this._settingsSaved);
      this._settingsDirty = false;
      this._applyInterfaceSettings();
      this._renderSettings();
      this._setStatus("Alterações de configuração descartadas.", "info", 3000);
    }

    _resetSettings() {
      this._settingsDraft = clone(DEFAULT_SETTINGS);
      this._settingsDirty = true;
      const form = this._nodes.settingsForm;
      form.querySelectorAll("[data-setting],[data-setting-list],[data-setting-csv]").forEach((control) => {
        const key = control.dataset.setting || control.dataset.settingList || control.dataset.settingCsv;
        const value = this._settingsDraft[key];
        if (control.dataset.settingList) control.checked = asArray(value).includes(control.value);
        else if (control.dataset.settingCsv) control.value = asArray(value).join(", ");
        else if (control.type === "checkbox") control.checked = Boolean(value);
        else control.value = value ?? "";
      });
      this._updateSettingsDirtyState();
    }

    _renderMaintenance() {
      const container = this.shadowRoot?.querySelector("#maintenance-summary");
      const retention = this.shadowRoot?.querySelector("#retention-summary");
      if (!container) return;
      const storage = asObject(this._snapshot.storage ?? this._snapshot.database);
      const counters = asObject(this._snapshot.counters);
      const rows = [
        ["Banco", storage.path ?? storage.filename ?? "SQLite próprio"],
        ["Schema", storage.schema_version ?? this._snapshot.schema_version],
        ["Tamanho", formatBytes(storage.size_bytes ?? counters.database_size_bytes)],
        ["Linhas", storage.total_events ?? counters.total_events],
        ["Eventos/dia", counters.events_per_day],
        ["Maior produtor", counters.top_producer ?? storage.top_producer],
        ["Compactados", counters.compacted ?? storage.compacted_events],
        ["Descartados", counters.dropped ?? storage.dropped_events],
        ["Última limpeza", this._formatDate(storage.last_cleanup)],
        ["Última migration", this._formatDate(storage.last_migration)],
        ["Saúde", storage.healthy ?? this._snapshot.status?.storage_health],
      ];
      container.replaceChildren(this._definitionFragment(rows));
      if (retention) retention.textContent = `Banco atual: ${formatBytes(storage.size_bytes ?? counters.database_size_bytes)} · ${storage.total_events ?? counters.total_events ?? 0} eventos · próxima limpeza: ${this._formatDate(storage.next_cleanup)}`;
    }

    async _runCleanup() {
      const confirmed = await this._confirm("Executar limpeza", "A integração aplicará as regras de retenção e compactação configuradas.", "LIMPAR");
      if (!confirmed) return;
      await this._ws("run_cleanup", { confirmation: "LIMPAR" });
      await this._loadSnapshot();
      this._setStatus("Limpeza concluída.", "success", 4000);
    }

    _clearCurrentView() {
      EVENT_TABS.forEach((tab) => {
        const state = this._newViewState();
        state.total = 0;
        this._viewStates.set(tab, state);
        this._renderEventView(tab);
        this._updatePagination(tab);
      });
      this._setStatus("A visualização local foi limpa; nenhum registro do banco foi excluído.", "info", 4500);
    }

    async _clearEvents(mode) {
      if (!this._hass?.user?.is_admin) throw new Error("Esta operação exige administrador.");
      const all = mode === "all";
      const old = mode === "old";
      let before;
      if (old) {
        const suggestion = new Date(Date.now() - (this._settingsSaved.retention_essential_days || 60) * 86400000).toISOString();
        const value = window.prompt("Excluir eventos anteriores a (data/hora ou ISO)", suggestion);
        if (value === null) return;
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) throw new Error("Data limite inválida.");
        before = parsed.toISOString();
      }
      const message = all
        ? "Todos os eventos do diagnóstico serão excluídos. Observações e anomalias podem ser preservadas conforme o backend."
        : old
          ? `Eventos anteriores a ${this._formatDate(before)} serão excluídos.`
        : "Os eventos correspondentes à consulta aplicada serão excluídos.";
      const title = all ? "Excluir todos os logs" : old ? "Excluir logs antigos" : "Excluir logs filtrados";
      const filteredQuery = !all && !old ? this._effectiveFilters("timeline") : null;
      if (filteredQuery && isEmptyObject(filteredQuery)) {
        throw new Error("Aplique ao menos um filtro antes de excluir logs filtrados.");
      }
      const confirmed = await this._confirm(title, message, "APAGAR");
      if (!confirmed) return;
      const payload = { confirmation: "APAGAR" };
      if (old) payload.before = before;
      else if (!all) payload.filters = filteredQuery;
      await this._ws("clear_events", payload);
      EVENT_TABS.forEach((tab) => this._viewStates.set(tab, this._newViewState()));
      await this._loadSnapshot();
      if (EVENT_TABS.has(this._activeTab)) await this._loadEvents(this._activeTab, { reset: true });
      this._setStatus("Exclusão concluída.", "success", 4000);
    }

    async _createExport() {
      const form = this.shadowRoot.querySelector("#export-form");
      if (!form.reportValidity()) return;
      const data = new FormData(form);
      const scope = String(data.get("scope") || "current_query");
      const selectedId = String(data.get("selected_id") || "").trim();
      const filters = { ...this._effectiveFilters("timeline") };
      if (scope === "selected_event") {
        const eventId = selectedId || this._detailEvent?.event_id;
        if (!eventId) throw new Error("Informe ou abra o evento que deseja exportar.");
        filters.advanced = this._appendAdvancedCondition(filters.advanced, { field: "event_id", operator: "eq", value: eventId });
      } else if (scope === "correlation") {
        const correlationId = selectedId || this._detailEvent?.correlation_id;
        if (!correlationId) throw new Error("Informe ou abra a correlação que deseja exportar.");
        filters.correlation_id = correlationId;
      } else if (scope === "evaluation") {
        const evaluationId = selectedId || this._detailEvent?.evaluation_id;
        if (!evaluationId) throw new Error("Informe ou abra a avaliação que deseja exportar.");
        filters.evaluation_id = evaluationId;
      } else if (scope === "anomaly") {
        const anomalyId = selectedId;
        const anomaly = this._anomalies.find((item) => String(item.anomaly_id || item.id) === anomalyId);
        if (!anomalyId) throw new Error("Informe o ID da anomalia que deseja exportar.");
        filters.is_anomaly = true;
        if (anomaly?.correlation_id) filters.correlation_id = anomaly.correlation_id;
        else if (anomaly?.event_id) filters.advanced = this._appendAdvancedCondition(filters.advanced, { field: "event_id", operator: "eq", value: anomaly.event_id });
        else if (anomaly?.anomaly_type) filters.advanced = this._appendAdvancedCondition(filters.advanced, { field: "anomaly_type", operator: "eq", value: anomaly.anomaly_type });
      }
      const response = await this._ws("create_export", {
        format: String(data.get("format") || "json"),
        filters,
        include_details: Boolean(data.get("include_details")),
      });
      const exported = asObject(response?.export ?? response);
      this._downloadExport(exported);
      this._setStatus(`Exportação criada: ${exported.filename || "arquivo"}.`, "success", 4000);
    }

    _downloadExport(response) {
      if (!response?.content_base64) throw new Error("O backend não retornou o conteúdo da exportação.");
      const binary = atob(response.content_base64);
      const bytes = new Uint8Array(binary.length);
      for (let index = 0; index < binary.length; index += 1) bytes[index] = binary.charCodeAt(index);
      const url = URL.createObjectURL(new Blob([bytes], { type: response.mime_type || "application/octet-stream" }));
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = response.filename || `elgin-diagnostico-${Date.now()}`;
      anchor.rel = "noopener";
      anchor.click();
      setTimeout(() => URL.revokeObjectURL(url), 5000);
    }

    _openDialog(dialog, modal = true) {
      if (!dialog) return;
      if (dialog.open) return;
      if (modal && typeof dialog.showModal === "function") dialog.showModal();
      else if (typeof dialog.show === "function") dialog.show();
      else dialog.setAttribute("open", "");
    }

    _confirm(title, message, confirmationCode = null) {
      const dialog = this._nodes.confirmDialog;
      this.shadowRoot.querySelector("#confirm-title").textContent = title;
      this.shadowRoot.querySelector("#confirm-message").textContent = message;
      const field = this.shadowRoot.querySelector("#confirm-code-field");
      const input = this.shadowRoot.querySelector("#confirm-code");
      field.hidden = !confirmationCode;
      field.querySelector("span").textContent = confirmationCode ? `Digite ${confirmationCode}` : "Confirmação";
      input.value = "";
      this._confirmationCode = confirmationCode;
      this._openDialog(dialog);
      return new Promise((resolve) => { this._confirmationResolver = resolve; });
    }

    _settleConfirmation(accepted) {
      if (accepted && this._confirmationCode && this.shadowRoot.querySelector("#confirm-code").value !== this._confirmationCode) {
        this._setStatus(`Digite ${this._confirmationCode} exatamente para confirmar.`, "warning", 3500);
        return;
      }
      this._nodes.confirmDialog.close();
      const resolve = this._confirmationResolver;
      this._confirmationResolver = null;
      this._confirmationCode = null;
      if (resolve) resolve(Boolean(accepted));
    }

    _updateAdminControls() {
      if (!this.shadowRoot || !this._hass) return;
      const admin = Boolean(this._hass.user?.is_admin);
      this.shadowRoot.querySelectorAll(".admin-only").forEach((node) => {
        node.hidden = !admin;
        node.disabled = !admin;
      });
    }

    _setStatus(message, type = "info", timeout = 0) {
      const banner = this._nodes?.banner;
      if (!banner) return;
      banner.hidden = false;
      banner.setAttribute("alert-type", type);
      banner.textContent = message;
      if (this._statusTimer) clearTimeout(this._statusTimer);
      if (timeout) this._statusTimer = setTimeout(() => this._clearStatus(), timeout);
    }

    _clearStatus() {
      if (!this._nodes?.banner) return;
      this._nodes.banner.hidden = true;
      this._nodes.banner.textContent = "";
    }

    _showError(error) {
      this._setStatus(error?.message || String(error), "error");
    }

    _styles() {
      return `
        :host{
          display:block;min-width:0;color:var(--primary-text-color);
          --diag-blue:var(--info-color,#1976d2);--diag-green:var(--success-color,#2e7d32);
          --diag-yellow:var(--warning-color,#f9a825);--diag-orange:#ef6c00;
          --diag-red:var(--error-color,#c62828);--diag-purple:#7b1fa2;
          --diag-cyan:#008fa8;--diag-gray:#607d8b;
        }
        :host([hidden]),[hidden]{display:none!important}*{box-sizing:border-box}
        .sr-only{position:absolute!important;width:1px!important;height:1px!important;padding:0!important;margin:-1px!important;overflow:hidden!important;clip:rect(0,0,0,0)!important;white-space:nowrap!important;border:0!important}
        .diagnostic-card{overflow:hidden;border-radius:20px;container-type:inline-size;background:var(--ha-card-background,var(--card-background-color))}
        button,input,select,textarea{font:inherit}button{border:0;border-radius:11px;padding:9px 13px;display:inline-flex;align-items:center;justify-content:center;gap:7px;background:var(--primary-color);color:var(--text-primary-color,#fff);cursor:pointer;min-height:40px}button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}button.accent{background:var(--diag-purple);color:#fff}button.danger{background:var(--diag-red);color:#fff}button:disabled{opacity:.45;cursor:not-allowed}.icon-button{width:40px;padding:0;flex:0 0 40px}.button-row{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
        button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible,summary:focus-visible,[tabindex]:focus-visible{outline:2px solid var(--primary-color);outline-offset:2px}
        .hero{display:flex;justify-content:space-between;gap:24px;padding:clamp(18px,2.3vw,30px);background:linear-gradient(135deg,color-mix(in srgb,var(--diag-blue) 18%,var(--card-background-color)),color-mix(in srgb,var(--diag-cyan) 10%,var(--card-background-color)))}.hero-title{min-width:0}.hero h1{font-size:clamp(1.55rem,3vw,2rem);margin:3px 0 7px}.hero p{margin:0;max-width:840px;color:var(--secondary-text-color);line-height:1.45}.hero-actions{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}.eyebrow{text-transform:uppercase;letter-spacing:.105em;font-weight:750;font-size:.7rem;color:var(--diag-cyan)}
        #status-banner{margin:12px 18px}.pending-banner{margin:12px 18px 0;padding:11px 13px;border-radius:13px;background:color-mix(in srgb,var(--diag-cyan) 12%,var(--secondary-background-color));border:1px solid color-mix(in srgb,var(--diag-cyan) 35%,var(--divider-color));display:flex;align-items:center;justify-content:space-between;gap:12px}.pending-banner>div{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.pending-banner span{color:var(--secondary-text-color);font-size:.84rem}.pending-banner ha-icon{color:var(--diag-cyan)}
        .tabs{display:flex;gap:4px;overflow:auto;padding:10px 14px;border-bottom:1px solid var(--divider-color);scrollbar-width:thin}.tab{background:transparent;color:var(--secondary-text-color);white-space:nowrap;border-radius:10px}.tab.active{background:color-mix(in srgb,var(--diag-cyan) 16%,var(--secondary-background-color));color:var(--primary-text-color);box-shadow:inset 0 -2px 0 var(--diag-cyan)}.tab ha-icon{--mdc-icon-size:20px}
        .query-toolbar{display:grid;grid-template-columns:minmax(280px,1fr) auto minmax(150px,220px) repeat(3,auto);gap:8px;align-items:center;padding:13px 18px 7px}.global-search{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;padding-left:11px;border:1px solid var(--divider-color);border-radius:12px;background:var(--secondary-background-color)}.global-search input{border:0;background:transparent;color:var(--primary-text-color);padding:10px 0;min-width:0;outline:0}.global-search .icon-button{min-height:36px;height:36px;width:36px;border-radius:9px;background:transparent;color:var(--secondary-text-color)}.saved-select select{width:100%}.count-badge{display:inline-flex;min-width:20px;height:20px;align-items:center;justify-content:center;border-radius:999px;background:color-mix(in srgb,var(--primary-color) 20%,transparent);font-size:.72rem}.quick-filters{display:flex;gap:6px;overflow:auto;padding:6px 18px 13px;scrollbar-width:thin}.quick-filter{min-height:32px;padding:6px 10px;border-radius:999px;background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color);white-space:nowrap;font-size:.78rem}.quick-filter ha-icon{--mdc-icon-size:17px}
        .filter-panel{margin:0 18px 16px;border:1px solid var(--divider-color);border-radius:16px;background:var(--secondary-background-color);overflow:visible}.filter-panel-head,.filter-footer{display:flex;justify-content:space-between;align-items:center;gap:16px;padding:14px}.filter-panel-head h2{margin:0}.filter-panel-head p{margin:4px 0 0;color:var(--secondary-text-color);font-size:.84rem}.filter-panel details{border-top:1px solid var(--divider-color);padding:0 14px 12px}.filter-panel details>summary,.settings-form details>summary{cursor:pointer;padding:13px 0;font-weight:700}.filter-grid,.settings-grid{display:grid;grid-template-columns:repeat(4,minmax(150px,1fr));gap:11px}.field{display:flex;flex-direction:column;gap:5px;min-width:0;font-size:.79rem;font-weight:650}.field>span,.inline-field{color:var(--secondary-text-color)}input,select,textarea{width:100%;border:1px solid var(--divider-color);border-radius:9px;padding:9px;background:var(--card-background-color);color:var(--primary-text-color);min-height:40px}textarea{resize:vertical}.toggle-field{display:flex;align-items:flex-start;gap:8px;padding:9px;border-radius:10px;background:var(--secondary-background-color);font-size:.82rem}.toggle-field input{width:auto;min-height:0;margin-top:2px}.change-grid .toggle-field{align-self:end}.filter-footer{border-top:1px solid var(--divider-color);position:sticky;bottom:0;background:var(--secondary-background-color);z-index:4}.filter-footer>span{color:var(--secondary-text-color);font-size:.82rem}
        .advanced-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.advanced-head p{color:var(--secondary-text-color)}.advanced-builder{display:grid;gap:10px}.filter-group{border:1px solid var(--divider-color);border-radius:13px;padding:11px;background:var(--card-background-color)}.filter-group>header{display:flex;justify-content:space-between;align-items:end;gap:10px}.filter-group>header label{font-size:.77rem;color:var(--secondary-text-color)}.conditions{display:grid;gap:8px;margin-top:10px}.condition-row{display:grid;grid-template-columns:minmax(140px,1.2fr) minmax(125px,.8fr) minmax(150px,1fr) auto;gap:8px;align-items:end}.condition-row label{display:grid;gap:4px;font-size:.75rem;color:var(--secondary-text-color)}
        main{padding:18px}.tab-panel{min-height:360px}.panel-head,.section-title{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;margin-bottom:14px}.panel-head h2,.section-title h2{margin:3px 0}.panel-head p{margin:4px 0 0;color:var(--secondary-text-color);max-width:860px}.view-meta{display:flex;gap:10px;color:var(--secondary-text-color);font-size:.8rem}.loading-indicator{display:inline-flex;align-items:center;gap:4px}.loading-indicator ha-icon{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
        .metrics{display:grid;grid-template-columns:repeat(7,minmax(125px,1fr));gap:9px;margin-bottom:14px}.metric{display:flex;align-items:center;gap:9px;padding:11px;border-radius:13px;background:var(--secondary-background-color);min-width:0;border-left:3px solid var(--diag-blue)}.metric ha-icon{color:var(--diag-blue)}.metric>div{min-width:0}.metric span{display:block;color:var(--secondary-text-color);font-size:.69rem}.metric strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;font-size:.88rem;margin-top:2px}.metric.success{border-color:var(--diag-green)}.metric.success ha-icon{color:var(--diag-green)}.metric.error{border-color:var(--diag-red)}.metric.error ha-icon{color:var(--diag-red)}.metric.orange{border-color:var(--diag-orange)}.metric.orange ha-icon{color:var(--diag-orange)}.metric.purple{border-color:var(--diag-purple)}.metric.purple ha-icon{color:var(--diag-purple)}.metric.cyan{border-color:var(--diag-cyan)}.metric.cyan ha-icon{color:var(--diag-cyan)}
        .overview-layout{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(270px,.8fr);gap:14px;margin-bottom:14px;align-items:start}.surface{padding:16px;border:1px solid var(--divider-color);border-radius:15px;background:var(--secondary-background-color);min-width:0}.flow-surface{min-width:0}.section-title>ha-icon{color:var(--diag-cyan);--mdc-icon-size:30px}.section-subtitle{margin:5px 0 0;color:var(--secondary-text-color);font-size:.78rem;line-height:1.4}.flow{display:grid;grid-template-columns:repeat(5,minmax(150px,1fr));gap:7px;overflow:auto;padding:5px 0;scrollbar-width:thin}.flow-step{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:center;gap:8px;min-width:0;min-height:82px;max-height:104px;overflow:hidden;padding:10px;border-radius:12px;background:var(--card-background-color);border:1px solid var(--divider-color)}.flow-step>ha-icon{color:var(--secondary-text-color);flex:0 0 auto}.flow-step div{min-width:0;overflow:hidden}.flow-step strong,.flow-step small{display:-webkit-box;-webkit-box-orient:vertical;overflow:hidden;overflow-wrap:anywhere}.flow-step strong{-webkit-line-clamp:2;line-clamp:2}.flow-step small{-webkit-line-clamp:2;line-clamp:2;color:var(--secondary-text-color);margin-top:3px;font-size:.73rem;line-height:1.35}.flow-index{display:flex;align-items:center;justify-content:center;width:25px;height:25px;border-radius:50%;background:var(--diag-blue);color:#fff;font-weight:700;flex:0 0 25px}.flow-step.confirmed .flow-index,.flow-step.success .flow-index{background:var(--diag-green)}.flow-step.blocked .flow-index{background:var(--diag-yellow)}.definition-list,.detail-section dl,.action-card dl,.external-card dl,.anomaly-card dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 12px;margin:0}.definition-list dt,.detail-section dt,.action-card dt,.external-card dt,.anomaly-card dt{font-size:.75rem;color:var(--secondary-text-color)}.definition-list dd,.detail-section dd,.action-card dd,.external-card dd,.anomaly-card dd{margin:0;overflow-wrap:anywhere;line-height:1.4}.compact-events{display:grid;gap:5px}.compact-event{display:grid;grid-template-columns:auto auto minmax(180px,1fr) minmax(100px,.5fr) auto;align-items:center;text-align:left;gap:9px;background:var(--card-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}.compact-event time,.compact-event small{font-size:.74rem;color:var(--secondary-text-color)}.severity-dot{width:8px;height:8px;border-radius:50%;background:var(--diag-blue)}.severity-dot.warning{background:var(--diag-yellow)}.severity-dot.error,.severity-dot.critical{background:var(--diag-red)}.severity-dot.success{background:var(--diag-green)}
        .table-wrap{overflow:auto;border:1px solid var(--divider-color);border-radius:14px}.event-table,.comparison-table{border-collapse:collapse;width:100%}.event-table{min-width:1450px}.event-table thead,.comparison-table thead{position:sticky;top:0;z-index:2;background:var(--card-background-color)}.event-table th,.event-table td,.comparison-table th,.comparison-table td{padding:10px;border-bottom:1px solid var(--divider-color);text-align:left;vertical-align:top;font-size:.78rem}.event-table tbody tr{cursor:pointer}.event-table tbody tr:hover{background:color-mix(in srgb,var(--diag-cyan) 7%,transparent)}.event-table tr.anomaly{box-shadow:inset 4px 0 0 var(--diag-red)}.event-table tr.external{background:color-mix(in srgb,var(--diag-cyan) 4%,transparent)}.event-table strong,.event-table small{display:block}.event-table small{margin-top:3px;color:var(--secondary-text-color)}code{font-family:var(--code-font-family,monospace);font-size:.76rem;overflow-wrap:anywhere;color:var(--primary-text-color)}
        :host([data-density="compact"]) .event-table th,:host([data-density="compact"]) .event-table td{padding:6px 8px;font-size:.73rem}:host([data-density="compact"]) .decision-card,:host([data-density="compact"]) .action-card,:host([data-density="compact"]) .state-change-card,:host([data-density="compact"]) .external-card,:host([data-density="compact"]) .observation-card{padding:10px!important}
        .chip-row{display:flex;gap:5px;flex-wrap:wrap}.chip{display:inline-flex;align-items:center;border-radius:999px;padding:3px 7px;font-size:.68rem;background:var(--secondary-background-color);border:1px solid var(--divider-color);white-space:nowrap}.chip.severity.value-warning{color:var(--diag-yellow);border-color:var(--diag-yellow)}.chip.severity.value-error,.chip.severity.value-critical{color:var(--diag-red);border-color:var(--diag-red)}.chip.severity.value-success{color:var(--diag-green);border-color:var(--diag-green)}.chip.audibility.value-audible_expected{color:var(--diag-orange);border-color:var(--diag-orange)}.chip.audibility.value-silent_expected,.chip.origin{color:var(--diag-cyan);border-color:color-mix(in srgb,var(--diag-cyan) 60%,var(--divider-color))}.chip.outcome.value-confirmed,.chip.outcome.value-success,.chip.outcome.value-resolved{color:var(--diag-green);border-color:var(--diag-green)}.chip.outcome.value-blocked,.chip.outcome.value-suppressed,.chip.outcome.value-acknowledged{color:var(--diag-yellow);border-color:var(--diag-yellow)}.chip.outcome.value-failed,.chip.outcome.value-error{color:var(--diag-red);border-color:var(--diag-red)}.chip.category,.chip.field{color:var(--diag-purple);border-color:color-mix(in srgb,var(--diag-purple) 55%,var(--divider-color))}
        .pagination{display:flex;justify-content:center;align-items:end;gap:7px;flex-wrap:wrap;margin:14px 0}.pagination label{display:grid;gap:3px;color:var(--secondary-text-color);font-size:.7rem}.pagination input{min-height:40px}.empty-state{min-height:180px;display:flex;align-items:center;justify-content:center;flex-direction:column;gap:9px;color:var(--secondary-text-color);padding:28px;text-align:center}.empty-state ha-icon{--mdc-icon-size:34px}
        .decision-grid,.action-grid,.anomaly-grid,.statistics-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.decision-card,.action-card,.state-change-card,.external-card,.anomaly-card,.observation-card,.stat-card{border:1px solid var(--divider-color);border-radius:15px;padding:14px;background:var(--secondary-background-color);min-width:0}.decision-card>header,.action-card>header,.state-change-card>header,.anomaly-card>header,.observation-card header{display:flex;align-items:flex-start;justify-content:space-between;gap:10px}.decision-card h3,.action-card h3,.state-change-card h3,.external-card h3,.anomaly-card h3,.observation-card h3{margin:4px 0}.decision-card time,.action-card time,.state-change-card time,.external-card time,.anomaly-card time,.observation-card time{color:var(--secondary-text-color);font-size:.73rem}.decision-columns{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:12px 0}.decision-columns section{padding:10px;border-radius:11px;background:var(--card-background-color)}.decision-columns dl{display:grid;grid-template-columns:auto minmax(0,1fr);gap:5px 9px;margin:8px 0 0}.decision-columns dt{font-size:.71rem;color:var(--secondary-text-color)}.decision-columns dd{margin:0;overflow-wrap:anywhere}.section-label{font-size:.66rem;font-weight:800;letter-spacing:.08em;color:var(--diag-purple)}.decision-card footer,.action-card footer,.state-change-card footer,.anomaly-card footer{display:flex;justify-content:flex-end;align-items:center;gap:7px;flex-wrap:wrap;margin-top:12px}
        .state-change-list,.external-list,.observation-list{display:grid;gap:10px}.state-change-card>header code{display:block;margin-top:4px}.before-after{display:grid;grid-template-columns:minmax(0,1fr) auto minmax(0,1fr);gap:10px;align-items:center;margin:12px 0}.before-after section{padding:10px;border-radius:11px;background:var(--card-background-color);min-width:0}.before-after section span,.before-after section strong{display:block}.before-after section span{font-size:.66rem;font-weight:800;color:var(--secondary-text-color)}.before-after section strong{margin-top:4px;overflow-wrap:anywhere}.before-after>ha-icon{color:var(--diag-cyan)}.state-change-card footer{justify-content:space-between;color:var(--secondary-text-color);font-size:.78rem}
        .action-card{border-top:4px solid var(--diag-orange)}.action-card>p{color:var(--secondary-text-color)}.layer-note,.notice,.lifecycle-note,.relation-explanation,.setting-info{padding:10px;border-radius:10px;background:color-mix(in srgb,var(--diag-yellow) 10%,var(--card-background-color));color:var(--secondary-text-color);font-size:.8rem}.external-card{display:grid;grid-template-columns:auto minmax(0,1fr) auto;align-items:start;gap:12px;border-left:4px solid var(--diag-cyan)}.external-icon{width:42px;height:42px;display:flex;align-items:center;justify-content:center;border-radius:50%;background:color-mix(in srgb,var(--diag-cyan) 15%,var(--card-background-color));color:var(--diag-cyan)}.external-main header{display:flex;gap:8px;align-items:center}.before-after.compact{grid-template-columns:repeat(2,minmax(0,1fr))}.anomaly-card{border-left:4px solid var(--diag-yellow)}.anomaly-card.severity-error,.anomaly-card.severity-critical{border-left-color:var(--diag-red)}.anomaly-count{font-size:1.15rem;font-weight:800;color:var(--secondary-text-color)}.observation-card{display:grid;grid-template-columns:auto minmax(0,1fr) auto;gap:12px;align-items:start;border-left:4px solid var(--diag-purple)}.observation-card>ha-icon{color:var(--diag-purple);--mdc-icon-size:30px}.observation-card p{color:var(--secondary-text-color)}.observation-actions{display:grid;gap:6px}
        .statistics-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.stat-summary{grid-column:1/-1}.stat-card h3{margin-top:0}.stat-summary-grid{display:grid;grid-template-columns:repeat(7,minmax(100px,1fr));gap:8px}.stat-summary-grid>div{padding:9px;border-radius:10px;background:var(--card-background-color)}.stat-summary-grid span,.stat-summary-grid strong{display:block}.stat-summary-grid span{font-size:.7rem;color:var(--secondary-text-color)}.stat-summary-grid strong{font-size:1.2rem;margin-top:3px}.bars{display:grid;gap:7px}.bar-row{display:grid;grid-template-columns:minmax(90px,1fr) minmax(80px,2fr) auto;gap:7px;align-items:center;font-size:.75rem}.bar-row>span{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.bar-row>div{height:8px;border-radius:999px;background:var(--card-background-color);overflow:hidden}.bar-row i{display:block;height:100%;border-radius:inherit;background:linear-gradient(90deg,var(--diag-blue),var(--diag-cyan))}.empty-small{padding:14px;color:var(--secondary-text-color);text-align:center}
        .settings-head{position:sticky;top:0;background:var(--card-background-color);z-index:6;padding:6px 0}.dirty-chip{padding:5px 9px;border-radius:999px;background:color-mix(in srgb,var(--diag-yellow) 18%,var(--secondary-background-color));color:var(--diag-yellow);font-size:.76rem}.settings-form details{border:1px solid var(--divider-color);border-radius:14px;padding:0 14px 14px;margin-bottom:10px;background:var(--secondary-background-color)}.toggle-grid{display:grid;grid-template-columns:repeat(3,minmax(170px,1fr));gap:8px}.full{grid-column:1/-1}.maintenance-grid{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 14px;margin-bottom:12px}.maintenance-grid dt{color:var(--secondary-text-color);font-size:.75rem}.maintenance-grid dd{margin:0;overflow-wrap:anywhere}.maintenance-actions{margin-top:10px}.sticky-form-actions{display:flex;justify-content:flex-end;gap:8px;position:sticky;bottom:0;padding:12px;background:color-mix(in srgb,var(--card-background-color) 94%,transparent);border-top:1px solid var(--divider-color);z-index:5}
        .export-layout{display:grid;grid-template-columns:minmax(280px,1fr) minmax(250px,.7fr);gap:14px}.export-form{display:grid;gap:12px}.privacy-note{display:flex;gap:12px;align-items:flex-start}.privacy-note>ha-icon{color:var(--diag-green);--mdc-icon-size:36px}.privacy-note h3{margin:0}.privacy-note p{color:var(--secondary-text-color);line-height:1.5}
        dialog{border:0;border-radius:18px;background:var(--card-background-color);color:var(--primary-text-color);padding:0;box-shadow:0 22px 90px rgba(0,0,0,.48);max-height:94vh;max-width:calc(100vw - 20px)}dialog::backdrop{background:rgba(0,0,0,.58)}dialog:not(.wide-dialog){width:min(560px,calc(100vw - 20px))}.wide-dialog{width:min(1220px,calc(100vw - 20px))}.dialog-shell{padding:18px;display:grid;gap:13px;min-width:0}.dialog-shell>header,.dialog-shell>footer{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.dialog-shell>header{position:sticky;top:-18px;background:var(--card-background-color);z-index:6;padding:2px 0 10px;border-bottom:1px solid var(--divider-color)}.dialog-shell>header>div{min-width:0}.dialog-shell>header .icon-button{flex:0 0 40px}.dialog-shell h2{margin:3px 0;overflow-wrap:anywhere}.dialog-shell>footer{justify-content:flex-end}#event-dialog{overflow:hidden}#event-dialog .dialog-shell{height:min(90vh,900px);display:flex;flex-direction:column;overflow:hidden}#event-dialog .dialog-shell>header{position:relative;top:auto;flex:0 0 auto}#event-dialog #detail-loading{flex:1 1 auto;min-height:0}#event-dialog #detail-content{flex:1 1 auto;min-height:0;overflow:auto;overscroll-behavior:contain;padding-right:2px}.detail-tabs{display:flex;flex:0 0 auto;align-items:center;gap:5px;overflow:auto;border-bottom:1px solid var(--divider-color);padding-bottom:7px}.detail-tabs button{flex:0 0 auto;align-self:center;background:transparent;color:var(--secondary-text-color);white-space:nowrap}.detail-tabs button.active{background:color-mix(in srgb,var(--diag-cyan) 15%,var(--secondary-background-color));color:var(--primary-text-color)}.detail-panels{min-width:0}.detail-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:10px}.detail-section{border:1px solid var(--divider-color);border-radius:12px;padding:12px;min-width:0}.detail-section h3{margin:0 0 9px}.comparison-table{min-width:0;table-layout:fixed}.comparison-table th:first-child{width:18%}.comparison-table th:nth-child(2),.comparison-table th:nth-child(3){width:33%}.comparison-table th:last-child{width:16%}.comparison-table tr.changed{box-shadow:inset 3px 0 0 var(--diag-cyan)}.comparison-table tr.unchanged{color:var(--secondary-text-color)}.comparison-wrap{margin:10px 0;overflow-x:hidden}.comparison-value{display:block;max-width:100%;white-space:pre-wrap;overflow-wrap:anywhere;word-break:break-word;line-height:1.4}.json-columns{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:9px}.json-columns h4{margin:0 0 5px}.technical-sections details{border-bottom:1px solid var(--divider-color)}.technical-sections summary,details>summary{cursor:pointer;font-weight:700;padding:10px 0}.detail-empty{margin:0 0 10px;padding:11px;border-radius:10px;background:var(--secondary-background-color);color:var(--secondary-text-color);line-height:1.45}pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:430px;overflow:auto;padding:11px;border-radius:10px;background:var(--code-editor-background-color,var(--secondary-background-color));font-size:.76rem}.related-events{display:grid;gap:6px;margin-top:10px}.related-event{display:grid;grid-template-columns:auto minmax(160px,1fr) auto;text-align:left}.related-event time,.related-event span{font-size:.73rem;color:var(--secondary-text-color)}
        :host([data-detail-mode="panel"]) #event-dialog{position:fixed;inset:0 0 0 auto;margin:0;width:min(920px,100vw);height:100dvh;max-height:none;max-width:100vw;border-radius:18px 0 0 18px;overflow:hidden}:host([data-detail-mode="panel"]) #event-dialog::backdrop{background:rgba(0,0,0,.22)}:host([data-detail-mode="panel"]) #event-dialog .dialog-shell{height:100%;min-height:0}
        @container(max-width:1180px){.metrics{grid-template-columns:repeat(4,minmax(125px,1fr))}.filter-grid,.settings-grid{grid-template-columns:repeat(3,minmax(150px,1fr))}.statistics-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.stat-summary-grid{grid-template-columns:repeat(4,1fr)}}
        @container(max-width:820px){.hero{display:block}.hero-actions{margin-top:14px}.query-toolbar{grid-template-columns:minmax(0,1fr) auto}.saved-select,.query-toolbar>.icon-button{display:none}.filter-grid,.settings-grid{grid-template-columns:repeat(2,minmax(140px,1fr))}.metrics{grid-template-columns:repeat(3,minmax(110px,1fr))}.overview-layout,.export-layout{grid-template-columns:1fr}.decision-grid,.action-grid,.anomaly-grid,.statistics-grid{grid-template-columns:1fr}.stat-summary-grid{grid-template-columns:repeat(3,1fr)}.external-card{grid-template-columns:auto minmax(0,1fr)}.external-card>button{grid-column:2}.observation-card{grid-template-columns:auto minmax(0,1fr)}.observation-actions{grid-column:2;display:flex}.toggle-grid{grid-template-columns:repeat(2,minmax(150px,1fr))}.json-columns{grid-template-columns:1fr}.detail-grid{grid-template-columns:1fr}}
        @container(max-width:560px){main{padding:10px}.hero{padding:16px}.tabs{padding:8px}.tab span{display:none}.tab{padding:8px}.query-toolbar{padding:10px;grid-template-columns:1fr}.query-toolbar>button{width:100%}.quick-filters{padding:4px 10px 10px}.filter-panel{margin:0 10px 12px}.filter-panel-head,.filter-footer{display:block}.filter-panel-head .button-row,.filter-footer .button-row{margin-top:10px}.filter-grid,.settings-grid,.toggle-grid{grid-template-columns:1fr}.condition-row{grid-template-columns:1fr auto}.condition-row label{grid-column:1}.condition-row button{grid-column:2;grid-row:1}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.metric{padding:9px}.flow{grid-template-columns:repeat(5,minmax(180px,1fr))}.flow-step{min-width:180px}.compact-event{grid-template-columns:auto auto minmax(140px,1fr) auto}.compact-event small{display:none}.decision-columns{grid-template-columns:1fr}.before-after{grid-template-columns:1fr}.before-after>ha-icon{transform:rotate(90deg);justify-self:center}.external-card,.observation-card{grid-template-columns:1fr}.external-icon{display:none}.external-card>button,.observation-actions{grid-column:1}.stat-summary-grid{grid-template-columns:repeat(2,1fr)}.pagination{display:grid;grid-template-columns:1fr 1fr}.pagination label{grid-column:1/-1}.panel-head{display:block}.panel-head>.button-row,.view-meta{margin-top:10px}.detail-tabs button{font-size:.75rem;padding:8px}.dialog-shell{padding:13px}.comparison-wrap{overflow-x:auto}.comparison-table{min-width:620px}.related-event{grid-template-columns:1fr}.sticky-form-actions{flex-wrap:wrap}.sticky-form-actions button{flex:1}.hero-actions button{width:100%}}
        @media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important;animation-duration:.01ms!important;transition-duration:.01ms!important}}
      `;
    }
  }

  if (!customElements.get(CARD_TAG)) customElements.define(CARD_TAG, ElginSupervisorDiagnosticoCard);
  window.customCards = Array.isArray(window.customCards) ? window.customCards : [];
  if (!window.customCards.some((card) => card.type === CARD_TAG)) {
    window.customCards.push({
      type: CARD_TAG,
      name: "Elgin Supervisor — Diagnóstico",
      description: "Observabilidade completa: timeline, decisões, estados, transmissões, alterações externas, anomalias e exportação.",
      preview: false,
    });
  }
  console.info(`[Elgin Supervisor Diagnóstico] card registrado (${BUILD})`);
})();
