import logging
from pathlib import Path
from core.hand_parser import parse_hand_history_file
from core.xml_hand_parser import parse_session_file

logger = logging.getLogger(__name__)


def missing_configured_folders(directories: list[str]) -> list[str]:
    """Which of the configured hand-history folders don't currently exist
    — used to surface a visible warning in the UI (a folder that's been
    moved/renamed since it was configured otherwise just silently
    contributes 0 hands, with only a log line to explain why)."""
    return [d for d in directories if not Path(d).is_dir()]


def parse_directory(directory: str | Path):
    """Returns (hands, errors, files_seen). A single .txt export or .xml
    session file can contain many hands, so files_seen and len(hands) are
    not the same thing.

    Manual iPoker exports routinely overlap in date range (e.g. re-exporting
    "all hands" without deleting the previous export), so the same hand_id
    can show up in multiple files. Hands are deduplicated by hand_id, first
    occurrence wins."""
    directory = Path(directory)
    hands = []
    errors = []
    files_seen = 0
    seen_ids = set()
    duplicates = 0
    for path in sorted(directory.rglob('*.txt')):
        files_seen += 1
        try:
            text = path.read_text(encoding='utf-8-sig', errors='replace')
            file_hands, file_errors = parse_hand_history_file(text)
            for h in file_hands:
                if h.hand_id in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(h.hand_id)
                hands.append(h)
            errors.extend((f"{path}#{gid}", msg) for gid, msg in file_errors)
        except Exception as exc:
            errors.append((str(path), str(exc)))
    for path in sorted(directory.rglob('*.xml')):
        files_seen += 1
        try:
            file_hands, file_errors = parse_session_file(path)
            for h in file_hands:
                if h.hand_id in seen_ids:
                    duplicates += 1
                    continue
                seen_ids.add(h.hand_id)
                hands.append(h)
            errors.extend((f"{path}#{gamecode}", msg) for gamecode, msg in file_errors)
        except Exception as exc:
            errors.append((str(path), str(exc)))
    if duplicates:
        logger.info("Skipped %d duplicate hands (same hand_id seen in multiple files)", duplicates)
    for key, msg in errors:
        logger.warning("Failed to parse %s: %s", key, msg)
    return hands, errors, files_seen


def parse_directory_incremental(directories: str | Path | list[str | Path], db):
    """Like parse_directory, but skips any file whose (mtime, size)
    fingerprint already matches a prior import recorded in `db` —
    avoids re-parsing raw hand-history text for files nothing has
    changed about, which is most of them on every launch after the
    first. Returns (new_hands, errors, files_parsed, files_skipped).
    Caller is responsible for calling db.mark_files_imported(...) with
    the returned fingerprints once the hands are actually committed.

    `directories` accepts one path or several — e.g. the client's own live
    per-hand XML folder (updated as soon as a hand finishes) alongside an
    older manual export folder. Hands are deduplicated by hand_id across
    ALL of them (first occurrence wins), and hand_id is also the database's
    own primary key (INSERT OR IGNORE), so the same hand showing up in two
    different sources — expected, since the live folder's history overlaps
    with anything already manually exported before it was wired up — never
    creates a duplicate row."""
    if isinstance(directories, (str, Path)):
        directories = [directories]
    directories = [Path(d) for d in directories]
    known = db.get_file_fingerprints()
    hands = []
    errors = []
    seen_ids = set()
    duplicates = 0
    files_parsed = 0
    files_skipped = 0
    new_fingerprints = []

    def _handle(path, file_hands, file_errors, err_key_fn):
        nonlocal duplicates
        for h in file_hands:
            if h.hand_id in seen_ids:
                duplicates += 1
                continue
            seen_ids.add(h.hand_id)
            hands.append(h)
        errors.extend((err_key_fn(key), msg) for key, msg in file_errors)

    for directory in directories:
        if not directory.is_dir():
            # A configured folder that's been moved, renamed, or deleted
            # since — rglob() would just silently yield nothing, which
            # reads to a customer as "the app found 0 hands" with no clue
            # why, rather than the actual, fixable cause.
            logger.warning("Configured hand-history folder not found, skipping: %s", directory)
            continue
        for path in sorted(directory.rglob('*.txt')):
            stat = path.stat()
            fp = (stat.st_mtime, stat.st_size)
            if known.get(str(path)) == fp:
                files_skipped += 1
                continue
            files_parsed += 1
            try:
                text = path.read_text(encoding='utf-8-sig', errors='replace')
                file_hands, file_errors = parse_hand_history_file(text)
                _handle(path, file_hands, file_errors, lambda gid: f"{path}#{gid}")
                new_fingerprints.append((str(path), fp[0], fp[1]))
            except Exception as exc:
                errors.append((str(path), str(exc)))
        for path in sorted(directory.rglob('*.xml')):
            stat = path.stat()
            fp = (stat.st_mtime, stat.st_size)
            if known.get(str(path)) == fp:
                files_skipped += 1
                continue
            files_parsed += 1
            try:
                file_hands, file_errors = parse_session_file(path)
                _handle(path, file_hands, file_errors, lambda gamecode: f"{path}#{gamecode}")
                new_fingerprints.append((str(path), fp[0], fp[1]))
            except Exception as exc:
                errors.append((str(path), str(exc)))

    if duplicates:
        logger.info("Skipped %d duplicate hands (same hand_id seen in multiple files)", duplicates)
    for key, msg in errors:
        logger.warning("Failed to parse %s: %s", key, msg)
    return hands, errors, files_parsed, files_skipped, new_fingerprints
