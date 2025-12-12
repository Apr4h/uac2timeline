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


def cmd_show_stats(args):
    """Handle the 'show stats' subcommand."""
    db_path = args.database or DEFAULT_DB_NAME
    collection_id = args.collection_id
    
    engine = init_db(db_path)
    session = get_session(engine)
    
    # Get the specified collection
    from uac_parser.models import Process, NetworkConnection, CommandHistory, Authentication
    collection = session.query(UACCollection).filter_by(id=collection_id).first()
    
    console = Console()
    
    if not collection:
        console.print(f"[red]Collection with ID {collection_id} not found in database: {db_path}[/red]")
        session.close()
        return
    
    # Collection metadata table
    meta_table = Table(title=f"Collection Metadata (ID: {collection_id})", show_header=True, header_style="bold magenta")
    meta_table.add_column("Property", style="cyan", width=20)
    meta_table.add_column("Value", style="white")
    
    meta_table.add_row("Hostname", collection.hostname or "N/A")
    meta_table.add_row("Operating System", collection.os or "N/A")
    meta_table.add_row("Primary IP", collection.primary_ip_address or "N/A")
    meta_table.add_row("Timezone", collection.timezone_setting or "N/A")
    meta_table.add_row("Created At", collection.created_at.strftime("%Y-%m-%d %H:%M:%S") if collection.created_at else "N/A")
    meta_table.add_row("UAC Log MD5", collection.uac_log_md5 or "N/A")
    
    console.print(meta_table)
    console.print()
    
    # Artifact counts table
    stats_table = Table(title="Artifact Statistics", show_header=True, header_style="bold magenta")
    stats_table.add_column("Artifact Type", style="cyan", width=30)
    stats_table.add_column("Count", style="green", justify="right", width=15)
    
    # Count artifacts for this collection
    process_count = session.query(Process).filter_by(collection_id=collection_id).count()
    netconn_count = session.query(NetworkConnection).filter_by(collection_id=collection_id).count()
    cmdhistory_count = session.query(CommandHistory).filter_by(collection_id=collection_id).count()
    auth_count = session.query(Authentication).filter_by(collection_id=collection_id).count()
    
    stats_table.add_row("Processes", str(process_count))
    stats_table.add_row("Network Connections", str(netconn_count))
    stats_table.add_row("Command History Entries", str(cmdhistory_count))
    stats_table.add_row("Authentication Events", str(auth_count))
    
    # Calculate total
    total_artifacts = process_count + netconn_count + cmdhistory_count + auth_count
    stats_table.add_row("[bold]Total Artifacts[/bold]", f"[bold]{total_artifacts}[/bold]")
    
    console.print(stats_table)
    console.print()
    
    # Authentication breakdown if there are any
    if auth_count > 0:
        auth_breakdown_table = Table(title="Authentication Breakdown by Method", show_header=True, header_style="bold magenta")
        auth_breakdown_table.add_column("Method", style="cyan", width=25)
        auth_breakdown_table.add_column("Count", style="green", justify="right", width=15)
        
        # Query authentication methods and their counts
        from sqlalchemy import func
        auth_methods = session.query(
            Authentication.method,
            func.count(Authentication.id).label('count')
        ).filter_by(collection_id=collection_id).group_by(Authentication.method).order_by(func.count(Authentication.id).desc()).all()
        
        for method, count in auth_methods:
            auth_breakdown_table.add_row(method or "Unknown", str(count))
        
        console.print(auth_breakdown_table)
        console.print()
    
    # Network connection breakdown if there are any
    if netconn_count > 0:
        netconn_breakdown_table = Table(title="Network Connections by State", show_header=True, header_style="bold magenta")
        netconn_breakdown_table.add_column("State", style="cyan", width=25)
        netconn_breakdown_table.add_column("Count", style="green", justify="right", width=15)
        
        # Query network connection states and their counts
        from sqlalchemy import func
        netconn_states = session.query(
            NetworkConnection.state,
            func.count(NetworkConnection.id).label('count')
        ).filter_by(collection_id=collection_id).group_by(NetworkConnection.state).order_by(func.count(NetworkConnection.id).desc()).all()
        
        for state, count in netconn_states:
            netconn_breakdown_table.add_row(state or "Unknown", str(count))
        
        console.print(netconn_breakdown_table)
    
    session.close()
