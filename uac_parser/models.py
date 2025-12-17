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


    files = relationship("File", back_populates="collection")
    processes = relationship("Process", back_populates="collection")
    network_connections = relationship("NetworkConnection", back_populates="collection")
    authentications = relationship("Authentication", back_populates="collection")
    command_history = relationship("CommandHistory", back_populates="collection")
    users = relationship("User", back_populates="collection")

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
    inode = Column(Integer)
    mode = Column(Integer)
    uid = Column(Integer)
    gid = Column(Integer)
    rdev = Column(Integer)
    nlink = Column(Integer)
    flags = Column(Integer)
    crtime = Column(Integer)
    btime = Column(Integer)
    dtime = Column(Integer)
    btime = Column(Integer)
    btime = Column(Integer)

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