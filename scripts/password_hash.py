"""Create a password hash without writing or echoing the password."""
import getpass
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.auth import password_hash

if __name__ == '__main__':
    print(password_hash(getpass.getpass('Invitation password: ')))
