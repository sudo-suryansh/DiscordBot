"""Crash-resistant JSON persistence for the bot's small local data files."""

import copy
import json
import logging
import os
import shutil
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def _read(path, expected_type):
    with open(path, "r", encoding="utf-8") as file:
        value = json.load(file)
    if not isinstance(value, expected_type):
        raise ValueError(f"expected JSON {expected_type.__name__} at root")
    return value


def _atomic_write(path, value):
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    temp_path = path + ".tmp"
    try:
        with open(temp_path, "w", encoding="utf-8", newline="\n") as file:
            json.dump(value, file, indent=2, ensure_ascii=False)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp_path, path)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)


def load_json(path, default, expected_type=dict):
    """Load JSON, restoring the last valid backup if the primary is damaged."""
    if not os.path.exists(path):
        return copy.deepcopy(default)
    try:
        return _read(path, expected_type)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        logger.error("Could not read JSON data file %s: %s", path, error)

    backup = path + ".bak"
    try:
        value = _read(backup, expected_type)
    except FileNotFoundError:
        logger.error("No backup exists for damaged JSON file %s", path)
        return copy.deepcopy(default)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        logger.error("Backup for JSON file %s is also unusable: %s", path, error)
        return copy.deepcopy(default)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    damaged_path = f"{path}.corrupt.{stamp}"
    try:
        os.replace(path, damaged_path)
        _atomic_write(path, value)
        logger.warning("Restored %s from backup; damaged file preserved at %s", path, damaged_path)
    except OSError:
        logger.exception("Could not restore damaged JSON file %s from backup", path)
    return value


def save_json(path, value):
    """Atomically save JSON and keep the previous valid file as a backup."""
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    backup = path + ".bak"
    if os.path.exists(path):
        try:
            _read(path, (dict, list))
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            logger.error("Not backing up invalid JSON before replacing %s", path)
        else:
            backup_temp = backup + ".tmp"
            try:
                shutil.copy2(path, backup_temp)
                os.replace(backup_temp, backup)
            finally:
                if os.path.exists(backup_temp):
                    os.remove(backup_temp)
    _atomic_write(path, value)
    backup_valid = False
    try:
        _read(backup, (dict, list))
        backup_valid = True
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
        pass
    if not backup_valid:
        backup_temp = backup + ".tmp"
        try:
            shutil.copy2(path, backup_temp)
            os.replace(backup_temp, backup)
        finally:
            if os.path.exists(backup_temp):
                os.remove(backup_temp)
