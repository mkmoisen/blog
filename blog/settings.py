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
    DOMAIN = 'matthewmoisen.com/'
    GOOGLE_SITE_VERIFICATION = 'uV8BaAWi7Oqilx1jL9gnMB1l4RQR154v3tunwZKvCpQ'


server_config = Config

try:
    from blog.local_settings import *
except ImportError:
    pass