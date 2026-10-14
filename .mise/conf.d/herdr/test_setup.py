import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import setup


class _AudioDeploymentTest(unittest.TestCase):
    def setUp(self) -> None:
        directory = tempfile.TemporaryDirectory(prefix="hiho_herdr_setup_test_")
        self.addCleanup(directory.cleanup)
        self._directory = Path(directory.name) / "日本語 with spaces"
        self._directory.mkdir()
        self._identity = self._directory / "miseのdotfilesの秘密鍵.txt"
        public_key = self._create_identity(self._identity)
        module_directory = self._directory / "module"
        module_directory.mkdir()
        module_directory.joinpath("recipients.txt").write_text(public_key + "\n")
        module_file = patch.object(
            setup, "__file__", str(module_directory / "setup.py")
        )
        module_file.start()
        self.addCleanup(module_file.stop)
        self._source = self._directory / "original"
        self._home = self._directory / "home"
        self._destination = self._home / ".config" / "herdr"
        self._contents = {
            Path("round-robin-sound/sounds/01.mp3"): bytes(range(256)) * 4,
            Path("sounds/08.wav"): b"RIFF" + bytes(range(256)) * 8,
        }
        for relative_path, contents in self._contents.items():
            source = self._source / relative_path
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_bytes(contents)
        setup._encrypt_audio(self._source)

    def _create_identity(self, path: Path) -> str:
        result = subprocess.run(
            ["age-keygen", "--output", str(path)],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stderr.removeprefix("Public key: ").strip()

    def test_binary_audio_round_trip_and_repeated_apply(self) -> None:
        for encrypted_path in setup._audio_directory().rglob("*.age"):
            contents = encrypted_path.read_text(encoding="ascii")
            self.assertTrue(contents.startswith("-----BEGIN AGE ENCRYPTED FILE-----\n"))
        audio = setup._decrypt_audio(self._destination, self._identity)
        self.assertEqual(setup._write_audio(audio), 2)
        timestamps = {target: target.stat().st_mtime_ns for target, _ in audio}
        setup._check_audio(audio)
        for relative_path, contents in self._contents.items():
            self.assertEqual((self._destination / relative_path).read_bytes(), contents)
        self.assertEqual(setup._write_audio(audio), 0)
        self.assertEqual(
            timestamps, {target: target.stat().st_mtime_ns for target, _ in audio}
        )

    def test_check_detects_modified_audio(self) -> None:
        audio = setup._decrypt_audio(self._destination, self._identity)
        setup._write_audio(audio)
        audio[0][0].write_bytes(b"changed")
        with self.assertRaises(ValueError):
            setup._check_audio(audio)

    def test_invalid_ciphertext_does_not_overwrite_existing_audio(self) -> None:
        wrong_identity = self._directory / "wrong.txt"
        wrong_public_key = self._create_identity(wrong_identity)
        relative_path = Path("sounds/08.wav")
        encrypted_path = setup._audio_directory() / "sounds" / "08.wav.age"
        result = subprocess.run(
            [
                "age",
                "--armor",
                "--recipient",
                wrong_public_key,
                str(self._source / relative_path),
            ],
            check=True,
            capture_output=True,
        )
        encrypted_path.write_bytes(result.stdout)
        for relative_path in self._contents:
            destination = self._destination / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"keep")
        with (
            patch.object(setup.sys, "argv", ["setup.py", "apply"]),
            patch.object(setup.Path, "home", return_value=self._home),
            patch.object(setup, "_identity_path", return_value=self._identity),
            self.assertRaises(subprocess.CalledProcessError),
        ):
            setup.main()
        for relative_path in self._contents:
            self.assertEqual((self._destination / relative_path).read_bytes(), b"keep")


if __name__ == "__main__":
    unittest.main()
