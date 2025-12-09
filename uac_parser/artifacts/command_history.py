import os
import logging
import datetime
from ..models import CommandHistory

command_history_files = [
    ".bash_history",
    ".zsh_history",
    ".sh_history",
    ".csh_history",
    ".tcsh_history",
    ".fish_history",
    ".mysql_history",
    ".psql_history",
    ".sqlite_history",
    ".python_history",
    ".ipython/profile_default/history.sqlite",
    ".node_repl_history",
    ".irb_history",
    ".Rhistory",
    ".ghci_history",
    ".lesshst",
    ".viminfo",
    ".wget-hsts",
    ".curl_history",
    ".gdb_history"
]

def parse_command_history(uac_collection_path: str):
    """
    Parse command history files from the UAC collection.
    
    Recursively searches [root] directory for history files and creates
    CommandHistory objects for each command line found.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        
    Returns:
        List of CommandHistory objects
    """
    logging.info("Parsing command history files")
    
    root_path = os.path.join(uac_collection_path, "[root]")
    
    if not os.path.exists(root_path):
        logging.warning(f"[root] directory not found at: {root_path}")
        return []
    
    history_entries = []
    
    # Recursively walk through all directories
    for dirpath, dirnames, filenames in os.walk(root_path):
        for filename in filenames:
            # Check if this file is a history file
            if filename in command_history_files or any(filename.endswith(hf) for hf in command_history_files):
                file_path = os.path.join(dirpath, filename)
                
                # Convert to absolute path from collection root (trim everything before and including [root])
                # Example: test_data/ubuntu_vm/[root]/home/apra/.bash_history -> /home/apra/.bash_history
                if '[root]' in file_path:
                    absolute_from_root = '/' + file_path.split('[root]/', 1)[1]
                else:
                    absolute_from_root = file_path
                
                # Extract user from path (typically /[root]/home/username or /[root]/Users/username)
                user = extract_user_from_path(file_path, root_path)
                
                # Get file modification time
                try:
                    mtime = os.path.getmtime(file_path)
                    file_time = datetime.datetime.fromtimestamp(mtime)
                except Exception as e:
                    logging.warning(f"Could not get mtime for {file_path}: {e}")
                    file_time = None
                
                # Parse the history file
                try:
                    with open(file_path, 'r', errors='ignore') as f:
                        for line_number, line in enumerate(f, start=1):
                            line = line.strip()
                            if not line:
                                continue
                            
                            # Skip metadata lines (common in bash history)
                            if line.startswith('#'):
                                continue
                            
                            history_entry = CommandHistory(
                                command=line,
                                user=user,
                                time=file_time,
                                history_file=absolute_from_root,
                                file_index=line_number
                            )
                            history_entries.append(history_entry)
                            
                except Exception as e:
                    logging.warning(f"Error parsing history file {file_path}: {e}")
    
    logging.info(f"Parsed {len(history_entries)} command history entries from {len(set(e.history_file for e in history_entries))} files")
    return history_entries

def extract_user_from_path(file_path: str, root_path: str) -> str:
    """
    Extract username from file path.
    
    Assumes paths like:
    - /path/to/[root]/home/username/...
    - /path/to/[root]/Users/username/...
    - /path/to/[root]/root/...
    
    Args:
        file_path: Full path to the history file
        root_path: Path to the [root] directory
        
    Returns:
        Username extracted from path, or 'unknown' if not found
    """
    # Remove the root_path prefix to get relative path
    relative_path = os.path.relpath(file_path, root_path)
    parts = relative_path.split(os.sep)
    
    # Common user home directory patterns
    if len(parts) >= 2:
        if parts[0] in ['home', 'Users']:
            # /home/username or /Users/username
            return parts[1]
        elif parts[0] == 'root':
            # /root directory
            return 'root'
    
    # Default to unknown if we can't determine
    return 'unknown'