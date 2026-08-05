#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace esphome {
namespace elgin_aux {

constexpr size_t ELGIN_FRAME_SIZE = 13;
constexpr size_t ELGIN_RAW_SIZE = 211;

using Frame = std::array<uint8_t, ELGIN_FRAME_SIZE>;

enum class Mode : uint8_t {
  MODE_AUTO = 0x00,
  MODE_COOL = 0x20,
  MODE_DRY = 0x40,
  MODE_HEAT = 0x80,
  MODE_FAN = 0xC0,
};

enum class Fan : uint8_t {
  SPEED_HIGH = 0x20,
  SPEED_MEDIUM = 0x40,
  SPEED_LOW = 0x60,
  SPEED_AUTO = 0xA0,
};

enum class Command : uint8_t {
  CMD_TEMPERATURE_DOWN = 0x00,
  CMD_TEMPERATURE_UP = 0x01,
  CMD_SWING_VERTICAL = 0x02,
  CMD_SWING_HORIZONTAL = 0x03,
  CMD_FAN = 0x04,
  CMD_POWER = 0x05,
  CMD_MODE = 0x06,
  CMD_HEALTH = 0x07,
  CMD_TURBO = 0x08,
  CMD_SLEEP = 0x0B,
  CMD_TIMER = 0x0D,
  CMD_DISPLAY = 0x15,
  CMD_CLEAN = 0x19,
  CMD_IFEEL = 0x1E,
};

enum class FrameKind : uint8_t {
  KIND_NORMAL,
  KIND_TIMER_OFF_30_MINUTES,
  KIND_TIMER_OFF_1_HOUR,
  KIND_UNKNOWN_SPECIAL,
};

enum class TimerPreset : uint8_t {
  PRESET_OFF_30_MINUTES,
  PRESET_OFF_1_HOUR,
};

struct State {
  bool power{true};
  Mode mode{Mode::MODE_COOL};
  Fan fan{Fan::SPEED_LOW};

  bool target_temperature_valid{true};
  uint8_t target_temperature{24};

  bool swing_vertical{false};
  bool swing_horizontal{false};

  bool ifeel{true};
  uint8_t sensor_temperature{20};

  bool turbo{false};
  bool sleep{false};
  bool health{false};
  bool clean{false};

  Command command{Command::CMD_POWER};
};

struct DecodedFrame {
  FrameKind kind{FrameKind::KIND_NORMAL};
  State state{};
};

struct SelfTestResult {
  uint16_t passed{0};
  uint16_t total{0};
  const char *first_failed{nullptr};

  bool ok() const { return this->passed == this->total; }
};

class ElginAuxProtocol {
 public:
  static bool encode(const State &state, Frame &frame);
  static bool encode_timer(TimerPreset preset, Frame &frame);
  static bool encode_sensor_update(const Frame &base_frame, uint8_t sensor_temperature, Frame &frame);
  static bool decode(const Frame &frame, DecodedFrame &decoded);

  static uint8_t checksum(const Frame &frame);
  static bool checksum_valid(const Frame &frame);
  static std::vector<int32_t> to_raw(const Frame &frame);

  static SelfTestResult run_self_test();

 private:
  static bool mode_valid_(Mode mode);
  static bool fan_valid_(Fan fan);
};

}  // namespace elgin_aux
}  // namespace esphome
