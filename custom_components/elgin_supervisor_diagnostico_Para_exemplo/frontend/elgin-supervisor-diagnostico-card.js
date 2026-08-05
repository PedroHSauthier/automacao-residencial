(() => {
  "use strict";

  const DOMAIN = "elgin_supervisor_diagnostico";
  const BUILD = "diagnostico-20260731.2";
  const TABS = [
    ["timeline", "Linha do tempo", "mdi:timeline-clock-outline"],
    ["transmissions", "Transmissões", "mdi:remote"],
    ["anomalies", "Anomalias", "mdi:alert-decagram"],
    ["beeps", "Observações de bip", "mdi:volume-high"],
    ["stats", "Estatísticas", "mdi:chart-box-outline"],
    ["settings", "Configurações", "mdi:cog-outline"],
    ["export", "Exportação", "mdi:file-export-outline"],
  ];
  const SEVERITY_LABEL = {
    debug: "Debug", info: "Informação", success: "Concluído",
    warning: "Atenção", error: "Erro", critical: "Crítico",
  };
  const OUTCOME_LABEL = {
    started: "Iniciado", calculated: "Calculado", unchanged: "Sem mudança",
    requested: "Solicitado", accepted: "Aceito", transmitted_by_software: "Transmissor chamado",
    confirmed: "Confirmado", suppressed: "Suprimido", blocked: "Bloqueado",
    rejected: "Rejeitado", failed: "Falhou", external: "Externo", unknown: "Desconhecido",
  };
  const AUDIBILITY_LABEL = {
    audible_expected: "Audível esperado", silent_expected: "Silencioso esperado",
    no_transmission: "Sem transmissão", unknown: "Desconhecida",
  };
  const RETENTION_LABEL = { absolute: "Absoluto", error: "Erros", full: "Completo" };

  const esc = (value) => String(value ?? "").replace(/[&<>'"]/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
  })[char]);
  const fmt = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString("pt-BR");
  };
  const bytes = (value) => {
    const n = Number(value || 0);
    if (n < 1024) return `${n} B`;
    if (n < 1024 ** 2) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / 1024 ** 2).toFixed(2)} MB`;
  };
  const pretty = (value) => JSON.stringify(value ?? null, null, 2);
  const bool = (value) => value ? "Sim" : "Não";
  const icon = (name) => `<ha-icon icon="${esc(name)}"></ha-icon>`;

  class ElginSupervisorDiagnosticoCard extends HTMLElement {
    setConfig(config) {
      this.config = config || {};
      this.entryId = this.config.entry_id || null;
      this.activeTab = this.activeTab || "timeline";
      this.snapshot = null;
      this.events = [];
      this.anomalies = [];
      this.nextCursor = null;
      this.filters = {};
      this.loading = false;
      this.error = "";
      this.expanded = null;
      this._loaded = false;
      this._subscribed = false;
      this._build = BUILD;
      this.render();
    }

    set hass(hass) {
      this._hass = hass;
      if (!this._loaded) this.loadAll();
      this.subscribe();
    }

    getCardSize() { return 12; }
    getGridOptions() { return { columns: 12, min_columns: 6, rows: 10, min_rows: 6 }; }

    async subscribe() {
      if (!this._hass || this._subscribed) return;
      this._subscribed = true;
      try {
        this._unsubscribe = await this._hass.connection.subscribeEvents(
          () => this.scheduleRefresh(), `${DOMAIN}_updated`,
        );
      } catch (_err) {
        this._subscribed = false;
      }
    }

    disconnectedCallback() {
      if (this._unsubscribe) {
        try { this._unsubscribe(); } catch (_err) { /* closed */ }
      }
      this._unsubscribe = null;
      this._subscribed = false;
      if (this._refreshTimer) clearTimeout(this._refreshTimer);
    }

    scheduleRefresh() {
      if (this._refreshTimer) clearTimeout(this._refreshTimer);
      this._refreshTimer = setTimeout(() => {
        this._refreshTimer = null;
        this.loadSnapshot();
        if (["timeline", "transmissions", "beeps"].includes(this.activeTab)) this.loadEvents(true);
        if (this.activeTab === "anomalies") this.loadAnomalies();
      }, 250);
    }

    async ws(type, payload = {}) {
      const message = { type: `${DOMAIN}/${type}`, ...payload };
      if (this.entryId) message.entry_id = this.entryId;
      return this._hass.callWS(message);
    }

    async loadAll() {
      if (!this._hass || this.loading) return;
      this._loaded = true;
      this.loading = true;
      this.error = "";
      this.render();
      try {
        await Promise.all([this.loadSnapshot(false), this.loadEvents(true, false), this.loadAnomalies(false)]);
      } catch (error) {
        this.error = error.message || String(error);
      } finally {
        this.loading = false;
        this.render();
      }
    }

    async loadSnapshot(render = true) {
      try {
        this.snapshot = await this.ws("get_snapshot");
        this.entryId = this.snapshot.entry_id || this.entryId;
      } catch (error) {
        this.error = error.message || String(error);
      }
      if (render) this.render();
    }

    currentFilters() {
      const filters = { ...this.filters };
      if (this.activeTab === "timeline" && !filters.category) {
        const visible = this.snapshot?.settings?.visible_categories || [];
        if (visible.length) filters.category = visible;
      }
      if (this.activeTab === "transmissions") filters.category = ["ir", "action"];
      if (this.activeTab === "beeps") filters.event_type = ["user.beep_observed", "user.note"];
      return filters;
    }

    async loadEvents(reset = true, render = true) {
      if (!this._hass) return;
      try {
        const result = await this.ws("list_events", {
          filters: this.currentFilters(),
          cursor: reset ? undefined : this.nextCursor,
          limit: Number(this.snapshot?.settings?.default_page_size || 50),
          include_details: false,
        });
        this.events = reset ? result.events : [...this.events, ...result.events];
        this.nextCursor = result.next_cursor;
      } catch (error) {
        this.error = error.message || String(error);
      }
      if (render) this.render();
    }

    async loadAnomalies(render = true) {
      try {
        const result = await this.ws("list_anomalies", { status: "active" });
        this.anomalies = result.anomalies || [];
      } catch (error) {
        this.error = error.message || String(error);
      }
      if (render) this.render();
    }

    async openEvent(eventId) {
      this.expanded = { loading: true, event_id: eventId };
      this.render();
      try {
        const event = await this.ws("get_event", { event_id: eventId });
        let related = [];
        if (event.correlation_id) {
          related = (await this.ws("get_correlation", { correlation_id: event.correlation_id })).events || [];
        }
        this.expanded = { ...event, related };
      } catch (error) {
        this.expanded = { error: error.message || String(error) };
      }
      this.render();
      const dialog = this.querySelector("dialog.event-dialog");
      if (dialog && !dialog.open) dialog.showModal();
    }

    severityChip(event) {
      return `<span class="chip severity ${esc(event.severity)}">${esc(SEVERITY_LABEL[event.severity] || event.severity)}</span>`;
    }

    actorChip(event) {
      return `<span class="chip actor">${icon(event.is_external ? "mdi:account-question" : "mdi:account-cog")} ${esc(event.actor_name || "Desconhecido")}</span>`;
    }

    audibilityChip(event) {
      const value = event.expected_audibility || "unknown";
      return `<span class="chip audibility ${esc(value)}">${esc(AUDIBILITY_LABEL[value] || value)}</span>`;
    }

    render() {
      if (!this.shadowRoot) this.attachShadow({ mode: "open" });
      const snapshot = this.snapshot || {};
      const storage = snapshot.storage || {};
      const health = snapshot.health || {};
      this.shadowRoot.innerHTML = `
        <style>${this.styles()}</style>
        <ha-card>
          <section class="hero">
            <div class="hero-main">
              <div class="eyebrow">Elgin Supervisor</div>
              <h1>Auditoria e Logs</h1>
              <p>Correlação temporal, origem, decisões, transmissões e evidências do sistema local.</p>
            </div>
            <div class="hero-actions">
              <button class="beep" data-action="beep">${icon("mdi:volume-high")} Registrar bip agora</button>
              <button class="secondary" data-action="refresh">${icon("mdi:refresh")} Atualizar</button>
            </div>
          </section>
          ${this.error ? `<div class="banner error">${icon("mdi:alert-circle")} ${esc(this.error)}</div>` : ""}
          <section class="metrics">
            ${this.metric("Saúde geral", health.persistence_healthy ? "Saudável" : "Degradada", health.persistence_healthy ? "success" : "error", "mdi:heart-pulse")}
            ${this.metric("Modo", health.intensive_mode ? "Intensivo" : "Normal", health.intensive_mode ? "warning" : "info", "mdi:timeline-plus")}
            ${this.metric("Eventos", storage.total_events ?? 0, "info", "mdi:counter")}
            ${this.metric("Anomalias ativas", storage.active_anomalies ?? 0, storage.active_anomalies ? "error" : "success", "mdi:alert-decagram")}
            ${this.metric("Última transmissão", snapshot.last_transmission?.frame_kind || "Nenhuma", "transmission", "mdi:remote")}
            ${this.metric("Banco", bytes((storage.database_size_bytes || 0) + (storage.wal_size_bytes || 0)), "database", "mdi:database")}
          </section>
          <nav class="tabs">
            ${TABS.map(([id, label, iconName]) => `<button class="tab ${this.activeTab === id ? "active" : ""}" data-tab="${id}">${icon(iconName)}<span>${label}</span></button>`).join("")}
          </nav>
          <section class="content">
            ${this.loading && !this.snapshot ? `<div class="loading">${icon("mdi:loading")} Carregando auditoria…</div>` : this.renderTab()}
          </section>
          ${this.renderBeepDialog()}
          ${this.renderEventDialog()}
        </ha-card>
      `;
      this.bind();
    }

    metric(label, value, tone, iconName) {
      return `<article class="metric ${tone}">${icon(iconName)}<div><span>${esc(label)}</span><strong>${esc(value)}</strong></div></article>`;
    }

    renderTab() {
      switch (this.activeTab) {
        case "timeline": return this.renderTimeline();
        case "transmissions": return this.renderTransmissions();
        case "anomalies": return this.renderAnomalies();
        case "beeps": return this.renderBeeps();
        case "stats": return this.renderStats();
        case "settings": return this.renderSettings();
        case "export": return this.renderExport();
        default: return "";
      }
    }

    renderFilters() {
      return `<details class="filters">
        <summary>${icon("mdi:filter-variant")} Filtros</summary>
        <div class="filter-grid">
          <label>Busca<input data-filter="text" value="${esc(this.filters.text || "")}" placeholder="Resumo, ator ou mensagem"></label>
          <label>Categoria<input data-filter="category" value="${esc(Array.isArray(this.filters.category) ? this.filters.category.join(",") : this.filters.category || "")}" placeholder="ir, localtuya, agenda"></label>
          <label>Tipo<input data-filter="event_type" value="${esc(Array.isArray(this.filters.event_type) ? this.filters.event_type.join(",") : this.filters.event_type || "")}" placeholder="ir.sensor_update.response"></label>
          <label>Severidade<select data-filter="severity"><option value="">Todas</option>${Object.keys(SEVERITY_LABEL).map((value) => `<option value="${value}" ${this.filters.severity === value ? "selected" : ""}>${SEVERITY_LABEL[value]}</option>`).join("")}</select></label>
          <label>Resultado<select data-filter="outcome"><option value="">Todos</option>${Object.keys(OUTCOME_LABEL).map((value) => `<option value="${value}" ${this.filters.outcome === value ? "selected" : ""}>${OUTCOME_LABEL[value]}</option>`).join("")}</select></label>
          <label>Audibilidade<select data-filter="audibility"><option value="">Todas</option>${Object.keys(AUDIBILITY_LABEL).map((value) => `<option value="${value}" ${this.filters.audibility === value ? "selected" : ""}>${AUDIBILITY_LABEL[value]}</option>`).join("")}</select></label>
          <label>Correlation ID<input data-filter="correlation_id" value="${esc(this.filters.correlation_id || "")}"></label>
          <label>Transmission ID<input data-filter="transmission_id" value="${esc(this.filters.transmission_id || "")}"></label>
          <label>Frame hash<input data-filter="frame_hash" value="${esc(this.filters.frame_hash || "")}"></label>
          <label>Retenção<select data-filter="retention_class"><option value="">Todas</option>${Object.keys(RETENTION_LABEL).map((value) => `<option value="${value}" ${this.filters.retention_class === value ? "selected" : ""}>${RETENTION_LABEL[value]}</option>`).join("")}</select></label>
        </div>
        <div class="filter-actions"><button data-action="apply-filters">Aplicar</button><button class="secondary" data-action="clear-filters">Limpar</button></div>
      </details>`;
    }

    renderTimeline() {
      return `${this.renderFilters()}${this.renderEventTable(this.events)}`;
    }

    renderEventTable(events) {
      if (!events.length) return `<div class="empty">${icon("mdi:timeline-remove-outline")} Nenhum evento encontrado.</div>`;
      return `<div class="table-wrap"><table>
        <thead><tr><th>Horário</th><th>Evento</th><th>Ator</th><th>Resultado</th><th>Audibilidade</th><th></th></tr></thead>
        <tbody>${events.map((event) => `<tr class="event-row ${event.is_anomaly ? "anomaly" : ""}" data-event="${esc(event.event_id)}">
          <td class="time">${esc(fmt(event.occurred_at_local || event.occurred_at))}${event.compacted_count > 1 ? `<small>${event.compacted_count} ocorrências</small>` : ""}</td>
          <td><div class="event-title">${this.severityChip(event)}<strong>${esc(event.summary)}</strong></div><small>${esc(event.event_type)} · ${esc(event.category)}</small></td>
          <td>${this.actorChip(event)}<small>${esc(event.origin_class || "—")}</small></td>
          <td><span class="chip outcome ${esc(event.outcome)}">${esc(OUTCOME_LABEL[event.outcome] || event.outcome)}</span></td>
          <td>${this.audibilityChip(event)}</td>
          <td>${icon("mdi:chevron-right")}</td>
        </tr>`).join("")}</tbody>
      </table></div>${this.nextCursor ? `<button class="load-more" data-action="load-more">Carregar mais</button>` : ""}`;
    }

    renderTransmissions() {
      const events = this.events.filter((event) => event.transmission_id || String(event.event_type).startsWith("ir."));
      return `${this.renderFilters()}<div class="transmission-cards">${events.map((event) => {
        const details = event.details_json || {};
        return `<article class="transmission-card" data-event="${esc(event.event_id)}">
          <header><div>${this.audibilityChip(event)} ${this.severityChip(event)}</div><time>${esc(fmt(event.occurred_at_local))}</time></header>
          <h3>${esc(event.frame_kind || event.event_type)}</h3>
          <p>${esc(event.summary)}</p>
          <dl><dt>Transmission ID</dt><dd>${esc(event.transmission_id || "—")}</dd><dt>Correlation ID</dt><dd>${esc(event.correlation_id || "—")}</dd><dt>Hash</dt><dd>${esc(event.frame_hash || "—")}</dd><dt>Comando</dt><dd>${esc(details.command || event.action_name || "—")}</dd></dl>
        </article>`;
      }).join("")}</div>${!events.length ? `<div class="empty">Nenhuma transmissão encontrada.</div>` : ""}`;
    }

    renderAnomalies() {
      if (!this.anomalies.length) return `<div class="empty success">${icon("mdi:check-decagram")} Nenhuma anomalia ativa.</div>`;
      return `<div class="anomaly-grid">${this.anomalies.map((item) => `<article class="anomaly-card ${esc(item.severity)}">
        <header>${icon("mdi:alert-decagram")}<div><span>${esc(item.anomaly_type)}</span><strong>${esc(item.explanation)}</strong></div></header>
        <p>${esc(item.recommendation)}</p>
        <dl><dt>Primeiro</dt><dd>${esc(fmt(item.first_seen))}</dd><dt>Último</dt><dd>${esc(fmt(item.last_seen))}</dd><dt>Quantidade</dt><dd>${esc(item.count)}</dd></dl>
        <button class="secondary" data-ack="${esc(item.anomaly_id)}">Reconhecer</button>
      </article>`).join("")}</div>`;
    }

    renderBeeps() {
      return `<div class="beep-intro"><div>${icon("mdi:volume-high")}<h2>Observações de bip</h2><p>Registre imediatamente. A janela é recalculada após o período configurado e nunca presume causalidade apenas por proximidade.</p></div><button class="beep" data-action="beep">Registrar bip agora</button></div>${this.renderEventTable(this.events.filter((event) => String(event.event_type).startsWith("user.")))}`;
    }

    renderStats() {
      const storage = this.snapshot?.storage || {};
      const health = this.snapshot?.health || {};
      return `<div class="stats-grid">
        ${this.statPanel("Persistência", [
          ["Estado do escritor", storage.writer_state || "—"], ["Fila total", storage.queue_size || 0], ["Descartados", storage.dropped_events || 0], ["Última falha", storage.last_failure || "Nenhuma"], ["Última limpeza", fmt(storage.last_cleanup)], ["Schema", storage.schema_version || "—"],
        ])}
        ${this.statPanel("Eventos por classe", Object.entries(storage.events_by_retention_class || {}).map(([key, value]) => [RETENTION_LABEL[key] || key, value]))}
        ${this.statPanel("Eventos por categoria", Object.entries(storage.events_by_category || {}).map(([key, value]) => [key, value]))}
        ${this.statPanel("Instrumentação", [["Completa", bool(health.instrumentation_complete)], ["Persistência saudável", bool(health.persistence_healthy)], ["Modo intensivo", bool(health.intensive_mode)], ["Latência última gravação", `${storage.last_write_latency_ms || 0} ms`], ["Maior latência", `${storage.max_write_latency_ms || 0} ms`]])}
      </div>`;
    }

    statPanel(title, rows) {
      return `<article class="stat-panel"><h3>${esc(title)}</h3><dl>${rows.map(([key, value]) => `<dt>${esc(key)}</dt><dd>${esc(value)}</dd>`).join("")}</dl></article>`;
    }

    renderSettings() {
      const s = this.snapshot?.settings || {};
      const number = (key, label, min, max, help) => `<label>${label}<input type="number" data-setting="${key}" min="${min}" max="${max}" value="${esc(s[key])}"><small>${help || ""}</small></label>`;
      return `<form class="settings-form">
        <section><h2>Retenção</h2><p><strong>Completo</strong> contém todo o fluxo técnico; <strong>Erros</strong> mantém detalhes de falhas; <strong>Absoluto</strong> preserva acontecimentos importantes.</p><div class="settings-grid">
          ${number("retention_absolute_days", "Absoluto (dias)", 1, 365)}
          ${number("retention_error_days", "Erros (dias)", 1, 180)}
          ${number("retention_full_days", "Completo (dias)", 1, 30)}
        </div></section>
        <section><h2>Correlação de bip</h2><div class="settings-grid">
          ${number("beep_window_before_seconds", "Janela anterior (s)", 10, 1800)}
          ${number("beep_window_after_seconds", "Janela posterior (s)", 10, 1800)}
          ${number("localtuya_confirmation_seconds", "Confirmação LocalTuya (s)", 1, 600)}
        </div></section>
        <section><h2>Anomalias</h2><div class="settings-grid">
          ${number("multiple_full_frames_limit", "Limite de frames completos", 1, 20)}
          ${number("multiple_full_frames_window_seconds", "Janela de frames (s)", 1, 3600)}
          ${number("close_transmissions_seconds", "Transmissões próximas (s)", 1, 60)}
          ${number("identical_frame_window_seconds", "Frame idêntico (s)", 1, 3600)}
          ${number("logical_concurrency_seconds", "Concorrência lógica (s)", 1, 300)}
          ${number("external_reaction_window_seconds", "Reação após mudança externa (s)", 1, 1800)}
          ${number("oscillation_window_seconds", "Janela de oscilação (s)", 10, 7200)}
          ${number("oscillation_min_changes", "Mudanças para oscilação", 4, 20)}
        </div></section>
        <section><h2>Persistência e interface</h2><div class="settings-grid">
          ${number("max_database_mb", "Tamanho máximo do banco (MB)", 10, 4096)}
          ${number("default_page_size", "Eventos por página", 10, 250)}
          <label class="toggle"><input type="checkbox" data-setting="intensive_mode" ${s.intensive_mode ? "checked" : ""}><span>Modo intensivo</span><small>Registra avaliações sem mudança e detalhes intermediários.</small></label>
          <label class="toggle"><input type="checkbox" data-setting="compaction_enabled" ${s.compaction_enabled ? "checked" : ""}><span>Compactação</span><small>Agrupa avaliações equivalentes sem transmissão.</small></label>
          <label class="toggle"><input type="checkbox" data-setting="technical_details_enabled" ${s.technical_details_enabled ? "checked" : ""}><span>Detalhes técnicos</span><small>Permite armazenar payloads técnicos sanitizados.</small></label>
        </div></section>
        <section><h2>Notificações</h2><div class="settings-grid">
          <label class="toggle"><input type="checkbox" data-setting="notifications_enabled" ${s.notifications_enabled ? "checked" : ""}><span>Notificações habilitadas</span></label>
          <label>Severidade mínima<select data-setting="notification_min_severity">${Object.keys(SEVERITY_LABEL).map((value) => `<option value="${value}" ${s.notification_min_severity === value ? "selected" : ""}>${SEVERITY_LABEL[value]}</option>`).join("")}</select></label>
          ${number("notification_cooldown_seconds", "Cooldown (s)", 60, 86400)}
          <label>Serviço notify opcional<input data-setting="notify_service" value="${esc(s.notify_service || "")}" placeholder="notify.mobile_app"></label>
          <label>Tipos de anomalia notificados<input data-setting="enabled_anomaly_types" data-list="true" value="${esc((s.enabled_anomaly_types || []).join(", "))}" placeholder="Vazio = todos"><small>Lista separada por vírgulas.</small></label>
          <label>Categorias visíveis padrão<input data-setting="visible_categories" data-list="true" value="${esc((s.visible_categories || []).join(", "))}" placeholder="Vazio = todas"><small>Ex.: ir, agenda, localtuya, anomaly.</small></label>
        </div></section>
        <div class="form-actions"><button type="button" data-action="save-settings">Salvar configurações</button><button type="button" class="secondary" data-action="cleanup">Executar limpeza agora</button></div>
      </form>`;
    }

    renderExport() {
      return `<div class="export-grid">
        ${this.exportCard("CSV da consulta", "Dados tabulares da consulta e filtros atuais.", "csv", "mdi:file-delimited-outline")}
        ${this.exportCard("JSON completo", "Eventos detalhados da consulta atual, sanitizados.", "json", "mdi:code-json")}
        ${this.exportCard("Pacote de diagnóstico", "Snapshot, saúde, anomalias, eventos, transmissões e relatório humano em ZIP.", "diagnostic_package", "mdi:folder-zip-outline")}
        ${this.exportCard("Relatório do problema", "Texto humano pronto para copiar e comparar os bips com SensorUpdate, frame completo e mudanças externas.", "problem_report", "mdi:text-box-search-outline")}
      </div>`;
    }

    exportCard(title, description, type, iconName) {
      return `<article class="export-card">${icon(iconName)}<h3>${esc(title)}</h3><p>${esc(description)}</p><button data-export="${type}">Gerar</button></article>`;
    }

    renderBeepDialog() {
      const local = new Date();
      local.setMinutes(local.getMinutes() - local.getTimezoneOffset());
      const current = local.toISOString().slice(0, 19);
      return `<dialog class="beep-dialog"><form method="dialog">
        <header><div>${icon("mdi:volume-high")}<h2>Registrar bip agora</h2></div><button class="icon secondary" value="cancel">${icon("mdi:close")}</button></header>
        <label>Quantidade<select name="quantity"><option>1 bip</option><option selected>2 bips</option><option>vários bips</option><option>não tenho certeza</option></select></label>
        <label>Horário<input type="datetime-local" name="occurred_at" value="${current}" step="1"><small>Permitido ajustar apenas alguns segundos para corrigir o instante do clique.</small></label>
        <label>Observação opcional<textarea name="note" rows="3" placeholder="Ex.: dois bips sem alteração visual aparente"></textarea></label>
        <p class="notice">A janela padrão considera eventos antes e depois. Proximidade temporal não confirma causalidade.</p>
        <footer><button class="secondary" value="cancel">Cancelar</button><button type="button" data-action="confirm-beep">Confirmar registro</button></footer>
      </form></dialog>`;
    }

    renderEventDialog() {
      if (!this.expanded) return `<dialog class="event-dialog"></dialog>`;
      const event = this.expanded;
      if (event.loading) return `<dialog class="event-dialog" open><div class="loading">Carregando detalhes…</div></dialog>`;
      if (event.error) return `<dialog class="event-dialog" open><div class="banner error">${esc(event.error)}</div></dialog>`;
      const details = event.details_json || {};
      return `<dialog class="event-dialog"><article class="event-detail">
        <header><div><div class="eyebrow">${esc(event.event_type)}</div><h2>${esc(event.summary)}</h2><div class="chip-row">${this.severityChip(event)} ${this.actorChip(event)} ${this.audibilityChip(event)}</div></div><button class="icon secondary" data-action="close-event">${icon("mdi:close")}</button></header>
        <div class="detail-grid">
          ${this.detailSection("Resumo", { horário: fmt(event.occurred_at_local), resultado: OUTCOME_LABEL[event.outcome] || event.outcome, retenção: RETENTION_LABEL[event.retention_class] || event.retention_class, mensagem_técnica: event.technical_message })}
          ${this.detailSection("Origem", { ator_executor: event.actor_name, usuário_originador: event.user_name || "Sistema/indisponível", classe: event.origin_class, confiança: event.origin_confidence, componente: event.source_component, entidade: event.source_entity_id })}
          ${this.detailSection("Gatilho e contexto", { trigger_platform: event.trigger_platform, trigger_entity_id: event.trigger_entity_id, context_id: event.context_id, parent_context_id: event.parent_context_id, correlation_id: event.correlation_id, parent_correlation_id: event.parent_correlation_id })}
          ${this.detailSection("Comando solicitado", { domínio: event.action_domain, ação: event.action_name, transmission_id: event.transmission_id, frame_kind: event.frame_kind, frame_hash: event.frame_hash, audibilidade_esperada: AUDIBILITY_LABEL[event.expected_audibility] || event.expected_audibility })}
        </div>
        ${this.comparisonTable(event.before_json, event.desired_json, event.confirmed_json)}
        <details open><summary>Dados técnicos</summary><pre>${esc(pretty(details))}</pre></details>
        <details><summary>Eventos relacionados (${event.related?.length || 0})</summary><div class="related">${(event.related || []).map((item) => `<button data-event="${esc(item.event_id)}"><span>${esc(fmt(item.occurred_at_local))}</span><strong>${esc(item.summary)}</strong></button>`).join("") || "Nenhum evento correlacionado."}</div></details>
      </article></dialog>`;
    }

    detailSection(title, data) {
      return `<section class="detail-section"><h3>${esc(title)}</h3><dl>${Object.entries(data).filter(([, value]) => value !== null && value !== undefined && value !== "").map(([key, value]) => `<dt>${esc(key.replaceAll("_", " "))}</dt><dd>${esc(value)}</dd>`).join("") || `<dd>Não informado</dd>`}</dl></section>`;
    }

    comparisonTable(before, desired, confirmed) {
      const keys = ["power", "mode", "treatment", "power_profile", "level", "target_temperature", "current_temperature", "fan", "swing_vertical", "swing_horizontal", "turbo", "sleep", "health", "eco", "preset", "limits", "priority"];
      const a = before || {}, b = desired || {}, c = confirmed || {};
      if (!Object.keys(a).length && !Object.keys(b).length && !Object.keys(c).length) return "";
      return `<section class="comparison"><h3>Antes / Desejado / Confirmado</h3><div class="table-wrap"><table><thead><tr><th>Campo</th><th>Antes</th><th>Desejado</th><th>Confirmado</th></tr></thead><tbody>${keys.map((key) => `<tr><th>${esc(key)}</th><td>${esc(this.cell(a[key]))}</td><td>${esc(this.cell(b[key]))}</td><td>${esc(c[key] === undefined ? "Não confirmado" : this.cell(c[key]))}</td></tr>`).join("")}</tbody></table></div><p class="notice">“Confirmado” nunca é preenchido automaticamente com o desejado; depende de fonte observada, como LocalTuya.</p></section>`;
    }

    cell(value) {
      if (value === undefined || value === null || value === "") return "—";
      if (typeof value === "object") return JSON.stringify(value);
      return String(value);
    }

    bind() {
      this.shadowRoot.querySelectorAll("[data-tab]").forEach((button) => button.addEventListener("click", () => {
        this.activeTab = button.dataset.tab;
        this.events = [];
        this.nextCursor = null;
        this.render();
        if (["timeline", "transmissions", "beeps"].includes(this.activeTab)) this.loadEvents(true);
        if (this.activeTab === "anomalies") this.loadAnomalies();
      }));
      this.shadowRoot.querySelectorAll("[data-event]").forEach((row) => row.addEventListener("click", (event) => {
        event.stopPropagation();
        this.openEvent(row.dataset.event);
      }));
      this.shadowRoot.querySelectorAll("[data-action]").forEach((button) => button.addEventListener("click", (event) => this.handleAction(button.dataset.action, event)));
      this.shadowRoot.querySelectorAll("[data-ack]").forEach((button) => button.addEventListener("click", async () => {
        await this.ws("acknowledge_anomaly", { anomaly_id: button.dataset.ack });
        await this.loadAnomalies();
      }));
      this.shadowRoot.querySelectorAll("[data-export]").forEach((button) => button.addEventListener("click", () => this.createExport(button.dataset.export)));
    }

    async handleAction(action, event) {
      if (action === "beep") this.shadowRoot.querySelector("dialog.beep-dialog")?.showModal();
      if (action === "refresh") await this.loadAll();
      if (action === "load-more") await this.loadEvents(false);
      if (action === "apply-filters") {
        this.filters = {};
        this.shadowRoot.querySelectorAll("[data-filter]").forEach((input) => {
          if (!input.value) return;
          const key = input.dataset.filter;
          this.filters[key] = ["category", "event_type"].includes(key) && input.value.includes(",") ? input.value.split(",").map((item) => item.trim()).filter(Boolean) : input.value;
        });
        await this.loadEvents(true);
      }
      if (action === "clear-filters") { this.filters = {}; await this.loadEvents(true); }
      if (action === "close-event") { this.shadowRoot.querySelector("dialog.event-dialog")?.close(); this.expanded = null; }
      if (action === "confirm-beep") await this.confirmBeep();
      if (action === "save-settings") await this.saveSettings();
      if (action === "cleanup") { await this.ws("run_cleanup"); await this.loadSnapshot(); }
    }

    async confirmBeep() {
      const dialog = this.shadowRoot.querySelector("dialog.beep-dialog");
      const form = dialog.querySelector("form");
      const data = new FormData(form);
      const occurred = new Date(data.get("occurred_at"));
      await this.ws("register_beep", {
        quantity: data.get("quantity"),
        note: data.get("note") || undefined,
        occurred_at: Number.isNaN(occurred.getTime()) ? undefined : occurred.toISOString(),
      });
      dialog.close();
      await this.loadSnapshot();
      if (this.activeTab === "beeps") await this.loadEvents(true);
    }

    async saveSettings() {
      const settings = { ...(this.snapshot?.settings || {}) };
      this.shadowRoot.querySelectorAll("[data-setting]").forEach((input) => {
        const key = input.dataset.setting;
        if (input.type === "checkbox") settings[key] = input.checked;
        else if (input.type === "number") settings[key] = Number(input.value);
        else if (input.dataset.list === "true") settings[key] = input.value.split(",").map((item) => item.trim()).filter(Boolean);
        else settings[key] = input.value;
      });
      try {
        const result = await this.ws("update_settings", { settings });
        this.snapshot.settings = result.settings;
        this.error = "";
      } catch (error) {
        this.error = error.message || String(error);
      }
      this.render();
    }

    async createExport(type) {
      try {
        const result = await this.ws("create_export", { export_type: type, filters: this.currentFilters() });
        const binary = atob(result.content_base64);
        const bytesArray = new Uint8Array(binary.length);
        for (let i = 0; i < binary.length; i += 1) bytesArray[i] = binary.charCodeAt(i);
        const url = URL.createObjectURL(new Blob([bytesArray], { type: result.mime_type }));
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = result.filename;
        anchor.click();
        setTimeout(() => URL.revokeObjectURL(url), 2000);
      } catch (error) {
        this.error = error.message || String(error);
        this.render();
      }
    }

    styles() {
      return `
        :host{display:block;color:var(--primary-text-color);--cyan:#00a6c8;--blue:#1976d2;--green:#2e7d32;--orange:#ef6c00;--yellow:#b28704;--red:#c62828;--purple:#6a1b9a;--magenta:#ad1457;--gray:#607d8b}
        *{box-sizing:border-box}ha-card{overflow:hidden;border-radius:20px;background:var(--card-background-color)}button,input,select,textarea{font:inherit}button{border:0;border-radius:11px;padding:10px 14px;cursor:pointer;background:var(--primary-color);color:var(--text-primary-color,#fff);display:inline-flex;align-items:center;justify-content:center;gap:7px}button.secondary{background:var(--secondary-background-color);color:var(--primary-text-color);border:1px solid var(--divider-color)}button.icon{width:40px;height:40px;padding:0}.hero{display:flex;justify-content:space-between;gap:24px;padding:24px;background:linear-gradient(135deg,color-mix(in srgb,var(--blue) 18%,var(--card-background-color)),color-mix(in srgb,var(--cyan) 11%,var(--card-background-color)))}.eyebrow{text-transform:uppercase;letter-spacing:.12em;font-size:.72rem;font-weight:800;color:var(--cyan)}h1{font-size:1.65rem;margin:4px 0 7px}.hero p{margin:0;color:var(--secondary-text-color);max-width:760px}.hero-actions{display:flex;align-items:flex-start;gap:8px;flex-wrap:wrap}.beep{background:var(--magenta)}.metrics{display:grid;grid-template-columns:repeat(6,minmax(130px,1fr));gap:10px;padding:14px 18px;border-bottom:1px solid var(--divider-color)}.metric{display:flex;align-items:center;gap:10px;padding:12px;border-radius:14px;background:var(--secondary-background-color);min-width:0}.metric ha-icon{color:var(--blue)}.metric.success ha-icon{color:var(--green)}.metric.error ha-icon{color:var(--red)}.metric.warning ha-icon{color:var(--orange)}.metric.transmission ha-icon{color:var(--cyan)}.metric.database ha-icon{color:var(--purple)}.metric span{display:block;color:var(--secondary-text-color);font-size:.75rem}.metric strong{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.tabs{display:flex;overflow:auto;padding:10px 14px;gap:4px;border-bottom:1px solid var(--divider-color)}.tab{background:transparent;color:var(--secondary-text-color);white-space:nowrap;border-radius:10px}.tab.active{color:var(--primary-text-color);background:color-mix(in srgb,var(--cyan) 18%,var(--secondary-background-color));box-shadow:inset 0 -2px 0 var(--cyan)}.content{padding:18px;min-height:360px}.banner{padding:11px 16px;margin:12px 18px;border-radius:12px}.banner.error{background:color-mix(in srgb,var(--red) 15%,var(--card-background-color));color:var(--red)}.filters{border:1px solid var(--divider-color);border-radius:14px;margin-bottom:14px;background:var(--secondary-background-color)}.filters summary{padding:12px;cursor:pointer;font-weight:700;display:flex;align-items:center;gap:8px}.filter-grid,.settings-grid{display:grid;grid-template-columns:repeat(4,minmax(160px,1fr));gap:12px;padding:12px}.filter-actions,.form-actions{display:flex;gap:8px;padding:0 12px 12px}label{display:flex;flex-direction:column;gap:5px;font-size:.82rem;font-weight:600}input,select,textarea{width:100%;border:1px solid var(--divider-color);background:var(--card-background-color);color:var(--primary-text-color);border-radius:9px;padding:9px}label small{font-weight:400;color:var(--secondary-text-color)}.table-wrap{overflow:auto;border:1px solid var(--divider-color);border-radius:14px}table{border-collapse:collapse;width:100%;min-width:900px}thead{position:sticky;top:0;z-index:2;background:var(--card-background-color)}th,td{padding:11px 12px;border-bottom:1px solid var(--divider-color);text-align:left;vertical-align:top}.event-row{cursor:pointer}.event-row:hover{background:color-mix(in srgb,var(--cyan) 7%,transparent)}.event-row.anomaly{box-shadow:inset 4px 0 0 var(--red)}.time{white-space:nowrap}.time small,td small{display:block;color:var(--secondary-text-color);margin-top:4px}.event-title{display:flex;align-items:flex-start;gap:8px;max-width:540px}.chip-row{display:flex;flex-wrap:wrap;gap:6px;margin-top:9px}.chip{display:inline-flex;align-items:center;gap:4px;border-radius:999px;padding:4px 8px;font-size:.72rem;background:var(--secondary-background-color);white-space:nowrap}.severity.info{border:1px solid var(--blue);color:var(--blue)}.severity.success{border:1px solid var(--green);color:var(--green)}.severity.warning{border:1px solid var(--orange);color:var(--orange)}.severity.error,.severity.critical{border:1px solid var(--red);color:var(--red)}.audibility.silent_expected{border:1px solid var(--cyan);color:var(--cyan)}.audibility.audible_expected{border:1px solid var(--orange);color:var(--orange)}.actor{border:1px solid color-mix(in srgb,var(--purple) 50%,transparent);color:var(--purple)}.outcome.blocked,.outcome.suppressed{color:var(--yellow)}.outcome.confirmed,.outcome.accepted{color:var(--green)}.outcome.failed,.outcome.rejected{color:var(--red)}.load-more{display:flex;margin:14px auto}.empty{padding:50px;text-align:center;color:var(--secondary-text-color);display:flex;flex-direction:column;align-items:center;gap:9px}.empty.success{color:var(--green)}.transmission-cards,.anomaly-grid,.export-grid,.stats-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px}.transmission-card,.anomaly-card,.export-card,.stat-panel{padding:16px;border:1px solid var(--divider-color);border-radius:15px;background:var(--secondary-background-color)}.transmission-card{cursor:pointer}.transmission-card header{display:flex;justify-content:space-between;gap:10px}.transmission-card h3{margin:12px 0 5px}.transmission-card p{color:var(--secondary-text-color)}dl{display:grid;grid-template-columns:max-content minmax(0,1fr);gap:6px 12px;margin:0}dt{color:var(--secondary-text-color);font-size:.78rem}dd{margin:0;overflow-wrap:anywhere}.anomaly-card{border-left:4px solid var(--orange)}.anomaly-card.error,.anomaly-card.critical{border-left-color:var(--red)}.anomaly-card header{display:flex;gap:10px}.anomaly-card header strong,.anomaly-card header span{display:block}.anomaly-card header span{font-size:.75rem;color:var(--secondary-text-color)}.beep-intro{display:flex;justify-content:space-between;gap:18px;align-items:center;padding:18px;border-radius:15px;background:color-mix(in srgb,var(--magenta) 10%,var(--secondary-background-color));margin-bottom:14px}.beep-intro>div{display:grid;grid-template-columns:auto 1fr;column-gap:10px}.beep-intro h2,.beep-intro p{margin:0}.beep-intro p{grid-column:2;color:var(--secondary-text-color)}.stat-panel h3,.export-card h3{margin-top:0}.stat-panel dl{grid-template-columns:1fr auto}.settings-form section{border:1px solid var(--divider-color);border-radius:14px;margin-bottom:14px;padding:14px}.settings-form section h2{margin:0 0 4px}.settings-form section>p{color:var(--secondary-text-color)}label.toggle{display:grid;grid-template-columns:auto 1fr;align-items:center;column-gap:8px;background:var(--secondary-background-color);padding:10px;border-radius:10px}.toggle input{width:auto}.toggle small{grid-column:2}.export-card>ha-icon{color:var(--purple);--mdc-icon-size:34px}.export-card p{color:var(--secondary-text-color);min-height:46px}.notice{padding:10px;border-radius:10px;background:color-mix(in srgb,var(--yellow) 12%,var(--secondary-background-color));color:var(--secondary-text-color);font-size:.84rem}dialog{border:0;border-radius:18px;background:var(--card-background-color);color:var(--primary-text-color);box-shadow:0 20px 80px rgba(0,0,0,.45);max-height:92vh}dialog::backdrop{background:rgba(0,0,0,.55)}.beep-dialog{width:min(520px,calc(100vw - 24px))}.beep-dialog form{display:grid;gap:14px}.beep-dialog header,.beep-dialog footer,.event-detail>header{display:flex;justify-content:space-between;align-items:flex-start;gap:12px}.beep-dialog header>div{display:flex;gap:8px;align-items:center}.beep-dialog h2{margin:0}.event-dialog{width:min(1180px,calc(100vw - 24px));padding:0}.event-detail{padding:20px}.event-detail>header{position:sticky;top:0;background:var(--card-background-color);z-index:3;padding-bottom:12px;border-bottom:1px solid var(--divider-color)}.event-detail h2{margin:4px 0}.detail-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:14px 0}.detail-section{border:1px solid var(--divider-color);border-radius:12px;padding:12px}.detail-section h3{margin:0 0 10px}.comparison{margin:16px 0}.comparison h3{margin-bottom:8px}details>summary{cursor:pointer;font-weight:700;padding:10px 0}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:var(--code-editor-background-color,var(--secondary-background-color));padding:12px;border-radius:10px;max-height:400px;overflow:auto}.related{display:grid;gap:6px}.related button{background:var(--secondary-background-color);color:var(--primary-text-color);justify-content:flex-start;text-align:left}.related button span{color:var(--secondary-text-color);font-size:.75rem}.loading{padding:50px;text-align:center}.loading ha-icon{animation:spin 1s linear infinite}@keyframes spin{to{transform:rotate(360deg)}}
        @media(max-width:1100px){.metrics{grid-template-columns:repeat(3,1fr)}.filter-grid,.settings-grid{grid-template-columns:repeat(2,1fr)}}
        @media(max-width:700px){.hero{display:block;padding:18px}.hero-actions{margin-top:14px}.metrics{grid-template-columns:repeat(2,1fr);padding:10px}.content{padding:10px}.tab span{display:none}.filter-grid,.settings-grid,.transmission-cards,.anomaly-grid,.export-grid,.stats-grid,.detail-grid{grid-template-columns:1fr}.beep-intro{display:block}.beep-intro button{margin-top:12px}.event-detail{padding:12px}.metric{padding:9px}.metric strong{font-size:.87rem}}
      `;
    }
  }

  customElements.define("elgin-supervisor-diagnostico-card", ElginSupervisorDiagnosticoCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "elgin-supervisor-diagnostico-card",
    name: "Elgin Supervisor — Auditoria e Diagnóstico",
    description: "Linha do tempo, transmissões, anomalias, bips, estatísticas e exportações.",
    preview: true,
  });
})();
