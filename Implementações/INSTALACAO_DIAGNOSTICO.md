# Elgin Supervisor — instalação manual do diagnóstico

Versão deste pacote: **1.0.3** (schema SQLite 6).

Este pacote instala somente auditoria local. Ele não contém alterações de
ESPHome/C++ e não deve chamar Climate, LocalTuya ou o transmissor IR.

## Conteúdo a transferir

- `custom_components/elgin_supervisor_diagnostico/` →
  `/config/custom_components/elgin_supervisor_diagnostico/`
- `packages/elgin_supervisor_climatico.yaml` →
  `/config/packages/elgin_supervisor_climatico.yaml`
- `Dashboards/dashboard_supervisor.yaml` → copiar e colar pelo editor YAML do
  dashboard; a pasta `Dashboards/` não deve ser criada no Home Assistant.

Não transfira `tests/`, `Images/`, a pasta de referência `_Para_exemplo` ou
arquivos do ESPHome.

## Antes de copiar

1. Ative `input_boolean.elgin_supervisor_modo_sombra`.
2. Faça um backup completo do Home Assistant.
3. Guarde o package e o dashboard atualmente ativos.
4. Se já houver diagnóstico instalado, preserve seu diretório e o banco
   `.storage/elgin_supervisor_diagnostico.sqlite3` pelo backup do sistema.
5. Confira no registro do Home Assistant todas as entidades LocalTuya citadas
   no `AGENTS.md`.

## Instalação

1. Copie o custom component e substitua o package pelos caminhos acima.
2. Em Ferramentas do desenvolvedor, execute **Verificar configuração**.
3. Se a verificação passar, reinicie o Home Assistant manualmente.
4. Abra Configurações > Dispositivos e serviços > Adicionar integração e
   selecione **Elgin Supervisor — Diagnóstico**.
5. Confirme que foi criada apenas uma instância.
6. Verifique os logs por mensagens de migration. Nenhuma entidade canônica deve
   terminar em `_2`; conflitos com IDs alheios são preservados e registrados
   para correção manual.
7. Em Lovelace no modo storage, o recurso é registrado automaticamente como:

   `/elgin_supervisor_diagnostico/frontend/elgin-supervisor-diagnostico-card.js?v=1.0.3`

   Se os recursos forem mantidos em YAML, registre essa URL manualmente como
   `module`. Remova somente URLs antigas do mesmo card após confirmar o backup.
8. No primeiro início, o componente cria antes da migração o backup
   `.storage/elgin_supervisor_diagnostico.pre-v6.sqlite3.bak`. A migração
   reclassifica somente eventos rotineiros conhecidos e limpa perfis de
   potência ambíguos; o histórico bruto sanitizado permanece preservado.
9. Cole `Dashboards/dashboard_supervisor.yaml` no editor do dashboard.

## Primeiro teste obrigatório

Mantenha o modo sombra ligado. Confirme no card:

- status operacional, schema 6 e `quick_check: ok`;
- seletor de severidade com Rotina, Informação, Sucesso, Atenção, Erro e
  Crítico, nessa ordem, inclusive quando a contagem for zero;
- faceta Potência sem `0`, `1`, `true`, `false`, `on` ou `off`;
- somente um seletor auxiliar aberto, com fechamento por clique externo,
  `Tab` e `Escape`;
- último fluxo coerente com a correlação mais recente, inclusive após novo
  carregamento do card;
- Timeline recebendo avaliações sem transmissão;
- abas, detalhes Antes/Depois/Diff, cursores e filtros;
- registro de 1, 2, vários e quantidade incerta de bips;
- anomalias, reconhecimento, resolução e recorrência;
- limpeza/exclusão somente como administrador e após digitar a confirmação;
- exportação e pacote administrativo sanitizado;
- unload/reload sem listeners ou tasks residuais.

O diagnóstico deve continuar sem qualquer ação caso seja removido ou falhe.

## Teste físico controlado

Depois do modo sombra passar, desative-o apenas durante uma janela acompanhada.
Teste Power ON/OFF, Aquecimento, Refrigeração, Desumidificação, ventilação,
swing, Eco, I Feel e LocalTuya. Valide:

- um estado completo produz um único frame IR;
- importação LocalTuya não transmite IR;
- `SensorUpdate` é silencioso;
- Eco só é separado em Refrigeração;
- não há comando duplicado nem bip introduzido pelo diagnóstico.

Para investigar os bips do ciclo de desumidificação, registre a observação no
horário exato e filtre por `audible_expected`, função, modo Desumidificação, umidade,
tratamento, transmissão e correlação. Uma proximidade temporal é evidência, não
prova de causalidade física.

## Rollback

1. Reative o modo sombra.
2. Restaure pelo backup/Git o package, o custom component e o dashboard da
   versão 1.0.2.
3. Retorne o recurso Lovelace para `?v=1.0.2`.
4. Se a migração do schema 6 já ocorreu, restaure o SQLite pelo backup somente
   com o Home Assistant parado; nunca edite `.storage` manualmente.
5. Para usar o backup automático, restaure
   `.storage/elgin_supervisor_diagnostico.pre-v6.sqlite3.bak` como
   `.storage/elgin_supervisor_diagnostico.sqlite3` ainda com o Home Assistant
   parado.
6. Reinicie manualmente e confirme o fluxo original antes de sair do modo
   sombra.
