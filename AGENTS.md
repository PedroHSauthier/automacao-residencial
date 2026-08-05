# AGENTS.md

## Projeto

Automação residencial **local-first** do ar-condicionado **Elgin Inverter II Wi-Fi 12.000 BTUs Quente/Frio, modelo HJQI12C2WD**.

O Home Assistant decide o tratamento climático, o ESP8266 transmite o estado completo por infravermelho e o LocalTuya observa o estado físico do aparelho. A automação deve continuar funcional sem depender da nuvem.

## Estado atual do repositório

Este diretório é um **backup de recuperação de uma versão anterior**. Alterações posteriores no ESPHome e no diagnóstico causaram regressões no Supervisor, na transmissão IR e na sincronização de estado.

Regras obrigatórias:

- Trate as imagens dentro da pasta Images como contexto extra para cada prompt.
- Trate os arquivos atuais como a baseline de recuperação.
- Não copie ou mescle automaticamente implementações posteriores.
- A pasta `custom_components/elgin_supervisor_diagnostico_Para_exemplo/` é apenas referência; não é componente de produção.
- Primeiro restaure e valide o fluxo já existente. Novas funcionalidades vêm depois.
- Antes de alterar arquivos ativos, obtenha autorização expressa do usuário.
- Não reinicie o Home Assistant nem o ESPHome automaticamente.

## Hardware e ambiente

- Home Assistant OS em notebook dedicado.
- ESP físico: NodeMCU V3 / ESP8266, compilado como `nodemcuv2`.
- Emissor IR KY-005 no pino `D1`, portadora de 38 kHz e duty de 50%.
- Receptor IR KY-022 no pino `D2`, invertido.
- Ar-condicionado Elgin HJQI12C2WD.
- Protocolo AUX: frame de 104 bits, 13 bytes, transmitido uma vez por comando.
- Roteador Mercusys.
- Estado físico observado por LocalTuya.
- Temperatura e umidade principais vêm dos sensores dedicados do quarto.

Nunca grave credenciais, chaves de API, senhas Wi-Fi ou segredos no repositório.

## Estrutura principal

```text
custom_components/
├── elgin_supervisor_agenda/                  # integração ativa: agenda, presets e potência
└── elgin_supervisor_diagnostico_Para_exemplo/ # referência antiga; não ativar

esphome/
├── esp8266.yaml                              # nó ESPHome e actions da API
└── components/elgin_aux/
    ├── elgin_aux.cpp                         # Climate e transmissão/importação de estado
    ├── elgin_aux.h
    ├── elgin_aux_protocol.cpp                # encoder, decoder e autotestes AUX
    └── elgin_aux_protocol.h

Images/..

packages/
├── elgin_aux_controle.yaml                   # Climate, funções avançadas e LocalTuya
└── elgin_supervisor_climatico.yaml           # decisão, proteções e transmissão automática

www/                                         # recursos frontend ainda utilizados
configuration.yaml                            # inclui packages e configuração principal
Implementações futuras.txt                    # roadmap funcional
```

Use sempre os nomes canônicos sem sufixos numéricos.

## Relação com o projeto real

Com exceção de `AGENTS.md`, `Implementações futuras.txt`, `.gitignore` e das pastas auxiliares iniciadas por letra maiúscula, o conteúdo deste repositório deve ser tratado como uma réplica da estrutura atual do projeto real no Home Assistant e no ESPHome.

Regras para alterações e transferência:

- Trate os arquivos e pastas da réplica como se fossem o projeto real durante análises, correções e validações.
- Quando uma correção exigir mudança em `packages/`, `custom_components/`, `esphome/`, `www/` ou nos arquivos de configuração, deixe somente os arquivos necessários prontos para o usuário copiar e substituir na instalação real.
- Faça sempre a menor alteração necessária e preserve o restante da estrutura e do comportamento existentes.
- Não crie cópias, versões numeradas, arquivos paralelos nem múltiplas instâncias para uma mesma implementação. O histórico e o rollback são responsabilidade do Git.
- O usuário fará manualmente a transferência para o projeto real, a instalação e os testes no Home Assistant ou no ESPHome.
- Não presuma que uma alteração feita nesta réplica já está instalada ou validada no ambiente físico.
- Pastas iniciadas por letra maiúscula são auxiliares deste repositório e não existem como pastas no projeto real.
- `Dashboards/` reúne arquivos YAML que o usuário copia e cola na interface do Home Assistant; esses arquivos não são carregados diretamente de uma pasta da instalação real.
- `Images/` contém imagens usadas como contexto visual e apoio para prompts e análises de erros; não faz parte do conteúdo a ser instalado.

## Contrato entre os componentes

Fluxo esperado:

```text
Sensores + Agenda + Presets + Potência
→ Supervisor calcula tratamento e configuração desejada
→ uma chamada esphome.esp8266_elgin_send_state
→ um único frame IR completo
→ LocalTuya observa o estado físico
→ elgin_import_observed_state atualiza o Climate sem transmitir IR
```

Entidade Climate principal:

```text
climate.esp8266_elgin_aux_quarto
```

Princípios que não podem ser quebrados:

1. **Um estado completo, um frame IR.** Não dividir modo, temperatura, fan ou swing em vários comandos.
2. A importação do LocalTuya é passiva e nunca deve chamar o transmissor.
3. O Climate deve refletir o estado físico observado sem provocar novo bip.
4. Atualização de temperatura I Feel usa `SensorUpdate` silencioso.
5. Eco é separado do frame AUX e só pode ser reconciliado em `cool`.
6. Sem Eco: um bip por comando completo. Com Eco em refrigeração: um bip do IR e um do Eco.
7. Heat e Dry nunca devem tentar ligar Eco.
8. Evitar loops entre Climate, LocalTuya, Supervisor e automações de reconciliação.
9. O Supervisor não pode alterar `tratamento_ativo` antes de uma transmissão confirmada.
10. IDs de entidades devem ser verificados nos arquivos e no registro do Home Assistant; não inferir pelo nome amigável.

Entidades LocalTuya centrais atualmente esperadas:

```text
switch.smart_air_conditioner_power_ar_condicionado_id_1
number.smart_air_conditioner_temperatura_alvo_ar_condicionado_id_2
select.smart_air_conditioner_mode_ar_condicionado_id_4
select.smart_air_conditioner_windspeed_ar_condicionado_id_5
switch.smart_air_conditioner_eco_ar_condicionado_id_8
switch.smart_air_conditioner_swing_ar_condicionado_id_33
switch.smart_air_conditioner_sleep_ar_condicionado_id_102
switch.smart_air_conditioner_up_down_wind_ar_condicionado_id_105
switch.smart_air_conditioner_health_ar_condicionado_id_106
sensor.smart_air_conditioner_fault_up_ar_condicionado_id_107
```

Confirme a existência delas antes de modificar templates ou automações.

## Método de trabalho

Antes de editar:

1. Leia os dois packages, `esp8266.yaml` e o componente C++ completo.
2. Identifique o fluxo exato que será alterado e todos os consumidores da entidade, action ou atributo.
3. Compare a assinatura da action em quatro pontos: YAML do ESPHome, `.h`, `.cpp` e chamadas do Home Assistant.
4. Faça a menor alteração possível; não reestruture subsistemas estáveis durante uma correção.
5. Preserve compatibilidade com as regras e dados persistidos da Agenda.

Validação mínima após alterações:

- YAML válido e sem IDs duplicados.
- `esphome config` e compilação do nó quando o ESPHome mudar.
- `python -m compileall` no custom component.
- `node --check` nos recursos JavaScript.
- Verificação de configuração do Home Assistant.
- Teste em modo sombra antes de liberar transmissão automática.
- Testar Power ON, Power OFF, Heat, Cool, Dry, fan, swing, I Feel e reconciliação LocalTuya.
- Confirmar ausência de IR durante importação passiva.
- Confirmar ausência de comandos duplicados e bips extras.

Toda entrega deve informar arquivos alterados, instalação, validações executadas, riscos restantes e procedimento de rollback.

## Objetivos atuais

1. Manter o Climate Elgin AUX sincronizado com o LocalTuya sem IR de retorno.
2. Garantir que o Supervisor detecte demanda, selecione tratamento e transmita corretamente.
3. Preservar proteções de tempo mínimo, troca de modo, pausa manual e adoção física.
4. Manter Agenda, presets e potência integrados sem bloquear o fluxo por estados transitórios.
5. Evitar múltiplos bips e comandos redundantes.
6. Preservar operação totalmente local e recuperável.

## Implementações futuras

Após a baseline estar validada:

1. Criar auditoria e logs próprios do Supervisor, humanos e detalhados: decisão, origem, bloqueios, comandos, transmissões e resultados.
2. Implementar ventilação pós-ciclo configurável por modo, velocidade e duração.
3. Transformar clima regional em motor dinâmico com card próprio, regras e efeitos sobre preset e potência.
4. Remover helpers e elementos antigos substituídos pelos novos componentes.
5. Criar um card principal coeso, responsivo e visualmente padronizado para o Supervisor.
6. Auditar todas as interconexões entre Agenda, presets, potência, clima regional, Supervisor, ESPHome, Climate e LocalTuya.
7. Executar testes de regressão completos antes de remover qualquer caminho legado.
