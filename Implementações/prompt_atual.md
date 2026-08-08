# Instalação e validação real do Diagnóstico do Supervisor

## Estado desta etapa

A implementação na réplica está concluída. Não reimplementar banco, card,
dashboard, filtros, correlação, anomalias, migrations, fallback, segurança ou
instrumentação. Este prompt contém somente o trabalho que depende do Home
Assistant e do aparelho físicos.

Artefato pronto para transferência:
`Implementações/elgin_supervisor_diagnostico_instalacao.zip`. As instruções
detalhadas estão em `Implementações/INSTALACAO_DIAGNOSTICO.md`.

## Restrições

- Não alterar nem recompilar o ESPHome.
- Não alterar `esphome/esp8266.yaml` ou `esphome/components/elgin_aux/*`.
- Não usar `custom_components/elgin_supervisor_diagnostico_Para_exemplo/`.
- Não editar arquivos internos de `.storage` manualmente.
- Não reiniciar Home Assistant ou ESPHome sem ação expressa do usuário.
- Instalar primeiro com `input_boolean.elgin_supervisor_modo_sombra` ligado.

## 1. Backup antes da instalação

1. Criar um backup completo do Home Assistant.
2. Preservar as versões ativas de:
   - `packages/elgin_supervisor_climatico.yaml`;
   - `custom_components/elgin_supervisor_diagnostico/`, se existir;
   - dashboard atual e recursos Lovelace;
   - `.storage/elgin_supervisor_diagnostico.sqlite3` e backups associados, se
     existirem, por meio do backup do Home Assistant.
3. Confirmar as entidades LocalTuya listadas no `AGENTS.md` no registro de
   entidades.

## 2. Instalação manual

1. Ativar o modo sombra do Supervisor.
2. Copiar do ZIP somente:
   - `custom_components/elgin_supervisor_diagnostico/` para
     `/config/custom_components/`;
   - `packages/elgin_supervisor_climatico.yaml` para `/config/packages/`.
3. Executar a verificação de configuração do Home Assistant.
4. Reiniciar o Home Assistant manualmente somente se a configuração estiver
   válida.
5. Adicionar a integração **Elgin Supervisor — Diagnóstico** em
   Configurações > Dispositivos e serviços.
6. Confirmar que existe apenas uma instância e que nenhum entity ID recebeu
   sufixo `_2`.
7. Confirmar a migration do dispositivo e das entidades legadas; conflitos
   registrados no log devem ser resolvidos manualmente, sem sobrescrever
   entidades alheias.
8. Confirmar o recurso Lovelace do card. Se o Lovelace usar recursos YAML,
   registrar manualmente a URL informada no guia de instalação.
9. Copiar e colar `Dashboards/dashboard_supervisor.yaml` no dashboard pela
   interface do Home Assistant.

## 3. Validação técnica no Home Assistant

- Executar config check e hassfest quando disponível.
- Testar setup, reload, unload e restart da integração.
- Confirmar ausência de listeners, timers, tasks e executor residuais após
  unload.
- Confirmar banco schema 5, WAL, quick check `ok`, fila drenando, retenção e
  limpeza dinâmica.
- Confirmar migrations idempotentes de banco, opções, Entity Registry e Device
  Registry após um segundo restart.
- Testar permissões com administrador e usuário comum:
  - configurações e reavaliação;
  - exclusão com `APAGAR`;
  - limpeza com `LIMPAR`;
  - pacote diagnóstico administrativo.
- Confirmar que o Recorder não recebe snapshots detalhados em `last_action`.
- Confirmar recurso Lovelace único, sem URL antiga ou tag custom duplicada.

## 4. Validação em modo sombra

Com o modo sombra ainda ligado:

1. Produzir avaliações de Heat, Cool, Dry, fan, swing, Eco e proteções.
2. Confirmar que o diagnóstico registra decisões e bloqueios sem chamar
   Climate, ESPHome, LocalTuya ou transmitir IR.
3. Registrar observações de 1 bip, 2 bips, vários e quantidade incerta.
4. Validar filtros por modo, tratamento, preset, temperatura, umidade,
   potência, usuário, modelo de ativação, função, ação e audibilidade.
5. Reconstruir uma correlação completa na Timeline e exportar um relatório.
6. Simular reload/restart e confirmar cooldown de notificações, anomalias,
   retenção e replay do fallback.

## 5. Validação física controlada

Somente depois do modo sombra passar:

1. Desativar o modo sombra de forma controlada.
2. Testar Power ON, Power OFF, Heat, Cool, Dry, fan e swing.
3. Confirmar I Feel por `SensorUpdate` silencioso.
4. Confirmar importação LocalTuya passiva, sem IR de retorno.
5. Confirmar um único frame por `send_state` e nenhum comando duplicado.
6. Confirmar um bip por comando completo sem Eco e, em Cool com Eco, somente
   o bip do frame completo e o bip separado do Eco.
7. Confirmar que o diagnóstico não cria IR, comandos ou bips adicionais.
8. Reproduzir, se seguro, o caso de umidade acima de 65% até 60% e relacionar
   cada bip observado à solicitação audível, Eco, ação externa ou origem
   indeterminada correspondente.

## 6. Aceite ou rollback

A instalação só é aceita quando todos os itens anteriores passarem. Em caso de
erro funcional, bip extra, loop, entidade `_2`, migration conflitante ou falha
de configuração:

1. reativar imediatamente o modo sombra;
2. restaurar os arquivos anteriores pelo backup;
3. remover o recurso Lovelace novo se ele tiver sido criado;
4. restaurar o banco do diagnóstico somente com o Home Assistant parado;
5. reiniciar manualmente e confirmar o Supervisor original antes de qualquer
   nova tentativa.
