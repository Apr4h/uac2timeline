from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship
import datetime
from .database import init_db, get_session, Base


class UACCollection(Base):
    __tablename__ = 'uac_collections'

    id = Column(Integer, primary_key=True)
    hostname = Column(String, nullable=False)
    os = Column(String)
    uac_log_md5 = Column(String, index=True)  # MD5 hash of uac.log for duplicate detection
    primary_ip_address = Column(String)
    timezone_setting = Column(String)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


    system_info = relationship("SystemInfo", back_populates="collection", uselist=False)
    files = relationship("File", back_populates="collection")
    processes = relationship("Process", back_populates="collection")
    network_connections = relationship("NetworkConnection", back_populates="collection")
    authentications = relationship("Authentication", back_populates="collection")
    command_history = relationship("CommandHistory", back_populates="collection")
    users = relationship("User", back_populates="collection")
    cron_jobs = relationship("CronJob", back_populates="collection")
    systemd_services = relationship("SystemdService", back_populates="collection")
    rc_scripts = relationship("RcScript", back_populates="collection")
    syslog_entries = relationship("SyslogEntry", back_populates="collection")

    def __repr__(self):
        return f"<UACCollection(hostname='{self.hostname}')>"

    def commit(self, db_path):
        engine = init_db(db_path)
        session = get_session(engine)
        
        # Add the collection first to get its ID
        session.add(self)
        session.flush()  # Get the ID without committing
        
        # Set collection_id on all files
        for file in self.files:
            file.collection_id = self.id
        
        # Set collection_id on all processes
        for process in self.processes:
            process.collection_id = self.id

        # Set collection_id on all network connections
        for nc in self.network_connections:
            nc.collection_id = self.id
        
        # Set collection_id on all command history entries
        for cmd in self.command_history:
            cmd.collection_id = self.id
        
        # Set collection_id on all authentications
        for auth in self.authentications:
            auth.collection_id = self.id
        
        # Set collection_id on all users
        for user in self.users:
            user.collection_id = self.id
        
        # Bulk insert files and processes for better performance
        session.bulk_save_objects(self.files)
        session.bulk_save_objects(self.processes)
        
        session.bulk_save_objects(self.network_connections)
        session.bulk_save_objects(self.command_history)
        session.bulk_save_objects(self.authentications)
        session.bulk_save_objects(self.users)
        session.commit()


class File(Base):
    __tablename__ = 'files'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    path = Column(String)
    filename = Column(String)
    size = Column(Integer)
    md5 = Column(String)
    sha1 = Column(String)
    sha256 = Column(String)
    atime = Column(DateTime)
    mtime = Column(DateTime)
    ctime = Column(DateTime)
    crtime = Column(DateTime)
    inode = Column(Integer)
    mode = Column(String)
    uid = Column(Integer)
    gid = Column(Integer)
    rdev = Column(Integer)
    nlink = Column(Integer)
    flags = Column(Integer)
    btime = Column(Integer)
    dtime = Column(Integer)

    collection = relationship("UACCollection", back_populates="files")

    def __repr__(self):
        return f"<File(filename='{self.filename}')>"


class Process(Base):
    __tablename__ = 'processes'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    pid = Column(Integer)
    ppid = Column(Integer)
    uid = Column(Integer)
    user = Column(String)
    started = Column(DateTime)  # Store as DateTime object
    command = Column(String)  # Executable path
    arguments = Column(String)  # Command-line arguments

    collection = relationship("UACCollection", back_populates="processes")

    def __repr__(self):
        return f"<Process(pid={self.pid}, command='{self.command}')>"


class NetworkConnection(Base):
    __tablename__ = 'network_connections'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    proto = Column(String)
    local_addr = Column(String)
    local_port = Column(Integer)
    remote_addr = Column(String)
    remote_port = Column(Integer)
    state = Column(String)
    pid = Column(Integer)

    collection = relationship("UACCollection", back_populates="network_connections")

    def __repr__(self):
        return f"<NetworkConnection(proto='{self.proto}', local='{self.local_addr}:{self.local_port}', pid={self.pid})>"


class Authentication(Base):
    __tablename__ = 'authentications'

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    uid = Column(Integer)
    username = Column(String)
    result = Column(String)
    time = Column(DateTime)
    method = Column(String)
    source = Column(String)
    destination = Column(String)
    
    collection = relationship("UACCollection", back_populates="authentications")

    def __repr__(self):
        return f"<Authentication(pid={self.pid}, command='{self.command}')>"


class CommandHistory(Base):
    __tablename__ = 'command_history'

    command = Column(String)
    user = Column(String)
    time = Column(DateTime)
    history_file = Column(String)
    file_index = Column(Integer)

    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    collection = relationship("UACCollection", back_populates="command_history")
    

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))
    username = Column(String)
    uid = Column(Integer)
    gid = Column(Integer)
    gecos = Column(String)  # Full name / comment field
    home = Column(String)  # Home directory
    shell = Column(String)  # Login shell
    
    collection = relationship("UACCollection", back_populates="users")
    
    def __repr__(self):
        return f"<User(username='{self.username}', uid={self.uid})>"


class CronJob(Base):
    __tablename__ = 'cron_jobs'

    id             = Column(Integer, primary_key=True)
    collection_id  = Column(Integer, ForeignKey('uac_collections.id'))

    minute         = Column(String)   # cron minute field, or '@reboot' etc.
    hour           = Column(String)
    day_of_month   = Column(String)
    month          = Column(String)
    day_of_week    = Column(String)

    username       = Column(String)   # run-as user; filename for user crontabs
    command        = Column(String)

    source_file          = Column(String)   # e.g. /etc/cron.d/sysstat
    source_type          = Column(String)   # system | cron.d | user | cron.hourly | …
    source_file_modified = Column(DateTime) # UTC mtime of the source file

    collection = relationship("UACCollection", back_populates="cron_jobs")

    def __repr__(self):
        return f"<CronJob(source_type='{self.source_type}', command='{self.command}')>"


class SystemdService(Base):
    __tablename__ = 'systemd_services'

    id                   = Column(Integer, primary_key=True)
    collection_id        = Column(Integer, ForeignKey('uac_collections.id'))

    unit_name            = Column(String)
    unit_type            = Column(String)   # service | timer | socket | mount | path | target
    description          = Column(String)
    after                = Column(String)
    wants                = Column(String)
    requires             = Column(String)

    exec_start           = Column(String)
    exec_start_pre       = Column(String)
    exec_start_post      = Column(String)
    exec_stop            = Column(String)
    run_user             = Column(String)
    run_group            = Column(String)
    working_directory    = Column(String)
    service_type         = Column(String)   # simple | forking | oneshot | notify | dbus | idle
    restart              = Column(String)
    environment          = Column(String)
    wanted_by            = Column(String)

    source_file          = Column(String)   # filename only, e.g. ssh.service
    source_path          = Column(String)   # full path relative to [root]/
    source_dir_type      = Column(String)   # system | lib-system | runtime | user | lib-user | user-local
    source_file_modified = Column(DateTime)

    collection = relationship("UACCollection", back_populates="systemd_services")

    def __repr__(self):
        return f"<SystemdService(unit_name='{self.unit_name}', unit_type='{self.unit_type}')>"


class RcScript(Base):
    __tablename__ = 'rc_scripts'

    id                   = Column(Integer, primary_key=True)
    collection_id        = Column(Integer, ForeignKey('uac_collections.id'))

    path                 = Column(String)   # full path as on the original system
    source_type          = Column(String)   # system-init | profile | shellrc | bsd-rcd | profile-d | startup-item | session
    run_context          = Column(String)   # boot | login | interactive | logout | session
    username             = Column(String)   # None for system-wide files
    shell                = Column(String)   # bash | zsh | sh | ksh | csh | tcsh | unknown
    interpreter          = Column(String)   # shebang line content
    file_size            = Column(Integer)
    content_snippet      = Column(String)   # first N non-blank, non-comment lines (not shown in table columns)
    source_file_modified = Column(DateTime)

    collection = relationship("UACCollection", back_populates="rc_scripts")

    def __repr__(self):
        return f"<RcScript(path='{self.path}', source_type='{self.source_type}')>"


class SyslogEntry(Base):
    __tablename__ = 'syslog_entries'

    id           = Column(Integer, primary_key=True)
    collection_id = Column(Integer, ForeignKey('uac_collections.id'))

    timestamp    = Column(DateTime)          # parsed; None when no year can be inferred
    hostname     = Column(String)            # host field in the log line
    program      = Column(String)            # process/program name
    pid          = Column(Integer)           # optional PID from program[pid]
    severity     = Column(String)            # optional syslog severity label
    message      = Column(String)            # the log message body
    source_file  = Column(String)            # relative path of the source log file

    # Enriched fields populated by second-pass message parsing
    event_type   = Column(String)            # e.g. "ssh_login_success", "sudo_command"
    actor_user   = Column(String)            # user initiating the action
    target_user  = Column(String)            # user being acted upon (sudo -u, su to)
    source_ip    = Column(String)            # source IP for SSH/network events
    command      = Column(String)            # command string for sudo/cron events

    collection = relationship("UACCollection", back_populates="syslog_entries")

    def __repr__(self):
        return f"<SyslogEntry(program='{self.program}', timestamp='{self.timestamp}')>"


class SystemInfo(Base):
    __tablename__ = 'system_info'

    id              = Column(Integer, primary_key=True)
    collection_id   = Column(Integer, ForeignKey('uac_collections.id'), unique=True)
    hostname        = Column(String)
    fqdn            = Column(String)
    primary_ip      = Column(String)
    os_name         = Column(String)
    kernel          = Column(String)
    cpu_arch        = Column(String)
    timezone_name   = Column(String)
    timezone_offset = Column(String)  # ISO 8601 signed offset, e.g. +10:30 or -05:00
    memory_bytes    = Column(Integer)
    domain          = Column(String)
    hardware_model  = Column(String)
    virtualization  = Column(String)

    collection = relationship("UACCollection", back_populates="system_info")

    def __repr__(self):
        return f"<SystemInfo(hostname='{self.hostname}', os='{self.os_name}')>"