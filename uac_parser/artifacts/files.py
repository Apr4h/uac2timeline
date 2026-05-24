from uac_parser.grok_patterns import bodyfile_patterns, custom_patterns
from uac_parser.grok import Grok
import os
import logging
from tqdm import tqdm
import datetime
from uac_parser.models import File


def _epoch_to_dt(val) -> datetime.datetime | None:
    if val is None:
        return None
    try:
        return datetime.datetime.utcfromtimestamp(int(val))
    except (ValueError, TypeError, OSError):
        return None


def parse_bodyfile(uac_collection_path: str):
    bodyfile_path = os.path.join(uac_collection_path, "bodyfile", "bodyfile.txt")
    logging.info(f"Parsing bodyfile: {bodyfile_path}")

    files = []
    grok = Grok(bodyfile_patterns["bodyfile_v3"], custom_patterns=custom_patterns)

    if not os.path.exists(bodyfile_path):
        logging.warning(f"Bodyfile not found at {bodyfile_path}")
        return files

    # Count total lines for progress bar
    with open(bodyfile_path, 'r') as f:
        total_lines = sum(1 for _ in f)

    with open(bodyfile_path, 'r') as f:
        for line in tqdm(f, total=total_lines, desc="Parsing bodyfile", unit="lines"):
            match = grok.match(line)
            if match:
                raw_md5 = match.get('md5')
                file_obj = File(
                    md5=None if (not raw_md5 or raw_md5 == '0') else raw_md5,
                    path=match.get('file_path'),
                    inode=int(match.get('inode', 0)) if match.get('inode') else None,
                    mode=match.get('mode_as_string'),
                    uid=int(match.get('uid', 0)) if match.get('uid') else None,
                    gid=int(match.get('gid', 0)) if match.get('gid') else None,
                    size=int(match.get('size', 0)) if match.get('size') else None,
                    atime=_epoch_to_dt(match.get('atime')),
                    mtime=_epoch_to_dt(match.get('mtime')),
                    ctime=_epoch_to_dt(match.get('ctime')),
                    crtime=_epoch_to_dt(match.get('crtime')),
                )
                files.append(file_obj)

    hash_map = parse_hash_executables(uac_collection_path)
    if hash_map:
        for f in files:
            if f.path and f.path in hash_map:
                f.md5 = hash_map[f.path]

    return files


def parse_hash_executables(uac_collection_path: str) -> dict:
    """
    Parse the hash_executables.md5 file and return a dictionary mapping file paths to MD5 hashes.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        
    Returns:
        Dictionary with file paths as keys and MD5 hashes as values
    """
    hash_file_path = os.path.join(uac_collection_path, "hash_executables", "hash_executables.md5")
    logging.info(f"Parsing hash executables: {hash_file_path}")
    
    hash_map = {}
    
    if not os.path.exists(hash_file_path):
        logging.warning(f"Hash executables file not found at {hash_file_path}")
        return hash_map
    
    # Count total lines for progress bar
    with open(hash_file_path, 'r') as f:
        total_lines = sum(1 for _ in f)
    
    with open(hash_file_path, 'r') as f:
        for line in tqdm(f, total=total_lines, desc="Parsing hash executables", unit="lines"):
            line = line.strip()
            if not line:
                continue
            
            # Format: "md5hash  /path/to/file"
            # Split on two spaces (standard md5sum format)
            parts = line.split('  ', 1)
            if len(parts) == 2:
                md5_hash = parts[0].strip()
                file_path = parts[1].strip()
                hash_map[file_path] = md5_hash
            else:
                logging.debug(f"Skipping malformed line: {line}")
    
    logging.info(f"Parsed {len(hash_map)} MD5 hashes from hash_executables.md5")
    return hash_map