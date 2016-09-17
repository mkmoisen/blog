from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import Engine
from sqlalchemy import event
from settings import Config
import logging
import os
import traceback

from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config.from_object(Config)
app.secret_key = app.config['SECRET_KEY']
app.config['DATABASE'] = app.config['DATABASE']

print "WTF ", app.config['SQLALCHEMY_DATABASE_URI']



if app.config['DATABASE'] == 'sqlite':
    # Sqlite doesn't enforce Foreign Keys by default. This enables it
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'images')

db = SQLAlchemy(app)
'''
from blog.models import Log
class SQLAlchemyHandler(logging.Handler):
    # http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/logging/sqlalchemy_logger.html
    def emit(self, record):
        trace = None
        exc = record.__dict__['exc_info']
        if exc:
            trace = traceback.format_exc(exc)
        log = Log(logger=record.__dict__['name'],
                  level=record.__dict__['levelname'],
                  trace=trace,
                  message=record.__dict__['msg'])
        db.session.add(log)
        db.session.commit()

db_handler = SQLAlchemyHandler()
db_handler.setLevel(logging.WARN)
app.logger.addHandler(db_handler)

file_handler = RotatingFileHandler( os.path.join(os.path.split(__file__)[0], 'blog.log'), maxBytes=10*1024*1024,
                                    backupCount=5)
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
'''
from blog.views import *