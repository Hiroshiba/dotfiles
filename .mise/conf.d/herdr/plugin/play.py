import fcntl
import json
import os
import platform
import random
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

PLUGIN_STATE_VERSION = 1
NO_SOUND_PLAYED = "not_played"
EVENT_SETTLE_SECONDS = 1.0
PLAYBACK_TIMEOUT_SECONDS = 15
PATH_CONVERSION_TIMEOUT_SECONDS = 5
AGENT_STATUSES = frozenset({"idle", "working", "blocked", "done", "unknown"})
NOTIFICATION_STATUSES = frozenset({"done", "blocked"})
JSON_EVENT_NAMES = {
    "pane.agent_status_changed": "pane_agent_status_changed",
    "pane.closed": "pane_closed",
}
SOUND_FILE_NAMES = (
    "01.mp3",
    "02.mp3",
    "03.mp3",
    "04.mp3",
    "05.mp3",
    "06.mp3",
)


@dataclass
class _PluginState:
    remaining: list[str]
    last_played: str
    pane_statuses: dict[str, str]


@dataclass(frozen=True)
class _NoSelection:
    pass


@dataclass(frozen=True)
class _SoundSelection:
    file_name: str


type _Selection = _NoSelection | _SoundSelection


@dataclass(frozen=True)
class _Afplay:
    executable: Path

    def command(self, sound_path: Path) -> list[str]:
        return [str(self.executable), str(sound_path)]


@dataclass(frozen=True)
class _LocalFfplay:
    executable: Path

    def command(self, sound_path: Path) -> list[str]:
        return _ffplay_command(self.executable, str(sound_path))


@dataclass(frozen=True)
class _WindowsFfplay:
    executable: Path
    path_converter: Path

    def command(self, sound_path: Path) -> list[str]:
        windows_sound_path = _windows_path(self.path_converter, sound_path)
        return _ffplay_command(self.executable, windows_sound_path)


type _AudioPlayer = _Afplay | _LocalFfplay | _WindowsFfplay


def main() -> None:
    """Herdrの通知イベントまたは手動アクションを処理する。"""
    if sys.argv == [sys.argv[0], "event"]:
        _handle_event()
        return
    if sys.argv == [sys.argv[0], "manual"]:
        _handle_manual()
        return
    raise RuntimeError("実行方法が不正です。eventまたはmanualを指定してください")


def _handle_event() -> None:
    plugin_root = _required_directory("HERDR_PLUGIN_ROOT")
    state_dir = _required_directory("HERDR_PLUGIN_STATE_DIR")
    _validate_sound_files(plugin_root)
    event_name, data = _read_event()

    if event_name == "pane.agent_status_changed":
        _handle_agent_status_changed(plugin_root, state_dir, data)
        return
    if event_name == "pane.closed":
        _handle_pane_closed(state_dir, data)
        return
    raise RuntimeError(f"未対応のイベントです: {event_name}")


def _handle_manual() -> None:
    plugin_root = _required_directory("HERDR_PLUGIN_ROOT")
    state_dir = _required_directory("HERDR_PLUGIN_STATE_DIR")
    _validate_sound_files(plugin_root)
    audio_player = _resolve_audio_player()
    file_name = _take_next_sound(_state_path(state_dir), _lock_path(state_dir))
    _play_sound(audio_player, plugin_root / "sounds" / file_name)


def _handle_agent_status_changed(
    plugin_root: Path,
    state_dir: Path,
    data: dict[str, object],
) -> None:
    pane_id = _required_string(data, "pane_id")
    status = _required_string(data, "agent_status")
    if status not in AGENT_STATUSES:
        raise ValueError(f"不明なエージェント状態です: {status}")
    if "agent" in data:
        agent = data["agent"]
        if not isinstance(agent, str):
            raise TypeError("イベントのagentは文字列でなければなりません")
        if agent == "droid":
            return

    state_path = _state_path(state_dir)
    lock_path = _lock_path(state_dir)
    status_changed = _record_pane_status(state_path, lock_path, pane_id, status)
    if status_changed is False or status not in NOTIFICATION_STATUSES:
        return

    time.sleep(EVENT_SETTLE_SECONDS)
    audio_player = _resolve_audio_player()
    selection = _select_if_status_unchanged(
        state_path,
        lock_path,
        pane_id,
        status,
    )
    if isinstance(selection, _NoSelection):
        return
    _play_sound(audio_player, plugin_root / "sounds" / selection.file_name)


def _handle_pane_closed(state_dir: Path, data: dict[str, object]) -> None:
    pane_id = _required_string(data, "pane_id")
    _remove_pane_status(_state_path(state_dir), _lock_path(state_dir), pane_id)


def _read_event() -> tuple[str, dict[str, object]]:
    environment_event_name = _required_environment("HERDR_PLUGIN_EVENT")
    if environment_event_name not in JSON_EVENT_NAMES:
        raise ValueError(f"未対応のイベントです: {environment_event_name}")

    event_json = _required_environment("HERDR_PLUGIN_EVENT_JSON")
    parsed = json.loads(event_json)
    envelope = _json_object(parsed, "イベント")
    if set(envelope) != {"event", "data"}:
        raise ValueError("イベントにはeventとdataだけが必要です")

    expected_json_event_name = JSON_EVENT_NAMES[environment_event_name]
    json_event_name = _required_string(envelope, "event")
    if json_event_name != expected_json_event_name:
        raise ValueError(
            "HERDR_PLUGIN_EVENTとHERDR_PLUGIN_EVENT_JSONのイベント名が一致しません"
        )

    data = _json_object(envelope["data"], "イベントのdata")
    data_event_name = _required_string(data, "type")
    if data_event_name != expected_json_event_name:
        raise ValueError("イベントのeventとdata.typeが一致しません")
    return environment_event_name, data


def _required_environment(name: str) -> str:
    if name not in os.environ:
        raise RuntimeError(f"環境変数{name}がありません")
    value = os.environ[name]
    if value == "":
        raise RuntimeError(f"環境変数{name}が空です")
    return value


def _required_directory(name: str) -> Path:
    path = Path(_required_environment(name))
    if not path.is_dir():
        raise NotADirectoryError(f"環境変数{name}のディレクトリがありません: {path}")
    return path


def _json_object(value: object, name: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise TypeError(f"{name}はオブジェクトでなければなりません")
    for key in value:
        if not isinstance(key, str):
            raise TypeError(f"{name}のキーは文字列でなければなりません")
    return value


def _required_string(values: dict[str, object], key: str) -> str:
    if key not in values:
        raise ValueError(f"必須項目{key}がありません")
    value = values[key]
    if not isinstance(value, str):
        raise TypeError(f"{key}は文字列でなければなりません")
    if value == "":
        raise ValueError(f"{key}が空です")
    return value


def _state_path(state_dir: Path) -> Path:
    return state_dir / "state.json"


def _lock_path(state_dir: Path) -> Path:
    return state_dir / "state.lock"


def _initial_state() -> _PluginState:
    return _PluginState(
        remaining=[],
        last_played=NO_SOUND_PLAYED,
        pane_statuses={},
    )


def _load_state(state_path: Path) -> _PluginState:
    if state_path.exists() is False:
        return _initial_state()
    parsed = json.loads(state_path.read_text(encoding="utf-8"))
    values = _json_object(parsed, "状態ファイル")
    expected_keys = {
        "version",
        "playlist",
        "remaining",
        "last_played",
        "pane_statuses",
    }
    if set(values) != expected_keys:
        raise ValueError("状態ファイルの項目が現在の形式と一致しません")
    if type(values["version"]) is not int:
        raise TypeError("状態ファイルのversionは整数でなければなりません")
    if values["version"] != PLUGIN_STATE_VERSION:
        raise ValueError(f"未対応の状態ファイル形式です: {values['version']}")
    if values["playlist"] != list(SOUND_FILE_NAMES):
        raise ValueError("状態ファイルのプレイリストが現在の音声一覧と一致しません")

    remaining_value = values["remaining"]
    if not isinstance(remaining_value, list):
        raise TypeError("状態ファイルのremainingは配列でなければなりません")
    remaining: list[str] = []
    for file_name in remaining_value:
        if not isinstance(file_name, str):
            raise TypeError("状態ファイルのremainingには文字列だけを指定できます")
        remaining.append(file_name)
    if len(remaining) != len(set(remaining)):
        raise ValueError("状態ファイルのremainingに重複があります")
    if set(remaining).issubset(SOUND_FILE_NAMES) is False:
        raise ValueError("状態ファイルのremainingに不明な音声があります")

    last_played = values["last_played"]
    if not isinstance(last_played, str):
        raise TypeError("状態ファイルのlast_playedは文字列でなければなりません")
    if last_played != NO_SOUND_PLAYED and last_played not in SOUND_FILE_NAMES:
        raise ValueError("状態ファイルのlast_playedに不明な音声があります")
    if last_played in remaining:
        raise ValueError("直前に再生した音声がremainingにも含まれています")

    pane_statuses_value = _json_object(values["pane_statuses"], "pane_statuses")
    pane_statuses: dict[str, str] = {}
    for pane_id, status in pane_statuses_value.items():
        if pane_id == "":
            raise ValueError("pane_statusesのペインIDが空です")
        if not isinstance(status, str):
            raise TypeError("pane_statusesの状態は文字列でなければなりません")
        if status not in AGENT_STATUSES:
            raise ValueError(f"pane_statusesに不明な状態があります: {status}")
        pane_statuses[pane_id] = status

    return _PluginState(
        remaining=remaining,
        last_played=last_played,
        pane_statuses=pane_statuses,
    )


def _write_state(state_path: Path, state: _PluginState) -> None:
    values = {
        "version": PLUGIN_STATE_VERSION,
        "playlist": list(SOUND_FILE_NAMES),
        "remaining": state.remaining,
        "last_played": state.last_played,
        "pane_statuses": state.pane_statuses,
    }
    temporary_path = state_path.with_name(f".{state_path.name}.{os.getpid()}.tmp")
    temporary_path.write_text(
        json.dumps(values, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary_path.chmod(0o600)
    os.replace(temporary_path, state_path)


@contextmanager
def _state_lock(lock_path: Path) -> Iterator[None]:
    descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def _record_pane_status(
    state_path: Path,
    lock_path: Path,
    pane_id: str,
    status: str,
) -> bool:
    with _state_lock(lock_path):
        state = _load_state(state_path)
        if pane_id in state.pane_statuses:
            if state.pane_statuses[pane_id] == status:
                return False
        state.pane_statuses[pane_id] = status
        _write_state(state_path, state)
        return True


def _remove_pane_status(state_path: Path, lock_path: Path, pane_id: str) -> None:
    with _state_lock(lock_path):
        state = _load_state(state_path)
        if pane_id not in state.pane_statuses:
            return
        del state.pane_statuses[pane_id]
        _write_state(state_path, state)


def _select_if_status_unchanged(
    state_path: Path,
    lock_path: Path,
    pane_id: str,
    expected_status: str,
) -> _Selection:
    with _state_lock(lock_path):
        state = _load_state(state_path)
        if pane_id not in state.pane_statuses:
            return _NoSelection()
        if state.pane_statuses[pane_id] != expected_status:
            return _NoSelection()
        file_name = _select_next_sound(state)
        _write_state(state_path, state)
        return _SoundSelection(file_name=file_name)


def _take_next_sound(state_path: Path, lock_path: Path) -> str:
    with _state_lock(lock_path):
        state = _load_state(state_path)
        file_name = _select_next_sound(state)
        _write_state(state_path, state)
        return file_name


def _select_next_sound(state: _PluginState) -> str:
    if state.remaining == []:
        state.remaining = _shuffled_playlist(state.last_played)
    file_name = state.remaining.pop(0)
    state.last_played = file_name
    return file_name


def _shuffled_playlist(last_played: str) -> list[str]:
    playlist = list(SOUND_FILE_NAMES)
    random_source = random.SystemRandom()
    random_source.shuffle(playlist)
    if (
        len(playlist) > 1
        and last_played != NO_SOUND_PLAYED
        and playlist[0] == last_played
    ):
        replacement_index = random_source.randrange(1, len(playlist))
        playlist[0], playlist[replacement_index] = (
            playlist[replacement_index],
            playlist[0],
        )
    return playlist


def _validate_sound_files(plugin_root: Path) -> None:
    for file_name in SOUND_FILE_NAMES:
        sound_path = plugin_root / "sounds" / file_name
        if not sound_path.is_file():
            raise FileNotFoundError(f"音声ファイルがありません: {sound_path}")


def _resolve_audio_player() -> _AudioPlayer:
    if sys.platform == "darwin":
        return _Afplay(executable=_required_executable("afplay"))
    if sys.platform != "linux":
        raise RuntimeError(f"未対応のプラットフォームです: {sys.platform}")
    if _is_wsl():
        return _WindowsFfplay(
            executable=_required_executable("ffplay.exe"),
            path_converter=_required_executable("wslpath"),
        )
    return _LocalFfplay(executable=_required_executable("ffplay"))


def _required_executable(name: str) -> Path:
    executable = shutil.which(name)
    if executable is None:
        raise FileNotFoundError(f"実行ファイル{name}がPATHにありません")
    return Path(executable)


def _is_wsl() -> bool:
    return "microsoft" in platform.release().lower()


def _windows_path(path_converter: Path, sound_path: Path) -> str:
    completed = subprocess.run(
        [
            str(path_converter),
            "-w",
            str(sound_path.resolve(strict=True)),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=PATH_CONVERSION_TIMEOUT_SECONDS,
    )
    windows_path = completed.stdout.rstrip("\r\n")
    if windows_path == "":
        raise RuntimeError("wslpathが空のパスを返しました")
    if "\r" in windows_path or "\n" in windows_path:
        raise RuntimeError("wslpathが複数行のパスを返しました")
    return windows_path


def _ffplay_command(executable: Path, sound_path: str) -> list[str]:
    return [
        str(executable),
        "-nodisp",
        "-autoexit",
        "-nostats",
        "-loglevel",
        "error",
        sound_path,
    ]


def _play_sound(audio_player: _AudioPlayer, sound_path: Path) -> None:
    subprocess.run(
        audio_player.command(sound_path),
        check=True,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        timeout=PLAYBACK_TIMEOUT_SECONDS,
    )


if __name__ == "__main__":
    main()
