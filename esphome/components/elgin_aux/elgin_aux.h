#pragma once

#include <cstdint>
#include <string>

#include "elgin_aux_protocol.h"
#include "esphome/components/binary_sensor/binary_sensor.h"
#include "esphome/components/climate/climate.h"
#include "esphome/components/remote_transmitter/remote_transmitter.h"
#include "esphome/core/component.h"

namespace esphome {
namespace elgin_aux {

class ElginAuxComponent : public climate::Climate, public Component {
 public:
  void set_run_self_test(bool run_self_test) { this->run_self_test_ = run_self_test; }
  void set_transmitter(remote_transmitter::RemoteTransmitterComponent *transmitter) {
    this->transmitter_ = transmitter;
  }
  void set_state_valid_sensor(binary_sensor::BinarySensor *sensor) {
    this->state_valid_sensor_ = sensor;
  }

  void setup() override;
  void dump_config() override;

  // Envia um frame já codificado e validado usando o remote_transmitter do ESPHome.
  bool transmit_frame(const Frame &frame);

  // Estado fixo usado para validar fisicamente o primeiro frame gerado.
  bool send_reference_state();

  // Compositor atômico usado pelas ações personalizadas da API nativa.
  bool send_state_from_api(bool power, const std::string &mode, const std::string &fan,
                           int target_temperature, int current_temperature, bool ifeel,
                           bool swing_vertical, bool swing_horizontal, bool turbo,
                           bool sleep, bool health, const std::string &command);

  // Alterna o visor da evaporadora. O protocolo não informa o estado final,
  // portanto esta função é exposta como comando momentâneo, não como switch.
  bool send_display_toggle_from_api();

  // Inicia o ciclo Clean usando o frame especial capturado com o aparelho desligado.
  bool send_clean_from_api();

  // Atualiza exclusivamente a temperatura remota usando SensorUpdate.
  bool send_sensor_temperature_update_from_api(int current_temperature);

  // Importa o estado físico observado pelo LocalTuya.
  //
  // Este método NÃO transmite IR. Ele reconstrói um frame-base coerente,
  // atualiza o estado interno do protocolo e publica o Climate.
  //
  // I Feel e Turbo só são substituídos quando advanced_values_authoritative
  // for verdadeiro. Sleep e Health são observados diretamente pelo LocalTuya.
  bool import_observed_state_from_api(
      bool power, const std::string &mode, const std::string &fan,
      int target_temperature, int current_temperature,
      bool swing_vertical, bool swing_horizontal,
      bool sleep, bool health,
      bool advanced_values_authoritative, bool ifeel, bool turbo);

  const std::string &get_last_error() const { return this->last_error_; }
  bool has_valid_full_state() const { return this->has_last_full_state_frame_; }

 protected:
  climate::ClimateTraits traits() override;
  void control(const climate::ClimateCall &call) override;

  bool fail_(const std::string &message);
  static std::string normalize_token_(const std::string &value);
  static bool parse_mode_(const std::string &value, Mode &mode);
  static bool parse_fan_(const std::string &value, Fan &fan);
  static bool parse_command_(const std::string &value, Command &command);

  static bool protocol_mode_from_climate_(climate::ClimateMode source, Mode &destination);
  static climate::ClimateMode climate_mode_from_protocol_(Mode source);
  static bool protocol_fan_from_climate_(climate::ClimateFanMode source, Fan &destination);
  static climate::ClimateFanMode climate_fan_from_protocol_(Fan source);
  static void protocol_swing_from_climate_(climate::ClimateSwingMode source,
                                           bool &vertical, bool &horizontal);
  static climate::ClimateSwingMode climate_swing_from_protocol_(bool vertical,
                                                                 bool horizontal);

  void initialize_default_state_();
  void sync_protocol_state_from_climate_();
  void sync_climate_from_protocol_state_(bool publish);
  void commit_full_state_(const State &state, const Frame &frame);
  void publish_state_valid_(bool valid);

  remote_transmitter::RemoteTransmitterComponent *transmitter_{nullptr};
  binary_sensor::BinarySensor *state_valid_sensor_{nullptr};

  bool run_self_test_{true};
  bool self_test_executed_{false};
  bool self_test_ok_{false};
  uint16_t self_test_passed_{0};
  uint16_t self_test_total_{0};
  const char *self_test_first_failed_{nullptr};

  State current_state_{};
  Frame last_full_state_frame_{};
  bool has_last_full_state_frame_{false};

  std::string last_error_{};
};

}  // namespace elgin_aux
}  // namespace esphome
