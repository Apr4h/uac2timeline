"""
Utility functions for parsing data from grok pattern matches.
"""
import logging
from datetime import datetime
from typing import Optional, Dict, Any


def parse_timestamp_from_match(match: Dict[str, Any]) -> Optional[datetime]:
    """
    Parse a timestamp from a grok pattern match dictionary.
    
    Tries multiple common timestamp formats and fields:
    - ISO 8601 timestamp (TIMESTAMP_ISO8601 field)
    - Individual date/time components (day, month, monthday, hour, minute, year)
    - 'timestamp' field with various formats
    
    Args:
        match: Dictionary of matched fields from a grok pattern
        
    Returns:
        datetime object if parsing succeeds, None otherwise
    """
    if not match:
        return None
    
    # Try ISO 8601 timestamp field (most common in logs)
    if 'TIMESTAMP_ISO8601' in match:
        timestamp_str = match['TIMESTAMP_ISO8601']
        if timestamp_str:
            try:
                # Handle timezone info - strip it for simplicity
                timestamp_str = timestamp_str.split('+')[0].split('-')[0]
                # Try with microseconds
                if '.' in timestamp_str:
                    return datetime.fromisoformat(timestamp_str)
                else:
                    # Try without microseconds
                    return datetime.strptime(timestamp_str[:19], "%Y-%m-%dT%H:%M:%S")
            except (ValueError, IndexError) as e:
                logging.debug(f"Failed to parse TIMESTAMP_ISO8601 '{timestamp_str}': {e}")
    
    # Try generic 'timestamp' field
    if 'timestamp' in match:
        timestamp_str = match['timestamp']
        if timestamp_str:
            try:
                # Remove timezone suffix for parsing
                cleaned = timestamp_str.replace('+00:00', '').replace('Z', '')
                # Try ISO format
                if 'T' in cleaned:
                    if '.' in cleaned:
                        # With microseconds
                        return datetime.fromisoformat(cleaned)
                    else:
                        # Without microseconds
                        return datetime.strptime(cleaned[:19], "%Y-%m-%dT%H:%M:%S")
                # Try other common formats
                return datetime.fromisoformat(cleaned)
            except (ValueError, IndexError) as e:
                logging.debug(f"Failed to parse timestamp '{timestamp_str}': {e}")
    
    # Try day/month/monthday/hour/minute components (e.g., from 'last' command)
    # Format: "Sat Nov 22 16:58" (no year, use current year)
    if all(key in match for key in ['day', 'month', 'monthday', 'hour', 'minute']):
        day = match['day']
        month = match['month']
        monthday = match['monthday']
        hour = match['hour']
        minute = match['minute']
        
        if all([day, month, monthday, hour, minute]):
            # Use current year if not provided
            year = match.get('year', datetime.now().year)
            time_str = f"{day} {month} {monthday} {hour}:{minute} {year}"
            try:
                return datetime.strptime(time_str, "%a %b %d %H:%M %Y")
            except ValueError as e:
                logging.debug(f"Failed to parse component time '{time_str}': {e}")
    
    # Try syslog format: Month Day HH:MM:SS
    if all(key in match for key in ['MONTH', 'MONTHDAY', 'TIME']):
        month = match['MONTH']
        monthday = match['MONTHDAY']
        time = match['TIME']
        
        if all([month, monthday, time]):
            year = match.get('YEAR', datetime.now().year)
            time_str = f"{month} {monthday} {year} {time}"
            try:
                return datetime.strptime(time_str, "%b %d %Y %H:%M:%S")
            except ValueError as e:
                logging.debug(f"Failed to parse syslog time '{time_str}': {e}")
    
    # No timestamp found or parseable
    return None


def safe_int(value: Any) -> Optional[int]:
    """
    Safely convert a value to an integer.
    
    Handles various edge cases:
    - None values
    - Empty strings
    - Float strings (e.g., "00.30" -> 0)
    - Invalid formats
    
    Args:
        value: Value to convert
        
    Returns:
        Integer if conversion succeeds, None otherwise
    """
    if not value:
        return None
    
    try:
        return int(value)
    except (ValueError, TypeError):
        # Try to handle float strings
        try:
            return int(float(value))
        except (ValueError, TypeError):
            return None
