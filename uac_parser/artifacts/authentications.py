from uac_parser.grok_patterns import auth_patterns, custom_patterns
from pygrok import Grok
import os
import logging
from datetime import datetime
from tqdm import tqdm
from uac_parser.models import Authentication
from uac_parser.utils import parse_timestamp_from_match


def parse_authentications(uac_collection_path: str, threshold: int = 75):
    """
    Parse authentication files from the live_response/system directory and [root]/var/log.
    
    Note: Unlike process/network parsers, authentication parsing does NOT use threshold-based
    filtering because auth logs typically contain many non-authentication lines. All matching
    authentication events are captured regardless of the overall match percentage.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        threshold: Ignored (kept for API compatibility with other parsers)
        
    Returns:
        List of Authentication objects
    """
    logging.info("Parsing authentication logs")
    
    # Two directories to search
    search_dirs = [
        os.path.join(uac_collection_path, "live_response", "system"),
        os.path.join(uac_collection_path, "[root]", "var", "log")
    ]
    
    
    all_files = []
    
    # Collect all files from both directories
    for search_dir in search_dirs:
        if not os.path.exists(search_dir):
            logging.debug(f"Directory not found: {search_dir}")
            continue
            
        logging.info(f"Searching for auth files in: {search_dir}")
        
        try:
            # For live_response/system, filter for auth-related files
            if "live_response" in search_dir:
                files = [
                    os.path.join(search_dir, f) 
                    for f in os.listdir(search_dir) 
                    if os.path.isfile(os.path.join(search_dir, f))
                ]
                
                # Filter for auth-related files
                auth_files = [
                    f for f in files 
                    if any(keyword in os.path.basename(f).lower() 
                           for keyword in ['auth', 'last', 'secure', 'wtmp', 'btmp', 'login'])
                ]
                
                all_files.extend(auth_files)
                logging.info(f"Found {len(auth_files)} auth-related files in {search_dir}")
            
            # For [root]/var/log, recursively scan ALL files
            else:
                file_count = 0
                for dirpath, dirnames, filenames in os.walk(search_dir):
                    for filename in filenames:
                        file_path = os.path.join(dirpath, filename)
                        # Skip binary files and compressed files (they won't have parseable text)
                        if not filename.endswith(('.gz', '.bz2', '.xz', '.zip', '.tar')):
                            all_files.append(file_path)
                            file_count += 1
                
                logging.info(f"Found {file_count} files (recursive) in {search_dir}")
            
        except OSError as e:
            logging.error(f"Failed to list directory {search_dir}: {e}")
            continue
    
    if not all_files:
        logging.warning("No authentication files found")
        return []
    
    logging.info(f"Total authentication files to process: {len(all_files)}")
    
    authentications = []
    
    # Try each grok pattern against each file
    for file_path in tqdm(all_files, desc="Parsing authentication files", unit="files"):
        filename = os.path.basename(file_path)
        
        # Try all available grok patterns
        for pattern_name, pattern in auth_patterns.items():
            logging.debug(f"Trying pattern {pattern_name} on file {filename}")
            
            try:
                grok = Grok(pattern, custom_patterns=custom_patterns)
            except Exception as e:
                logging.warning(f"Failed to compile pattern {pattern_name}: {e}")
                continue
            
            # Count total lines for threshold calculation
            try:
                with open(file_path, 'r', errors='ignore') as f:
                    total_lines = sum(1 for _ in f)
            except Exception as e:
                logging.warning(f"Failed to read file {filename}: {e}")
                continue
                
            if total_lines == 0:
                continue
            
            # Track matches for this specific file/pattern combination
            current_matches = []
            match_count = 0
            
            # Parse the file with this pattern
            try:
                with open(file_path, 'r', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        match = grok.match(line)
                        if match:
                            match_count += 1
                            current_matches.append(match)
            except Exception as e:
                logging.warning(f"Error parsing {filename} with pattern {pattern_name}: {e}")
                continue
            
            # Process all matches (no threshold check for authentication logs)
            if match_count > 0:
                logging.info(f"Pattern {pattern_name} matched {match_count}/{total_lines} lines ({(match_count/total_lines)*100:.1f}%) in {filename}. Processing results.")
                
                for match in current_matches:
                    auth_obj = create_authentication_from_match(match, pattern_name)
                    if auth_obj:
                        authentications.append(auth_obj)
            else:
                logging.debug(f"Pattern {pattern_name} had no matches in {filename}")
    
    # Deduplicate based on key fields
    unique_auths = {}
    for auth in authentications:
        # Create a key based on username, time, source, method
        # Use str() to handle None values
        key = (
            str(auth.username),
            str(auth.time),
            str(auth.source),
            str(auth.method),
            str(auth.result)
        )
        if key not in unique_auths:
            unique_auths[key] = auth
    
    deduplicated_list = list(unique_auths.values())
    logging.info(f"Parsed {len(authentications)} authentications, deduplicated to {len(deduplicated_list)}")
    return deduplicated_list


def create_authentication_from_match(match: dict, pattern_name: str) -> Authentication:
    """
    Create an Authentication object from a grok match.
    
    Args:
        match: Dictionary of matched fields from grok pattern
        pattern_name: Name of the pattern that matched
        
    Returns:
        Authentication object or None if creation fails
    """
    try:
        # Parse timestamp using utility function
        auth_time = parse_timestamp_from_match(match)
        
        # Determine authentication method and result based on pattern
        method = None
        result = None
        source = None
        destination = None
        uid = None
        
        if pattern_name == "LAST_LOGIN":
            method = "console"
            result = "success"
            source = match.get('tty')
            
        elif pattern_name == "SSH_AUTH_SUCCESS":
            method = match.get('auth_method', 'ssh')
            result = "success"
            source = match.get('source')
            # Extract username from 'user' field
            if 'user' in match:
                match['username'] = match['user']
        
        # Create Authentication object
        auth = Authentication(
            username=match.get('username'),
            time=auth_time,
            method=method,
            result=result,
            source=source,
            destination=destination,
            uid=uid
        )
        
        return auth
        
    except Exception as e:
        logging.warning(f"Failed to create Authentication from match: {e}")
        return None
