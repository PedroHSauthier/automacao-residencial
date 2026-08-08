# Elgin Supervisor — instalação manual do diagnóstico

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

   `/elgin_supervisor_diagnostico/frontend/elgin-supervisor-diagnostico-card.js?v=1.0.0`

   Se os recursos forem mantidos em YAML, registre essa URL manualmente como
   `module`. Remova somente URLs antigas do mesmo card após confirmar o backup.
8. Cole `Dashboards/dashboard_supervisor.yaml` no editor do dashboard.

## Primeiro teste obrigatório

Mantenha o modo sombra ligado. Confirme no card:

- status operacional, schema 5 e `quick_check: ok`;
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
Teste Power ON/OFF, Heat, Cool, Dry, fan, swing, Eco, I Feel e LocalTuya. Valide:

- um estado completo produz um único frame IR;
- importação LocalTuya não transmite IR;
- `SensorUpdate` é silencioso;
- Eco só é separado em Cool;
- não há comando duplicado nem bip introduzido pelo diagnóstico.

Para investigar os bips do ciclo de desumidificação, registre a observação no
horário exato e filtre por `audible_expected`, função, modo Dry, umidade,
tratamento, transmissão e correlação. Uma proximidade temporal é evidência, não
prova de causalidade física.

## Rollback

1. Reative o modo sombra.
2. Restaure o package, o custom component e o dashboard anteriores.
3. Remova o recurso Lovelace novo se necessário.
4. Para restaurar o SQLite, pare o Home Assistant antes de repor o arquivo do
   backup; nunca edite `.storage` manualmente.
5. Reinicie manualmente e confirme o fluxo original antes de sair do modo
   sombra.
