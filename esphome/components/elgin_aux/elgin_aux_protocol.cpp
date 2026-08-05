#include "elgin_aux_protocol.h"

namespace esphome {
namespace elgin_aux {

namespace {

constexpr uint8_t SIGNATURE = 0xC3;
constexpr uint8_t TARGET_MIN = 16;
constexpr uint8_t TARGET_MAX = 32;
constexpr uint8_t SENSOR_MAX = 50;
constexpr uint8_t SENSOR_OFFSET = 0x4A;

constexpr int32_t HEADER_MARK_US = 9000;
constexpr int32_t HEADER_SPACE_US = 4500;
constexpr int32_t BIT_MARK_US = 560;
constexpr int32_t ZERO_SPACE_US = 560;
constexpr int32_t ONE_SPACE_US = 1690;
constexpr int32_t FOOTER_MARK_US = 560;

State base_state() {
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
  state.command = Command::CMD_POWER;
  return state;
}

Frame frame_of(std::initializer_list<uint8_t> values) {
  Frame frame{};
  size_t index = 0;
  for (const auto value : values) {
    if (index < frame.size())
      frame[index++] = value;
  }
  return frame;
}

}  // namespace

bool ElginAuxProtocol::mode_valid_(Mode mode) {
  switch (mode) {
    case Mode::MODE_AUTO:
    case Mode::MODE_COOL:
    case Mode::MODE_DRY:
    case Mode::MODE_HEAT:
    case Mode::MODE_FAN:
      return true;
    default:
      return false;
  }
}

bool ElginAuxProtocol::fan_valid_(Fan fan) {
  switch (fan) {
    case Fan::SPEED_HIGH:
    case Fan::SPEED_MEDIUM:
    case Fan::SPEED_LOW:
    case Fan::SPEED_AUTO:
      return true;
    default:
      return false;
  }
}

uint8_t ElginAuxProtocol::checksum(const Frame &frame) {
  uint16_t sum = 0;
  for (size_t index = 0; index < frame.size() - 1; index++)
    sum += frame[index];
  return static_cast<uint8_t>(sum & 0xFF);
}

bool ElginAuxProtocol::checksum_valid(const Frame &frame) {
  return frame[0] == SIGNATURE && frame[12] == checksum(frame);
}

bool ElginAuxProtocol::encode(const State &state, Frame &frame) {
  if (!mode_valid_(state.mode) || !fan_valid_(state.fan))
    return false;

  const bool mode_has_target = state.mode != Mode::MODE_AUTO && state.mode != Mode::MODE_FAN;
  if (mode_has_target) {
    if (!state.target_temperature_valid || state.target_temperature < TARGET_MIN ||
        state.target_temperature > TARGET_MAX)
      return false;
  }

  if (state.ifeel && state.sensor_temperature > SENSOR_MAX)
    return false;

  if (state.turbo && state.fan != Fan::SPEED_HIGH)
    return false;

  // Clean foi capturado somente neste formato específico.
  if (state.clean &&
      (state.power || state.mode != Mode::MODE_COOL || state.fan != Fan::SPEED_HIGH || !state.turbo || state.ifeel))
    return false;

  frame.fill(0);
  frame[0] = SIGNATURE;

  if (mode_has_target)
    frame[1] = static_cast<uint8_t>((state.target_temperature - 8U) << 3U);
  frame[1] |= state.swing_vertical ? 0x00 : 0x07;

  frame[2] = state.swing_horizontal ? 0x00 : 0xE0;
  frame[3] = 0x00;
  frame[4] = static_cast<uint8_t>(state.fan);
  frame[5] = state.turbo ? 0x40 : 0x00;

  frame[6] = static_cast<uint8_t>(state.mode);
  if (state.ifeel)
    frame[6] |= 0x08;
  if (state.sleep)
    frame[6] |= 0x04;

  frame[7] = state.ifeel ? static_cast<uint8_t>(state.sensor_temperature + SENSOR_OFFSET) : 0x00;
  frame[8] = 0x00;

  if (state.power)
    frame[9] |= 0x20;
  if (state.mode == Mode::MODE_HEAT)
    frame[9] |= 0x10;
  if (state.clean)
    frame[9] |= 0x04;
  if (state.health)
    frame[9] |= 0x02;

  frame[10] = 0x00;
  frame[11] = static_cast<uint8_t>(state.command);
  frame[12] = checksum(frame);
  return true;
}

bool ElginAuxProtocol::encode_timer(TimerPreset preset, Frame &frame) {
  frame.fill(0);

  switch (preset) {
    case TimerPreset::PRESET_OFF_30_MINUTES:
      frame = frame_of({0xC3, 0x97, 0x00, 0x00, 0x40, 0x1E, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0x00});
      break;
    case TimerPreset::PRESET_OFF_1_HOUR:
      frame = frame_of({0xC3, 0x97, 0x00, 0x00, 0x41, 0x00, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0x00});
      break;
    default:
      return false;
  }

  frame[12] = checksum(frame);
  return true;
}

bool ElginAuxProtocol::encode_sensor_update(const Frame &base_frame, uint8_t sensor_temperature, Frame &frame) {
  if (!checksum_valid(base_frame) || sensor_temperature > SENSOR_MAX)
    return false;

  frame = base_frame;
  frame[3] |= 0x40;  // SensorUpdate: o aparelho considera somente o byte da temperatura e não emite bip.
  frame[7] = static_cast<uint8_t>(sensor_temperature + SENSOR_OFFSET);
  frame[12] = checksum(frame);
  return true;
}

bool ElginAuxProtocol::decode(const Frame &frame, DecodedFrame &decoded) {
  if (!checksum_valid(frame))
    return false;

  const Frame timer_30 =
      frame_of({0xC3, 0x97, 0x00, 0x00, 0x40, 0x1E, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0xCB});
  const Frame timer_60 =
      frame_of({0xC3, 0x97, 0x00, 0x00, 0x41, 0x00, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0xAE});

  if (frame == timer_30) {
    decoded.kind = FrameKind::KIND_TIMER_OFF_30_MINUTES;
    return true;
  }
  if (frame == timer_60) {
    decoded.kind = FrameKind::KIND_TIMER_OFF_1_HOUR;
    return true;
  }

  decoded.kind = static_cast<Command>(frame[11]) == Command::CMD_TIMER ? FrameKind::KIND_UNKNOWN_SPECIAL
                                                                   : FrameKind::KIND_NORMAL;

  State &state = decoded.state;

  switch (frame[6] & 0xE0) {
    case 0x00:
      state.mode = Mode::MODE_AUTO;
      break;
    case 0x20:
      state.mode = Mode::MODE_COOL;
      break;
    case 0x40:
      state.mode = Mode::MODE_DRY;
      break;
    case 0x80:
      state.mode = Mode::MODE_HEAT;
      break;
    case 0xC0:
      state.mode = Mode::MODE_FAN;
      break;
    default:
      return false;
  }

  switch (frame[4] & 0xE0) {
    case 0x20:
      state.fan = Fan::SPEED_HIGH;
      break;
    case 0x40:
      state.fan = Fan::SPEED_MEDIUM;
      break;
    case 0x60:
      state.fan = Fan::SPEED_LOW;
      break;
    case 0xA0:
      state.fan = Fan::SPEED_AUTO;
      break;
    default:
      return false;
  }

  state.target_temperature_valid = state.mode != Mode::MODE_AUTO && state.mode != Mode::MODE_FAN;
  if (state.target_temperature_valid) {
    state.target_temperature = static_cast<uint8_t>((frame[1] >> 3U) + 8U);
    if (state.target_temperature < TARGET_MIN || state.target_temperature > TARGET_MAX)
      return false;
  } else {
    state.target_temperature = 0;
  }

  state.swing_vertical = (frame[1] & 0x07) == 0x00;
  state.swing_horizontal = (frame[2] & 0xE0) == 0x00;
  state.ifeel = (frame[6] & 0x08) != 0;
  state.sleep = (frame[6] & 0x04) != 0;

  if (state.ifeel) {
    if (frame[7] < SENSOR_OFFSET)
      return false;
    state.sensor_temperature = static_cast<uint8_t>(frame[7] - SENSOR_OFFSET);
    if (state.sensor_temperature > SENSOR_MAX)
      return false;
  } else {
    state.sensor_temperature = 0;
  }

  state.power = (frame[9] & 0x20) != 0;
  state.clean = (frame[9] & 0x04) != 0;
  state.health = (frame[9] & 0x02) != 0;
  state.turbo = (frame[5] & 0x40) != 0;
  state.command = static_cast<Command>(frame[11]);
  return true;
}

std::vector<int32_t> ElginAuxProtocol::to_raw(const Frame &frame) {
  std::vector<int32_t> raw;
  raw.reserve(ELGIN_RAW_SIZE);
  raw.push_back(HEADER_MARK_US);
  raw.push_back(-HEADER_SPACE_US);

  for (const auto byte : frame) {
    for (uint8_t bit = 0; bit < 8; bit++) {
      raw.push_back(BIT_MARK_US);
      raw.push_back((byte & (1U << bit)) != 0 ? -ONE_SPACE_US : -ZERO_SPACE_US);
    }
  }

  raw.push_back(FOOTER_MARK_US);
  return raw;
}

SelfTestResult ElginAuxProtocol::run_self_test() {
  SelfTestResult result;

  auto register_failure = [&result](const char *name) {
    if (result.first_failed == nullptr)
      result.first_failed = name;
  };

  auto test_state = [&result, &register_failure](const char *name, const State &state, const Frame &expected) {
    result.total++;

    Frame actual{};
    if (!ElginAuxProtocol::encode(state, actual) || actual != expected ||
        !ElginAuxProtocol::checksum_valid(actual)) {
      register_failure(name);
      return;
    }

    DecodedFrame decoded{};
    if (!ElginAuxProtocol::decode(actual, decoded) || decoded.kind != FrameKind::KIND_NORMAL) {
      register_failure(name);
      return;
    }

    const auto raw = ElginAuxProtocol::to_raw(actual);
    if (raw.size() != ELGIN_RAW_SIZE) {
      register_failure(name);
      return;
    }

    result.passed++;
  };

  auto test_timer = [&result, &register_failure](const char *name, TimerPreset preset, FrameKind kind,
                                                  const Frame &expected) {
    result.total++;

    Frame actual{};
    DecodedFrame decoded{};
    if (!ElginAuxProtocol::encode_timer(preset, actual) || actual != expected ||
        !ElginAuxProtocol::decode(actual, decoded) || decoded.kind != kind) {
      register_failure(name);
      return;
    }

    result.passed++;
  };

  auto test_sensor_update = [&result, &register_failure](const char *name, const Frame &base,
                                                        uint8_t sensor_temperature, const Frame &expected) {
    result.total++;

    Frame actual{};
    if (!ElginAuxProtocol::encode_sensor_update(base, sensor_temperature, actual) || actual != expected ||
        !ElginAuxProtocol::checksum_valid(actual) || (actual[3] & 0x40) == 0) {
      register_failure(name);
      return;
    }

    result.passed++;
  };

  State state;

  state = base_state();
  state.power = false;
  state.fan = Fan::SPEED_HIGH;
  state.ifeel = false;
  state.turbo = true;
  state.clean = true;
  state.command = Command::CMD_CLEAN;
  test_state("Clean", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x20, 0x40, 0x20, 0x00, 0x00, 0x04, 0x00, 0x19, 0xC7}));

  state = base_state();
  state.power = false;
  state.ifeel = false;
  state.command = Command::CMD_POWER;
  test_state("Power OFF", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x20, 0x00, 0x00, 0x00, 0x00, 0x05, 0xAF}));

  state = base_state();
  state.target_temperature = 32;
  state.command = Command::CMD_MODE;
  test_state("Mode Cool", state, frame_of({0xC3, 0xC7, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x06, 0x76}));

  state = base_state();
  state.mode = Mode::MODE_DRY;
  state.command = Command::CMD_MODE;
  test_state("Mode Dry", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x48, 0x5E, 0x00, 0x20, 0x00, 0x06, 0x56}));

  state = base_state();
  state.mode = Mode::MODE_AUTO;
  state.target_temperature_valid = false;
  state.swing_horizontal = true;
  state.command = Command::CMD_MODE;
  test_state("Mode Auto", state, frame_of({0xC3, 0x07, 0x00, 0x00, 0x60, 0x00, 0x08, 0x5E, 0x00, 0x20, 0x00, 0x06, 0xB6}));

  state = base_state();
  state.mode = Mode::MODE_FAN;
  state.target_temperature_valid = false;
  state.command = Command::CMD_MODE;
  test_state("Mode Fan", state, frame_of({0xC3, 0x07, 0xE0, 0x00, 0x60, 0x00, 0xC8, 0x5E, 0x00, 0x20, 0x00, 0x06, 0x56}));

  state = base_state();
  state.mode = Mode::MODE_HEAT;
  state.swing_horizontal = true;
  state.command = Command::CMD_MODE;
  test_state("Mode Heat", state, frame_of({0xC3, 0x87, 0x00, 0x00, 0x60, 0x00, 0x88, 0x5E, 0x00, 0x30, 0x00, 0x06, 0xC6}));

  state = base_state();
  state.command = Command::CMD_DISPLAY;
  test_state("Display toggle", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x15, 0x45}));

  state = base_state();
  state.ifeel = false;
  state.command = Command::CMD_POWER;
  test_state("Power ON without IFeel", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x20, 0x00, 0x00, 0x20, 0x00, 0x05, 0xCF}));

  state = base_state();
  state.sleep = true;
  state.command = Command::CMD_SLEEP;
  test_state("Sleep", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x2C, 0x5E, 0x00, 0x20, 0x00, 0x0B, 0x3F}));

  state = base_state();
  state.target_temperature = 26;
  state.fan = Fan::SPEED_AUTO;
  state.health = true;
  state.command = Command::CMD_HEALTH;
  test_state("Health", state, frame_of({0xC3, 0x97, 0xE0, 0x00, 0xA0, 0x00, 0x28, 0x5E, 0x00, 0x22, 0x00, 0x07, 0x89}));

  state = base_state();
  state.swing_vertical = true;
  state.command = Command::CMD_SWING_VERTICAL;
  test_state("Swing vertical", state, frame_of({0xC3, 0x80, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x02, 0x2B}));

  state = base_state();
  state.swing_horizontal = true;
  state.command = Command::CMD_SWING_HORIZONTAL;
  test_state("Swing horizontal", state, frame_of({0xC3, 0x87, 0x00, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x03, 0x53}));

  state = base_state();
  state.command = Command::CMD_IFEEL;
  test_state("IFeel", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x1E, 0x4E}));

  const uint8_t temperature_commands[] = {
      0x01, 0x01, 0x01, 0x00, 0x01, 0x00, 0x01, 0x01, 0x01,
      0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
  };
  const Frame temperature_frames[] = {
      frame_of({0xC3, 0x47, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0xF1}),
      frame_of({0xC3, 0x4F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0xF9}),
      frame_of({0xC3, 0x57, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x01}),
      frame_of({0xC3, 0x5F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x08}),
      frame_of({0xC3, 0x67, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x11}),
      frame_of({0xC3, 0x6F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x18}),
      frame_of({0xC3, 0x77, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x21}),
      frame_of({0xC3, 0x7F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x29}),
      frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x31}),
      frame_of({0xC3, 0x8F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x01, 0x39}),
      frame_of({0xC3, 0x97, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x40}),
      frame_of({0xC3, 0x9F, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x48}),
      frame_of({0xC3, 0xA7, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x50}),
      frame_of({0xC3, 0xAF, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x58}),
      frame_of({0xC3, 0xB7, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x60}),
      frame_of({0xC3, 0xBF, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x68}),
      frame_of({0xC3, 0xC7, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x00, 0x70}),
  };

  for (uint8_t temperature = 16; temperature <= 32; temperature++) {
    state = base_state();
    state.target_temperature = temperature;
    state.command = static_cast<Command>(temperature_commands[temperature - 16]);

    static const char *temperature_names[] = {
        "Temperature 16", "Temperature 17", "Temperature 18", "Temperature 19", "Temperature 20",
        "Temperature 21", "Temperature 22", "Temperature 23", "Temperature 24", "Temperature 25",
        "Temperature 26", "Temperature 27", "Temperature 28", "Temperature 29", "Temperature 30",
        "Temperature 31", "Temperature 32",
    };
    test_state(temperature_names[temperature - 16], state, temperature_frames[temperature - 16]);
  }

  test_timer("Timer OFF 30 minutes", TimerPreset::PRESET_OFF_30_MINUTES, FrameKind::KIND_TIMER_OFF_30_MINUTES,
             frame_of({0xC3, 0x97, 0x00, 0x00, 0x40, 0x1E, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0xCB}));
  test_timer("Timer OFF 1 hour", TimerPreset::PRESET_OFF_1_HOUR, FrameKind::KIND_TIMER_OFF_1_HOUR,
             frame_of({0xC3, 0x97, 0x00, 0x00, 0x41, 0x00, 0x48, 0x5E, 0x00, 0x60, 0x00, 0x0D, 0xAE}));

  state = base_state();
  state.fan = Fan::SPEED_LOW;
  state.command = Command::CMD_FAN;
  test_state("Fan Low", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x04, 0x34}));

  state = base_state();
  state.fan = Fan::SPEED_AUTO;
  state.command = Command::CMD_FAN;
  test_state("Fan Auto", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0xA0, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x04, 0x74}));

  state = base_state();
  state.fan = Fan::SPEED_MEDIUM;
  state.command = Command::CMD_FAN;
  test_state("Fan Medium", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x40, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x04, 0x14}));

  state = base_state();
  state.fan = Fan::SPEED_HIGH;
  state.command = Command::CMD_FAN;
  test_state("Fan High", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x20, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x04, 0xF4}));

  state = base_state();
  state.fan = Fan::SPEED_HIGH;
  state.turbo = true;
  state.command = Command::CMD_TURBO;
  test_state("Turbo", state, frame_of({0xC3, 0x87, 0xE0, 0x00, 0x20, 0x40, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x08, 0x38}));

  // Vetor adicional baseado no comportamento documentado do protocolo Electra/AUX:
  // parte de um estado completo válido, ativa SensorUpdate (byte 3, bit 6) e altera somente a temperatura remota.
  const Frame sensor_base =
      frame_of({0xC3, 0x87, 0xE0, 0x00, 0x60, 0x00, 0x28, 0x5E, 0x00, 0x20, 0x00, 0x1E, 0x4E});
  test_sensor_update(
      "Silent sensor update 24C", sensor_base, 24,
      frame_of({0xC3, 0x87, 0xE0, 0x40, 0x60, 0x00, 0x28, 0x62, 0x00, 0x20, 0x00, 0x1E, 0x92}));

  return result;
}

}  // namespace elgin_aux
}  // namespace esphome
