# Diagnóstico 1.0.3 — classificação, filtros e fluxo útil

## Objetivo desta etapa

Implementar somente as correções pendentes de organização e leitura do card de
Diagnóstico do Supervisor:

1. distribuir corretamente os eventos entre níveis de severidade;
2. corrigir a semântica e a apresentação do filtro de potência;
3. tornar todos os seletores auxiliares intuitivos, com fechamento automático;
4. padronizar a interface em português e em escrita consistente;
5. transformar o bloco de último fluxo em uma reconstrução real e útil.

Não reimplementar banco, Timeline, paginação, popup de detalhes, filtros
avançados, exportação, observações, anomalias ou alterações visuais já
concluídas. Não alterar ESPHome, C++ AUX, transmissão IR ou o comportamento do
Supervisor. As alterações no package devem ficar restritas aos payloads dos
eventos de diagnóstico.

Baseline desta etapa: componente `1.0.2`. Somente ao concluir e validar estas
correções, atualizar componente, recurso frontend e pacote para `1.0.3`.

## Modo de execução

- Ler integralmente o `AGENTS.md` antes de implementar.
- Tratar a análise técnica deste prompt como concluída; confirmar os pontos
  exatos no código, mas não repetir uma auditoria ampla nem reimplementar partes
  prontas.
- Informar os arquivos que serão alterados e o plano curto de execução; depois
  prosseguir como autorizado pelo usuário.
- Trabalhar somente na réplica. Não copiar para a instalação ativa, não
  reiniciar Home Assistant e não executar transmissão física.
- Preservar mudanças alheias já existentes no worktree.

## Diagnóstico técnico já confirmado

### Severidades

- O modelo já aceita `debug`, `info`, `success`, `warning`, `error` e
  `critical`, mas quase nenhum produtor usa `debug`.
- Mudanças rotineiras de helpers, recálculos da Agenda, avaliações sem ação e
  chamadas lógicas acabam concentradas em `info`.
- O filtro mostra somente valores existentes no banco; por isso `debug` e
  `critical` podem parecer categorias ausentes.
- O catálogo suporta filtros, mas o frontend o carrega sem o recorte aplicado
  e não o atualiza ao aplicar filtros. As contagens mostradas são globais e
  podem não corresponder à consulta atual.
- O número exibido é um `COUNT(*)` sem formatação ou explicação de escopo.

### Potência

- O cadastro dos perfis de potência na Agenda não é a causa do valor isolado
  `1`.
- O contrato dos eventos de diagnóstico usa a chave `power` com dois
  significados diferentes:
  - liga/desliga do comando completo (`true/false`, persistido também como
    `1/0` em alguns caminhos);
  - nome do perfil desejado, como `Fraco`.
- O manager usa hoje `data.get("power") or data.get("potencia")` como
  `power_profile`, portanto valores booleanos entram incorretamente na faceta
  de potência.
- Esse é um erro do contrato de instrumentação e da normalização do
  diagnóstico; não se deve renomear ou alterar os perfis reais da Agenda.

### Seletores auxiliares

- O multiselect próprio usa `<details>` isolados.
- Não existe listener para clique externo, `Escape` ou abertura de outro
  seletor.
- Cada popup permanece aberto até o usuário clicar novamente no mesmo campo.

### Português e padrão de escrita

- `semanticValue()` traduz apenas booleanos, `unknown` e `unavailable`.
- Facetas, chips, métricas e detalhes ainda podem mostrar códigos crus, por
  exemplo `essential`, `normal`, `warning`, `action` e resultados internos.
- O backend gera parte dos rótulos por `capitalize()`, o que não traduz os
  termos e não preserva adequadamente nomes como ESPHome, LocalTuya, HA, IR e
  I Feel.
- Códigos canônicos precisam continuar intactos nos filtros, no JSON técnico e
  no banco; somente a camada de apresentação deve ser traduzida.

### Último fluxo

- O backend escolhe o anchor por prioridade fixa:
  `last_confirmation or last_transmission or last_decision`.
- Depois da primeira confirmação, uma confirmação antiga pode continuar sendo
  preferida a transmissões e decisões mais recentes.
- A reconstrução usa apenas o deque recente em memória e no máximo doze
  eventos; depois de restart ou alto volume, partes do fluxo podem existir no
  SQLite e não aparecer.
- O frontend tenta descobrir as fases por regex sobre tipo, categoria e resumo,
  e sempre desenha cinco caixas. Fases ausentes viram cartões genéricos vazios,
  fazendo o bloco parecer estático.
- O título afirma “completo” mesmo quando não há confirmação, ação ou decisão.

## Arquivos previstos

Alterar somente o necessário entre:

- `custom_components/elgin_supervisor_diagnostico/models.py`;
- `custom_components/elgin_supervisor_diagnostico/manager.py`;
- `custom_components/elgin_supervisor_diagnostico/storage.py`;
- `custom_components/elgin_supervisor_diagnostico/migrations.py`;
- `custom_components/elgin_supervisor_diagnostico/websocket.py`;
- `custom_components/elgin_supervisor_diagnostico/frontend/elgin-supervisor-diagnostico-card.js`;
- `custom_components/elgin_supervisor_diagnostico/const.py`;
- `custom_components/elgin_supervisor_diagnostico/manifest.json`;
- `packages/elgin_supervisor_climatico.yaml`, exclusivamente nos
  `event_data` de `elgin_supervisor_diagnostic_event`;
- testes direcionados em `tests/elgin_supervisor_diagnostico/`;
- `Implementações/INSTALACAO_DIAGNOSTICO.md` e o ZIP de instalação.

Não alterar `custom_components/elgin_supervisor_agenda/`, arquivos ESPHome,
C++, entidades LocalTuya, dashboard ou automações de controle fora dos payloads
diagnósticos citados.

## Plano de implementação

### 1. Taxonomia de severidade

Manter os seis níveis já aceitos pelo modelo e apresentá-los sempre nesta
ordem:

1. `debug` — **Rotina**;
2. `info` — **Informação**;
3. `success` — **Sucesso**;
4. `warning` — **Atenção**;
5. `error` — **Erro**;
6. `critical` — **Crítico**.

Não criar níveis proprietários adicionais. Severidade deve indicar impacto,
enquanto categoria e tipo continuam indicando a natureza do evento.

Reclassificar de forma determinística:

- **Rotina/debug:** recálculos periódicos da Agenda, gatilhos e início de
  avaliação, avaliação sem mudança, mudanças de helpers de bookkeeping como
  timestamps/textos internos e chamadas lógicas de scripts sem transmissão;
- **Informação/info:** mudança funcional relevante, decisão calculada,
  solicitação lógica significativa e observação neutra;
- **Sucesso/success:** avaliação concluída, duplicata corretamente suprimida,
  software aceitou a solicitação e confirmação LocalTuya correspondente;
- **Atenção/warning:** decisão bloqueada, timeout de confirmação, entidade
  indisponível, divergência ou mudança externa/indeterminada;
- **Erro/error:** falha de avaliação, persistência, serviço ou integração;
- **Crítico/critical:** perda de componente essencial ou falha que comprometa a
  continuidade da auditoria.

Regras de proteção:

- evento com transmissão potencialmente audível nunca pode virar `debug`;
- transmissão, confirmação, mudança externa, erro e observação do usuário não
  podem ser rebaixados por regra de volume;
- não classificar toda mudança de estado como rotina: usar allowlist de tipos e
  entidades internas conhecidos;
- manter `has_error` coerente apenas com `error` e `critical`.

### 2. Histórico e contagens das severidades

Criar migração idempotente para o banco existente:

- alterar somente linhas `severity='info'` que correspondam exatamente aos
  tipos rotineiros definidos;
- não reclassificar por texto livre do resumo;
- não tocar eventos de transmissão, externos, observações ou erros;
- registrar quantidade de linhas alteradas e permitir segundo restart sem nova
  modificação;
- usar transação e rollback em caso de falha.

O seletor de severidade deve:

- mostrar sempre os seis níveis, inclusive os que tenham contagem zero;
- ordenar pela escala acima, nunca por contagem ou ordem alfabética;
- exibir contagens no padrão `pt-BR`, por exemplo `28.923`;
- informar por tooltip ou texto auxiliar que a contagem representa registros
  no recorte atual;
- recalcular as facetas ao aplicar ou limpar filtros.

Implementar facetas disjuntivas: para calcular a contagem de uma faceta, aplicar
todos os filtros atuais exceto o próprio campo. Assim o usuário ainda consegue
ver e selecionar alternativas de severidade, potência, categoria e demais
campos sem receber números globais enganosos.

### 3. Contrato canônico de potência

Separar explicitamente os significados nos eventos diagnósticos:

- `power_state`: liga/desliga (`true/false`);
- `power_profile`: nome ou ID do perfil, por exemplo `Fraco`;
- `power_level`: nível numérico somente quando essa informação existir e tiver
  significado próprio.

No package:

- eventos de transmissão completa devem enviar `power_state`, nunca usar o
  booleano em `power_profile`;
- avaliações e decisões devem enviar `power_profile` com
  `potencia_desejada`;
- preservar o booleano dentro de `desired.power` quando fizer parte do estado
  completo;
- não alterar argumentos de scripts, actions ESPHome ou lógica de decisão.

No manager/modelo:

- parar de usar a chave genérica `power` como fallback de `power_profile`;
- aceitar `power_profile` e o alias legado inequívoco `potencia`;
- rejeitar como perfil os valores booleanos e tokens `0`, `1`, `true`, `false`,
  `on` e `off`;
- manter estado de energia nos detalhes/estado desejado, não na coluna de
  perfil;
- se existir somente um nível numérico real, apresentá-lo como `Nível N` e não
  como perfil sem contexto;
- nunca inferir um nome de perfil sem evidência no payload ou catálogo.

Na migração histórica:

- recuperar o perfil a partir de payload/snapshot somente quando houver campo
  inequívoco;
- limpar `power_profile` para `NULL` quando contiver apenas booleano/tokens de
  energia;
- não converter `1` automaticamente para `Fraco`;
- preservar o dado bruto sanitizado para auditoria técnica.

Na interface:

- a faceta Potência deve conter somente perfis reais com rótulo humano;
- níveis, quando existentes, devem aparecer como `Nível 1`, `Nível 2`, etc.;
- valores técnicos podem aparecer secundariamente apenas quando “Mostrar
  códigos técnicos” estiver habilitado.

### 4. Fechamento intuitivo dos seletores

Aplicar a todos os `elgin-diagnostic-multiselect`:

- somente um popup pode permanecer aberto por vez;
- clicar em outro seletor fecha o anterior antes de abrir o novo;
- clicar fora fecha o popup aberto;
- pressionar `Escape` fecha e devolve foco ao campo correspondente;
- navegar por `Tab` e retirar o foco do seletor deve fechá-lo;
- marcar várias opções dentro do mesmo seletor não deve fechá-lo a cada clique;
- aplicar filtros continua fechando o painel geral, como já implementado;
- listeners globais devem ser removidos em `disconnectedCallback`, sem vazamento
  após reload do card.

Usar `event.composedPath()` para funcionar corretamente através dos Shadow DOM
do card e do picker. Não usar recriação destrutiva do card nem alterar foco,
scroll, filtros aplicados ou rascunhos.

### 5. Português e padrão de apresentação

Criar uma função central de apresentação sensível ao tipo do campo, sem mudar o
valor canônico persistido. Padronizar:

- modos de captura: `essential` → **Essencial**, `normal` → **Normal**,
  `intensive` → **Intensivo**;
- severidades conforme a taxonomia desta etapa;
- categorias, resultados, audibilidade, origem, agenda, proteções, modos e
  funções com rótulos portugueses;
- valores `unknown` e `unavailable` como **Desconhecido** e **Indisponível** na
  interface comum;
- início de frase e valores nominais com maiúscula inicial quando cabível;
- preservar grafia oficial de **Home Assistant**, **ESPHome**, **LocalTuya**,
  **I Feel**, **Eco**, **IR** e **HA**;
- trocar atalhos visuais `Cool`, `Heat` e `Dry` por **Refrigeração**,
  **Aquecimento** e **Desumidificação**, mantendo o código apenas no modo
  técnico;
- não capitalizar cegamente entity IDs, nomes definidos pelo usuário, JSON,
  chaves técnicas ou textos completos.

Aplicar o formatador em métricas, chips, filtros, tabelas, cards de decisão,
ações, anomalias, popup e estatísticas. A aba Técnico e exportações devem
continuar exibindo os valores canônicos necessários à investigação.

Revisar todos os textos visíveis do card para concordância, acentuação e padrão
de sentença. Evitar misturar rótulo português com valor inglês cru quando
existe tradução inequívoca.

### 6. Reconstrução útil do último fluxo

Definir o propósito do bloco como: mostrar a correlação operacional mais
recente desde o gatilho até seu resultado, permitindo entender se houve ação,
supressão, bloqueio, transmissão, confirmação, timeout ou mudança externa.

No backend:

- selecionar o anchor mais recente por `occurred_at`, e não pela prioridade fixa
  entre confirmação, transmissão e decisão;
- preferir a correlação operacional mais recente que tenha ao menos uma
  decisão, ação ou resultado;
- buscar os eventos pelo `correlation_id` no SQLite quando não estiverem mais
  no deque em memória;
- ordenar cronologicamente e gerar fases por `event_type`/categoria canônicos,
  sem depender de resumo ou idioma;
- fornecer por fase: presença, horário, event ID, tipo, resumo, severidade,
  resultado, tratamento, modo, preset, potência, proteção, audibilidade e
  confirmação;
- informar `complete`, `incomplete`, `blocked`, `no_action`, `timeout` ou
  `external` como estado do fluxo;
- limitar a resposta sem perder o primeiro gatilho nem o último resultado.

Fases semânticas esperadas:

1. **Gatilho recebido**;
2. **Supervisor avaliou**;
3. **Decisão calculada ou bloqueada**;
4. **Ação, transmissão, supressão ou nenhuma ação**;
5. **Confirmação, timeout, alteração externa ou resultado pendente**.

No frontend:

- criar cartões somente para fases realmente presentes; não preencher o bloco
  com cinco cartões genéricos;
- quando for importante explicar uma correlação incompleta, listar as fases
  ausentes em um único aviso compacto `Não registradas: ...`;
- usar **Último fluxo completo** somente quando houver resultado terminal;
- usar **Último fluxo observado** quando estiver incompleto;
- mostrar horário, tratamento/modo e desfecho no cabeçalho do bloco;
- incluir conteúdo útil e específico em cada etapa, em vez de cinco rótulos
  fixos;
- tornar cada fase clicável para abrir o evento correspondente;
- incluir ação para abrir toda a correlação na Linha do tempo;
- quando não houver correlação, usar um estado vazio compacto em vez de cinco
  caixas;
- atualizar o resumo de forma leve e com debounce ao receber evento relevante
  enquanto o Panorama estiver ativo, sem inserir linhas, trocar aba, perder
  scroll ou modificar filtros.

### 7. Compatibilidade, versão e instalação

- Preservar consulta de eventos antigos e filtros salvos com valores canônicos.
- Não apagar histórico; somente executar as migrações semânticas idempotentes
  definidas acima.
- Se houver bump de schema, atualizar migrations e teste de segundo restart.
- Atualizar `VERSION`, `manifest.json`, build do JavaScript e URL do recurso
  para `1.0.3` apenas após todos os itens passarem.
- Recriar `Implementações/elgin_supervisor_diagnostico_instalacao.zip` e
  atualizar o guia.
- Não reiniciar Home Assistant nem instalar na aplicação real automaticamente.

## Testes mínimos obrigatórios

Executar somente testes direcionados:

1. **Python puro — severidade:** um exemplo por nível, proteção contra rebaixar
   transmissão/externo/erro e migração idempotente de linhas `info` conhecidas.
2. **Python puro — potência:** `Fraco` permanece perfil; booleanos e
   `0/1/on/off` não entram em `power_profile`; backfill só usa evidência
   inequívoca.
3. **Python/storage — facetas:** contagens respeitam os outros filtros, excluem
   o próprio campo e preservam opções selecionáveis.
4. **Python/storage — fluxo:** anchor mais recente vence confirmação antiga,
   fallback SQLite após deque vazio e classificação de completo/incompleto.
5. **Frontend smoke:** apenas um picker aberto, clique externo, troca de picker,
   `Escape`, rótulos portugueses, potência formatada e fluxo vazio/completo.
6. `node --check`, `python -m compileall`, JSON do manifesto, YAML válido,
   `git diff --check` e teste estrutural garantindo que o package mudou somente
   dentro de eventos diagnósticos.

Não repetir suíte de volume, testes físicos ou regressão completa do Supervisor
nesta etapa visual/semântica. Não compilar ESPHome porque nenhum arquivo ESPHome
deve mudar.

## Critérios de aceite

- O filtro de severidade mostra os seis níveis em português e em ordem fixa.
- Eventos rotineiros deixam de dominar `Informação`, inclusive no histórico
  migrado.
- As contagens refletem o recorte aplicado e têm formatação `pt-BR`.
- Potência não oferece `0`, `1`, booleanos ou estados liga/desliga como perfil.
- Cada perfil exibido é compreensível sem consultar JSON técnico.
- Abrir outro seletor, clicar fora, usar `Tab` ou `Escape` fecha corretamente o
  popup anterior.
- Nenhum listener permanece após remover/recarregar o card.
- Métricas, filtros, chips e detalhes usam português consistente; códigos crus
  ficam restritos ao modo técnico.
- O último fluxo muda quando surge correlação mais recente, explica o desfecho
  real e abre seus eventos/correlação.
- Nenhuma mudança desta etapa chama Climate, LocalTuya, ESPHome, transmite IR ou
  altera a decisão climática.

## Entrega e rollback

Na entrega, informar arquivos alterados, testes executados, hash do ZIP,
instalação e riscos restantes. A instalação real será manual pelo usuário.

Rollback:

1. restaurar o componente e o package `1.0.2` pelo backup/Git;
2. restaurar o banco pelo backup somente com Home Assistant parado caso a
   migração já tenha sido aplicada;
3. retornar o recurso frontend para `?v=1.0.2`;
4. reiniciar manualmente e confirmar que Supervisor, transmissão IR e
   LocalTuya continuam operando como antes.
