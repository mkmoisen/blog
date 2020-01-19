from blog import app, db
from functools import wraps
from flask import jsonify, abort, render_template, request, session
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import NotFound
import uuid

date_format = '%Y-%m-%dT%H:%M:%S.%fZ'

class ServerError(Exception):
    pass

class UserError(Exception):
    pass

def try_except(api=False):
    def real_decorator(func):
        @wraps(func)
        def _try_except(*args, **kwargs):
            try:
                return func(*args, **kwargs)
            except NoResultFound as ex:
                db.session.rollback()
                app.logger.exception("NoResultFound in {} for path {}".format(func.__name__, request.path))
                if not api:
                    abort(404)
                return jsonify({"error": str(ex)}), 400
            except UserError as ex:
                db.session.rollback()
                app.logger.exception("UserError in {} for path {}: {}".format(func.__name__, ex.message, request.path))
                if not api:
                    abort(400)
                return jsonify({"error": str(ex)}), 400
            except ServerError as ex:
                db.session.rollback()
                app.logger.exception("ServerError in {} for path {}: {}".format(func.__name__, ex.message, request.path))
                if not api:
                    abort(400)
                return jsonify({"error": str(ex)}), 500
            except NotFound as ex:
                # This is kind of strange.
                # If one route returns (not redirects) to another route who throws a NoResultFound
                # Execution appears to go into the NoResultFound block above, but then into the Exception block below
                # This will catch it and handle it appropriately
                db.session.rollback()
                app.logger.exception("NotFound in {} for path {}".format(func.__name__, request.path))
                if not api:
                    abort(404)
                return jsonify({"error": str(ex)}), 400
            except Exception as ex:
                db.session.rollback()
                app.logger.exception("Exception in {} for path {}: {}".format(func.__name__, ex.message, request.path))
                if not api:
                    abort(500)
                return jsonify({"error": str(ex)}), 500

        return _try_except
    return real_decorator

@app.errorhandler(404)
def page_not_found(error):
    app.logger.debug("I AM 404 LOL")
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(error):
    app.logger.debug("I AM 500 LOL")
    return render_template('500.html'), 500

def check_admin_status():
    return 'is_admin' in session and session['is_admin']


@app.context_processor
def inject_global_vars():
    return {
        'web_protocol': app.config['WEB_PROTOCOL'],
        'domain': app.config['DOMAIN'],
        'google_site_verification': app.config['GOOGLE_SITE_VERIFICATION'],
        'is_admin': check_admin_status(),
    }


def _check_referrer():
    is_success = True
    if not request.referrer:
        is_success = False

    if is_success:
        refferer_uri = urlparse(request.referrer)
        good_uri = urlparse(app.config['WEB_PROTOCOL'] + app.config['DOMAIN'])

        if refferer_uri.scheme != good_uri.scheme:
            is_success = False

        if refferer_uri.hostname != good_uri.hostname:
            is_success = False

        if refferer_uri.port != good_uri.port:
            is_success = False

    if not is_success:
        app.logger.error("CSRF Violation from remote user {} at referrer {}".format(request.remote_addr, request.referrer))

    return is_success


def _check_csrf(request_type):
    true_csrf = session.get('csrf_token', None)
    given_csrf = getattr(request, request_type).get('_csrf_token')
    if not true_csrf or true_csrf != given_csrf:
        app.logger.error("CSRF Violation: true is {} but given is {}".format(true_csrf, given_csrf))
        return False

    return True


from urllib.parse import urlparse
def csrf(request_type='json'):
    if request_type not in ('json', 'form'):
        raise ServerError("csrf request_type must be either json or form, not {}".format(request_type))
    def real_csrf(func):
        @wraps(func)
        def _csrf(*args, **kwargs):
            print("NOOB SESSION IS ", session)
            if not _check_referrer() or not _check_csrf(request_type):
                app.logger.exception("Csrf failure in {}".format(func.__name__))
                abort(400)

            return func(*args, **kwargs)

        return _csrf
    return real_csrf

def generate_csrf_token():
    if 'csrf_token' not in session:
        session['csrf_token'] = str(uuid.uuid4())
    return session['csrf_token']

app.jinja_env.globals['csrf_token'] = generate_csrf_token









'''
def try_except(func):
    @wraps(func)
    def _try_except(*args, **kwargs):
        try:
            app.logger.debug("In {}, args={}, kwargs={}".format(func.func_name, args, kwargs))
            return func(*args, **kwargs)

        except BadRequest as ex:
            app.logger.exception(ex)
            return jsonify({'error': 'Invalid JSON request {}'.format(ex.message)}), 400

        except UserError as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 400

        except ServerError as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

        except SQLAlchemyError as ex:
            #This is a server error
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

        except Exception as ex:
            app.logger.exception(ex.message)
            db.session.rollback()
            return jsonify({'error': ex.message}), 500

    return _try_except
'''
from . import home