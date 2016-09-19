from flask import Flask, request, session
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.engine import Engine
from sqlalchemy import event
from settings import server_config
import logging
import os
import traceback

from logging.handlers import RotatingFileHandler

app = Flask(__name__)
app.config.from_object(server_config)
app.secret_key = app.config['SECRET_KEY']
app.config['DATABASE'] = app.config['DATABASE']
if not app.config['DOMAIN'].endswith('/'):
    app.config['DOMAIN'] += '/'



if app.config['DATABASE'] == 'sqlite':
    # Sqlite doesn't enforce Foreign Keys by default. This enables it
    @event.listens_for(Engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

app.config['UPLOAD_FOLDER'] = os.path.join(app.static_folder, 'images')

db = SQLAlchemy(app)

from blog.views import *
from blog.models import Log
class SQLAlchemyHandler(logging.Handler):
    # http://docs.pylonsproject.org/projects/pyramid_cookbook/en/latest/logging/sqlalchemy_logger.html
    def emit(self, record):
        trace = None
        exc = record.__dict__['exc_info']
        if exc:
            trace = traceback.format_exc(exc)

        path = request.path
        method = request.method
        ip = request.remote_addr
        is_admin = False
        if session and session.get('is_admin', False):
            is_admin = True

        log = Log(logger=record.__dict__['name'],
                  level=record.__dict__['levelname'],
                  trace=trace,
                  message=record.__dict__['msg'],
                  path=path,
                  method=method,
                  ip=ip,
                  is_admin=is_admin
        )
        db.session.add(log)
        db.session.commit()

db_handler = SQLAlchemyHandler()
db_handler.setLevel(logging.WARN)
app.logger.addHandler(db_handler)

file_handler = RotatingFileHandler( os.path.join(os.path.split(__file__)[0], 'blog.log'), maxBytes=10*1024*1024,
                                    backupCount=5)
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s %(levelname)-8s %(message)s')
file_handler.setFormatter(formatter)
app.logger.addHandler(file_handler)