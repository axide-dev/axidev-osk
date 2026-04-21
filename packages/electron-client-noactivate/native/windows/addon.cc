#include <windows.h>

#include <node_api.h>

#include <cstdlib>
#include <cstdio>
#include <memory>
#include <mutex>
#include <sstream>
#include <string>
#include <unordered_map>

namespace {

enum class LogLevel {
  kSilent = 0,
  kError = 1,
  kWarn = 2,
  kInfo = 3,
  kDebug = 4,
};

struct HookState {
  WNDPROC previous_proc = nullptr;
  LONG_PTR original_exstyle = 0;
  bool added_noactivate_style = false;
  bool noactivate_enabled = false;
  bool allow_next_activation = false;
  HWND last_external_foreground = nullptr;
};

struct HookSummary {
  int total_windows = 0;
  int changed_windows = 0;
  int already_changed_windows = 0;
  int skipped_foreign_windows = 0;
  int skipped_missing_windows = 0;
  int failed_windows = 0;

  bool installed() const {
    return changed_windows > 0 || already_changed_windows > 0;
  }
};

std::mutex g_hooks_mutex;
std::unordered_map<HWND, std::shared_ptr<HookState>> g_hook_states;
HWINEVENTHOOK g_foreground_hook = nullptr;

constexpr UINT_PTR kRestoreFocusTimerId = 0x41584944;
constexpr UINT kRestoreFocusDelayMs = 50;
constexpr const char* kLogLevelEnvVar = "ELECTRON_CLIENT_NOACTIVATE_LOG_LEVEL";

LRESULT CALLBACK PassiveClientWndProc(HWND hwnd,
                                      UINT message,
                                      WPARAM w_param,
                                      LPARAM l_param);

std::string GetLastErrorMessage(DWORD error_code) {
  if (error_code == 0) {
    return "unknown error";
  }

  LPSTR message_buffer = nullptr;
  const DWORD size = FormatMessageA(
      FORMAT_MESSAGE_ALLOCATE_BUFFER | FORMAT_MESSAGE_FROM_SYSTEM |
          FORMAT_MESSAGE_IGNORE_INSERTS,
      nullptr,
      error_code,
      MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
      reinterpret_cast<LPSTR>(&message_buffer),
      0,
      nullptr);

  std::string message =
      size > 0 && message_buffer != nullptr ? std::string(message_buffer, size)
                                            : "unknown error";

  if (message_buffer != nullptr) {
    LocalFree(message_buffer);
  }

  while (!message.empty() &&
         (message.back() == '\r' || message.back() == '\n' ||
          message.back() == ' ')) {
    message.pop_back();
  }

  return message;
}

LogLevel ParseLogLevel(const char* value) {
  if (value == nullptr) {
    return LogLevel::kWarn;
  }

  const std::string normalized(value);
  if (normalized == "silent") {
    return LogLevel::kSilent;
  }
  if (normalized == "error") {
    return LogLevel::kError;
  }
  if (normalized == "warn") {
    return LogLevel::kWarn;
  }
  if (normalized == "info") {
    return LogLevel::kInfo;
  }
  if (normalized == "debug") {
    return LogLevel::kDebug;
  }

  return LogLevel::kWarn;
}

LogLevel GetCurrentLogLevel() {
  return ParseLogLevel(std::getenv(kLogLevelEnvVar));
}

bool ShouldLog(LogLevel level) {
  return static_cast<int>(level) <= static_cast<int>(GetCurrentLogLevel());
}

void LogMessage(LogLevel level, const std::string& message) {
  if (!ShouldLog(level)) {
    return;
  }

  std::fprintf(stderr, "[electron-client-noactivate] %s\n", message.c_str());
  std::fflush(stderr);
}

void ThrowTypeError(napi_env env, const char* message) {
  napi_throw_type_error(env, nullptr, message);
}

std::string HwndToHex(HWND hwnd) {
  if (hwnd == nullptr) {
    return "null";
  }

  std::ostringstream stream;
  stream << "0x" << std::hex << reinterpret_cast<uintptr_t>(hwnd);
  return stream.str();
}

std::string BuildWindowsErrorLog(const char* action, HWND hwnd) {
  const DWORD error_code = GetLastError();
  std::ostringstream message;
  message << action;
  if (hwnd != nullptr) {
    message << " failed for " << HwndToHex(hwnd);
  } else {
    message << " failed";
  }
  message << " (" << error_code << "): " << GetLastErrorMessage(error_code);
  return message.str();
}

void LogInfo(const std::string& message) {
  LogMessage(LogLevel::kInfo, message);
}

void LogWarn(const std::string& message) {
  LogMessage(LogLevel::kWarn, message);
}

void LogError(const std::string& message) {
  LogMessage(LogLevel::kError, message);
}

bool GetHwndFromValue(napi_env env, napi_value value, HWND* out_hwnd) {
  bool is_buffer = false;
  if (napi_is_buffer(env, value, &is_buffer) != napi_ok || !is_buffer) {
    ThrowTypeError(env, "Expected a native window handle Buffer.");
    return false;
  }

  void* data = nullptr;
  size_t length = 0;
  if (napi_get_buffer_info(env, value, &data, &length) != napi_ok) {
    napi_throw_error(env, nullptr, "Failed to read the native window handle Buffer.");
    return false;
  }

  if (length < sizeof(void*)) {
    ThrowTypeError(env, "Native window handle Buffer is smaller than a pointer.");
    return false;
  }

  auto* pointer = reinterpret_cast<void* const*>(data);
  *out_hwnd = reinterpret_cast<HWND>(*pointer);
  return true;
}

napi_value CreateBoolean(napi_env env, bool value) {
  napi_value result = nullptr;
  napi_get_boolean(env, value, &result);
  return result;
}

void SetNamedInt32(napi_env env, napi_value object, const char* name, int value) {
  napi_value number = nullptr;
  napi_create_int32(env, value, &number);
  napi_set_named_property(env, object, name, number);
}

napi_value CreateHookSummaryValue(napi_env env, const HookSummary& summary) {
  napi_value result = nullptr;
  napi_create_object(env, &result);
  napi_set_named_property(env, result, "installed", CreateBoolean(env, summary.installed()));
  SetNamedInt32(env, result, "totalWindows", summary.total_windows);
  SetNamedInt32(env, result, "changedWindows", summary.changed_windows);
  SetNamedInt32(env, result, "alreadyChangedWindows", summary.already_changed_windows);
  SetNamedInt32(env, result, "skippedForeignWindows", summary.skipped_foreign_windows);
  SetNamedInt32(env, result, "skippedMissingWindows", summary.skipped_missing_windows);
  SetNamedInt32(env, result, "failedWindows", summary.failed_windows);
  return result;
}

HWND GetTopLevelWindow(HWND hwnd) {
  if (hwnd == nullptr) {
    return nullptr;
  }

  return GetAncestor(hwnd, GA_ROOT);
}

bool IsCurrentProcessWindow(HWND hwnd) {
  if (hwnd == nullptr) {
    return false;
  }

  DWORD process_id = 0;
  GetWindowThreadProcessId(hwnd, &process_id);
  return process_id == GetCurrentProcessId();
}

std::shared_ptr<HookState> GetHookState(HWND hwnd, WNDPROC* out_previous_proc = nullptr) {
  std::lock_guard<std::mutex> lock(g_hooks_mutex);
  auto iterator = g_hook_states.find(hwnd);
  if (iterator == g_hook_states.end()) {
    return nullptr;
  }

  if (out_previous_proc != nullptr) {
    *out_previous_proc = iterator->second->previous_proc;
  }

  return iterator->second;
}

void TrackExternalForegroundWindow(HWND hwnd) {
  const HWND top_level = GetTopLevelWindow(hwnd);
  if (top_level == nullptr || !IsWindow(top_level) || IsCurrentProcessWindow(top_level)) {
    return;
  }

  {
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    for (auto& [tracked_hwnd, state] : g_hook_states) {
      if (state != nullptr) {
        state->last_external_foreground = top_level;
      }
    }
  }

  LogInfo("Tracked external foreground window " + HwndToHex(top_level));
}

void CALLBACK ForegroundChangedHook(HWINEVENTHOOK,
                                    DWORD,
                                    HWND hwnd,
                                    LONG,
                                    LONG,
                                    DWORD,
                                    DWORD) {
  TrackExternalForegroundWindow(hwnd);
}

void EnsureForegroundHookInstalled() {
  if (g_foreground_hook != nullptr) {
    return;
  }

  g_foreground_hook = SetWinEventHook(
      EVENT_SYSTEM_FOREGROUND,
      EVENT_SYSTEM_FOREGROUND,
      nullptr,
      ForegroundChangedHook,
      0,
      0,
      WINEVENT_OUTOFCONTEXT | WINEVENT_SKIPOWNPROCESS);

  if (g_foreground_hook == nullptr) {
    LogError(BuildWindowsErrorLog("SetWinEventHook(EVENT_SYSTEM_FOREGROUND)", nullptr));
    return;
  }

  LogInfo("Installed foreground tracking hook.");
}

void MaybeUninstallForegroundHook() {
  bool should_uninstall = false;
  {
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    should_uninstall = g_hook_states.empty();
  }

  if (!should_uninstall || g_foreground_hook == nullptr) {
    return;
  }

  if (!UnhookWinEvent(g_foreground_hook)) {
    LogError(BuildWindowsErrorLog("UnhookWinEvent", nullptr));
    return;
  }

  g_foreground_hook = nullptr;
  LogInfo("Uninstalled foreground tracking hook.");
}

bool SetWindowExStyle(HWND hwnd, LONG_PTR next_exstyle, bool no_activate_flag) {
  SetLastError(0);
  const LONG_PTR result = SetWindowLongPtr(hwnd, GWL_EXSTYLE, next_exstyle);
  if (result == 0 && GetLastError() != 0) {
    LogError(BuildWindowsErrorLog("SetWindowLongPtr(GWL_EXSTYLE)", hwnd));
    return false;
  }

  UINT flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOOWNERZORDER | SWP_NOZORDER |
               SWP_FRAMECHANGED;
  if (no_activate_flag) {
    flags |= SWP_NOACTIVATE;
  }

  if (!SetWindowPos(hwnd, nullptr, 0, 0, 0, 0, flags)) {
    LogError(BuildWindowsErrorLog("SetWindowPos", hwnd));
    return false;
  }

  return true;
}

bool EnableNoActivateForState(HWND hwnd, HookState* state, const char* reason) {
  if (state == nullptr || !IsWindow(hwnd)) {
    return false;
  }

  LONG_PTR current_exstyle = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
  if ((current_exstyle & WS_EX_NOACTIVATE) != 0) {
    state->noactivate_enabled = true;
    LogInfo(
        "WS_EX_NOACTIVATE already enabled for " + HwndToHex(hwnd) + " (" + reason + ")");
    return true;
  }

  if (!SetWindowExStyle(hwnd, current_exstyle | WS_EX_NOACTIVATE, true)) {
    return false;
  }

  state->noactivate_enabled = true;
  LogInfo("Enabled WS_EX_NOACTIVATE for " + HwndToHex(hwnd) + " (" + reason + ")");
  return true;
}

bool DisableNoActivateForState(HWND hwnd, HookState* state, const char* reason) {
  if (state == nullptr || !IsWindow(hwnd)) {
    return false;
  }

  LONG_PTR current_exstyle = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
  if ((current_exstyle & WS_EX_NOACTIVATE) == 0) {
    state->noactivate_enabled = false;
    LogInfo(
        "WS_EX_NOACTIVATE already disabled for " + HwndToHex(hwnd) + " (" + reason + ")");
    return true;
  }

  if (!SetWindowExStyle(
          hwnd,
          current_exstyle & ~static_cast<LONG_PTR>(WS_EX_NOACTIVATE),
          false)) {
    return false;
  }

  state->noactivate_enabled = false;
  LogInfo("Disabled WS_EX_NOACTIVATE for " + HwndToHex(hwnd) + " (" + reason + ")");
  return true;
}

void InstallTopLevelHook(HWND hwnd, HookSummary* summary) {
  summary->total_windows += 1;

  if (!IsWindow(hwnd)) {
    summary->skipped_missing_windows += 1;
    LogWarn("Skipping missing top-level window " + HwndToHex(hwnd));
    return;
  }

  if (!IsCurrentProcessWindow(hwnd)) {
    summary->skipped_foreign_windows += 1;
    LogWarn("Skipping foreign top-level window " + HwndToHex(hwnd));
    return;
  }

  {
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    if (g_hook_states.find(hwnd) != g_hook_states.end()) {
      summary->already_changed_windows += 1;
      LogInfo("Top-level window already hooked " + HwndToHex(hwnd));
      return;
    }
  }

  SetLastError(0);
  const LONG_PTR original_exstyle = GetWindowLongPtr(hwnd, GWL_EXSTYLE);
  if (original_exstyle == 0 && GetLastError() != 0) {
    summary->failed_windows += 1;
    LogError(BuildWindowsErrorLog("GetWindowLongPtr(GWL_EXSTYLE)", hwnd));
    return;
  }

  auto state = std::make_shared<HookState>();
  state->original_exstyle = original_exstyle;
  state->added_noactivate_style = (original_exstyle & WS_EX_NOACTIVATE) == 0;
  state->noactivate_enabled = (original_exstyle & WS_EX_NOACTIVATE) != 0;
  state->last_external_foreground = GetTopLevelWindow(GetForegroundWindow());

  if (state->last_external_foreground != nullptr &&
      IsCurrentProcessWindow(state->last_external_foreground)) {
    state->last_external_foreground = nullptr;
  }

  EnsureForegroundHookInstalled();

  if (!EnableNoActivateForState(hwnd, state.get(), "install")) {
    summary->failed_windows += 1;
    return;
  }

  SetLastError(0);
  const LONG_PTR previous =
      SetWindowLongPtr(hwnd,
                       GWLP_WNDPROC,
                       reinterpret_cast<LONG_PTR>(PassiveClientWndProc));
  if (previous == 0 && GetLastError() != 0) {
    summary->failed_windows += 1;
    LogError(BuildWindowsErrorLog("SetWindowLongPtr(GWLP_WNDPROC)", hwnd));

    if (state->added_noactivate_style) {
      SetWindowExStyle(hwnd, state->original_exstyle, false);
    }

    return;
  }

  state->previous_proc = reinterpret_cast<WNDPROC>(previous);

  {
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    g_hook_states.emplace(hwnd, state);
  }

  if (state->last_external_foreground != nullptr) {
    LogInfo(
        "Seeded last external foreground window " +
        HwndToHex(state->last_external_foreground));
  }

  summary->changed_windows += 1;
  LogInfo("Installed top-level hook for " + HwndToHex(hwnd));
}

void UninstallTopLevelHook(HWND hwnd, HookSummary* summary) {
  summary->total_windows += 1;

  std::shared_ptr<HookState> state;
  {
    std::lock_guard<std::mutex> lock(g_hooks_mutex);
    auto iterator = g_hook_states.find(hwnd);
    if (iterator == g_hook_states.end()) {
      summary->skipped_missing_windows += 1;
      LogWarn("Skipping uninstall for untracked top-level window " + HwndToHex(hwnd));
      return;
    }

    state = iterator->second;
    g_hook_states.erase(iterator);
  }

  if (!IsWindow(hwnd)) {
    summary->skipped_missing_windows += 1;
    LogWarn("Top-level window destroyed before uninstall " + HwndToHex(hwnd));
    MaybeUninstallForegroundHook();
    return;
  }

  KillTimer(hwnd, kRestoreFocusTimerId);

  SetLastError(0);
  const LONG_PTR result =
      SetWindowLongPtr(hwnd,
                       GWLP_WNDPROC,
                       reinterpret_cast<LONG_PTR>(state->previous_proc));
  if (result == 0 && GetLastError() != 0) {
    summary->failed_windows += 1;
    LogError(BuildWindowsErrorLog("SetWindowLongPtr(GWLP_WNDPROC)", hwnd));
    MaybeUninstallForegroundHook();
    return;
  }

  if (!SetWindowExStyle(hwnd, state->original_exstyle, false)) {
    summary->failed_windows += 1;
    MaybeUninstallForegroundHook();
    return;
  }

  MaybeUninstallForegroundHook();

  summary->changed_windows += 1;
  LogInfo("Uninstalled top-level hook for " + HwndToHex(hwnd));
}

LRESULT CALLBACK PassiveClientWndProc(HWND hwnd,
                                      UINT message,
                                      WPARAM w_param,
                                      LPARAM l_param) {
  WNDPROC previous_proc = nullptr;
  const std::shared_ptr<HookState> state = GetHookState(hwnd, &previous_proc);

  if (message == WM_MOUSEACTIVATE) {
    const auto hit_test = static_cast<int>(LOWORD(l_param));
    if (hit_test == HTCLIENT) {
      LogInfo("WM_MOUSEACTIVATE HTCLIENT -> MA_NOACTIVATE for " + HwndToHex(hwnd));
      return MA_NOACTIVATE;
    }

    if (state != nullptr) {
      {
        std::lock_guard<std::mutex> lock(g_hooks_mutex);
        state->allow_next_activation = true;
      }

      KillTimer(hwnd, kRestoreFocusTimerId);
      DisableNoActivateForState(hwnd, state.get(), "non-client mouse activate");
    }

    LogInfo("WM_MOUSEACTIVATE non-client -> MA_ACTIVATE for " + HwndToHex(hwnd));
    return MA_ACTIVATE;
  }

  if (message == WM_NCLBUTTONDOWN || message == WM_NCLBUTTONDBLCLK) {
    const auto hit_test = static_cast<int>(w_param);
    if (hit_test != HTCLIENT && state != nullptr) {
      {
        std::lock_guard<std::mutex> lock(g_hooks_mutex);
        state->allow_next_activation = true;
      }

      KillTimer(hwnd, kRestoreFocusTimerId);
      DisableNoActivateForState(hwnd, state.get(), "non-client button down");
      SetForegroundWindow(hwnd);
      LogInfo("Promoted top-level activation from non-client click for " + HwndToHex(hwnd));
    }
  }

  if (message == WM_ACTIVATE) {
    const auto activation_state = LOWORD(w_param);
    if (activation_state == WA_INACTIVE) {
      if (state != nullptr && state->added_noactivate_style) {
        EnableNoActivateForState(hwnd, state.get(), "window deactivated");
      }
    } else {
      bool allow_next_activation = false;
      HWND restore_target = nullptr;

      if (state != nullptr) {
        std::lock_guard<std::mutex> lock(g_hooks_mutex);
        allow_next_activation = state->allow_next_activation;
        state->allow_next_activation = false;
        restore_target = state->last_external_foreground;
      }

      if (allow_next_activation) {
        LogInfo("Allowed explicit activation for " + HwndToHex(hwnd));
      } else if (restore_target != nullptr && IsWindow(restore_target) &&
                 restore_target != hwnd) {
        KillTimer(hwnd, kRestoreFocusTimerId);
        SetTimer(hwnd, kRestoreFocusTimerId, kRestoreFocusDelayMs, nullptr);
        LogInfo(
            "Scheduled focus restore to " + HwndToHex(restore_target) +
            " after client activation of " + HwndToHex(hwnd));
      }

      LogInfo("Window activated " + HwndToHex(hwnd));
    }
  }

  if (message == WM_TIMER && w_param == kRestoreFocusTimerId) {
    KillTimer(hwnd, kRestoreFocusTimerId);

    HWND restore_target = nullptr;
    if (state != nullptr) {
      std::lock_guard<std::mutex> lock(g_hooks_mutex);
      restore_target = state->last_external_foreground;
    }

    if (restore_target != nullptr && IsWindow(restore_target) && restore_target != hwnd) {
      if (IsIconic(restore_target)) {
        ShowWindow(restore_target, SW_RESTORE);
      }

      SetForegroundWindow(restore_target);
      LogInfo(
          "Restored foreground window " + HwndToHex(restore_target) +
          " after client activation.");
    }

    return 0;
  }

  if (message == WM_NCDESTROY) {
    std::shared_ptr<HookState> uninstall_state;
    {
      std::lock_guard<std::mutex> lock(g_hooks_mutex);
      auto iterator = g_hook_states.find(hwnd);
      if (iterator != g_hook_states.end()) {
        uninstall_state = iterator->second;
        g_hook_states.erase(iterator);
      }
    }

    if (uninstall_state != nullptr) {
      KillTimer(hwnd, kRestoreFocusTimerId);
      SetWindowLongPtr(hwnd,
                       GWLP_WNDPROC,
                       reinterpret_cast<LONG_PTR>(uninstall_state->previous_proc));
      MaybeUninstallForegroundHook();
      LogInfo("Window destroyed; removed hook state for " + HwndToHex(hwnd));
      return CallWindowProc(
          uninstall_state->previous_proc, hwnd, message, w_param, l_param);
    }
  }

  if (previous_proc != nullptr) {
    return CallWindowProc(previous_proc, hwnd, message, w_param, l_param);
  }

  return DefWindowProc(hwnd, message, w_param, l_param);
}

bool GetSingleArgument(napi_env env, napi_callback_info info, napi_value* out_argument) {
  size_t argc = 1;
  if (napi_get_cb_info(env, info, &argc, out_argument, nullptr, nullptr) != napi_ok) {
    napi_throw_error(env, nullptr, "Failed to read callback arguments.");
    return false;
  }

  if (argc < 1) {
    ThrowTypeError(env, "Expected a native window handle Buffer.");
    return false;
  }

  return true;
}

napi_value Install(napi_env env, napi_callback_info info) {
  napi_value argument = nullptr;
  if (!GetSingleArgument(env, info, &argument)) {
    return nullptr;
  }

  HWND hwnd = nullptr;
  if (!GetHwndFromValue(env, argument, &hwnd)) {
    return nullptr;
  }

  if (!IsWindow(hwnd)) {
    napi_throw_error(env, nullptr, "install received an invalid or destroyed HWND.");
    return nullptr;
  }

  HookSummary summary;
  InstallTopLevelHook(hwnd, &summary);
  return CreateHookSummaryValue(env, summary);
}

napi_value Uninstall(napi_env env, napi_callback_info info) {
  napi_value argument = nullptr;
  if (!GetSingleArgument(env, info, &argument)) {
    return nullptr;
  }

  HWND hwnd = nullptr;
  if (!GetHwndFromValue(env, argument, &hwnd)) {
    return nullptr;
  }

  HookSummary summary;
  UninstallTopLevelHook(hwnd, &summary);
  return CreateHookSummaryValue(env, summary);
}

napi_value IsInstalled(napi_env env, napi_callback_info info) {
  napi_value argument = nullptr;
  if (!GetSingleArgument(env, info, &argument)) {
    return nullptr;
  }

  HWND hwnd = nullptr;
  if (!GetHwndFromValue(env, argument, &hwnd)) {
    return nullptr;
  }

  std::lock_guard<std::mutex> lock(g_hooks_mutex);
  return CreateBoolean(env, g_hook_states.find(hwnd) != g_hook_states.end());
}

napi_value Init(napi_env env, napi_value exports) {
  napi_value install = nullptr;
  napi_value is_installed = nullptr;
  napi_value uninstall = nullptr;

  napi_create_function(env, "install", NAPI_AUTO_LENGTH, Install, nullptr, &install);
  napi_create_function(
      env, "isInstalled", NAPI_AUTO_LENGTH, IsInstalled, nullptr, &is_installed);
  napi_create_function(env, "uninstall", NAPI_AUTO_LENGTH, Uninstall, nullptr, &uninstall);

  napi_set_named_property(env, exports, "install", install);
  napi_set_named_property(env, exports, "isInstalled", is_installed);
  napi_set_named_property(env, exports, "uninstall", uninstall);
  return exports;
}

}  // namespace

NAPI_MODULE(NODE_GYP_MODULE_NAME, Init)
