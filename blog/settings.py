import os

class Config(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.urandom(32) # this will invalidate session each time good for debugging login stuff
    DATABASE = 'sqlite'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///db.db'

try:
    from blog.local_settings import *
except ImportError:
    pass