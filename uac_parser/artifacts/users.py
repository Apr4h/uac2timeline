import os
import logging
import plistlib
from uac_parser.grok import Grok
from uac_parser.grok_patterns import user_patterns, custom_patterns
from uac_parser.models import User
from uac_parser.utils import safe_int


def parse_users(uac_collection_path: str, collection_os: str = None):
    """
    Parse user account information from a UAC collection.
    
    For Linux: Parses /etc/passwd using grok patterns (default)
    For macOS: Parses plist files from /private/var/db/dslocal/nodes/Default/users
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        collection_os: Operating system type (defaults to Linux unless 'mac' or 'darwin')
        
    Returns:
        List of User objects
    """
    logging.info("Parsing user accounts")
    
    # Default to Linux unless explicitly Mac/Darwin
    if collection_os:
        os_lower = collection_os.lower()
        if os_lower in ('mac', 'darwin', 'macos'):
            return parse_mac_users(uac_collection_path)
    
    # Default to Linux for all other cases (including None)
    return parse_linux_users(uac_collection_path)


def parse_linux_users(uac_collection_path: str):
    """
    Parse Linux /etc/passwd file using grok patterns.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        
    Returns:
        List of User objects
    """
    passwd_path = os.path.join(uac_collection_path, "[root]", "etc", "passwd")
    
    if not os.path.exists(passwd_path):
        logging.warning(f"passwd file not found at: {passwd_path}")
        return []
    
    logging.info(f"Parsing Linux passwd file: {passwd_path}")
    
    users = []
    pattern_name = "ETC_PASSWD"
    
    if pattern_name not in user_patterns:
        logging.error(f"Pattern {pattern_name} not found in user_patterns")
        return []
    
    pattern = user_patterns[pattern_name]
    
    try:
        grok = Grok(pattern, custom_patterns=custom_patterns)
    except Exception as e:
        logging.error(f"Failed to compile pattern {pattern_name}: {e}")
        return []
    
    try:
        with open(passwd_path, 'r') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                
                match = grok.match(line)
                if match:
                    user = User(
                        username=match.get('user'),
                        uid=safe_int(match.get('uid')),
                        gid=safe_int(match.get('gid')),
                        gecos=match.get('gecos'),
                        home=match.get('home'),
                        shell=match.get('shell')
                    )
                    users.append(user)
                else:
                    logging.debug(f"Line {line_num} did not match pattern: {line}")
    
    except Exception as e:
        logging.error(f"Error parsing passwd file: {e}")
        return []
    
    logging.info(f"Parsed {len(users)} users from Linux passwd file")
    return users


def parse_mac_users(uac_collection_path: str):
    """
    Parse macOS user plist files.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        
    Returns:
        List of User objects
    """
    users_dir = os.path.join(
        uac_collection_path, 
        "[root]", 
        "private", 
        "var", 
        "db", 
        "dslocal", 
        "nodes", 
        "Default", 
        "users"
    )
    
    if not os.path.exists(users_dir):
        logging.warning(f"macOS users directory not found at: {users_dir}")
        return []
    
    logging.info(f"Parsing macOS user plist files from: {users_dir}")
    
    users = []
    
    try:
        plist_files = [f for f in os.listdir(users_dir) if f.endswith('.plist')]
        logging.info(f"Found {len(plist_files)} plist files")
        
        for plist_file in plist_files:
            plist_path = os.path.join(users_dir, plist_file)
            
            try:
                with open(plist_path, 'rb') as f:
                    plist_data = plistlib.load(f)
                
                # Extract user information from plist
                # macOS plist files store data in arrays for each field
                username = plist_data.get('name', [None])[0] if plist_data.get('name') else None
                uid = plist_data.get('uid', [None])[0] if plist_data.get('uid') else None
                gid = plist_data.get('gid', [None])[0] if plist_data.get('gid') else None
                home = plist_data.get('home', [None])[0] if plist_data.get('home') else None
                shell = plist_data.get('shell', [None])[0] if plist_data.get('shell') else None
                realname = plist_data.get('realname', [None])[0] if plist_data.get('realname') else None
                
                # Create user object if username exists
                if username:
                    user = User(
                        username=username,
                        uid=safe_int(uid),
                        gid=safe_int(gid),
                        gecos=realname,  # Use realname as gecos equivalent
                        home=home,
                        shell=shell
                    )
                    users.append(user)
                    
            except Exception as e:
                logging.warning(f"Failed to parse plist {plist_file}: {e}")
                continue
    
    except Exception as e:
        logging.error(f"Error reading macOS users directory: {e}")
        return []
    
    logging.info(f"Parsed {len(users)} users from macOS plist files")
    return users
