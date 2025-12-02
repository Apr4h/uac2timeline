from uac_parser.grok_patterns import network_patterns, custom_patterns
from pygrok import Grok
import os
import logging
from tqdm import tqdm
from uac_parser.models import NetworkConnection


def parse_network_connections(uac_collection_path: str, threshold: int = 75):
    """
    Parse network connection files from the live_response/network directory.
    
    Args:
        uac_collection_path: Path to the UAC collection directory
        threshold: Minimum percentage of lines that must match a pattern to be used (default: 75)
        
    Returns:
        List of NetworkConnection objects
    """
    network_dir = os.path.join(uac_collection_path, "live_response", "network")
    logging.info(f"Parsing network connections from: {network_dir}")
    
    if not os.path.exists(network_dir):
        logging.warning(f"Network directory not found at {network_dir}")
        return []
    
    # Get all files in the network directory
    try:
        network_files = [f for f in os.listdir(network_dir) if os.path.isfile(os.path.join(network_dir, f))]
    except OSError as e:
        logging.error(f"Failed to list network directory: {e}")
        return []
    
    logging.info(f"Found {len(network_files)} files in network directory")
    
    network_connections = []
    
    # Try each grok pattern against each file
    for filename in tqdm(network_files, desc="Parsing network files", unit="files"):
        file_path = os.path.join(network_dir, filename)
        
        # Try all available grok patterns
        for pattern_name, pattern in network_patterns.items():
            logging.debug(f"Trying pattern {pattern_name} on file {filename}")
            
            try:
                grok = Grok(pattern, custom_patterns=custom_patterns)
            except Exception as e:
                logging.warning(f"Failed to compile pattern {pattern_name}: {e}")
                continue
            
            # Count total lines for progress bar and threshold
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
                
                for match in current_matches:
                    # Helper to safely convert to int
                    def safe_int(val):
                        if not val:
                            return None
                        try:
                            return int(val)
                        except (ValueError, TypeError):
                            return None

                    # Helper to safely convert port to int
                    def safe_port(val):
                        if not val:
                            return None
                        if val == '*':
                            return 0
                        try:
                            port = int(val)
                            if 0 <= port <= 65535:
                                return port
                            return None
                        except (ValueError, TypeError):
                            return None

                    # All patterns now use standardized field names
                    local_addr = match.get('local_addr')
                    local_port = match.get('local_port')
                    remote_addr = match.get('remote_addr')
                    remote_port = match.get('remote_port')

                    state = match.get('state')
                    if state:
                        state = state.upper()

                    nc = NetworkConnection(
                        proto=match.get('proto'),
                        local_addr=local_addr,
                        local_port=safe_port(local_port),
                        remote_addr=remote_addr,
                        remote_port=safe_port(remote_port),
                        state=state,
                        pid=safe_int(match.get('pid'))
                    )
                    
                    # Add to list (will deduplicate later)
                    network_connections.append(nc)
            else:
                if match_count > 0:
                    logging.info(f"Discarding results for {filename} + {pattern_name}: matched only {match_count}/{total_lines} lines ({match_percentage:.1f}%) which is below threshold {threshold}%")
                else:
                    logging.debug(f"Pattern {pattern_name} had no matches in {filename}")
            
    # Deduplicate based on local/remote ip/port, state, and pid
    unique_connections = {}
    for nc in network_connections:
        key = (nc.local_addr, nc.local_port, nc.remote_addr, nc.remote_port, nc.state, nc.pid)
        if key not in unique_connections:
            unique_connections[key] = nc
        else:
            # Optional: Merge logic if needed, but for now just keep the first one
            # or maybe keep the one with more info if that was applicable.
            # Since grok pattern is the same, first one is fine.
            pass
            
    deduplicated_list = list(unique_connections.values())
    logging.info(f"Parsed {len(network_connections)} connections, deduplicated to {len(deduplicated_list)}")
    return deduplicated_list
