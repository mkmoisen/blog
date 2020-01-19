
from datetime import datetime, timedelta
from flask.sessions import SessionInterface, SessionMixin
from werkzeug.datastructures import CallbackDict
import sqlalchemy
import json
import uuid
from blog.models import DBSession
from sqlalchemy.orm.exc import NoResultFound


# http://flask.pocoo.org/snippets/110/
class SqlAlchemySession(CallbackDict, SessionMixin):
    def __init__(self, initial=None, sid=None):
        super(SqlAlchemySession, self).__init__(initial)
        self.sid = sid
        self.modified = False


class SqlAlchemySessionInterface(SessionInterface):
    def __init__(self, db):
        self.db = db

    def open_session(self, app, request):
        sid = request.cookies.get(app.session_cookie_name)
        renew_sid = True
        if sid:
            try:
                stored_session = DBSession.query.filter_by(sid=sid).one()
            except NoResultFound:
                stored_session = None
            if stored_session:
                print("stored session is ", stored_session)
                data = json.loads(stored_session.data)
                if stored_session.expiration_date > datetime.utcnow():
                    return SqlAlchemySession(initial=data, sid=stored_session.sid)
                renew_sid = False

        if renew_sid:
            sid = str(uuid.uuid4())

        return SqlAlchemySession(sid=sid)

    def save_session(self, app, session, response):
        domain = self.get_cookie_domain(app)

        if not session:
            response.delete_cookie(app.session_cookie_name, domain=domain)
            return

        if self.get_expiration_time(app, session):
            expiration = self.get_expiration_time(app, session)
        else:
            expiration = datetime.utcnow() + timedelta(hours=12)
            #expiration = datetime.utcnow() + timedelta(seconds=15)

        try:
            stored_session = DBSession.query.filter_by(sid=session.sid).one()
        except NoResultFound:
            stored_session = None

        if not stored_session:
            stored_session = DBSession(sid=session.sid)

        # Serialize the session dict to json and store that in the rdbms' clob field
        data = json.dumps(session)
        stored_session.data = data
        stored_session.expiration_date = expiration
        # Write session to DB

        self.db.session.add(stored_session)
        self.db.session.commit()


        response.set_cookie(app.session_cookie_name, session.sid, expires=self.get_expiration_time(app, session),
                            httponly=True, domain=domain)

