import logging
import os
import hashlib
from .models import UACCollection, File
from .database import DEFAULT_DB_NAME
from .grok_patterns import bodyfile_patterns
from pygrok import Grok
import datetime
from tqdm import tqdm
from .artifacts.files import parse_bodyfile, parse_hash_executables
from .artifacts.processes import parse_processes
from .artifacts.netconns import parse_network_connections
from .database import check_existing_collection


def parse_uac_collection(uac_collection_path: str, output_db_path: str = DEFAULT_DB_NAME, threshold: int = 75) -> None:
    logging.info(f"Parsing UAC collection: {uac_collection_path}")

    metadata = get_collection_metadata(uac_collection_path)
    if not metadata:
        logging.error("Failed to get metadata for UAC collection")
        return


    # Check for duplicate collection based on MD5
    if metadata.get("uac_log_md5"):
        
        existing = check_existing_collection(metadata["uac_log_md5"], output_db_path)
        if existing:
            logging.warning(f"Collection already exists in database (MD5: {metadata['uac_log_md5']})")
            logging.warning(f"Existing collection: hostname={existing.hostname}, created={existing.created_at}")
            logging.info("Skipping duplicate collection import")
            return


    # files = parse_bodyfile(uac_collection_path)
    
    # Parse hash executables and associate with files
    # hash_map = parse_hash_executables(uac_collection_path)
    # if hash_map:
    #     logging.info(f"Associating MD5 hashes with {len(files)} files")
    #     for file_obj in files:
    #         if file_obj.path and file_obj.path in hash_map:
    #             file_obj.md5 = hash_map[file_obj.path]
    
    processes = parse_processes(uac_collection_path, threshold=threshold)
    netconns = parse_network_connections(uac_collection_path)
    # logins = parse_logins(uac_collection_path)
    # commands = parse_commands(uac_collection_path)

    uac_collection = UACCollection(**metadata)
    # uac_collection.files = files
    uac_collection.processes = processes
    uac_collection.network_connections = netconns
    
    uac_collection.commit(output_db_path)
    logging.info("UAC collection parsed successfully")


def get_collection_metadata(uac_collection_path: str):
    logging.info(f"Getting metadata for UAC collection: {uac_collection_path}")

    meta = {
        "hostname": None,
        "os": None,
        "uac_log_md5": None,
    }

    uac_log_path = os.path.join(uac_collection_path, "uac.log")

    try:
        # Calculate MD5 hash of uac.log
        md5_hash = hashlib.md5()
        with open(uac_log_path, "rb") as f:
            # Read in chunks for memory efficiency
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)
        meta["uac_log_md5"] = md5_hash.hexdigest()
        
        # Parse metadata from uac.log
        with open(uac_log_path, "r") as f:
            for line in f:
                if "Hostname: " in line:
                    meta["hostname"] = line.split(":")[-1].strip()
                if "Operating system" in line:
                    meta["os"] = line.split(":")[-1].strip()
    except FileNotFoundError:
        logging.error(f"UAC log not found at: {uac_log_path}")
        return None

    return meta