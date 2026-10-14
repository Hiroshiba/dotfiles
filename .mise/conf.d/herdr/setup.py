import os
import subprocess
import sys
from pathlib import Path


def main() -> None:
    """通知音を暗号化・配置・検証する。"""
    if sys.platform == "win32":
        print("Windowsネイティブの通知プラグイン配置は対象外です")
        return
    if sys.platform not in {"darwin", "linux"}:
        raise RuntimeError(f"未対応のプラットフォームです: {sys.platform}")
    config_directory = Path.home() / ".config" / "herdr"
    if sys.argv == [sys.argv[0], "encrypt"]:
        _encrypt_audio(config_directory)
        return
    if sys.argv not in [[sys.argv[0], "apply"], [sys.argv[0], "check"]]:
        raise RuntimeError(
            "実行方法が不正です。apply・check・encryptを指定してください"
        )
    identity = _identity_path()
    if not identity.is_file():
        raise FileNotFoundError(
            f"共通の秘密鍵をGoogle Driveから配置してください: {identity}"
        )
    if sys.argv == [sys.argv[0], "apply"]:
        if identity.stat().st_mode & 0o777 != 0o600:
            identity.chmod(0o600)
        audio = _decrypt_audio(config_directory, identity)
        changed = _write_audio(audio)
        subprocess.run(
            [
                "herdr",
                "plugin",
                "link",
                str(config_directory / "round-robin-sound"),
                "--enabled",
            ],
            check=True,
        )
        print(f"通知音{len(audio)}本を確認し、{changed}本を配置しました")
        return
    audio = _decrypt_audio(config_directory, identity)
    _check_audio(audio)
    print(f"通知音{len(audio)}本の復号結果と配置済みファイルが一致しました")


def _identity_path() -> Path:
    result = subprocess.run(
        ["mise", "settings", "get", "age.key_file"],
        check=True,
        capture_output=True,
        text=True,
    )
    value = result.stdout.strip()
    if value == "":
        raise ValueError("age.key_fileに秘密鍵の保存先が設定されていません")
    return Path(value).expanduser()


def _audio_directory() -> Path:
    return Path(__file__).resolve().parent / "audio"


def _decrypt_audio(config_directory: Path, identity: Path) -> list[tuple[Path, bytes]]:
    audio_directory = _audio_directory()
    encrypted_paths = sorted(audio_directory.rglob("*.age"))
    if len(encrypted_paths) == 0:
        raise FileNotFoundError(f"暗号化した音声がありません: {audio_directory}")
    audio: list[tuple[Path, bytes]] = []
    for encrypted_path in encrypted_paths:
        result = subprocess.run(
            ["age", "--decrypt", "--identity", str(identity), str(encrypted_path)],
            check=True,
            stdout=subprocess.PIPE,
        )
        target = config_directory / encrypted_path.relative_to(
            audio_directory
        ).with_suffix("")
        audio.append((target, result.stdout))
    return audio


def _write_audio(audio: list[tuple[Path, bytes]]) -> int:
    changed = 0
    for target, contents in audio:
        if target.is_file() and target.read_bytes() == contents:
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        temporary_path.write_bytes(contents)
        temporary_path.replace(target)
        changed += 1
    return changed


def _check_audio(audio: list[tuple[Path, bytes]]) -> None:
    for target, contents in audio:
        if not target.is_file():
            raise FileNotFoundError(f"配置済みの音声がありません: {target}")
        if target.read_bytes() != contents:
            raise ValueError(f"配置済みの音声が復号結果と一致しません: {target}")


def _encrypt_audio(config_directory: Path) -> None:
    source_directories = [
        config_directory / "round-robin-sound" / "sounds",
        config_directory / "sounds",
    ]
    sources = sorted(
        path
        for directory in source_directories
        for path in directory.iterdir()
        if path.is_file() and path.suffix in {".mp3", ".wav"}
    )
    if len(sources) == 0:
        raise FileNotFoundError(f"暗号化する音声がありません: {config_directory}")
    recipients = Path(__file__).resolve().parent / "recipients.txt"
    for source in sources:
        encrypted_path = _audio_directory() / source.relative_to(config_directory)
        encrypted_path = encrypted_path.with_name(f"{encrypted_path.name}.age")
        result = subprocess.run(
            ["age", "--armor", "--recipients-file", str(recipients), str(source)],
            check=True,
            stdout=subprocess.PIPE,
        )
        encrypted_path.parent.mkdir(parents=True, exist_ok=True)
        encrypted_path.write_bytes(result.stdout)
    print(f"通知音{len(sources)}本を暗号化しました")


if __name__ == "__main__":
    main()
