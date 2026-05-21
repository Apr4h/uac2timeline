from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

Base = declarative_base()

DEFAULT_DB_NAME = "uac.db"



def init_db(db_path):
    db_url=f'sqlite:///{db_path}'
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    return engine

def get_session(engine):
    Session = sessionmaker(bind=engine)
    return Session()

def check_existing_collection(uac_log_md5: str, db_path: str = DEFAULT_DB_NAME):
    """
    Check if a collection with the given MD5 hash already exists in the database.
    
    Args:
        uac_log_md5: MD5 hash of the uac.log file
        db_path: Path to the database file
        
    Returns:
        UACCollection object if found, None otherwise
    """
    from .models import UACCollection
    
    engine = init_db(db_path)
    session = get_session(engine)
    
    existing = session.query(UACCollection).filter_by(uac_log_md5=uac_log_md5).first()
    session.close()
    
    return existing
