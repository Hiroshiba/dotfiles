local wezterm = require("wezterm")
local config = wezterm.config_builder()

-- GUIがない環境（mux serverなど）ではダーク扱いにする
local appearance = wezterm.gui and wezterm.gui.get_appearance() or "Dark"

-- システムに合わせてライト・ダークを変更
if appearance:find("Dark") then
  config.color_scheme = "Vs Code Dark+ (Gogh)"
else
  config.color_scheme = "Vs Code Light+ (Gogh)"
end

-- フォント
config.font = wezterm.font { family = 'PlemolJP' }
config.font_size = 11.0

-- キー設定
-- macOSではCodex CLIにctrl+vを渡すため、ペーストへの割り当てはWindowsに限定する
if wezterm.target_triple:find("windows") then
  config.keys = {
    {
      key = "v",
      mods = "CTRL",
      action = wezterm.action.PasteFrom("Clipboard"),
    },
  }
end

-- return
return config
