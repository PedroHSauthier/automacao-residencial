#include "elgin_aux.h"

#include <algorithm>
#include <cctype>
#include <cmath>

#include "esphome/core/log.h"

namespace esphome {
namespace elgin_aux {

static const char *const TAG = "elgin_aux";
static constexpr uint32_t ELGIN_CARRIER_FREQUENCY = 38000;

void ElginAuxComponent::initialize_default_state_() {
  this->current_state_ = State{};
  this->current_state_.power = false;
  this->current_state_.mode = Mode::MODE_COOL;
  this->current_state_.fan = Fan::SPEED_LOW;
  this->current_state_.target_temperature_valid = true;
  this->current_state_.target_temperature = 24;
  this->current_state_.swing_vertical = false;
  this->current_state_.swing_horizontal = false;
  this->current_state_.ifeel = true;
  this->current_state_.sensor_temperature = 20;
  this->current_state_.turbo = false;
  this->current_state_.sleep = false;
  this->current_state_.health = false;
  this->current_state_.clean = false;
  this->current_state_.command = Command::CMD_POWER;
}

void ElginAuxComponent::setup() {
  this->initialize_default_state_();
  this->has_last_full_state_frame_ = false;
  this->publish_state_valid_(false);
  this->sync_climate_from_protocol_state_(false);

  if (this->transmitter_ == nullptr) {
    ESP_LOGE(TAG, "Remote Transmitter não foi configurado.");
    this->mark_failed();
    return;
  }

  if (this->run_self_test_) {
    const SelfTestResult result = ElginAuxProtocol::run_self_test();
    this->self_test_executed_ = true;
    this->self_test_ok_ = result.ok();
    this->self_test_passed_ = result.passed;
    this->self_test_total_ = result.total;
    this->self_test_first_failed_ = result.first_failed;

    if (!this->self_test_ok_)
      this->mark_failed();
  }

  auto restored = this->restore_state_();
  if (restored.has_value()) {
    restored->apply(this);
    this->sync_protocol_state_from_climate_();
    ESP_LOGI(TAG,
             "Estado básico do climate restaurado sem transmissão IR; funções avançadas "
             "permanecem nos valores seguros até o próximo estado completo.");
  } else {
    this->publish_state();
  }
}

void ElginAuxComponent::dump_config() {
  ESP_LOGCONFIG(TAG, "Elgin AUX HJQI12C2WD:");
  ESP_LOGCONFIG(TAG, "  Encoder/decoder: 104 bits, 13 bytes, LSB-first");
  ESP_LOGCONFIG(TAG, "  Transmissor IR configurado: %s", YESNO(this->transmitter_ != nullptr));
  ESP_LOGCONFIG(TAG, "  Portadora: 38 kHz");
  ESP_LOGCONFIG(TAG, "  Compositor de estado pela API: YES");
  ESP_LOGCONFIG(TAG, "  Atualização silenciosa da temperatura pela API: YES");
  ESP_LOGCONFIG(TAG, "  Importação passiva LocalTuya sem IR: YES");
  ESP_LOGCONFIG(TAG, "  Alternância do visor pela API: YES");
  ESP_LOGCONFIG(TAG, "  Clean pela API: YES");
  ESP_LOGCONFIG(TAG, "  Climate próprio: YES");
  ESP_LOGCONFIG(TAG, "  Diagnóstico de estado-base: %s",
                YESNO(this->state_valid_sensor_ != nullptr));
  ESP_LOGCONFIG(TAG, "  Estado-base válido após o boot: %s",
                YESNO(this->has_last_full_state_frame_));
  ESP_LOGCONFIG(TAG, "  Autoteste no boot: %s", YESNO(this->run_self_test_));

  if (!this->run_self_test_) {
    ESP_LOGCONFIG(TAG, "  Resultado do autoteste: DESATIVADO");
  } else if (!this->self_test_executed_) {
    ESP_LOGW(TAG, "Resultado do autoteste: PENDENTE");
  } else if (this->self_test_ok_) {
    ESP_LOGCONFIG(TAG, "  Resultado do autoteste: APROVADO (%u/%u vetores)",
                  this->self_test_passed_, this->self_test_total_);
  } else {
    ESP_LOGE(TAG, "Resultado do autoteste: FALHOU (%u/%u). Primeiro erro: %s",
             this->self_test_passed_, this->self_test_total_,
             this->self_test_first_failed_ == nullptr ? "desconhecido"
                                                      : this->self_test_first_failed_);
  }

  LOG_CLIMATE("  ", "Elgin AUX", this);
  this->dump_traits_(TAG);
}

climate::ClimateTraits ElginAuxComponent::traits() {
  climate::ClimateTraits traits;
  traits.add_feature_flags(climate::CLIMATE_SUPPORTS_CURRENT_TEMPERATURE);

  traits.add_supported_mode(climate::CLIMATE_MODE_OFF);
  traits.add_supported_mode(climate::CLIMATE_MODE_AUTO);
  traits.add_supported_mode(climate::CLIMATE_MODE_COOL);
  traits.add_supported_mode(climate::CLIMATE_MODE_HEAT);
  traits.add_supported_mode(climate::CLIMATE_MODE_DRY);
  traits.add_supported_mode(climate::CLIMATE_MODE_FAN_ONLY);

  traits.add_supported_fan_mode(climate::CLIMATE_FAN_AUTO);
  traits.add_supported_fan_mode(climate::CLIMATE_FAN_LOW);
  traits.add_supported_fan_mode(climate::CLIMATE_FAN_MEDIUM);
  traits.add_supported_fan_mode(climate::CLIMATE_FAN_HIGH);

  traits.add_supported_swing_mode(climate::CLIMATE_SWING_OFF);
  traits.add_supported_swing_mode(climate::CLIMATE_SWING_VERTICAL);
  traits.add_supported_swing_mode(climate::CLIMATE_SWING_HORIZONTAL);
  traits.add_supported_swing_mode(climate::CLIMATE_SWING_BOTH);

  traits.set_visual_min_temperature(16.0f);
  traits.set_visual_max_temperature(32.0f);
  traits.set_visual_target_temperature_step(1.0f);
  traits.set_visual_current_temperature_step(1.0f);
  return traits;
}

bool ElginAuxComponent::fail_(const std::string &message) {
  this->last_error_ = message;
  ESP_LOGE(TAG, "%s", message.c_str());
  return false;
}

std::string ElginAuxComponent::normalize_token_(const std::string &value) {
  std::string normalized;
  normalized.reserve(value.size());

  for (const unsigned char character : value) {
    if (character == ' ' || character == '-') {
      normalized.push_back('_');
    } else {
      normalized.push_back(static_cast<char>(std::tolower(character)));
    }
  }

  return normalized;
}

bool ElginAuxComponent::parse_mode_(const std::string &value, Mode &mode) {
  const std::string token = normalize_token_(value);

  if (token == "auto" || token == "automatico") {
    mode = Mode::MODE_AUTO;
    return true;
  }
  if (token == "cool" || token == "frio") {
    mode = Mode::MODE_COOL;
    return true;
  }
  if (token == "dry" || token == "seco" || token == "desumidificar") {
    mode = Mode::MODE_DRY;
    return true;
  }
  if (token == "heat" || token == "quente" || token == "aquecer") {
    mode = Mode::MODE_HEAT;
    return true;
  }
  if (token == "fan" || token == "fan_only" || token == "ventilar" ||
      token == "ventilacao") {
    mode = Mode::MODE_FAN;
    return true;
  }

  return false;
}

bool ElginAuxComponent::parse_fan_(const std::string &value, Fan &fan) {
  const std::string token = normalize_token_(value);

  if (token == "auto" || token == "automatico") {
    fan = Fan::SPEED_AUTO;
    return true;
  }
  if (token == "low" || token == "baixa") {
    fan = Fan::SPEED_LOW;
    return true;
  }
  if (token == "medium" || token == "mid" || token == "media") {
    fan = Fan::SPEED_MEDIUM;
    return true;
  }
  if (token == "high" || token == "alta") {
    fan = Fan::SPEED_HIGH;
    return true;
  }

  return false;
}

bool ElginAuxComponent::parse_command_(const std::string &value, Command &command) {
  const std::string token = normalize_token_(value);

  if (token == "temperature_down" || token == "temp_down" ||
      token == "diminuir_temperatura") {
    command = Command::CMD_TEMPERATURE_DOWN;
    return true;
  }
  if (token == "temperature_up" || token == "temp_up" ||
      token == "aumentar_temperatura") {
    command = Command::CMD_TEMPERATURE_UP;
    return true;
  }
  if (token == "swing_vertical" || token == "oscilar_vertical") {
    command = Command::CMD_SWING_VERTICAL;
    return true;
  }
  if (token == "swing_horizontal" || token == "swing2" ||
      token == "oscilar_horizontal") {
    command = Command::CMD_SWING_HORIZONTAL;
    return true;
  }
  if (token == "fan" || token == "velocidade") {
    command = Command::CMD_FAN;
    return true;
  }
  if (token == "power" || token == "energia" || token == "ligar" ||
      token == "desligar") {
    command = Command::CMD_POWER;
    return true;
  }
  if (token == "mode" || token == "modo" || token == "funcao") {
    command = Command::CMD_MODE;
    return true;
  }
  if (token == "health" || token == "ionair") {
    command = Command::CMD_HEALTH;
    return true;
  }
  if (token == "turbo") {
    command = Command::CMD_TURBO;
    return true;
  }
  if (token == "sleep" || token == "dormir") {
    command = Command::CMD_SLEEP;
    return true;
  }
  if (token == "display" || token == "screen" || token == "visor") {
    command = Command::CMD_DISPLAY;
    return true;
  }
  if (token == "clean" || token == "limpar") {
    command = Command::CMD_CLEAN;
    return true;
  }
  if (token == "ifeel" || token == "comfort" || token == "conforto") {
    command = Command::CMD_IFEEL;
    return true;
  }

  return false;
}

bool ElginAuxComponent::protocol_mode_from_climate_(climate::ClimateMode source,
                                                     Mode &destination) {
  switch (source) {
    case climate::CLIMATE_MODE_AUTO:
      destination = Mode::MODE_AUTO;
      return true;
    case climate::CLIMATE_MODE_COOL:
      destination = Mode::MODE_COOL;
      return true;
    case climate::CLIMATE_MODE_HEAT:
      destination = Mode::MODE_HEAT;
      return true;
    case climate::CLIMATE_MODE_DRY:
      destination = Mode::MODE_DRY;
      return true;
    case climate::CLIMATE_MODE_FAN_ONLY:
      destination = Mode::MODE_FAN;
      return true;
    default:
      return false;
  }
}

climate::ClimateMode ElginAuxComponent::climate_mode_from_protocol_(Mode source) {
  switch (source) {
    case Mode::MODE_AUTO:
      return climate::CLIMATE_MODE_AUTO;
    case Mode::MODE_COOL:
      return climate::CLIMATE_MODE_COOL;
    case Mode::MODE_HEAT:
      return climate::CLIMATE_MODE_HEAT;
    case Mode::MODE_DRY:
      return climate::CLIMATE_MODE_DRY;
    case Mode::MODE_FAN:
      return climate::CLIMATE_MODE_FAN_ONLY;
    default:
      return climate::CLIMATE_MODE_COOL;
  }
}

bool ElginAuxComponent::protocol_fan_from_climate_(climate::ClimateFanMode source,
                                                    Fan &destination) {
  switch (source) {
    case climate::CLIMATE_FAN_AUTO:
      destination = Fan::SPEED_AUTO;
      return true;
    case climate::CLIMATE_FAN_LOW:
      destination = Fan::SPEED_LOW;
      return true;
    case climate::CLIMATE_FAN_MEDIUM:
      destination = Fan::SPEED_MEDIUM;
      return true;
    case climate::CLIMATE_FAN_HIGH:
      destination = Fan::SPEED_HIGH;
      return true;
    default:
      return false;
  }
}

climate::ClimateFanMode ElginAuxComponent::climate_fan_from_protocol_(Fan source) {
  switch (source) {
    case Fan::SPEED_AUTO:
      return climate::CLIMATE_FAN_AUTO;
    case Fan::SPEED_LOW:
      return climate::CLIMATE_FAN_LOW;
    case Fan::SPEED_MEDIUM:
      return climate::CLIMATE_FAN_MEDIUM;
    case Fan::SPEED_HIGH:
      return climate::CLIMATE_FAN_HIGH;
    default:
      return climate::CLIMATE_FAN_LOW;
  }
}

void ElginAuxComponent::protocol_swing_from_climate_(climate::ClimateSwingMode source,
                                                      bool &vertical, bool &horizontal) {
  switch (source) {
    case climate::CLIMATE_SWING_BOTH:
      vertical = true;
      horizontal = true;
      break;
    case climate::CLIMATE_SWING_VERTICAL:
      vertical = true;
      horizontal = false;
      break;
    case climate::CLIMATE_SWING_HORIZONTAL:
      vertical = false;
      horizontal = true;
      break;
    case climate::CLIMATE_SWING_OFF:
    default:
      vertical = false;
      horizontal = false;
      break;
  }
}

climate::ClimateSwingMode ElginAuxComponent::climate_swing_from_protocol_(bool vertical,
                                                                          bool horizontal) {
  if (vertical && horizontal)
    return climate::CLIMATE_SWING_BOTH;
  if (vertical)
    return climate::CLIMATE_SWING_VERTICAL;
  if (horizontal)
    return climate::CLIMATE_SWING_HORIZONTAL;
  return climate::CLIMATE_SWING_OFF;
}

void ElginAuxComponent::sync_protocol_state_from_climate_() {
  this->current_state_.power = this->mode != climate::CLIMATE_MODE_OFF;

  Mode protocol_mode;
  if (this->mode != climate::CLIMATE_MODE_OFF &&
      protocol_mode_from_climate_(this->mode, protocol_mode)) {
    this->current_state_.mode = protocol_mode;
  }

  if (this->fan_mode.has_value()) {
    Fan protocol_fan;
    if (protocol_fan_from_climate_(this->fan_mode.value(), protocol_fan))
      this->current_state_.fan = protocol_fan;
  }

  protocol_swing_from_climate_(this->swing_mode, this->current_state_.swing_vertical,
                               this->current_state_.swing_horizontal);

  if (!std::isnan(this->target_temperature)) {
    const int target = static_cast<int>(std::lround(this->target_temperature));
    if (target >= 16 && target <= 32)
      this->current_state_.target_temperature = static_cast<uint8_t>(target);
  }

  this->current_state_.target_temperature_valid =
      this->current_state_.mode != Mode::MODE_AUTO &&
      this->current_state_.mode != Mode::MODE_FAN;
}

void ElginAuxComponent::sync_climate_from_protocol_state_(bool publish) {
  this->mode = this->current_state_.power
                   ? climate_mode_from_protocol_(this->current_state_.mode)
                   : climate::CLIMATE_MODE_OFF;
  this->target_temperature = static_cast<float>(this->current_state_.target_temperature);
  this->current_temperature = static_cast<float>(this->current_state_.sensor_temperature);
  this->fan_mode = climate_fan_from_protocol_(this->current_state_.fan);
  this->swing_mode = climate_swing_from_protocol_(this->current_state_.swing_vertical,
                                                  this->current_state_.swing_horizontal);
  this->action = this->current_state_.power ? climate::CLIMATE_ACTION_IDLE
                                            : climate::CLIMATE_ACTION_OFF;

  if (publish)
    this->publish_state();
}

void ElginAuxComponent::publish_state_valid_(bool valid) {
  if (this->state_valid_sensor_ != nullptr)
    this->state_valid_sensor_->publish_state(valid);
}

void ElginAuxComponent::commit_full_state_(const State &state, const Frame &frame) {
  this->current_state_ = state;
  this->last_full_state_frame_ = frame;
  this->has_last_full_state_frame_ = true;
  this->sync_climate_from_protocol_state_(true);
  this->publish_state_valid_(true);
  ESP_LOGI(TAG, "Estado-base completo atualizado: VÁLIDO.");
}

bool ElginAuxComponent::transmit_frame(const Frame &frame) {
  this->last_error_.clear();

  if (this->transmitter_ == nullptr)
    return this->fail_("Transmissão cancelada: Remote Transmitter indisponível.");

  if (this->run_self_test_ && (!this->self_test_executed_ || !this->self_test_ok_))
    return this->fail_("Transmissão cancelada: autoteste do protocolo não está aprovado.");

  if (!ElginAuxProtocol::checksum_valid(frame))
    return this->fail_("Transmissão cancelada: assinatura ou checksum inválido.");

  const auto raw = ElginAuxProtocol::to_raw(frame);
  if (raw.size() != ELGIN_RAW_SIZE)
    return this->fail_("Transmissão cancelada: quantidade de tempos raw inválida.");

  ESP_LOGI(TAG,
           "Frame TX: %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X %02X",
           frame[0], frame[1], frame[2], frame[3], frame[4], frame[5], frame[6], frame[7],
           frame[8], frame[9], frame[10], frame[11], frame[12]);

  auto call = this->transmitter_->transmit();
  auto *data = call.get_data();
  data->set_carrier_frequency(ELGIN_CARRIER_FREQUENCY);
  data->set_data(raw);
  call.set_send_times(1);
  call.perform();

  ESP_LOGI(TAG, "Transmissão IR concluída: 1 frame, 104 bits, 38 kHz.");
  return true;
}

bool ElginAuxComponent::send_reference_state() {
  State state;
  state.power = true;
  state.mode = Mode::MODE_COOL;
  state.fan = Fan::SPEED_LOW;
  state.target_temperature_valid = true;
  state.target_temperature = 24;
  state.swing_vertical = false;
  state.swing_horizontal = false;
  state.ifeel = true;
  state.sensor_temperature = 20;
  state.turbo = false;
  state.sleep = false;
  state.health = false;
  state.clean = false;
  state.command = Command::CMD_IFEEL;

  Frame frame{};
  if (!ElginAuxProtocol::encode(state, frame))
    return this->fail_("Falha ao codificar o estado de referência.");

  ESP_LOGI(TAG, "Enviando estado de referência: ON, Cool, Low, alvo 24°C, sensor 20°C, IFeel ON.");
  if (!this->transmit_frame(frame))
    return false;

  this->commit_full_state_(state, frame);
  return true;
}

bool ElginAuxComponent::send_state_from_api(bool power, const std::string &mode_text,
                                             const std::string &fan_text, int target_temperature,
                                             int current_temperature, bool ifeel, bool swing_vertical,
                                             bool swing_horizontal, bool turbo, bool sleep, bool health,
                                             const std::string &command_text) {
  this->last_error_.clear();

  State state;

  if (!parse_mode_(mode_text, state.mode))
    return this->fail_("Modo inválido. Use: auto, cool, dry, heat ou fan.");

  if (!parse_fan_(fan_text, state.fan))
    return this->fail_("Velocidade inválida. Use: auto, low, medium ou high.");

  if (!parse_command_(command_text, state.command))
    return this->fail_("Comando inválido. Consulte a lista de command do componente.");

  state.power = power;
  state.target_temperature_valid = state.mode != Mode::MODE_AUTO && state.mode != Mode::MODE_FAN;

  if (state.target_temperature_valid && (target_temperature < 16 || target_temperature > 32))
    return this->fail_("Temperatura-alvo inválida. Faixa permitida: 16 a 32 °C.");
  state.target_temperature = static_cast<uint8_t>(target_temperature);

  state.ifeel = ifeel;
  if (ifeel && (current_temperature < 0 || current_temperature > 50))
    return this->fail_("Temperatura atual inválida. Faixa permitida com IFeel: 0 a 50 °C.");
  state.sensor_temperature = static_cast<uint8_t>(current_temperature);

  state.swing_vertical = swing_vertical;
  state.swing_horizontal = swing_horizontal;
  state.turbo = turbo;
  state.sleep = sleep;
  state.health = health;
  state.clean = false;

  if (turbo && state.fan != Fan::SPEED_HIGH)
    return this->fail_("Combinação inválida: Turbo exige fan high.");

  Frame frame{};
  if (!ElginAuxProtocol::encode(state, frame))
    return this->fail_("O estado solicitado não pôde ser codificado.");

  ESP_LOGI(TAG,
           "Estado solicitado: power=%s mode=%s fan=%s alvo=%d°C atual=%d°C ifeel=%s "
           "swing_v=%s swing_h=%s turbo=%s sleep=%s health=%s command=%s",
           YESNO(power), mode_text.c_str(), fan_text.c_str(), target_temperature,
           current_temperature, YESNO(ifeel), YESNO(swing_vertical), YESNO(swing_horizontal),
           YESNO(turbo), YESNO(sleep), YESNO(health), command_text.c_str());

  if (!this->transmit_frame(frame))
    return false;

  this->commit_full_state_(state, frame);
  return true;
}

bool ElginAuxComponent::send_display_toggle_from_api() {
  this->last_error_.clear();

  if (!this->has_last_full_state_frame_)
    return this->fail_(
        "Visor bloqueado: envie primeiro um estado completo após o boot.");

  if (!this->current_state_.power)
    return this->fail_(
        "Visor bloqueado: o aparelho precisa estar ligado no Climate.");

  State state = this->current_state_;
  state.clean = false;
  state.command = Command::CMD_DISPLAY;

  Frame frame{};
  if (!ElginAuxProtocol::encode(state, frame))
    return this->fail_("Falha ao codificar o comando de alternância do visor.");

  ESP_LOGI(TAG,
           "Alternância do visor solicitada: comando momentâneo; o estado final do visor "
           "não é reportado pelo protocolo.");

  if (!this->transmit_frame(frame))
    return false;

  this->commit_full_state_(state, frame);
  return true;
}

bool ElginAuxComponent::send_clean_from_api() {
  this->last_error_.clear();

  if (!this->has_last_full_state_frame_)
    return this->fail_(
        "Clean bloqueado: desligue o aparelho pelo Climate após o boot e tente novamente.");

  if (this->current_state_.power)
    return this->fail_(
        "Clean bloqueado: desligue primeiro o aparelho pelo Climate.");

  State clean_state;
  clean_state.power = false;
  clean_state.mode = Mode::MODE_COOL;
  clean_state.fan = Fan::SPEED_HIGH;
  clean_state.target_temperature_valid = true;
  clean_state.target_temperature = 24;
  clean_state.swing_vertical = false;
  clean_state.swing_horizontal = false;
  clean_state.ifeel = false;
  clean_state.sensor_temperature = 0;
  clean_state.turbo = true;
  clean_state.sleep = false;
  clean_state.health = false;
  clean_state.clean = true;
  clean_state.command = Command::CMD_CLEAN;

  Frame frame{};
  if (!ElginAuxProtocol::encode(clean_state, frame))
    return this->fail_("Falha ao codificar o frame especial de Clean.");

  ESP_LOGI(TAG,
           "Clean solicitado: aparelho desligado, frame especial independente.");

  if (!this->transmit_frame(frame))
    return false;

  this->current_state_.power = false;
  this->current_state_.clean = false;
  this->has_last_full_state_frame_ = false;
  this->last_full_state_frame_.fill(0);
  this->publish_state_valid_(false);
  this->sync_climate_from_protocol_state_(true);

  ESP_LOGI(TAG,
           "Clean transmitido. Estado-base invalidado até o próximo comando completo.");
  return true;
}

bool ElginAuxComponent::import_observed_state_from_api(
    bool power, const std::string &mode_text, const std::string &fan_text,
    int target_temperature, int current_temperature,
    bool swing_vertical, bool swing_horizontal,
    bool sleep, bool health,
    bool advanced_values_authoritative, bool ifeel, bool turbo) {
  this->last_error_.clear();

  State observed = this->current_state_;

  if (!parse_mode_(mode_text, observed.mode))
    return this->fail_(
        "Importação passiva cancelada: modo observado inválido.");

  if (!parse_fan_(fan_text, observed.fan))
    return this->fail_(
        "Importação passiva cancelada: ventilação observada inválida.");

  observed.power = power;
  observed.target_temperature_valid =
      observed.mode != Mode::MODE_AUTO && observed.mode != Mode::MODE_FAN;

  if (observed.target_temperature_valid &&
      (target_temperature < 16 || target_temperature > 32)) {
    return this->fail_(
        "Importação passiva cancelada: temperatura-alvo fora de 16 a 32 °C.");
  }

  if (target_temperature >= 16 && target_temperature <= 32)
    observed.target_temperature = static_cast<uint8_t>(target_temperature);

  if (current_temperature < 0 || current_temperature > 50)
    return this->fail_(
        "Importação passiva cancelada: temperatura atual fora de 0 a 50 °C.");

  observed.sensor_temperature = static_cast<uint8_t>(current_temperature);
  observed.swing_vertical = swing_vertical;
  observed.swing_horizontal = swing_horizontal;
  observed.sleep = sleep;
  observed.health = health;
  observed.clean = false;
  observed.command = Command::CMD_POWER;

  if (advanced_values_authoritative) {
    observed.ifeel = ifeel;
    observed.turbo = turbo;
  }

  // O estado físico de ventilação é mais confiável que a hipótese de Turbo.
  // O protocolo não permite Turbo com fan diferente de High.
  if (observed.turbo && observed.fan != Fan::SPEED_HIGH) {
    ESP_LOGW(TAG,
             "Importação passiva: Turbo foi descartado porque o LocalTuya "
             "observou fan diferente de high.");
    observed.turbo = false;
  }

  // Ao observar o aparelho desligado, Turbo não deve permanecer no frame-base.
  if (!observed.power)
    observed.turbo = false;

  Frame reconstructed{};
  if (!ElginAuxProtocol::encode(observed, reconstructed))
    return this->fail_(
        "Importação passiva cancelada: não foi possível reconstruir o frame-base.");

  // Deliberadamente não chama transmit_frame().
  this->current_state_ = observed;
  this->last_full_state_frame_ = reconstructed;
  this->has_last_full_state_frame_ = true;
  this->sync_climate_from_protocol_state_(true);
  this->publish_state_valid_(true);

  ESP_LOGI(
      TAG,
      "Estado observado importado SEM IR: power=%s mode=%s fan=%s "
      "alvo=%d°C atual=%d°C swing_v=%s swing_h=%s sleep=%s health=%s "
      "ifeel=%s turbo=%s.",
      YESNO(power), mode_text.c_str(), fan_text.c_str(),
      target_temperature, current_temperature,
      YESNO(swing_vertical), YESNO(swing_horizontal),
      YESNO(sleep), YESNO(health),
      YESNO(observed.ifeel), YESNO(observed.turbo));
  ESP_LOGI(TAG, "Estado-base reconstruído pelo LocalTuya: VÁLIDO, nenhum IR enviado.");
  return true;
}

bool ElginAuxComponent::send_sensor_temperature_update_from_api(int current_temperature) {
  this->last_error_.clear();

  if (current_temperature < 0 || current_temperature > 50)
    return this->fail_("Temperatura atual inválida. Faixa permitida: 0 a 50 °C.");

  if (!this->has_last_full_state_frame_)
    return this->fail_(
        "Atualização silenciosa bloqueada: envie primeiro um estado completo após o boot.");

  const Frame &base = this->last_full_state_frame_;

  Frame frame{};
  if (!ElginAuxProtocol::encode_sensor_update(base,
                                               static_cast<uint8_t>(current_temperature), frame))
    return this->fail_("Falha ao codificar a atualização silenciosa da temperatura.");

  ESP_LOGI(TAG,
           "Atualização silenciosa solicitada: temperatura atual=%d°C; demais campos serão "
           "ignorados pelo aparelho.",
           current_temperature);

  if (!this->transmit_frame(frame))
    return false;

  this->current_state_.sensor_temperature = static_cast<uint8_t>(current_temperature);
  this->current_temperature = static_cast<float>(current_temperature);
  this->publish_state();
  return true;
}

void ElginAuxComponent::control(const climate::ClimateCall &call) {
  this->last_error_.clear();

  State next = this->current_state_;
  Command selected_command = next.command;
  int command_priority = -1;
  bool has_request = false;

  const auto select_command = [&](Command command, int priority) {
    if (priority > command_priority) {
      selected_command = command;
      command_priority = priority;
    }
  };

  if (call.get_mode().has_value()) {
    has_request = true;
    const climate::ClimateMode requested_mode = *call.get_mode();

    if (requested_mode == climate::CLIMATE_MODE_OFF) {
      next.power = false;
      select_command(Command::CMD_POWER, 100);
    } else {
      Mode protocol_mode;
      if (!protocol_mode_from_climate_(requested_mode, protocol_mode)) {
        this->fail_("Climate recebeu um modo não suportado.");
        this->sync_climate_from_protocol_state_(true);
        return;
      }

      const bool was_off = !next.power;
      const bool mode_changed = next.mode != protocol_mode;
      next.power = true;
      next.mode = protocol_mode;

      if (was_off)
        select_command(Command::CMD_POWER, 100);
      else if (mode_changed)
        select_command(Command::CMD_MODE, 80);
      else
        select_command(Command::CMD_MODE, 20);
    }
  }

  if (call.get_fan_mode().has_value()) {
    has_request = true;
    Fan protocol_fan;
    if (!protocol_fan_from_climate_(*call.get_fan_mode(), protocol_fan)) {
      this->fail_("Climate recebeu uma ventilação não suportada.");
      this->sync_climate_from_protocol_state_(true);
      return;
    }
    next.fan = protocol_fan;
    select_command(Command::CMD_FAN, 60);
  }

  if (call.get_swing_mode().has_value()) {
    has_request = true;
    const bool old_vertical = next.swing_vertical;
    const bool old_horizontal = next.swing_horizontal;
    protocol_swing_from_climate_(*call.get_swing_mode(), next.swing_vertical,
                                 next.swing_horizontal);

    if (old_vertical != next.swing_vertical)
      select_command(Command::CMD_SWING_VERTICAL, 50);
    else if (old_horizontal != next.swing_horizontal)
      select_command(Command::CMD_SWING_HORIZONTAL, 50);
    else
      select_command(Command::CMD_SWING_VERTICAL, 20);
  }

  if (call.get_target_temperature().has_value()) {
    has_request = true;
    const int requested_target =
        static_cast<int>(std::lround(*call.get_target_temperature()));

    if (requested_target < 16 || requested_target > 32) {
      this->fail_("Climate recebeu temperatura-alvo fora da faixa de 16 a 32 °C.");
      this->sync_climate_from_protocol_state_(true);
      return;
    }

    if (next.mode == Mode::MODE_AUTO || next.mode == Mode::MODE_FAN) {
      ESP_LOGW(TAG,
               "Temperatura-alvo recebida em Auto/Fan Only; valor foi guardado para o próximo "
               "modo térmico, mas não é aplicado neste modo.");
    }

    const uint8_t old_target = next.target_temperature;
    next.target_temperature = static_cast<uint8_t>(requested_target);
    if (requested_target < old_target)
      select_command(Command::CMD_TEMPERATURE_DOWN, 40);
    else
      select_command(Command::CMD_TEMPERATURE_UP, 40);
  }

  if (!has_request) {
    ESP_LOGW(TAG, "Climate recebeu uma chamada sem campos controláveis.");
    return;
  }

  next.target_temperature_valid =
      next.mode != Mode::MODE_AUTO && next.mode != Mode::MODE_FAN;

  if (next.turbo && next.fan != Fan::SPEED_HIGH) {
    next.turbo = false;
    ESP_LOGW(TAG,
             "Turbo foi desligado automaticamente porque o Climate selecionou ventilação "
             "diferente de High.");
  }

  next.command = selected_command;

  Frame frame{};
  if (!ElginAuxProtocol::encode(next, frame)) {
    this->fail_("O estado solicitado pelo Climate não pôde ser codificado.");
    this->sync_climate_from_protocol_state_(true);
    return;
  }

  ESP_LOGI(TAG,
           "Climate solicitado: power=%s mode=%s fan=%s alvo=%u°C atual=%u°C ifeel=%s "
           "swing_v=%s swing_h=%s turbo=%s sleep=%s health=%s",
           YESNO(next.power),
           LOG_STR_ARG(climate::climate_mode_to_string(
               next.power ? climate_mode_from_protocol_(next.mode)
                          : climate::CLIMATE_MODE_OFF)),
           LOG_STR_ARG(climate::climate_fan_mode_to_string(
               climate_fan_from_protocol_(next.fan))),
           next.target_temperature, next.sensor_temperature, YESNO(next.ifeel),
           YESNO(next.swing_vertical), YESNO(next.swing_horizontal), YESNO(next.turbo),
           YESNO(next.sleep), YESNO(next.health));

  if (!this->transmit_frame(frame)) {
    this->sync_climate_from_protocol_state_(true);
    return;
  }

  this->commit_full_state_(next, frame);
}

}  // namespace elgin_aux
}  // namespace esphome
