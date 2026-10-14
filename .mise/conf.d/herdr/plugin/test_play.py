import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import play


class _AudioPlayerTest(unittest.TestCase):
    def test_wsl_uses_windows_ffplay_with_converted_plugin_path(self) -> None:
        executable_paths = {
            "ffplay.exe": "/mnt/c/ffmpeg/bin/ffplay.exe",
            "wslpath": "/usr/bin/wslpath",
        }

        def executable_path(name: str) -> str | None:
            return executable_paths.get(name)

        windows_sound_path = "\\\\wsl.localhost\\Ubuntu\\plugin\\sounds\\06.mp3"
        conversion = subprocess.CompletedProcess(
            args=[],
            returncode=0,
            stdout=windows_sound_path + "\r\n",
            stderr="",
        )
        directory = tempfile.TemporaryDirectory(prefix="hiho_herdr_player_test_")
        self.addCleanup(directory.cleanup)
        sound_path = Path(directory.name) / "通知音 with spaces.mp3"
        sound_path.write_bytes(b"fixture")

        with (
            patch.object(play.sys, "platform", "linux"),
            patch.object(
                play.platform,
                "release",
                return_value="5.15.0-microsoft-standard-WSL2",
            ),
            patch.object(play.shutil, "which", side_effect=executable_path),
            patch.object(play.subprocess, "run", return_value=conversion) as run,
        ):
            audio_player = play._resolve_audio_player()
            command = audio_player.command(sound_path)

        self.assertEqual(
            command,
            [
                "/mnt/c/ffmpeg/bin/ffplay.exe",
                "-nodisp",
                "-autoexit",
                "-nostats",
                "-loglevel",
                "error",
                windows_sound_path,
            ],
        )
        run.assert_called_once_with(
            [
                "/usr/bin/wslpath",
                "-w",
                str(sound_path.resolve(strict=True)),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=play.PATH_CONVERSION_TIMEOUT_SECONDS,
        )

    def test_linux_uses_local_ffplay(self) -> None:
        with (
            patch.object(play.sys, "platform", "linux"),
            patch.object(play.platform, "release", return_value="6.8.0-generic"),
            patch.object(
                play.shutil,
                "which",
                return_value="/usr/bin/ffplay",
            ),
        ):
            audio_player = play._resolve_audio_player()
            command = audio_player.command(Path("/plugin/sounds/01.mp3"))

        self.assertEqual(
            command,
            [
                "/usr/bin/ffplay",
                "-nodisp",
                "-autoexit",
                "-nostats",
                "-loglevel",
                "error",
                "/plugin/sounds/01.mp3",
            ],
        )

    def test_macos_uses_afplay(self) -> None:
        with (
            patch.object(play.sys, "platform", "darwin"),
            patch.object(
                play.shutil,
                "which",
                return_value="/usr/bin/afplay",
            ),
        ):
            audio_player = play._resolve_audio_player()
            command = audio_player.command(Path("/plugin/sounds/01.mp3"))

        self.assertEqual(
            command,
            ["/usr/bin/afplay", "/plugin/sounds/01.mp3"],
        )

    def test_missing_player_raises_error(self) -> None:
        with (
            patch.object(play.sys, "platform", "darwin"),
            patch.object(play.shutil, "which", return_value=None),
            self.assertRaisesRegex(FileNotFoundError, "afplay"),
        ):
            play._resolve_audio_player()


if __name__ == "__main__":
    unittest.main()
