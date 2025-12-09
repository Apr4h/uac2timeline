from rich.console import Console
from rich.table import Table
from uac_parser.database import init_db, get_session, DEFAULT_DB_NAME
from uac_parser.models import UACCollection


def cmd_show_collections(args):
    """Handle the 'show collections' subcommand."""
    db_path = args.database or DEFAULT_DB_NAME
    
    engine = init_db(db_path)
    session = get_session(engine)
    
    collections = session.query(UACCollection).all()
    
    if not collections:
        console = Console()
        console.print(f"[yellow]No collections found in database: {db_path}[/yellow]")
        session.close()
        return
    
    # Create a Rich table
    table = Table(title=f"UAC Collections ({db_path})", show_header=True, header_style="bold magenta")
    
    # Add columns
    table.add_column("ID", style="cyan", justify="right", width=5)
    table.add_column("Hostname", style="green", width=25)
    table.add_column("OS", style="blue", width=15)
    table.add_column("Timezone", style="yellow", width=10)
    table.add_column("Created", style="white", width=20)
    table.add_column("Log File MD5", style="red", width=10)
    
    # Add rows
    for col in collections:
        md5_short = col.uac_log_md5[:8] if col.uac_log_md5 else "N/A"
        created_str = col.created_at.strftime("%Y-%m-%d %H:%M:%S") if col.created_at else "N/A"
        hostname = (col.hostname[:22] + "...") if len(col.hostname) > 25 else col.hostname
        os_str = (col.os[:12] + "...") if col.os and len(col.os) > 15 else (col.os or "N/A")
        tz_str = col.timezone_setting or "N/A"
        
        table.add_row(
            str(col.id),
            hostname,
            os_str,
            tz_str,
            created_str,
            md5_short
        )
    
    # Print the table
    console = Console()
    console.print(table)
    console.print(f"\n[bold green]Total collections:[/bold green] {len(collections)}")
    
    session.close()
