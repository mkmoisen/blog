import os

db = os.path.join(os.path.split(__file__)[0], 'db.db')

class Config(object):
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    BASEDIR = os.path.abspath(os.path.dirname(__file__))
    SECRET_KEY = os.urandom(32) # this will invalidate session each time good for debugging login stuff
    DATABASE = 'sqlite'
    SQLALCHEMY_DATABASE_URI = 'sqlite:///{}'.format(db)
    WEB_PROTOCOL = 'http://'  # 'http://'
    ENABLE_GOOGLE_SITEMAP_PING = False
    PREFERRED_URL_SCHEME = 'http'
    DOMAIN = 'localhost:5000/'
    GOOGLE_SITE_VERIFICATION = None


class ProductionConfig(Config):
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    ENABLE_GOOGLE_SITEMAP_PING = True
    WEB_PROTOCOL = 'https://'
    # DOMAIN = 'matthewmoisen.com/'
    # GOOGLE_SITE_VERIFICATION = 'abd1234'

server_config = Config


print("server_config is %s" % server_config.__name__)

try:
    from blog.local_settings import *
except ImportError:
    pass

print("server_config is %s" % server_config.__name__)