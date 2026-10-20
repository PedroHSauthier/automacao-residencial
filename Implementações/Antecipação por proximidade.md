# Antecipação por proximidade — Agenda 1.2.0

Implementação local e opcional por preset. Os presets existentes recebem a função
desabilitada, preservando o comportamento anterior. A potência continua separada,
com os perfis Fraco / Normal / Forte / Extremo e os perfis personalizados existentes.

## Critérios implementados

A baseline tem início/fim por temperatura em Heat/Cool e por umidade em Dry.
Esta entrega usa essas mesmas condições. Não adiciona um segundo limite de umidade
a Heat/Cool nem um segundo limite de temperatura a Dry; portanto, não implementa
dois critérios combinados por OU dentro de um mesmo preset.

| Modo | Faixa antes do limite normal | Condição mantida |
| --- | --- | --- |
| Cool | início − faixa ≤ temperatura < início | Temperatura em passos de 0,1 °C |
| Heat | início < temperatura ≤ início + faixa | Temperatura em passos de 0,1 °C |
| Dry | início − faixa ≤ umidade < início | Umidade em passos de 1%; temperatura mínima preservada |

Exemplo: Cool com início em 26,0 °C, faixa de 0,5 °C e 10 minutos conta enquanto
25,5 ≤ temperatura < 26,0. Com 10 minutos completos solicita demanda; atingir
26,0 antes disso ativa a demanda normal imediatamente. As proteções de partida
continuam valendo nos dois casos.

Cada preset armazena `proximity.enabled`, `temperature_margin`, `humidity_margin`
e `minutes`. Apenas a margem do critério do modo é aplicada. A faixa deve ser
menor que a histerese; isso evita pedir início em um ponto que já encerra o ciclo.
O tempo é inteiro, de 1 a 1440 minutos. Os limites efetivos incluem offsets da Agenda.
Se esses offsets tornarem a faixa incompatível com a histerese, somente a antecipação
fica indisponível; o motivo aparece no diagnóstico.

A contagem é independente por modo e não é persistida. Reiniciar/recarregar a
integração, sair da faixa, perder uma leitura necessária, desabilitar a função/modo,
bloquear a partida ou mudar o preset/limites aplicáveis inicia uma nova contagem.
Eventos rápidos de saída e retorno também cancelam o tempo anterior. O prazo vence
sem depender de nova atualização do sensor. Entrar em um ciclo preserva a condição
normal de encerramento e não gera retransmissão pelo temporizador.

O contador aparece no Panorama, em Presets e no Diagnóstico do card Presets e
Potência. A atualização visual ocorre no navegador. Apenas a passagem do tempo
restante não gera um novo evento de política. Os snapshots de diagnóstico existentes
já incluem o estado da antecipação nos dados dos presets.

## Arquivos para copiar

Substituir estes arquivos nos mesmos caminhos da instalação real:

- `custom_components/elgin_supervisor_agenda/const.py`
- `custom_components/elgin_supervisor_agenda/frontend/elgin-supervisor-agenda-card.js`
- `custom_components/elgin_supervisor_agenda/manager.py`
- `custom_components/elgin_supervisor_agenda/manifest.json`
- `custom_components/elgin_supervisor_agenda/powers.py`
- `custom_components/elgin_supervisor_agenda/presets.py`
- `custom_components/elgin_supervisor_agenda/services.yaml`
- `packages/elgin_supervisor_climatico.yaml`

Adicionar o novo arquivo:

- `custom_components/elgin_supervisor_agenda/proximity.py`

Este documento e os arquivos de `tests/` são auxiliares de desenvolvimento.
Nenhum arquivo de ESPHome, LocalTuya ou da integração de diagnóstico precisa ser
substituído. O dashboard continua usando os cards existentes.

## Instalação e validação física

1. Criar um backup do Home Assistant, incluindo os dados persistidos da Agenda.
2. Ativar o modo sombra antes da troca dos arquivos. Copiar o conjunto acima.
3. Executar a verificação de configuração do Home Assistant e conferir os IDs reais
   dos sensores e entidades LocalTuya no registro. Não há registro exportado nesta réplica.
4. Após uma verificação válida, reiniciar manualmente o Home Assistant para carregar
   Python e package juntos. Atualizar a página do dashboard. Nenhum reinício foi executado
   durante a implementação e não é necessário recompilar o ESPHome.
5. Confirmar que todos os presets anteriores continuam com antecipação desabilitada
   e que Agenda, presets e potência mostram a mesma revisão de snapshot.
6. No editor de um preset, habilitar a antecipação e definir faixa/tempo. Conferir no
   modo sombra: entrada na faixa, contagem completa, saída e reentrada, leitura
   indisponível, troca de preset, mudança de offset e limite normal antes do prazo.
7. Conferir Heat, Cool e Dry separadamente. Dry deve bloquear a antecipação abaixo
   da temperatura mínima. Alterar a potência não deve herdar nem acumular tempos.
8. Com o resultado em sombra correto, liberar manualmente a transmissão e verificar
   Power ON/OFF, Heat/Cool/Dry, fan, swing, I Feel, pausa manual, mínimos ligado/desligado,
   troca de modo e reconciliação LocalTuya. Importação passiva deve continuar sem IR;
   sem Eco deve haver um bip por comando completo; com Eco em Cool, um bip de IR e um
   de Eco. Heat/Dry não devem tentar ligar Eco.

Os testes locais não substituem esses testes físicos nem a verificação completa do
Home Assistant, indisponível neste ambiente Windows. ESPHome e o transporte IR
permaneceram iguais à baseline, conferidos por revisão e contratos estáticos.
A revisão ampla dos logs e a unificação das demais telas continuam sendo etapas
posteriores; esta entrega integra a nova função às telas existentes.

## Validações locais

Resultado final: **39/39 testes da Agenda aprovados**, incluindo temporizador,
persistência, eventos, templates reais de demanda e integração entre as etapas.
Os testes JavaScript da Agenda e do Diagnóstico passaram. Na suíte de diagnóstico,
**84/85 testes passaram**; a única falha é a de retenção por data descrita abaixo,
reproduzida também antes das alterações.

- `python -X utf8 -m compileall -q custom_components/elgin_supervisor_agenda custom_components/elgin_supervisor_diagnostico`.
- `node --check` nos cards da Agenda e do Diagnóstico, além dos respectivos testes
  de comportamento JavaScript.
- Leitura de seis arquivos YAML sem chaves duplicadas e análise sintática de 953
  templates Jinja. Os testes de contrato também conferem IDs e preservação do fluxo IR.
- Testes da Agenda: `python -X utf8 -B -m unittest discover -s tests/elgin_supervisor_agenda -p 'test_*.py'`.
- Regressões de diagnóstico: `python -X utf8 -B -m unittest discover -s tests/elgin_supervisor_diagnostico -p 'test_*.py'`.
  Há uma falha preexistente no teste de retenção
  `test_statistics_count_distinct_evaluations_and_persist_health_metadata`: ele usa
  eventos fixos de agosto de 2026 e a limpeza os expira com a data atual.

Os testes Python usam PyYAML e Jinja2; essas dependências de validação foram
instaladas somente em diretório temporário, fora do repositório. Não são novos
requisitos da integração.

## Rollback

Para desativar apenas a função, desligar a antecipação nos presets alterados.
Para retornar integralmente, ativar modo sombra, restaurar pelo Git os oito arquivos
substituídos e remover da instalação o novo `proximity.py`; restaurar o backup dos
dados da Agenda se também quiser reverter alterações de configuração feitas após
a instalação. Validar a configuração e reiniciar manualmente. Não restaurar arquivos
de ESPHome ou diagnóstico de outras versões.
