from uac_parser.grok_patterns import process_patterns, custom_patterns
from pygrok import Grok
import os
import logging
from datetime import datetime
from tqdm import tqdm
from uac_parser.models import Process


def parse_processes(uac_collection_path: str, threshold: int = 75):
    """
    Parse process files from the live_response/process directory and correlate
    values from multiple grok patterns based on the common 'command' value.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        threshold: Minimum percentage of lines that must match a pattern to be used (default: 75)
        
    Returns:
        List of Process objects
    """
    process_dir = os.path.join(uac_collection_path, "live_response", "process")
    logging.info(f"Parsing processes from: {process_dir}")
    
    if not os.path.exists(process_dir):
        logging.warning(f"Process directory not found at {process_dir}")
        return []
    
    # Dictionary to store process data by command
    # Key: command, Value: dict of process attributes
    process_map = {}
    
    # Get all files in the process directory
    try:
        process_files = [f for f in os.listdir(process_dir) if os.path.isfile(os.path.join(process_dir, f))]
    except OSError as e:
        logging.error(f"Failed to list process directory: {e}")
        return []
    
    logging.info(f"Found {len(process_files)} files in process directory")
    
    # Try each grok pattern against each file
    for filename in tqdm(process_files, desc="Parsing process files", unit="files"):
        file_path = os.path.join(process_dir, filename)
        
        # Try all available grok patterns
        for pattern_name, pattern in process_patterns.items():
            logging.debug(f"Trying pattern {pattern_name} on file {filename}")
            
            try:
                grok = Grok(pattern, custom_patterns=custom_patterns)
            except Exception as e:
                logging.warning(f"Failed to compile pattern {pattern_name}: {e}")
                continue
            
            # Count total lines for progress bar
            try:
                with open(file_path, 'r') as f:
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
                with open(file_path, 'r') as f:
                    for line_num, line in enumerate(f, 1):
                        match = grok.match(line)
                        if match:
                            match_count += 1
                            current_matches.append(match)
            except Exception as e:
                logging.warning(f"Error parsing {filename} with pattern {pattern_name}: {e}")
                continue
            
            # Calculate match percentage
            match_percentage = (match_count / total_lines) * 100
            
            if match_percentage >= threshold:
                logging.info(f"Pattern {pattern_name} matched {match_count}/{total_lines} lines ({match_percentage:.1f}%) in {filename}. Merging results.")
                
                # Merge matches into main process map
                for match in current_matches:
                    command = match.get('command')
                    if not command:
                        continue
                    
                    # Initialize process entry if not exists
                    if command not in process_map:
                        process_map[command] = {'command': command}
                    
                    # Merge matched fields into the process entry
                    for key, value in match.items():
                        if value and key != 'command':  # Don't overwrite command
                            # Only set if not already set (first match wins)
                            if key not in process_map[command]:
                                process_map[command][key] = value
            else:
                if match_count > 0:
                    logging.info(f"Discarding results for {filename} + {pattern_name}: matched only {match_count}/{total_lines} lines ({match_percentage:.1f}%) which is below threshold {threshold}%")
                else:
                    logging.debug(f"Pattern {pattern_name} had no matches in {filename}")
    
    # Convert process_map to Process objects
    processes = []
    for command_str, attrs in tqdm(process_map.items(), desc="Creating Process objects", unit="processes"):
        # Parse started timestamp to DateTime
        started_dt = None
        if attrs.get('started'):
            try:
                # Format: "Sun Nov 16 19:25:29 2025"
                started_dt = datetime.strptime(attrs.get('started'), "%a %b %d %H:%M:%S %Y")
            except (ValueError, TypeError) as e:
                logging.debug(f"Failed to parse started time '{attrs.get('started')}': {e}")
        
        # Split command into executable and arguments
        command_path = command_str
        arguments = None
        if command_str:
            parts = command_str.split(None, 1)  # Split on first whitespace
            if len(parts) > 0:
                command_path = parts[0]
            if len(parts) > 1:
                arguments = parts[1]
        
        # Helper to safely convert to int
        def safe_int(val):
            if not val:
                return None
            try:
                return int(val)
            except (ValueError, TypeError):
                # Try to handle float strings like "00.30" by converting to float then int
                try:
                    return int(float(val))
                except (ValueError, TypeError):
                    return None

        process_obj = Process(
            pid=safe_int(attrs.get('pid')),
            ppid=safe_int(attrs.get('ppid')),
            uid=safe_int(attrs.get('uid')),
            user=attrs.get('user'),
            started=started_dt,
            command=command_path,
            arguments=arguments
        )
        processes.append(process_obj)
    
    logging.info(f"Parsed {len(processes)} processes before deduplication")

    # Deduplicate by PID
    pid_map = {}
    deduplicated_processes = []
    
    # Handle processes without PID separately (keep them)
    for p in processes:
        if p.pid is None:
            deduplicated_processes.append(p)
        else:
            if p.pid not in pid_map:
                pid_map[p.pid] = []
            pid_map[p.pid].append(p)
            
    # For each PID, keep the one with most populated fields
    for pid, proc_list in pid_map.items():
        if len(proc_list) == 1:
            deduplicated_processes.append(proc_list[0])
        else:
            # Count non-None fields for each process
            # Fields to check: ppid, uid, user, started, command, arguments
            best_proc = max(proc_list, key=lambda p: sum(1 for f in [p.ppid, p.uid, p.user, p.started, p.command, p.arguments] if f is not None))
            deduplicated_processes.append(best_proc)
            
    logging.info(f"Deduplicated to {len(deduplicated_processes)} unique processes")
    return deduplicated_processes
