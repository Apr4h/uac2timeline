import argparse
import logging
from uac_parser.parser import parse_uac_collection
from uac_parser.database import init_db, get_session, DEFAULT_DB_NAME
from uac_parser.models import UACCollection

def cmd_collect(args):
    """Handle the 'collect' subcommand."""
    logging.basicConfig(level=logging.INFO, format='%(levelname)s - %(message)s')
    parse_uac_collection(args.input, threshold=args.threshold)

def cmd_show_collections(args):
    """Handle the 'show collections' subcommand."""
    db_path = args.database or DEFAULT_DB_NAME
    
    engine = init_db(db_path)
    session = get_session(engine)
    
    collections = session.query(UACCollection).all()
    
    if not collections:
        print(f"No collections found in database: {db_path}")
        session.close()
        return
    
    print(f"\n{'ID':<5} {'Hostname':<30} {'OS':<30} {'Created':<20} {'MD5':<32}")
    print("-" * 120)
    
    for col in collections:
        md5_short = col.uac_log_md5[:8] if col.uac_log_md5 else "N/A"
        created_str = col.created_at.strftime("%Y-%m-%d %H:%M:%S") if col.created_at else "N/A"
        hostname = (col.hostname[:27] + "...") if len(col.hostname) > 30 else col.hostname
        os_str = (col.os[:27] + "...") if col.os and len(col.os) > 30 else (col.os or "N/A")
        
        print(f"{col.id:<5} {hostname:<30} {os_str:<30} {created_str:<20} {md5_short:<32}")
    
    print(f"\nTotal collections: {len(collections)}")
    session.close()

def main():
    parser = argparse.ArgumentParser(
        description="UAC Timeline - Process UAC collections and manage artifact databases"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Collect subcommand
    parser_collect = subparsers.add_parser(
        'collect',
        help='Parse a UAC collection and store artifacts in database'
    )
    parser_collect.add_argument(
        "-i", "--input",
        required=True,
        help="Path to UAC collection directory"
    )
    parser_collect.add_argument(
        "-t", "--threshold",
        type=int,
        default=75,
        help="Parsing threshold percentage (default: 75)"
    )
    parser_collect.set_defaults(func=cmd_collect)
    
    # Show subcommand
    parser_show = subparsers.add_parser(
        'show',
        help='Display information from the database'
    )
    show_subparsers = parser_show.add_subparsers(dest='show_command', help='What to show')
    
    # Show collections subcommand
    parser_show_collections = show_subparsers.add_parser(
        'collections',
        help='List all collections in the database'
    )
    parser_show_collections.add_argument(
        "-d", "--database",
        help=f"Path to database file (default: {DEFAULT_DB_NAME})"
    )
    parser_show_collections.set_defaults(func=cmd_show_collections)
    
    args = parser.parse_args()
    
    # If no subcommand provided, print help
    if not hasattr(args, 'func'):
        parser.print_help()
        return
    
    # Execute the appropriate function
    args.func(args)
    