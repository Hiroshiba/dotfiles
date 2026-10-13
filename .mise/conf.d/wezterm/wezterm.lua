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
config.keys = {
  -- ctrl+vでペースト
  {
    key = "v",
    mods = "CTRL",
    action = wezterm.action.PasteFrom("Clipboard"),
  },
}

-- return
return config
