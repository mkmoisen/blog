import os

#db = os.path.join(os.path.abspath(os.path.join(__file__, os.pardir, os.pardir)), 'db.db')
#print db
db = os.path.join(os.path.split(__file__)[0], 'db.db')
class Config(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.urandom(32) # this will invalidate session each time good for debugging login stuff
    DATABASE = 'sqlite'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///{}'.format(db)

try:
    from blog.local_settings import *
except ImportError:
    pass